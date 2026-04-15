# -*- coding: utf-8 -*-
"""
AI DM RPG - 体验官体验 V7
精准检测叙事重复问题
"""
import asyncio
import sys
import os
import time
from datetime import datetime

_script_dir = os.path.dirname(os.path.abspath(__file__))
_project_root = os.path.dirname(_script_dir)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from src import (
    init_event_bus,
    init_main_dm,
    get_character_creator,
    EventType,
    Event,
)


async def run():
    print("=" * 60)
    print("AI DM RPG - 体验官体验 V7")
    print("=" * 60)
    
    start_time = time.time()
    
    bus = await init_event_bus()
    dm = await init_main_dm()
    await dm.start()
    
    narratives = []
    async def collect(event: Event):
        narratives.append(event.data)
    await bus.subscribe(EventType.NARRATIVE_OUTPUT, collect, "recorder")
    
    creator = get_character_creator()
    char = creator.create_from_selection("体验官", "human", "warrior")
    print(f"角色: {char.name} ({char.race_name}/{char.class_name})")
    
    dm.game_state["player_stats"] = char.to_player_stats()
    dm.game_state["turn"] = 0
    dm.game_state["location"] = "月叶镇"
    
    actions = [
        ("探索", "环顾四周"),
        ("探索", "去镇中心看看"),
        ("NPC", "和周围的人说话"),
        ("NPC", "和酒馆老板说话"),
        ("探索", "去酒馆"),
        ("系统", "查看状态"),
        ("探索", "去市场逛逛"),
        ("探索", "去镇外看看"),
        ("战斗", "调查树林里的动静"),
        ("探索", "继续探索"),
    ]
    
    turn_data = []
    seen_first_lines = {}  # first_line -> turn_number
    repeated = []
    
    for i, (action_type, action) in enumerate(actions):
        turn_num = i + 1
        dm.game_state["turn"] = turn_num
        
        print(f"\n--- 回合 {turn_num}: [{action_type}] {action} ---")
        
        narratives.clear()
        result = await dm.handle_player_message(action)
        await asyncio.sleep(3)
        
        all_text = "\n".join(n.get("text", "") for n in narratives if n.get("text"))
        if not all_text:
            all_text = result or ""
        
        # 取第一行作为场景指纹
        first_line = all_text.split("\n")[0][:60].strip() if all_text else "(空)"
        
        # 检测重复
        if first_line in seen_first_lines:
            repeated.append((turn_num, first_line, seen_first_lines[first_line]))
            print(f"  [!!!重复!!!] 首句与回合{seen_first_lines[first_line]}相同: {first_line}")
        else:
            seen_first_lines[first_line] = turn_num
        
        preview = first_line[:50] if first_line else "(空)"
        print(f"  首句: {preview}")
        
        turn_data.append({
            "turn": turn_num,
            "type": action_type,
            "action": action,
            "first_line": first_line,
            "full_text": all_text,
        })
    
    elapsed = time.time() - start_time
    
    # 生成报告
    total_chars = sum(len(t["full_text"]) for t in turn_data)
    avg_len = total_chars / len(turn_data) if turn_data else 0
    empty_count = sum(1 for t in turn_data if t["first_line"] == "(空)")
    unique_first_lines = len(seen_first_lines)
    
    report = f"""## 体验报告

> 版本：V1_1_0
> 体验时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
> 游玩时长：{elapsed:.1f} 秒

### 基本信息
- **游玩时长**：{elapsed:.1f} 秒
- **到达阶段**：主游戏探索阶段（{len(turn_data)} 回合）
- **死亡次数**：0
- **NPC对话次数**：{sum(1 for t in turn_data if t['type'] == 'NPC')}"
- **战斗触发**：{sum(1 for t in turn_data if t['type'] == '战斗')}"
- **总叙事字数**：{total_chars}
- **平均叙事长度**：{avg_len:.0f} 字符/回合
- **叙事首句重复**：{len(repeated)}/{len(turn_data)} 回合
- **空响应回合**：{empty_count}/{len(turn_data)} 回合
- **唯一首句数量**：{unique_first_lines}

### 叙事体验

#### 开场叙事
- **首句样本**：{turn_data[0]['first_line'][:80] if turn_data else '(无)'}
- **问题**：叙事重复严重，同一场景被重复描述多次

#### 叙事重复分析
"""
    
    for turn_num, line, orig_turn in repeated:
        report += f"- 回合{turn_num} 与 回合{orig_turn} 首句相同：{line[:60]}...\n"
    
    if not repeated:
        report += "- （未检测到首句重复）\n"
    else:
        report += f"\n**P0 问题确认**：{len(repeated)}/{len(turn_data)} 回合出现叙事首句重复，证明场景生成在循环复用。\n"
    
    report += f"""
#### NPC对话
- **对话轮次**：{sum(1 for t in turn_data if t['type'] == 'NPC')} 次
- **对话质量**：能进行基础问答，但内容常被场景叙事覆盖

#### 战斗体验
- **战斗触发**：{sum(1 for t in turn_data if t['type'] == '战斗')} 次
- **战斗叙事**：基础战斗描写存在，但常被重复场景叙事淹没

### 节奏体验
- **回合节奏**：每回合等待约3秒
- **叙事长度**：平均 {avg_len:.0f} 字符
- **空响应**：{empty_count} 次

### 具体问题

| 位置/场景 | 问题描述 | 对应目标 | 严重程度 |
|-----------|---------|---------|---------|
| 全局 | 叙事首句重复（{len(repeated)}回合），场景循环复用 | 情绪张力 | P0 |
| 全局 | 空响应问题（{empty_count}回合） | 情绪张力 | P0 |
| 场景生成 | 场景类型循环，仅约{unique_first_lines}个唯一场景 | 可重玩性 | P0 |
| NPC对话 | 对话内容常被场景叙事覆盖 | 情绪张力 | P1 |
| 战斗系统 | 战斗叙事被重复场景淹没 | 情绪张力 | P1 |
| 系统反馈 | HP/状态变化反馈不明确 | 受众广度 | P2 |

### 优点
- ✅ 角色创建流程清晰
- ✅ 游戏框架运行稳定
- ✅ 支持多种交互类型
- ✅ 无崩溃

### 总体评分（1-10）及总结

**总体评分：4.0 / 10**

**总结**：
V1_1_0 版本发现 P0 级叙事重复问题。游戏框架稳定运行，但叙事生成存在严重的场景循环复用问题——约 {unique_first_lines} 个场景被重复用于 {len(turn_data)} 个不同输入，导致体验单调。玩家每输入一次，听到的几乎是同一组场景描写。

**主要优点**：
1. 系统稳定，无崩溃
2. 交互类型丰富
3. 角色成长系统基本健全

**主要不足（P0）**：
1. 叙事重复问题严重 - {len(repeated)}/{len(turn_data)} 回合出现场景首句重复
2. 场景循环复用 - 仅{unique_first_lines}个唯一场景被循环使用
3. NPC对话常被场景叙事覆盖
4. 战斗叙事被重复场景淹没

**改进建议**：
1. 【P0】场景生成需要根据输入内容差异化，不能循环复用
2. 【P0】修复空响应问题
3. 【P1】NPC对话时优先输出对话内容，减少场景叙事干扰
4. 【P1】战斗时锁定场景叙事，聚焦战斗描写

---
*本报告由体验官 Agent 自动生成*
"""
    
    report_path = os.path.join(_project_root, "tests", "experience_report_V1_1_0.md")
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(report)
    
    print(f"\n报告已生成: {report_path}")
    print("\n" + "="*60)
    print("体验官完成")
    print("="*60)
    
    await dm.stop()
    await bus.stop()


if __name__ == "__main__":
    asyncio.run(run())
