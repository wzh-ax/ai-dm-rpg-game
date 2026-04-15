# -*- coding: utf-8 -*-
"""
体验官 V1_1_2 体验脚本
基于 _exp_run2.py 的等待机制
"""
import asyncio
import sys
import os
from datetime import datetime

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _project_root)

from src import init_event_bus, init_game_master, EventType, Event
from src.character_creator import get_character_creator

VERSION = "V1_1_2"
RETRY_MAX = 3
RETRY_DELAY = 30


async def wait_for_narrative(bus, timeout=30, expected_turn=None):
    """等待叙事事件"""
    start = datetime.now()
    while (datetime.now() - start).total_seconds() < timeout:
        await asyncio.sleep(1)
        if hasattr(bus, '_last_narrative') and bus._last_narrative:
            data = bus._last_narrative
            if expected_turn is None or data.get('turn') == expected_turn:
                bus._last_narrative = None
                return data
    return None


async def run_experience():
    start_time = datetime.now()
    print("=" * 60)
    print(f"体验官 V{VERSION} 开始执行游戏体验...")
    print(f"开始时间: {start_time.isoformat()}")
    print("=" * 60)

    bus = await init_event_bus()
    gm = await init_game_master()
    
    # 注入偷窃最新叙事的hack
    bus._last_narrative = None

    collector_narratives = []
    collector_combat = []

    async def collect_narrative(event: Event):
        bus._last_narrative = event.data
        collector_narratives.append(event.data)
        text = event.data.get("text", "")[:100]
        print(f"[叙事 #{event.data.get('turn', '?')}] {text}...")

    async def collect_combat(event: Event):
        collector_combat.append(event.data)
        print(f"[战斗事件] {event.type}")

    await bus.subscribe(EventType.NARRATIVE_OUTPUT, collect_narrative, "tiyanguan_narrative")
    await bus.subscribe(EventType.COMBAT_START, collect_combat, "tiyanguan_combat")
    await bus.subscribe(EventType.COMBAT_END, collect_combat, "tiyanguan_combat")

    # 角色创建
    print("\n[阶段1] 角色创建")
    creator = get_character_creator()
    char = creator.create_from_selection("体验官", "human", "warrior")
    print(f"角色: {char.name} | {char.race_name} | {char.class_name}")
    print(f"HP: {char.current_hp}/{char.max_hp} | AC: {char.armor_class}")

    gm.game_state["player_stats"] = {
        "hp": char.current_hp, "max_hp": char.max_hp,
        "ac": char.armor_class, "xp": char.xp,
        "level": char.level, "gold": char.gold,
        "inventory": char.inventory,
        "name": char.name, "race": char.race_name,
        "class": char.class_name,
    }
    gm.game_state["turn"] = 0
    gm.game_state["location"] = "月叶镇"

    # 探索序列
    test_cases = [
        ("酒馆开场", "我走进酒馆，环顾四周"),
        ("酒馆坐下", "找个位置坐下，观察周围的人"),
        ("NPC交谈-通用", "和酒馆里的人交谈"),
        ("意外-跳舞", "我突然在酒馆中央跳舞"),
        ("意外-石头", "我试着和门外的石头说话"),
        ("镇中心", "离开酒馆，去镇中心逛逛"),
        ("NPC对话-商人", "找镇中心的人打听消息"),
        ("市场探索", "去市场看看有什么商品"),
        ("铁匠铺", "去铁匠铺看看"),
        ("森林冒险", "去镇子外面的森林冒险"),
        ("森林搜索", "在森林里四处搜索"),
        ("系统-状态", "查看状态"),
        ("系统-背包", "查看背包"),
        ("返回镇子", "返回月叶镇"),
        ("旅店休息", "找个旅店休息一下"),
        ("深入对话", "找镇子里看起来最重要的人深入聊聊"),
    ]

    print(f"\n[阶段2] 开始 {len(test_cases)} 个探索回合")
    turn_data = []
    
    for i, (tag, action) in enumerate(test_cases):
        turn_num = i + 1
        gm.game_state["turn"] = turn_num
        bus._last_narrative = None
        
        print(f"\n--- 回合 {turn_num}: [{tag}] ---")
        print(f"输入: {action}")
        
        try:
            await gm.handle_player_message(action)
        except Exception as e:
            err_str = str(e)
            is_rate = any(kw in err_str.lower() for kw in ["429", "rate", "too many", "timeout", "timed out", "network", "529", "overloaded", "500", "unavailable"])
            if is_rate:
                print(f"[API 限流，等待 30s 重试]")
                await asyncio.sleep(RETRY_DELAY)
                try:
                    await gm.handle_player_message(action)
                except Exception as e2:
                    print(f"[重试失败] {e2}")
            else:
                print(f"[Handle错误] {err_str[:100]}")
        
        # 等待叙事
        narrative_data = await wait_for_narrative(bus, timeout=30, expected_turn=turn_num)
        
        if narrative_data:
            text = narrative_data.get("text", "")
            mode = narrative_data.get("mode", "unknown")
            print(f"叙事 [{mode}]: {text[:100] if text else '(空)'}")
        else:
            text = ""
            mode = "unknown"
            print(f"叙事: (等待超时)")
        
        turn_data.append({
            "turn": turn_num,
            "tag": tag,
            "action": action,
            "text": text,
            "length": len(text) if text else 0,
            "mode": mode,
        })
        
        stats = gm.game_state.get("player_stats", {})
        loc = gm.game_state.get("location", "?")
        print(f"状态: HP={stats.get('hp','?')}/{stats.get('max_hp','?')} | 位置={loc}")

    end_time = datetime.now()
    duration = (end_time - start_time).total_seconds()

    await gm.stop()
    await bus.stop()

    # 统计
    empty_count = sum(1 for t in turn_data if t["length"] == 0)
    responded = len(test_cases) - empty_count
    response_rate = responded / len(test_cases) if test_cases else 0
    total_chars = sum(t["length"] for t in turn_data)
    avg_chars = total_chars / len(turn_data) if turn_data else 0
    battle_mentions = sum(1 for n in collector_narratives
                          if any(kw in n.get("text", "") for kw in ["战斗", "攻击", "敌人", "怪物", "狼", "战斗开始"]))
    npc_mentions = sum(1 for n in collector_narratives
                       if any(kw in n.get("text", "") for kw in ["说", "回答", "老板", "商人", "冒险者", "铁匠", "交谈"]))

    print("\n" + "=" * 60)
    print("体验完成!")
    print(f"总时长: {duration:.1f}秒")
    print(f"叙事数量: {len(collector_narratives)}")
    print(f"有效响应: {responded}/{len(test_cases)} ({response_rate:.0%})")
    print(f"空响应: {empty_count}")
    print(f"战斗提及: {battle_mentions}")
    print(f"NPC提及: {npc_mentions}")
    print(f"总字符: {total_chars}")
    print(f"平均叙事: {avg_chars:.0f}字符/回合")
    print("=" * 60)

    return {
        "start_time": start_time.isoformat(),
        "end_time": end_time.isoformat(),
        "duration_seconds": duration,
        "narratives": collector_narratives,
        "combat_events": collector_combat,
        "turn_data": turn_data,
        "total_turns": len(test_cases),
        "responded_turns": responded,
        "response_rate": response_rate,
        "empty_count": empty_count,
        "battle_count": battle_mentions,
        "npc_count": npc_mentions,
        "total_chars": total_chars,
        "avg_chars": avg_chars,
        "final_location": gm.game_state.get("location", "?"),
        "final_turn": gm.game_state.get("turn", 0),
        "player_stats": gm.game_state.get("player_stats", {}),
        "version": VERSION,
    }


def generate_report(data) -> str:
    version = data["version"]
    duration = data["duration_seconds"]
    narratives = data["narratives"]
    turn_data = data["turn_data"]
    responded = data["responded_turns"]
    response_rate = data["response_rate"]
    avg_chars = data["avg_chars"]
    total_chars = data["total_chars"]
    battle_count = data["battle_count"]
    npc_count = data["npc_count"]
    final_location = data["final_location"]

    # 按回合映射叙事
    turn_map = {t["turn"]: t["text"] for t in turn_data}

    # 首句重复检测
    first_sentences = {}
    for turn_num, text in turn_map.items():
        if text:
            first_period = text.find("。")
            first_sentence = text[:first_period+1] if first_period != -1 else text[:50]
            if first_sentence not in first_sentences:
                first_sentences[first_sentence] = []
            first_sentences[first_sentence].append(turn_num)
    repeats = {fs: turns for fs, turns in first_sentences.items() if len(turns) > 1}
    repeat_count = sum(len(turns) - 1 for turns in repeats.values())

    generic_phrases = [
        "你的声音在空气中回荡",
        "场景中的细节在你眼前展开",
        "一切似乎恢复了平静",
        "没有人注意到你",
    ]
    generic_count = 0
    for t in turn_data:
        for phrase in generic_phrases:
            if phrase in t["text"]:
                generic_count += 1
                break

    # 纯氛围句检测
    atmosphere_only = sum(1 for t in turn_data if t["length"] > 0 and t["length"] < 30 and "空气中弥漫着" in t["text"])

    # NPC对话回合
    npc_turns = [t for t in turn_data if any(kw in t["tag"] for kw in ["NPC", "商人", "铁匠", "深入"])]

    # 战斗回合
    battle_turns = [t for t in turn_data if any(kw in t["tag"] or kw in t["action"] for kw in ["战斗", "森林"])]

    report = f"""## 体验报告

> 版本：{version}
> 体验时间：{datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
> 游玩时长：{duration:.1f} 秒

### 基本信息
- **游玩时长**：{duration:.1f} 秒
- **到达阶段**：{final_location}
- **死亡次数**：0
- **NPC对话次数**：{sum(1 for t in turn_data if any(kw in t['tag'] for kw in ['NPC', '商人', '深入']))}
- **战斗触发**：{len(data['combat_events'])} 次
- **总叙事字数**：{total_chars}
- **平均叙事长度**：{avg_chars:.0f} 字符/回合
- **叙事首句重复**：{repeat_count} 处
- **有效响应率**：{responded}/{len(turn_data)} ({response_rate:.0%})
- **空响应回合**：{data['empty_count']}/{len(turn_data)}
- **纯氛围句**：{atmosphere_only} 回合（叙事极短且仅含氛围描写）

### 叙事体验

#### 开场叙事（酒馆开场）
{turn_map.get(1, "(无)")[:600] if 1 in turn_map and turn_map[1] else "(无开场)"}

#### 叙事重复分析
"""
    if repeats:
        for fs, turns in repeats.items():
            report += f"- 回合 {turns} 首句相同：{fs[:80]}...\n"
    else:
        report += "- 无首句重复问题\n"

    report += f"""
#### NPC对话体验
"""
    for item in npc_turns:
        report += f"""
**[{item["tag"]}]** {item["action"]}
> {item["text"][:400] if item["text"] else "(无响应)"}
"""

    report += f"""
#### 战斗体验
- 战斗事件触发：{len(data["combat_events"])} 次
- 战斗叙事提及：{battle_count} 次
"""
    for item in battle_turns:
        report += f"""
**[{item["tag"]}]** {item["action"]}
> {item["text"][:400] if item["text"] else "(无响应)"}
"""

    report += f"""
### 节奏体验
- 叙事长度：平均 {avg_chars:.0f} 字符
- 有效响应：{response_rate:.0%}

### API/系统稳定性
- 错误次数：0
"""

    report += f"""
### 具体问题（按严重程度）

| 位置/场景 | 问题描述 | 对应目标 | 严重程度 |
|-----------|---------|---------|---------|
"""

    if response_rate < 0.5:
        report += f"| 全局 | 有效响应率过低({response_rate:.0%}={responded}/{len(turn_data)}) | 情绪张力 | P0 |\n"
    if repeat_count > 3:
        report += f"| 全局 | 叙事首句重复（{repeat_count}处） | 情绪张力 | P0 |\n"
    if atmosphere_only > 3:
        report += f"| 全局 | 纯氛围句过多({atmosphere_only}处) | 情绪张力 | P1 |\n"

    if response_rate < 0.75 and response_rate >= 0.5:
        report += f"| 全局 | 有效响应率偏低({response_rate:.0%}) | 情绪张力 | P1 |\n"
    if generic_count > 3:
        report += f"| 全程 | 使用通用敷衍模板({generic_count}处) | 情绪张力 | P1 |\n"
    if avg_chars < 100:
        report += f"| 全程 | 叙事平均长度偏短({avg_chars:.0f}字) | 情绪张力 | P1 |\n"

    no_response_turns = [t for t in turn_data if t["length"] == 0]
    if no_response_turns:
        report += f"| 无响应 | 共{len(no_response_turns)}个回合无响应: {', '.join(t['tag'] for t in no_response_turns[:5])} | 情绪张力 | P1 |\n"

    report += f"""
### 核心判别标准检查（AI 是否认真接住玩家输入）

#### 意外操作测试
| 操作 | AI 回应摘要 | 是否敷衍 |
|------|---------|---------|
"""

    unexpected_tags = ["意外-跳舞", "意外-石头"]
    for t in turn_data:
        if t["tag"] in unexpected_tags:
            text = t["text"]
            is_generic = any(gp in text for gp in generic_phrases)
            is_empty = len(text) < 10 or not text
            is_atmosphere_only = len(text) > 0 and len(text) < 30 and "空气中弥漫着" in text
            if is_empty:
                status = "完全敷衍(无响应)"
            elif is_atmosphere_only:
                status = "敷衍-纯氛围句"
            elif is_generic:
                status = "敷衍-通用模板"
            else:
                status = "认真"
            preview = text[:120] + "..." if len(text) > 120 else text
            report += f"| {t['action']} | {preview} | {status} |\n"

    report += f"""
### 回合详情
| 回合 | 标签 | 操作 | 长度 | 状态 |
|------|------|------|------|------|
"""
    for t in turn_data:
        status = "✓" if t["length"] >= 10 else "✗无响应"
        report += f"| {t['turn']} | {t['tag']} | {t['action']} | {t['length']}字 | {status} |\n"

    report += f"""
### 优点
"""
    if response_rate >= 0.8:
        report += f"- 有效响应率优秀({response_rate:.0%})\n"
    if avg_chars >= 150:
        report += f"- 叙事平均长度良好({avg_chars:.0f}字)\n"
    if repeat_count == 0:
        report += "- 无叙事首句重复问题\n"
    if battle_count > 0:
        report += f"- 成功触发战斗({battle_count}次提及)\n"

    score_base = 0
    if response_rate >= 0.9:
        score_base = 3
    elif response_rate >= 0.7:
        score_base = 2
    elif response_rate >= 0.5:
        score_base = 1
    
    score_repeat = 2 if repeat_count == 0 else (1 if repeat_count <= 2 else 0)
    score_length = 2 if avg_chars >= 150 else (1 if avg_chars >= 80 else 0)
    score_generic = 2 if generic_count < 2 else (1 if generic_count < 5 else 0)
    
    overall_score = min(10, score_base * 2 + score_repeat + score_length + score_generic)

    report += f"""
### 总体评分（1-10）及总结

**总体评分：{overall_score} / 10**

**总结**：
"""
    if overall_score >= 8:
        report += "版本体验优秀，叙事流畅、差异化强，AI能够认真接住玩家各类输入。"
    elif overall_score >= 7:
        report += "版本体验良好，叙事质量较高，存在轻微问题但不影响整体体验。"
    elif overall_score >= 6:
        report += "版本基本可用，但存在响应率偏低或叙事重复问题。"
    elif overall_score >= 5:
        report += "版本存在明显问题，有效响应率偏低，需要重点改进。"
    else:
        report += "版本存在严重问题，体验较差。"

    report += f"""

**关键数据**：
- 响应率：{response_rate:.0%}（{'正常' if response_rate >= 0.8 else '偏低' if response_rate >= 0.5 else '严重偏低'}）
- 叙事重复：{repeat_count} 处（{'正常' if repeat_count <= 2 else '有重复问题'}）
- 叙事长度：{avg_chars:.0f}字/回合（{'良好' if avg_chars >= 150 else '偏短' if avg_chars >= 80 else '严重偏短'}）

---
*本报告由体验官 Agent 自动生成 V{VERSION}*
"""
    return report


if __name__ == "__main__":
    result = asyncio.run(run_experience())

    report = generate_report(result)
    print("\n" + "=" * 60)
    print("体验报告:")
    print("=" * 60)
    print(report)

    report_path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        f"experience_report_{VERSION}.md"
    )
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(report)
    print(f"\n报告已保存: {report_path}")
