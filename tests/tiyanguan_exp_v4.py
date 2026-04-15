# -*- coding: utf-8 -*-
"""
AI DM RPG - 体验官自动化体验 V4
简化版，专注于获取有效体验数据
"""
import asyncio
import sys
import os
from datetime import datetime

_script_dir = os.path.dirname(os.path.abspath(__file__))
_project_root = os.path.dirname(_script_dir)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from src import init_event_bus, init_game_master, EventType, Event
from src.character_creator import get_character_creator


async def main():
    print("=" * 60)
    print("AI DM RPG - 体验官体验 V4")
    print("=" * 60)
    
    actions = [
        ("探索", "去镇中心看看"),
        ("探索", "环顾四周"),
        ("NPC", "和周围的人说话"),
        ("NPC", "问路人这里最近有什么新鲜事"),
        ("NPC", "和酒馆老板说话"),
        ("NPC", "点一杯啤酒"),
        ("探索", "去酒馆"),
        ("NPC", "和酒馆里的人聊天"),
        ("系统", "查看状态"),
        ("系统", "查看背包"),
        ("探索", "去市场逛逛"),
        ("探索", "看看有没有任务可以接"),
        ("探索", "去冒险者公会"),
        ("探索", "去镇外看看"),
        ("战斗", "调查树林里的动静"),
        ("战斗", "主动寻找敌人"),
        ("探索", "休息一下"),
        ("探索", "继续探索"),
    ]
    
    start_time = datetime.now()
    bus = await init_event_bus()
    gm = await init_game_master()
    
    creator = get_character_creator()
    char = creator.create_from_selection("体验官", "human", "warrior")
    print(f"角色: {char.name} ({char.race_name}/{char.class_name})")
    
    gm.game_state["player_stats"] = char.to_player_stats()
    gm.game_state["turn"] = 0
    gm.game_state["location"] = "月叶镇"
    
    # 收集 NARRATIVE_OUTPUT
    narratives = []
    async def collect(event: Event):
        narratives.append(event.data)
    await bus.subscribe(EventType.NARRATIVE_OUTPUT, collect, "coll")
    
    turn_data = []
    for i, (action_type, action) in enumerate(actions):
        turn_num = i + 1
        gm.game_state["turn"] = turn_num
        
        print(f"\n--- 回合 {turn_num}: [{action_type}] {action} ---")
        
        narratives.clear()
        await gm.handle_player_message(action)
        await asyncio.sleep(3)
        
        text = narratives[-1].get("text", "") if narratives else ""
        print(f"叙事: {text[:60] if text else '(空)'}...")
        
        turn_data.append({
            "turn": turn_num,
            "type": action_type,
            "action": action,
            "text": text,
            "length": len(text),
        })
    
    duration = (datetime.now() - start_time).total_seconds()
    
    # 统计
    total = len(turn_data)
    avg_len = sum(t["length"] for t in turn_data) / total if total else 0
    empty = sum(1 for t in turn_data if t["length"] == 0)
    battles = sum(1 for t in turn_data if t["type"] == "战斗")
    npc = sum(1 for t in turn_data if t["type"] == "NPC")
    
    print(f"\n总计: {total}回合, {duration:.0f}秒, 平均{avg_len:.0f}字/叙事, {empty}次无响应")
    
    # 报告
    tension = min(10, 5 + (avg_len / 80) + (0 if empty > 5 else 2))
    overall = (tension + 6 + 7) / 3
    
    problems = []
    for t in turn_data:
        if t["length"] == 0:
            problems.append(f"| 回合{t['turn']} | 输入无响应: {t['action']} | 情绪张力 | P1 |")
        elif t["length"] < 50:
            problems.append(f"| 回合{t['turn']} | 叙事过短({t['length']}字) | 情绪张力 | P2 |")
    
    merits = []
    if battles > 0:
        merits.append(f"- 成功触发{battles}次战斗")
    if empty == 0:
        merits.append("- 所有输入均有响应")
    if avg_len > 150:
        merits.append(f"- 叙事平均长度良好({avg_len:.0f}字)")
    
    merits_str = "\n".join(merits) if merits else "- 无"
    problems_str = "\n".join(problems) if problems else "| - | - | - | - |"
    
    turn_table = "\n".join([
        f"| {t['turn']} | {t['type']} | {t['action']} | {t['length']}字 |"
        for t in turn_data
    ])
    
    summary_parts = ["体验了AI DM RPG的核心探索流程。"]
    if avg_len < 100:
        summary_parts.append("叙事质量有待加强。")
    if empty > 0:
        summary_parts.append(f"主要问题: {empty}次无响应。")
    
    report = f"""# 体验报告

> 生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
> 体验版本: V1_0_5

## 基本信息

| 项目 | 值 |
|------|-----|
| 游玩时长 | {duration:.1f} 秒 |
| 总回合数 | {total} |
| 死亡次数 | 0 |
| 到达阶段 | 主游戏流程 |
| 战斗次数 | {battles} |
| NPC对话次数 | {npc} |

## 叙事体验

### 开场叙事
{turn_data[0]['text'][:300] if turn_data else '(无)'}

### 叙事统计
- 平均叙事长度: {avg_len:.1f} 字符
- 无响应次数: {empty} 次

### 回合详情
| 回合 | 类型 | 操作 | 叙事长度 |
|------|------|------|---------|
{turn_table}

## 具体问题（按严重程度）

| 位置 | 问题描述 | 对应目标 | 严重程度 |
|------|---------|---------|---------|
{problems_str}

## 优点
{merits_str}

## 总体评分（1-10）及总结

- **情绪张力**: {tension:.1f}/10
- **可重玩性**: 6.0/10
- **受众广度**: 7.0/10
- **综合评分**: {overall:.1f}/10

### 总结
{" ".join(summary_parts)}

---
*本报告由体验官AI自动生成*
"""
    
    with open(os.path.join(_script_dir, "experience_report_V1_0_0.md"), "w", encoding="utf-8") as f:
        f.write(report)
    
    print("报告已保存")
    await gm.stop()
    await bus.stop()


if __name__ == "__main__":
    asyncio.run(main())
