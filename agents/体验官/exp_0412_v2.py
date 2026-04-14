"""
体验官自动体验 2026-04-12 10:06
"""
import asyncio
import sys
import json
import time
sys.path.insert(0, '.')
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

from src import init_event_bus, init_game_master, EventType, Event
from src.character_creator import get_character_creator
from src.tutorial_system import get_tutorial_system

def detect_template(text):
    templates = ["你听到回声", "空气中弥漫着", "你的声音在空气中回荡",
                 "mysterious", "神秘", "微风吹拂"]
    return [t for t in templates if t in text]

def detect_ai_ref(text):
    patterns = [r"DM", r"\(DM\)", r"DM说", r"系统说", r"请选择", r"提示"]
    return [p for p in patterns if p in text]

def quality_score(text):
    if not text or len(text.strip()) < 20:
        return 0, ["无响应"]
    s = 10
    tmpl = detect_template(text)
    refs = detect_ai_ref(text)
    if tmpl:
        s -= min(len(tmpl) * 2, 6)
    if refs:
        s -= min(len(refs) * 2, 4)
    if len(text) < 100:
        s -= 2
    return max(0, s), tmpl

async def playtest():
    print("=" * 60)
    print("体验官自动体验 2026-04-12 10:06")
    print("=" * 60)

    bus = await init_event_bus()
    master = await init_game_master()
    await master.initialize()

    creator = get_character_creator()
    tutorial = get_tutorial_system()
    tutorial.set_mode('skip')

    char = creator.create_from_selection('体验官', 'human', 'warrior')
    print(f"\n[角色] {char.name} | {char.race_name} | {char.class_name} | HP:{char.current_hp}/{char.max_hp}")

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

    latest = {}
    ev = asyncio.Event()

    async def handler(event):
        latest['text'] = event.data.get('text', '')
        latest['turn'] = event.data.get('turn', '?')
        ev.set()

    await bus.subscribe(EventType.NARRATIVE_OUTPUT, handler, 'play_out')
    await bus.subscribe(EventType.COMBAT_START, handler, 'play_combat')
    await bus.subscribe(EventType.COMBAT_END, handler, 'play_combat_end')

    results = []

    async def act(action, phase):
        latest.clear()
        ev.clear()
        t0 = time.time()
        await master.handle_player_message(action)
        try:
            await asyncio.wait_for(ev.wait(), timeout=30.0)
        except asyncio.TimeoutError:
            resp = None
        else:
            resp = latest.get('text')
        elapsed = time.time() - t0
        q, tmpl = quality_score(resp or '')
        stats = master.game_state.get('player_stats', {})
        entry = {
            'phase': phase,
            'action': action,
            'response': resp,
            'quality': q,
            'templates': tmpl,
            'elapsed': elapsed,
            'hp': stats.get('hp'),
            'location': master.game_state.get('location', '?'),
        }
        results.append(entry)
        tag = f"[Q{q}]" if q > 0 else "[无]"
        print(f"\n--- {phase} ---")
        print(f"操作: {action}")
        print(f"质量: {tag} {tmpl}")
        print(f"用时: {elapsed:.1f}s | HP: {stats.get('hp')}/{stats.get('max_hp')} | 位置: {entry['location']}")
        print(f"叙事: {(resp or '(无响应)')[:300]}")
        return resp

    # 探索流程
    await act('环顾四周', '开场-环顾')
    await act('描述一下这个镇子', '开场-描述镇子')
    await act('去镇中心看看', '探索-镇中心')
    await act('和周围的人说话', '探索-NPC交流')
    await act('去酒馆', '探索-酒馆')
    await act('向酒保打听最近的新鲜事', '酒馆-打听消息')
    await act('酒馆里有看起来有趣的人吗', '酒馆-观察')
    await act('和那个角落里的陌生人交谈', '酒馆-陌生人对话')
    await act('查看状态', '系统-状态')
    await act('查看背包', '系统-背包')
    await act('使用治疗药水', '道具-使用药水')

    # 保存数据
    with open('agents/体验官/exp_0412_data.json', 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    print("\n" + "=" * 60)
    print("体验完成，数据已保存")
    print("=" * 60)

    await master.stop()
    await bus.stop()

asyncio.run(playtest())
