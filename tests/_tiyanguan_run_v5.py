# -*- coding: utf-8 -*-
"""
体验官 V1_0_5 体验脚本 - 正确订阅 NARRATIVE_OUTPUT 事件
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
                # 安全打印（移除emoji）
                safe = text.encode("utf-8", errors="replace").decode("utf-8", errors="replace")
                print(f"[叙事 #{turn}] {safe[:100]}...")
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
    print("体验官 V1_0_5 开始执行游戏体验...")
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
    char = creator.create_from_selection("冒险者", "human", "warrior")
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
        ("NPC对话1", "和酒馆里的人交谈"),
        ("酒保对话", "向酒保打听镇子里的情况"),
        ("镇中心探索", "离开酒馆，去镇中心逛逛"),
        ("镇中心NPC", "在镇中心找人聊聊"),
        ("意外-跳舞", "我突然在镇中心跳舞"),
        ("意外-大喊", "我对天空大喊一声"),
        ("市场探索", "去市场看看有什么商品"),
        ("商人对话", "向商人打听消息"),
        ("森林冒险", "去镇子外面的森林冒险"),
        ("森林深处", "在森林里四处搜索"),
        ("系统-状态", "查看状态"),
        ("返回镇子", "返回月叶镇"),
        ("旅店休息", "找个旅店休息一下"),
        ("重要NPC", "找镇子里看起来最重要的人深入聊聊"),
        ("深入对话", "询问关于这片土地的传说"),
    ]

    print(f"\n[阶段2] 开始 {len(test_cases)} 个探索回合")
    for i, (tag, action) in enumerate(test_cases):
        turn_num = master.game_state.get("turn", 0) + 1
        print(f"\n--- 回合 {turn_num}: {tag} ---")
        print(f"输入: {action}")
        await safe_handle_with_retry(master, action)
        await asyncio.sleep(4)  # 等待 LLM 处理

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
                          if any(kw in n["text"] for kw in ["战斗", "攻击", "敌人", "战斗"]))
    npc_mentions = sum(1 for n in collector.narratives
                       if any(kw in n["text"] for kw in ["说", "回答", "对话", "NPC", "老板", "商人", "冒险者"]))

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
    }


if __name__ == "__main__":
    result = asyncio.run(run_experience())
