"""
TutorialSystem - 单元测试
"""

import pytest

from src.tutorial_system import (
    TutorialSystem,
    TutorialState,
    WORLD_INTRO,
    COMMANDS_INTRO,
    FIRST_TASK_INTRO,
    get_tutorial_system,
)


class TestTutorialSystem:
    """测试教程系统"""

    @pytest.fixture
    def tutorial(self):
        return TutorialSystem()

    def test_initial_state_is_not_started(self, tutorial):
        """初始状态应为 NOT_STARTED"""
        assert tutorial.state == TutorialState.NOT_STARTED

    def test_start_tutorial_sets_welcome_state(self, tutorial):
        """开始教程应设置 WELCOME 状态"""
        tutorial.start_tutorial("测试角色")
        assert tutorial.state == TutorialState.WELCOME

    def test_start_tutorial_returns_welcome_text(self, tutorial):
        """开始教程应返回欢迎文本"""
        text = tutorial.start_tutorial("冒险者A")
        assert "冒险者A" in text
        assert len(text) > 0

    def test_get_world_intro_returns_intro_text(self, tutorial):
        """世界观简介应包含关键内容"""
        text = tutorial.get_world_intro()
        assert "艾瑟拉大陆" in text
        assert "月叶镇" in text
        assert "人类" in text or "种族" in text

    def test_get_world_intro_updates_state(self, tutorial):
        """获取世界观简介应更新状态"""
        tutorial.state = TutorialState.WELCOME
        tutorial.get_world_intro()
        assert tutorial.state == TutorialState.WORLD_INTRO

    def test_get_commands_intro_returns_commands_text(self, tutorial):
        """操作说明应包含基本命令"""
        text = tutorial.get_commands_intro()
        assert "探索" in text or "酒馆" in text
        assert "/save" in text or "save" in text.lower()

    def test_get_commands_intro_updates_state(self, tutorial):
        """获取操作说明应更新状态"""
        tutorial.state = TutorialState.WORLD_INTRO
        tutorial.get_commands_intro()
        assert tutorial.state == TutorialState.COMMANDS

    def test_get_first_scene_intro(self, tutorial):
        """第一场景介绍应包含场景描写"""
        text = tutorial.get_first_scene_intro()
        assert len(text) > 0
        assert "月叶镇" in text or "场景" in text

    def test_get_first_task(self, tutorial):
        """新手任务应包含任务目标"""
        text = tutorial.get_first_task()
        assert "酒馆" in text or "任务" in text

    def test_complete_tutorial(self, tutorial):
        """完成教程应设置 COMPLETED 状态"""
        tutorial.complete_tutorial()
        assert tutorial.state == TutorialState.COMPLETED

    def test_is_completed(self, tutorial):
        """is_completed 应正确反映状态"""
        assert not tutorial.is_completed()
        tutorial.complete_tutorial()
        assert tutorial.is_completed()

    def test_reset(self, tutorial):
        """重置教程应回到初始状态"""
        tutorial.start_tutorial("Test")
        tutorial.get_world_intro()
        tutorial.reset()
        assert tutorial.state == TutorialState.NOT_STARTED


class TestTutorialStateTransitions:
    """测试教程状态转换"""

    @pytest.fixture
    def tutorial(self):
        return TutorialSystem()

    def test_state_progression(self, tutorial):
        """状态应该按正确顺序推进"""
        tutorial.start_tutorial("Test")
        assert tutorial.state == TutorialState.WELCOME

        tutorial.get_world_intro()
        assert tutorial.state == TutorialState.WORLD_INTRO

        tutorial.get_commands_intro()
        assert tutorial.state == TutorialState.COMMANDS

        tutorial.get_first_scene_intro()
        assert tutorial.state == TutorialState.FIRST_SCENE

        tutorial.get_first_task()
        assert tutorial.state == TutorialState.FIRST_TASK

    def test_allow_repeated_calls_same_state(self, tutorial):
        """同一状态的重复调用应该是安全的"""
        tutorial.start_tutorial("Test")
        text1 = tutorial.get_world_intro()
        text2 = tutorial.get_world_intro()  # 不应该改变状态
        assert text1 == text2
        assert tutorial.state == TutorialState.WORLD_INTRO


class TestTutorialContent:
    """测试教程内容"""

    def test_world_intro_has_all_races(self):
        """世界观简介应包含所有种族"""
        assert "人类" in WORLD_INTRO
        assert "精灵" in WORLD_INTRO
        assert "矮人" in WORLD_INTRO
        assert "兽人" in WORLD_INTRO

    def test_world_intro_has_all_classes(self):
        """世界观简介应包含所有职业"""
        assert "战士" in WORLD_INTRO
        assert "游侠" in WORLD_INTRO
        assert "法师" in WORLD_INTRO
        assert "盗贼" in WORLD_INTRO

    def test_world_intro_mentions_location(self):
        """世界观简介应提到位置"""
        assert "月叶镇" in WORLD_INTRO

    def test_commands_intro_has_save_load(self):
        """操作说明应包含存档/加载命令"""
        assert "/save" in COMMANDS_INTRO or "save" in COMMANDS_INTRO.lower()
        assert "/load" in COMMANDS_INTRO or "load" in COMMANDS_INTRO.lower()

    def test_commands_intro_has_combat_commands(self):
        """操作说明应包含战斗命令"""
        assert "攻击" in COMMANDS_INTRO or "战斗" in COMMANDS_INTRO

    def test_first_task_has_objective(self):
        """新手任务应有明确目标"""
        assert len(FIRST_TASK_INTRO) > 20


class TestTutorialSingleton:
    """测试全局单例"""

    def test_get_tutorial_system_returns_same_instance(self):
        """get_tutorial_system 应该返回同一个实例"""
        t1 = get_tutorial_system()
        t2 = get_tutorial_system()
        assert t1 is t2
