# -*- coding: utf-8 -*-
"""
诊断测试 v2 - 直接使用 GameMaster 的 event_bus
"""
import asyncio
import sys
import os
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src import init_event_bus, init_game_master
from src.event_bus import EventType, Event
from src.character_creator import get_character_creator

EVENT_LOG = []

def log_event(tag, msg):
    ts = datetime.now().strftime("%H:%M:%S.%f")[:-3]
    line = f"[{ts}] [{tag}] {msg}"
    print(line)
    EVENT_LOG.append(line)

async def main():
    print("=== 诊断测试 v2 开始 ===", flush=True)
    
    bus = await init_event_bus()
    master = await init_game_master()
    
    # 直接订阅 master.event_bus（GameMaster 使用的同一个 bus）
    received_events = []
    
    async def catch_all(event: Event):
        received_events.append(event.type)
        log_event("EVENT", f"Got {event.type.value}")
    
    for et in EventType:
        await bus.subscribe(et, catch_all, f"catchall_{et.value}")
    
    log_event("SETUP", f"Subscribed to {len(EventType)} event types on bus id {id(bus)}")
    log_event("SETUP", f"Master bus id {id(master.event_bus)}")
    log_event("SETUP", f"Same bus? {bus is master.event_bus}")
    
    # 创建角色
    creator = get_character_creator()
    char = creator.create_from_selection("诊断测试", "human", "warrior")
    
    master.game_state["player_stats"] = {
        "hp": char.current_hp, "max_hp": char.max_hp,
        "ac": char.armor_class, "xp": char.xp,
        "level": char.level, "gold": char.gold,
        "inventory": char.inventory,
        "name": char.name, "race": char.race_name,
        "class": char.class_name,
    }
    master.game_state["turn"] = 0
    master.game_state["location"] = "醉梦酒馆"
    
    log_event("TEST", "Sending player message...")
    await master.handle_player_message("你好")
    log_event("TEST", f"handle_player_message done, turn={master.game_state['turn']}")
    
    log_event("TEST", "Waiting 15 seconds...")
    await asyncio.sleep(15)
    
    log_event("TEST", f"Final turn: {master.game_state['turn']}")
    log_event("TEST", f"Events received: {[e.value for e in received_events]}")
    
    await master.stop()
    await bus.stop()
    
    log_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "diagnostic_log.txt")
    with open(log_path, "w", encoding="utf-8") as f:
        f.write("\n".join(EVENT_LOG))
    print(f"日志: {log_path}")

if __name__ == "__main__":
    asyncio.run(main())
