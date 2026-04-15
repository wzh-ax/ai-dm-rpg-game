# -*- coding: utf-8 -*-
"""
体验官脚本 - 使用 MainDM (简化模式)
"""
import asyncio
import sys
import os
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src import init_event_bus, init_main_dm, EventType, Event
from src.character_creator import get_character_creator


class ExperienceCapture:
    def __init__(self):
        self.narratives = []
        self.combat_events = []
        self.errors = []
        self.subscription_id = "exp_capture"
        
    async def handle_narrative(self, event: Event):
        text = event.data.get("text", "")
        turn = event.data.get("turn", 0)
        self.narratives.append({"turn": turn, "text": text})
        print(f"\n[Narrative #{turn}] {text[:120]}...")
        
    async def handle_combat(self, event: Event):
        self.combat_events.append(event.data)
        print(f"\n[Combat] {event.data}")
        
    async def handle_error(self, event: Event):
        self.errors.append(event.data)
        print(f"\n[Error] {event.data}")


async def main():
    start_time = datetime.now()
    
    print("=" * 60)
    print("体验官开始执行 (MainDM模式)")
    print("=" * 60)
    
    # 初始化
    bus = await init_event_bus()
    dm = await init_main_dm()
    
    # 订阅叙事输出
    capture = ExperienceCapture()
    await bus.subscribe(EventType.NARRATIVE_OUTPUT, capture.handle_narrative, capture.subscription_id)
    
    # 角色创建
    print("\n[1] 创建角色")
    creator = get_character_creator()
    char = creator.create_from_selection("体验官", "human", "warrior")
    print(f"    {char.name} | {char.race_name} | {char.class_name}")
    print(f"    HP: {char.current_hp}/{char.max_hp} | AC: {char.armor_class}")
    
    # 初始化游戏状态
    dm.game_state["player_stats"] = {
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
    dm.game_state["turn"] = 0
    dm.game_state["location"] = "月叶镇"
    
    # 测试序列
    test_inputs = [
        "我走进酒馆，环顾四周",
        "去镇中心看看",
        "和周围的人说话",
        "去酒馆找个位置坐下",
        "我突然想跳舞",
        "离开酒馆，去街道上走走",
        "去市场逛逛",
        "去森林冒险",
    ]
    
    print(f"\n[2] 开始 {len(test_inputs)} 个测试回合")
    for i, inp in enumerate(test_inputs):
        dm.game_state["turn"] += 1
        print(f"\n--- 回合 {dm.game_state['turn']}: {inp} ---")
        
        await dm.handle_player_message(inp)
        
        # 等待事件处理
        await asyncio.sleep(2)
    
    end_time = datetime.now()
    duration = (end_time - start_time).total_seconds()
    
    print(f"\n[3] 清理...")
    await bus.unsubscribe(EventType.NARRATIVE_OUTPUT, capture.subscription_id)
    await dm.stop()
    await bus.stop()
    
    # 统计
    print(f"\n" + "=" * 60)
    print("体验完成!")
    print(f"总时长: {duration:.1f}秒")
    print(f"获取叙事数: {len(capture.narratives)}")
    print(f"战斗事件: {len(capture.combat_events)}")
    print(f"错误: {len(capture.errors)}")
    
    return {
        "start": start_time.isoformat(),
        "end": end_time.isoformat(),
        "duration": duration,
        "turns": dm.game_state.get("turn", 0),
        "narratives": capture.narratives,
        "combat_events": capture.combat_events,
        "errors": capture.errors,
    }


if __name__ == "__main__":
    result = asyncio.run(main())
