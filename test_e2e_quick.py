import sys
import asyncio
import time
sys.path.insert(0, '.')
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
print("=" * 60, flush=True)
print("Quick E2E Test 2026-04-12", flush=True)
print("=" * 60, flush=True)

from src import init_event_bus, init_game_master, EventType, Event
from src.character_creator import get_character_creator
from src.tutorial_system import get_tutorial_system, TutorialMode

async def main():
    start = time.time()
    
    bus = await init_event_bus()
    master = await init_game_master()
    await master.initialize()
    
    creator = get_character_creator()
    char = creator.create_from_selection('体验官', 'human', 'warrior')
    print(f"[角色] {char.name} | {char.race_name} | {char.class_name}", flush=True)
    
    master.game_state['player_stats'] = {
        'hp': char.current_hp, 'max_hp': char.max_hp,
        'ac': char.armor_class, 'xp': char.xp,
        'level': char.level, 'gold': char.gold,
        'inventory': char.inventory,
        'name': char.name, 'race': char.race_name, 'class': char.class_name,
    }
    master.game_state['turn'] = 0
    master.game_state['location'] = '月叶镇'
    master.game_state['active_npcs_per_scene'] = {}
    master.game_state['active_npcs'] = {}
    master.game_state['quest_stage'] = 'not_started'
    master.game_state['quest_active'] = False
    
    tutorial = get_tutorial_system()
    tutorial.set_mode(TutorialMode.SKIP)
    
    latest = {}
    ev = asyncio.Event()
    
    async def handler(event):
        latest['text'] = event.data.get('text', '')
        latest['type'] = event.type.value
        ev.set()
    
    await bus.subscribe(EventType.NARRATIVE_OUTPUT, handler, 'e2e')
    await bus.subscribe(EventType.COMBAT_START, handler, 'e2e_combat')
    await bus.subscribe(EventType.COMBAT_END, handler, 'e2e_combat_end')
    
    results = []
    
    async def act(msg, label):
        latest.clear()
        ev.clear()
        print(f"\n>>> [{label}] {msg}", flush=True)
        try:
            result = await asyncio.wait_for(master.handle_player_message(msg), timeout=30)
        except asyncio.TimeoutError:
            result = "(超时)"
        try:
            await asyncio.wait_for(ev.wait(), timeout=30)
        except asyncio.TimeoutError:
            pass
        text = latest.get('text', result or '')
        print(f"    [{latest.get('type','?')}] {text[:200] if text else '(无)'}...", flush=True)
        results.append({'phase': label, 'message': msg, 'narrative': text[:300], 'type': latest.get('type', '?')})
        return text
    
    # 快速测试各阶段
    print("\n[阶段] Tutorial", flush=True)
    await act("教程", "Tutorial")
    
    print("\n[阶段] 探索", flush=True)
    await act("探索月叶镇", "Explore-Town")
    await act("去镇中心", "Move-Center")
    await act("去酒馆", "Move-Tavern")
    
    print("\n[阶段] 系统命令", flush=True)
    await act("状态", "Status")
    await act("背包", "Inventory")
    await act("任务", "Quest")
    await act("帮助", "Help")
    
    print("\n[阶段] 探索指令", flush=True)
    await act("look", "Look-EN")
    await act("看看周围", "Look-CN")
    await act("search", "Search-EN")
    await act("仔细搜索", "Search-CN")
    await act("move 镇中心", "Move-CN")
    await act("和酒馆老板说话", "Talk-CN")
    
    print("\n[阶段] 战斗触发", flush=True)
    await act("去森林", "Scene-Forest")
    await act("深入森林", "Scene-Forest-Deep")
    await act("调查声音", "Explore-Investigate")
    
    print("\n[阶段] 战斗", flush=True)
    await act("攻击", "Combat-Attack")
    await act("防御", "Combat-Defend")
    
    elapsed = time.time() - start
    print(f"\n{'='*60}", flush=True)
    print(f"测试完成! 耗时: {elapsed:.1f}s, 回合: {master.game_state['turn']}", flush=True)
    
    # 统计
    no_response = [r for r in results if not r.get('narrative') or r.get('narrative') == '(无)']
    print(f"无响应次数: {len(no_response)}", flush=True)
    
    # 保存结果
    import json
    with open('C:/Users/15901/.openclaw/workspace/ai-dm-rpg/tasks/quick_test_1341.json', 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    
    await master.stop()
    await bus.stop()
    
    return results

asyncio.run(main())
print("Done.", flush=True)
