# -*- coding: utf-8 -*-
"""
体验官测试脚本 - 自动化游戏体验
"""
import asyncio
import sys
import os
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src import init_event_bus, init_game_master
from src.character_creator import get_character_creator

OUTPUT_LOG = []

def log(msg):
    timestamp = datetime.now().strftime("%H:%M:%S")
    line = f"[{timestamp}] {msg}"
    print(line)
    OUTPUT_LOG.append(line)

async def main():
    log("=== 体验官测试开始 ===")
    
    # 初始化
    bus = await init_event_bus()
    master = await init_game_master()
    
    # 创建角色
    creator = get_character_creator()
    char = creator.create_from_selection("体验官", "human", "warrior")
    log(f"角色创建: {char.name} | {char.race_name} | {char.class_name}")
    
    # 初始化状态
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
    
    # 初始叙事
    log("--- 初始场景 ---")
    initial = (
        "你睁开眼睛，发现自己正坐在「醉梦酒馆」的一张木桌旁。"
        "窗外是黄昏的余晖，空气中弥漫着麦酒和烤肉的气息。"
        "酒馆里人声鼎沸，角落里有几个冒险者在低声交谈。"
        "你握紧腰间的武器，决定先四处看看，了解一下情况。"
    )
    log(initial[:80])
    
    # 探索序列
    actions = [
        # 探索酒馆
        ("探索酒馆", "环顾酒馆四周，描述环境"),
        ("和酒馆里的人说话", "和周围的人交谈"),
        ("去柜台问问", "走到柜台询问老板"),
        # 离开酒馆
        ("离开酒馆去镇上", "走出酒馆，去镇上看看"),
        ("在镇中心逛逛", "在镇中心广场逛逛"),
        # 触发战斗
        ("寻找危险", "主动寻找危险"),
        # 意外操作测试
        ("唱首歌", "突然唱起歌来"),
        ("询问关于酒馆的秘密", "问老板这个酒馆有没有什么秘密"),
    ]
    
    turn = 0
    for label, action in actions:
        turn += 1
        log(f"\n--- 回合 {turn}: {label} ---")
        log(f"行动: {action}")
        try:
            result = await master.handle_player_message(action)
            if result:
                # 提取叙事内容（取前300字）
                text = str(result)
                if len(text) > 300:
                    text = text[:300] + "..."
                log(f"叙事: {text}")
            else:
                log("结果: (空)")
        except Exception as e:
            log(f"错误: {e}")
            # API限流处理
            if "429" in str(e) or "rate" in str(e).lower():
                log("API限流，等待30秒...")
                await asyncio.sleep(30)
                try:
                    result = await master.handle_player_message(action)
                    if result:
                        text = str(result)[:300]
                        log(f"重试后叙事: {text}")
                except:
                    pass
    
    # 战斗测试
    log("\n--- 战斗测试 ---")
    try:
        result = await master.handle_player_message("主动寻找怪物战斗")
        if result:
            text = str(result)[:300]
            log(f"战斗叙事: {text}")
    except Exception as e:
        log(f"战斗错误: {e}")
    
    # 最终状态
    stats = master.game_state.get("player_stats", {})
    log(f"\n=== 测试结束 ===")
    log(f"最终HP: {stats.get('hp', '?')}/{stats.get('max_hp', '?')}")
    log(f"位置: {master.game_state.get('location', '?')}")
    log(f"回合数: {master.game_state.get('turn', '?')}")
    
    await master.stop()
    await bus.stop()
    
    # 保存日志
    with open(os.path.join(os.path.dirname(__file__), "playtest_log.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(OUTPUT_LOG))
    log("日志已保存到 playtest_log.txt")
    
    return OUTPUT_LOG

if __name__ == "__main__":
    asyncio.run(main())
