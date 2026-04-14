import sys
sys.path.insert(0, '.')
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

import asyncio
from src import init_event_bus, init_game_master, EventType, Event
from src.character_creator import get_character_creator

async def test():
    bus = await init_event_bus()
    master = await init_game_master()
    await master.initialize()
    
    creator = get_character_creator()
    char = creator.create_from_selection('test', 'human', 'warrior')
    
    master.game_state['player_stats'] = {
        'hp': char.current_hp, 'max_hp': char.max_hp,
        'ac': char.armor_class, 'xp': char.xp,
        'level': char.level, 'gold': char.gold,
        'inventory': char.inventory,
        'name': char.name, 'race': char.race_name, 'class': char.class_name,
    }
    master.game_state['turn'] = 0
    master.game_state['location'] = 'moonleaf_town'
    master.game_state['quest_stage'] = 'not_started'
    master.game_state['quest_active'] = False
    
    # 订阅叙事输出
    narrative_ready = asyncio.Event()
    latest_narrative = {"text": "", "turn": 0, "mode": ""}
    
    async def output_handler(event: Event):
        latest_narrative["text"] = event.data.get("text", "")
        latest_narrative["turn"] = event.data.get("turn", "?")
        latest_narrative["mode"] = event.data.get("mode", "?")
        narrative_ready.set()
    
    await bus.subscribe(EventType.NARRATIVE_OUTPUT, output_handler, "test_output")
    
    async def do_action(action: str):
        latest_narrative["text"] = ""
        narrative_ready.clear()
        await master.handle_player_message(action)
        try:
            await asyncio.wait_for(narrative_ready.wait(), timeout=30.0)
        except asyncio.TimeoutError:
            print(f"[超时] {action}")
            return None
        return latest_narrative["text"]
    
    # Test
    r = await do_action('test action')
    print(f"Result: {repr(r[:200] if r else 'NONE')}")
    
    await master.stop()
    await bus.stop()

asyncio.run(test())
