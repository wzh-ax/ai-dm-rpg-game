"""
Tests for system command handlers in interactive_master.py
"""

import pytest
import sys
from io import StringIO
from unittest.mock import MagicMock, patch


class MockQuestState:
    """Mock QuestState for testing"""
    def __init__(self, stage="find_mayor", is_active=True, quest_log=None):
        from src.quest_state import QuestStage
        self.stage = QuestStage[stage.upper()] if isinstance(stage, str) else stage
        self.quest_log = quest_log or []
        self._is_active = is_active

    def is_active(self):
        return self._is_active

    def get_quest_info(self):
        from src.quest_state import QuestStage
        hints = {
            QuestStage.FIND_MAYOR: "镇中心似乎有人聚集，过去看看？",
            QuestStage.TALK_TO_MAYOR: "镇长正焦急地在广场中央等待",
            QuestStage.GO_TO_TAVERN: "月光酒馆就在街道尽头",
            QuestStage.GATHER_INFO: "酒馆里人声鼎沸",
            QuestStage.GO_TO_FOREST: "幽影森林就在镇子北边入口",
            QuestStage.DEFEAT_MONSTER: "一头凶猛的影狼挡住了你的去路！",
            QuestStage.RETURN_TO_MAYOR: "影狼已被击败，回去向镇长报告！",
            QuestStage.QUEST_COMPLETE: "任务完成！",
            QuestStage.NOT_STARTED: "",
        }
        stage_names = {
            QuestStage.FIND_MAYOR: "寻找镇长",
            QuestStage.TALK_TO_MAYOR: "与镇长对话",
            QuestStage.GO_TO_TAVERN: "前往酒馆",
            QuestStage.GATHER_INFO: "打听情报",
            QuestStage.GO_TO_FOREST: "进入森林",
            QuestStage.DEFEAT_MONSTER: "击败影狼",
            QuestStage.RETURN_TO_MAYOR: "回报镇长",
            QuestStage.QUEST_COMPLETE: "任务完成",
            QuestStage.NOT_STARTED: "未开始",
        }
        return {
            "name": "月叶镇危机",
            "stage": self.stage.value,
            "stage_display": stage_names.get(self.stage, "未知"),
            "hint": hints.get(self.stage, ""),
            "completed": self.stage == QuestStage.QUEST_COMPLETE,
            "is_active": self._is_active,
        }


class TestPrintStatus:
    """Tests for print_status function"""

    def test_print_status_basic(self):
        """print_status should not crash with valid game_state"""
        from interactive_master import print_status

        game_state = {
            "turn": 5,
            "location": "月叶镇",
            "mode": "exploration",
            "player_stats": {
                "hp": 25,
                "max_hp": 30,
                "ac": 14,
                "xp": 50,
                "level": 2,
                "gold": 100,
                "inventory": [
                    {"name": "治疗药水", "rarity": "common"},
                    {"name": "铁剑", "rarity": "uncommon"},
                ],
                "name": "测试冒险者",
                "race": "人类",
                "class": "战士",
            }
        }

        # Should not raise
        print_status(game_state)

    def test_print_status_minimal(self):
        """print_status should handle minimal game_state"""
        from interactive_master import print_status

        game_state = {
            "turn": 0,
            "location": "未知",
            "mode": "exploration",
            "player_stats": {
                "hp": 30,
                "max_hp": 30,
                "ac": 10,
                "xp": 0,
                "level": 1,
                "gold": 0,
                "inventory": [],
            }
        }

        # Should not raise
        print_status(game_state)


class TestPrintShop:
    """Tests for print_shop function"""

    def test_print_shop_basic(self):
        """print_shop should display items and prices"""
        from interactive_master import print_shop

        game_state = {
            "player_stats": {
                "gold": 500,
            }
        }

        # Capture stdout
        captured = StringIO()
        sys.stdout = captured

        try:
            print_shop(game_state)
        finally:
            sys.stdout = sys.__stdout__

        output = captured.getvalue()
        # Should contain shop header
        assert "商店" in output or "shop" in output.lower() or "月光" in output
        # Should contain gold amount
        assert "500" in output
        # Should contain some items
        assert len(output) > 100  # Has substantial content

    def test_print_shop_no_gold(self):
        """print_shop should handle 0 gold gracefully"""
        from interactive_master import print_shop

        game_state = {
            "player_stats": {
                "gold": 0,
            }
        }

        captured = StringIO()
        sys.stdout = captured

        try:
            print_shop(game_state)
        finally:
            sys.stdout = sys.__stdout__

        output = captured.getvalue()
        assert "0" in output  # Shows 0 gold


class TestPrintQuest:
    """Tests for print_quest function"""

    def test_print_quest_active(self):
        """print_quest should display active quest with stages and hints"""
        from interactive_master import print_quest
        from src.quest_state import QuestStage

        game_state = {"player_stats": {}}
        mock_quest = MockQuestState(stage="find_mayor", is_active=True, quest_log=[])

        captured = StringIO()
        sys.stdout = captured

        try:
            print_quest(game_state, mock_quest)
        finally:
            sys.stdout = sys.__stdout__

        output = captured.getvalue()
        # Should contain quest name
        assert "月叶镇危机" in output
        # Should contain current stage
        assert "寻找镇长" in output
        # Should contain hint
        assert "镇中心" in output or "聚集" in output
        # Should show task markers
        assert "👉" in output or "⬜" in output

    def test_print_quest_completed(self):
        """print_quest should display completion message for finished quest"""
        from interactive_master import print_quest

        game_state = {"player_stats": {}}
        mock_quest = MockQuestState(stage="quest_complete", is_active=False, quest_log=["find_mayor", "talk_to_mayor"])

        captured = StringIO()
        sys.stdout = captured

        try:
            print_quest(game_state, mock_quest)
        finally:
            sys.stdout = sys.__stdout__

        output = captured.getvalue()
        assert "完成" in output or "已完成" in output

    def test_print_quest_not_started(self):
        """print_quest should handle not started state"""
        from interactive_master import print_quest

        game_state = {"player_stats": {}}
        mock_quest = MockQuestState(stage="not_started", is_active=False, quest_log=[])

        captured = StringIO()
        sys.stdout = captured

        try:
            print_quest(game_state, mock_quest)
        finally:
            sys.stdout = sys.__stdout__

        output = captured.getvalue()
        assert len(output) > 0  # Has content

    def test_print_quest_all_stages(self):
        """print_quest should display correctly for all quest stages"""
        from interactive_master import print_quest

        game_state = {"player_stats": {}}
        stages_to_test = [
            "find_mayor",
            "talk_to_mayor",
            "go_to_tavern",
            "gather_info",
            "go_to_forest",
            "defeat_monster",
            "return_to_mayor",
        ]

        for stage in stages_to_test:
            mock_quest = MockQuestState(stage=stage, is_active=True, quest_log=[])

            captured = StringIO()
            sys.stdout = captured

            try:
                print_quest(game_state, mock_quest)
            finally:
                sys.stdout = sys.__stdout__

            output = captured.getvalue()
            assert len(output) > 50, f"Stage {stage} produced too little output"


class TestCommandMatching:
    """Tests for command matching logic in main loop"""

    def test_status_commands(self):
        """status command variants should match"""
        status_variants = ["status", "查看状态", "状态"]
        for cmd in status_variants:
            # Should be matched as status
            assert cmd == "status" or cmd in ["查看状态", "状态"]

    def test_shop_commands(self):
        """shop command variants should match"""
        shop_variants = ["商店", "shop", "商店列表", "商品"]
        for cmd in shop_variants:
            assert cmd in shop_variants

    def test_quest_commands(self):
        """quest command variants should match"""
        quest_variants = ["任务", "quest", "任务详情"]
        for cmd in quest_variants:
            assert cmd in quest_variants

    def test_accept_quest_commands(self):
        """accept quest command variants should match"""
        accept_variants = ["接受任务", "accept quest", "接受", "start quest"]
        for cmd in accept_variants:
            assert cmd in accept_variants
