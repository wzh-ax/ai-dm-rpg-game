"""
体验官新鲜体验 2026-04-12 01:20
"""
import asyncio
import sys
import json
import time
sys.path.insert(0, '.')
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

from src import init_event_bus, init_game_master, EventType, Event
from src.character_creator import get_character_creator
from src.tutorial_system import get_tutorial_system, TutorialMode

def detect_template(text):
    templates = ["空气中弥漫着", "你的声音在空气中回荡", "这里似乎没有",
                 "mysterious", "阳光洒落", "微风吹过"]
    return [t for t in templates if t in text]

def detect_ai_ref(text):
    patterns = [r"玩家正在", r"\(DM\)", r"DM正在", r"请输入", r"系统提示", r"你选择"]
    return [p for p in patterns if p in text]

def quality_score(text):
    if not text or len(text.strip()) < 20:
        return 0, ["空响应"]
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
    print("体验官定时体验 2026-04-12 01:20")
    print("=" * 60)

    bus = await init_event_bus()
    master = await init_game_master()
    await master.initialize()

    creator = get_character_creator()
    tutorial = get_tutorial_system()
    tutorial.set_mode(TutorialMode.SKIP)

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
            "action": action, "phase": phase, "elapsed": round(elapsed, 1),
            "resp_len": len(resp) if resp else 0,
            "quality": q, "templates": tmpl,
            "preview": (resp[:250] if resp else "[空]"),
            "location": master.game_state.get('location', '?'),
            "hp": stats.get('hp', 0), "turn": master.game_state.get('turn', 0),
        }
        results.append(entry)
        ico = "✅" if q >= 8 else "⚠️" if q >= 5 else "❌"
        print(f"  {ico} [{phase}] {action[:30]} | Q:{q} | {len(resp or '')}字 | {elapsed:.1f}s | {master.game_state.get('location','?')}")
        if tmpl:
            print(f"       模板: {tmpl}")
        return resp

    # Stage 1: Opening
    print("\n=== Stage 1: Opening ===")
    await act("探索月叶镇", "opening")

    # Stage 2: NPC interaction
    print("\n=== Stage 2: NPC ===")
    await act("和周围的人说话", "npc")
    await act("向老人询问镇子的情况", "npc")
    await act("询问有什么任务", "npc")

    # Stage 3: System commands
    print("\n=== Stage 3: System ===")
    await act("查看状态", "system")
    await act("查看背包", "system")

    # Stage 4: Scene transitions
    print("\n=== Stage 4: Scene ===")
    await act("去酒馆", "scene")
    await act("在酒馆里四处看看", "scene")
    await act("和酒馆里的人交谈", "scene")

    # Stage 5: Combat
    print("\n=== Stage 5: Combat ===")
    await act("离开酒馆去野外", "scene")
    await act("在野外探索", "scene")
    combat_resp = await act("寻找敌人战斗", "combat")

    combat_active = master.game_state.get('game_mode') == 'combat'
    if combat_active or (combat_resp and '⚔️' in combat_resp):
        print("  [Combat triggered]")
        await act("攻击", "combat")
        await act("防御", "combat")
    else:
        await act("主动攻击一只野狼", "combat")

    # Stage 6: Edge cases
    print("\n=== Stage 6: Edge Cases ===")
    await act("我什么都不做只是站着发呆", "edge")
    await act("用头撞墙", "edge")
    await act("唱一首关于被遗忘国王的歌", "edge")

    # Summary
    total_time = time.time()
    qs = [r['quality'] for r in results]
    avg_q = sum(qs) / len(qs) if qs else 0
    empty_cnt = sum(1 for r in results if r['quality'] == 0)
    tmpl_cnt = sum(1 for r in results if r['templates'])

    summary = {
        "test_time": "2026-04-12 01:20",
        "total_actions": len(results),
        "avg_quality": round(avg_q, 1),
        "empty_responses": empty_cnt,
        "template_responses": tmpl_cnt,
        "results": results
    }

    with open('fresh_playtest_0412.json', 'w', encoding='utf-8') as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    print(f"\n=== Summary ===")
    print(f"Actions: {len(results)} | Avg Quality: {avg_q:.1f} | Empty: {empty_cnt} | Templates: {tmpl_cnt}")

    # Build report
    opening_results = [r for r in results if r['phase'] == 'opening']
    npc_results = [r for r in results if r['phase'] == 'npc']
    combat_results = [r for r in results if r['phase'] == 'combat']
    edge_results = [r for r in results if r['phase'] == 'edge']
    system_results = [r for r in results if r['phase'] == 'system']
    scene_results = [r for r in results if r['phase'] == 'scene']

    report_lines = []
    report_lines.append("## 体验报告")
    report_lines.append("### 基本信息")
    report_lines.append(f"- 游玩时长: 约{int(total_time)}秒")
    report_lines.append(f"- 到达阶段: 完成{len(results)}个动作")
    report_lines.append(f"- 死亡次数: 0")

    report_lines.append("\n### 叙事体验")
    report_lines.append("\n#### 开场叙事")
    if opening_results:
        r = opening_results[0]
        report_lines.append(f"- 质量:{r['quality']}/10 | 长度:{r['resp_len']}字")
        report_lines.append(f"- 预览: {r['preview'][:200]}...")
    else:
        report_lines.append("- 无开场数据")

    report_lines.append("\n#### NPC对话")
    for r in npc_results:
        report_lines.append(f"- [{r['action']}] Q:{r['quality']} | {r['resp_len']}字 | 预览:{r['preview'][:100]}...")

    report_lines.append("\n#### 战斗叙事")
    if combat_results:
        for r in combat_results:
            report_lines.append(f"- [{r['action']}] Q:{r['quality']} | {r['resp_len']}字")
    else:
        report_lines.append("- 未能成功触发战斗")

    report_lines.append("\n#### 系统命令")
    for r in system_results:
        report_lines.append(f"- [{r['action']}] Q:{r['quality']} | {r['resp_len']}字")

    report_lines.append("\n### 节奏体验")
    report_lines.append(f"- 平均质量: {avg_q:.1f}/10")
    report_lines.append(f"- 空响应率: {empty_cnt}/{len(results)}")
    report_lines.append(f"- 模板使用: {tmpl_cnt}次")

    report_lines.append("\n### 具体问题（按严重程度）")
    report_lines.append("| 阶段 | 问题 | 质量 | 严重度 |")
    report_lines.append("|------|------|------|--------|")
    for r in results:
        if r['quality'] < 5 or r['templates']:
            sev = "P0" if r['quality'] == 0 else "P1" if r['quality'] < 5 else "P2"
            report_lines.append(f"| {r['phase']} | {r['action']} | Q:{r['quality']} | {sev} |")

    report_lines.append(f"\n### 总体评分: {avg_q:.1f}/10")
    if avg_q >= 8:
        report_lines.append("**评价: 优秀 - 叙事质量高，响应及时**")
    elif avg_q >= 6:
        report_lines.append("**评价: 良好 - 有少量问题但整体体验可接受**")
    elif avg_q >= 4:
        report_lines.append("**评价: 一般 - 存在较多问题需要修复**")
    else:
        report_lines.append("**评价: 较差 - 存在阻断性问题，需要紧急修复**")

    report = "\n".join(report_lines)
    print("\n" + report)

    with open('fresh_playtest_report_0412.md', 'w', encoding='utf-8') as f:
        f.write(report)

    await master.stop()
    await bus.stop()
    return summary

if __name__ == "__main__":
    asyncio.run(playtest())
