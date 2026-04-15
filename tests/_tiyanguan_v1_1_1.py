# -*- coding: utf-8 -*-
"""
体验官 V1_1_1 体验脚本 - 简化版
基于实际可用的 API
"""
import asyncio
import sys
import os
from datetime import datetime

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src import init_event_bus, init_game_master, EventType, Event
from src.character_creator import get_character_creator


RETRY_MAX = 3
RETRY_DELAY = 30
VERSION = "V1_1_1"


class NarrativeCollector:
    def __init__(self):
        self.narratives = []
        self.combat_events = []
        self.errors = []

    async def narrative_handler(self, event: Event):
        try:
            text = event.data.get("text", "")
            turn = event.data.get("turn", 0)
            if text and len(text.strip()) > 0:
                self.narratives.append({"turn": turn, "text": text})
                safe = text.encode("utf-8", errors="replace").decode("utf-8", errors="replace")
                print(f"[叙事 #{turn}] {safe[:120]}...")
        except Exception as e:
            self.errors.append(str(e))

    async def combat_handler(self, event: Event):
        self.combat_events.append(event.data)


async def safe_handle(master, message, retries=0):
    """带重试的 handle_player_message"""
    try:
        await master.handle_player_message(message)
        return True
    except Exception as e:
        err_str = str(e).lower()
        if any(kw in err_str for kw in ["429", "rate", "too many", "timeout", "timed out", "network", "529", "overloaded", "500", "unknown"]) and retries < RETRY_MAX:
            print(f"[API 限流，等待 30s 重试（第 {retries+1}/{RETRY_MAX} 次）]")
            await asyncio.sleep(RETRY_DELAY)
            return await safe_handle(master, message, retries + 1)
        # 其他错误，打印但不重试
        print(f"[Handle错误] {str(e)[:100]}")
        return False


async def run_experience():
    start_time = datetime.now()
    print("=" * 60)
    print(f"体验官 V{VERSION} 开始执行游戏体验...")
    print(f"开始时间: {start_time.isoformat()}")
    print("=" * 60)

    bus = await init_event_bus()
    master = await init_game_master()

    collector = NarrativeCollector()
    await bus.subscribe(EventType.NARRATIVE_OUTPUT, collector.narrative_handler, "tiyanguan_narrative")
    await bus.subscribe(EventType.COMBAT_START, collector.combat_handler, "tiyanguan_combat")
    await bus.subscribe(EventType.COMBAT_END, collector.combat_handler, "tiyanguan_combat")

    # 角色创建
    print("\n[阶段1] 角色创建")
    creator = get_character_creator()
    char = creator.create_from_selection("体验官", "human", "warrior")
    print(f"角色: {char.name} | {char.race_name} | {char.class_name}")
    print(f"HP: {char.current_hp}/{char.max_hp} | AC: {char.armor_class}")

    master.game_state["player_stats"] = {
        "hp": char.current_hp, "max_hp": char.max_hp,
        "ac": char.armor_class, "xp": char.xp,
        "level": char.level, "gold": char.gold,
        "inventory": char.inventory,
        "name": char.name, "race": char.race_name,
        "class": char.class_name,
    }
    master.game_state["turn"] = 0
    master.game_state["location"] = "月叶镇"

    # 探索序列
    test_cases = [
        ("酒馆开场", "我走进酒馆，环顾四周"),
        ("酒馆观察", "找个位置坐下，观察周围的人"),
        ("NPC对话-酒保", "向酒保打听镇子里的情况"),
        ("NPC对话-冒险者", "和旁边的冒险者交谈"),
        ("意外-跳舞", "我突然在酒馆中央跳舞"),
        ("意外-石头", "我试着和路边的石头说话"),
        ("镇中心探索", "离开酒馆，去镇中心逛逛"),
        ("市场探索", "去市场看看有什么商品"),
        ("商人对话", "向商人打听消息"),
        ("铁匠铺", "去铁匠铺看看"),
        ("森林冒险", "去镇子外面的森林冒险"),
        ("系统-状态", "查看状态"),
        ("系统-背包", "查看背包"),
        ("返回镇子", "返回月叶镇"),
        ("旅店休息", "找个旅店休息一下"),
        ("深入对话", "找镇子里看起来最重要的人深入聊聊"),
    ]

    print(f"\n[阶段2] 开始 {len(test_cases)} 个探索回合")
    for i, (tag, action) in enumerate(test_cases):
        turn_num = i + 1
        print(f"\n--- 回合 {turn_num}: [{tag}] ---")
        print(f"输入: {action}")
        
        # 记录当前叙事数量
        prev_count = len(collector.narratives)
        
        try:
            await safe_handle(master, action)
        except Exception as e:
            print(f"[发送输入异常] {e}")
        
        # 等待叙事产出（根据实际情况调整）
        # 如果刚发了输入，等待更长时间
        await asyncio.sleep(8)
        
        # 检查新叙事
        new_count = len(collector.narratives)
        added = new_count - prev_count
        if added == 0:
            print(f"[回合{turn_num}] 无新叙事")
        
        # 检查游戏状态
        try:
            stats = master.game_state.get("player_stats", {})
            loc = master.game_state.get("location", "?")
            print(f"状态: HP={stats.get('hp','?')}/{stats.get('max_hp','?')} | 位置={loc}")
        except:
            pass

    end_time = datetime.now()
    duration = (end_time - start_time).total_seconds()

    # 清理订阅
    try:
        await bus.unsubscribe(EventType.NARRATIVE_OUTPUT, "tiyanguan_narrative")
        await bus.unsubscribe(EventType.COMBAT_START, "tiyanguan_combat")
        await bus.unsubscribe(EventType.COMBAT_END, "tiyanguan_combat")
    except Exception:
        pass

    await master.stop()
    await bus.stop()

    # 统计
    narratives = collector.narratives
    empty_count = sum(1 for n in narratives if len(n["text"].strip()) < 10)
    battle_mentions = sum(1 for n in narratives
                          if any(kw in n["text"] for kw in ["战斗", "攻击", "敌人", "怪物", "狼"]))
    npc_mentions = sum(1 for n in narratives
                       if any(kw in n["text"] for kw in ["说", "回答", "老板", "商人", "冒险者", "铁匠"]))
    
    total_chars = sum(len(n["text"]) for n in narratives)
    avg_chars = total_chars / len(narratives) if narratives else 0
    
    responded = len([n for n in narratives if len(n["text"].strip()) >= 10])
    response_rate = responded / len(test_cases) if test_cases else 0

    print("\n" + "=" * 60)
    print("体验完成!")
    print(f"总时长: {duration:.1f}秒")
    print(f"叙事数量: {len(narratives)}")
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
        "narratives": narratives,
        "combat_events": collector.combat_events,
        "errors": collector.errors,
        "total_turns": len(test_cases),
        "responded_turns": responded,
        "response_rate": response_rate,
        "empty_count": empty_count,
        "battle_count": battle_mentions,
        "npc_count": npc_mentions,
        "total_chars": total_chars,
        "avg_chars": avg_chars,
        "final_location": master.game_state.get("location", "?"),
        "final_turn": master.game_state.get("turn", 0),
        "player_stats": master.game_state.get("player_stats", {}),
        "test_cases": test_cases,
        "version": VERSION,
    }


def generate_report(data) -> str:
    version = data["version"]
    duration = data["duration_seconds"]
    narratives = data["narratives"]
    test_cases = data["test_cases"]
    responded = data["responded_turns"]
    response_rate = data["response_rate"]
    avg_chars = data["avg_chars"]
    total_chars = data["total_chars"]
    battle_count = data["battle_count"]
    npc_count = data["npc_count"]
    errors = data["errors"]
    final_location = data["final_location"]

    # 按回合映射
    turn_map = {}
    for n in narratives:
        turn_map[n["turn"]] = n["text"]

    # 首句重复
    first_sentences = {}
    for turn, text in turn_map.items():
        if text:
            first_period = text.find("。")
            first_sentence = text[:first_period+1] if first_period != -1 else text[:50]
            if first_sentence not in first_sentences:
                first_sentences[first_sentence] = []
            first_sentences[first_sentence].append(turn)
    repeats = {fs: turns for fs, turns in first_sentences.items() if len(turns) > 1}
    repeat_count = sum(len(turns) - 1 for turns in repeats.values())

    # 通用模板
    generic_phrases = [
        "你的声音在空气中回荡",
        "场景中的细节在你眼前展开",
        "一切似乎恢复了平静",
        "没有人注意到你",
        "你的声音在空气中回荡，你的声音在空气中回荡",
    ]
    generic_count = 0
    for n in narratives:
        for phrase in generic_phrases:
            if phrase in n["text"]:
                generic_count += 1
                break

    # NPC回合
    npc_tags = ["NPC", "酒保", "冒险者", "商人", "铁匠", "深入"]
    npc_turns = []
    for i, (tag, action) in enumerate(test_cases):
        if any(kw in tag for kw in npc_tags):
            idx = i + 1
            text = turn_map.get(idx, "")
            npc_turns.append({"tag": tag, "action": action, "text": text[:300] if text else "(无响应)"})

    # 战斗回合
    battle_turns = []
    for i, (tag, action) in enumerate(test_cases):
        if any(kw in tag or kw in action for kw in ["战斗", "森林", "敌人"]):
            idx = i + 1
            text = turn_map.get(idx, "")
            battle_turns.append({"tag": tag, "action": action, "text": text[:300] if text else "(无响应)"})

    # 回合详细
    turn_details = []
    for i, (tag, action) in enumerate(test_cases):
        turn_num = i + 1
        text = turn_map.get(turn_num, "")
        length = len(text) if text else 0
        status = "✓" if length >= 10 else "✗无响应"
        turn_details.append({"turn": turn_num, "tag": tag, "action": action, "length": length, "status": status})

    report = f"""## 体验报告

> 版本：{version}
> 体验时间：{datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
> 游玩时长：{duration:.1f} 秒

### 基本信息
- **游玩时长**：{duration:.1f} 秒
- **到达阶段**：{final_location}
- **死亡次数**：0
- **NPC对话次数**：{sum(1 for t in test_cases if any(kw in t[0] for kw in npc_tags))}
- **战斗触发**：{len(data['combat_events'])} 次
- **总叙事字数**：{total_chars}
- **平均叙事长度**：{avg_chars:.0f} 字符/回合
- **叙事首句重复**：{repeat_count} 处
- **有效响应率**：{responded}/{len(test_cases)} ({response_rate:.0%})
- **空响应回合**：{len(test_cases) - responded}/{len(test_cases)}

### 叙事体验

#### 开场叙事
{turn_map.get(1, "(无)")[:500] if 1 in turn_map else "(无开场)"}

#### 叙事重复分析
"""
    if repeats:
        for fs, turns in repeats.items():
            report += f"- 回合 {turns} 首句相同：{fs[:60]}...\n"
    else:
        report += "- 无首句重复问题\n"

    report += f"""
#### NPC对话体验
"""
    for item in npc_turns:
        report += f"""
**[{item["tag"]}]** {item["action"]}
> {item["text"]}
"""

    report += f"""
#### 战斗体验
- 战斗事件触发：{len(data["combat_events"])} 次
- 战斗叙事提及：{battle_count} 次
"""
    for item in battle_turns:
        report += f"""
**[{item["tag"]}]** {item["action"]}
> {item["text"]}
"""

    report += f"""
### 节奏体验
- 叙事长度：平均 {avg_chars:.0f} 字符
- 有效响应：{response_rate:.0%}

### API/系统稳定性
- 错误次数：{len(errors)}
"""
    if errors:
        report += "- 错误详情：\n"
        for e in errors[:5]:
            report += f"  - {e}\n"

    report += f"""
### 具体问题（按严重程度）

| 位置/场景 | 问题描述 | 对应目标 | 严重程度 |
|-----------|---------|---------|---------|
"""

    if response_rate < 0.5:
        report += f"| 全局 | 有效响应率过低({response_rate:.0%}={responded}/{len(test_cases)}) | 情绪张力 | P0 |\n"
    if repeat_count > 3:
        report += f"| 全局 | 叙事首句重复（{repeat_count}处） | 情绪张力 | P0 |\n"
    if response_rate < 0.75 and response_rate >= 0.5:
        report += f"| 全局 | 有效响应率偏低({response_rate:.0%}) | 情绪张力 | P1 |\n"
    if generic_count > 3:
        report += f"| 全程 | 使用通用敷衍模板({generic_count}处) | 情绪张力 | P1 |\n"
    if avg_chars < 100:
        report += f"| 全程 | 叙事平均长度偏短({avg_chars:.0f}字) | 情绪张力 | P1 |\n"

    no_response_turns = [t for t in turn_details if t["status"] == "✗无响应"]
    if no_response_turns:
        names = ", ".join(t["tag"] for t in no_response_turns[:5])
        report += f"| 无响应 | 共{len(no_response_turns)}个回合无响应: {names} | 情绪张力 | P1 |\n"

    report += f"""
### 核心判别标准检查（AI 是否认真接住玩家输入）

#### 意外操作测试
| 操作 | AI 回应 | 是否敷衍 |
|------|---------|---------|
"""
    unexpected_tags = ["意外-跳舞", "意外-石头"]
    for tag, action in test_cases:
        if tag in unexpected_tags:
            idx = next((i for i, (t, a) in enumerate(test_cases) if t == tag), None)
            turn_num = idx + 1 if idx is not None else 1
            text = turn_map.get(turn_num, "")
            is_generic = any(gp in text for gp in generic_phrases)
            is_empty = len(text) < 10 or not text
            if is_empty:
                status = "完全敷衍"
            elif is_generic:
                status = "敷衍-通用模板"
            else:
                status = "认真"
            preview = text[:100] + "..." if len(text) > 100 else text
            report += f"| {action} | {preview} | {status} |\n"

    report += f"""
### 回合详情
| 回合 | 标签 | 操作 | 长度 | 状态 |
|------|------|------|------|------|
"""
    for td in turn_details:
        report += f"| {td['turn']} | {td['tag']} | {td['action']} | {td['length']}字 | {td['status']} |\n"

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

    # 评分
    score_response = 3 if response_rate >= 0.8 else (2 if response_rate >= 0.6 else (1 if response_rate >= 0.4 else 0))
    score_repeat = 2 if repeat_count == 0 else (1 if repeat_count <= 2 else 0)
    score_length = 2 if avg_chars >= 150 else (1 if avg_chars >= 80 else 0)
    score_generic = 2 if generic_count < 2 else (1 if generic_count < 5 else 0)
    overall_score = min(10, score_response + score_repeat + score_length + score_generic)

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
- 响应率：{response_rate:.0%}（{'优秀' if response_rate >= 0.8 else '正常' if response_rate >= 0.6 else '偏低' if response_rate >= 0.4 else '严重偏低'}）
- 叙事重复：{repeat_count} 处（{'正常' if repeat_count <= 2 else '有重复问题'}）
- 叙事长度：{avg_chars:.0f}字/回合（{'良好' if avg_chars >= 150 else '偏短' if avg_chars >= 80 else '严重偏短'}）

---
*本报告由体验官 Agent 自动生成*
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
        "experience_report_{}.md".format(VERSION)
    )
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(report)
    print(f"\n报告已保存: {report_path}")
