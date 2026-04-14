import asyncio
import sys
import time
sys.path.insert(0, '.')
sys.stdout.reconfigure(encoding='utf-8')

from src import init_event_bus, init_game_master

async def quick_playtest():
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
    
    print('=== 开场场景 ===')
    scene = await master._generate_scene('月叶镇')
    print(f'开场场景: {scene[:300] if scene else "(无)"}')
    
    print('=== 探索开始 ===')
    
    # 探索场景
    actions = [
        '去镇中心看看',
        '去酒馆坐坐',
        '和酒馆里的人说话',
        '查看我的状态',
    ]
    
    for i, action in enumerate(actions):
        print(f'\n回合 {master.game_state["turn"] + 1}: {action}')
        result = await master.handle_player_message(action)
        if result:
            lines = result.split('\n')
            narrative = [l for l in lines if l and not l.startswith('==') and not l.startswith('📊') and not l.startswith('---')]
            if narrative:
                print(f'叙事: {" ".join(narrative[:3])[:200]}')
    
    print(f'\n=== 体验结束 ===')
    print(f'当前回合: {master.game_state["turn"]}')
    print(f'当前位置: {master.game_state.get("location", "?")}')
    print(f'HP: {master.game_state["player_stats"]["hp"]}/{master.game_state["player_stats"]["max_hp"]}')
    
    await master.stop()
    await bus.stop()

t0 = time.time()
asyncio.run(quick_playtest())
print(f'总耗时: {time.time()-t0:.1f}s')
