"""
Bug #002 - 自然语言场景切换检测
问题：场景切换检测不支持「去外面看看」「进森林」等自然语言变体，
     导致玩家无法自然进入危险区域触发战斗

验收标准：
- 「进森林」应触发场景切换到森林
- 「去外面看看」应触发场景切换到森林
- 「离开酒馆去森林」应触发场景切换到森林
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from src.game_master import GameMaster, GameMode
from src.event_bus import EventBus


class TestNaturalLanguageSceneSwitch:
    """自然语言场景切换测试 - Bug #002"""

    @pytest.fixture
    def gm_in_tavern(self):
        """创建酒馆场景的 GameMaster"""
        event_bus = EventBus()
        gm = GameMaster(event_bus=event_bus)
        gm.llm = None
        
        gm.current_scene = {
            "type": "酒馆",
            "name": "月光酒馆",
            "atmosphere": "热闹温馨",
            "npcs": [{"name": "酒馆老板", "role": "innkeeper"}],
        }
        gm.game_state = {
            "mode": "exploration",
            "active_combat": None,
            "current_location": "月光酒馆",
        }
        gm.active_npcs = {}
        return gm

    @pytest.mark.asyncio
    async def test_enter_forest_direct(self, gm_in_tavern):
        """「进森林」应触发场景切换"""
        with patch.object(gm_in_tavern, '_generate_scene', new_callable=AsyncMock) as mock_gen:
            mock_gen.return_value = "你走进了黑森林..."
            result = await gm_in_tavern._check_scene_update("进森林")
            assert result is not None, "「进森林」未能触发场景切换"
            mock_gen.assert_called_once_with("森林")

    @pytest.mark.asyncio
    async def test_go_outside_natural_lang(self, gm_in_tavern):
        """「去外面看看」应触发场景切换到森林"""
        with patch.object(gm_in_tavern, '_generate_scene', new_callable=AsyncMock) as mock_gen:
            mock_gen.return_value = "你走出酒馆，来到了野外..."
            result = await gm_in_tavern._check_scene_update("去外面看看")
            assert result is not None, "「去外面看看」未能触发场景切换"
            mock_gen.assert_called_once_with("森林")

    @pytest.mark.asyncio
    async def test_leave_tavern_forest(self, gm_in_tavern):
        """「离开酒馆去森林」应触发场景切换"""
        with patch.object(gm_in_tavern, '_generate_scene', new_callable=AsyncMock) as mock_gen:
            mock_gen.return_value = "你离开了月光酒馆..."
            result = await gm_in_tavern._check_scene_update("离开酒馆去森林")
            assert result is not None, "「离开酒馆去森林」未能触发场景切换"
            mock_gen.assert_called_once_with("森林")

    @pytest.mark.asyncio
    async def test_go_to_woods(self, gm_in_tavern):
        """「去树林」应触发场景切换"""
        with patch.object(gm_in_tavern, '_generate_scene', new_callable=AsyncMock) as mock_gen:
            mock_gen.return_value = "你走进了树林..."
            result = await gm_in_tavern._check_scene_update("去树林")
            assert result is not None, "「去树林」未能触发场景切换"

    @pytest.mark.asyncio
    async def test_forest_is_dangerous_zone(self, gm_in_tavern):
        """森林场景切换后应能触发战斗（危险区域）"""
        with patch.object(gm_in_tavern, '_generate_scene', new_callable=AsyncMock) as mock_gen:
            # 先切到森林
            async def fake_generate(scene_type):
                if scene_type == "森林":
                    gm_in_tavern.current_scene = {
                        "type": "森林",
                        "name": "黑森林",
                        "atmosphere": "阴森恐怖",
                        "danger_level": "high",
                    }
                    gm_in_tavern.game_state["current_location"] = "黑森林"
                    return "你走进了黑森林，四周弥漫着雾气..."
                return None
            mock_gen.side_effect = fake_generate
            
            result = await gm_in_tavern._check_scene_update("进森林")
            assert result is not None
            
            # 确认切换到了危险区域
            assert gm_in_tavern.current_scene["type"] == "森林"
            assert gm_in_tavern.current_scene.get("danger_level") == "high"
