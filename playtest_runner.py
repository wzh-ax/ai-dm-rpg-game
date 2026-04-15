# -*- coding: utf-8 -*-
"""
体验官测试脚本 - 简化版，仅记录关键信息
"""
import asyncio
import sys
import os
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src import init_event_bus, init_game_master
from src.event_bus import EventType, Event
from src.character_creator import get_character_creator

OUTPUT_LOG = []

def log(msg):
    timestamp = datetime.now().strftime("%H:%M:%S")
    line = f"[{timestamp}] {msg}"
    try:
        print(line)
    except UnicodeEncodeError:
        safe_line = line.encode('utf-8', errors='replace').decode('utf-8', errors='replace')
        print(safe_line)
    OUTPUT_LOG.append(line)

async def main():
    log("=== 体验官测试开始 ===")
    
    bus = await init_event_bus()
    master = await init_game_master()
    
    # 订阅叙事输出
    narrative_results = []
    async def narrative_handler(event: Event):
        data = event.data
        narrative_results.append(data)
        text = data.get("text", "")
        if text:
            safe_text = text[:200].replace('\n', ' ')
            log(f"[NARRATIVE] {safe_text}")
    
    await bus.subscribe(EventType.NARRATIVE_OUTPUT, narrative_handler, "playtest_narrative")
    
    # 创建角色
    creator = get_character_creator()
    char = creator.create_from_selection("体验官", "human", "warrior")
    log(f"角色创建: {char.name} | {char.race_name} | {char.class_name}")
    
    master.game_state["player_stats"] = {
        "hp": char.current_hp, "max_hp": char.max_hp,
        "ac": char.armor_class, "xp": char.xp,
        "level": char.level, "gold": char.gold,
        "inventory": char.inventory,
        "name": char.name, "race": char.race_name,
        "class": char.class_name,
    }
    master.game_state["turn"] = 0
    master.game_state["location"] = "醉梦酒馆"
    
    log("--- 初始场景 ---")
    initial = "你睁开眼睛，发现自己正坐在「醉梦酒馆」的一张木桌旁。窗外是黄昏的余晖，空气中弥漫着麦酒和烤肉的气息。"
    log(initial[:80])
    
    actions = [
        ("探索酒馆", "环顾酒馆四周，描述环境"),
        ("和酒馆里的人说话", "和周围的人交谈，问问他们在聊什么"),
        ("去柜台问老板", "走到柜台询问老板"),
        ("离开酒馆", "走出酒馆，去镇上"),
        ("镇中心", "在镇中心广场逛逛"),
        ("寻找危险", "主动寻找危险"),
        ("唱首歌", "突然唱起歌来"),
    ]
    
    for i, (label, action) in enumerate(actions):
        log(f"\n--- {i+1}: {label} ---")
        log(f"行动: {action}")
        narrative_results.clear()
        
        try:
            await master.handle_player_message(action)
            await asyncio.sleep(6)
            
            if narrative_results:
                for nr in narrative_results:
                    text = str(nr.get("text", ""))
                    if text and len(text) > 5:
                        log(f"叙事OK[{nr.get('turn','?')}]: {text[:150].replace(chr(10), ' ')}")
                    elif text:
                        log(f"叙事短[{nr.get('turn','?')}]: {text[:80].replace(chr(10), ' ')}")
                    else:
                        log(f"空叙事[{nr.get('turn','?')}]: mode={nr.get('mode','?')}")
            else:
                log("结果: (无叙事)")
        except Exception as e:
            log(f"错误: {str(e)[:100]}")
    
    # 战斗测试
    log("\n--- 战斗测试 ---")
    narrative_results.clear()
    try:
        await master.handle_player_message("主动寻找怪物战斗")
        await asyncio.sleep(8)
        if narrative_results:
            for nr in narrative_results:
                log(f"战斗: {str(nr.get('text',''))[:150].replace(chr(10), ' ')}")
        else:
            log("战斗: (无叙事)")
    except Exception as e:
        log(f"战斗错误: {str(e)[:100]}")
    
    stats = master.game_state.get("player_stats", {})
    log(f"\n=== 测试结束 ===")
    log(f"HP: {stats.get('hp','?')}/{stats.get('max_hp','?')}")
    log(f"位置: {master.game_state.get('location','?')}")
    log(f"回合: {master.game_state.get('turn','?')}")
    
    await master.stop()
    await bus.stop()
    
    log_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tests", "playtest_log.txt")
    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    with open(log_path, "w", encoding="utf-8") as f:
        f.write("\n".join(OUTPUT_LOG))
    log(f"日志: {log_path}")
    
    return OUTPUT_LOG

if __name__ == "__main__":
    asyncio.run(main())
