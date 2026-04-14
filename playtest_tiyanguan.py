import asyncio
import sys
import time
sys.path.insert(0, '.')
from src import init_event_bus, init_game_master
from src.event_bus import EventType, Event

async def playtest():
    start_time = time.time()
    bus = await init_event_bus()
    master = await init_game_master()
    
    results = []
    all_narratives = []
    
    async def on_narrative(event: Event):
        text = event.data.get("text", "")
        all_narratives.append(text)
    
    await bus.subscribe(EventType.NARRATIVE_OUTPUT, on_narrative, "tiyanguan_listener")
    
    results.append('=== 启动游戏 ===')
    
    from src.character_creator import get_character_creator
    creator = get_character_creator()
    char = creator.create_from_selection('体验官', 'human', 'warrior')
    results.append(f'创建角色: {char.name}')
    
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
    
    results.append('=== 教程阶段 ===')
    from src.tutorial_system import get_tutorial_system, TutorialMode
    tutorial = get_tutorial_system()
    tutorial.set_mode(TutorialMode.FULL)
    
    results.append('[跳过世界观介绍]')
    results.append('[跳过操作说明]')
    
    char_dict = {
        'name': char.name, 'race': char.race_name, 'class': char.class_name,
        'level': char.level, 'hp': char.current_hp, 'max_hp': char.max_hp,
        'ac': char.armor_class, 'xp': char.xp, 'gold': char.gold
    }
    welcome = await tutorial.generate_welcome_narrative(char_dict)
    results.append(f'欢迎叙事: {welcome[:200]}...')
    
    results.append('=== 开场场景 ===')
    scene = await master._generate_scene('月叶镇')
    results.append(f'场景: {scene[:300] if scene else "(无)"}')
    
    results.append('=== 探索开始 ===')
    
    actions = [
        '去镇中心看看',
        '和周围的人说话',
        '去酒馆',
        '查看状态',
        '去铁匠铺看看',
        '询问最近的麻烦',
    ]
    
    for i, action in enumerate(actions):
        results.append(f'\n回合 {master.game_state["turn"] + 1}: {action}')
        await master.handle_player_message(action)
        await asyncio.sleep(3)
        results.append(f'收到 {len(all_narratives)} 条叙事')
        for n in all_narratives:
            results.append(f'叙事[{len(n)}字符]: {n[:200]}')
        all_narratives.clear()  # 清空准备下一轮
    
    elapsed = time.time() - start_time
    
    results.append(f'\n=== 快速体验总结 ===')
    results.append(f'当前回合: {master.game_state["turn"]}')
    results.append(f'当前位置: {master.game_state.get("location", "?")}')
    results.append(f'HP: {master.game_state["player_stats"]["hp"]}/{master.game_state["player_stats"]["max_hp"]}')
    results.append(f'耗时: {elapsed:.1f}秒')
    
    await master.stop()
    await bus.stop()
    
    return '\n'.join(results)

if __name__ == '__main__':
    result = asyncio.run(playtest())
    with open('C:/Users/15901/.openclaw/workspace/ai-dm-rpg/tiyanguan_result.txt', 'w', encoding='utf-8') as f:
        f.write(result)
    print('Done - result written to tiyanguan_result.txt')
