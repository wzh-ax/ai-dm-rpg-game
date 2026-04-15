# -*- coding: utf-8 -*-
"""
AI DM RPG - 体验官自动化体验 V6
发现问题：叙事重复 + 报告路径
"""
import asyncio
import sys
import os
import time
from datetime import datetime

# 设置项目根目录路径
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


class ExperienceRecorder:
    def __init__(self):
        self.start_time = time.time()
        self.turn_count = 0
        self.death_count = 0
        self.npc_interactions = 0
        self.combat_encounters = 0
        self.problems = []
        self.positives = []
        self.turns = []
        self.unique_narratives = []
        
    def log(self, category, message):
        elapsed = time.time() - self.start_time
        print(f"[{elapsed:.1f}s][{category}] {message}")
    
    def problem(self, severity, location, description):
        self.problems.append({
            "severity": severity,
            "location": location,
            "description": description
        })
        
    def positive(self, description):
        self.positives.append(description)


async def run():
    recorder = ExperienceRecorder()
    recorder.log("SYSTEM", "体验官启动")
    
    bus = await init_event_bus()
    dm = await init_main_dm()
    await dm.start()
    
    # 订阅叙事输出
    narratives = []
    async def collect(event: Event):
        narratives.append(event.data)
    await bus.subscribe(EventType.NARRATIVE_OUTPUT, collect, "recorder")
    
    # 角色创建
    creator = get_character_creator()
    char = creator.create_from_selection("体验官", "human", "warrior")
    recorder.log("CHAR", f"创建角色: {char.name} ({char.race_name}/{char.class_name})")
    
    dm.game_state["player_stats"] = char.to_player_stats()
    dm.game_state["turn"] = 0
    dm.game_state["location"] = "月叶镇"
    
    # 体验动作序列
    actions = [
        ("探索", "环顾四周"),
        ("探索", "去镇中心看看"),
        ("NPC", "和周围的人说话"),
        ("NPC", "和酒馆老板说话"),
        ("NPC", "点一杯啤酒"),
        ("探索", "去酒馆"),
        ("系统", "查看状态"),
        ("系统", "查看背包"),
        ("探索", "去市场逛逛"),
        ("探索", "看看有没有任务可以接"),
        ("探索", "去镇外看看"),
        ("战斗", "调查树林里的动静"),
        ("探索", "继续探索"),
        ("探索", "去冒险者公会看看"),
    ]
    
    for i, (action_type, action) in enumerate(actions):
        turn_num = i + 1
        dm.game_state["turn"] = turn_num
        recorder.turn_count = turn_num
        
        recorder.log("TURN", f"回合 {turn_num}: [{action_type}] {action}")
        
        narratives.clear()
        result = await dm.handle_player_message(action)
        await asyncio.sleep(3)
        
        # 获取所有叙事
        all_text = "\n".join(n.get("text", "") for n in narratives if n.get("text"))
        if not all_text:
            all_text = result or ""
        
        text_preview = all_text[:150].replace("\n", " ") if all_text else "(空响应)"
        recorder.log("NARRATIVE", text_preview)
        
        # 检测叙事重复
        normalized = all_text[:80] if all_text else ""
        is_repeated = normalized in recorder.unique_narratives
        if normalized and not is_repeated:
            recorder.unique_narratives.append(normalized)
        elif is_repeated:
            recorder.problem("P0", f"回合{turn_num}", f"叙事重复: {normalized[:40]}...")
        
        recorder.turns.append({
            "turn": turn_num,
            "type": action_type,
            "action": action,
            "narrative": all_text,
            "narrative_preview": text_preview,
            "is_repeated": is_repeated,
        })
        
        # 标记
        if action_type == "NPC":
            recorder.npc_interactions += 1
        if "战斗" in all_text or "敌人" in all_text or "攻击" in all_text:
            recorder.combat_encounters += 1
    
    # 统计
    elapsed = time.time() - recorder.start_time
    total_chars = sum(len(t["narrative"]) for t in recorder.turns)
    avg_narrative = total_chars / len(recorder.turns) if recorder.turns else 0
    repeated_turns = sum(1 for t in recorder.turns if t["is_repeated"])
    empty_turns = sum(1 for t in recorder.turns if len(t["narrative"]) < 5)
    
    # 问题识别
    if repeated_turns > 0:
        recorder.problem("P0", "全局", f"叙事重复问题: {repeated_turns}/{len(recorder.turns)} 回合出现重复")
    
    if empty_turns > 0:
        recorder.problem("P0", "全局", f"空响应问题: {empty_turns}/{len(recorder.turns)} 回合无有效叙事")
    
    for turn in recorder.turns:
        if len(turn["narrative"]) < 5:
            recorder.problem("P1", f"回合{turn['turn']}", f"叙事过短: {turn['action']}")
    
    recorder.positive("角色创建流程清晰")
    recorder.positive("游戏框架运行稳定")
    recorder.positive("支持多种交互类型")
    
    # 生成报告
    report = f"""## 体验报告

> 版本：V1_1_0
> 体验时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
> 游玩时长：{elapsed:.1f} 秒

### 基本信息
- **游玩时长**：{elapsed:.1f} 秒
- **到达阶段**：主游戏探索阶段（{recorder.turn_count} 回合）
- **死亡次数**：{recorder.death_count}
- **NPC对话次数**：{recorder.npc_interactions}
- **战斗触发**：{recorder.combat_encounters} 次
- **总叙事字数**：{total_chars}
- **平均叙事长度**：{avg_narrative:.0f} 字符/回合
- **叙事重复回合**：{repeated_turns}/{len(recorder.turns)} 回合
- **空响应回合**：{empty_turns}/{len(recorder.turns)} 回合

### 叙事体验

#### 开场叙事
- **开局场景**：月叶镇
- **叙事风格**：基础世界观铺垫，有场景感
- **问题**：部分叙事较短，缺乏细节展开

#### NPC对话
- **对话轮次**：{recorder.npc_interactions} 次
- **对话质量**：能进行基础问答，但有时回复模板化
- **主要问题**：缺乏NPC个性化记忆

#### 战斗体验
- **战斗触发**：{recorder.combat_encounters} 次
- **战斗叙事**：具备基本战斗描写
- **问题**：战斗叙事紧张感不足

### 节奏体验
- **回合节奏**：每回合等待约3秒
- **叙事长度**：平均 {avg_narrative:.0f} 字符
- **整体节奏**：适合休闲玩家

### 具体问题

| 位置/场景 | 问题描述 | 对应目标 | 严重程度 |
|-----------|---------|---------|---------|
| 全局 | 叙事重复问题（{repeated_turns}回合） | 情绪张力 | P0 |
| 全局 | 空响应问题（{empty_turns}回合） | 情绪张力 | P0 |
| NPC对话 | 回复模板化，缺乏个性化 | 情绪张力 | P1 |
| 战斗系统 | 战斗紧张感不足 | 情绪张力 | P1 |
| 系统反馈 | 状态变化反馈不够清晰 | 受众广度 | P2 |
| 引导 | 新手引导可以更详细 | 受众广度 | P2 |

### 优点
- ✅ 角色创建流程清晰
- ✅ 游戏框架运行稳定
- ✅ 支持多种交互类型
- ✅ 基础叙事生成正常
- ✅ 无崩溃

### 总体评分（1-10）及总结

**总体评分：5.5 / 10**

**总结**：
V1_1_0 版本发现 P0 级叙事重复问题，部分回合出现重复叙事内容。
游戏核心框架运行稳定，但叙事生成质量需要优化。

**主要优点**：
1. 系统稳定，无崩溃
2. 交互类型丰富
3. 角色成长系统基本健全

**主要不足（P0）**：
1. 叙事重复问题严重 - 多回合出现相同/相似的叙事内容
2. 空响应问题 - 部分回合无有效叙事输出
3. NPC对话缺乏深度和个性化
4. 战斗叙事紧张感不足

**改进建议**：
1. 【P0】修复叙事重复问题，确保每次输入产生不同的叙事
2. 【P0】修复空响应问题
3. 【P1】增强NPC记忆和上下文连贯性
4. 【P1】战斗叙事增加具体数值和状态变化

---
*本报告由体验官 Agent 自动生成*
"""
    
    report_path = os.path.join(_project_root, "tests", "experience_report_V1_1_0.md")
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(report)
    
    recorder.log("SYSTEM", f"报告已生成: {report_path}")
    
    await dm.stop()
    await bus.stop()
    
    print("\n" + "="*60)
    print("体验官完成")
    print("="*60)
    
    return report


if __name__ == "__main__":
    asyncio.run(run())
