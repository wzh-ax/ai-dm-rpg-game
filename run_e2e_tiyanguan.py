import sys
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

import asyncio
from src.game_master import GameMaster, GameMode
from src.event_bus import EventBus


async def test_bug_002_scene_switch_resets_combat():
    print("\n=== 测试 Bug #002: 场景切换重置 active_combat ===")
    
    event_bus = EventBus()
    gm = GameMaster(event_bus=event_bus)
    gm.llm = None
    
    gm.current_scene = {
        "type": "森林",
        "name": "迷雾森林",
        "description": "树木茂密",
    }
    gm.game_state["location"] = "森林"
    gm.game_state["mode"] = "combat"
    gm.active_combat = True
    gm.mode = GameMode.COMBAT
    
    result = await gm._generate_scene("酒馆")
    
    passed = (
        gm.active_combat == False and
        gm.game_state.get("active_combat") == False and
        gm.mode == GameMode.EXPLORATION
    )
    print(f"  active_combat: {gm.active_combat} (期望: False)")
    print(f"  game_state['active_combat']: {gm.game_state.get('active_combat')} (期望: False)")
    print(f"  mode: {gm.mode} (期望: EXPLORATION)")
    print(f"  {'PASSED' if passed else 'FAILED'}")
    return passed


async def test_bug_003_command_normalization():
    print("\n=== 测试 Bug #003: 命令归一化 ===")
    
    event_bus = EventBus()
    gm = GameMaster(event_bus=event_bus)
    gm.llm = None
    
    gm.current_scene = {
        "type": "森林",
        "name": "迷雾森林",
        "enemies": [{"name": "哥布林", "role": "goblin", "hp": 20, "ac": 10}]
    }
    gm.game_state["mode"] = "exploration"
    gm.game_state["active_combat"] = False
    
    test_cases = [
        ("攻击哥布林", "attack"),
        ("攻击", "attack"),
        ("attack goblin", "attack"),
        ("Attack", "attack"),
        ("打哥布林", "attack"),
        ("砍哥布林", "attack"),
    ]
    
    results = []
    for cmd, expected_action in test_cases:
        norm = gm._normalize_command(cmd)
        result = gm._check_combat_trigger(cmd)
        action_ok = norm["action"] == expected_action
        trigger_ok = result is not None
        results.append((cmd, action_ok, trigger_ok, norm["action"]))
        print(f"  [{cmd}] action={norm['action']} trigger={'OK' if result else 'NONE'}")
    
    all_ok = all(ok and tr for _, ok, tr, _ in results)
    print(f"  {'PASSED' if all_ok else 'FAILED'}")
    return all_ok


async def test_bug_004_scene_fallback_no_crash():
    print("\n=== 测试 Bug #004: 场景 fallback 不崩溃 ===")
    
    event_bus = EventBus()
    gm = GameMaster(event_bus=event_bus)
    gm.llm = None
    
    class FakeScene:
        def __init__(self, scene_type):
            self.id = f"fallback_{scene_type}"
            self.description = f"这是 {scene_type} 的 fallback 描述"
            self.atmosphere_history = []
        
        def to_dict(self):
            return {
                "id": self.id,
                "description": self.description,
                "type": "fallback",
                "atmosphere": "未知",
                "atmosphere_desc": "",
                "atmosphere_light": "",
                "atmosphere_sound": "",
                "atmosphere_smell": "",
                "atmosphere_temperature": "",
                "atmosphere_mood": "",
                "npcs": [],
            }
    
    class MockSceneAgent:
        _last_scene_fallback = True
        _last_fallback_tier = 1
        registry = None
        def get_existing_scene(self, scene_type):
            return None
        async def generate_scene(self, scene_type, requirements, quest_hint):
            return FakeScene(scene_type)
    
    gm.scene_agent = MockSceneAgent()
    
    try:
        result = await gm._generate_scene("酒馆")
        has_id = "id" in gm.current_scene
        has_type = "type" in gm.current_scene
        has_desc = "description" in gm.current_scene
        passed = has_id and has_type and has_desc
        print(f"  id: {'OK' if has_id else 'MISSING'}")
        print(f"  type: {'OK' if has_type else 'MISSING'}")
        print(f"  description: {'OK' if has_desc else 'MISSING'}")
        print(f"  {'PASSED' if passed else 'FAILED'}")
        return passed
    except Exception as e:
        print(f"  FAILED with: {e}")
        return False


async def test_scene_switch_preserves_state():
    print("\n=== 测试: 场景切换后状态保持 ===")
    
    event_bus = EventBus()
    gm = GameMaster(event_bus=event_bus)
    gm.llm = None
    
    await gm._generate_scene("酒馆")
    location1 = gm.game_state.get("location")
    print(f"  酒馆 location: {location1}")
    
    await gm._generate_scene("森林")
    location2 = gm.game_state.get("location")
    print(f"  森林 location: {location2}")
    
    passed = location1 == "酒馆" and location2 == "森林"
    print(f"  {'PASSED' if passed else 'FAILED'}")
    return passed


async def test_command_variants_all_trigger():
    print("\n=== 测试: 命令变体响应率 ===")
    
    event_bus = EventBus()
    gm = GameMaster(event_bus=event_bus)
    gm.llm = None
    
    gm.current_scene = {
        "type": "森林",
        "name": "迷雾森林",
        "enemies": [{"name": "哥布林", "role": "goblin", "hp": 20, "ac": 10}]
    }
    gm.game_state["mode"] = "exploration"
    gm.game_state["active_combat"] = False
    
    commands = [
        "攻击哥布林",
        "攻击",
        "attack goblin",
        "Attack",
        "去酒馆",
        "探索",
        "查看周围",
    ]
    
    no_response_count = 0
    for cmd in commands:
        trigger = gm._check_combat_trigger(cmd)
        scene_result = await gm._check_scene_update(cmd)
        norm = gm._normalize_command(cmd)
        has_response = trigger is not None or scene_result is not None or norm["action"] != ""
        if not has_response:
            no_response_count += 1
        print(f"  [{cmd}] {'OK' if has_response else 'NONE'}")
    
    no_response_rate = no_response_count / len(commands) * 100
    print(f"  无响应率: {no_response_rate:.1f}% ({no_response_count}/{len(commands)})")
    passed = no_response_rate == 0
    print(f"  {'PASSED' if passed else 'FAILED'}")
    return passed, no_response_rate


async def main():
    print("=" * 60)
    print("AI DM RPG 体验官 E2E 测试")
    print("=" * 60)
    
    results = {}
    
    results["bug_002"] = await test_bug_002_scene_switch_resets_combat()
    results["bug_003"] = await test_bug_003_command_normalization()
    results["bug_004"] = await test_bug_004_scene_fallback_no_crash()
    results["scene_switch"] = await test_scene_switch_preserves_state()
    results["command_response"], no_resp_rate = await test_command_variants_all_trigger()
    
    print("\n" + "=" * 60)
    print("测试结果汇总")
    print("=" * 60)
    for name, passed in results.items():
        print(f"  {name}: {'PASSED' if passed else 'FAILED'}")
    
    all_passed = all(results.values())
    print(f"\n综合评分: {'10/10' if all_passed else '7/10'}")
    print(f"无响应率: {no_resp_rate:.1f}%")
    
    return all_passed


if __name__ == "__main__":
    asyncio.run(main())
