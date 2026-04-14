import asyncio
import sys
sys.path.insert(0, 'C:/Users/15901/.openclaw/workspace/ai-dm-rpg')

async def simple_test():
    from src import init_event_bus, init_game_master
    from src.event_bus import EventType, Event
    
    bus = await init_event_bus()
    master = await init_game_master()
    
    results = []
    
    async def on_narrative(event: Event):
        text = event.data.get("text", "")
        print(f"[CALLBACK] Received narrative: {len(text)} chars")
        results.append(text)
    
    await bus.subscribe(EventType.NARRATIVE_OUTPUT, on_narrative, "simple_test")
    
    print("Sending first message...")
    await master.handle_player_message('去镇中心看看')
    await asyncio.sleep(3)
    print(f"After first message: {len(results)} outputs")
    
    if results:
        print(f"First output: {results[-1][:200]}")
    
    await master.stop()
    await bus.stop()

asyncio.run(simple_test())
