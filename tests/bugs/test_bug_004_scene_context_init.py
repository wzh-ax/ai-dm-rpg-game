"""
Bug #004 - 场景切换上下文初始化
问题：特定路径（Move-Forest → Move-Inn）触发上下文初始化 bug，导致后续命令全部失效

测试场景：
1. 执行路径：进入森林 → 进入酒馆
2. 在酒馆中执行命令
3. 验证命令能正常工作（不是上下文初始化 bug）

验收标准：
- 无论何种路径切换，场景切换后 current_scene 非空
- current_scene 包含必要字段：type, name, atmosphere
- 场景切换后游戏命令能正常路由
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from src.game_master import GameMaster, GameMode
from src.event_bus import EventBus


class TestSceneContextInit:
    """场景上下文初始化测试 - Bug #004"""

    @pytest.fixture
    async def gm(self):
        """创建初始 GameMaster"""
        event_bus = EventBus()
        gm = GameMaster(event_bus=event_bus)
        gm.llm = None
        # 正确初始化所有必要字段
        gm.game_state = {
            "mode": "exploration",
            "active_combat": False,
            "current_location": "起点",
            "active_npcs_per_scene": {},
            "npcs": {},
        }
        gm.current_scene = {
            "type": "平原",
            "name": "起始平原",
            "atmosphere": "平静",
        }
        return gm

    @pytest.mark.asyncio
    async def test_forest_to_inn_preserves_context(self, gm):
        """森林 → 酒馆路径切换后上下文应保持完整"""
        # Step 1: 进入森林
        result1 = await gm._check_scene_update("进入森林")
        assert gm.current_scene is not None, "切换到森林后 current_scene 不应为 None"
        assert gm.current_scene.get("type") == "森林", f"应为森林场景，实际: {gm.current_scene.get('type')}"
        
        # Step 2: 进入酒馆
        result2 = await gm._check_scene_update("进入酒馆")
        assert gm.current_scene is not None, "切换到酒馆后 current_scene 不应为 None"
        assert gm.current_scene.get("type") == "酒馆", f"应为酒馆场景，实际: {gm.current_scene.get('type')}"
        
        # 验证 current_scene 包含 atmosphere 字段
        assert "atmosphere" in gm.current_scene, "current_scene 应包含 atmosphere 字段"
        assert "npcs" in gm.current_scene, "current_scene 应包含 npcs 字段"

    @pytest.mark.asyncio
    async def test_forest_to_inn_command_works(self, gm):
        """森林 → 酒馆路径切换后命令应正常工作"""
        # 执行路径
        await gm._check_scene_update("进入森林")
        await gm._check_scene_update("进入酒馆")
        
        # 酒馆中执行 NPC 交互命令
        npc_result = await gm._check_npc_interaction("和酒馆老板说话")
        assert npc_result is not None, "场景切换后 NPC 交互不应返回 None（除非是 bug #001）"

    @pytest.mark.asyncio
    async def test_any_path_to_inn_works(self, gm):
        """任意路径切换到酒馆后上下文应完整"""
        paths = [
            ["进入酒馆"],  # 直接
            ["进入森林", "进入酒馆"],  # 森林绕路
            ["查看周围的环境", "进入酒馆"],  # 有探索的路径
        ]
        
        for path in paths:
            # 重新初始化
            gm.current_scene = {"type": "平原", "name": "起点", "atmosphere": "平静"}
            gm.game_state = {
                "mode": "exploration",
                "active_combat": False,
                "current_location": "起点",
                "active_npcs_per_scene": {},
                "inventory": ["治疗药水"],
                "player_hp": 100,
            }
            
            for move in path:
                await gm._check_scene_update(move)
            
            # 验证上下文完整
            assert gm.current_scene is not None, f"路径 {path} 切换后 current_scene 不应为 None"
            assert "type" in gm.current_scene, f"路径 {path} 切换后 current_scene 应包含 type"
            assert gm.current_scene.get("type") == "酒馆", \
                f"最终应为酒馆场景，实际: {gm.current_scene.get('type')}"

    @pytest.mark.asyncio
    async def test_scene_switch_preserves_game_state(self, gm):
        """场景切换应保留 game_state 中的关键状态"""
        # 设置一些 game_state
        gm.game_state = {
            "mode": "exploration",
            "active_combat": False,
            "player_hp": 100,
            "inventory": ["治疗药水"],
            "current_location": "起点",
            "active_npcs_per_scene": {},
        }
        
        # 切换场景
        await gm._check_scene_update("进入森林")
        await gm._check_scene_update("进入酒馆")
        
        # 验证关键状态保留
        assert gm.game_state.get("player_hp") == 100, "player_hp 应在场景切换后保留"
        assert "治疗药水" in gm.game_state.get("inventory", []), "inventory 应在场景切换后保留"
