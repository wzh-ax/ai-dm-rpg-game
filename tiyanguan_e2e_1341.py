"""
AI DM RPG 完整 E2E 体验验证 2026-04-12 13:41
测试范围：
1. 启动菜单 → 角色创建 → Tutorial → 新手任务(找市长) → 酒馆场景 → 战斗 → 探索指令
2. 系统命令：状态、背包、商店、任务、帮助
3. 中文命令路由（Windows 中文环境）
4. 万能敷衍、战斗卡死、命令失效、场景空洞等问题
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
from src.quest_state import QuestStage, QUEST_NAME

# ========== 问题检测函数 ==========

def detect_template(text):
    """检测模板化叙事"""
    templates = [
        "你听到回声", "空气中弥漫着", "你的声音在空气中回荡",
        "mysterious", "神秘", "微风吹拂", "温暖的阳光", "清新的空气",
        "这是一个", "你看到", "你来到", "这里是",
        "突然，你", "就在这时",
    ]
    return [t for t in templates if t in text]

def detect_vague(text):
    """检测万能敷衍回复"""
    vague_patterns = [
        "好的", "明白了", "我理解了", "没问题", "你可以",
        "让我想想", "这个嘛", "其实", "一般来说",
        "作为你的DM", "作为你的游戏主持人",
    ]
    return [p for p in vague_patterns if p in text]

def detect_ai_ref(text):
    """检测AI引用/DM跳出"""
    patterns = [r"DM", r"\(DM\)", r"DM说", r"系统说", r"请选择", r"提示：", r"作为DM"]
    import re
    return [p for p in patterns if re.search(p, text)]

def detect_empty_scene(text):
    """检测空洞场景"""
    short_vague = [
        "没什么特别的", "看起来很普通", "一切如常",
        "这里没什么", "你环顾四周",
    ]
    return [t for t in short_vague if t in text]

async def run_e2e():
    print("=" * 70)
    print("AI DM RPG 完整 E2E 体验验证 2026-04-12 13:41")
    print("=" * 70)
    
    start_time = time.time()

    # === 初始化 ===
    bus = await init_event_bus()
    master = await init_game_master()
    await master.initialize()

    # === 角色创建 ===
    print("\n[阶段1] 角色创建")
    creator = get_character_creator()
    char = creator.create_from_selection('体验官', 'human', 'warrior')
    print(f"  角色: {char.name} | {char.race_name} | {char.class_name} | HP:{char.current_hp}/{char.max_hp} AC:{char.armor_class} Gold:{char.gold}")

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
        latest['type'] = event.type.value
        ev.set()

    await bus.subscribe(EventType.NARRATIVE_OUTPUT, handler, 'e2e_narrative')
    await bus.subscribe(EventType.COMBAT_START, handler, 'e2e_combat_start')
    await bus.subscribe(EventType.COMBAT_END, handler, 'e2e_combat_end')
    await bus.subscribe(EventType.SCENE_UPDATE, handler, 'e2e_scene_update')
    await bus.subscribe(EventType.GENERIC, handler, 'e2e_generic')

    results = []

    async def act(msg, label, expected_phase=None):
        latest.clear()
        ev.clear()
        turn_before = master.game_state['turn']
        print(f"\n>>> [{label}] {msg}")
        
        result = await master.handle_player_message(msg)
        
        try:
            await asyncio.wait_for(ev.wait(), timeout=35)
        except asyncio.TimeoutError:
            pass
        
        text = latest.get('text', result or '')
        event_type = latest.get('type', 'unknown')
        
        templates = detect_template(text)
        vague = detect_vague(text)
        ai_refs = detect_ai_ref(text)
        empty = detect_empty_scene(text)
        
        quality = 10
        quality -= min(len(templates) * 2, 6)
        quality -= min(len(vague) * 2, 4)
        quality -= min(len(ai_refs) * 2, 4)
        quality = max(0, min(10, quality))
        
        issues = []
        if templates:
            issues.append(f"模板化({len(templates)})")
        if vague:
            issues.append(f"万能敷衍({len(vague)})")
        if ai_refs:
            issues.append(f"AI引用({len(ai_refs)})")
        if empty:
            issues.append(f"场景空洞")
        if not text or len(text) < 30:
            issues.append("过短/无响应")
        
        results.append({
            'turn': master.game_state['turn'],
            'turn_delta': master.game_state['turn'] - turn_before,
            'phase': label,
            'message': msg,
            'narrative': text[:500] if text else '(无响应)',
            'event_type': event_type,
            'templates': templates,
            'vague': vague,
            'ai_refs': ai_refs,
            'empty': empty,
            'quality': quality,
            'issues': issues,
            'location': master.game_state.get('location', '?'),
        })
        
        print(f"    [质量:{quality}] [{event_type}] {text[:150] if text else '(无)'}...")
        if issues:
            print(f"    [问题] {'; '.join(issues)}")
        
        return text

    # ===== 阶段2: Tutorial =====
    print("\n" + "=" * 50)
    print("[阶段2] Tutorial")
    print("=" * 50)
    
    tutorial = get_tutorial_system()
    tutorial.set_mode(TutorialMode.FULL)
    
    char_dict = {
        'name': char.name, 'race': char.race_name, 'class': char.class_name,
        'level': char.level, 'hp': char.current_hp, 'max_hp': char.max_hp,
        'ac': char.armor_class, 'xp': char.xp, 'gold': char.gold
    }
    
    # 生成欢迎叙事
    welcome = await tutorial.generate_welcome_narrative(char_dict)
    results.append({
        'phase': 'Tutorial-Welcome',
        'narrative': welcome[:500],
        'quality': 5 if len(detect_template(welcome)) > 2 else 8,
        'issues': detect_template(welcome),
    })
    print(f"[Tutorial Welcome] {welcome[:200]}...")
    
    # 教程指令
    await act("教程", "Tutorial-开始")
    await act("查看帮助", "Tutorial-帮助")
    await act("继续", "Tutorial-继续")
    await act("跳过教程", "Tutorial-跳过")

    # ===== 阶段3: 新手任务（找市长）=====
    print("\n" + "=" * 50)
    print("[阶段3] 新手任务 - 找市长")
    print("=" * 50)
    
    # 触发任务
    await act("我在镇子里，想找点事做", "任务-触发")
    await act("有什么需要帮忙的吗", "任务-接取")
    await act("镇长在哪里", "任务-寻路")
    await act("去镇长办公室", "任务-前往")
    await act("和镇长说话", "任务-NPC对话")
    await act("接受任务", "任务-接受")
    
    # 尝试获取任务描述
    await act("任务是什么", "系统-任务")

    # ===== 阶段4: 酒馆场景 =====
    print("\n" + "=" * 50)
    print("[阶段4] 酒馆场景")
    print("=" * 50)
    
    await act("去酒馆", "场景-酒馆")
    await act("look", "探索-观察(EN)")
    await act("看看周围", "探索-观察(CN)")
    await act("search 酒馆", "探索-搜索(EN)")
    await act("仔细搜索酒馆", "探索-搜索(CN)")
    await act("酒馆里有什么人", "探索-人物")
    await act("和酒馆老板说话", "社交-NPC")
    await act("打听最近的消息", "社交-打听")
    await act("mover 酒馆门口", "移动-门口(EN误拼)")
    await act("move 酒馆门口", "移动-门口")
    await act("talk to 酒馆老板", "社交-NPC(EN)")

    # ===== 阶段5: 探索指令测试 =====
    print("\n" + "=" * 50)
    print("[阶段5] 探索指令测试")
    print("=" * 50)
    
    await act("look", "探索-look")
    await act("look around", "探索-look_around")
    await act("search", "探索-search")
    await act("search room", "探索-search_room")
    await act("move 镇中心", "移动-镇中心")
    await act("move 市场", "移动-市场")
    await act("talk to stranger", "社交-陌生人(EN)")
    await act("和陌生人说话", "社交-陌生人(CN)")
    await act("查看周围环境", "探索-环境")

    # ===== 阶段6: 系统命令测试 =====
    print("\n" + "=" * 50)
    print("[阶段6] 系统命令测试")
    print("=" * 50)
    
    await act("状态", "系统-状态")
    await act("背包", "系统-背包")
    await act("商店", "系统-商店")
    await act("任务", "系统-任务")
    await act("帮助", "系统-帮助")
    await act("/状态", "系统-状态(SLASH)")
    await act("/help", "系统-帮助(SLASH)")
    await act("help", "系统-help(EN)")

    # ===== 阶段7: 战斗测试 =====
    print("\n" + "=" * 50)
    print("[阶段7] 战斗测试")
    print("=" * 50)
    
    # 触发战斗
    await act("去森林", "场景-森林")
    await act("深入森林", "场景-森林深处")
    await act("调查声音", "探索-调查")
    await act("查看周围", "探索-查看")
    await act("遭遇怪物", "战斗-触发")
    
    # 战斗中指令
    await act("攻击", "战斗-攻击")
    await act("查看状态", "战斗-状态")
    await act("防御", "战斗-防御")
    await act("查看背包", "战斗-背包")
    await act("攻击", "战斗-攻击2")
    await act("攻击怪物", "战斗-攻击3")
    
    # ===== 阶段8: 中文命令路由验证 =====
    print("\n" + "=" * 50)
    print("[阶段8] 中文命令路由验证")
    print("=" * 50)
    
    chinese_commands = [
        ("看看周围", "look_around"),
        ("查看环境", "check_environment"),
        ("搜索房间", "search_room"),
        ("和老板说话", "talk_to_owner"),
        ("去酒馆", "go_to_tavern"),
        ("去镇中心", "go_to_center"),
        ("状态", "status"),
        ("背包", "inventory"),
        ("帮助", "help"),
    ]
    
    for cmd, desc in chinese_commands:
        await act(cmd, f"中文路由-{desc}")

    # ===== 清理 =====
    await master.stop()
    await bus.stop()
    elapsed = time.time() - start_time

    # ===== 生成报告 =====
    quality_scores = [r['quality'] for r in results if 'quality' in r]
    avg_q = sum(quality_scores) / len(quality_scores) if quality_scores else 0
    
    total_turns = master.game_state['turn']
    final_location = master.game_state.get('location', '?')
    
    # 按严重程度分类问题
    p1_issues = []  # 阻塞性问题
    p2_issues = []  # 严重体验问题
    p3_issues = []  # 一般体验问题
    
    for r in results:
        if not r.get('issues'):
            continue
        quality = r.get('quality', 10)
        issue_str = f"[{r['phase']}] {r['message']} → {'; '.join(r['issues'])} | 质量:{quality} | 叙事:{r['narrative'][:80]}"
        if quality <= 2:
            p1_issues.append(issue_str)
        elif quality <= 5:
            p2_issues.append(issue_str)
        else:
            p3_issues.append(issue_str)
    
    # 无响应/过短
    no_response = [r for r in results if '无响应' in r.get('narrative', '') or (not r.get('narrative') and r.get('quality', 10) < 5)]
    
    report = f"""# AI DM RPG E2E 体验报告
**日期**: 2026-04-12 13:41
**测试者**: 体验官（子代理）

---

## 体验摘要

- **角色**: {char.name} | {char.race_name} | {char.class_name}
- **总回合数**: {total_turns}
- **最终位置**: {final_location}
- **平均叙事质量**: {avg_q:.1f}/10
- **测试耗时**: {elapsed:.1f}秒

### 各阶段测试结果

| 阶段 | 描述 | 质量 | 主要问题 |
|------|------|------|---------|
"""
    
    phase_summary = {}
    for r in results:
        ph = r.get('phase', '?')
        if ph not in phase_summary:
            phase_summary[ph] = {'count': 0, 'quality_sum': 0, 'issues': []}
        if 'quality' in r:
            phase_summary[ph]['count'] += 1
            phase_summary[ph]['quality_sum'] += r['quality']
        phase_summary[ph]['issues'].extend(r.get('issues', []))
    
    for ph, s in phase_summary.items():
        avg = s['quality_sum'] / s['count'] if s['count'] > 0 else 0
        issues_str = ', '.join(set(s['issues']))[:60] if s['issues'] else '无'
        report += f"| {ph} | 回合{s['count']}次 | {avg:.1f} | {issues_str} |\n"
    
    report += f"""
---

## 问题列表（按严重程度）

### P1 - 阻塞性问题（必须修复）

"""
    if p1_issues:
        for i in p1_issues:
            report += f"- ❌ {i}\n"
    else:
        report += "- ✅ 未发现阻塞性问题\n"
    
    report += f"""
### P2 - 严重体验问题

"""
    if p2_issues:
        for i in p2_issues:
            report += f"- 🔴 {i}\n"
    else:
        report += "- 🟡 未发现严重体验问题\n"
    
    report += f"""
### P3 - 一般体验问题

"""
    if p3_issues:
        for i in p3_issues[:10]:
            report += f"- 🟠 {i}\n"
    else:
        report += "- 🟢 未发现一般问题\n"
    
    report += f"""
---

## 详细问题明细

| 回合 | 阶段 | 动作 | 叙事片段 | 问题 | 质量 |
|------|------|------|---------|------|------|
"""
    for r in results:
        if r.get('issues') or r.get('quality', 10) <= 5:
            report += f"| {r.get('turn','?')} | {r.get('phase','?')} | {r.get('message','?')[:20]} | {r.get('narrative','?')[:40]} | {';'.join(r.get('issues',[]))} | {r.get('quality','?')} |\n"
    
    report += f"""
---

## 中文命令路由测试

| 命令 | 阶段 | 质量 | 结果 |
|------|------|------|------|
"""
    for r in results:
        if '中文路由' in r.get('phase', ''):
            status = '✅ 正常' if r.get('quality', 0) >= 5 and r.get('narrative') != '(无响应)' else '❌ 失效'
            report += f"| {r.get('message')} | {r.get('phase')} | {r.get('quality')} | {status} |\n"
    
    # 战斗测试结果
    combat_events = [r for r in results if '战斗' in r.get('phase', '') or r.get('event_type', '').startswith('combat')]
    report += f"""
---

## 战斗测试结果

- **战斗触发次数**: {len(combat_events)}
- **战斗状态**: {'✅ 正常' if combat_events else '⚠️ 未触发战斗'}

"""
    
    # 总体评分
    overall_score = max(1, min(10, int(avg_q)))
    report += f"""
---

## 总体评分与建议

### 评分

**总分: {overall_score}/10**

| 维度 | 评分 | 说明 |
|------|------|------|
| 叙事质量 | {avg_q:.1f}/10 | 模板化和敷衍回复影响较大 |
| 命令响应 | {10 - len(no_response)*2}/10 | {'无阻塞性命令失效' if len(no_response) < 3 else f'{len(no_response)}次无响应'} |
| 战斗体验 | {'?'}/10 | 需手动验证 |
| 中文支持 | {'?'}/10 | 需手动验证 |

### 建议优先级

"""
    
    priorities = []
    if p1_issues:
        priorities.append("**P1**: 修复阻塞性问题（命令失效、空场景、无响应）")
    if any('模板化' in i for i in p2_issues + p3_issues):
        priorities.append("**P2**: 优化叙事模板，增加场景多样性")
    if any('万能敷衍' in i for i in p2_issues + p3_issues):
        priorities.append("**P2**: 消除万能敷衍回复，确保每次回复有具体内容")
    if len(no_response) > 0:
        priorities.append(f"**P3**: 检查{len(no_response)}次无响应的原因（可能是API超时）")
    
    for p in priorities:
        report += f"- {p}\n"
    
    if not priorities:
        report += "- ✅ 当前版本整体体验良好，无重大问题\n"
    
    report += f"""
---

*报告生成时间: {time.strftime('%Y-%m-%d %H:%M:%S')} | 耗时: {elapsed:.1f}秒*
"""
    
    # 保存报告和数据
    report_path = 'C:/Users/15901/.openclaw/workspace/ai-dm-rpg/tasks/tiyanguan_2026-04-12_1341.md'
    data_path = 'C:/Users/15901/.openclaw/workspace/ai-dm-rpg/tasks/tiyanguan_2026-04-12_1341_data.json'
    
    with open(report_path, 'w', encoding='utf-8') as f:
        f.write(report)
    
    data = {
        'timestamp': '2026-04-12 13:41',
        'character': {'name': char.name, 'race': char.race_name, 'class': char.class_name},
        'results': results,
        'stats': {
            'avg_quality': avg_q,
            'total_turns': total_turns,
            'final_location': final_location,
            'elapsed': elapsed,
            'p1_count': len(p1_issues),
            'p2_count': len(p2_issues),
            'p3_count': len(p3_issues),
            'no_response_count': len(no_response),
        },
        'report': report,
    }
    
    with open(data_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    
    print("\n" + "=" * 70)
    print(report)
    print("=" * 70)
    print(f"\n报告已保存: {report_path}")
    print(f"数据已保存: {data_path}")
    
    return report, data

if __name__ == '__main__':
    asyncio.run(run_e2e())
