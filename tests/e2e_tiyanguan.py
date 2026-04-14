"""
体验官 E2E 测试 - 验证 3 个 P0 Bug 修复

运行方式:
cd C:/Users/15901/.openclaw/workspace/ai-dm-rpg
python tests/e2e_tiyanguan.py
"""

import sys
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

import asyncio
from src.game_master import GameMaster, GameMode
from src.event_bus import EventBus


async def test_bug_002_scene_switch_resets_combat():
    """Bug #002: active_combat 场景切换后未清理"""
    print("\n=== 测试 Bug #002: 场景切换重置 active_combat ===")
    
    event_bus = EventBus()
    gm = GameMaster(event_bus=event_bus)
    gm.llm = None  # 不需要 LLM
    
    # 模拟在森林中进入战斗
    gm.current_scene = {
        "type": "森林",
        "name": "迷雾森林",
        "description": "树木茂密",
    }
    gm.game_state["location"] = "森林"
    gm.game_state["mode"] = "combat"
    gm.active_combat = True
    gm.mode = GameMode.COMBAT
    
    # 切换到酒馆
    result = await gm._generate_scene("酒馆")
    
    # 验证
    passed = (
        gm.active_combat == False and
        gm.game_state.get("active_combat") == False and
        gm.mode == GameMode.EXPLORATION
    )
    print(f"  active_combat 状态: {gm.active_combat} (期望: False)")
    print(f"  game_state['active_combat']: {gm.game_state.get('active_combat')} (期望: False)")
    print(f"  mode: {gm.mode} (期望: EXPLORATION)")
    print(f"  ✅ PASSED" if passed else f"  ❌ FAILED")
    return passed


async def test_bug_003_command_normalization():
    """Bug #003: 命令归一化缺失"""
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
        print(f"  「{cmd}」→ action={norm['action']}, trigger={'✓' if result else '✗'}")
    
    all_ok = all(ok and tr for _, ok, tr, _ in results)
    print(f"  ✅ PASSED" if all_ok else f"  ❌ FAILED")
    return all_ok


async def test_bug_004_scene_fallback_no_crash():
    """Bug #004: 场景上下文初始化（fallback 路径不崩溃）"""
    print("\n=== 测试 Bug #004: 场景 fallback 不崩溃 ===")
    
    event_bus = EventBus()
    gm = GameMaster(event_bus=event_bus)
    gm.llm = None
    
    # Mock scene_agent to return None (triggers fallback)
    class MockSceneAgent:
        _last_scene_fallback = True
        _last_fallback_tier = 1
        registry = None
        
        def get_existing_scene(self, scene_type):
            return None
        
        async def generate_scene(self, scene_type, requirements, quest_hint):
            # Return a minimal scene object (not a dict)
            class FakeScene:
                id = f"fallback_{scene_type}"
                description = f"这是 {scene_type} 的 fallback 描述"
                atmosphere_history = []
            return FakeScene()
    
    gm.scene_agent = MockSceneAgent()
    
    try:
        result = await gm._generate_scene("酒馆")
        has_id = "id" in gm.current_scene
        has_type = "type" in gm.current_scene
        has_desc = "description" in gm.current_scene
        passed = has_id and has_type and has_desc
        print(f"  current_scene.id: {'✓' if has_id else '✗'}")
        print(f"  current_scene.type: {'✓' if has_type else '✗'}")
        print(f"  current_scene.description: {'✓' if has_desc else '✗'}")
        print(f"  ✅ PASSED" if passed else f"  ❌ FAILED")
        return passed
    except Exception as e:
        print(f"  ❌ FAILED with exception: {e}")
        return False


async def test_scene_switch_preserves_state():
    """场景切换后游戏状态保持正常"""
    print("\n=== 测试: 场景切换后状态保持 ===")
    
    event_bus = EventBus()
    gm = GameMaster(event_bus=event_bus)
    gm.llm = None
    
    # 初始场景
    await gm._generate_scene("酒馆")
    location1 = gm.game_state.get("location")
    print(f"  酒馆切换后 location: {location1}")
    
    # 切换到森林
    await gm._generate_scene("森林")
    location2 = gm.game_state.get("location")
    print(f"  森林切换后 location: {location2}")
    
    # 验证
    passed = location1 == "酒馆" and location2 == "森林"
    print(f"  ✅ PASSED" if passed else f"  ❌ FAILED")
    return passed


async def test_command_variants_all_trigger():
    """命令变体都能触发响应（无响应率测试）"""
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
        "攻击 goblin",
        "去酒馆",
        "探索",
        "查看周围",
    ]
    
    responses = []
    for cmd in commands:
        # _generate_main_narrative 需要 LLM，这里用简单方法测试
        trigger = gm._check_combat_trigger(cmd)
        scene_result = gm._check_scene_update(cmd)
        norm = gm._normalize_command(cmd)
        
        has_response = trigger is not None or scene_result is not None or norm["action"] != ""
        responses.append((cmd, has_response))
        print(f"  「{cmd}」→ {'✓ 有响应' if has_response else '✗ 无响应'}")
    
    no_response_count = sum(1 for _, r in responses if not r)
    no_response_rate = no_response_count / len(responses) * 100
    print(f"  无响应率: {no_response_rate:.1f}% ({no_response_count}/{len(responses)})")
    
    passed = no_response_rate == 0
    print(f"  ✅ PASSED" if passed else f"  ❌ FAILED")
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
        status = "✅ PASSED" if passed else "❌ FAILED"
        print(f"  {name}: {status}")
    
    all_passed = all(results.values())
    print(f"\n综合评分: {'10/10' if all_passed else '7/10'}")
    print(f"无响应率: {no_resp_rate:.1f}%")
    
    return all_passed


if __name__ == "__main__":
    asyncio.run(main())
