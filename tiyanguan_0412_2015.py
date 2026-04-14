"""
体验官 - 完整游戏体验测试 2026-04-12 20:15
重点测试：系统命令、酒馆NPC对话、场景切换
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
from src.quest_state import QuestStage

async def playtest():
    print("=" * 60)
    print("体验官完整游戏体验 2026-04-12 20:15")
    print("=" * 60)
    
    start_time = time.time()
    
    # === 初始化 ===
    print("\n[阶段0] 初始化")
    bus = await init_event_bus()
    master = await init_game_master()
    await master.initialize()
    
    creator = get_character_creator()
    tutorial = get_tutorial_system()
    tutorial.set_mode(TutorialMode.SKIP)
    
    # === 角色创建 ===
    print("\n[阶段1] 角色创建")
    char = creator.create_from_selection('阿辉', 'human', 'warrior')
    print(f"角色: {char.name} | {char.race_name} | {char.class_name}")
    print(f"HP: {char.current_hp}/{char.max_hp} | AC: {char.armor_class} | 金币: {char.gold}")
    
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
    
    # === 叙事订阅 ===
    latest = {}
    ev = asyncio.Event()
    
    async def handler(event):
        latest['text'] = event.data.get('text', '')
        latest['turn'] = event.data.get('turn', '?')
        latest['mode'] = event.data.get('mode', '?')
        ev.set()
    
    await bus.subscribe(EventType.NARRATIVE_OUTPUT, handler, 'play_out')
    await bus.subscribe(EventType.COMBAT_START, handler, 'play_combat_start')
    await bus.subscribe(EventType.COMBAT_END, handler, 'play_combat_end')
    
    async def wait_narrative(timeout=45):
        ev.clear()
        latest['text'] = ''
        try:
            await asyncio.wait_for(ev.wait(), timeout=timeout)
        except asyncio.TimeoutError:
            latest['text'] = '[超时]'
        return latest.get('text', '')
    
    results = []  # (阶段, 输入, 叙事, 模式)
    
    # === 阶段2: 新手引导/开局 ===
    print("\n[阶段2] 新手引导/开局")
    
    # 开场场景
    print("\n--- 开场场景 ---")
    text = await wait_narrative()
    print(f"开场叙事: {text[:300] if text else '(空)'}")
    results.append(('开局', '自动开场', text, latest.get('mode', '?')))
    
    # 教程对话
    inputs_tutorial = [
        '你好',
        '我是新来的冒险者',
        '月叶镇有什么有趣的地方吗',
        '好的，谢谢'
    ]
    
    for inp in inputs_tutorial:
        print(f"\n--- 教程回合: {inp} ---")
        await master.handle_player_message(inp)
        text = await wait_narrative()
        print(f"叙事: {text[:300] if text else '(空)'}")
        results.append(('教程', inp, text, latest.get('mode', '?')))
    
    # 完成教程
    tutorial.complete_tutorial()
    print("\n教程已完成")
    
    # === 阶段3: 系统命令测试 ===
    print("\n[阶段3] 系统命令测试")
    
    sys_commands = [
        ('/状态', '查看状态'),
        ('/背包', '查看背包'),
        ('/任务', '查看任务'),
        ('/帮助', '查看帮助'),
    ]
    
    for cmd, desc in sys_commands:
        print(f"\n--- 系统命令: {desc} ---")
        await master.handle_player_message(cmd)
        text = await wait_narrative(60)
        print(f"响应: {text[:400] if text else '(空)'}")
        results.append(('系统命令', cmd, text, latest.get('mode', '?')))
    
    # === 阶段4: 场景切换测试 ===
    print("\n[阶段4] 场景切换测试")
    
    scene_changes = [
        ('去酒馆', '场景切换-酒馆'),
        ('去商店', '场景切换-商店'),
        ('回镇中心', '场景切换-镇中心'),
    ]
    
    for inp, desc in scene_changes:
        print(f"\n--- {desc}: {inp} ---")
        loc = master.game_state.get('location', '?')
        print(f"当前位置: {loc}")
        await master.handle_player_message(inp)
        text = await wait_narrative()
        new_loc = master.game_state.get('location', '?')
        print(f"新位置: {new_loc}")
        print(f"叙事: {text[:300] if text else '(空)'}")
        results.append((desc, inp, text, latest.get('mode', '?')))
    
    # === 阶段5: 酒馆NPC对话测试 ===
    print("\n[阶段5] 酒馆NPC对话测试")
    
    # 先进入酒馆
    print("\n--- 进入酒馆 ---")
    await master.handle_player_message('进入酒馆')
    text = await wait_narrative()
    print(f"酒馆描述: {text[:300] if text else '(空)'}")
    results.append(('酒馆进入', '进入酒馆', text, latest.get('mode', '?')))
    
    # 酒馆NPC对话测试（多种命令变体）
    tavern_commands = [
        ('和老板说话', '酒馆NPC-老板'),
        ('和酒馆老板交谈', '酒馆NPC-老板2'),
        ('Talk to the innkeeper', '酒馆NPC-英文'),
        ('询问任务', '酒馆NPC-任务'),
        ('老板有什么消息吗', '酒馆NPC-闲聊'),
        ('我要买药水', '酒馆NPC-买药水'),
    ]
    
    for inp, desc in tavern_commands:
        print(f"\n--- {desc}: {inp} ---")
        mode_before = master.mode
        loc = master.game_state.get('location', '?')
        print(f"当前模式: {mode_before}, 位置: {loc}")
        await master.handle_player_message(inp)
        text = await wait_narrative()
        mode_after = master.mode
        print(f"模式变化: {mode_before} -> {mode_after}")
        print(f"响应: {text[:400] if text else '(空)'}")
        results.append(('酒馆NPC', inp, text, latest.get('mode', '?')))
    
    # === 阶段6: 自由探索 ===
    print("\n[阶段6] 自由探索")
    
    free_actions = [
        ('查看周围环境', '自由探索'),
        ('查看有什么人', '自由探索-NPC'),
        ('去街上看看', '场景切换-街道'),
        ('攻击', '战斗测试'),
    ]
    
    for inp, desc in free_actions:
        print(f"\n--- {desc}: {inp} ---")
        await master.handle_player_message(inp)
        text = await wait_narrative()
        print(f"响应: {text[:300] if text else '(空)'}")
        results.append(('自由探索', inp, text, latest.get('mode', '?')))
    
    # === 统计分析 ===
    print("\n" + "=" * 60)
    print("=== 体验统计 ===")
    
    total_time = time.time() - start_time
    total_turns = master.game_state.get('turn', 0)
    
    empty_count = sum(1 for _, _, t, _ in results if not t or t == '[超时]' or t == '[超时] 无叙事响应')
    ai_expose = sum(1 for _, _, t, _ in results if t and (
        '正在寻找' in t or '类型的地点' in t or '这是一个' in t or
        'DM说' in t or '(DM)' in t or '系统说' in t
    ))
    sys_cmd_success = sum(1 for _, inp, t, _ in results if inp.startswith('/') and t and len(t) > 10)
    tavern_success = sum(1 for _, _, t, _ in results if '酒馆' in str(results) and t and len(t) > 20)
    
    # 分类统计
    phase_stats = {}
    for phase, inp, text, mode in results:
        if phase not in phase_stats:
            phase_stats[phase] = {'total': 0, 'empty': 0, 'texts': []}
        phase_stats[phase]['total'] += 1
        if not text or text == '[超时]' or text == '[超时] 无叙事响应':
            phase_stats[phase]['empty'] += 1
        phase_stats[phase]['texts'].append(text[:100] if text else '')
    
    print(f"总耗时: {total_time:.1f}秒")
    print(f"总回合: {total_turns}")
    print(f"总测试次数: {len(results)}")
    print(f"空响应: {empty_count}/{len(results)} ({empty_count*100//len(results)}%)")
    print(f"AI暴露: {ai_expose}次")
    print(f"系统命令成功: {sys_cmd_success}/{len(sys_commands)}")
    
    print("\n各阶段统计:")
    for phase, stats in phase_stats.items():
        empty_pct = stats['empty'] * 100 // stats['total'] if stats['total'] > 0 else 0
        print(f"  {phase}: {stats['total']}次, 空响应{empty_pct}%")
    
    print(f"\n最终位置: {master.game_state.get('location', '?')}")
    print(f"玩家HP: {master.game_state['player_stats']['hp']}/{master.game_state['player_stats']['max_hp']}")
    
    # === 详细记录 ===
    print("\n" + "=" * 60)
    print("=== 详细记录 ===")
    for i, (phase, inp, text, mode) in enumerate(results):
        print(f"\n[{i+1}] {phase} | {inp}")
        print(f"  模式: {mode}")
        print(f"  叙事: {text[:200] if text else '(空)'}")
    
    # === 生成报告 ===
    report = f"""# 体验报告

## 基本信息
- **游玩时间**: {total_time:.1f}秒
- **到达阶段**: 完成全部测试流程
- **死亡次数**: 0（未遭遇致命战斗）
- **总回合**: {total_turns}
- **测试次数**: {len(results)}

## 叙事体验

### 开场叙事
"""
    # 开局分析
    opening = next((t for p, i, t, m in results if p == '开局'), '')
    report += f"- 开场叙事质量: {'良好' if opening and len(opening) > 50 else '偏短' if opening else '无响应'}\n"
    report += f"- 开场内容: {opening[:200] if opening else '(无)'}\n\n"
    
    report += """### NPC对话
"""
    tavern_results = [(i, t) for p, i, t, m in results if p == '酒馆NPC']
    for inp, text in tavern_results:
        status = '✓ 有响应' if text and len(text) > 20 else '✗ 无响应/过短'
        report += f"- **{inp}**: {status}\n"
        if text and len(text) > 50:
            report += f"  - {text[:150]}...\n"
    report += "\n"
    
    report += """### 战斗叙事
"""
    combat_results = [(p, i, t) for p, i, t, m in results if m == 'combat' or '攻击' in i]
    if combat_results:
        for p, i, t in combat_results:
            report += f"- {i}: {t[:100] if t else '(空)'}...\n"
    else:
        report += "- 未触发战斗\n"
    report += "\n"
    
    report += """## 节奏体验
"""
    avg_text_len = sum(len(t) for _, _, t, _ in results if t) / max(1, len([t for _, _, t, _ in results if t]))
    report += f"- 平均响应长度: {avg_text_len:.0f}字符\n"
    report += f"- 响应速度: {'流畅' if total_time / len(results) < 5 else '偏慢'}\n"
    report += f"- 节奏评分: {'良好' if avg_text_len > 80 else '偏短'}\n\n"
    
    report += """## 具体问题

### P0 (崩溃/致命)
"""
    p0_issues = [(p, i, t) for p, i, t, m in results if not t or t == '[超时]' or t == '[超时] 无叙事响应']
    if p0_issues:
        for p, i, t in p0_issues:
            report += f"- **{p}** - {i}: 无响应\n"
    else:
        report += "- 无P0问题\n"
    report += "\n"
    
    report += """### P1 (严重影响体验)
"""
    sys_cmd_fails = [(i, t) for p, i, t, m in results if p == '系统命令' and (not t or len(t) < 10)]
    if sys_cmd_fails:
        report += "- 系统命令响应异常:\n"
        for i, t in sys_cmd_fails:
            report += f"  - {i}: {'无响应' if not t else '响应过短:' + t[:50]}\n"
    else:
        report += "- 系统命令正常\n"
    
    tavern_fails = [(i, t) for p, i, t, m in results if p == '酒馆NPC' and (not t or len(t) < 20)]
    if tavern_fails:
        report += "- 酒馆NPC对话异常:\n"
        for i, t in tavern_fails:
            report += f"  - {i}: {'无响应' if not t else '响应过短'}\n"
    else:
        report += "- 酒馆NPC对话正常\n"
    report += "\n"
    
    report += """### P2 (需改进)
"""
    ai_expose_list = [(p, i, t) for p, i, t, m in results if t and ('正在寻找' in t or '类型的地点' in t or '这是一个' in t)]
    if ai_expose_list:
        report += "- AI暴露/模板化叙事:\n"
        for p, i, t in ai_expose_list:
            report += f"  - {p} ({i[:20]}...)\n"
    else:
        report += "- 无明显P2问题\n"
    report += "\n"
    
    # 总体评分
    quality_issues = empty_count + ai_expose
    score = max(0, 10 - quality_issues * 0.5 - (avg_text_len < 60) * 1)
    report += f"""## 总体评分

**评分: {score}/10**

### 总结
"""
    if empty_count > len(results) * 0.2:
        report += f"- ⚠️ 空响应率偏高 ({empty_count}/{len(results)})\n"
    if sys_cmd_success < len(sys_commands):
        report += f"- ⚠️ 系统命令成功率偏低 ({sys_cmd_success}/{len(sys_commands)})\n"
    if tavern_fails:
        report += f"- ⚠️ 酒馆NPC对话存在问题\n"
    if empty_count < 3:
        report += "- ✓ 整体响应质量良好\n"
    if avg_text_len > 60:
        report += f"- ✓ 叙事内容充实（平均{avg_text_len:.0f}字符）\n"
    
    report += f"\n**详细测试记录**: {len(results)}次交互，覆盖开局、教程、系统命令、场景切换、酒馆NPC、自由探索\n"
    
    print("\n" + "=" * 60)
    print(report)
    
    # 保存报告
    report_path = 'C:/Users/15901/.openclaw/workspace-ai-dm-rpg/tasks/tiyanguan_report_20260412_2015.md'
    with open(report_path, 'w', encoding='utf-8') as f:
        f.write(report)
    print(f"\n报告已保存: {report_path}")
    
    # 保存完整数据
    data_path = 'C:/Users/15901/.openclaw/workspace-ai-dm-rpg/tasks/tiyanguan_0412_2015.json'
    with open(data_path, 'w', encoding='utf-8') as f:
        json.dump({
            'results': [(p, i, t, m) for p, i, t, m in results],
            'stats': {
                'total_time': total_time,
                'total_turns': total_turns,
                'empty_count': empty_count,
                'ai_expose': ai_expose,
                'sys_cmd_success': sys_cmd_success,
                'score': score,
            }
        }, f, ensure_ascii=False, indent=2)
    print(f"数据已保存: {data_path}")
    
    await master.stop()
    await bus.stop()
    
    return results, report

if __name__ == '__main__':
    asyncio.run(playtest())
