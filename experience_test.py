import asyncio
import sys
import io
sys.path.insert(0, '.')
from src import init_event_bus, init_game_master

# Fix stdout encoding for Windows
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

async def playtest():
    bus = await init_event_bus()
    master = await init_game_master()
    
    print('=== 启动游戏 ===')
    
    # 角色创建
    from src.character_creator import get_character_creator
    creator = get_character_creator()
    char = creator.create_from_selection('体验官', 'human', 'warrior')
    print(f'创建角色: {char.name}')
    
    # 初始化玩家状态
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
    scene = await master._generate_scene('月叶镇')
    print(scene[:500] if scene else '(无)')
    
    # 探索1: 镇中心
    print('\n=== 探索1: 镇中心 ===')
    result1 = await master.handle_player_message('去镇中心看看')
    print(result1[:800] if result1 else '(无)')
    
    # 探索2: 和人说话
    print('\n=== 探索2: 和镇民说话 ===')
    result2 = await master.handle_player_message('和周围的人说话')
    print(result2[:800] if result2 else '(无)')
    
    # 探索3: 去酒馆
    print('\n=== 探索3: 去酒馆 ===')
    result3 = await master.handle_player_message('去酒馆')
    print(result3[:800] if result3 else '(无)')
    
    # 探索4: 与酒馆NPC对话
    print('\n=== 探索4: 与酒馆老板对话 ===')
    result4 = await master.handle_player_message('询问老板最近有什么新鲜事')
    print(result4[:800] if result4 else '(无)')
    
    # 探索5: 离开酒馆
    print('\n=== 探索5: 离开酒馆 ===')
    result5 = await master.handle_player_message('离开酒馆')
    print(result5[:800] if result5 else '(无)')
    
    print('\n=== 状态检查 ===')
    print(f'回合: {master.game_state["turn"]}')
    print(f'位置: {master.game_state.get("location", "?")}')
    print(f'HP: {master.game_state["player_stats"]["hp"]}/{master.game_state["player_stats"]["max_hp"]}')
    
    await master.stop()
    await bus.stop()

asyncio.run(playtest())
