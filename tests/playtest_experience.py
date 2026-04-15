# -*- coding: utf-8 -*-
"""
AI DM RPG - 体验官自动体验脚本
用于自动化游戏体验审计
"""
import asyncio
import sys
import os
import time
from datetime import datetime

# Windows 控制台 UTF-8 修复
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# 设置路径
_script_dir = os.path.dirname(os.path.abspath(__file__))
_project_root = os.path.dirname(_script_dir)  # tests -> game root
sys.path.insert(0, _project_root)

from src import (
    init_event_bus,
    init_game_master,
    get_character_creator,
    get_tutorial_system,
    TutorialMode,
    Event,
    EventType,
)


class ExperienceRecorder:
    """体验记录器"""
    
    def __init__(self):
        self.narratives = []  # 所有叙事记录
        self.combat_logs = []  # 战斗记录
        self.npc_dialogues = []  # NPC对话记录
        self.problems = []  # 问题记录
        self.start_time = None
        self.end_time = None
        self.death_count = 0
        self.turn_count = 0
        self.current_scene = "未知"
        self.hp_history = []
        self.mode = "探索"  # 探索/战斗/对话
        
    def record_narrative(self, text: str, turn: int, mode: str = "探索"):
        """记录叙事"""
        self.narratives.append({
            "turn": turn,
            "text": text,
            "mode": mode,
            "length": len(text),
        })
        self.mode = mode
        
    def record_combat(self, log: str):
        """记录战斗"""
        self.combat_logs.append(log)
        
    def record_npc_dialogue(self, npc: str, dialogue: str):
        """记录NPC对话"""
        self.npc_dialogues.append({
            "npc": npc,
            "dialogue": dialogue,
            "length": len(dialogue),
        })
        
    def add_problem(self, location: str, description: str, severity: str, related_goal: str):
        """添加问题"""
        self.problems.append({
            "location": location,
            "description": description,
            "severity": severity,
            "related_goal": related_goal,
        })
        
    def set_scene(self, scene: str):
        """设置当前场景"""
        self.current_scene = scene


class ExperienceAuditor:
    """体验审计员"""
    
    def __init__(self):
        self.recorder = ExperienceRecorder()
        self.api_retry_count = 0
        self.max_retries = 3
        
    async def run(self):
        """执行完整游戏体验"""
        print("=" * 60)
        print("🎮 AI DM RPG - 体验官自动体验开始")
        print("=" * 60)
        
        self.recorder.start_time = datetime.now()
        
        try:
            # 初始化
            print("\n[1/6] 初始化游戏系统...")
            bus = await init_event_bus()
            master = await init_game_master()
            
            # 创建角色
            print("[2/6] 创建角色...")
            character = await self._create_character(master)
            if character is None:
                self._add_problem("角色创建", "角色创建失败", "P0", "受众广度")
                return None
            
            # 教程体验
            print("[3/6] 体验教程...")
            await self._experience_tutorial(master, character)
            
            # 主游戏体验
            print("[4/6] 主游戏探索...")
            await self._explore_main_game(master, character)
            
            # 清理
            print("[5/6] 清理资源...")
            await master.stop()
            await bus.stop()
            
        except Exception as e:
            print(f"\n❌ 游戏过程中出错: {e}")
            import traceback
            traceback.print_exc()
            self._add_problem("游戏崩溃", f"错误: {str(e)}", "P0", "情绪张力")
            return None
            
        finally:
            self.recorder.end_time = datetime.now()
            
        # 生成报告
        print("[6/6] 生成体验报告...")
        report = await self._generate_report()
        
        print("\n" + "=" * 60)
        print("✅ 体验官自动体验完成")
        print("=" * 60)
        
        return report
        
    async def _create_character(self, master) -> dict:
        """创建角色"""
        creator = get_character_creator()
        
        # 使用预设选择创建角色
        char = creator.create_from_selection(
            name="体验官测试",
            race_id="human",
            class_id="warrior"
        )
        
        if char is None:
            return None
            
        print(f"  角色创建成功: {char.name} ({char.race_name}/{char.class_name})")
        
        # 初始化玩家状态
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
        
        return char
        
    async def _experience_tutorial(self, master, character):
        """体验教程阶段"""
        tutorial = get_tutorial_system()
        tutorial.set_mode(TutorialMode.QUICK)  # 快速入门模式
        
        print("  教程模式: 快速入门")
        
        # 生成欢迎叙事
        welcome = await tutorial.generate_welcome_narrative(character.to_dict())
        self.recorder.record_narrative(welcome, 0, "教程")
        print(f"  欢迎叙事: {len(welcome)} 字符")
        
        # 开场场景
        print("  生成开场场景...")
        scene = await master._generate_scene('月叶镇')
        self.recorder.record_narrative(scene, 0, "探索")
        self.recorder.set_scene("月叶镇")
        print(f"  开场场景: {len(scene)} 字符")
        
    async def _explore_main_game(self, master, character):
        """探索主游戏"""
        # 定义探索动作序列
        exploration_actions = [
            # 探索镇中心
            ("探索镇中心", "exploration", "探索镇中心，环顾四周"),
            ("与镇民交谈", "dialogue", "和周围的镇民交谈"),
            ("去酒馆", "transition", "前往镇上的酒馆"),
            ("与酒馆老板交谈", "dialogue", "和酒馆老板聊天"),
            ("听酒馆里的人聊天", "exploration", "听听酒馆里其他人在聊什么"),
            ("询问任务", "dialogue", "向酒馆里的人询问有没有任务"),
            ("离开酒馆", "transition", "离开酒馆"),
            ("去商店", "transition", "去镇上的商店看看"),
            ("与店主交谈", "dialogue", "和商店老板交谈"),
            ("查看商品", "exploration", "看看商店里卖什么"),
            ("离开商店", "transition", "离开商店"),
            ("去镇外", "transition", "走出镇子，探索野外"),
        ]
        
        turn = master.game_state["turn"]
        
        for action_name, action_type, action_text in exploration_actions:
            turn += 1
            self.recorder.turn_count = turn
            print(f"  回合 {turn}: {action_name}...")
            
            try:
                result = await self._safe_handle_input(master, action_text)
                
                if result:
                    self.recorder.record_narrative(result, turn, action_type)
                    
                    # 检查HP状态
                    stats = master.game_state.get("player_stats", {})
                    hp = stats.get("hp", 0)
                    self.recorder.hp_history.append(hp)
                    
                    # 检查是否死亡
                    if hp <= 0:
                        self.recorder.death_count += 1
                        print(f"    💀 玩家死亡! (死亡次数: {self.recorder.death_count})")
                        break
                        
                    # 检查是否进入战斗
                    if "combat" in master.mode.lower() or "战斗" in result:
                        self.recorder.record_combat(result)
                        
                    # 提取NPC对话
                    if "npc" in action_type or "对话" in action_type:
                        self.recorder.record_npc_dialogue("未知NPC", result[:200])
                        
                # 更新位置
                location = master.game_state.get("location", "未知")
                self.recorder.set_scene(location)
                    
            except Exception as e:
                print(f"    ⚠️ 处理输入时出错: {e}")
                self._add_problem(f"回合{turn}:{action_name}", str(e), "P1", "情绪张力")
                await asyncio.sleep(1)  # 等待一下
                
        master.game_state["turn"] = turn
        
    async def _safe_handle_input(self, master, text: str) -> str:
        """安全地处理输入，带重试机制"""
        for retry in range(self.max_retries):
            try:
                # 使用事件总线方式
                from src import Event, EventType
                
                result_text = None
                
                async def capture_output(event: Event):
                    nonlocal result_text
                    if event.type == EventType.NARRATIVE_OUTPUT:
                        result_text = event.data.get("text", "")
                        
                # 订阅输出
                sub_id = f"playtest_{id(text)}"
                await master.event_bus.subscribe(EventType.NARRATIVE_OUTPUT, capture_output, sub_id)
                
                # 发送输入
                await master.event_bus.publish(Event(
                    type=EventType.PLAYER_INPUT,
                    data={"text": text},
                    source="playtest"
                ))
                
                # 等待结果
                wait_count = 0
                while result_text is None and wait_count < 30:
                    await asyncio.sleep(0.5)
                    wait_count += 1
                    
                # 取消订阅
                await master.event_bus.unsubscribe(EventType.NARRATIVE_OUTPUT, sub_id)
                
                if result_text:
                    return result_text
                else:
                    print(f"    ⚠️ 等待叙事输出超时 (重试 {retry + 1}/{self.max_retries})")
                    
            except Exception as e:
                if "429" in str(e) or "rate" in str(e).lower() or "限流" in str(e):
                    print(f"    ⏳ API限流，等待30秒重试 (第 {retry + 1} 次)...")
                    await asyncio.sleep(30)
                else:
                    raise
                    
        return "(叙事获取失败)"
        
    def _add_problem(self, location: str, description: str, severity: str, related_goal: str):
        """添加问题"""
        self.recorder.add_problem(location, description, severity, related_goal)
        
    async def _generate_report(self) -> str:
        """生成体验报告"""
        recorder = self.recorder
        
        # 计算体验时长
        duration = recorder.end_time - recorder.start_time if recorder.end_time else None
        duration_str = str(duration).split('.')[0] if duration else "未知"
        
        # 统计叙事长度
        total_narrative_chars = sum(n["length"] for n in recorder.narratives)
        avg_narrative_len = total_narrative_chars / len(recorder.narratives) if recorder.narratives else 0
        
        # 评估叙事质量
        short_narratives = [n for n in recorder.narratives if n["length"] < 100]
        empty_narratives = [n for n in recorder.narratives if n["length"] < 30]
        
        # 生成报告
        report = f"""## 体验报告

> 生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
> 版本: V1_0_3

### 基本信息

| 项目 | 值 |
|------|-----|
| 游玩时长 | {duration_str} |
| 到达回合 | 回合 {recorder.turn_count} |
| 死亡次数 | {recorder.death_count} |
| 叙事条数 | {len(recorder.narratives)} |
| 总叙事字符 | {total_narrative_chars} |
| 平均叙事长度 | {avg_narrative_len:.0f} 字符 |
| 战斗次数 | {len(recorder.combat_logs)} |
| NPC对话次数 | {len(recorder.npc_dialogues)} |
| 当前场景 | {recorder.current_scene} |

### 评估一：情绪张力（1-10分）

**得分: 待评估**

#### 具体感受

"""

        # 分析叙事引人入胜程度
        if short_narratives:
            report += f"- ⚠️ 存在 {len(short_narratives)} 条过短的叙事（<100字符），可能缺乏细节描写\n"
        if empty_narratives:
            report += f"- ❌ 存在 {len(empty_narratives)} 条极短叙事（<30字符），可能是敷衍或错误\n"
            
        if avg_narrative_len > 200:
            report += f"- ✅ 平均叙事长度 {avg_narrative_len:.0f} 字符，叙事较充实\n"
        elif avg_narrative_len > 100:
            report += f"- ⚠️ 平均叙事长度 {avg_narrative_len:.0f} 字符，可能偏简略\n"
        else:
            report += f"- ❌ 平均叙事长度仅 {avg_narrative_len:.0f} 字符，叙事严重不足\n"
            
        report += f"- 📍 场景切换次数: {len([n for n in recorder.narratives if n['mode'] == 'transition'])}\n"
        
        report += """
#### 主要问题

"""

        # 检查敷衍感
        template_phrases = [
            "你的声音在空气中回荡",
            "你的身影在月光下",
            "你感觉一阵寒意",
            "四周一片寂静",
        ]
        
        for narrative in recorder.narratives[:5]:  # 检查前5条
            for phrase in template_phrases:
                if phrase in narrative["text"]:
                    self._add_problem(
                        f"回合{narrative['turn']}",
                        f"可能使用了万能敷衍模板: {phrase}",
                        "P1",
                        "情绪张力"
                    )
                    
        if recorder.problems:
            for p in recorder.problems[:5]:
                report += f"- **{p['severity']}** {p['location']}: {p['description']}\n"
        else:
            report += "- 暂未发现明显问题\n"
            
        report += f"""
### 评估二：可重玩性（1-10分）

**得分: 待评估**

#### 具体感受

- 探索回合数: {recorder.turn_count}
- 场景类型: {len(set(n['mode'] for n in recorder.narratives))} 种
- NPC对话样本: {len(recorder.npc_dialogues)} 条

#### 主要问题

- 每次开局角色创建选项: 4种族 × 4职业 = 16种组合
- 探索路径是否随机化: 待观察
- 场景/NPC是否有随机性: 待观察

### 评估三：受众广度（1-10分）

**得分: 待评估**

#### 具体感受

- 新手引导: {"快速入门" if len(recorder.narratives) > 0 else "未体验"}
- 操作说明: {"已包含" if any("帮助" in n['text'] or "help" in n['text'].lower() for n in recorder.narratives) else "未包含"}
- 难度曲线: {"合理" if recorder.death_count == 0 else f"较难(死亡{recorder.death_count}次)"}

#### 主要问题

- 新手是否知道该做什么: 待观察
- 是否有明确的任务指引: 待观察
- 系统命令是否易于发现: 待观察

### 具体问题列表

| 位置 | 问题描述 | 对应目标 | 严重程度 |
|------|---------|---------|---------|
"""

        if recorder.problems:
            for p in recorder.problems:
                report += f"| {p['location']} | {p['description']} | {p['related_goal']} | {p['severity']} |\n"
        else:
            report += "| - | 暂未发现具体问题 | - | - |\n"
            
        report += """
### 优点

"""
        # 列举做得好的地方
        if avg_narrative_len > 150:
            report += f"- ✅ 叙事长度适中（平均 {avg_narrative_len:.0f} 字符），阅读体验良好\n"
        if recorder.turn_count > 10:
            report += f"- ✅ 游戏流程完整（体验了 {recorder.turn_count} 个回合）\n"
        if len(recorder.combat_logs) > 0:
            report += f"- ✅ 包含战斗环节（{len(recorder.combat_logs)} 次）\n"
        if len(recorder.npc_dialogues) > 0:
            report += f"- ✅ 包含NPC对话（{len(recorder.npc_dialogues)} 次）\n"
            
        if not any(line.startswith("- ✅") for line in report.split("\n")[-10:]):
            report += "- ⚠️ 体验数据不足，难以总结优点\n"
            
        report += f"""
### 叙事样本（按时间顺序）

"""
        for i, narrative in enumerate(recorder.narratives[:5]):
            text_preview = narrative["text"][:150].replace("\n", " ").strip()
            report += f"**{i+1}. 回合{narrative['turn']} [{narrative['mode']}]**\n> {text_preview}...\n\n"
            
        if len(recorder.narratives) > 5:
            report += f"_...还有 {len(recorder.narratives) - 5} 条叙事_"
            
        report += f"""

### 总体评分（1-10）及总结

**综合评分: 待人工评估**

**总结:**

本次自动体验覆盖了游戏的核心流程：
- 角色创建 → 教程 → 探索 → 场景切换 → NPC对话

体验数据：
- 共 {len(recorder.narratives)} 条叙事
- {recorder.turn_count} 个游戏回合
- {len(recorder.combat_logs)} 次战斗
- {len(recorder.npc_dialogues)} 次NPC对话
- {recorder.death_count} 次死亡

由于是自动脚本体验，缺乏真实玩家的主观感受。建议人工复核报告中的「叙事样本」部分，结合实际体验给出最终评分。

---

*本报告由体验官 AI 自动生成*
"""
        
        # 保存报告
        report_path = os.path.join(os.path.dirname(__file__), "experience_report_V1_0_3.md")
        with open(report_path, "w", encoding="utf-8") as f:
            f.write(report)
            
        print(f"  报告已保存到: {report_path}")
        
        return report


async def main():
    auditor = ExperienceAuditor()
    report = await auditor.run()
    
    if report:
        print("\n" + "=" * 60)
        print("报告预览（前2000字符）:")
        print("=" * 60)
        print(report[:2000])
    

if __name__ == "__main__":
    asyncio.run(main())
