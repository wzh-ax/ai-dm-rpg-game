"""
Hook 机制 - 输入 → 信号 → 触发子 Agent
允许在游戏流程的特定节点插入自定义逻辑
"""

import asyncio
import logging
from typing import Callable, Any
from dataclasses import dataclass, field

from .event_bus import Event

logger = logging.getLogger(__name__)


@dataclass
class Hook:
    """单个 Hook 定义"""
    name: str
    callback: Callable[..., Any]
    phase: str  # "before" | "after"
    order: int = 0  # 执行顺序,数字越小越先执行


class HookRegistry:
    """
    Hook 注册器
    
    Hook 是游戏流程中的"钩子点",允许在特定节点触发自定义逻辑。
    
    使用方式:
    1. 注册 hook: registry.register("before_input_processing", my_callback)
    2. 触发 hook: await registry.trigger("before_input_processing", event)
    """
    
    def __init__(self):
        self._hooks: dict[str, list[Hook]] = {}
        
    def register(
        self,
        name: str,
        callback: Callable[..., Any],
        phase: str = "after",
        order: int = 0
    ):
        """
        注册 Hook
        
        Args:
            name: Hook 名称(如 "before_input_processing")
            callback: 回调函数
            phase: "before" 或 "after"
            order: 执行顺序
        """
        hook = Hook(name=name, callback=callback, phase=phase, order=order)
        
        if name not in self._hooks:
            self._hooks[name] = []
        self._hooks[name].append(hook)
        
        # 按 order 排序
        self._hooks[name].sort(key=lambda h: h.order)
        logger.debug(f"Registered hook '{name}' (phase={phase}, order={order})")
        
    def unregister(self, name: str, callback: Callable):
        """取消注册 Hook"""
        if name in self._hooks:
            self._hooks[name] = [
                h for h in self._hooks[name] if h.callback != callback
            ]
            
    async def trigger(self, name: str, *args, **kwargs) -> list[Any]:
        """
        触发 Hook
        
        Returns:
            所有回调的返回值列表
        """
        if name not in self._hooks:
            return []
            
        results = []
        for hook in self._hooks[name]:
            try:
                result = hook.callback(*args, **kwargs)
                if asyncio.iscoroutine(result):
                    result = await result
                results.append(result)
            except Exception as e:
                logger.error(f"Hook '{name}' error: {e}")
                
        return results
    
    def list_hooks(self) -> dict[str, int]:
        """列出所有已注册的 Hook(调试用)"""
        return {name: len(hooks) for name, hooks in self._hooks.items()}


# 预定义的 Hook 名称常量
class HookNames:
    """预定义 Hook 名称"""
    # 输入处理
    BEFORE_INPUT_PROCESSING = "before_input_processing"
    AFTER_INPUT_PROCESSING = "after_input_processing"
    
    # 叙事输出
    BEFORE_NARRATIVE_OUTPUT = "before_narrative_output"
    AFTER_NARRATIVE_OUTPUT = "after_narrative_output"
    
    # 子 Agent
    BEFORE_SUBNET_CALL = "before_subnet_call"
    AFTER_SUBNET_CALL = "after_subnet_call"
    
    # 场景
    BEFORE_SCENE_UPDATE = "before_scene_update"
    AFTER_SCENE_UPDATE = "after_scene_update"
    
    # NPC
    BEFORE_NPC_GENERATION = "before_npc_generation"
    AFTER_NPC_GENERATION = "after_npc_generation"
    BEFORE_NPC_RESPONSE = "before_npc_response"
    AFTER_NPC_RESPONSE = "after_npc_response"

    # 物品
    BEFORE_ITEM_USE = "before_item_use"
    AFTER_ITEM_USE = "after_item_use"


# 全局单例
_global_registry: HookRegistry | None = None


def get_hook_registry() -> HookRegistry:
    """获取全局 Hook 注册器"""
    global _global_registry
    if _global_registry is None:
        _global_registry = HookRegistry()
    return _global_registry
