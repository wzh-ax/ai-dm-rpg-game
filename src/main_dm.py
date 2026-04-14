"""
Main DM Agent - 主 Dungeon Master
负责任务分发、流程编排、最终叙事输出
"""

import asyncio
import logging
from typing import TYPE_CHECKING

from .event_bus import EventBus, EventType, Event, get_event_bus

if TYPE_CHECKING:
    from .hooks import HookRegistry

logger = logging.getLogger(__name__)


class MainDM:
    """
    主 DM Agent
    
    职责:
    1. 接收玩家输入(通过 EventBus 订阅 player_input)
    2. 分析输入,决定触发哪些子 Agent
    3. 协调子 Agent 执行
    4. 汇总结果,生成最终叙事
    5. 输出叙事(通过 EventBus 发布 narrative_output)
    """
    
    def __init__(self, event_bus: EventBus | None = None):
        self.event_bus = event_bus or get_event_bus()
        self.subscriber_id = "main_dm"
        self.hooks: HookRegistry | None = None
        self._running = False
        
        # 状态
        self.current_scene: dict = {}
        self.game_state: dict = {
            "turn": 0,
            "story_history": [],
        }
        
    async def start(self):
        """启动 Main DM"""
        if self._running:
            return
            
        # 订阅玩家输入
        await self.event_bus.subscribe(
            EventType.PLAYER_INPUT,
            self._on_player_input,
            self.subscriber_id
        )
        
        # 订阅子 Agent 结果
        await self.event_bus.subscribe(
            EventType.SUBNET_AGENT_RESULT,
            self._on_subagent_result,
            self.subscriber_id
        )
        
        self._running = True
        logger.info("Main DM started")
        
    async def stop(self):
        """停止 Main DM"""
        self._running = False
        await self.event_bus.unsubscribe_all(self.subscriber_id)
        logger.info("Main DM stopped")
        
    def set_hooks(self, hooks: "HookRegistry"):
        """设置 Hook 注册器"""
        self.hooks = hooks
        
    async def _on_player_input(self, event: Event):
        """处理玩家输入事件"""
        player_text = event.data.get("text", "")
        logger.info(f"Main DM received player input: {player_text[:50]}...")
        
        self.game_state["turn"] += 1
        turn = self.game_state["turn"]
        
        # 触发前置 Hook
        if self.hooks:
            await self.hooks.trigger("before_input_processing", event)
        
        # 简单处理:直接生成叙事
        # TODO: 后续替换为真正的子 Agent 调用
        narrative = await self._generate_narrative(player_text, turn)
        
        # 发布叙事输出
        await self.event_bus.publish(Event(
            type=EventType.NARRATIVE_OUTPUT,
            data={
                "text": narrative,
                "turn": turn,
                "scene": self.current_scene,
            },
            source=self.subscriber_id
        ))
        
        # 触发后置 Hook
        if self.hooks:
            await self.hooks.trigger("after_narrative_output", event)
            
    async def _on_subagent_result(self, event: Event):
        """处理子 Agent 结果"""
        agent_name = event.data.get("agent", "unknown")
        result = event.data.get("result", {})
        logger.info(f"Main DM received result from {agent_name}")
        
        # 可以在这里合并子 Agent 的结果
        # TODO: 实现结果聚合逻辑
        
    async def _generate_narrative(self, player_input: str, turn: int) -> str:
        """
        生成叙事(临时实现,后续接入 LLM)
        
        TODO:
        - 接入 MiniMax API
        - 实现真正的叙事生成逻辑
        """
        # 模拟 LLM 调用延迟
        await asyncio.sleep(0.1)
        
        # 临时返回模拟叙事
        narratives = [
            f"夜色笼罩着古老的城堡,你(回合 {turn})踏入阴暗的大厅...",
            f"烛火摇曳,一阵寒风从身后袭来。你感觉到背后有目光注视着你...",
            f"脚步声在石廊中回荡,你紧握手中的武器,警惕地观察四周...",
        ]
        
        return narratives[turn % len(narratives)] + f"\n\n> 玩家输入: {player_input}"
        
    async def handle_player_message(self, text: str):
        """外部接口:处理玩家消息"""
        await self.event_bus.publish(Event(
            type=EventType.PLAYER_INPUT,
            data={"text": text},
            source="player"
        ))


# 全局单例
_global_dm: MainDM | None = None


def get_main_dm() -> MainDM:
    """获取全局 Main DM 实例"""
    global _global_dm
    if _global_dm is None:
        _global_dm = MainDM()
    return _global_dm


async def init_main_dm() -> MainDM:
    """初始化并启动全局 Main DM"""
    dm = get_main_dm()
    await dm.start()
    return dm
