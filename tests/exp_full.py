# -*- coding: utf-8 -*-
"""
体验官脚本 - 完整版 v2
"""
import asyncio
import sys
import os
import logging
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logging.basicConfig(level=logging.INFO, format="%(name)s - %(levelname)s - %(message)s")

# Windows console encoding fix
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

from src import init_event_bus, init_game_master, EventType, Event
from src.character_creator import get_character_creator


class ExperienceCollector:
    def __init__(self):
        self.narratives = []
        self.api_errors = 0
        
    async def narrative_handler(self, event: Event):
        text = event.data.get("text", "")
        turn = event.data.get("turn", 0)
        self.narratives.append({"turn": turn, "text": text})
        print(f"\n[Narrative #{turn}] {text[:100]}...")
        
    async def error_handler(self, event: Event):
        self.api_errors += 1
        print(f"\n[API Error]")


async def main():
    start_time = datetime.now()
    
    print("=" * 60)
    print("体验官开始完整游戏体验")
    print("=" * 60)
    
    bus = await init_event_bus()
    master = await init_game_master()
    
    collector = ExperienceCollector()
    await bus.subscribe(EventType.NARRATIVE_OUTPUT, collector.narrative_handler, "exp_collector")
    await bus.subscribe(EventType.SUBNET_AGENT_ERROR, collector.error_handler, "exp_errors")
    
    print("\n[1] 创建角色")
    creator = get_character_creator()
    char = creator.create_from_selection("体验官", "human", "warrior")
    print(f"    {char.name} | {char.race_name} | {char.class_name}")
    
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
    
    test_inputs = [
        ("酒馆开场", "我走进酒馆，环顾四周"),
        ("镇中心", "去镇中心看看"),
        ("NPC对话", "和周围的人说话"),
        ("酒馆坐下", "去酒馆找个位置坐下"),
        ("意外操作", "我突然想跳舞"),
        ("街道探索", "离开酒馆，去街道上走走"),
        ("市场", "去市场逛逛"),
        ("森林冒险", "去森林冒险"),
    ]
    
    print(f"\n[2] 开始 {len(test_inputs)} 个测试回合")
    
    for i, (tag, inp) in enumerate(test_inputs):
        master.game_state["turn"] += 1
        turn = master.game_state["turn"]
        print(f"\n--- 回合 {turn}: {tag} ---")
        print(f"    输入: {inp}")
        
        prev_count = len(collector.narratives)
        await master.handle_player_message(inp)
        
        waited = 0
        while len(collector.narratives) == prev_count and waited < 45:
            await asyncio.sleep(3)
            waited += 3
            print(f"    [等待 API {waited}s]")
        
        if len(collector.narratives) == prev_count:
            print(f"    [API超时或无响应]")
        else:
            print(f"    [收到叙事]")
    
    end_time = datetime.now()
    duration = (end_time - start_time).total_seconds()
    
    print(f"\n[3] 清理...")
    await master.stop()
    await bus.stop()
    
    print(f"\n" + "=" * 60)
    print("体验完成!")
    print(f"总时长: {duration:.1f}秒")
    print(f"获取叙事数: {len(collector.narratives)}")
    print(f"API 错误: {collector.api_errors}")
    
    import json
    data = {
        "start": start_time.isoformat(),
        "end": end_time.isoformat(),
        "duration_seconds": duration,
        "narrative_count": len(collector.narratives),
        "narratives": collector.narratives,
        "api_errors": collector.api_errors,
        "final_turn": master.game_state.get("turn", 0),
        "location": master.game_state.get("location", "?"),
    }
    
    output_file = r"D:\ai-dm-rpg-game\tests\experience_data.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"数据已保存: {output_file}")
    
    return data


if __name__ == "__main__":
    result = asyncio.run(main())
