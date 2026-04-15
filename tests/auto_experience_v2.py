# -*- coding: utf-8 -*-
"""
体验官自动体验脚本 v2
通过 Event Bus 正确订阅叙事输出
"""
import asyncio
import sys
import os
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src import init_event_bus, init_game_master, EventType, Event
from src.character_creator import get_character_creator


class ExperienceCapture:
    def __init__(self):
        self.narratives = []
        self.combat_events = []
        self.errors = []
        
    async def narrative_handler(self, event: Event):
        text = event.data.get("text", "")
        turn = event.data.get("turn", 0)
        if text:
            self.narratives.append({"turn": turn, "text": text})
            print(f"\n📜 [Turn {turn}] {text[:150]}...")
            
    async def combat_handler(self, event: Event):
        self.combat_events.append(event.data)
        print(f"\n⚔️  战斗事件: {event.data}")
    
    async def error_handler(self, event: Event):
        self.errors.append(event.data)
        print(f"\n❌ 错误: {event.data}")


async def wait_for_narrative_with_timeout(bus, timeout=30):
    """等待叙事输出，带超时"""
    narrative = None
    async def get_first(event: Event):
        nonlocal narrative
        narrative = event.data.get("text", "")
    await bus.subscribe(EventType.NARRATIVE_OUTPUT, get_first, "experience_capture")
    await asyncio.sleep(timeout)
    await bus.unsubscribe("experience_capture")
    return narrative


async def run_experience():
    start_time = datetime.now()
    
    print("=" * 60)
    print("体验官开始执行游戏体验...")
    print("=" * 60)
    
    # 初始化
    bus = await init_event_bus()
    master = await init_game_master()
    
    capture = ExperienceCapture()
    await bus.subscribe(EventType.NARRATIVE_OUTPUT, capture.narrative_handler, "exp_narrative")
    await bus.subscribe(EventType.COMBAT_EVENT, capture.combat_handler, "exp_combat")
    
    # 角色创建
    print("\n[阶段1] 角色创建")
    creator = get_character_creator()
    char = creator.create_from_selection("体验官", "human", "warrior")
    print(f"角色: {char.name} | {char.race_name} | {char.class_name}")
    
    master.game_state["player_stats"] = {
        "hp": char.current_hp,
        "max_hp": char.max_hp,
        "ac": char.armor_class,
        "xp": char.xp,
        "level": char.level,
        "gold": char.gold,
        "inventory": char.inventory,
        "name": char.name,
        "race": char.race_name,
        "class": char.class_name,
    }
    master.game_state["turn"] = 0
    master.game_state["location"] = "月叶镇"
    
    # 测试序列
    test_cases = [
        ("酒馆开场", "我走进酒馆，环顾四周"),
        ("探索镇中心", "去镇中心看看"),
        ("NPC对话", "和周围的人说话"),
        ("酒馆深入", "去酒馆找个位置坐下，听听有什么消息"),
        ("意外操作", "我突然想跳舞，在酒馆中央跳了起来"),
        ("离开探索", "离开酒馆，去外面的街道走走"),
        ("市场区域", "去市场逛逛"),
        ("森林冒险", "去镇子外面的森林冒险"),
        ("道具使用", "使用一个治疗药水"),
    ]
    
    for i, (tag, action) in enumerate(test_cases):
        print(f"\n[测试{i+1}] {tag}: {action}")
        master.game_state["turn"] += 1
        await master.handle_player_message(action)
        await asyncio.sleep(3)  # 等待 LLM 处理
        
    end_time = datetime.now()
    duration = (end_time - start_time).total_seconds()
    
    await master.stop()
    await bus.stop()
    
    return {
        "start": start_time.isoformat(),
        "end": end_time.isoformat(),
        "duration": duration,
        "narratives": capture.narratives,
        "combat_events": capture.combat_events,
        "errors": capture.errors,
        "turns": master.game_state.get("turn", 0),
        "location": master.game_state.get("location", "?"),
        "final_stats": master.game_state.get("player_stats", {}),
    }


if __name__ == "__main__":
    result = asyncio.run(run_experience())
    print("\n" + "=" * 60)
    print("体验完成!")
    print(f"时长: {result['duration']:.1f}秒")
    print(f"叙事数量: {len(result['narratives'])}")
    print(f"战斗事件: {len(result['combat_events'])}")
    print(f"错误: {len(result['errors'])}")
