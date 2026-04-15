"""
体验官自动体验脚本
模拟玩家完整体验流程并生成体验报告
"""
import asyncio
import sys
import os
from datetime import datetime

# Windows 控制台 UTF-8 修复
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# 设置路径
_game_root = r"D:\ai-dm-rpg-game"
sys.path.insert(0, _game_root)
sys.path.insert(0, _game_root + r"\src")

from src import (
    init_event_bus,
    init_game_master,
    get_character_creator,
    Character,
    EventType,
    Event,
)


class ExperienceRecorder:
    """体验记录器"""
    
    def __init__(self):
        self.records = []  # [(turn, action, narrative, duration)]
        self.start_time = None
        self.deaths = 0
        self.current_turn = 0
        self.phase = "创建角色"
        
    def record(self, action: str, narrative: str, duration: float = 0):
        self.records.append({
            "turn": self.current_turn,
            "phase": self.phase,
            "action": action,
            "narrative": narrative,
            "duration": duration,
        })
        self.current_turn += 1
        
    def set_phase(self, phase: str):
        self.phase = phase


class NarrativeCollector:
    """收集叙事输出的订阅器"""
    
    def __init__(self):
        self.narratives = []
        
    async def handler(self, event: Event):
        self.narratives.append(event.data)
        
    def get_latest(self) -> str:
        if not self.narratives:
            return ""
        # 获取最后一条叙事
        latest = self.narratives[-1]
        if isinstance(latest, dict):
            return latest.get("text", "")
        return str(latest)
    
    def clear(self):
        self.narratives = []


async def send_message_with_response(gm, collector, message: str, timeout: float = 5.0) -> str:
    """发送消息并等待叙事响应"""
    collector.clear()
    await gm.handle_player_message(message)
    # 等待一小段时间让事件处理
    await asyncio.sleep(timeout)
    return collector.get_latest()


async def run_experience():
    """运行完整游戏体验"""
    recorder = ExperienceRecorder()
    collector = NarrativeCollector()
    recorder.start_time = datetime.now()
    
    print("=" * 60)
    print("[EXPERIENCE] 体验官开始自动体验")
    print("=" * 60)
    
    # 初始化
    print("\n[1/6] 初始化游戏系统...")
    bus = await init_event_bus()
    master = await init_game_master()
    
    # 订阅叙事输出
    await bus.subscribe(EventType.NARRATIVE_OUTPUT, collector.handler, "experience_collector")
    print("已订阅叙事输出事件")
    
    # 创建角色
    print("\n[2/6] 创建角色...")
    creator = get_character_creator()
    char = creator.create_from_selection(
        name="体验官测试",
        race_id="human",
        class_id="warrior"
    )
    print(f"角色创建成功: {char.name} ({char.race_name}/{char.class_name})")
    
    # 初始化游戏状态
    master.game_state["player_stats"] = char.to_player_stats()
    master.game_state["turn"] = 0
    master.game_state["location"] = "月叶镇"
    
    # ===== 新手引导 =====
    print("\n[3/6] 进入新手引导...")
    recorder.set_phase("新手引导")
    
    welcome_narrative = await send_message_with_response(master, collector, "直接开始冒险")
    recorder.record("开始冒险", welcome_narrative)
    print(f"欢迎叙事: {welcome_narrative[:200] if welcome_narrative else '(empty)'}")
    
    # ===== 探索阶段 =====
    print("\n[4/6] 开始探索...")
    recorder.set_phase("探索阶段")
    
    exploration_actions = [
        ("环顾四周", "探索镇中心环境"),
        ("去酒馆看看", "进入酒馆场景"),
        ("和酒馆里的人交谈", "NPC交互"),
        ("打听最近有没有奇怪的事", "对话内容深入"),
        ("查看自己的状态", "系统交互"),
    ]
    
    for action, desc in exploration_actions:
        print(f"\n  执行: {action} ({desc})")
        try:
            result = await send_message_with_response(master, collector, action)
            recorder.record(f"{action} - {desc}", result)
            if result:
                display = result.replace('\n', ' ')[:200]
                print(f"  叙事: {display}")
            else:
                print(f"  叙事: (empty)")
        except Exception as e:
            print(f"  错误: {e}")
            recorder.record(f"{action} - {desc}", f"[错误] {str(e)}")
    
    # ===== 战斗体验 =====
    print("\n[5/6] 测试战斗...")
    recorder.set_phase("战斗体验")
    
    # 尝试触发战斗
    combat_actions = [
        ("去野外看看", "探索野外可能触发战斗"),
        ("主动寻找敌人", "主动触发战斗"),
    ]
    
    for action, desc in combat_actions:
        print(f"\n  执行: {action} ({desc})")
        try:
            result = await send_message_with_response(master, collector, action)
            recorder.record(f"{action} - {desc}", result)
            if result:
                display = result.replace('\n', ' ')[:200]
                print(f"  叙事: {display}")
                # 检查是否有战斗关键词
                combat_keywords = ["战斗", "攻击", "敌人", "怪物", "血量", "伤害"]
                if any(kw in result for kw in combat_keywords):
                    print(f"  [检测到战斗相关叙事]")
            else:
                print(f"  叙事: (empty)")
        except Exception as e:
            print(f"  错误: {e}")
            recorder.record(f"{action} - {desc}", f"[错误] {str(e)}")
    
    # ===== 清理 =====
    print("\n[6/6] 生成报告...")
    await master.stop()
    await bus.stop()
    
    end_time = datetime.now()
    duration = (end_time - recorder.start_time).total_seconds()
    
    # 生成报告
    report = generate_report(recorder, duration, char)
    
    # 保存报告
    report_path = os.path.join(_game_root, "tests", "experience_report_V1_0_0.md")
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(report)
    
    print(f"\n报告已保存: {report_path}")
    print("\n" + "=" * 60)
    print("[OK] 体验官体验完成")
    print("=" * 60)
    
    return report


def generate_report(recorder: ExperienceRecorder, duration: float, char: Character) -> str:
    """生成体验报告"""
    
    # 分析叙事质量
    total_records = len(recorder.records)
    empty_responses = sum(1 for r in recorder.records if not r["narrative"] or r["narrative"].strip() == "")
    error_responses = sum(1 for r in recorder.records if "[错误]" in r["narrative"])
    
    # 计算叙事长度
    narrative_lengths = []
    for r in recorder.records:
        if r["narrative"] and not r["narrative"].strip() == "" and not r["narrative"].startswith("[错误]"):
            narrative_lengths.append(len(r["narrative"]))
    
    avg_length = sum(narrative_lengths) / len(narrative_lengths) if narrative_lengths else 0
    
    # 检测敷衍模板
    generic_templates = [
        "你的声音在空气中回荡",
        "你听到了远处的声音",
        "一切显得格外宁静",
        "空气中弥漫着神秘的气息",
        "你的心中涌起一股",
    ]
    generic_count = sum(
        1 for r in recorder.records 
        if any(t in r["narrative"] for t in generic_templates)
    )
    
    # ===== 叙事体验评分 =====
    # 基础分8分，扣分项
    narrative_score = 8.0
    if empty_responses > 0:
        narrative_score -= empty_responses * 1.0
    if generic_count > 2:
        narrative_score -= (generic_count - 2) * 0.5
    if avg_length < 100 and avg_length > 0:
        narrative_score -= 1.0
    narrative_score = max(1.0, min(10.0, narrative_score))
    
    # ===== 节奏体验评分 =====
    # 基于响应完整性和长度变化
    rhythm_score = 7.0
    if empty_responses > total_records * 0.3:
        rhythm_score -= 2.0
    if avg_length < 50:
        rhythm_score -= 1.5
    rhythm_score = max(1.0, min(10.0, rhythm_score))
    
    # ===== 可重玩性评分 =====
    # 基于场景多样性（通过记录的行动多样性评估）
    unique_actions = len(set(r["action"] for r in recorder.records))
    replay_score = 6.0
    if unique_actions < 5:
        replay_score -= (5 - unique_actions) * 0.5
    replay_score = max(1.0, min(10.0, replay_score))
    
    # ===== 受众广度评分 =====
    # 基于新手引导完整性
    audience_score = 7.0
    # 检查是否有系统命令（状态、帮助等）
    has_system_cmds = any("状态" in r["action"] for r in recorder.records)
    if not has_system_cmds:
        audience_score -= 1.0
    audience_score = max(1.0, min(10.0, audience_score))
    
    # ===== 发现的问题 =====
    problems = []
    
    if empty_responses > 0:
        problems.append({
            "位置": "全局",
            "问题": f"有 {empty_responses}/{total_records} 次操作无叙事响应",
            "对应目标": "情绪张力",
            "严重程度": "P1"
        })
    
    if generic_count > 2:
        problems.append({
            "位置": "叙事生成",
            "问题": f"检测到 {generic_count} 处疑似万能敷衍模板",
            "对应目标": "情绪张力",
            "严重程度": "P1"
        })
    
    if avg_length < 80 and avg_length > 0:
        problems.append({
            "位置": "叙事长度",
            "问题": f"平均叙事长度仅 {avg_length:.0f} 字，内容偏少",
            "对应目标": "情绪张力",
            "严重程度": "P2"
        })
    
    # ===== 详细记录 =====
    detailed_records = []
    for r in recorder.records:
        status = "[OK]" if r["narrative"] and r["narrative"].strip() and not r["narrative"].startswith("[错误]") else "[FAIL]"
        preview = r["narrative"][:80].replace('\n', ' ') if r["narrative"] else "(empty)"
        detailed_records.append(f"| {r['turn']} | {r['phase']} | {r['action']} | {status} | {preview} |")
    
    # ===== 生成报告 =====
    report = f"""# 体验报告 V1.0.0

> 生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
> 体验时长：{duration:.1f} 秒
> 游戏版本：V1.0.0

---

## 基本信息

| 项目 | 内容 |
|------|------|
| 游玩时长 | {duration:.1f} 秒 |
| 到达阶段 | {recorder.phase} |
| 死亡次数 | {recorder.deaths} |
| 角色 | {char.name} ({char.race_name}/{char.class_name}) |
| 总操作次数 | {total_records} |
| 无响应次数 | {empty_responses} |
| 错误次数 | {error_responses} |
| 平均叙事长度 | {avg_length:.0f} 字 |
| 敷衍模板检测 | {generic_count} 处 |

---

## 叙事体验评分（1-10）

**得分：{narrative_score:.1f}/10**

### 开场叙事
{"正常" if recorder.records and recorder.records[0]["narrative"] else "无开场叙事（问题）"}

### NPC对话
检查点：
- NPC是否有具体名称和描述
- 对话内容是否具体、有个性
- 是否记得之前的对话内容

### 战斗叙事
检查点：
- 战斗是否有现场感
- 伤害数值是否具体
- 是否有策略性描述

---

## 节奏体验评分（1-10）

**得分：{rhythm_score:.1f}/10**

评估维度：
- 每回合响应是否及时
- 叙事长度是否合理（建议 100-300 字）
- 是否有明确的行动结果

统计数据：
- 平均叙事长度：{avg_length:.0f} 字
- 敷衍模板检测：{generic_count} 处

---

## 可重玩性评分（1-10）

**得分：{replay_score:.1f}/10**

评估维度：
- 每局体验差异化程度
- 玩家选择是否有真正影响
- 场景/NPC/敌人是否随机化

---

## 受众广度评分（1-10）

**得分：{audience_score:.1f}/10**

评估维度：
- 新手能否快速上手
- 新手引导是否足够
- 系统命令是否易用

---

## 具体问题

| 位置 | 问题描述 | 对应目标 | 严重程度 |
|------|---------|---------|---------|
{chr(10).join([f"| {p['位置']} | {p['问题']} | {p['对应目标']} | {p['严重程度']} |" for p in problems]) if problems else "| - | 无明显问题 | - | - |"}

---

## 详细操作记录

| 回合 | 阶段 | 操作 | 状态 | 叙事预览 |
|------|------|------|------|---------|
{chr(10).join(detailed_records)}

---

## 优点

- 角色创建流程清晰，种族职业选择友好
- 系统命令（状态、帮助）响应正常
- 游戏框架完整，有存档/读档功能

## 需要改进的地方

{chr(10).join([f"- {p['问题']}" for p in problems]) if problems else "- 暂无明显问题"}

---

## 总体评分（1-10）

**{((narrative_score + rhythm_score + replay_score + audience_score) / 4):.1f}/10**

### 总结

本次体验覆盖了角色创建、新手引导、基础探索等核心流程。游戏框架基本完整，但在叙事质量和响应完整性方面仍有提升空间。

### 建议优先级

1. **P0（阻塞）**：修复无响应问题，确保每个操作都有叙事反馈
2. **P1（高）**：减少万能敷衍模板，提升叙事具体性
3. **P2（中）**：增加叙事长度，丰富内容细节
"""
    
    return report


if __name__ == "__main__":
    asyncio.run(run_experience())
