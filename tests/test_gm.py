# -*- coding: utf-8 -*-
import sys
sys.path.insert(0, 'D:/ai-dm-rpg-game')
from src import init_game_master, CharacterCreator
import asyncio

async def test():
    gm = await init_game_master()
    creator = CharacterCreator()
    char = creator.create_from_selection('test', 'human', 'warrior')
    gm.game_state['player_stats'] = char.to_player_stats()
    
    result = await gm.handle_player_message('我走出酒馆')
    print(f'Result type: {type(result)}')
    print(f'Result: {repr(result)}')
    
    # Check game_state keys
    print(f'game_state keys: {list(gm.game_state.keys())}')
    
    await gm.stop()

asyncio.run(test())
