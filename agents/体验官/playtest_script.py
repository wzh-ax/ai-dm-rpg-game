import asyncio
import sys
import time
sys.path.insert(0, '.')

start = time.time()
results = []

def log(msg):
    results.append(f'[{int(time.time()-start)}s] {msg}')
    print(f'[{int(time.time()-start)}s] {msg}')

async def play():
    from src import init_event_bus, init_game_master
    
    log('=== 游戏启动 ===')
    
    bus = await init_event_bus()
    master = await init_game_master()
    
    # 创建角色
    from src.character_creator import get_character_creator
    creator = get_character_creator()
    char = creator.create_from_selection('体验官', 'human', 'warrior')
    log(f'角色创建: {char.name} ({char.race_name}/{char.class_name})')
    
    # 初始化状态
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
    log('=== 开场场景 ===')
    scene = await master._generate_scene('月叶镇')
    log(f'场景: {scene[:200] if scene else "(空)"}')
    
    # 回合1
    log('=== 回合1: 探索镇中心 ===')
    r1 = await master.handle_player_message('去镇中心看看')
    log(f'行动1: {r1[:300] if r1 else "(空)"}')
    
    # 回合2
    log('=== 回合2: 与镇民对话 ===')
    r2 = await master.handle_player_message('和周围的镇民说话')
    log(f'行动2: {r2[:300] if r2 else "(空)"}')
    
    # 回合3
    log('=== 回合3: 去酒馆 ===')
    r3 = await master.handle_player_message('去镇上的酒馆')
    log(f'行动3: {r3[:300] if r3 else "(空)"}')
    
    # 回合4
    log('=== 回合4: 酒馆聊天 ===')
    r4 = await master.handle_player_message('和酒馆里的人聊天')
    log(f'行动4: {r4[:300] if r4 else "(空)"}')
    
    # 回合5 - 意外操作
    log('=== 回合5: 砸酒杯 ===')
    r5 = await master.handle_player_message('我想要把酒杯砸在地上引发骚动')
    log(f'行动5: {r5[:300] if r5 else "(空)"}')
    
    # 回合6 - 询问任务
    log('=== 回合6: 询问任务 ===')
    r6 = await master.handle_player_message('这里有什么委托或任务吗')
    log(f'行动6: {r6[:300] if r6 else "(空)"}')
    
    # 回合7 - 查看状态
    log('=== 回合7: 查看状态 ===')
    r7 = await master.handle_player_message('查看我的状态')
    log(f'行动7: {r7[:300] if r7 else "(空)"}')
    
    # 回合8 - 离开酒馆
    log('=== 回合8: 离开酒馆 ===')
    r8 = await master.handle_player_message('离开酒馆，去广场看看')
    log(f'行动8: {r8[:300] if r8 else "(空)"}')
    
    # 回合9 - 去商店
    log('=== 回合9: 去商店 ===')
    r9 = await master.handle_player_message('我想去商店看看')
    log(f'行动9: {r9[:300] if r9 else "(空)"}')
    
    # 回合10 - 购买
    log('=== 回合10: 购买物品 ===')
    r10 = await master.handle_player_message('购买一个治疗药水')
    log(f'行动10: {r10[:300] if r10 else "(空)"}')
    
    log('=== 总结 ===')
    log(f'最终回合: {master.game_state["turn"]}')
    log(f'位置: {master.game_state.get("location", "?")}')
    stats = master.game_state["player_stats"]
    log(f'HP: {stats["hp"]}/{stats["max_hp"]} | 金币: {stats["gold"]} | 等级: {stats["level"]}')
    
    await master.stop()
    await bus.stop()
    
    return results

if __name__ == '__main__':
    asyncio.run(play())
