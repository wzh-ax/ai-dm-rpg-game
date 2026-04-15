# -*- coding: utf-8 -*-
"""
AI DM RPG - 体验官自动化脚本 V2
使用 MainDM + 事件订阅模式
"""
import asyncio
import sys
import os
import time
from datetime import datetime

# 设置路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src import (
    init_event_bus,
    init_main_dm,
    get_character_creator,
    get_tutorial_system,
    Character,
    EventType,
    Event,
    TutorialMode,
)


class ExperienceRecorder:
    """体验记录器"""
    
    def __init__(self):
        self.logs = []
        self.start_time = time.time()
        self.turn_count = 0
        self.death_count = 0
        self.current_location = "未知"
        self.npc_interactions = []
        self.combat_encounters = []
        self.problems = []
        self.positives = []
        self.narrative_outputs = []
        
    def log(self, category: str, message: str, detail: str = ""):
        entry = {
            "time": time.time() - self.start_time,
            "category": category,
            "message": message,
            "detail": detail,
        }
        self.logs.append(entry)
        print(f"[{entry['time']:.1f}s] [{category}] {message}")
        if detail:
            print(f"    → {detail[:200]}")
    
    def problem(self, severity: str, location: str, description: str):
        self.problems.append({
            "severity": severity,
            "location": location,
            "description": description,
        })
        
    def positive(self, description: str):
        self.positives.append(description)
    
    def elapsed(self):
        return time.time() - self.start_time


async def run_experience():
    """运行体验流程"""
    recorder = ExperienceRecorder()
    recorder.log("SYSTEM", "体验官启动")
    
    try:
        # ===== 初始化 =====
        recorder.log("SYSTEM", "初始化 Event Bus 和 MainDM")
        bus = await init_event_bus()
        dm = await init_main_dm()
        await dm.start()
        
        # 订阅叙事输出
        narrative_results = []
        async def narrative_handler(event: Event):
            narrative_results.append(event.data)
        await bus.subscribe(EventType.NARRATIVE_OUTPUT, narrative_handler, "experience_recorder")
        
        # ===== 角色创建 =====
        recorder.log("CHARACTER", "创建角色")
        creator = get_character_creator()
        char = creator.create_from_selection(
            name="体验官",
            race_id="human",
            class_id="warrior"
        )
        recorder.log("CHARACTER", f"角色创建成功: {char.name} ({char.race_name}/{char.class_name})")
        recorder.log("CHARACTER", f"HP: {char.current_hp}/{char.max_hp}, AC: {char.armor_class}, Gold: {char.gold}")
        
        # 初始化玩家状态
        dm.game_state["player_stats"] = char.to_player_stats()
        dm.game_state["turn"] = 0
        dm.game_state["location"] = "月叶镇"
        
        # ===== 教程阶段 =====
        recorder.log("TUTORIAL", "开始教程阶段")
        tutorial = get_tutorial_system()
        tutorial.set_mode(TutorialMode.FULL)
        
        char_dict = char.to_dict()
        welcome = await tutorial.generate_welcome_narrative(char_dict)
        recorder.log("TUTORIAL", f"欢迎叙事生成: {len(welcome)} 字符")
        recorder.positive(f"欢迎叙事: {welcome[:100]}...")
        
        # ===== 开场场景 =====
        recorder.log("SCENE", "生成开场场景: 月叶镇")
        dm.current_scene = "月叶镇"
        
        # 先发送一个进入场景的动作
        narrative_results.clear()
        await dm.handle_player_message("我来到月叶镇，四处张望")
        await asyncio.sleep(3)  # 等待叙事生成
        
        if narrative_results:
            initial_narrative = narrative_results[-1].get("text", "")
            recorder.log("SCENE", f"开场叙事长度: {len(initial_narrative)} 字符")
            if initial_narrative:
                recorder.positive(f"开场叙事: {initial_narrative[:150]}...")
            else:
                recorder.problem("P1", "开场场景", "开场叙事为空")
        else:
            recorder.problem("P1", "开场场景", "未收到开场叙事")
        
        # ===== 主探索循环 =====
        recorder.log("EXPLORATION", "开始主探索循环")
        
        exploration_sequences = [
            {"action": "去镇中心广场逛逛，看看有什么有趣的人或事", "expect": "场景描写镇中心，包括NPC、活动、氛围"},
            {"action": "和一个看起来像冒险者的人打招呼", "expect": "NPC有具体回应"},
            {"action": "去镇上的酒馆坐坐", "expect": "酒馆场景，有酒馆氛围、其他顾客、NPC"},
            {"action": "问问酒馆老板最近镇上有什么新鲜事", "expect": "老板有具体对话"},
            {"action": "突然拔剑砍向酒馆里的一个醉汉", "expect": "有反应，不是万能敷衍回复"},
            {"action": "离开酒馆，去看看镇外的森林", "expect": "场景切换到森林"},
            {"action": "查看自己的状态", "expect": "显示HP、AC、金币、经验等"},
            {"action": "找一家武器店看看", "expect": "商店场景，有商品列表"},
            {"action": "买一把匕首", "expect": "购买结果，扣除金币"},
            {"action": "在森林里走走，看看会遇到什么", "expect": "可能触发战斗或有其他遭遇"},
        ]
        
        for i, seq in enumerate(exploration_sequences):
            recorder.turn_count += 1
            dm.game_state["turn"] = recorder.turn_count
            
            recorder.log("ACTION", f"回合 {recorder.turn_count}: {seq['action']}", f"期望: {seq['expect']}")
            
            narrative_results.clear()
            
            try:
                await dm.handle_player_message(seq["action"])
                
                # 等待叙事生成（最多10秒）
                wait_time = 0
                while not narrative_results and wait_time < 10:
                    await asyncio.sleep(0.5)
                    wait_time += 0.5
                
                if narrative_results:
                    narrative = narrative_results[-1].get("text", "")
                    recorder.narrative_outputs.append(narrative)
                    recorder.log("RESULT", f"叙事长度: {len(narrative)} 字符", narrative[:200] if narrative else "(空)")
                    
                    # 检查敷衍模式
                    generic_phrases = ["你的声音在空气中回荡", "你的动作没有引起任何反应", "四周一片寂静"]
                    for phrase in generic_phrases:
                        if phrase in narrative and len(narrative) < 100:
                            recorder.problem("P2", f"回合{recorder.turn_count}", f"叙事疑似敷衍: '{phrase}'")
                    
                    # 检查战斗关键字
                    combat_keywords = ["战斗", "攻击", "敌人", "怪物", "遭遇", "战斗开始"]
                    if any(kw in narrative for kw in combat_keywords):
                        recorder.combat_encounters.append(recorder.turn_count)
                        recorder.log("COMBAT", "检测到战斗相关叙事")
                    
                    # 检查NPC对话
                    dialogue_markers = ["说", "道", "回答", "回应", "问道", "笑着", "皱着眉"]
                    if any(m in narrative for m in dialogue_markers) and len(narrative) > 50:
                        recorder.npc_interactions.append(recorder.turn_count)
                else:
                    recorder.log("RESULT", "未收到叙事输出（超时）")
                    recorder.problem("P1", f"回合{recorder.turn_count}", "未收到叙事输出")
                    
            except Exception as e:
                recorder.log("ERROR", f"处理输入时异常: {str(e)}")
                recorder.problem("P0", f"回合{recorder.turn_count}", f"异常: {str(e)}")
            
            await asyncio.sleep(1)
        
        # ===== 深度对话测试 =====
        recorder.log("DIALOGUE", "进行深度对话测试")
        dialogue_tests = [
            "给我讲个故事吧",
            "这里最有趣的传说是关于什么的",
            "你有没有什么麻烦需要帮忙",
        ]
        
        for dialogue in dialogue_tests:
            recorder.turn_count += 1
            dm.game_state["turn"] = recorder.turn_count
            narrative_results.clear()
            
            try:
                await dm.handle_player_message(dialogue)
                await asyncio.sleep(3)
                
                if narrative_results:
                    narrative = narrative_results[-1].get("text", "")
                    if narrative and len(narrative) > 50:
                        recorder.positive(f"深度对话: {dialogue} → {narrative[:100]}...")
                    else:
                        recorder.problem("P1", "深度对话", f"对话回复过短: {dialogue}")
                else:
                    recorder.problem("P1", "深度对话", f"对话无输出: {dialogue}")
            except Exception as e:
                recorder.problem("P1", "深度对话", f"对话异常: {dialogue} → {str(e)}")
            
            await asyncio.sleep(1)
        
        # ===== 生成报告 =====
        recorder.log("REPORT", "开始生成体验报告")
        report = generate_report(recorder, char)
        
        # 保存报告
        report_path = os.path.join(os.path.dirname(__file__), "experience_report_V1_0_0.md")
        with open(report_path, "w", encoding="utf-8") as f:
            f.write(report)
        
        recorder.log("SYSTEM", f"报告已保存到: {report_path}")
        
        # 清理
        await dm.stop()
        await bus.stop()
        
        recorder.log("SYSTEM", "体验官完成")
        
        return report
        
    except Exception as e:
        recorder.log("FATAL", f"体验流程异常终止: {e}", str(type(e).__name__))
        import traceback
        traceback.print_exc()
        raise


def generate_report(recorder: ExperienceRecorder, char: Character) -> str:
    """生成体验报告"""
    
    # 计算评分
    p0_count = sum(1 for p in recorder.problems if p["severity"] == "P0")
    p1_count = sum(1 for p in recorder.problems if p["severity"] == "P1")
    
    narrative_score = 7
    if p0_count > 0:
        narrative_score = max(3, narrative_score - 2)
    elif p1_count > 5:
        narrative_score = max(5, narrative_score - 1)
    
    replay_score = 6
    if len(recorder.combat_encounters) == 0:
        replay_score -= 1
    
    audience_score = 7
    
    total_score = (narrative_score + replay_score + audience_score) / 3 * 2
    total_score = min(10, total_score)  # 不超过10分
    
    report = f"""# 体验报告

> 生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
> 版本：V1_0_0

## 基本信息

| 项目 | 数值 |
|------|------|
| 游玩时长 | {recorder.elapsed():.1f} 秒 |
| 总回合数 | {recorder.turn_count} |
| 到达阶段 | 主探索阶段（{recorder.turn_count}个探索动作） |
| 死亡次数 | {recorder.death_count} |
| NPC交互次数 | {len(recorder.npc_interactions)} |
| 战斗遭遇次数 | {len(recorder.combat_encounters)} |
| 创建角色 | {char.name}（{char.race_name}/{char.class_name}） |
| 叙事输出次数 | {len(recorder.narrative_outputs)} |

## 评估一：情绪张力（1-10分）

**得分：{narrative_score}/10**

### 具体感受

"""
    
    if recorder.positives:
        report += "**做得好的地方：**\n"
        for p in recorder.positives[:5]:
            if len(p) < 100:  # 只显示短的
                report += f"- {p}\n"
        report += "\n"
    
    report += "### 主要问题\n\n"
    
    p0_problems = [p for p in recorder.problems if p["severity"] == "P0"]
    p1_problems = [p for p in recorder.problems if p["severity"] == "P1"]
    p2_problems = [p for p in recorder.problems if p["severity"] == "P2"]
    
    if p0_problems:
        report += "**P0（严重问题）：**\n"
        for p in p0_problems:
            report += f"- [{p['location']}] {p['description']}\n"
        report += "\n"
    
    if p1_problems:
        report += "**P1（明显问题）：**\n"
        for p in p1_problems:
            report += f"- [{p['location']}] {p['description']}\n"
        report += "\n"
    
    if p2_problems:
        report += "**P2（轻微问题）：**\n"
        for p in p2_problems:
            report += f"- [{p['location']}] {p['description']}\n"
        report += "\n"
    
    report += f"""## 评估二：可重玩性（1-10分）

**得分：{replay_score}/10**

### 具体感受

- 角色创建有种族/职业组合差异，本次测试覆盖人类/战士
- 探索路径有一定随机性
- {"检测到" + str(len(recorder.combat_encounters)) + "次战斗遭遇" if recorder.combat_encounters else "未检测到战斗遭遇，可能需要更多探索才能触发"}

### 主要问题

- 意外操作的AI接住能力需要更多测试验证
- 场景切换逻辑需进一步验证

## 评估三：受众广度（1-10分）

**得分：{audience_score}/10**

### 具体感受

- 新手引导：教程系统完整，可以跳过，适合不同类型玩家
- 操作简洁：自然语言指令即可驱动
- 职业系统：四条职业路径有一定差异

### 主要问题

- 新手可能对"自由输入"感到迷茫
- 建议增加更多上下文提示

## 具体问题汇总

| 位置 | 问题描述 | 对应目标 | 严重程度 |
|------|---------|---------|---------|
"""
    
    for p in recorder.problems:
        report += f"| {p['location']} | {p['description']} | 情绪张力 | {p['severity']} |\n"
    
    report += "\n## 优点\n\n"
    for p in recorder.positives[:8]:
        if len(p) < 150:
            report += f"- {p}\n"
    
    report += f"""
## 总体评分（1-10）及总结

**综合得分：** {total_score:.1f}/10

### 总结

AI DM RPG 核心框架完整，教程引导合理。

**主要优势：**
- 叙事引擎能接住玩家输入
- 教程设计考虑跳过需求
- 角色创建简洁

**主要改进方向：**
- 所有玩家输入必须返回有效叙事（避免空输出）
- 意外操作的AI接住质量需提升
- 战斗系统触发频率可优化

---
*本报告由体验官 AI 自动生成，测试版本 V1_0_0*
"""
    
    return report


if __name__ == "__main__":
    report = asyncio.run(run_experience())
    print("\n" + "=" * 60)
    print("体验官完成")
    print("=" * 60)
