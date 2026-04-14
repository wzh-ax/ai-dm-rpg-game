"""
Bug #003 - 命令归一化
问题：同义命令变体（中文/英文、不同表述）路由结果不同

测试场景：
1. 测试「攻击哥布林」「攻击」「attack goblin」「attack」等命令变体
2. 验证归一化后触发相同的战斗动作

验收标准：
- 中文攻击命令 → action="attack"
- 英文攻击命令 → action="attack"
- 同义词（砍、打、揍）→ action="attack"
- 所有变体应触发相同的游戏动作
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from src.game_master import GameMaster, GameMode
from src.event_bus import EventBus


class TestCommandNormalization:
    """命令归一化测试 - Bug #003"""

    @pytest.fixture
    async def gm_in_forest(self):
        """创建森林战斗场景的 GameMaster"""
        event_bus = EventBus()
        gm = GameMaster(event_bus=event_bus)
        gm.llm = None
        
        gm.current_scene = {
            "type": "森林",
            "name": "迷雾森林",
            "atmosphere": "阴森神秘",
            "enemies": [
                {"name": "哥布林", "role": "goblin", "hp": 20, "ac": 10}
            ]
        }
        gm.game_state = {
            "mode": "exploration",
            "active_combat": False,
            "current_location": "迷雾森林"
        }
        return gm

    def _get_normalized_action(self, gm, command):
        """辅助方法：获取命令归一化后的 action"""
        if hasattr(gm, '_normalize_command'):
            normalized = gm._normalize_command(command)
            return normalized.get("action")
        else:
            # Bug 未修复时，_normalize_command 不存在
            return command  # 返回原始命令（未归一化）

    def test_attack_chinese_variants(self, gm_in_forest):
        """中文攻击命令变体应归一化到同一 action"""
        variants = [
            "攻击哥布林",
            "攻击",
            "攻击 goblin",
            "打哥布林",
            "砍哥布林",
        ]
        actions = set()
        for v in variants:
            action = self._get_normalized_action(gm_in_forest, v)
            actions.add(action)
        
        # 所有中文变体应归一化到相同 action
        assert len(actions) == 1, f"中文攻击命令变体应归一化到相同 action，实际: {actions}"
        assert "attack" in str(actions).lower() or "攻击" in str(actions), \
            f"应归一化为 attack，实际: {actions}"

    def test_attack_english_variants(self, gm_in_forest):
        """英文攻击命令变体应归一化到同一 action"""
        variants = [
            "attack goblin",
            "attack",
            "attack the goblin",
            "kill goblin",
            "fight goblin",
        ]
        actions = set()
        for v in variants:
            action = self._get_normalized_action(gm_in_forest, v)
            actions.add(action)
        
        # 所有英文变体应归一化到相同 action
        assert len(actions) == 1, f"英文攻击命令变体应归一化到相同 action，实际: {actions}"

    def test_chinese_and_english_same_action(self, gm_in_forest):
        """中英文命令应归一化到相同 action"""
        cn_action = self._get_normalized_action(gm_in_forest, "攻击哥布林")
        en_action = self._get_normalized_action(gm_in_forest, "attack goblin")
        
        assert cn_action == en_action, \
            f"中英文命令应归一化到相同 action，「攻击哥布林」={cn_action}，「attack goblin」={en_action}"

    @pytest.mark.asyncio
    async def test_attack_triggers_combat(self, gm_in_forest):
        """攻击命令应触发战斗"""
        result = gm_in_forest._check_combat_trigger("攻击哥布林")
        assert result is not None, "攻击哥布林应触发战斗"
        assert result.get("trigger") in ["aggressive", "attack"], f"应为攻击触发，实际: {result}"

    @pytest.mark.asyncio
    async def test_attack_goblin_english_triggers_combat(self, gm_in_forest):
        """「attack goblin」应触发战斗（与中文版一致）"""
        result = gm_in_forest._check_combat_trigger("attack goblin")
        assert result is not None, "attack goblin 应触发战斗"
        assert result.get("trigger") in ["aggressive", "attack"], f"应为攻击触发，实际: {result}"
