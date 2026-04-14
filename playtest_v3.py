import asyncio
import sys
import time
sys.path.insert(0, '.')
from src import init_event_bus, init_game_master
from src.event_bus import Event, EventType

async def main():
    bus = await init_event_bus()
    master = await init_game_master()
    
    log = []
    start = time.time()
    narrative_received = asyncio.Event()
    last_narrative = ['']
    
    async def catch_narrative(event: Event):
        if event.type == EventType.NARRATIVE_OUTPUT:
            last_narrative[0] = event.data.get('text', '')
            narrative_received.set()
    
    await bus.subscribe(EventType.NARRATIVE_OUTPUT, catch_narrative, 'test_listener')
    
    # 创建角色
    from src.character_creator import get_character_creator
    creator = get_character_creator()
    char = creator.create_from_selection('体验官', 'human', 'warrior')
    log.append(f'[角色创建] {char.name}, {char.race_name}, {char.class_name}')
    
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
    log.append('=== 开场场景 ===')
    scene = await master._generate_scene('月叶镇')
    log.append(scene[:300] if scene else '(无)')
    
    # 更多探索序列
    actions = [
        '去镇中心看看',
        '和周围的人说话',
        '去酒馆',
        '酒馆里和酒馆老板说话',
        '酒馆里找一个冒险者聊聊',
        '酒馆里有没有什么任务可以接',
        '我想喝酒',
        '查看状态',
        '查看背包',
        '去酒馆外面看看有没有怪物',
        '查看任务',
    ]
    
    for action in actions:
        log.append(f'\n>>> {action}')
        narrative_received.clear()
        last_narrative[0] = ''
        
        await bus.publish(Event(
            type=EventType.PLAYER_INPUT,
            data={'text': action},
            source='test'
        ))
        
        try:
            await asyncio.wait_for(narrative_received.wait(), timeout=30)
        except asyncio.TimeoutError:
            log.append('[超时，无响应]')
            continue
        
        narrative = last_narrative[0]
        if narrative:
            lines = narrative.split('\n')
            meaningful = [l.strip() for l in lines if l.strip() and not l.startswith('==')][:5]
            for n in meaningful[:3]:
                log.append(n[:200])
    
    elapsed = time.time() - start
    log.append(f'\n[耗时] {elapsed:.1f}s, [回合] {master.game_state["turn"]}')
    
    await master.stop()
    await bus.stop()
    
    return '\n'.join(log)

result = asyncio.run(main())
with open('playtest_result.txt', 'w', encoding='utf-8') as f:
    f.write(result)
print('Done')
