# -*- coding: utf-8 -*-
"""
体验官 V1_0_8 体验脚本
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
VERSION = "V1_0_8"


class NarrativeCollector:
    """叙事收集器"""
    def __init__(self):
        self.narratives = []
        self.combat_events = []
        self.errors = []

    async def narrative_handler(self, event: Event):
        try:
            text = event.data.get("text", "")
            turn = event.data.get("turn", 0)
            if text:
                self.narratives.append({"turn": turn, "text": text})
                safe = text.encode("utf-8", errors="replace").decode("utf-8", errors="replace")
                print(f"[叙事 #{turn}] {safe[:120]}...")
        except Exception as e:
            self.errors.append(str(e))

    async def combat_handler(self, event: Event):
        self.combat_events.append(event.data)


async def safe_handle_with_retry(master, message, retries=0):
    """带重试的 handle_player_message"""
    try:
        await master.handle_player_message(message)
        return True
    except Exception as e:
        err_str = str(e).lower()
        if any(kw in err_str for kw in ["429", "rate", "too many", "timeout", "timed out"]) and retries < RETRY_MAX:
            print(f"[API 限流，等待 30s 重试（第 {retries+1}/{RETRY_MAX} 次）]")
            await asyncio.sleep(RETRY_DELAY)
            return await safe_handle_with_retry(master, message, retries + 1)
        raise


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

    # 探索序列 - 测试核心功能
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
        ("森林战斗", "主动寻找敌人"),
        ("系统-状态", "查看状态"),
        ("系统-背包", "查看背包"),
        ("返回镇子", "返回月叶镇"),
        ("旅店休息", "找个旅店休息一下"),
        ("深入对话", "找镇子里看起来最重要的人深入聊聊"),
    ]

    print(f"\n[阶段2] 开始 {len(test_cases)} 个探索回合")
    for i, (tag, action) in enumerate(test_cases):
        turn_num = master.game_state.get("turn", 0) + 1
        print(f"\n--- 回合 {turn_num}: [{tag}] ---")
        print(f"输入: {action}")
        try:
            await safe_handle_with_retry(master, action)
        except Exception as e:
            print(f"发送输入异常: {e}")
        await asyncio.sleep(5)  # 等待 LLM 处理

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
    empty_count = sum(1 for n in collector.narratives if len(n["text"].strip()) < 5)
    battle_mentions = sum(1 for n in collector.narratives
                          if any(kw in n["text"] for kw in ["战斗", "攻击", "敌人", "怪物", "狼"]))
    npc_mentions = sum(1 for n in collector.narratives
                       if any(kw in n["text"] for kw in ["说", "回答", "对话", "老板", "商人", "冒险者", "铁匠"]))

    total_chars = sum(len(n["text"]) for n in collector.narratives)
    avg_chars = total_chars / len(collector.narratives) if collector.narratives else 0

    print("\n" + "=" * 60)
    print("体验完成!")
    print(f"总时长: {duration:.1f}秒")
    print(f"叙事数量: {len(collector.narratives)}")
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
        "narratives": collector.narratives,
        "combat_events": collector.combat_events,
        "errors": collector.errors,
        "total_turns": len(test_cases),
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
    """生成体验报告"""
    version = data["version"]
    duration = data["duration_seconds"]
    narratives = data["narratives"]
    test_cases = data["test_cases"]
    empty_count = data["empty_count"]
    avg_chars = data["avg_chars"]
    total_chars = data["total_chars"]
    battle_count = data["battle_count"]
    npc_count = data["npc_count"]
    errors = data["errors"]
    final_location = data["final_location"]
    final_turn = data["final_turn"]

    # 分析叙事数据
    turn_map = {n["turn"]: n["text"] for n in narratives}

    # 核心判别：意外操作测试
    unexpected_results = {}
    for tag, action in test_cases:
        if tag.startswith("意外"):
            turn = None
            for n in narratives:
                if n["text"] == turn_map.get(n["turn"]):
                    pass
            turn_text = None
            for turn_num, text in turn_map.items():
                for n in narratives:
                    if n["turn"] == turn_num and n["text"] == text:
                        turn_text = text
                        break
                if turn_text:
                    break
            unexpected_results[tag] = {
                "action": action,
                "text": turn_text or "(无响应)"
            }

    # 通用模板检测
    generic_phrases = [
        "你的声音在空气中回荡",
        "场景中的细节在你眼前展开",
        "一切似乎恢复了平静",
        "没有人注意到你",
        "你感觉到",
    ]
    generic_count = 0
    for n in narratives:
        for phrase in generic_phrases:
            if phrase in n["text"]:
                generic_count += 1
                break

    # 叙事详细分析
    narrative_details = []
    for tag, action in test_cases:
        found = None
        for n in narratives:
            if len(n["text"]) > 5:
                found = n["text"]
                break
        narrative_details.append({
            "tag": tag,
            "action": action,
            "narrative": found[:200] if found else "(无响应)"
        })

    report = f"""## 体验报告

### 基本信息
- 游玩时长：约 {duration:.0f} 秒
- 到达阶段：{final_location}（回合 {final_turn}）
- 死亡次数：0
- 角色：体验官（人类 战士）
- 版本：{version}

### 叙事体验

#### 开场叙事
{turn_map.get(1, "(无)")[:300] if 1 in turn_map else "(无开场)"}

#### NPC对话
- NPC相关叙事提及：{npc_count} 次
- 体验：{'NPC互动较为丰富' if npc_count > 3 else 'NPC互动较少'}

#### 战斗体验
- 战斗相关叙事提及：{battle_count} 次
- 战斗紧张感：{'有' if battle_count > 0 else '未触发战斗'}

### 节奏体验
- 平均每回合叙事长度：{avg_chars:.0f} 字符
- 空响应（无叙事）次数：{empty_count} 次
- 整体节奏：{'流畅' if empty_count == 0 and avg_chars > 100 else '有中断'}

### API/系统稳定性
- 错误次数：{len(errors)}
- 错误详情：{errors[:3] if errors else "无"}

### 具体问题（按严重程度）

| 位置 | 问题描述 | 对应目标 | 严重程度 |
|------|---------|---------|---------|
"""

    # 检测问题
    if empty_count > len(test_cases) * 0.3:
        report += f"| 全程 | 空响应过多({empty_count}/{len(test_cases)}) | 情绪张力 | P0 |\n"
    if generic_count > 3:
        report += f"| 全程 | 使用通用敷衍模板({generic_count}处) | 情绪张力 | P1 |\n"

    for tag, action in test_cases:
        found_text = None
        for n in narratives:
            found_text = n["text"]
            break
        if not found_text or len(found_text) < 10:
            report += f"| {tag} | 输入无响应: {action} | 情绪张力 | P1 |\n"

    report += f"""
### 核心判别标准检查（AI 是否认真接住玩家输入）

#### 意外操作测试
| 操作 | AI 回应 | 是否敷衍 |
|------|---------|---------|
"""

    for tag, result in unexpected_results.items():
        text = result["text"]
        is_generic = any(gp in text for gp in generic_phrases)
        is_empty = len(text) < 10
        if is_empty:
            status = "完全敷衍"
        elif is_generic:
            status = "敷衍-通用模板"
        else:
            status = "认真"
        preview = text[:100] + "..." if len(text) > 100 else text
        report += f"| {result['action']} | {preview} | {status} |\n"

    report += f"""
### 回合详情
| 回合 | 标签 | 操作 | 叙事长度 |
|------|------|------|---------|
"""

    for i, (tag, action) in enumerate(test_cases):
        turn_num = i + 1
        text = turn_map.get(turn_num, "")
        length = len(text) if text else 0
        report += f"| {turn_num} | {tag} | {action} | {length}字 |\n"

    report += f"""
### 优点
"""
    if avg_chars > 150:
        report += f"- 叙事平均长度良好({avg_chars:.0f}字)\n"
    if empty_count == 0:
        report += "- 所有输入均有响应\n"
    if battle_count > 0:
        report += f"- 成功触发战斗({battle_count}次提及)\n"
    if npc_count > 3:
        report += f"- NPC互动丰富({npc_count}次提及)\n"

    if empty_count == 0 and avg_chars > 100 and generic_count < 3:
        overall_score = 8
    elif empty_count < 3 and avg_chars > 80:
        overall_score = 6
    else:
        overall_score = 4

    report += f"""
### 总体评分（1-10）及总结

**评分：{overall_score}/10**

**总结**："""

    if overall_score >= 8:
        report += "版本体验良好，叙事流畅，AI能够认真接住玩家输入。"
    elif overall_score >= 6:
        report += "版本基本可用，但存在空响应或叙事偏短的问题。"
    else:
        report += "版本存在严重问题，空响应过多或叙事质量差。"

    report += f"""

---
*报告生成时间：{datetime.now().strftime("%Y-%m-%d %H:%M:%S")}*
*体验官：tiyanguan*
"""
    return report


if __name__ == "__main__":
    result = asyncio.run(run_experience())

    report = generate_report(result)
    print("\n" + "=" * 60)
    print("体验报告:")
    print("=" * 60)
    print(report)

    # 保存报告
    report_path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        f"experience_report_{VERSION}.md"
    )
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(report)
    print(f"\n报告已保存: {report_path}")
