"""
体验官自动化体验脚本
"""
import asyncio
import logging
import sys
import json
import os
from datetime import datetime

# 添加项目根目录到 path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.stderr.reconfigure(encoding='utf-8', errors='replace')

from src import (
    init_event_bus,
    init_game_master,
    EventType,
    Event,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logging.getLogger("src.event_bus").setLevel(logging.WARNING)
logging.getLogger("src.memory_manager").setLevel(logging.WARNING)

async def main():
    start_time = datetime.now()
    print(f"\n{'='*60}")
    print(f"体验官自动化测试开始: {start_time}")
    print(f"{'='*60}\n")

    # 初始化
    bus = await init_event_bus()
    master = await init_game_master()

    # 收集所有事件
    events_log = []
    narratives = []

    async def narrative_handler(event: Event):
        data = event.data
        narratives.append(data)
        turn = data.get('turn', '?')
        mode = data.get('mode', '?')
        text = data.get("text", "")
        print(f"\n[NARRATIVE] 回合 {turn} [{mode}]:")
        print("-" * 40)
        print(text[:500] if len(text) > 500 else text)
        print("-" * 40)

    async def combat_start(event: Event):
        print(f"\n*** 战斗开始! ***")
        combatants = event.data.get("combatants", [])
        for c in combatants:
            print(f"  - {c.get('name','?')} (HP:{c.get('hp','?')}, AC:{c.get('armor_class','?')})")

    async def combat_end(event: Event):
        print(f"\n*** 战斗结束! ***")
        rewards = event.data.get("rewards", {})
        if rewards:
            print(f"  奖励: XP={rewards.get('xp',0)}, Gold={rewards.get('gold',0)}")
            if rewards.get("items"):
                print(f"  获得物品: {', '.join(rewards['items'])}")

    await bus.subscribe(EventType.NARRATIVE_OUTPUT, narrative_handler, "exp_narrative")
    await bus.subscribe(EventType.COMBAT_START, combat_start, "exp_combat")
    await bus.subscribe(EventType.COMBAT_END, combat_end, "exp_combat")

    # 测试流程
    test_inputs = [
        "我走进酒馆",
        "我和酒馆老板说话",
        "酒馆老板你好",
        "查看状态",
        "背包",
        "help",
        "攻击",
        "我前往森林探索",
        "quit"
    ]

    print("\n【测试输入序列】")
    for i, inp in enumerate(test_inputs, 1):
        print(f"  {i}. {inp}")

    results = []
    for inp in test_inputs:
        print(f"\n\n{'='*60}")
        print(f">>> {inp}")
        print(f"{'='*60}")
        await master.handle_player_message(inp)
        await asyncio.sleep(1.0)
        stats = master.game_state["player_stats"]
        results.append({
            "input": inp,
            "hp": stats["hp"],
            "max_hp": stats["max_hp"],
            "gold": stats["gold"],
            "xp": stats["xp"],
            "level": stats["level"],
            "mode": master.game_state.get("mode", "unknown"),
        })

    # 保存结果
    output = {
        "start_time": start_time.isoformat(),
        "end_time": datetime.now().isoformat(),
        "test_inputs": test_inputs,
        "results": results,
        "narrative_count": len(narratives),
    }

    with open("sandbox/tiyanguan_output.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"\n\n{'='*60}")
    print("体验官测试完成")
    print(f"{'='*60}")
    print(f"叙事输出: {len(narratives)} 条")
    print(f"测试输入: {len(test_inputs)} 条")
    print(f"结果已保存: sandbox/tiyanguan_output.json")

    await master.stop()
    await bus.stop()

if __name__ == "__main__":
    asyncio.run(main())
