import asyncio
import sys
import time
sys.path.insert(0, '.')
from src import init_event_bus, init_game_master

async def playtest():
    bus = await init_event_bus()
    master = await init_game_master()
    start_time = time.time()
    
    print('=== 游戏启动 ===')
    
    # 角色创建
    from src.character_creator import get_character_creator
    creator = get_character_creator()
    char = creator.create_from_selection('冒险者阿轩', 'human', 'warrior')
    print(f'创建角色: {char.name}, HP:{char.current_hp}, AC:{char.armor_class}')
    
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
    
    # 开场场景
    print('=== 开场场景 ===')
    scene1 = await master.handle_player_message('环顾四周')
    print(scene1[:500] if scene1 else '(无响应)')
    
    # 探索镇中心
    print('=== 探索镇中心 ===')
    scene2 = await master.handle_player_message('去镇中心')
    print(scene2[:500] if scene2 else '(无响应)')
    
    # 与NPC对话
    print('=== NPC对话测试 ===')
    scene3 = await master.handle_player_message('和一个看起来和善的镇民交谈')
    print(scene3[:500] if scene3 else '(无响应)')
    
    # 去酒馆
    print('=== 酒馆 ===')
    scene4 = await master.handle_player_message('去酒馆坐坐')
    print(scene4[:500] if scene4 else '(无响应)')
    
    # 酒馆对话
    print('=== 酒馆对话 ===')
    scene5 = await master.handle_player_message('向酒保打听最近有什么新鲜事')
    print(scene5[:500] if scene5 else '(无响应)')
    
    elapsed = time.time() - start_time
    print(f'=== 用时: {elapsed:.1f}秒 ===')
    
    await master.stop()
    await bus.stop()

asyncio.run(playtest())
