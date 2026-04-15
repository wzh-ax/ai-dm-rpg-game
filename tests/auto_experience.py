# -*- coding: utf-8 -*-
"""
体验官自动体验脚本
通过 API 直接调用游戏逻辑，模拟玩家体验
"""
import asyncio
import sys
import os
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src import init_event_bus, init_game_master
from src.character_creator import get_character_creator


async def run_experience():
    """执行完整游戏体验流程"""
    start_time = datetime.now()
    
    # ===== 初始化 =====
    print("=" * 60)
    print("体验官开始执行游戏体验...")
    print("=" * 60)
    
    bus = await init_event_bus()
    master = await init_game_master()
    
    # ===== 角色创建 =====
    print("\n[阶段1] 角色创建")
    creator = get_character_creator()
    char = creator.create_from_selection("体验官", "human", "warrior")
    print(f"创建角色: {char.name} | {char.race_name} | {char.class_name}")
    print(f"HP: {char.current_hp}/{char.max_hp} | AC: {char.armor_class}")
    
    # 初始化游戏状态
    master.game_state["player_stats"] = {
        "hp": char.current_hp,
        "max_hp": char.max_hp,
        "ac": char.armor_class,
        "xp": char.xp,
        "level": char.level,
        "gold": char.gold,
        "inventory": char.inventory,
        "name": char.name,
        "race": char.race_name,
        "class": char.class_name,
    }
    master.game_state["turn"] = 0
    master.game_state["location"] = "月叶镇"
    
    experience_log = []
    
    def log(tag, msg):
        entry = f"[{tag}] {msg}"
        print(entry)
        experience_log.append(entry)
    
    # ===== 体验流程 =====
    print("\n[阶段2] 开场体验")
    
    # 场景1: 酒馆开场
    log("开场", "酒馆内景 - 黄昏光线、麦酒气息、冒险者低声交谈")
    result1 = await master.handle_player_message("我走进酒馆，环顾四周")
    log("叙事", result1[:200] if result1 else "(无响应)")
    
    # 场景2: 探索镇中心
    print("\n[阶段3] 探索月叶镇")
    result2 = await master.handle_player_message("去镇中心看看")
    log("探索", result2[:200] if result2 else "(无响应)")
    
    # 场景3: 与NPC对话
    print("\n[阶段4] NPC对话体验")
    result3 = await master.handle_player_message("和周围的人说话")
    log("NPC", result3[:300] if result3 else "(无响应)")
    
    # 场景4: 酒馆深入
    print("\n[阶段5] 酒馆深度体验")
    result4 = await master.handle_player_message("去酒馆找个位置坐下，听听有什么消息")
    log("酒馆", result4[:300] if result4 else "(无响应)")
    
    # 场景5: 意外操作测试
    print("\n[阶段6] 意外操作测试")
    result5 = await master.handle_player_message("我突然想跳舞，在酒馆中央跳了起来")
    log("意外", result5[:200] if result5 else "(无响应)")
    
    # 场景6: 离开酒馆
    print("\n[阶段7] 离开酒馆探索")
    result6 = await master.handle_player_message("离开酒馆，去外面的街道走走")
    log("探索", result6[:200] if result6 else "(无响应)")
    
    # 场景7: 商店/市场
    print("\n[阶段8] 市场区域")
    result7 = await master.handle_player_message("去市场逛逛，看看有什么商品")
    log("市场", result7[:300] if result7 else "(无响应)")
    
    # 场景8: 触发战斗
    print("\n[阶段9] 战斗体验")
    result8 = await master.handle_player_message("去镇子外面的森林冒险")
    log("战斗", result8[:300] if result8 else "(无响应)")
    
    # 场景9: 使用道具
    print("\n[阶段10] 道具使用")
    result9 = await master.handle_player_message("使用一个治疗药水")
    log("道具", result9[:200] if result9 else "(无响应)")
    
    # 场景10: 深入对话
    print("\n[阶段11] 深入对话")
    result10 = await master.handle_player_message("找个看起来很重要的人深入聊聊")
    log("深度对话", result10[:300] if result10 else "(无响应)")
    
    # 场景11: 再次探索酒馆
    print("\n[阶段12] 返回酒馆")
    result11 = await master.handle_player_message("返回酒馆，看看有没有新面孔")
    log("返回", result11[:200] if result11 else "(无响应)")
    
    end_time = datetime.now()
    duration = (end_time - start_time).total_seconds()
    
    # ===== 清理 =====
    await master.stop()
    await bus.stop()
    
    # ===== 返回体验日志 =====
    return {
        "start_time": start_time.isoformat(),
        "end_time": end_time.isoformat(),
        "duration_seconds": duration,
        "log": experience_log,
        "final_location": master.game_state.get("location", "未知"),
        "final_turn": master.game_state.get("turn", 0),
        "player_stats": master.game_state.get("player_stats", {}),
    }


if __name__ == "__main__":
    result = asyncio.run(run_experience())
    print("\n" + "=" * 60)
    print("体验完成！")
    print(f"时长: {result['duration_seconds']:.1f}秒")
    print(f"回合: {result['final_turn']}")
    print(f"位置: {result['final_location']}")
    print("=" * 60)
