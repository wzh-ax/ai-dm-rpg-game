import asyncio
import sys
sys.path.insert(0, '.')
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

from src import init_event_bus, init_game_master
from src.character_creator import get_character_creator

async def test():
    bus = await init_event_bus()
    master = await init_game_master()
    creator = get_character_creator()
    char = creator.create_from_selection('Test', 'human', 'warrior')
    master.game_state['player_stats'] = {
        'hp': char.current_hp, 'max_hp': char.max_hp,
        'ac': char.armor_class, 'xp': char.xp,
        'level': char.level, 'gold': char.gold,
        'inventory': char.inventory,
        'name': char.name, 'race': char.race_name,
        'class': char.class_name,
    }
    master.game_state['turn'] = 0
    master.game_state['location'] = '月叶镇'
    
    print('Testing handle_player_message (awaited)...')
    result = await master.handle_player_message('去镇中心看看')
    if result:
        print('Result length:', len(result))
        print('First 300 chars:', result[:300])
    else:
        print('Result is empty or None')
    await master.stop()
    await bus.stop()

asyncio.run(test())
