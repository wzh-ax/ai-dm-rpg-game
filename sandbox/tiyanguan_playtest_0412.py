"""
AI DM RPG 体验官完整测试 2026-04-12 19:30
覆盖：角色创建、Tutorial、探索、NPC对话、战斗、系统命令
"""
import sys
import asyncio
import json
import time
sys.path.insert(0, '.')
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

print("=" * 70, flush=True)
print("AI DM RPG 体验官完整测试 2026-04-12 19:30", flush=True)
print("=" * 70, flush=True)

from src import init_event_bus, init_game_master, EventType, Event
from src.character_creator import get_character_creator
from src.tutorial_system import get_tutorial_system, TutorialMode

# ===== 记录结构 =====
class TestRecorder:
    def __init__(self):
        self.records = []  # {'phase', 'message', 'narrative', 'type', 'success', 'issue'}
        self.stats = {'total': 0, 'no_response': 0, 'issues': []}
        self.latest_text = ''
        self.ev = asyncio.Event()
    
    def record(self, phase, message, narrative, resp_type, success=True, issue=None):
        self.records.append({
            'phase': phase, 'message': message, 'narrative': narrative,
            'type': resp_type, 'success': success, 'issue': issue
        })
        self.stats['total'] += 1
        if not success or not narrative:
            self.stats['no_response'] += 1
        if issue:
            self.stats['issues'].append(issue)

recorder = TestRecorder()

async def main():
    start_time = time.time()
    
    # === 初始化 ===
    bus = await init_event_bus()
    master = await init_game_master()
    await master.initialize()
    
    # === 角色创建 ===
    print("\n[阶段1] 角色创建", flush=True)
    creator = get_character_creator()
    char = creator.create_from_selection('冒险者', 'human', 'warrior')
    print(f"  角色: {char.name} | {char.race_name} | {char.class_name} | HP:{char.current_hp}/{char.max_hp} AC:{char.armor_class} Gold:{char.gold}", flush=True)
    
    master.game_state['player_stats'] = {
        'hp': char.current_hp, 'max_hp': char.max_hp,
        'ac': char.armor_class, 'xp': char.xp,
        'level': char.level, 'gold': char.gold,
        'inventory': char.inventory,
        'name': char.name, 'race': char.race_name, 'class': char.class_name,
    }
    master.game_state['turn'] = 0
    master.game_state['location'] = '绿叶村'
    master.game_state['active_npcs_per_scene'] = {}
    master.game_state['active_npcs'] = {}
    master.game_state['quest_stage'] = 'not_started'
    master.game_state['quest_active'] = False
    
    # 事件处理
    latest = {}
    
    async def handler(event):
        latest['text'] = event.data.get('text', '')
        latest['type'] = event.type.value
        recorder.ev.set()
    
    await bus.subscribe(EventType.NARRATIVE_OUTPUT, handler, 'test')
    await bus.subscribe(EventType.COMBAT_START, handler, 'test_combat')
    await bus.subscribe(EventType.COMBAT_END, handler, 'test_combat_end')
    
    async def act(msg, label, expected_type='narrative'):
        """执行一个操作并记录结果"""
        latest.clear()
        recorder.ev.clear()
        print(f"\n>>> [{label}] {msg}", flush=True)
        try:
            result = await asyncio.wait_for(master.handle_player_message(msg), timeout=40)
        except asyncio.TimeoutError:
            result = "(超时)"
            recorder.record(label, msg, '', 'timeout', success=False,
                          issue=f'操作超时: {msg}')
        except Exception as e:
            result = f"(异常: {e})"
            recorder.record(label, msg, '', 'exception', success=False,
                          issue=f'异常: {msg} -> {e}')
        
        try:
            await asyncio.wait_for(recorder.ev.wait(), timeout=35)
        except asyncio.TimeoutError:
            pass
        
        text = latest.get('text', result or '')
        resp_type = latest.get('type', 'unknown')
        
        # 判断是否无响应
        is_empty = not text or len(text.strip()) < 5
        has_issue = False
        
        # 检查常见问题模式
        if '毫无反应' in text or '没有反应' in text or '什么也没发生' in text:
            has_issue = True
        
        # 输出摘要
        preview = text[:150].replace('\n', ' ') if text else '(空)'
        print(f"    [{resp_type}] {preview}...", flush=True)
        
        recorder.record(label, msg, text, resp_type, success=not is_empty and not has_issue,
                       issue=f'无响应' if is_empty else (f'异常模式: {text[:100]}' if has_issue else None))
        return text
    
    # === Tutorial 阶段 ===
    print("\n[阶段2] Tutorial", flush=True)
    await act("教程", "Tutorial")
    
    # === 系统命令测试 ===
    print("\n[阶段3] 系统命令", flush=True)
    await act("状态", "Status-CMD")
    await act("背包", "Inventory-CMD")
    await act("任务", "Quest-CMD")
    await act("帮助", "Help-CMD")
    await act("商店", "Shop-CMD")
    
    # === 探索场景 ===
    print("\n[阶段4] 场景探索", flush=True)
    await act("探索绿叶村", "Explore-Village")
    await act("前往酒馆", "Move-Tavern")
    await act("酒馆里有什么", "Look-Tavern")
    await act("和酒馆老板说话", "Talk-Innkeeper")
    await act("和酒馆里的人聊天", "Talk-Crowd")
    await act("离开酒馆", "Leave-Tavern")
    await act("前往广场", "Move-Plaza")
    await act("广场上有什么", "Look-Plaza")
    await act("和市场商人交谈", "Talk-Merchant")
    await act("探索森林", "Move-Forest")
    await act("深入森林", "Deep-Forest")
    await act("搜索周围", "Search-Forest")
    
    # === 战斗测试 ===
    print("\n[阶段5] 战斗测试", flush=True)
    await act("攻击哥布林", "Attack-Goblin")
    await act("我攻击狼人", "Attack-Werewolf")
    await act("我防御", "Defend")
    await act("使用治疗药水", "Use-Potion")
    await act("我使用治疗药水", "Use-Potion-Full")
    
    # === 更多探索 ===
    print("\n[阶段6] 更多探索", flush=True)
    await act("查看四周", "Look-Around")
    await act("look", "Look-EN")
    await act("search", "Search-EN")
    await act("我去酒馆", "Go-Tavern")
    await act("和老板聊聊天", "Chat-Innkeeper")
    await act("询问任务", "Ask-Quest")
    await act("购买物品", "Buy-Items")
    await act("买一瓶治疗药水", "Buy-Potion")
    
    # === 边缘情况测试 ===
    print("\n[阶段7] 边缘情况", flush=True)
    await act("喝醉了", "Edge-Drunk")
    await act("突然逃跑", "Edge-Run")
    await act("唱歌", "Edge-Sing")
    await act("在地上挖洞", "Edge-Dig")
    await act("抚摸路边的猫", "Edge-PetCat")
    
    elapsed = time.time() - start_time
    
    # === 生成报告 ===
    print("\n" + "=" * 70, flush=True)
    print("测试完成，生成报告...", flush=True)
    
    report = generate_report(recorder, elapsed)
    
    # 保存报告
    report_path = r'C:\Users\15901\.openclaw\workspace-ai-dm-rpg\tasks\tiyanguan_report_20260412_1930.md'
    with open(report_path, 'w', encoding='utf-8') as f:
        f.write(report)
    print(f"\n报告已保存: {report_path}", flush=True)
    
    # 打印报告摘要
    print("\n" + "=" * 70, flush=True)
    print("报告摘要:", flush=True)
    print(report[:2000], flush=True)
    
    await master.stop()
    await bus.stop()

def generate_report(recorder, elapsed):
    records = recorder.records
    stats = recorder.stats
    
    total = stats['total']
    no_resp = sum(1 for r in records if not r['success'] or not r['narrative'] or len(r['narrative'].strip()) < 5)
    no_resp_rate = f"{no_resp/total*100:.1f}%" if total > 0 else "0%"
    
    # 分类问题
    p0_issues = []
    p1_issues = []
    
    for rec in records:
        if not rec['success'] or (rec['narrative'] and len(rec['narrative'].strip()) < 5):
            issue_text = rec.get('issue') or '无有效响应'
            p0_issues.append({
                'phase': rec['phase'],
                'message': rec['message'],
                'narrative': rec['narrative'],
                'issue': issue_text
            })
        elif rec.get('issue') and '异常模式' in rec['issue']:
            p1_issues.append({
                'phase': rec['phase'],
                'message': rec['message'],
                'narrative': rec['narrative'],
                'issue': rec['issue']
            })
    
    # 综合评分 (粗略估计)
    if total == 0:
        score = 10
    else:
        # 基于无响应率和问题数量
        resp_rate = 1 - no_resp/total
        score = round(resp_rate * 10 * 0.7 + 3)  # 基础分3，最高10
        score = min(10, max(1, score))
    
    report_lines = [
        "# 体验官报告 - 20260412 19:30",
        "",
        f"## 综合评分：{score}/10",
        "",
        f"## 无响应率：{no_resp_rate} ({no_resp}/{total} 操作无有效响应)",
        "",
        f"## 测试耗时：{elapsed:.1f}秒",
        "",
        "## P0 问题（阻塞性）",
        "",
    ]
    
    if p0_issues:
        for i, issue in enumerate(p0_issues, 1):
            report_lines.append(f"### P0-{i}：{issue['phase']}")
            report_lines.append(f"**操作**：{issue['message']}")
            report_lines.append(f"**实际输出**：{issue['narrative'][:200] if issue['narrative'] else '(空)'}")
            report_lines.append(f"**预期输出**：有效的游戏响应")
            report_lines.append(f"**问题**：{issue['issue']}")
            report_lines.append("")
    else:
        report_lines.append("_无 P0 问题_")
        report_lines.append("")
    
    report_lines.extend([
        "## P1 问题（体验受损）",
        "",
    ])
    
    if p1_issues:
        for i, issue in enumerate(p1_issues, 1):
            report_lines.append(f"### P1-{i}：{issue['phase']}")
            report_lines.append(f"**操作**：{issue['message']}")
            report_lines.append(f"**实际输出**：{issue['narrative'][:200] if issue['narrative'] else '(空)'}")
            report_lines.append(f"**预期输出**：正常的游戏响应")
            report_lines.append(f"**问题**：{issue['issue']}")
            report_lines.append("")
    else:
        report_lines.append("_无 P1 问题_")
        report_lines.append("")
    
    report_lines.extend([
        "## 详细问题记录",
        "",
    ])
    
    all_issues = p0_issues + p1_issues
    if all_issues:
        for i, rec in enumerate(all_issues, 1):
            report_lines.append(f"### 问题{len(p0_issues)+i}：{rec['phase']} - {rec['message']}")
            report_lines.append(f"**操作**：{rec['message']}")
            report_lines.append(f"**实际输出**：{rec['narrative'][:300] if rec['narrative'] else '(空)'}")
            report_lines.append(f"**预期输出**：有效的游戏响应")
            report_lines.append("")
    else:
        report_lines.append("_无详细问题记录_")
        report_lines.append("")
    
    report_lines.extend([
        "## 操作记录摘要",
        "",
    ])
    
    for rec in records:
        preview = rec['narrative'][:100].replace('\n', ' ') if rec['narrative'] else '(空)'
        status = "✅" if rec['success'] and rec['narrative'] and len(rec['narrative'].strip()) >= 5 else "❌"
        report_lines.append(f"{status} [{rec['phase']}] {rec['message']} -> {preview}...")
    
    return '\n'.join(report_lines)

if __name__ == "__main__":
    asyncio.run(main())
