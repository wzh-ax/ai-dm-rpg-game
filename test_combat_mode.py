"""Test combat mode transition"""
import asyncio
from src import init_event_bus, init_game_master, EventType, Event

async def test():
    bus = await init_event_bus()
    master = await init_game_master()
    
    outputs = []
    async def collector(event):
        outputs.append(event.data)
        print(f"[MODE={event.data.get('mode', '?')}] {event.data.get('text', '')[:80]}...")
    
    await bus.subscribe(EventType.NARRATIVE_OUTPUT, collector, 'test')
    
    # Exploration mode
    print("=== Exploration ===")
    await master.handle_player_message("我走进酒馆")
    await asyncio.sleep(0.5)
    
    # Trigger combat
    print()
    print("=== Combat Trigger ===")
    await master.handle_player_message("我和酒馆里的怪物战斗")
    await asyncio.sleep(0.5)
    
    # Combat action
    print()
    print("=== Combat Action ===")
    await master.handle_player_message("我攻击敌人")
    await asyncio.sleep(0.5)
    
    print()
    print(f"Final mode: {master.mode.value}")
    await master.stop()
    await bus.stop()

if __name__ == "__main__":
    asyncio.run(test())
