import asyncio
import sys
import os
# Add the ai-dm-rpg root to path
root = r'C:\Users\15901\.openclaw\workspace\ai-dm-rpg'
if root not in sys.path:
    sys.path.insert(0, root)
os.chdir(root)
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

from src import init_event_bus, init_game_master, EventType, Event
from src.character_creator import get_character_creator
from src.tutorial_system import get_tutorial_system, TutorialMode

async def wait_for_narrative(bus, timeout=60):
    """等待叙事输出事件"""
    narrative_event = asyncio.Event()
    result = {"text": "", "turn": 0}
    
    def handler(event: Event):
        result["text"] = event.data.get("text", "")
        result["turn"] = event.data.get("turn", 0)
        narrative_event.set()
    
    sub_id = f"playtest_{id(asyncio.current_task())}"
    await bus.subscribe(EventType.NARRATIVE_OUTPUT, handler, sub_id)
    try:
        await asyncio.wait_for(narrative_event.wait(), timeout=timeout)
        return result["text"]
    except asyncio.TimeoutError:
        return "[超时无响应]"
    finally:
        await bus.unsubscribe(EventType.NARRATIVE_OUTPUT, sub_id)

async def act(master, bus, action, label):
    """执行动作并等待叙事响应"""
    print(f"\n--- {label}: {action} ---")
    await master.handle_player_message(action)
    response = await wait_for_narrative(bus)
    print(response[:500] if response else "[空响应]")
    return response

async def playtest():
    print("=" * 60)
    print("体验官自动体验")
    print("=" * 60)

    bus = await init_event_bus()
    master = await init_game_master()
    await master.initialize()

    creator = get_character_creator()
    tutorial = get_tutorial_system()
    tutorial.set_mode(TutorialMode.SKIP)

    char = creator.create_from_selection('体验官', 'human', 'warrior')
    print(f"\n[角色] {char.name} | {char.race_name} | {char.class_name} | HP:{char.current_hp}/{char.max_hp}")

    master.game_state['player_stats'] = {
        'hp': char.current_hp, 'max_hp': char.max_hp,
        'ac': char.armor_class, 'xp': char.xp,
        'level': char.level, 'gold': char.gold,
        'inventory': char.inventory,
        'name': char.name, 'race': char.race_name, 'class': char.class_name,
    }
    master.game_state['turn'] = 0
    master.game_state['location'] = '月叶镇'
    master.game_state['active_npcs_per_scene'] = {}
    master.game_state['active_npcs'] = {}
    master.game_state['quest_stage'] = 'not_started'
    master.game_state['quest_active'] = False

    results = {}
    
    # 开场叙事
    scene = await master._generate_scene('月叶镇')
    results['开场场景'] = scene
    
    # 动作测试
    await act(master, bus, "探索月叶镇", "开场探索")
    await act(master, bus, "和周围的人说话", "NPC泛化交互")
    await act(master, bus, "向镇子里的老人询问这里的情况", "NPC具体询问")
    await act(master, bus, "去镇上的酒馆", "场景切换-酒馆")
    await act(master, bus, "在酒馆里四处张望", "观察酒馆")
    await act(master, bus, "查看状态", "系统命令")
    await act(master, bus, "离开酒馆去野外", "离开酒馆")
    await act(master, bus, "在野外寻找敌人", "寻找战斗")
    
    await master.stop()
    await bus.stop()
    
    return results

if __name__ == '__main__':
    results = asyncio.run(playtest())
    print("\n\n=== 体验完成 ===")
