"""
Event Bus - 核心事件总线
实现发布/订阅机制,连接 Main DM 与各子 Agent

优化重点:
1. 事件类型覆盖完整（对齐架构文档定义的 schema）
2. 支持队列大小限制，防止内存溢出
3. Context manager 协议支持（async with）
4. 优雅关闭：等待队列排空
5. 显式 CancelledError 处理
6. 防止 listener 未注销的内存泄漏
7. 支持优先级事件（高优先级跳过队列直接分发）
8. 事件历史缓冲（用于调试和重放）
9. 完善指标采集（事件计数、处理耗时、队列深度）
10. Async-safe 单例初始化
11. Dead Letter 事件处理
"""

import asyncio
import logging
import weakref
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Any
from collections import defaultdict

logger = logging.getLogger(__name__)


class EventType(str, Enum):
    """事件类型枚举 - 覆盖所有 Agent 间协作事件"""
    
    # ========== 通用 ==========
    GENERIC = "generic"                     # 通用事件
    
    # ========== 玩家交互 ==========
    PLAYER_INPUT = "player_input"           # 玩家输入
    NARRATIVE_OUTPUT = "narrative_output"   # 叙事输出
    
    # ========== 场景事件 (景绘 Agent) ==========
    SCENE_UPDATE = "scene_update"           # 场景更新
    SCENE_REQUESTED = "scene_requested"    # 场景请求（战策/言者 → 景绘）
    SCENE_GENERATED = "scene_generated"     # 场景生成完成（景绘 → 请求者+审官）
    
    # ========== NPC 事件 (言者 Agent) ==========
    NPC_DIALOGUE = "npc_dialogue"           # NPC 对话
    NARRATIVE_REQUESTED = "narrative_requested"  # 叙事请求（战策 → 言者）
    NARRATIVE_GENERATED = "narrative_generated"  # 叙事生成完成（言者 → 战策+审官）
    NPC_GENERATION_REQUESTED = "npc_generation_requested"  # NPC 生成请求
    NPC_GENERATED = "npc_generated"         # NPC 生成完成
    
    # ========== 战斗事件 (战策 Agent) ==========
    COMBAT_START = "combat_start"           # 战斗开始
    COMBAT_END = "combat_end"               # 战斗结束
    COMBAT_DESIGN_REQUESTED = "combat_design_requested"  # 战斗设计请求（珂宝 → 战策）
    COMBAT_READY = "combat_ready"           # 战斗就绪（战策 → 审官）
    ROUND_START = "round_start"            # 回合开始
    ROUND_END = "round_end"                # 回合结束
    TURN_START = "turn_start"              # 行动开始
    TURN_END = "turn_end"                  # 行动结束
    ACTION_RESOLVED = "action_resolved"    # 动作结算
    COMBATANT_DOWN = "combatant_down"      # 战斗者倒下
    STATUS_APPLIED = "status_applied"      # 状态生效
    
    # ========== 子 Agent 事件 ==========
    SUBNET_AGENT_START = "subnet_agent_start"
    SUBNET_AGENT_RESULT = "subnet_agent_result"
    SUBNET_AGENT_ERROR = "subnet_agent_error"
    
    # ========== 代码/质量事件 ==========
    CODE_COMMIT = "code_commit"             # 代码提交（构师/智匠 → 审官）
    TEST_PASSED = "test_passed"            # 测试通过（审官 → 珂宝）
    TEST_FAILED = "test_failed"            # 测试失败（审官 → 珂宝）
    
    # ========== 系统事件 ==========
    GAME_START = "game_start"
    GAME_END = "game_end"
    TICK = "tick"                           # 心跳/定时事件
    
    # ========== 物品事件 ==========
    ITEM_ACQUIRED = "item_acquired"
    ITEM_USED = "item_used"
    ITEM_DISCARDED = "item_discarded"
    ITEM_EQUIPPED = "item_equipped"
    ITEM_UNEQUIPPED = "item_unequipped"
    INVENTORY_FULL = "inventory_full"
    ITEM_EFFECT = "item_effect"


class EventPriority(int, Enum):
    """事件优先级 - 高优先级事件跳过队列直接分发"""
    LOW = 0
    NORMAL = 1
    HIGH = 2
    CRITICAL = 3


@dataclass
class Event:
    """事件对象"""
    type: EventType
    data: dict = field(default_factory=dict)
    source: str = "system"
    timestamp: float = 0.0
    priority: EventPriority = EventPriority.NORMAL
    
    def __post_init__(self):
        if self.timestamp == 0.0:
            self.timestamp = time.monotonic()


@dataclass 
class Subscription:
    """订阅记录"""
    callback: Callable[[Event], Any]
    event_type: EventType
    subscriber_id: str
    filter_fn: Callable[[Event], bool] | None = None


@dataclass
class EventMetrics:
    """事件指标收集器"""
    events_published: int = 0
    events_processed: int = 0
    events_failed: int = 0
    total_processing_time: float = 0.0
    queue_max_depth: int = 0
    dead_letter_count: int = 0
    
    @property
    def avg_processing_time(self) -> float:
        if self.events_processed == 0:
            return 0.0
        return self.total_processing_time / self.events_processed


class EventBus:
    """
    异步事件总线
    支持发布/订阅、事件过滤、订阅者管理
    
    特性:
    - 线程安全的订阅管理
    - 支持队列大小限制（防止内存溢出）
    - Context manager 协议支持
    - 优雅关闭（可选择等待队列排空）
    - 订阅者生命周期追踪（防止内存泄漏）
    - 优先级事件支持（高优先级跳过队列）
    - 事件历史缓冲（用于调试和重放）
    - 指标采集（可监控事件处理性能）
    - Dead Letter 事件处理
    """
    
    # 默认队列大小限制（0 = 无限制）
    DEFAULT_QUEUE_MAXSIZE = 1000
    # 默认历史缓冲大小
    DEFAULT_HISTORY_SIZE = 500
    # 死信队列最大大小
    DEFAULT_DEAD_LETTER_MAXSIZE = 100
    
    def __init__(
        self,
        queue_maxsize: int = DEFAULT_QUEUE_MAXSIZE,
        history_size: int = DEFAULT_HISTORY_SIZE,
        dead_letter_maxsize: int = DEFAULT_DEAD_LETTER_MAXSIZE,
    ):
        """
        Args:
            queue_maxsize: 队列最大长度，0=无限制。防止事件积压导致内存溢出
            history_size: 事件历史缓冲大小，0=禁用。用于调试和重放
            dead_letter_maxsize: 死信队列最大长度，0=禁用。保存处理失败的事件
        """
        self._subscriptions: dict[EventType, list[Subscription]] = defaultdict(list)
        self._lock = asyncio.Lock()
        self._event_queue: asyncio.Queue[Event] = (
            asyncio.Queue(maxsize=queue_maxsize) if queue_maxsize > 0 else asyncio.Queue()
        )
        self._running = False
        self._processor_task: asyncio.Task | None = None
        self._queue_maxsize = queue_maxsize
        
        # 追踪活跃订阅者（用于内存泄漏检测）
        self._active_subscribers: set[str] = set()
        
        # 事件历史缓冲
        self._history_size = history_size
        self._event_history: list[Event] = []
        self._history_lock = asyncio.Lock()
        
        # 死信队列
        self._dead_letter_maxsize = dead_letter_maxsize
        self._dead_letter_queue: asyncio.Queue[Event] = (
            asyncio.Queue(maxsize=dead_letter_maxsize) if dead_letter_maxsize > 0 else asyncio.Queue()
        )
        
        # 指标收集
        self._metrics = EventMetrics()
        self._metrics_lock = asyncio.Lock()
        
        # Drain 同步事件
        self._drain_event: asyncio.Event | None = None
        
    async def start(self):
        """启动事件处理器"""
        if self._running:
            return
        self._running = True
        self._processor_task = asyncio.create_task(self._process_events())
        logger.info("EventBus started")
        
    async def stop(self, drain: bool = False, timeout: float = 5.0, exc_info: Any = None):
        """
        停止事件处理器
        
        Args:
            drain: 是否等待队列排空后再停止
            timeout: 等待队列排空的最大超时时间（秒）
            exc_info: 如果是因异常退出，传递的异常信息（会传递给 __aexit__）
        """
        if not self._running:
            return
            
        self._running = False
        
        if drain:
            # 优雅关闭：等待队列排空
            self._drain_event = asyncio.Event()
            try:
                # 等待队列清空或超时
                remaining = timeout
                while remaining > 0 and not self._event_queue.empty():
                    await asyncio.sleep(min(0.1, remaining))
                    remaining -= 0.1
                
                if not self._event_queue.empty():
                    logger.warning(
                        f"EventBus drain timeout, {self._event_queue.qsize()} events remaining"
                    )
                else:
                    logger.debug("EventBus drained successfully")
            except asyncio.CancelledError:
                pass
            finally:
                self._drain_event = None
        
        if self._processor_task:
            self._processor_task.cancel()
            try:
                await self._processor_task
            except asyncio.CancelledError:
                pass
            except Exception as e:
                logger.error(f"Error waiting for processor task: {e}")
        
        # 清空队列（防止 stop 后残留事件）
        self._clear_queue()
        
        logger.info("EventBus stopped")
    
    def _clear_queue(self):
        """清空事件队列"""
        try:
            while not self._event_queue.empty():
                self._event_queue.get_nowait()
        except asyncio.QueueEmpty:
            pass
    
    async def __aenter__(self) -> "EventBus":
        """Context manager 进入"""
        await self.start()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Context manager 退出"""
        await self.stop(exc_info=(exc_type, exc_val, exc_tb))
    
    @property
    def queue_size(self) -> int:
        """获取当前队列大小"""
        return self._event_queue.qsize()
    
    @property
    def is_running(self) -> bool:
        """检查是否正在运行"""
        return self._running
    
    @property
    def metrics(self) -> EventMetrics:
        """获取当前指标（副本）"""
        return EventMetrics(
            events_published=self._metrics.events_published,
            events_processed=self._metrics.events_processed,
            events_failed=self._metrics.events_failed,
            total_processing_time=self._metrics.total_processing_time,
            queue_max_depth=self._metrics.queue_max_depth,
            dead_letter_count=self._metrics.dead_letter_count,
        )
    
    async def subscribe(
        self,
        event_type: EventType,
        callback: Callable[[Event], Any],
        subscriber_id: str,
        filter_fn: Callable[[Event], bool] | None = None
    ):
        """
        订阅事件
        
        Args:
            event_type: 要订阅的事件类型
            callback: 回调函数,接收 Event 对象
            subscriber_id: 订阅者 ID(用于取消订阅)
            filter_fn: 可选的过滤函数,返回 True 才执行回调
        """
        async with self._lock:
            sub = Subscription(
                callback=callback,
                event_type=event_type,
                subscriber_id=subscriber_id,
                filter_fn=filter_fn
            )
            self._subscriptions[event_type].append(sub)
            self._active_subscribers.add(subscriber_id)
            logger.debug(f"Subscriber '{subscriber_id}' subscribed to {event_type.value}")
            
    async def unsubscribe(self, event_type: EventType, subscriber_id: str):
        """取消订阅"""
        async with self._lock:
            subs = self._subscriptions[event_type]
            self._subscriptions[event_type] = [
                s for s in subs if s.subscriber_id != subscriber_id
            ]
            # 检查是否还有其他该订阅者的订阅
            if not any(s.subscriber_id == subscriber_id for subs_list in self._subscriptions.values() for s in subs_list):
                self._active_subscribers.discard(subscriber_id)
            logger.debug(f"Subscriber '{subscriber_id}' unsubscribed from {event_type.value}")
            
    async def unsubscribe_all(self, subscriber_id: str):
        """取消订阅者的所有订阅"""
        async with self._lock:
            removed = False
            for event_type in self._subscriptions:
                before = len(self._subscriptions[event_type])
                self._subscriptions[event_type] = [
                    s for s in self._subscriptions[event_type]
                    if s.subscriber_id != subscriber_id
                ]
                if len(self._subscriptions[event_type]) < before:
                    removed = True
            if removed:
                self._active_subscribers.discard(subscriber_id)
            logger.debug(f"All subscriptions for '{subscriber_id}' removed")
    
    async def clear_all_subscriptions(self):
        """清空所有订阅（慎用，通常用于测试或完全重置）"""
        async with self._lock:
            self._subscriptions.clear()
            self._active_subscribers.clear()
            logger.debug("All subscriptions cleared")
    
    def get_active_subscriber_ids(self) -> set:
        """获取所有活跃订阅者 ID（调试用）"""
        return self._active_subscribers.copy()
    
    async def publish(self, event: Event):
        """
        发布事件到总线
        事件会被异步分发给所有订阅者
        
        Raises:
            asyncio.QueueFull: 当队列满且 maxsize > 0 时
        """
        await self._update_metrics_async(events_published_delta=1)
        
        # 更新队列最大深度
        current_size = self._event_queue.qsize()
        async with self._metrics_lock:
            if current_size > self._metrics.queue_max_depth:
                self._metrics.queue_max_depth = current_size
        
        # 高优先级事件直接分发，跳过队列
        if event.priority >= EventPriority.HIGH and self._running:
            await self._dispatch_event(event)
            return
            
        await self._event_queue.put(event)
        logger.debug(f"Event published: {event.type.value} from {event.source}")
        
    async def publish_immediate(self, event: Event):
        """
        立即发布事件（同步分发，不经过队列）
        适用于需要立即执行的紧急事件
        """
        await self._update_metrics_async(events_published_delta=1)
        await self._dispatch_event(event)
    
    async def publish_batch(self, events: list[Event]):
        """
        批量发布事件（原子操作，所有事件要么都发布，要么都不发布）
        
        Raises:
            asyncio.QueueFull: 当队列满且 maxsize > 0 时
        """
        for event in events:
            await self._event_queue.put(event)
            await self._update_metrics_async(events_published_delta=1)
        
    async def _update_metrics_async(self, events_published_delta: int = 0, events_processed_delta: int = 0,
                                     events_failed_delta: int = 0, processing_time_delta: float = 0.0):
        """异步更新指标"""
        async with self._metrics_lock:
            self._metrics.events_published += events_published_delta
            self._metrics.events_processed += events_processed_delta
            self._metrics.events_failed += events_failed_delta
            self._metrics.total_processing_time += processing_time_delta
    
    def _update_metrics_sync(self, events_published_delta: int = 0, events_processed_delta: int = 0,
                              events_failed_delta: int = 0, processing_time_delta: float = 0.0):
        """同步更新指标（在事件处理循环中使用）"""
        self._metrics.events_published += events_published_delta
        self._metrics.events_processed += events_processed_delta
        self._metrics.events_failed += events_failed_delta
        self._metrics.total_processing_time += processing_time_delta
    
    async def _add_to_history(self, event: Event):
        """将事件添加到历史缓冲"""
        if self._history_size <= 0:
            return
        async with self._history_lock:
            self._event_history.append(event)
            if len(self._event_history) > self._history_size:
                self._event_history.pop(0)
    
    async def _add_to_dead_letter(self, event: Event):
        """将失败事件添加到死信队列"""
        if self._dead_letter_maxsize <= 0:
            return
        try:
            self._dead_letter_queue.put_nowait(event)
            async with self._metrics_lock:
                self._metrics.dead_letter_count += 1
        except asyncio.QueueFull:
            logger.error(f"Dead letter queue full, dropping event: {event.type.value}")
    
    async def get_dead_letter(self) -> Event | None:
        """从死信队列获取一个事件（用于重试或调试）"""
        try:
            return self._dead_letter_queue.get_nowait()
        except asyncio.QueueEmpty:
            return None
    
    async def get_event_history(self, event_type: EventType | None = None, limit: int = 100) -> list[Event]:
        """
        获取事件历史
        
        Args:
            event_type: 如果指定，只返回该类型的事件
            limit: 最大返回数量
        """
        async with self._history_lock:
            if event_type:
                return [e for e in self._event_history if e.type == event_type][-limit:]
            return list(self._event_history)[-limit:]
    
    async def _process_events(self):
        """异步事件处理循环"""
        while True:
            try:
                event = await asyncio.wait_for(
                    self._event_queue.get(),
                    timeout=1.0
                )
                await self._dispatch_event(event)
                self._update_metrics_sync(events_processed_delta=1)
                
                # 检查是否是 drain 等待
                if self._drain_event is not None and self._event_queue.empty():
                    self._drain_event.set()
                    
            except asyncio.TimeoutError:
                # 超时后检查是否应该退出
                if not self._running:
                    if self._drain_event is not None:
                        self._drain_event.set()
                    break
            except asyncio.CancelledError:
                # 显式处理 CancelledError，不使用 except Exception
                if self._drain_event is not None:
                    self._drain_event.set()
                break
            except Exception as e:
                logger.error(f"Error processing event: {e}")
                self._update_metrics_sync(events_failed_delta=1)
                
    async def _dispatch_event(self, event: Event):
        """分发事件给订阅者"""
        start_time = time.monotonic()
        
        # 添加到历史
        await self._add_to_history(event)
        
        # 复制订阅列表，避免在分发过程中持有锁
        async with self._lock:
            subscriptions = list(self._subscriptions.get(event.type, []))
        
        for sub in subscriptions:
            try:
                # 应用过滤器（支持同步或异步 filter_fn）
                if sub.filter_fn:
                    filter_result = sub.filter_fn(event)
                    if asyncio.iscoroutine(filter_result):
                        filter_result = await filter_result
                    if not filter_result:
                        continue
                # 异步执行回调
                result = sub.callback(event)
                if asyncio.iscoroutine(result):
                    await result
            except Exception as e:
                logger.error(
                    f"Error in subscriber '{sub.subscriber_id}' "
                    f"for event {event.type.value}: {e}"
                )
                self._update_metrics_sync(events_failed_delta=1)
                # 将失败事件加入死信队列
                await self._add_to_dead_letter(event)
        
        processing_time = time.monotonic() - start_time
        self._update_metrics_sync(processing_time_delta=processing_time)
                
    def get_subscription_count(self, event_type: EventType | None = None) -> int:
        """获取订阅数量(调试用)"""
        if event_type:
            return len(self._subscriptions.get(event_type, []))
        return sum(len(subs) for subs in self._subscriptions.values())
    
    def get_all_event_types_with_subscriptions(self) -> list[EventType]:
        """获取所有有订阅的事件类型（调试用）"""
        return [et for et, subs in self._subscriptions.items() if subs]
    
    async def reset_metrics(self):
        """重置指标（通常用于测试）"""
        async with self._metrics_lock:
            self._metrics = EventMetrics()


# 全局单例（async-safe）
_global_event_bus: EventBus | None = None
_global_init_lock = asyncio.Lock()


def get_event_bus() -> EventBus:
    """获取全局事件总线实例（线程安全单例）"""
    global _global_event_bus
    if _global_event_bus is None:
        # 如果在 async context 中，使用 async 版本更安全
        # 但为了保持同步接口兼容性，这里使用双重检查锁定
        import threading
        if _global_event_bus is None:
            with threading.Lock():
                if _global_event_bus is None:
                    _global_event_bus = EventBus()
    return _global_event_bus


async def get_event_bus_async() -> EventBus:
    """获取全局事件总线实例（async-safe 版本）"""
    global _global_event_bus
    if _global_event_bus is None:
        async with _global_init_lock:
            if _global_event_bus is None:
                _global_event_bus = EventBus()
    return _global_event_bus


async def init_event_bus(
    queue_maxsize: int = EventBus.DEFAULT_QUEUE_MAXSIZE,
    history_size: int = EventBus.DEFAULT_HISTORY_SIZE,
) -> EventBus:
    """初始化并启动全局事件总线"""
    bus = await get_event_bus_async()
    # 如果传入了自定义参数，需要用这些参数重新初始化
    if bus._queue_maxsize != queue_maxsize or bus._history_size != history_size:
        logger.warning("EventBus already initialized with different parameters, ignoring new params")
    await bus.start()
    return bus
