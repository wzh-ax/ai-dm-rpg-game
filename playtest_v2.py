import asyncio
import sys
sys.path.insert(0, '.')
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.stderr.reconfigure(encoding='utf-8', errors='replace')

from src import init_event_bus, init_game_master, EventType, Event
from src.character_creator import get_character_creator
from src.tutorial_system import get_tutorial_system, TutorialMode
from src.quest_state import QuestStage, QUEST_NAME

async def playtest():
    results = []
    
    bus = await init_event_bus()
    master = await init_game_master()
    
    # ===== 角色创建 =====
    creator = get_character_creator()
    char = creator.create_from_selection('体验官', 'human', 'warrior')
    char_data = char.to_dict()
    results.append(('角色创建', f'名字:{char.name}, 种族:{char.race_name}, 职业:{char.class_name}'))
    
    # ===== 初始化玩家状态 =====
    player_stats = {
        "hp": char_data["current_hp"],
        "max_hp": char_data["max_hp"],
        "ac": char_data["armor_class"],
        "xp": char_data["xp"],
        "level": char_data["level"],
        "gold": char_data["gold"],
        "inventory": char_data["inventory"],
        "character_id": char_data["id"],
        "name": char_data["name"],
        "race": char_data["race_name"],
        "class": char_data["class_name"],
        "attributes": char_data["attributes"],
        "primary_skill": char_data["primary_skill"],
        "skill_description": char_data["skill_description"],
        "special_ability": char_data["special_ability"],
        "race_id": char_data["race_id"],
        "class_id": char_data["class_id"],
    }
    master.game_state["player_stats"] = player_stats
    master.game_state["turn"] = 0
    master.game_state["location"] = "月叶镇"
    
    # ===== 教程设置（跳过）=====
    tutorial = get_tutorial_system()
    tutorial.set_mode(TutorialMode.SKIP)
    
    # ===== 欢迎叙事 =====
    welcome = await tutorial.generate_welcome_narrative(char_data)
    results.append(('欢迎叙事', welcome[:300] if welcome else '(空)'))
    
    # ===== 开启主线任务 =====
    tutorial.complete_tutorial()
    master.quest_state.advance_to(QuestStage.FIND_MAYOR)
    master.game_state["quest_active"] = True
    master.game_state["quest_stage"] = QuestStage.FIND_MAYOR.value
    
    # ===== 开场场景 =====
    opening_scene = await master._generate_scene("月叶镇")
    results.append(('开场场景', opening_scene[:300] if opening_scene else '(空)'))
    
    # ===== 订阅叙事输出 =====
    narrative_texts = []
    narrative_ready = asyncio.Event()
    
    async def output_handler(event: Event):
        text = event.data.get("text", "")
        turn = event.data.get("turn", "?")
        mode = event.data.get("mode", "?")
        narrative_texts.append({'text': text, 'turn': turn, 'mode': mode})
        narrative_ready.set()
    
    await bus.subscribe(EventType.NARRATIVE_OUTPUT, output_handler, "playtest_output")
    
    # ===== 战斗事件订阅 =====
    async def combat_start_handler(event: Event):
        combatants = event.data.get("combatants", [])
        narrative_texts.append({'text': f'[战斗开始] {[c.get("name","?") for c in combatants]}', 'turn': '?', 'mode': 'combat'})
        narrative_ready.set()
    
    async def combat_end_handler(event: Event):
        winner = event.data.get("winner", "?")
        narrative_texts.append({'text': f'[战斗结束] 胜者:{winner}', 'turn': '?', 'mode': 'combat'})
        narrative_ready.set()
    
    await bus.subscribe(EventType.COMBAT_START, combat_start_handler, "playtest_combat")
    await bus.subscribe(EventType.COMBAT_END, combat_end_handler, "playtest_combat")
    
    # ===== 辅助函数：发送输入并获取叙事 =====
    async def send_and_get_response(action, timeout=30.0):
        narrative_ready.clear()
        narrative_texts.clear()
        await master.handle_player_message(action)
        try:
            await asyncio.wait_for(narrative_ready.wait(), timeout=timeout)
        except asyncio.TimeoutError:
            return f'[超时] {action}'
        if narrative_texts:
            return narrative_texts[0]['text'][:500]
        return f'[空响应] {action}'
    
    # ===== 探索流程 =====
    test_actions = [
        # 基础探索
        ('探索-去镇中心', '去镇中心看看'),
        ('探索-和NPC说话', '和周围的人说话'),
        ('探索-去酒馆', '去酒馆'),
        ('探索-查看状态', '查看状态'),
        
        # NPC交互
        ('对话-询问任务', '询问镇长这里发生了什么'),
        ('对话-闲聊', '随便聊聊'),
        
        # 意外操作测试
        ('意外-唱歌', '我在镇中心唱首歌'),
        ('意外-威胁', '我威胁路人要钱'),
        ('意外-发呆', '我站在原地发呆一分钟'),
        
        # 道具测试
        ('道具-查看背包', '查看背包'),
        ('道具-使用药水', '使用治疗药水'),
        
        # 商店测试
        ('商店-进入', '去商店'),
        ('商店-购买', '买治疗药水'),
    ]
    
    for label, action in test_actions:
        result = await send_and_get_response(action)
        results.append((label, result))
        print(f'[测试] {label}: {result[:100]}...' if len(result) > 100 else f'[测试] {label}: {result}')
        await asyncio.sleep(0.5)
    
    # ===== 战斗触发测试 =====
    combat_actions = [
        ('战斗-攻击NPC', '攻击最近的NPC'),
        ('战斗-挥拳', '我向空中挥拳'),
    ]
    for label, action in combat_actions:
        result = await send_and_get_response(action)
        results.append((f'战斗-{label}', result))
        print(f'[战斗测试] {label}: {result[:100]}...' if len(result) > 100 else f'[战斗测试] {label}: {result}')
        await asyncio.sleep(0.5)
    
    # ===== 最终状态 =====
    final_state = {
        'turn': master.game_state['turn'],
        'location': master.game_state.get('location', '?'),
        'hp': master.game_state['player_stats']['hp'],
        'max_hp': master.game_state['player_stats']['max_hp'],
        'gold': master.game_state['player_stats']['gold'],
        'xp': master.game_state['player_stats']['xp'],
        'level': master.game_state['player_stats']['level'],
        'quest_stage': master.game_state.get('quest_stage', '?'),
    }
    results.append(('最终状态', str(final_state)))
    
    # ===== 清理 =====
    await master.stop()
    await bus.stop()
    
    return results

if __name__ == "__main__":
    results = asyncio.run(playtest())
    print('\n\n=== 完整测试结果 ===')
    for label, content in results:
        print(f'\n[{label}]')
        print(content)
        print('---')
