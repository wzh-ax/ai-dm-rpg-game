# -*- coding: utf-8 -*-
"""
验收测试：D-001, D-002, D-003
D-001: interactive_master.py 交互入口模块
D-002: 角色创建流程的交互式引导
D-003: docs/PLAYER_GUIDE.md 与实际入口一致
"""
import inspect
import os

def test_d001_module_import():
    """D-001: interactive_master.py 可以正常导入"""
    import interactive_master
    assert interactive_master is not None
    # 核心组件存在
    assert hasattr(interactive_master, 'async_main')
    assert hasattr(interactive_master, 'InteractiveCharacterCreator')
    assert hasattr(interactive_master, 'Character')
    assert hasattr(interactive_master, 'GameMaster')
    assert hasattr(interactive_master, 'WELCOME_BANNER')
    assert hasattr(interactive_master, 'HELP_TEXT')
    assert hasattr(interactive_master, 'STATUS_TEMPLATE')
    assert hasattr(interactive_master, 'run_game_loop')
    assert hasattr(interactive_master, 'main')
    print("D-001: 模块导入 - PASS")


def test_d001_main_has_correct_commands():
    """D-001: async_main 处理所有必要命令"""
    import interactive_master
    source = inspect.getsource(interactive_master.async_main)
    required_commands = ['new', 'continue', 'status', 'save', 'load', 'help', 'quit']
    for cmd in required_commands:
        assert f'"{cmd}"' in source or f"'{cmd}'" in source, f"Command {cmd} not found in async_main"
    print("D-001: async_main 命令完整性 - PASS")


def test_d001_game_loop_handles_commands():
    """D-001: run_game_loop 处理 status/help/save/load/quit"""
    import interactive_master
    source = inspect.getsource(interactive_master.run_game_loop)
    loop_commands = ['status', 'help', 'save', 'load', 'quit']
    for cmd in loop_commands:
        assert f'"{cmd}"' in source or f"'{cmd}'" in source, f"Command {cmd} not found in run_game_loop"
    print("D-001: run_game_loop 命令处理 - PASS")


def test_d002_character_creator_integration():
    """D-002: InteractiveCharacterCreator 正确对接 CharacterCreator"""
    from interactive_master import InteractiveCharacterCreator
    from src import CharacterCreator
    icc = InteractiveCharacterCreator()
    assert icc.creator is not None
    assert isinstance(icc.creator, CharacterCreator)
    # 验证 _ask_race 和 _ask_class 方法存在
    assert hasattr(icc, '_ask_race')
    assert hasattr(icc, '_ask_class')
    assert hasattr(icc, '_ask_name')
    assert hasattr(icc, 'run')
    print("D-002: InteractiveCharacterCreator 对接 CharacterCreator - PASS")


def test_d002_race_class_mappings():
    """D-002: 种族和职业映射正确"""
    from interactive_master import InteractiveCharacterCreator
    import io
    import sys
    # 捕获 RACE_MENU 和 CLASS_MENU
    from src import CharacterCreator
    assert len(CharacterCreator.RACE_MENU) > 0
    assert len(CharacterCreator.CLASS_MENU) > 0
    # 验证菜单包含预期的种族和职业
    assert '人类' in CharacterCreator.RACE_MENU or 'Human' in CharacterCreator.RACE_MENU
    assert '战士' in CharacterCreator.CLASS_MENU or 'Warrior' in CharacterCreator.CLASS_MENU
    print("D-002: 种族/职业菜单完整性 - PASS")


def test_d003_player_guide_exists():
    """D-003: PLAYER_GUIDE.md 存在"""
    guide_path = os.path.join(os.path.dirname(__file__), '..', '..', 'docs', 'PLAYER_GUIDE.md')
    guide_path = os.path.normpath(guide_path)
    assert os.path.exists(guide_path), f"PLAYER_GUIDE.md not found at {guide_path}"
    print("D-003: PLAYER_GUIDE.md 存在 - PASS")


def test_d003_guide_start_command():
    """D-003: 指南中的启动命令正确"""
    guide_path = os.path.join(os.path.dirname(__file__), '..', '..', 'docs', 'PLAYER_GUIDE.md')
    guide_path = os.path.normpath(guide_path)
    with open(guide_path, 'r', encoding='utf-8') as f:
        content = f.read()
    # 启动命令正确
    assert 'python interactive_master.py' in content, "启动命令缺失"
    assert 'cd' in content and 'ai-dm-rpg-game' in content, "cd 路径缺失"
    print("D-003: PLAYER_GUIDE.md 启动命令正确 - PASS")


def test_d003_guide_commands_match_implementation():
    """D-003: 指南中的命令与实际实现一致"""
    import interactive_master
    guide_path = os.path.join(os.path.dirname(__file__), '..', '..', 'docs', 'PLAYER_GUIDE.md')
    guide_path = os.path.normpath(guide_path)
    with open(guide_path, 'r', encoding='utf-8') as f:
        guide = f.read()
    # 指南中明确描述的命令（基本命令表）
    # 指南提到：任意文字、状态、帮助、quit/exit
    assert '状态' in guide, "指南缺少状态命令"
    assert '帮助' in guide, "指南缺少帮助命令"
    assert 'quit' in guide.lower() or 'exit' in guide.lower(), "指南缺少 quit 命令"
    # 游戏流程部分提到 new（第一步：创建角色）
    assert '创建' in guide, "指南缺少角色创建说明"
    # 存档部分提到继续
    assert '继续' in guide, "指南缺少继续游戏说明"
    # 对比 HELP_TEXT 中的核心命令（new/continue/help/quit）
    help_text = interactive_master.HELP_TEXT
    assert ('new' in help_text.lower() or '开始游戏' in help_text)
    print("D-003: PLAYER_GUIDE.md 命令与实现一致 - PASS")


def test_d003_guide_races_and_classes():
    """D-003: 指南中的种族/职业列表与实现一致"""
    from src import CharacterCreator
    guide_path = os.path.join(os.path.dirname(__file__), '..', '..', 'docs', 'PLAYER_GUIDE.md')
    guide_path = os.path.normpath(guide_path)
    with open(guide_path, 'r', encoding='utf-8') as f:
        guide = f.read()
    # 指南列出种族
    assert '人类' in guide or 'Human' in guide
    assert '精灵' in guide or 'Elf' in guide
    assert '矮人' in guide or 'Dwarf' in guide
    assert '兽人' in guide or 'Orc' in guide
    # 指南列出职业
    assert '战士' in guide or 'Warrior' in guide
    assert '游侠' in guide or 'Ranger' in guide
    assert '法师' in guide or 'Mage' in guide
    assert '盗贼' in guide or 'Rogue' in guide
    print("D-003: PLAYER_GUIDE.md 种族/职业列表完整 - PASS")


if __name__ == '__main__':
    test_d001_module_import()
    test_d001_main_has_correct_commands()
    test_d001_game_loop_handles_commands()
    test_d002_character_creator_integration()
    test_d002_race_class_mappings()
    test_d003_player_guide_exists()
    test_d003_guide_start_command()
    test_d003_guide_commands_match_implementation()
    test_d003_guide_races_and_classes()
    print("\n✅ D-001/D-002/D-003 全部验收通过")
