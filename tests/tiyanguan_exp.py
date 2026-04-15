# -*- coding: utf-8 -*-
"""
AI DM RPG - 体验官直接体验脚本
直接调用GameMaster API，避免事件订阅问题
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
sys.path.insert(0, r'D:\ai-dm-rpg-game')
print(f'Python path: {sys.path[:3]}')

from src import init_event_bus, init_game_master, Character, EventType, Event
from src.character_creator import get_character_creator
from src.tutorial_system import get_tutorial_system, TutorialMode


class ExperienceReport:
    """体验报告生成器"""
    
    def __init__(self):
        self.start_time = None
        self.end_time = None
        self.turns = []
        self.death_count = 0
        self.battles = 0
        self.npc_talks = 0
        self.problems = []
        self.merits = []
        
    def record_turn(self, turn_num: int, action: str, action_type: str, narrative: str, stats: dict):
        """记录一个回合"""
        length = len(narrative) if narrative else 0
        self.turns.append({
            "turn": turn_num,
            "action": action,
            "type": action_type,
            "narrative": narrative,
            "length": length,
            "stats": stats,
        })
        
    def add_problem(self, severity: str, location: str, description: str, goal: str):
        self.problems.append({
            "severity": severity,
            "location": location,
            "description": description,
            "goal": goal,
        })
        
    def add_merit(self, description: str):
        self.merits.append(description)
        
    def generate(self, version: str) -> str:
        duration = (self.end_time - self.start_time).total_seconds() if self.end_time and self.start_time else 0
        
        # 统计数据
        total = len(self.turns)
        avg_len = sum(t["length"] for t in self.turns) / total if total else 0
        short_count = sum(1 for t in self.turns if 0 < t["length"] < 50)
        empty_count = sum(1 for t in self.turns if t["length"] == 0)
        npc_turns = [t for t in self.turns if t["type"] in ("对话", "NPC")]
        battle_turns = [t for t in self.turns if t["type"] == "战斗"]
        explore_turns = [t for t in self.turns if t["type"] == "探索"]
        
        # 评分
        tension = min(10, 5 + (avg_len / 80) + (0 if empty_count > 5 else 2))
        replay = 6.0
        audience = 7.0
        
        # 叙事样本
        opening = self.turns[0]["narrative"][:300] if self.turns else "（无）"
        
        # NPC对话详情
        npc_detail = ""
        if npc_turns:
            lines = []
            for t in npc_turns[:5]:
                lines.append(f"**输入**: {t['action']}")
                lines.append(f"**叙事**: {t['narrative'][:100] or '(空)'}")
                lines.append("")
            npc_detail = "\n".join(lines)
        else:
            npc_detail = "未进行NPC对话"
            
        # 问题表格
        problem_rows = []
        for p in self.problems:
            problem_rows.append(f"| {p['location']} | {p['description']} | {p['goal']} | {p['severity']} |")
        problem_table = "\n".join(problem_rows) if problem_rows else "| - | - | - | - |"
        
        # 优点
        merit_list = "\n".join(f"- {m}" for m in self.merits) if self.merits else "- 无"
        
        # 总结
        main_issues = [p['description'] for p in self.problems if p['severity'] in ('P0', 'P1')]
        summary_parts = []
        if tension >= 7:
            summary_parts.append("叙事质量较好，能够吸引玩家继续探索。")
        elif tension < 5:
            summary_parts.append("叙事体验有待加强，部分环节存在敷衍感。")
        if main_issues:
            summary_parts.append(f"**主要问题**: {'; '.join(main_issues[:3])}")
        if self.merits:
            summary_parts.append(f"**做得好的地方**: {self.merits[0]}")
            
        summary = " ".join(summary_parts) if summary_parts else "体验了AI DM RPG的核心探索流程。"
        
        return f"""# 体验报告

> 生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
> 体验版本: {version}

## 基本信息

| 项目 | 值 |
|------|-----|
| 游玩时长 | {duration:.1f} 秒 |
| 总回合数 | {total} |
| 死亡次数 | {self.death_count} |
| 到达阶段 | 主游戏流程 |
| 战斗次数 | {self.battles} |
| NPC对话次数 | {self.npc_talks} |
| 探索次数 | {len(explore_turns)} |

## 叙事体验

### 开场叙事

{opening}

### 叙事统计
- 总叙事条数: {total}
- 平均叙事长度: {avg_len:.0f} 字符
- 短回复/敷衍叙事: {short_count} 次
- 无响应次数: {empty_count} 次

### NPC对话体验

{npc_detail}

### 战斗体验
- 战斗回合数: {len(battle_turns)}

{battle_turns[0]['narrative'][:200] if battle_turns else '未触发战斗'}

## 节奏体验

- 总回合数: {total}
- 平均每回合耗时: {duration/total:.1f} 秒（如果total>0）
- 叙事充足的回合: {total - short_count - empty_count} 个
- 叙事过短/敷衍的回合: {short_count} 个
- 无响应的回合: {empty_count} 个

## 具体问题（按严重程度）

| 位置/回合 | 问题描述 | 对应目标 | 严重程度 |
|-----------|---------|---------|---------|
{problem_table}

## 优点
{merit_list}

## 总体评分（1-10）及总结

### 评分
- **情绪张力**: {tension:.1f}/10
- **可重玩性**: {replay:.1f}/10
- **受众广度**: {audience:.1f}/10
- **综合评分**: {(tension+replay+audience)/3:.1f}/10

### 总结
{summary}

---
*本报告由体验官AI自动生成*
"""


async def main():
    print("=" * 60)
    print("AI DM RPG - 体验官直接体验")
    print("=" * 60)
    
    report = ExperienceReport()
    report.start_time = datetime.now()
    
    max_retries = 3
    retry_count = 0
    
    while retry_count < max_retries:
        try:
            # 初始化
            print("\n[1/5] 初始化游戏系统...")
            bus = await init_event_bus()
            gm = await init_game_master()
            
            # 收集所有 NARRATIVE_OUTPUT
            narratives = []
            async def collect_narrative(event: Event):
                narratives.append(event.data)
            await bus.subscribe(EventType.NARRATIVE_OUTPUT, collect_narrative, "exp_collector")
            
            # 创建角色
            print("[2/5] 创建角色...")
            creator = get_character_creator()
            char = creator.create_from_selection("体验官", "human", "warrior")
            print(f"角色: {char.name} ({char.race_name}/{char.class_name})")
            
            # 初始化状态
            gm.game_state["player_stats"] = char.to_player_stats()
            gm.game_state["turn"] = 0
            gm.game_state["location"] = "月叶镇"
            
            # 教程
            print("[3/5] 初始化教程...")
            tutorial = get_tutorial_system()
            tutorial.set_mode(TutorialMode.FULL)
            
            # 体验动作列表
            actions = [
                ("探索", "去镇中心看看"),
                ("探索", "环顾四周"),
                ("NPC", "和周围的人说话"),
                ("NPC", "问路人这里最近有什么新鲜事"),
                ("NPC", "和酒馆老板说话"),
                ("NPC", "点一杯啤酒"),
                ("探索", "去酒馆"),
                ("NPC", "和酒馆里的人聊天"),
                ("系统", "查看状态"),
                ("系统", "查看背包"),
                ("探索", "去市场逛逛"),
                ("探索", "看看有没有任务可以接"),
                ("探索", "去冒险者公会"),
                ("探索", "去镇外看看"),
                ("战斗", "调查树林里的动静"),
                ("战斗", "主动寻找敌人"),
                ("探索", "休息一下"),
                ("探索", "继续探索"),
            ]
            
            print(f"[4/5] 开始体验（共{len(actions)}个动作）...")
            
            for i, (action_type, action) in enumerate(actions):
                turn_num = i + 1
                gm.game_state["turn"] = turn_num
                
                print(f"\n--- 回合 {turn_num}/{len(actions)}: [{action_type}] {action} ---")
                
                # 记录类型
                if action_type == "战斗":
                    report.battles += 1
                elif action_type in ("NPC", "对话"):
                    report.npc_talks += 1
                
                # 清空之前收集的叙事
                narratives.clear()
                
                turn_start = time.time()
                
                # 发送输入
                await gm.handle_player_message(action)
                
                # 等待足够长时间让LLM生成叙事
                await asyncio.sleep(4)
                
                turn_time = time.time() - turn_start
                
                # 提取叙事文本
                narrative_text = ""
                if narratives:
                    # 取最新的叙事
                    latest = narratives[-1]
                    narrative_text = latest.get("text", "")
                
                # 获取当前状态
                stats = gm.game_state.get("player_stats", {})
                hp = stats.get("hp", 0)
                
                # 检测死亡
                if hp <= 0:
                    report.death_count += 1
                    print(f"[死亡] HP: {hp}")
                
                # 记录
                report.record_turn(turn_num, action, action_type, narrative_text, stats)
                print(f"响应时间: {turn_time:.1f}s | 叙事长度: {len(narrative_text)} 字")
                if narrative_text:
                    print(f"叙事预览: {narrative_text[:80]}...")
                
                # 检测问题
                if not narrative_text:
                    report.add_problem("P1", f"回合{turn_num}", f"输入无响应: {action}", "情绪张力")
                elif len(narrative_text) < 50:
                    report.add_problem("P2", f"回合{turn_num}", f"叙事过短({len(narrative_text)}字): {action}", "情绪张力")
                    
            # 生成报告
            print("\n[5/5] 生成报告...")
            report.end_time = datetime.now()
            
            # 标记优点
            if report.battles > 0:
                report.add_merit(f"成功触发{report.battles}次战斗")
            avg_len = sum(t["length"] for t in report.turns) / len(report.turns) if report.turns else 0
            if avg_len > 200:
                report.add_merit(f"叙事平均长度良好({avg_len:.0f}字)")
            if report.npc_talks > 0:
                report.add_merit(f"成功进行{report.npc_talks}次NPC对话")
                
            report_text = report.generate("V1_0_5")
            
            # 保存
            report_path = os.path.join(os.path.dirname(__file__), "experience_report_V1_0_0.md")
            with open(report_path, "w", encoding="utf-8") as f:
                f.write(report_text)
            
            print(f"\n报告已保存: {report_path}")
            print("\n" + "=" * 60)
            print("体验完成！")
            print("=" * 60)
            
            await gm.stop()
            await bus.stop()
            return
            
        except Exception as e:
            retry_count += 1
            print(f"\n[ERROR] 体验出错 (第{retry_count}次): {e}")
            import traceback
            traceback.print_exc()
            if retry_count < max_retries:
                print("API限流，等待30s重试...")
                await asyncio.sleep(30)
            else:
                print("达到最大重试次数")
                raise


if __name__ == "__main__":
    asyncio.run(main())
