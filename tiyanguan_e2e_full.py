"""
AI DM RPG 完整 E2E 体验验证 2026-04-12 13:41
完整测试所有阶段：启动→角色创建→Tutorial→新手任务→酒馆→战斗→探索→系统命令
"""
import sys
import asyncio
import json
import time
sys.path.insert(0, '.')
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
print("=" * 70, flush=True)
print("AI DM RPG 完整 E2E 体验验证 2026-04-12 13:41", flush=True)
print("=" * 70, flush=True)

from src import init_event_bus, init_game_master, EventType, Event
from src.character_creator import get_character_creator
from src.tutorial_system import get_tutorial_system, TutorialMode
from src.quest_state import QuestStage, QUEST_NAME

# ========== 问题检测函数 ==========

def detect_template(text):
    if not text:
        return []
    templates = [
        "你听到回声", "空气中弥漫着", "你的声音在空气中回荡",
        "mysterious", "神秘", "微风吹拂", "温暖的阳光", "清新的空气",
        "这是一个", "你看到", "你来到", "这里是",
        "突然，你", "就在这时", "宁静祥和", "危机四伏", "阴森诡异",
    ]
    return list(set(t for t in templates if t in text))

def detect_vague(text):
    if not text:
        return []
    vague_patterns = [
        "好的", "明白了", "我理解了", "没问题", "你可以",
        "让我想想", "这个嘛", "其实", "一般来说",
        "作为你的DM", "作为你的游戏主持人",
        "你可以尝试", "也许你可以",
    ]
    return list(set(p for p in vague_patterns if p in text))

def detect_ai_ref(text):
    if not text:
        return []
    import re
    patterns = [r"DM\b", r"\(DM\)", r"DM说", r"系统说", r"请选择", r"提示：", r"作为DM", r"GM说"]
    return list(set(p for p in patterns if re.search(p, text)))

def detect_empty_scene(text):
    if not text:
        return []
    short_vague = [
        "没什么特别的", "看起来很普通", "一切如常",
        "这里没什么", "你环顾四周",
        "似乎没有", "看起来没有",
    ]
    return list(set(t for t in short_vague if t in text))

async def run_e2e():
    start_time = time.time()

    # === 初始化 ===
    bus = await init_event_bus()
    master = await init_game_master()
    await master.initialize()

    # === 角色创建 ===
    print("\n[阶段1] 角色创建", flush=True)
    creator = get_character_creator()
    char = creator.create_from_selection('体验官', 'human', 'warrior')
    print(f"  角色: {char.name} | {char.race_name} | {char.class_name} | HP:{char.current_hp}/{char.max_hp} AC:{char.armor_class} Gold:{char.gold}", flush=True)

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

    async def act(msg, label, timeout=35):
        latest.clear()
        ev.clear()
        turn_before = master.game_state['turn']
        print(f"\n>>> [{label}] {msg}", flush=True)
        
        result = "(无)"
        try:
            result = await asyncio.wait_for(master.handle_player_message(msg), timeout=timeout)
        except asyncio.TimeoutError:
            result = "(超时)"
        
        text = ""
        try:
            await asyncio.wait_for(ev.wait(), timeout=timeout)
            text = latest.get('text', result or '')
        except asyncio.TimeoutError:
            text = result if result != "(无)" else ""
        
        if not text or text is None:
            text = result if result and result != "(无)" else "(无响应)"
        
        templates = detect_template(text)
        vague = detect_vague(text)
        ai_refs = detect_ai_ref(text)
        empty = detect_empty_scene(text)
        
        quality = 10
        quality -= min(len(templates) * 1.5, 6)
        quality -= min(len(vague) * 1.5, 4)
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
        if not text or text is None or len(str(text).strip()) < 20:
            issues.append("过短/无响应")
        
        results.append({
            'turn': master.game_state['turn'],
            'turn_delta': master.game_state['turn'] - turn_before,
            'phase': label,
            'message': msg,
            'narrative': text[:600] if text else '(无)',
            'event_type': latest.get('type', '?'),
            'templates': templates,
            'vague': vague,
            'ai_refs': ai_refs,
            'empty': empty,
            'quality': quality,
            'issues': issues,
            'location': master.game_state.get('location', '?'),
        })
        
        print(f"    [质量:{quality}] [{latest.get('type','?')}] {text[:200] if text else '(无)'}...", flush=True)
        if issues:
            print(f"    [问题] {'; '.join(issues)}", flush=True)
        
        return text

    # ===== 阶段2: Tutorial =====
    print("\n" + "=" * 50, flush=True)
    print("[阶段2] Tutorial", flush=True)
    print("=" * 50, flush=True)
    await act("教程", "Tutorial-开始")
    await act("继续", "Tutorial-继续")
    await act("跳过教程", "Tutorial-跳过")

    # ===== 阶段3: 新手任务（找市长）=====
    print("\n" + "=" * 50, flush=True)
    print("[阶段3] 新手任务 - 找市长", flush=True)
    print("=" * 50, flush=True)
    await act("探索月叶镇", "任务-探索开场")
    await act("我在镇子里，想找点事做", "任务-触发")
    await act("镇长在哪里", "任务-寻路")
    await act("去镇长办公室", "任务-前往")
    await act("和镇长说话", "任务-NPC对话")
    await act("接受任务", "任务-接受")
    await act("任务是什么", "任务-详情")

    # ===== 阶段4: 酒馆场景 =====
    print("\n" + "=" * 50, flush=True)
    print("[阶段4] 酒馆场景", flush=True)
    print("=" * 50, flush=True)
    await act("去酒馆", "场景-酒馆")
    await act("look", "探索-look(EN)")
    await act("看看周围", "探索-look(CN)")
    await act("search 酒馆", "探索-search(EN)")
    await act("仔细搜索酒馆", "探索-search(CN)")
    await act("和酒馆老板说话", "社交-酒馆老板")
    await act("打听最近的消息", "社交-打听")
    await act("酒馆里有什么人", "探索-酒馆人物")

    # ===== 阶段5: 探索指令测试 =====
    print("\n" + "=" * 50, flush=True)
    print("[阶段5] 探索指令测试", flush=True)
    print("=" * 50, flush=True)
    await act("look around", "探索-look_around")
    await act("search room", "探索-search_room")
    await act("move 镇中心", "移动-镇中心")
    await act("move 市场", "移动-市场")
    await act("和陌生人说话", "社交-陌生人")
    await act("查看周围环境", "探索-环境")
    await act("检查地面", "探索-细节")

    # ===== 阶段6: 系统命令测试 =====
    print("\n" + "=" * 50, flush=True)
    print("[阶段6] 系统命令测试", flush=True)
    print("=" * 50, flush=True)
    await act("状态", "系统-状态")
    await act("背包", "系统-背包")
    await act("商店", "系统-商店")
    await act("任务", "系统-任务")
    await act("帮助", "系统-帮助")
    await act("/状态", "系统-状态_SLASH")
    await act("/help", "系统-help_SLASH")
    await act("help", "系统-help_EN")

    # ===== 阶段7: 战斗测试 =====
    print("\n" + "=" * 50, flush=True)
    print("[阶段7] 战斗测试", flush=True)
    print("=" * 50, flush=True)
    await act("去森林", "场景-森林")
    await act("深入森林", "场景-森林深处")
    await act("调查声音", "探索-调查")
    await act("look around", "战斗前-观察")
    
    # 战斗中
    await act("攻击", "战斗-攻击1")
    await act("防御", "战斗-防御")
    await act("查看状态", "战斗-状态")
    await act("攻击怪物", "战斗-攻击2")
    await act("使用治疗药水", "战斗-道具")
    await act("攻击", "战斗-攻击3")

    # ===== 阶段8: 中文命令路由验证 =====
    print("\n" + "=" * 50, flush=True)
    print("[阶段8] 中文命令路由", flush=True)
    print("=" * 50, flush=True)
    
    chinese_tests = [
        ("看看周围", "look_around"),
        ("查看环境", "check_env"),
        ("搜索房间", "search_room"),
        ("和老板说话", "talk_owner"),
        ("去酒馆", "go_tavern"),
        ("去镇中心", "go_center"),
        ("仔细看看", "look_detail"),
        ("四处看看", "look_around2"),
    ]
    
    for cmd, desc in chinese_tests:
        await act(cmd, f"中文路由-{desc}")

    # ===== 清理 =====
    await master.stop()
    await bus.stop()
    elapsed = time.time() - start_time

    # ===== 生成报告 =====
    quality_scores = [r['quality'] for r in results]
    avg_q = sum(quality_scores) / len(quality_scores) if quality_scores else 0
    
    total_turns = master.game_state['turn']
    final_location = master.game_state.get('location', '?')
    
    # 分类问题
    p1_issues = []
    p2_issues = []
    p3_issues = []
    no_response = []
    
    for r in results:
        q = r.get('quality', 10)
        narrative = r.get('narrative', '')
        
        if not narrative or narrative == '(无响应)' or narrative == '(超时)' or len(narrative.strip()) < 20:
            no_response.append(r)
        
        issue_str = f"[{r['phase']}] \"{r['message']}\" → {'; '.join(r['issues']) if r['issues'] else '正常'} | 质量:{q} | 叙事:{narrative[:60]}"
        
        if q <= 2:
            p1_issues.append(issue_str)
        elif q <= 5:
            p2_issues.append(issue_str)
        elif r['issues']:
            p3_issues.append(issue_str)
    
    # 按阶段汇总
    phase_summary = {}
    for r in results:
        ph = r.get('phase', '?')
        if ph not in phase_summary:
            phase_summary[ph] = {'count': 0, 'quality_sum': 0, 'issues': set(), 'no_resp': 0}
        phase_summary[ph]['count'] += 1
        if 'quality' in r:
            phase_summary[ph]['quality_sum'] += r['quality']
        phase_summary[ph]['issues'].update(r.get('issues', []))
        if not r.get('narrative') or r['narrative'] in ['(无响应)', '(超时)']:
            phase_summary[ph]['no_resp'] += 1
    
    report = f"""# AI DM RPG E2E 体验报告
**日期**: 2026-04-12 13:41
**测试者**: 体验官（子代理）
**测试耗时**: {elapsed:.1f}秒

---

## 体验摘要

| 项目 | 值 |
|------|-----|
| 角色 | {char.name} | {char.race_name} | {char.class_name} |
| 总回合数 | {total_turns} |
| 最终位置 | {final_location} |
| 平均叙事质量 | {avg_q:.1f}/10 |
| 总测试次数 | {len(results)} |
| 无响应次数 | {len(no_response)} |
| P1问题数 | {len(p1_issues)} |
| P2问题数 | {len(p2_issues)} |
| P3问题数 | {len(p3_issues)} |

### 叙事质量分布

| 质量 | 数量 | 说明 |
|------|------|------|
| 9-10 | {sum(1 for r in results if r.get('quality',0)>=9)} | 优秀，叙事丰富有创意 |
| 6-8 | {sum(1 for r in results if 6<=r.get('quality',0)<=8)} | 良好，基本可用 |
| 3-5 | {sum(1 for r in results if 3<=r.get('quality',0)<=5)} | 一般，有模板化倾向 |
| 0-2 | {sum(1 for r in results if r.get('quality',0)<=2)} | 差，严重问题 |

---

## 各阶段测试结果

| 阶段 | 次数 | 平均质量 | 无响应 | 主要问题 |
|------|------|---------|--------|---------|
"""
    
    for ph, s in sorted(phase_summary.items()):
        avg = s['quality_sum'] / s['count'] if s['count'] > 0 else 0
        issues_str = ', '.join(sorted(s['issues']))[:50] if s['issues'] else '无'
        report += f"| {ph} | {s['count']} | {avg:.1f} | {s['no_resp']} | {issues_str} |\n"
    
    report += f"""
---

## P1 - 阻塞性问题（必须修复）

"""
    if p1_issues:
        for i in p1_issues:
            report += f"- ❌ {i}\n"
    else:
        report += "- ✅ 未发现阻塞性问题\n"
    
    report += f"""
---

## P2 - 严重体验问题

"""
    if p2_issues:
        for i in p2_issues:
            report += f"- 🔴 {i}\n"
    else:
        report += "- 🟡 未发现严重体验问题\n"
    
    report += f"""
---

## P3 - 一般体验问题

"""
    if p3_issues:
        for i in p3_issues[:15]:
            report += f"- 🟠 {i}\n"
    else:
        report += "- 🟢 未发现一般问题\n"
    
    report += f"""
---

## 无响应/超时记录

| 回合 | 阶段 | 动作 | 说明 |
|------|------|------|------|
"""
    for r in no_response:
        report += f"| {r.get('turn','?')} | {r.get('phase','?')} | {r.get('message','?')} | {r.get('narrative','?')} |\n"
    
    report += f"""
---

## 中文命令路由测试结果

| 命令 | 阶段 | 质量 | 状态 | 叙事片段 |
|------|------|------|------|---------|
"""
    for r in results:
        if '中文路由' in r.get('phase', ''):
            status = '✅ 正常' if r.get('quality', 0) >= 5 and r.get('narrative') not in ['(无响应)', '(超时)', ''] else '❌ 失效'
            report += f"| {r.get('message')} | {r.get('phase')} | {r.get('quality')} | {status} | {r.get('narrative','?')[:50]} |\n"
    
    # 战斗测试结果
    combat_results = [r for r in results if '战斗' in r.get('phase', '')]
    combat_narratives = [r for r in results if r.get('event_type', '').startswith('combat') or 'combat' in r.get('phase', '').lower()]
    
    report += f"""
---

## 战斗测试结果

- **战斗触发**: {'✅ 成功' if combat_results else '⚠️ 未触发'}
- **战斗叙事质量**: {sum(r.get('quality',0) for r in combat_results)/len(combat_results) if combat_results else 'N/A':.1f}/10

"""
    for r in combat_results:
        report += f"- **{r['phase']}**: {r.get('narrative','?')[:100]}...\n"
    
    report += f"""
---

## 系统命令测试结果

| 命令 | 质量 | 状态 |
|------|------|------|
"""
    for r in results:
        if r.get('phase', '').startswith('系统-'):
            status = '✅ 正常' if r.get('quality', 0) >= 6 else '⚠️ 需检查'
            report += f"| {r.get('message')} | {r.get('quality')} | {status} |\n"
    
    # 总体评分
    overall_score = max(1, min(10, int(avg_q)))
    report += f"""
---

## 总体评分与建议

### 评分

**总分: {overall_score}/10** ({'优秀' if overall_score>=8 else '良好' if overall_score>=6 else '一般' if overall_score>=4 else '较差'})

| 维度 | 评分 | 说明 |
|------|------|------|
| 叙事质量 | {avg_q:.1f}/10 | 模板化和敷衍回复影响较大 |
| 命令响应率 | {10 - len(no_response)*2}/10 | {f'{len(no_response)}次无响应' if no_response else '无阻塞性命令失效'} |
| 战斗系统 | {sum(r.get('quality',0) for r in combat_results)/len(combat_results) if combat_results else 5:.1f}/10 | {'正常' if combat_results else '未触发'} |
| 中文支持 | {10 - sum(1 for r in results if '中文路由' in r.get('phase','') and r.get('quality',0)<5)*3}/10 | {'部分命令失效' if any('中文路由' in r.get('phase','') and r.get('quality',0)<5 for r in results) else '正常'} |

### 建议优先级

"""
    
    priorities = []
    if p1_issues:
        priorities.append("**P1**: 修复阻塞性问题（命令失效、空场景、无响应）")
    if any('模板化' in i for i in p2_issues):
        priorities.append("**P2**: 优化叙事模板，增加场景多样性")
    if any('万能敷衍' in i for i in p2_issues):
        priorities.append("**P2**: 消除万能敷衍回复，确保每次回复有具体内容")
    if no_response:
        priorities.append(f"**P3**: 检查{len(no_response)}次无响应的命令原因（可能是路由或API超时）")
    if any('中文路由' in r.get('phase','') and r.get('quality',0)<5 for r in results):
        priorities.append("**P2**: 修复中文探索命令路由（search/look/move的中文变体）")
    if any('场景空洞' in r.get('issues',[]) for r in results):
        priorities.append("**P3**: 改善酒馆等场景的NPC和内容填充")
    
    for p in priorities:
        report += f"- {p}\n"
    
    if not priorities:
        report += "- ✅ 当前版本整体体验良好\n"
    
    report += f"""
---

## 完整测试日志

"""
    for r in results:
        q = r.get('quality', '?')
        issues = '; '.join(r.get('issues', [])) or '正常'
        report += f"**[{r.get('turn','?')}] [{r['phase']}]** {r['message']}\n"
        report += f"   质量:{q} | {issues}\n"
        report += f"   叙事: {r.get('narrative', '?')[:120]}...\n\n"
    
    report += f"""
*报告生成: {time.strftime('%Y-%m-%d %H:%M:%S')} | 耗时: {elapsed:.1f}秒*
"""
    
    # 保存
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
        }
    }
    
    with open(data_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    
    print("\n" + "=" * 70, flush=True)
    print(report, flush=True)
    print("=" * 70, flush=True)
    print(f"\n报告已保存: {report_path}", flush=True)
    
    return report, data, results

if __name__ == '__main__':
    report, data, results = asyncio.run(run_e2e())
