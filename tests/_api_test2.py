# -*- coding: utf-8 -*-
import sys
sys.path.insert(0, 'D:/ai-dm-rpg-game')
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

import asyncio
from src import init_event_bus, init_game_master
from src.character_creator import get_character_creator

async def test():
    print("=" * 60)
    print("Testing Game Experience Flow")
    print("=" * 60)
    
    bus = await init_event_bus()
    master = await init_game_master()
    
    creator = get_character_creator()
    char = creator.create_from_selection("体验官", "human", "warrior")
    print(f"\n角色: {char.name} | {char.race_name} | {char.class_name}")
    print(f"HP: {char.current_hp}/{char.max_hp} | AC: {char.armor_class}")
    
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
    
    print("\n--- Test 1: 酒馆开场 ---")
    result1 = await master.handle_player_message("我走进酒馆，环顾四周")
    print(f"Result1: {result1[:300] if result1 else 'NONE'}")
    
    print("\n--- Test 2: 探索镇中心 ---")
    result2 = await master.handle_player_message("去镇中心看看")
    print(f"Result2: {result2[:300] if result2 else 'NONE'}")
    
    print("\n--- Test 3: NPC对话 ---")
    result3 = await master.handle_player_message("和周围的人说话")
    print(f"Result3: {result3[:300] if result3 else 'NONE'}")
    
    print(f"\nFinal turn: {master.game_state.get('turn', 0)}")
    print(f"Final location: {master.game_state.get('location', '?')}")
    
    await master.stop()
    await bus.stop()
    print("\nDone!")

asyncio.run(test())
