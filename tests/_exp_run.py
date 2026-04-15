# -*- coding: utf-8 -*-
"""
AI DM RPG - 体验官自动化体验 V7 (for V1_0_7)
"""
import asyncio
import sys
import os
from datetime import datetime

_script_dir = os.path.dirname(os.path.abspath(__file__))
_project_root = os.path.dirname(_script_dir)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

# UTF-8 输出
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

from src import init_event_bus, init_game_master, EventType, Event
from src.character_creator import get_character_creator


# 体验动作序列
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


async def run_with_retry(coro, max_retries=3, retry_delay=30):
    """带重试的执行"""
    for attempt in range(max_retries):
        try:
            return await coro()
        except Exception as e:
            err_str = str(e)
            if "429" in err_str or "rate" in err_str.lower() or "quota" in err_str.lower():
                print(f"API 限流，等待 {retry_delay}s 重试（第 {attempt+1}/{max_retries} 次）")
                await asyncio.sleep(retry_delay)
            else:
                raise
    raise Exception(f"重试 {max_retries} 次后仍然失败")


async def main():
    print("=" * 60)
    print("AI DM RPG - 体验官体验 V7 (V1_0_7)")
    print("=" * 60)
    
    start_time = datetime.now()
    
    async def init_game():
        bus = await init_event_bus()
        gm = await init_game_master()
        return bus, gm
    
    bus, gm = await run_with_retry(init_game)
    
    creator = get_character_creator()
    char = creator.create_from_selection("体验官", "human", "warrior")
    print(f"\n角色: {char.name} ({char.race_name}/{char.class_name})")
    print(f"HP: {char.current_hp}/{char.max_hp} | AC: {char.armor_class}")
    
    gm.game_state["player_stats"] = char.to_player_stats()
    gm.game_state["turn"] = 0
    gm.game_state["location"] = "月叶镇"
    
    # 收集 NARRATIVE_OUTPUT
    narratives = []
    async def collect(event: Event):
        narratives.append(event.data)
    await bus.subscribe(EventType.NARRATIVE_OUTPUT, collect, "collector")
    
    turn_data = []
    combat_triggered = 0
    combat_turns_in_combat = 0
    
    for i, (action_type, action) in enumerate(ACTIONS):
        turn_num = i + 1
        gm.game_state["turn"] = turn_num
        
        print(f"\n--- 回合 {turn_num}: [{action_type}] {action} ---")
        
        narratives.clear()
        
        async def send_and_wait():
            await gm.handle_player_message(action)
            # 等待足够长的时间让 LLM 生成响应
            await asyncio.sleep(8)
        
        await run_with_retry(send_and_wait)
        
        text = narratives[-1].get("text", "") if narratives else ""
        mode = narratives[-1].get("mode", "unknown") if narratives else "unknown"
        
        # 记录战斗状态
        if mode == "combat":
            combat_triggered += 1
            combat_turns_in_combat += 1
        elif mode == "exploration" and combat_turns_in_combat > 0:
            combat_turns_in_combat = 0
        
        print(f"叙事 [{mode}]: {text[:100] if text else '(空)'}")
        
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
    
    # 战斗相关
    combat_triggers = sum(1 for t in turn_data if "战斗" in t["type"] and t["length"] > 0)
    npc_success = sum(1 for t in turn_data if t["type"] == "NPC" and t["length"] > 50)
    
    # 敷衍检测：检查是否大量出现"空气中弥漫着X气息"模式
    template_count = sum(1 for t in turn_data if "空气中弥漫着" in t["text"])
    
    print(f"总回合: {total}")
    print(f"游玩时长: {duration:.0f}秒")
    print(f"平均叙事长度: {avg_len:.0f}字符")
    print(f"无响应次数: {empty_count}/{total} ({empty_rate:.1f}%)")
    print(f"战斗触发: {combat_triggered}次")
    print(f"NPC成功对话: {npc_success}次")
    print(f"万能氛围模板出现: {template_count}次")
    
    return {
        "version": "V1_0_7",
        "start_time": start_time.isoformat(),
        "duration_seconds": duration,
        "total_turns": total,
        "avg_narrative_length": avg_len,
        "empty_count": empty_count,
        "empty_rate": empty_rate,
        "combat_triggered": combat_triggered,
        "npc_success": npc_success,
        "template_count": template_count,
        "turn_data": turn_data,
        "final_location": gm.game_state.get("location", "?"),
    }


if __name__ == "__main__":
    result = asyncio.run(main())
    print("\n体验完成!")
