"""
体验官快速测试 - 2026-04-12 18:40
测试当前版本游戏核心流程
"""
import sys
import asyncio
import time
import traceback
sys.path.insert(0, 'C:/Users/15901/.openclaw/workspace/ai-dm-rpg')
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

print("=" * 60)
print("体验官测试 2026-04-12 18:40")
print("=" * 60)

from src import init_event_bus, init_game_master, EventType
from src.character_creator import get_character_creator
from src.tutorial_system import get_tutorial_system, TutorialMode

results = []
latest = {}
ev_signal = None

async def handler(event):
    latest['text'] = event.data.get('text', '')
    latest['type'] = event.type.value
    if ev_signal:
        ev_signal.set()

async def run():
    global ev_signal
    start = time.time()

    bus = await init_event_bus()
    master = await init_game_master()
    await master.initialize()

    # 创建角色
    creator = get_character_creator()
    char = creator.create_from_selection('体验官', 'human', 'warrior')
    print(f"角色: {char.name} | {char.race_name} | {char.class_name} | HP:{char.current_hp}/{char.max_hp}")

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

    tutorial = get_tutorial_system()
    tutorial.set_mode(TutorialMode.SKIP)

    ev_signal = asyncio.Event()
    await bus.subscribe(EventType.NARRATIVE_OUTPUT, handler, 'tiyanguan1840')

    async def act(msg, label, timeout=30):
        latest.clear()
        ev_signal.clear()
        print(f"\n>>> [{label}] 输入: {msg}")
        result = '(无)'
        try:
            result = await asyncio.wait_for(master.handle_player_message(msg), timeout=timeout)
        except asyncio.TimeoutError:
            result = '(超时)'
        except Exception as e:
            result = f'(异常: {e})'
        
        text = ''
        try:
            await asyncio.wait_for(ev_signal.wait(), timeout=5)
            text = latest.get('text', result or '')
        except asyncio.TimeoutError:
            text = result if result != '(无)' else ''
        
        if not text:
            text = result or '(无响应)'
        
        text_display = str(text)[:200] if text else '(无响应)'
        print(f"    响应: {text_display}")
        
        results.append({
            'label': label,
            'input': msg,
            'output': str(text)[:500] if text else '(无响应)',
            'type': latest.get('type', '?'),
            'error': 'exception' in str(result).lower() or '超时' in str(result),
        })
        return text
    
    # ====== 测试流程 ======
    
    # 1. 开场/教程
    print("\n--- 1. 开场 ---")
    await act("开始游戏", "开场")
    
    # 2. 探索
    print("\n--- 2. 探索月叶镇 ---")
    await act("探索月叶镇", "探索-开始")
    await act("看看周围", "探索-look")
    await act("镇长在哪里", "探索-寻路")
    await act("去镇长办公室", "移动-镇长")
    
    # 3. NPC交互
    print("\n--- 3. NPC交互 ---")
    await act("和镇长说话", "NPC-镇长")
    await act("询问任务", "NPC-询问任务")
    
    # 4. 系统命令
    print("\n--- 4. 系统命令 ---")
    await act("状态", "系统-状态")
    await act("背包", "系统-背包")
    await act("任务", "系统-任务")
    await act("帮助", "系统-帮助")
    
    # 5. 场景切换
    print("\n--- 5. 场景切换 ---")
    await act("去酒馆", "场景-酒馆")
    await act("看看酒馆里的人", "探索-酒馆人物")
    await act("和酒馆老板说话", "NPC-酒馆老板")
    
    # 6. 前往森林
    print("\n--- 6. 战斗区域 ---")
    await act("去森林", "场景-森林")
    await act("深入森林", "场景-深入")
    await act("搜索周围", "探索-森林搜索")
    
    # 7. 战斗
    print("\n--- 7. 战斗测试 ---")
    await act("攻击", "战斗-攻击1")
    await act("防御", "战斗-防御")
    await act("攻击怪物", "战斗-攻击2")
    await act("使用治疗药水", "战斗-道具")
    
    await master.stop()
    await bus.stop()
    
    elapsed = time.time() - start
    return elapsed, results

if __name__ == '__main__':
    try:
        elapsed, results = asyncio.run(run())
        print("\n" + "=" * 60)
        print(f"测试完成！耗时: {elapsed:.1f}s | 总操作: {len(results)}")
        
        errors = [r for r in results if r.get('error')]
        no_resp = [r for r in results if r['output'] in ['(无响应)', '(超时)', '(无)']]
        
        print(f"错误数: {len(errors)}")
        print(f"无响应数: {len(no_resp)}")
        
        if errors:
            print("\n错误操作:")
            for r in errors:
                print(f"  [{r['label']}] {r['input']} -> {r['output'][:100]}")
        
        if no_resp:
            print("\n无响应操作:")
            for r in no_resp:
                print(f"  [{r['label']}] {r['input']}")
        
        # 保存结果
        import json
        import os
        os.makedirs('C:/Users/15901/.openclaw/workspace-ai-dm-rpg/tasks', exist_ok=True)
        with open('C:/Users/15901/.openclaw/workspace-ai-dm-rpg/tasks/tiyanguan_1840_data.json', 'w', encoding='utf-8') as f:
            json.dump({'elapsed': elapsed, 'results': results}, f, ensure_ascii=False, indent=2)
        print("\n数据已保存到 tasks/tiyanguan_1840_data.json")
        
    except Exception as e:
        print(f"\n致命错误: {e}")
        traceback.print_exc()
