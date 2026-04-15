# -*- coding: utf-8 -*-
"""
AI DM RPG - 体验官自动化体验 V7b (for V1_0_7)
改进版：每次动作后等待直到收到叙事，不依赖固定sleep时间
"""
import asyncio
import sys
import os
from datetime import datetime

_script_dir = os.path.dirname(os.path.abspath(__file__))
_project_root = os.path.dirname(_script_dir)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

from src import init_event_bus, init_game_master, EventType, Event
from src.character_creator import get_character_creator


ACTIONS = [
    ("开场", "我走进酒馆，环顾四周"),
    ("探索", "去镇中心看看"),
    ("NPC", "和周围的人说话"),
    ("探索", "去酒馆找个位置坐下，听听有什么消息"),
    ("意外", "我突然想跳舞，在酒馆中央跳了起来"),
    ("探索", "离开酒馆，去外面的街道走走"),
    ("探索", "去市场逛逛，看看有什么商品"),
    ("战斗", "去镇子外面的森林冒险"),
    ("道具", "使用一个治疗药水"),
    ("NPC", "找个看起来很重要的人深入聊聊"),
    ("探索", "返回酒馆，看看有没有新面孔"),
    ("系统", "查看状态"),
]


async def wait_for_narrative(bus, timeout=30, expected_turn=None):
    """等待叙事事件，超时返回空"""
    start = datetime.now()
    last_data = None
    
    while (datetime.now() - start).total_seconds() < timeout:
        await asyncio.sleep(1)
        # 从事件总线获取最新的 NARRATIVE_OUTPUT
        # 由于我们用 subscribe，每次发布都会触发回调
        # 这里用偷窃方式：从 bus 内部状态获取
        if hasattr(bus, '_last_narrative') and bus._last_narrative:
            data = bus._last_narrative
            if expected_turn is None or data.get('turn') == expected_turn:
                bus._last_narrative = None
                return data
    return None


async def main():
    print("=" * 60)
    print("AI DM RPG - 体验官体验 V7b (V1_0_7)")
    print("=" * 60)
    
    start_time = datetime.now()
    bus = await init_event_bus()
    gm = await init_game_master()
    
    # 注入 _last_narrative 用于偷窃最新叙事
    bus._last_narrative = None
    
    creator = get_character_creator()
    char = creator.create_from_selection("体验官", "human", "warrior")
    print(f"\n角色: {char.name} ({char.race_name}/{char.class_name})")
    print(f"HP: {char.current_hp}/{char.max_hp} | AC: {char.armor_class}")
    
    gm.game_state["player_stats"] = char.to_player_stats()
    gm.game_state["turn"] = 0
    gm.game_state["location"] = "月叶镇"
    
    # 拦截 NARRATIVE_OUTPUT 事件
    async def collect(event: Event):
        bus._last_narrative = event.data
    
    await bus.subscribe(EventType.NARRATIVE_OUTPUT, collect, "v7b_collector")
    
    turn_data = []
    
    for i, (action_type, action) in enumerate(ACTIONS):
        turn_num = i + 1
        gm.game_state["turn"] = turn_num
        bus._last_narrative = None
        
        print(f"\n--- 回合 {turn_num}: [{action_type}] {action} ---")
        
        await gm.handle_player_message(action)
        
        # 等待叙事，最多30秒
        narrative_data = await wait_for_narrative(bus, timeout=30, expected_turn=turn_num)
        
        if narrative_data:
            text = narrative_data.get("text", "")
            mode = narrative_data.get("mode", "unknown")
            print(f"叙事 [{mode}]: {text[:120] if text else '(空)'}")
        else:
            text = ""
            mode = "unknown"
            print(f"叙事: (等待超时)")
        
        turn_data.append({
            "turn": turn_num,
            "type": action_type,
            "action": action,
            "text": text,
            "length": len(text),
            "mode": mode,
        })
    
    duration = (datetime.now() - start_time).total_seconds()
    
    await gm.stop()
    await bus.stop()
    
    # ===== 统计分析 =====
    print("\n" + "=" * 60)
    print("体验统计")
    print("=" * 60)
    
    total = len(turn_data)
    avg_len = sum(t["length"] for t in turn_data) / total if total else 0
    empty_count = sum(1 for t in turn_data if t["length"] == 0)
    empty_rate = empty_count / total * 100 if total else 0
    
    combat_triggers = sum(1 for t in turn_data if t["type"] == "战斗" and t["length"] > 0 and t["mode"] == "combat")
    npc_success = sum(1 for t in turn_data if t["type"] == "NPC" and t["length"] > 50)
    
    # 敷衍检测
    template_phrases = ["空气中弥漫着", "你的声音在空气中回荡", "仿佛在等待着什么"]
    template_count = sum(
        sum(1 for phrase in template_phrases if phrase in t["text"])
        for t in turn_data
    )
    
    # 具体问题：万能模板出现
    template_turns = []
    for t in turn_data:
        for phrase in template_phrases:
            if phrase in t["text"]:
                template_turns.append(t["turn"])
                break
    
    print(f"总回合: {total}")
    print(f"游玩时长: {duration:.0f}秒")
    print(f"平均叙事长度: {avg_len:.0f}字符")
    print(f"无响应次数: {empty_count}/{total} ({empty_rate:.1f}%)")
    print(f"战斗触发成功: {combat_triggers}次")
    print(f"NPC成功对话: {npc_success}次")
    print(f"万能敷衍模板出现: {template_count}次 (回合: {template_turns})")
    
    # 打印所有叙事
    print("\n" + "=" * 60)
    print("完整叙事记录")
    print("=" * 60)
    for t in turn_data:
        print(f"\n[回合{t['turn']}] [{t['type']}] {t['action']}")
        print(f"模式: {t['mode']} | 长度: {t['length']}")
        print(t['text'][:500] if t['text'] else "(空)")
    
    return {
        "version": "V1_0_7",
        "duration_seconds": duration,
        "total_turns": total,
        "avg_narrative_length": avg_len,
        "empty_count": empty_count,
        "empty_rate": empty_rate,
        "combat_triggers": combat_triggers,
        "npc_success": npc_success,
        "template_count": template_count,
        "template_turns": template_turns,
        "turn_data": turn_data,
    }


if __name__ == "__main__":
    result = asyncio.run(main())
    print("\n体验完成!")
