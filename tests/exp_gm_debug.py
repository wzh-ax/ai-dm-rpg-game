# -*- coding: utf-8 -*-
"""
体验官脚本 - GameMaster 调试版 v2
"""
import asyncio
import sys
import os
import logging
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 启用详细日志
logging.basicConfig(level=logging.DEBUG, format="%(name)s - %(levelname)s - %(message)s")

from src import init_event_bus, init_game_master, EventType, Event
from src.character_creator import get_character_creator


async def main():
    print("=" * 60)
    print("GameMaster 调试模式 v2")
    print("=" * 60)
    
    bus = await init_event_bus()
    print(f"EventBus: {bus}")
    
    master = await init_game_master()
    print(f"GameMaster: {master}")
    print(f"GameMaster subscriber_id: {master._subscriber_id}")
    print(f"GameMaster running: {master._running}")
    
    # 角色
    creator = get_character_creator()
    char = creator.create_from_selection("体验官", "human", "warrior")
    
    master.game_state["player_stats"] = {
        "hp": char.current_hp, "max_hp": char.max_hp,
        "ac": char.armor_class, "xp": char.xp,
        "level": char.level, "gold": char.gold,
        "inventory": char.inventory,
        "name": char.name, "race": char.race_name,
        "class": char.class_name,
    }
    master.game_state["turn"] = 0
    
    # 本地订阅 NARRATIVE_OUTPUT
    narratives = []
    async def local_narrative_handler(event: Event):
        narratives.append(event.data)
        print(f"[LOCAL] Narrative: {event.data.get('text', '')[:100]}...")
    
    await bus.subscribe(EventType.NARRATIVE_OUTPUT, local_narrative_handler, "local_test")
    
    print("\n发送测试输入...")
    master.game_state["turn"] = 1
    print("Calling handle_player_message...")
    await master.handle_player_message("我走进酒馆，环顾四周")
    print("handle_player_message returned")
    
    print("\n等待 8 秒 for LLM...")
    await asyncio.sleep(8)
    
    print(f"\n收到叙事数: {len(narratives)}")
    
    await master.stop()
    await bus.stop()


if __name__ == "__main__":
    asyncio.run(main())
