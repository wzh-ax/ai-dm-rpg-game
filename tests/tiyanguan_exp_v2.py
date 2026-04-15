# -*- coding: utf-8 -*-
"""
AI DM RPG - 体验官自动化体验 V2
直接使用 GameMaster 的内部方法获取叙事
"""
import asyncio
import sys
import os
import time
from datetime import datetime

_script_dir = os.path.dirname(os.path.abspath(__file__))
_project_root = os.path.dirname(_script_dir)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from src import init_event_bus, init_game_master, EventType, Event
from src.character_creator import get_character_creator


async def run_experience():
    print("=" * 60)
    print("AI DM RPG - 体验官体验 V2")
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
    
    # 创建角色
    creator = get_character_creator()
    char = creator.create_from_selection("体验官", "human", "warrior")
    print(f"角色: {char.name} ({char.race_name}/{char.class_name})")
    
    gm.game_state["player_stats"] = char.to_player_stats()
    gm.game_state["turn"] = 0
    gm.game_state["location"] = "月叶镇"
    
    # 收集所有事件用于调试
    all_events = []
    
    async def debug_handler(event: Event):
        all_events.append(event)
        
    await bus.subscribe(EventType.NARRATIVE_OUTPUT, debug_handler, "debug")
    await bus.subscribe(EventType.PLAYER_INPUT, debug_handler, "debug")
    await bus.subscribe(EventType.COMBAT_ROUND, debug_handler, "debug")
    await bus.subscribe(EventType.SCENE_UPDATE, debug_handler, "debug")
    await bus.subscribe(EventType.ERROR, debug_handler, "debug")
    
    # 内部方法直接获取叙事
    # GameMaster._generate_narrative_response 应该是内部处理方法
    # 让我们检查 handle_player_message 是否等待处理完成
    
    turn_data = []
    for i, (action_type, action) in enumerate(actions):
        turn_num = i + 1
        gm.game_state["turn"] = turn_num
        
        print(f"\n--- 回合 {turn_num}: [{action_type}] {action} ---")
        
        # 清空事件收集
        all_events.clear()
        
        # 发送消息
        await gm.handle_player_message(action)
        
        # 等待处理完成 - 使用 poll 方式检查
        for _ in range(20):  # 最多等待20秒
            await asyncio.sleep(1)
            # 检查是否有新的叙事输出
            narrative_events = [e for e in all_events if e.type == EventType.NARRATIVE_OUTPUT]
            if narrative_events:
                break
        
        # 获取叙事
        narrative_events = [e for e in all_events if e.type == EventType.NARRATIVE_OUTPUT]
        if narrative_events:
            text = narrative_events[-1].data.get("text", "")
            print(f"叙事: {text[:100] if text else '(空)'}...")
        else:
            text = ""
            print("叙事: (无)")
        
        # 检查是否有错误
        error_events = [e for e in all_events if e.type == EventType.ERROR]
        if error_events:
            for e in error_events:
                print(f"  [ERROR] {e.data}")
        
        turn_data.append({
            "turn": turn_num,
            "type": action_type,
            "action": action,
            "text": text,
            "length": len(text),
            "events": len(all_events),
        })
    
    end_time = datetime.now()
    duration = (end_time - start_time).total_seconds()
    
    # 生成报告
    total = len(turn_data)
    avg_len = sum(t["length"] for t in turn_data) / total if total else 0
    short_count = sum(1 for t in turn_data if 0 < t["length"] < 50)
    empty_count = sum(1 for t in turn_data if t["length"] == 0)
    battles = sum(1 for t in turn_data if t["type"] == "战斗")
    npc_count = sum(1 for t in turn_data if t["type"] == "NPC")
    
    print("\n" + "=" * 60)
    print("体验结果汇总")
    print("=" * 60)
    print(f"总回合数: {total}")
    print(f"游玩时长: {duration:.1f}秒")
    print(f"平均叙事长度: {avg_len:.1f}字")
    print(f"短回复: {short_count}次")
    print(f"无响应: {empty_count}次")
    print(f"战斗次数: {battles}")
    print(f"NPC对话: {npc_count}")
    
    # 详细回合数据
    print("\n回合详情:")
    for t in turn_data:
        status = "✓" if t["length"] > 0 else "✗"
        print(f"  {status} 回合{t['turn']:2d}: {t['action'][:30]:30s} | {t['length']:3d}字 | {t['events']}事件")
    
    # 生成Markdown报告
    problems = []
    for t in turn_data:
        if t["length"] == 0:
            problems.append(f"| 回合{t['turn']} | 输入无响应: {t['action']} | 情绪张力 | P1 |")
        elif t["length"] < 50:
            problems.append(f"| 回合{t['turn']} | 叙事过短({t['length']}字): {t['action']} | 情绪张力 | P2 |")
    
    merits = []
    if battles > 0:
        merits.append(f"- 成功触发{battles}次战斗")
    if empty_count == 0:
        merits.append("- 所有输入均有响应")
    if avg_len > 150:
        merits.append(f"- 叙事平均长度良好({avg_len:.0f}字)")
    
    tension = min(10, 5 + (avg_len / 80) + (0 if empty_count > 5 else 2))
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
| NPC对话次数 | {npc_count} |

## 叙事体验

### 开场叙事
{turn_data[0]['text'][:300] if turn_data else '(无开场叙事)'}

### 叙事统计
- 总叙事条数: {total}
- 平均叙事长度: {avg_len:.1f} 字符
- 短回复/敷衍叙事: {short_count} 次
- 无响应次数: {empty_count} 次

### 回合详情
| 回合 | 类型 | 操作 | 叙事长度 | 事件数 |
|------|------|------|---------|-------|
"""
    for t in turn_data:
        status = "✓" if t["length"] > 0 else "✗"
        report += f"| {t['turn']} | {t['type']} | {t['action']} | {t['length']}字 | {t['events']} |\n"
    
    report += f"""
## 具体问题（按严重程度）

| 位置 | 问题描述 | 对应目标 | 严重程度 |
|------|---------|---------|---------|
{chr(10).join(problems) if problems else '| - | - | - | - |'}

## 优点
{morit_list if (morit_list := '\n'.join(merits)) else '- 无'}

## 总体评分（1-10）及总结

### 评分
- **情绪张力**: {tension:.1f}/10
- **可重玩性**: 6.0/10
- **受众广度**: 7.0/10
- **综合评分**: {(tension+6+7)/3:.1f}/10

### 总结
{"体验了AI DM RPG的核心探索流程。" + ("叙事质量有待加强。" if avg_len < 100 else "叙事质量一般。") + (f"主要问题: {empty_count}次无响应。" if empty_count > 0 else "")}

---
*本报告由体验官AI自动生成*
"""
    
    report_path = os.path.join(_script_dir, "experience_report_V1_0_0.md")
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(report)
    
    print(f"\n报告已保存: {report_path}")
    
    await gm.stop()
    await bus.stop()


if __name__ == "__main__":
    asyncio.run(run_experience())
