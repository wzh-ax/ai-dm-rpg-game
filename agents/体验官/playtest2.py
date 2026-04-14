import asyncio
import sys
import time
import io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

sys.path.insert(0, '.')
from src import init_event_bus, init_game_master

async def playtest():
    start = time.time()
    bus = await init_event_bus()
    master = await init_game_master()
    
    print('=== startup ===')
    print('turn:', master.game_state.get('turn', 0))
    
    from src.character_creator import get_character_creator
    creator = get_character_creator()
    char = creator.create_from_selection('tester', 'human', 'warrior')
    print('char:', char.name, 'hp:', char.current_hp, '/', char.max_hp, 'ac:', char.armor_class)
    
    master.game_state['player_stats'] = {
        'hp': char.current_hp, 'max_hp': char.max_hp,
        'ac': char.armor_class, 'xp': char.xp,
        'level': char.level, 'gold': char.gold,
        'inventory': char.inventory,
        'name': char.name, 'race': char.race_name,
        'class': char.class_name,
    }
    master.game_state['turn'] = 0
    master.game_state['location'] = 'moonleaf_town'
    
    print()
    print('=== turn 1: explore ===')
    r1 = await master.handle_player_message('look around the town')
    print('response len:', len(r1) if r1 else 0)
    print('response:', r1[:600] if r1 else '(none)')
    
    print()
    print('=== turn 2: talk ===')
    r2 = await master.handle_player_message('talk to someone nearby')
    print('response len:', len(r2) if r2 else 0)
    print('response:', r2[:600] if r2 else '(none)')
    
    print()
    print('=== turn 3: unexpected action ===')
    r3 = await master.handle_player_message('sing a song to a stranger')
    print('response len:', len(r3) if r3 else 0)
    print('response:', r3[:600] if r3 else '(none)')
    
    print()
    print('=== turn 4: status ===')
    r4 = await master.handle_player_message('status')
    print('response len:', len(r4) if r4 else 0)
    print('response:', r4[:600] if r4 else '(none)')
    
    elapsed = time.time() - start
    
    print()
    print('=== summary ===')
    print('elapsed:', elapsed, 'sec')
    print('total turns:', master.game_state.get('turn', '?'))
    print('location:', master.game_state.get('location', '?'))
    
    await master.stop()
    await bus.stop()

asyncio.run(playtest())
