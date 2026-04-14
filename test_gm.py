# -*- coding: utf-8 -*-
import asyncio
import sys
sys.path.insert(0, '.')
from src import init_event_bus, init_game_master

async def test():
    bus = await init_event_bus()
    master = await init_game_master()
    
    # Set up game state properly
    from src.character_creator import get_character_creator
    creator = get_character_creator()
    char = creator.create_from_selection('TestPlayer', 'human', 'warrior')
    
    master.game_state['player_stats'] = {
        'hp': char.current_hp, 'max_hp': char.max_hp,
        'ac': char.armor_class, 'xp': char.xp,
        'level': char.level, 'gold': char.gold,
        'inventory': char.inventory,
        'name': char.name, 'race': char.race_name,
        'class': char.class_name,
    }
    master.game_state['turn'] = 0
    master.game_state['location'] = 'Moonleaf Town'
    master.game_state['current_scene'] = None
    master.game_state['scene_context'] = {}
    master.game_state['narrative_history'] = []
    master.game_state['pending_tasks'] = []
    
    print('Game state set up')
    
    result = await master.handle_player_message('Hello')
    print(f'Result type: {type(result)}')
    print(f'Result: {result}')
    
    await master.stop()
    await bus.stop()

if __name__ == '__main__':
    asyncio.run(test())
