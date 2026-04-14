"""
AI DM RPG 体验官快速测试 2026-04-12 19:45
"""
import sys
import asyncio
import time
sys.path.insert(0, '.')
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

print("=" * 60, flush=True)
print("AI DM RPG 体验官快速测试 2026-04-12 19:45", flush=True)
print("=" * 60, flush=True)

from src import init_event_bus, init_game_master, EventType
from src.character_creator import get_character_creator
from src.tutorial_system import get_tutorial_system, TutorialMode

class Recorder:
    def __init__(self):
        self.records = []
        self.latest = {}
        self.ev = asyncio.Event()
    
    async def handle(self, event):
        self.latest['text'] = event.data.get('text', '')
        self.latest['type'] = event.type.value
        self.ev.set()

rec = Recorder()

async def act(master, bus, msg, label):
    rec.latest.clear()
    rec.ev.clear()
    print(f"\n>>> [{label}] {msg}", flush=True)
    try:
        result = await asyncio.wait_for(master.handle_player_message(msg), timeout=25)
    except asyncio.TimeoutError:
        result = "(超时)"
    except Exception as e:
        result = f"(异常: {e})"
    
    try:
        await asyncio.wait_for(rec.ev.wait(), timeout=20)
    except asyncio.TimeoutError:
        pass
    
    text = rec.latest.get('text', result or '')
    rtype = rec.latest.get('type', 'unknown')
    is_empty = not text or len(text.strip()) < 5
    preview = text[:120].replace('\n', ' ') if text else '(空)'
    print(f"    [{rtype}] {preview}...", flush=True)
    rec.records.append({'phase': label, 'msg': msg, 'text': text, 'rtype': rtype, 'empty': is_empty})
    return text

async def main():
    t0 = time.time()
    bus = await init_event_bus()
    master = await init_game_master()
    await master.initialize()
    
    await bus.subscribe(EventType.NARRATIVE_OUTPUT, rec.handle, 't')
    await bus.subscribe(EventType.COMBAT_START, rec.handle, 't_c')
    await bus.subscribe(EventType.COMBAT_END, rec.handle, 't_ce')
    
    creator = get_character_creator()
    char = creator.create_from_selection('冒险者', 'human', 'warrior')
    print(f"\n角色: {char.name} | {char.race_name} | {char.class_name}", flush=True)
    
    master.game_state['player_stats'] = {
        'hp': char.current_hp, 'max_hp': char.max_hp, 'ac': char.armor_class,
        'xp': char.xp, 'level': char.level, 'gold': char.gold,
        'inventory': char.inventory, 'name': char.name,
        'race': char.race_name, 'class': char.class_name,
    }
    master.game_state['turn'] = 0
    master.game_state['location'] = '绿叶村'
    master.game_state['active_npcs_per_scene'] = {}
    master.game_state['active_npcs'] = {}
    master.game_state['quest_stage'] = 'not_started'
    master.game_state['quest_active'] = False
    
    # 测试阶段
    print("\n--- Tutorial ---", flush=True)
    await act(master, bus, "教程", "Tutorial")
    
    print("\n--- 系统命令 ---", flush=True)
    await act(master, bus, "状态", "Status")
    await act(master, bus, "背包", "Inventory")
    await act(master, bus, "任务", "Quest")
    await act(master, bus, "帮助", "Help")
    await act(master, bus, "商店", "Shop")
    
    print("\n--- 场景探索 ---", flush=True)
    await act(master, bus, "探索绿叶村", "Explore-Village")
    await act(master, bus, "前往酒馆", "Move-Tavern")
    await act(master, bus, "酒馆里有什么", "Look-Tavern")
    await act(master, bus, "和酒馆老板说话", "Talk-Innkeeper")
    
    print("\n--- 战斗 ---", flush=True)
    await act(master, bus, "前往森林", "Move-Forest")
    await act(master, bus, "搜索周围", "Search")
    await act(master, bus, "攻击哥布林", "Attack-Goblin")
    await act(master, bus, "我防御", "Defend")
    await act(master, bus, "使用治疗药水", "Use-Potion")
    
    print("\n--- 更多场景 ---", flush=True)
    await act(master, bus, "查看四周", "Look-Around")
    await act(master, bus, "和老板聊聊天", "Chat-Innkeep")
    await act(master, bus, "询问任务", "Ask-Quest")
    await act(master, bus, "买一瓶治疗药水", "Buy-Potion")
    
    elapsed = time.time() - t0
    
    # 生成报告
    records = rec.records
    total = len(records)
    empty_count = sum(1 for r in records if r['empty'])
    
    p0 = []
    p1 = []
    for r in records:
        if r['empty']:
            p0.append(r)
    
    score = max(1, min(10, round((1 - empty_count/total) * 10))) if total > 0 else 5
    
    report = f"""# 体验官报告 - 20260412 19:45

## 综合评分：{score}/10

## 无响应率：{empty_count/total*100:.1f}% ({empty_count}/{total} 操作无响应)

## 测试耗时：{elapsed:.1f}秒

## P0 问题（阻塞性）
"""
    for i, r in enumerate(p0, 1):
        report += f"""
### P0-{i}：{r['phase']}
**操作**：{r['msg']}
**实际输出**：{r['text'][:200] if r['text'] else '(空)'}
**预期输出**：有效的游戏响应
"""
    
    report += """
## P1 问题（体验受损）
_无详细 P1 问题记录_

## 详细问题记录
"""
    for i, r in enumerate(records, 1):
        status = "✅" if not r['empty'] else "❌"
        preview = r['text'][:80].replace('\n', ' ') if r['text'] else '(空)'
        report += f"{status} [{r['phase']}] {r['msg']} -> {preview}...\n"
    
    report_path = r'C:\Users\15901\.openclaw\workspace-ai-dm-rpg\tasks\tiyanguan_report_20260412_1945.md'
    with open(report_path, 'w', encoding='utf-8') as f:
        f.write(report)
    
    print(f"\n\n报告已保存: {report_path}", flush=True)
    print(f"\n综合评分: {score}/10 | 无响应率: {empty_count/total*100:.1f}% | 耗时: {elapsed:.1f}s", flush=True)
    print("\n=== 报告内容 ===", flush=True)
    print(report, flush=True)
    
    await master.stop()
    await bus.stop()

if __name__ == "__main__":
    asyncio.run(main())
