"""
Bug #002 - 战斗状态重置
问题：场景切换时 active_combat 状态未清理，导致非战斗动作被当作战斗处理

测试场景：
1. 在非战斗状态下使用道具（Buy-Potion）
2. 切换场景（从酒馆 → 森林）
3. 验证 active_combat 状态在场景切换后应为 False

验收标准：
- 场景切换后 active_combat == None
- 场景切换后「使用治疗药水」等非战斗动作不被当作战斗处理
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from src.game_master import GameMaster, GameMode
from src.event_bus import EventBus


class TestActiveCombatReset:
    """战斗状态重置测试 - Bug #002"""

    @pytest.fixture
    async def gm_in_tavern(self):
        """创建酒馆场景的 GameMaster，非战斗状态"""
        event_bus = EventBus()
        gm = GameMaster(event_bus=event_bus)
        gm.llm = None
        
        gm.current_scene = {
            "type": "酒馆",
            "name": "月光酒馆",
            "atmosphere": "热闹温馨",
        }
        gm.game_state = {
            "mode": "exploration",
            "active_combat": None,
            "current_location": "月光酒馆",
            "active_npcs_per_scene": {},
        }
        return gm

    @pytest.mark.asyncio
    async def test_active_combat_none_after_scene_switch(self, gm_in_tavern):
        """场景切换后 active_combat 应为 None"""
        # 确认初始状态
        assert gm_in_tavern.game_state.get("active_combat") is None
        
        # 切换场景
        await gm_in_tavern._check_scene_update("进入森林")
        
        # 场景切换后 active_combat 应为 None
        assert gm_in_tavern.game_state.get("active_combat") is None, \
            f"场景切换后 active_combat 应为 None，实际: {gm_in_tavern.game_state.get('active_combat')}"

    @pytest.mark.asyncio
    async def test_scene_switch_clears_combat_state(self, gm_in_tavern):
        """场景切换后 active_combat 状态应被清除为 None"""
        # 模拟战斗状态
        gm_in_tavern.game_state["active_combat"] = True
        
        # 切换场景
        await gm_in_tavern._check_scene_update("进入森林")
        
        # 场景切换后 active_combat 应为 None
        assert gm_in_tavern.game_state.get("active_combat") is None, \
            f"场景切换后 active_combat 应为 None，实际: {gm_in_tavern.game_state.get('active_combat')}"

    @pytest.mark.asyncio
    async def test_explore_after_scene_switch_still_works(self, gm_in_tavern):
        """场景切换后探索命令应正常工作（不是战斗状态）"""
        # 切换场景
        await gm_in_tavern._check_scene_update("进入森林")
        
        # 确认非战斗模式
        assert gm_in_tavern.mode == GameMode.EXPLORATION
        assert gm_in_tavern.game_state.get("active_combat") is None
        
        # 探索命令应返回 None（不触发任何战斗/特殊动作）
        result = gm_in_tavern._check_combat_trigger("查看周围的环境")
        assert result is None, f"普通探索命令不应触发战斗，实际: {result}"
