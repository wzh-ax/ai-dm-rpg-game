import asyncio
import sys
sys.path.insert(0, '.')
from src import init_event_bus, init_game_master, Event, EventType

async def playtest():
    bus = await init_event_bus()
    master = await init_game_master()
    
    # 收集叙事输出的队列
    narrative_queue = asyncio.Queue()
    
    async def on_narrative(event: Event):
        text = event.data.get("text", "")
        if text:
            await narrative_queue.put(text)
    
    # 订阅叙事输出
    await bus.subscribe(EventType.NARRATIVE_OUTPUT, on_narrative, "playtest")
    
    print('=== 启动游戏 ===')
    
    # 角色创建
    from src.character_creator import get_character_creator
    creator = get_character_creator()
    char = creator.create_from_selection('体验官', 'human', 'warrior')
    print(f'创建角色: {char.name}')
    
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
    
    # 教程阶段 - 使用 skip 模式快速跳过
    print('=== 教程阶段 ===')
    from src.tutorial_system import get_tutorial_system, TutorialMode
    tutorial = get_tutorial_system()
    tutorial.set_mode(TutorialMode.SKIP)
    welcome = tutorial.start_tutorial(char.name)
    print(f'欢迎叙事[前200字]: {welcome[:200]}')
    
    # 开场场景
    print('\n=== 开场场景 ===')
    scene = await master._generate_scene('月叶镇')
    print(f'开场场景[前300字]: {scene[:300]}')
    
    # 探索开始
    print('\n=== 探索开始 ===')
    
    async def send_action(action: str, timeout_ms=30000):
        """发送动作并等待叙事响应"""
        print(f'\n发送动作: {action}')
        await master.handle_player_message(action)
        try:
            result = await asyncio.wait_for(narrative_queue.get(), timeout=timeout_ms/1000)
            return result
        except asyncio.TimeoutError:
            return "(超时无响应)"
    
    actions = [
        '去镇中心看看',
        '和周围的人说话',
        '去酒馆',
        '查看状态',
        '去酒馆和老板说话',
    ]
    
    for action in actions:
        result = await send_action(action)
        if result:
            lines = result.split('\n')
            narrative = [l for l in lines if l and not l.startswith('==') and not l.startswith('📊') and not l.startswith('---')]
            if narrative:
                print(f'叙事[前200字]: {" ".join(narrative[:4])[:200]}')
            else:
                print(f'叙事为空或仅系统信息')
        else:
            print('(无响应)')
    
    print('\n=== 报告基础信息 ===')
    print(f'当前回合: {master.game_state["turn"]}')
    print(f'当前位置: {master.game_state.get("location", "?")}')
    print(f'HP: {master.game_state["player_stats"]["hp"]}/{master.game_state["player_stats"]["max_hp"]}')
    
    await master.stop()
    await bus.stop()

asyncio.run(playtest())
