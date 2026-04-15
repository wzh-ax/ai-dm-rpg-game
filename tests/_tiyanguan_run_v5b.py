# -*- coding: utf-8 -*-
"""
体验官 V1_0_5 详细体验脚本 - 捕获所有叙事
"""
import asyncio
import sys
import os
import json
from datetime import datetime

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src import init_event_bus, init_game_master, EventType, Event
from src.character_creator import get_character_creator


class DetailedCollector:
    def __init__(self):
        self.narratives = []
        self.combat_events = []
        self.errors = []
        self.scene_updates = []

    async def narrative_handler(self, event: Event):
        try:
            text = event.data.get("text", "")
            turn = event.data.get("turn", 0)
            mode = event.data.get("mode", "unknown")
            self.narratives.append({"turn": turn, "mode": mode, "text": text})
            safe = text.encode("utf-8", errors="replace").decode("utf-8", errors="replace")
            print(f"[叙事 #{turn}][{mode}] {safe[:120]}...")
        except Exception as e:
            self.errors.append(f"narrative_handler: {e}")

    async def combat_handler(self, event: Event):
        self.combat_events.append(event.data)
        print(f"[Combat] {event.type}: {str(event.data)[:80]}...")

    async def scene_handler(self, event: Event):
        self.scene_updates.append(event.data)
        print(f"[Scene] {str(event.data)[:80]}...")

    async def error_handler(self, event: Event):
        self.errors.append(str(event.data))
        print(f"[Error] {str(event.data)[:80]}...")


async def run_experience():
    start_time = datetime.now()
    print("=" * 60)
    print("体验官 V1_0_5 详细体验开始...")
    print("=" * 60)

    bus = await init_event_bus()
    master = await init_game_master()

    collector = DetailedCollector()
    await bus.subscribe(EventType.NARRATIVE_OUTPUT, collector.narrative_handler, "tiyanguan")
    await bus.subscribe(EventType.COMBAT_START, collector.combat_handler, "tiyanguan")
    await bus.subscribe(EventType.COMBAT_END, collector.combat_handler, "tiyanguan")
    await bus.subscribe(EventType.SCENE_UPDATE, collector.scene_handler, "tiyanguan")

    # 角色创建
    creator = get_character_creator()
    char = creator.create_from_selection("冒险者", "human", "warrior")
    print(f"角色: {char.name} | {char.race_name} | {char.class_name}")

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

    test_cases = [
        ("酒馆开场", "我走进酒馆，环顾四周"),
        ("酒馆坐下", "找个位置坐下，观察周围的人"),
        ("NPC交谈", "和酒馆里的人交谈"),
        ("酒保打听", "向酒保打听镇子里的情况"),
        ("镇中心", "离开酒馆，去镇中心逛逛"),
        ("镇中心NPC", "在镇中心找人聊聊"),
        ("意外跳舞", "我突然在镇中心跳舞"),
        ("意外大喊", "我对天空大喊一声"),
        ("市场", "去市场看看有什么商品"),
        ("商人打听", "向商人打听消息"),
        ("森林冒险", "去镇子外面的森林冒险"),
        ("森林搜索", "在森林里四处搜索"),
        ("查看状态", "查看状态"),
        ("返回镇子", "返回月叶镇"),
        ("旅店休息", "找个旅店休息一下"),
        ("重要NPC", "找镇子里看起来最重要的人深入聊聊"),
        ("询问传说", "询问关于这片土地的传说"),
    ]

    print(f"\n开始 {len(test_cases)} 个探索回合...\n")
    for i, (tag, action) in enumerate(test_cases):
        turn_before = master.game_state.get("turn", 0)
        print(f"\n--- [{i+1}/{len(test_cases)}] {tag} ---")
        print(f"输入: {action}")
        print(f"当前模式: {master.mode}")
        try:
            await master.handle_player_message(action)
            await asyncio.sleep(5)
        except Exception as e:
            print(f"[错误] {e}")
            await asyncio.sleep(5)
        turn_after = master.game_state.get("turn", 0)
        print(f"回合变化: {turn_before} -> {turn_after}")

    end_time = datetime.now()
    duration = (end_time - start_time).total_seconds()

    # 清理
    for et in [EventType.NARRATIVE_OUTPUT, EventType.COMBAT_START, EventType.COMBAT_END, EventType.SCENE_UPDATE]:
        try:
            await bus.unsubscribe(et, "tiyanguan")
        except Exception:
            pass

    await master.stop()
    await bus.stop()

    # 统计
    empty_count = sum(1 for n in collector.narratives if len(n["text"].strip()) < 5)
    battle_mentions = sum(1 for n in collector.narratives
                          if any(kw in n["text"] for kw in ["战斗", "攻击", "敌人"]))
    total_chars = sum(len(n["text"]) for n in collector.narratives)
    avg_chars = total_chars / len(collector.narratives) if collector.narratives else 0

    print("\n" + "=" * 60)
    print("体验完成!")
    print(f"总时长: {duration:.1f}秒")
    print(f"叙事数量: {len(collector.narratives)}")
    print(f"空响应: {empty_count}")
    print(f"战斗提及: {battle_mentions}")
    print(f"总字符: {total_chars}")
    print(f"平均叙事: {avg_chars:.0f}字符/回合")
    print("=" * 60)

    # 保存原始数据
    raw_data = {
        "start_time": start_time.isoformat(),
        "end_time": end_time.isoformat(),
        "duration_seconds": duration,
        "narratives": collector.narratives,
        "combat_events": collector.combat_events,
        "scene_updates": collector.scene_updates,
        "errors": collector.errors,
        "test_cases": test_cases,
        "stats": {
            "total_turns": len(test_cases),
            "narrative_count": len(collector.narratives),
            "empty_count": empty_count,
            "battle_mentions": battle_mentions,
            "total_chars": total_chars,
            "avg_chars": avg_chars,
        },
        "final_turn": master.game_state.get("turn", 0),
        "final_location": master.game_state.get("location", "?"),
        "final_mode": master.mode,
        "player_stats": master.game_state.get("player_stats", {}),
    }

    output_file = r"D:\ai-dm-rpg-game\tests\experience_data_v5.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(raw_data, f, ensure_ascii=False, indent=2)
    print(f"数据已保存: {output_file}")

    return raw_data


if __name__ == "__main__":
    asyncio.run(run_experience())
