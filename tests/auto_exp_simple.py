# -*- coding: utf-8 -*-
"""
体验官脚本 - 直接调用 GameMaster API
"""
import asyncio
import sys
import os
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src import init_event_bus, init_game_master, EventType, Event
from src.character_creator import get_character_creator


class NarrativeCollector:
    def __init__(self):
        self.narratives = []
        self.combat_events = []
        self.errors = []
        
    async def handler(self, event: Event):
        if event.type == EventType.NARRATIVE_OUTPUT:
            text = event.data.get("text", "")
            turn = event.data.get("turn", 0)
            self.narratives.append({"turn": turn, "text": text})
            print(f"[叙事 #{turn}] {text[:100]}...")
        elif event.type == EventType.COMBAT_EVENT:
            self.combat_events.append(event.data)
            print(f"[战斗] {event.data}")
        else:
            pass  # Ignore other event types


async def main():
    start_time = datetime.now()
    
    print("=" * 60)
    print("体验官开始执行...")
    print("=" * 60)
    
    # 初始化事件总线
    bus = await init_event_bus()
    
    # 初始化 GameMaster
    master = await init_game_master()
    
    # 收集器订阅叙事输出
    collector = NarrativeCollector()
    sub_id = "experience_collector"
    await bus.subscribe(EventType.NARRATIVE_OUTPUT, collector.handler, sub_id)
    
    # 角色创建
    print("\n[1] 创建角色")
    creator = get_character_creator()
    char = creator.create_from_selection("体验官", "human", "warrior")
    print(f"    {char.name} | {char.race_name} | {char.class_name}")
    print(f"    HP: {char.current_hp}/{char.max_hp} | AC: {char.armor_class}")
    
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
        master.game_state["turn"] += 1
        print(f"\n--- 回合 {master.game_state['turn']}: {inp} ---")
        
        # 发布玩家输入事件
        await master.handle_player_message(inp)
        
        # 等待事件处理 (LLM调用需要时间)
        await asyncio.sleep(4)
    
    end_time = datetime.now()
    duration = (end_time - start_time).total_seconds()
    
    print(f"\n[3] 清理...")
    await bus.unsubscribe(sub_id)
    await master.stop()
    await bus.stop()
    
    # 统计
    print(f"\n" + "=" * 60)
    print("体验完成!")
    print(f"总时长: {duration:.1f}秒")
    print(f"获取叙事数: {len(collector.narratives)}")
    print(f"战斗事件: {len(collector.combat_events)}")
    print(f"错误: {len(collector.errors)}")
    
    # 保存原始数据
    data = {
        "start": start_time.isoformat(),
        "end": end_time.isoformat(),
        "duration": duration,
        "turns": master.game_state.get("turn", 0),
        "location": master.game_state.get("location", "?"),
        "narratives": collector.narratives,
        "combat_events": collector.combat_events,
        "errors": collector.errors,
    }
    
    output_file = r"D:\ai-dm-rpg-game\tests\experience_raw.json"
    import json
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"数据已保存: {output_file}")
    
    return data


if __name__ == "__main__":
    asyncio.run(main())
