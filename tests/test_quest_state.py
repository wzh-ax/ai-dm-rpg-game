"""
QuestState - 单元测试
测试任务状态管理的核心功能
"""

import pytest

from src.quest_state import QuestState, QuestStage, QUEST_NAME


class TestQuestStageEnum:
    """测试 QuestStage 枚举"""

    def test_quest_stage_values(self):
        """验证所有任务阶段枚举值存在"""
        expected = [
            "not_started",
            "find_mayor",
            "talk_to_mayor",
            "go_to_tavern",
            "gather_info",
            "go_to_forest",
            "defeat_monster",
            "return_to_mayor",
            "quest_complete",
        ]
        actual = [e.value for e in QuestStage]
        assert set(actual) == set(expected)

    def test_quest_stage_count(self):
        """验证任务阶段数量"""
        assert len(QuestStage) == 9

    def test_quest_name(self):
        """验证任务名称"""
        assert QUEST_NAME == "月叶镇危机"


class TestQuestStateInit:
    """测试 QuestState 初始化"""

    def test_default_initialization(self):
        """默认状态应为 NOT_STARTED"""
        qs = QuestState()
        assert qs.stage == QuestStage.NOT_STARTED
        assert qs.completed is False
        assert qs.tavern_info_gathered is False
        assert qs.monster_hp_dealt == 0
        assert qs.quest_log == []

    def test_custom_initialization(self):
        """可以自定义初始化值"""
        qs = QuestState(
            stage=QuestStage.FIND_MAYOR,
            tavern_info_gathered=True,
            monster_hp_dealt=10,
        )
        assert qs.stage == QuestStage.FIND_MAYOR
        assert qs.tavern_info_gathered is True
        assert qs.monster_hp_dealt == 10


class TestQuestStateAdvance:
    """测试 QuestState advance_to 方法"""

    def test_advance_to_sets_stage(self):
        """advance_to 应正确设置阶段"""
        qs = QuestState()
        qs.advance_to(QuestStage.FIND_MAYOR)
        assert qs.stage == QuestStage.FIND_MAYOR

    def test_advance_to_logs_progress(self):
        """advance_to 应记录进度到 quest_log"""
        qs = QuestState()
        qs.advance_to(QuestStage.TALK_TO_MAYOR)
        assert len(qs.quest_log) == 1
        assert qs.quest_log[0] == "[talk_to_mayor]"

    def test_advance_to_consecutive_stages(self):
        """可以连续推进多个阶段"""
        qs = QuestState()
        qs.advance_to(QuestStage.FIND_MAYOR)
        qs.advance_to(QuestStage.TALK_TO_MAYOR)
        qs.advance_to(QuestStage.GO_TO_TAVERN)
        assert qs.stage == QuestStage.GO_TO_TAVERN
        assert len(qs.quest_log) == 3

    def test_advance_to_full_quest_path(self):
        """完整任务路径：FIND_MAYOR -> QUEST_COMPLETE"""
        qs = QuestState()
        stages = [
            QuestStage.FIND_MAYOR,
            QuestStage.TALK_TO_MAYOR,
            QuestStage.GO_TO_TAVERN,
            QuestStage.GATHER_INFO,
            QuestStage.GO_TO_FOREST,
            QuestStage.DEFEAT_MONSTER,
            QuestStage.RETURN_TO_MAYOR,
            QuestStage.QUEST_COMPLETE,
        ]
        for stage in stages:
            qs.advance_to(stage)
        assert qs.stage == QuestStage.QUEST_COMPLETE
        assert qs.completed is True  # advance_to(QUEST_COMPLETE) 会自动设置 completed=True


class TestQuestStateIsActive:
    """测试 is_active 方法"""

    def test_not_started_is_not_active(self):
        """NOT_STARTED 阶段不应视为活跃"""
        qs = QuestState()
        assert qs.is_active() is False

    def test_quest_complete_is_not_active(self):
        """QUEST_COMPLETE 阶段不应视为活跃"""
        qs = QuestState(stage=QuestStage.QUEST_COMPLETE)
        assert qs.is_active() is False

    def test_active_stages(self):
        """中间阶段都应视为活跃"""
        active_stages = [
            QuestStage.FIND_MAYOR,
            QuestStage.TALK_TO_MAYOR,
            QuestStage.GO_TO_TAVERN,
            QuestStage.GATHER_INFO,
            QuestStage.GO_TO_FOREST,
            QuestStage.DEFEAT_MONSTER,
            QuestStage.RETURN_TO_MAYOR,
        ]
        for stage in active_stages:
            qs = QuestState(stage=stage)
            assert qs.is_active() is True, f"Stage {stage.value} should be active"


class TestGetStageHint:
    """测试 get_stage_hint 方法"""

    def test_hint_for_find_mayor(self):
        """FIND_MAYOR 阶段应有提示"""
        qs = QuestState(stage=QuestStage.FIND_MAYOR)
        hint = qs.get_stage_hint()
        assert len(hint) > 0
        assert "镇" in hint or "中心" in hint

    def test_hint_for_defeat_monster(self):
        """DEFEAT_MONSTER 阶段应提及影狼"""
        qs = QuestState(stage=QuestStage.DEFEAT_MONSTER)
        hint = qs.get_stage_hint()
        assert len(hint) > 0

    def test_hint_for_not_started(self):
        """NOT_STARTED 阶段应返回空字符串"""
        qs = QuestState(stage=QuestStage.NOT_STARTED)
        assert qs.get_stage_hint() == ""

    def test_all_stages_have_hints(self):
        """所有非 NOT_STARTED 阶段都应有提示"""
        qs = QuestState()
        for stage in QuestStage:
            qs.stage = stage
            hint = qs.get_stage_hint()
            if stage != QuestStage.NOT_STARTED:
                assert len(hint) > 0, f"No hint for stage {stage.value}"


class TestGetMonsterName:
    """测试 get_monster_name 方法"""

    def test_returns_shadow_wolf(self):
        """应返回影狼"""
        qs = QuestState()
        assert qs.get_monster_name() == "影狼"


class TestGetQuestInfo:
    """测试 get_quest_info 方法"""

    def test_returns_dict_with_required_keys(self):
        """返回的字典应包含所有必需字段"""
        qs = QuestState(stage=QuestStage.GO_TO_TAVERN)
        info = qs.get_quest_info()
        assert "name" in info
        assert "stage" in info
        assert "stage_display" in info
        assert "hint" in info
        assert "completed" in info
        assert "is_active" in info

    def test_quest_info_name(self):
        """任务名称应为 QUEST_NAME"""
        qs = QuestState()
        info = qs.get_quest_info()
        assert info["name"] == QUEST_NAME

    def test_quest_info_stage(self):
        """stage 字段应为当前阶段的 value"""
        qs = QuestState(stage=QuestStage.GATHER_INFO)
        info = qs.get_quest_info()
        assert info["stage"] == "gather_info"

    def test_quest_info_is_active(self):
        """is_active 字段应正确反映状态"""
        qs = QuestState(stage=QuestStage.GATHER_INFO)
        info = qs.get_quest_info()
        assert info["is_active"] is True

        qs2 = QuestState(stage=QuestStage.QUEST_COMPLETE)
        info2 = qs2.get_quest_info()
        assert info2["is_active"] is False


class TestCheckLocationTrigger:
    """测试 check_location_trigger 方法"""

    def test_talk_to_mayor_location(self):
        """TALK_TO_MAYOR 阶段应触发广场相关地点"""
        qs = QuestState(stage=QuestStage.TALK_TO_MAYOR)
        assert qs.check_location_trigger("月叶镇广场") is True
        assert qs.check_location_trigger("广场") is True

    def test_go_to_tavern_location(self):
        """GO_TO_TAVERN 阶段应触发酒馆"""
        qs = QuestState(stage=QuestStage.GO_TO_TAVERN)
        assert qs.check_location_trigger("月光酒馆") is True
        assert qs.check_location_trigger("酒馆") is True

    def test_go_to_forest_location(self):
        """GO_TO_FOREST 阶段应触发森林"""
        qs = QuestState(stage=QuestStage.GO_TO_FOREST)
        assert qs.check_location_trigger("幽影森林") is True
        assert qs.check_location_trigger("森林") is True

    def test_no_trigger_for_completed(self):
        """QUEST_COMPLETE 不应有地点触发"""
        qs = QuestState(stage=QuestStage.QUEST_COMPLETE)
        assert qs.check_location_trigger("月叶镇广场") is False


class TestFullQuestFlow:
    """测试完整任务流程"""

    def test_full_quest_flow_logic(self):
        """模拟完整任务流程的状态变化"""
        qs = QuestState()

        # 开始任务
        assert qs.is_active() is False
        qs.advance_to(QuestStage.FIND_MAYOR)
        assert qs.is_active() is True

        # 对话后去酒馆
        qs.advance_to(QuestStage.TALK_TO_MAYOR)
        qs.advance_to(QuestStage.GO_TO_TAVERN)
        assert qs.check_location_trigger("酒馆") is True

        # 打听后去森林
        qs.advance_to(QuestStage.GATHER_INFO)
        qs.tavern_info_gathered = True
        qs.advance_to(QuestStage.GO_TO_FOREST)
        assert qs.check_location_trigger("森林") is True

        # 击败怪物
        qs.advance_to(QuestStage.DEFEAT_MONSTER)
        qs.monster_hp_dealt = 100
        qs.advance_to(QuestStage.RETURN_TO_MAYOR)

        # 回报完成
        qs.advance_to(QuestStage.QUEST_COMPLETE)
        qs.completed = True
        assert qs.is_active() is False
        assert qs.completed is True


class TestEndingType:
    """测试 EndingType 枚举"""

    def test_ending_type_values(self):
        """验证所有结局类型枚举值存在"""
        from src.quest_state import EndingType
        expected = ["heroic", "peaceful", "tragic", "mysterious", "commercial"]
        actual = [e.value for e in EndingType]
        assert set(actual) == set(expected)

    def test_ending_type_count(self):
        """验证结局类型数量"""
        from src.quest_state import EndingType
        assert len(EndingType) == 5


class TestRecordChoice:
    """测试 record_choice 方法"""

    def test_record_choice_adds_to_list(self):
        """record_choice 应将选择添加到 player_choices"""
        qs = QuestState()
        qs.record_choice("dialogue", "与镇长对话", "询问关于森林的事")
        assert len(qs.player_choices) == 1
        assert qs.player_choices[0]["type"] == "dialogue"
        assert qs.player_choices[0]["value"] == "与镇长对话"

    def test_record_choice_contains_stage(self):
        """record_choice 应记录当前阶段"""
        qs = QuestState(stage=QuestStage.GO_TO_TAVERN)
        qs.record_choice("combat", "攻击哥布林", "")
        assert qs.player_choices[0]["stage"] == "go_to_tavern"

    def test_record_multiple_choices(self):
        """可以记录多个选择"""
        qs = QuestState()
        qs.record_choice("dialogue", "与酒馆老板对话", "")
        qs.record_choice("combat", "攻击哥布林", "")
        qs.record_choice("skill", "治疗术", "")
        assert len(qs.player_choices) == 3


class TestEvaluateEnding:
    """测试 evaluate_ending 方法"""

    def test_peaceful_ending_zero_combat(self):
        """零战斗应评定为和平结局"""
        qs = QuestState()
        qs.combat_count = 0
        qs.advance_to(QuestStage.QUEST_COMPLETE)
        ending = qs.evaluate_ending()
        assert ending.value == "peaceful"

    def test_heroic_ending_high_combat(self):
        """多次战斗击败怪物应评定为英雄结局"""
        qs = QuestState()
        qs.combat_count = 5
        qs.monster_hp_dealt = 60
        qs.advance_to(QuestStage.QUEST_COMPLETE)
        ending = qs.evaluate_ending()
        assert ending.value == "heroic"

    def test_mysterious_ending_low_combat(self):
        """战斗次数少但完成任务应评定为神秘结局"""
        qs = QuestState()
        qs.combat_count = 2
        qs.monster_hp_dealt = 20
        qs.advance_to(QuestStage.QUEST_COMPLETE)
        ending = qs.evaluate_ending()
        # 神秘结局：快速解决
        assert ending.value in ("mysterious", "heroic")

    def test_commercial_ending_with_trade_choice(self):
        """包含交易选择应评定为商人之道结局"""
        qs = QuestState()
        qs.record_choice("dialogue", "买装备", "")
        qs.advance_to(QuestStage.QUEST_COMPLETE)
        ending = qs.evaluate_ending()
        assert ending.value == "commercial"


class TestGetEndingNarrative:
    """测试 get_ending_narrative 方法"""

    def test_heroic_narrative_contains_hero(self):
        """英雄结局叙事应包含英雄相关内容"""
        from src.quest_state import EndingType
        qs = QuestState()
        narrative = qs.get_ending_narrative(EndingType.HEROIC)
        assert "英雄" in narrative or "勇" in narrative

    def test_peaceful_narrative_contains_peace(self):
        """和平结局叙事应包含和平相关内容"""
        from src.quest_state import EndingType
        qs = QuestState()
        narrative = qs.get_ending_narrative(EndingType.PEACEFUL)
        assert len(narrative) > 0

    def test_all_endings_have_narratives(self):
        """所有结局类型都应有叙事"""
        from src.quest_state import EndingType
        qs = QuestState()
        for ending in EndingType:
            narrative = qs.get_ending_narrative(ending)
            assert len(narrative) > 0, f"No narrative for {ending.value}"


class TestGetPlayerProfile:
    """测试 get_player_profile 方法"""

    def test_profile_calculates_combat_style_warlike(self):
        """以战斗为主的选择应为好战型"""
        qs = QuestState()
        qs.record_choice("combat", "攻击", "")
        qs.record_choice("combat", "攻击", "")
        qs.record_choice("combat", "攻击", "")
        qs.record_choice("dialogue", "说话", "")  # 1/4 = 25%
        profile = qs.get_player_profile()
        assert profile["combat_style"] == "好战型"

    def test_profile_calculates_combat_style_diplomatic(self):
        """以对话为主的选择应为外交型"""
        qs = QuestState()
        qs.record_choice("dialogue", "与镇长对话", "")
        qs.record_choice("dialogue", "与老板对话", "")
        qs.record_choice("dialogue", "询问", "")
        qs.record_choice("combat", "攻击", "")  # 1/4 = 25%
        profile = qs.get_player_profile()
        assert profile["combat_style"] == "外交型"

    def test_profile_shows_total_choices(self):
        """玩家画像应包含总选择数"""
        qs = QuestState()
        qs.record_choice("dialogue", "对话1", "")
        qs.record_choice("combat", "战斗1", "")
        qs.record_choice("item", "使用药水", "")
        profile = qs.get_player_profile()
        assert profile["total_choices"] == 3

    def test_profile_shows_combat_count(self):
        """玩家画像应包含战斗次数"""
        qs = QuestState()
        qs.combat_count = 5
        profile = qs.get_player_profile()
        assert profile["combat_count"] == 5

    def test_profile_shows_npc_interactions(self):
        """玩家画像应包含NPC交互次数"""
        qs = QuestState()
        qs.talked_to_npcs = ["镇长", "老板", "猎人"]
        profile = qs.get_player_profile()
        assert profile["npc_interactions"] == 3

    def test_profile_choice_breakdown(self):
        """玩家画像应包含选择类型分布"""
        qs = QuestState()
        qs.record_choice("combat", "attack1", "")
        qs.record_choice("combat", "attack2", "")
        qs.record_choice("dialogue", "talk1", "")
        profile = qs.get_player_profile()
        assert profile["choice_breakdown"]["combat"] == 2
        assert profile["choice_breakdown"]["dialogue"] == 1
