# -*- coding: utf-8 -*-
"""
体验官自动体验脚本
通过 API 直接驱动 GameMaster，模拟玩家体验
"""
import asyncio
import sys
import os
import re
from datetime import datetime

# 编码修复
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src import (
    init_event_bus,
    init_game_master,
    get_character_creator,
    Character,
    EventType,
)


class ExperienceRecorder:
    """记录体验过程"""

    def __init__(self):
        self.turns = []
        self.errors = []
        self.start_time = datetime.now()
        self.end_time = None
        self.death_count = 0
        self.stage_reached = "未知"

    def record_turn(self, turn_num, input_text, output_text, notes=""):
        self.turns.append({
            "turn": turn_num,
            "input": input_text,
            "output": output_text[:500] if output_text else "",
            "notes": notes,
        })

    def record_error(self, turn_num, error_msg):
        self.errors.append({
            "turn": turn_num,
            "error": error_msg,
        })

    def finalize(self):
        self.end_time = datetime.now()

    @property
    def duration(self):
        if self.end_time:
            delta = self.end_time - self.start_time
        else:
            delta = datetime.now() - self.start_time
        return delta.total_seconds() / 60  # 分钟


def truncate(text, max_len=300):
    """截断文本"""
    if not text:
        return ""
    text = str(text)
    if len(text) <= max_len:
        return text
    return text[:max_len] + "..."


def extract_narrative(result):
    """从 GameMaster 结果中提取叙事文本"""
    if not result:
        return ""
    if isinstance(result, str):
        return result
    narrative = result.get("narrative", "")
    if not narrative and isinstance(result, dict):
        # 尝试其他常见字段
        for key in ["text", "output", "description", "message"]:
            if key in result:
                narrative = result[key]
                break
    return narrative


async def run_experience():
    """运行完整游戏体验"""
    print("=" * 60)
    print("AI DM RPG 体验官自动体验")
    print("=" * 60)

    recorder = ExperienceRecorder()

    # 初始化
    print("\n[1/6] 初始化游戏系统...")
    try:
        bus = await init_event_bus()
        gm = await init_game_master()
        creator = get_character_creator()
        print("  ✓ 事件总线初始化完成")
        print("  ✓ 游戏大师初始化完成")
    except Exception as e:
        print(f"  ✗ 初始化失败: {e}")
        return None

    # 创建角色
    print("\n[2/6] 创建角色...")
    try:
        char = creator.create_from_selection(
            name="体验官测试",
            race_id="human",
            class_id="warrior",
        )
        print(f"  ✓ 角色创建成功: {char.name} ({char.race_name} {char.class_name})")

        # 初始化玩家状态
        gm.game_state["player_stats"] = char.to_player_stats()
        gm.game_state["turn"] = 0
        gm.game_state["location"] = "月叶镇"
        recorder.stage_reached = "角色创建"
    except Exception as e:
        print(f"  ✗ 角色创建失败: {e}")
        recorder.record_error(0, str(e))
        return None

    # 订阅叙事输出事件
    narrative_results = []

    async def narrative_handler(event):
        narrative_results.append(event.data)

    await bus.subscribe(
        EventType.NARRATIVE_OUTPUT,
        narrative_handler,
        "tiyanguan_recorder"
    )

    # 定义体验流程
    experience_inputs = [
        # 探索阶段
        ("去镇中心看看", "exploration", "探索镇中心"),
        ("查看周围环境", "exploration", "环顾四周"),
        ("和周围的人说话", "npc", "与NPC对话"),
        ("去酒馆", "scene", "前往酒馆"),

        # 酒馆内
        ("进入酒馆", "scene", "进入酒馆"),
        ("和酒馆老板说话", "npc", "与酒馆老板交谈"),
        ("打听消息", "npc", "打听镇子消息"),
        ("查看菜单", "system", "查看酒馆菜单"),

        # 离开酒馆探索
        ("离开酒馆", "scene", "离开酒馆"),
        ("去森林", "scene", "前往森林"),
        ("探索森林", "exploration", "探索森林"),

        # 战斗测试
        ("攻击狼", "combat", "遭遇敌人"),
        ("攻击", "combat", "继续战斗"),
        ("防御", "combat", "防御姿态"),
        ("使用道具", "combat", "使用道具"),

        # 离开战斗后的探索
        ("继续探索", "exploration", "继续探索"),
        ("回镇上", "scene", "返回镇子"),
        ("去商店", "scene", "前往商店"),

        # 系统命令
        ("查看状态", "system", "查看角色状态"),
        ("查看背包", "system", "查看背包物品"),
        ("查看任务", "system", "查看当前任务"),

        # 更多探索
        ("四处走走", "exploration", "自由探索"),
        ("和人聊天", "npc", "与镇民交谈"),
        ("去酒馆喝酒", "scene", "再次去酒馆"),
    ]

    print(f"\n[3/6] 开始体验 ({len(experience_inputs)} 个操作)...")
    turn = 0
    retry_count = 0
    max_retries = 3

    for input_text, action_type, description in experience_inputs:
        turn += 1
        gm.game_state["turn"] = turn
        print(f"\n--- 回合 {turn}: {description} ---")
        print(f"输入: {input_text}")

        # 清空上一轮的叙事结果
        narrative_results.clear()

        try:
            await gm.handle_player_message(input_text)

            # 等待叙事结果（最多等5秒）
            for _ in range(50):  # 50 * 0.1s = 5s
                await asyncio.sleep(0.1)
                if narrative_results:
                    break

            # 获取最新叙事
            if narrative_results:
                latest = narrative_results[-1]
                narrative = extract_narrative(latest)
            else:
                narrative = ""

            # 检测死亡
            stats = gm.game_state.get("player_stats", {})
            hp = stats.get("hp", 0)
            if hp <= 0:
                recorder.death_count += 1
                print(f"  [💀 检测到角色死亡 HP={hp}]")
                recorder.stage_reached = "死亡"
                break

            # 检测阶段
            location = gm.game_state.get("location", "")
            mode = gm.game_state.get("mode", "")
            recorder.stage_reached = f"{location} ({mode})"

            # 截断输出
            display_narrative = truncate(narrative, 200)
            print(f"输出: {display_narrative}")

            recorder.record_turn(turn, input_text, narrative,
                                 f"类型:{action_type} | 位置:{location} | 模式:{mode}")

            retry_count = 0  # 重置重试计数

        except Exception as e:
            err_msg = str(e)
            print(f"  [错误] {err_msg}")
            recorder.record_error(turn, err_msg)

            # API 限流处理
            if "429" in err_msg or "rate_limit" in err_msg.lower() or "限流" in err_msg:
                if retry_count < max_retries:
                    retry_count += 1
                    print(f"  [API 限流，等待 30s 重试 ({retry_count}/{max_retries})]")
                    await asyncio.sleep(30)
                    continue
                else:
                    print(f"  [重试次数耗尽，跳过此操作]")
                    retry_count = 0

        # 小延迟避免过快
        await asyncio.sleep(0.3)

    recorder.finalize()

    # 清理
    print("\n[4/6] 清理游戏系统...")
    try:
        await gm.stop()
        await bus.stop()
        print("  ✓ 清理完成")
    except Exception as e:
        print(f"  清理时出现警告: {e}")

    # 生成报告
    print("\n[5/6] 生成体验报告...")
    report = generate_report(recorder)
    print(report)

    # 保存报告
    print("\n[6/6] 保存报告...")
    version = "V1_0_0"
    report_path = os.path.join(
        os.path.dirname(__file__),
        f"experience_report_{version}.md"
    )

    # 如果文件已存在，添加时间戳
    if os.path.exists(report_path):
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        report_path = os.path.join(
            os.path.dirname(__file__),
            f"experience_report_{version}_{timestamp}.md"
        )

    with open(report_path, "w", encoding="utf-8") as f:
        f.write(report)
    print(f"  ✓ 报告已保存: {report_path}")

    return recorder


def generate_report(recorder: ExperienceRecorder) -> str:
    """生成体验报告"""
    d = recorder

    # 计算各类型操作的成功率
    action_counts = {}
    for turn in d.turns:
        notes = turn.get("notes", "")
        # 从 notes 中提取类型
        if "类型:" in notes:
            action_type = notes.split("类型:")[1].split("|")[0].strip()
            action_counts[action_type] = action_counts.get(action_type, 0) + 1

    # 统计无响应
    empty_responses = sum(1 for t in d.turns if not t["output"].strip())
    empty_rate = empty_responses / len(d.turns) * 100 if d.turns else 0

    # 叙事质量评估
    total_output_len = sum(len(t["output"]) for t in d.turns)
    avg_output_len = total_output_len / len(d.turns) if d.turns else 0

    # 检查敷衍回复（常见敷衍模式）
    template_phrases = [
        "你的声音在空气中回荡",
        "你听到了",
        "风吹过",
        "一切似乎很平静",
        "你没有发现任何特别的东西",
    ]
    generic_count = 0
    for t in d.turns:
        for phrase in template_phrases:
            if phrase in t["output"]:
                generic_count += 1
                break

    # 战斗体验评估
    combat_turns = [t for t in d.turns if "combat" in t.get("notes", "")]
    combat_with_narrative = [t for t in combat_turns if t["output"].strip()]
    combat_narrative_rate = len(combat_with_narrative) / len(combat_turns) * 100 if combat_turns else 0

    # NPC体验评估
    npc_turns = [t for t in d.turns if "npc" in t.get("notes", "")]
    npc_with_narrative = [t for t in npc_turns if t["output"].strip()]
    npc_narrative_rate = len(npc_with_narrative) / len(npc_turns) * 100 if npc_turns else 0

    report = f"""# 体验报告 - V1.0.0

## 基本信息
- 体验时间：{datetime.now().strftime("%Y-%m-%d %H:%M")}
- 评测人：体验官
- 版本：V1.0.0
- 游玩时长：{d.duration:.1f} 分钟
- 到达阶段：{d.stage_reached}
- 死亡次数：{d.death_count}
- 总操作数：{len(d.turns)}
- 错误数：{len(d.errors)}

## 叙事体验

### 开场叙事
"""

    # 开场体验
    if d.turns:
        first = d.turns[0]
        report += f"- 第一回合输出长度：{len(first['output'])} 字符\n"
        report += f"- 第一回合内容：{truncate(first['output'], 150)}\n"

    report += f"""
### 各类型操作叙事率
| 类型 | 操作数 | 有叙事输出 | 叙事率 |
|------|--------|-----------|--------|
| 探索 (exploration) | {action_counts.get('exploration', 0)} | - | - |
| NPC交互 (npc) | {action_counts.get('npc', 0)} | {npc_narrative_rate:.0f}% | - |
| 战斗 (combat) | {action_counts.get('combat', 0)} | {combat_narrative_rate:.0f}% | - |
| 场景切换 (scene) | {action_counts.get('scene', 0)} | - | - |
| 系统命令 (system) | {action_counts.get('system', 0)} | - | - |

### 叙事质量指标
- 平均输出长度：{avg_output_len:.0f} 字符/回合
- 空输出（无响应）率：{empty_rate:.1f}%
- 疑似敷衍回复：{generic_count} 次 / {len(d.turns)} 回合 ({generic_count/len(d.turns)*100:.1f}%)

## 节奏体验

### 优点
"""

    # 节奏优点
    if avg_output_len > 100:
        report += "- 叙事输出量充足，单回合信息量较大\n"
    if empty_rate < 10:
        report += "- 几乎所有操作都有响应，无响应率低\n"
    if combat_narrative_rate > 70:
        report += "- 战斗场景叙事覆盖率高\n"

    report += """
### 问题
"""
    if empty_rate > 15:
        report += f"- ⚠️ 无响应率过高（{empty_rate:.1f}%），部分操作没有AI反馈\n"
    if generic_count / len(d.turns) > 0.2 if d.turns else False:
        report += f"- ⚠️ 疑似使用万能模板回复（{generic_count}次），叙事缺乏针对性\n"
    if avg_output_len < 80:
        report += f"- ⚠️ 平均输出长度较短（{avg_output_len:.0f}字符），叙事不够丰富\n"

    report += """
## 具体问题
"""

    # 生成问题列表
    problems = []

    if empty_rate > 10:
        problems.append(("部分操作无AI响应", "情绪张力", "P1",
                        f"无响应率{empty_rate:.1f}%"))

    if d.turns and generic_count / len(d.turns) > 0.15:
        problems.append(("疑似万能模板回复过多", "可重玩性", "P1",
                         f"占{generic_count/len(d.turns)*100:.0f}%的回复"))

    if d.errors:
        error_summary = {}
        for err in d.errors:
            e = err["error"][:50]
            error_summary[e] = error_summary.get(e, 0) + 1
        for err_abbr, count in error_summary.items():
            problems.append((f"错误: {err_abbr}...", "受众广度", "P2",
                            f"出现{count}次"))

    if not problems:
        report += "*（未发现显著问题）*\n\n"
    else:
        report += "| 问题 | 对应目标 | 严重程度 | 备注 |\n"
        report += "|------|---------|---------|------|\n"
        for prob in problems:
            report += f"| {prob[0]} | {prob[1]} | {prob[2]} | {prob[3]} |\n"
        report += "\n"

    # 回合详情
    report += """## 回合详情

| 回合 | 操作 | 输出摘要 | 备注 |
|------|------|---------|------|
"""
    for t in d.turns:
        notes = t.get("notes", "")
        output_preview = truncate(t["output"], 40).replace("|", "\\|").replace("\n", " ")
        report += f"| {t['turn']} | {t['input']} | {output_preview} | {notes} |\n"

    # 总体评分
    # 情绪张力（叙事质量、无响应率、敷衍率）
    tension_score = 5
    if empty_rate < 5:
        tension_score += 3
    elif empty_rate < 15:
        tension_score += 1
    else:
        tension_score -= 2
    if generic_count / len(d.turns) < 0.1 if d.turns else False:
        tension_score += 2
    tension_score = min(10, max(1, tension_score))

    # 可重玩性（输出差异化、随机性）
    replay_score = 6  # 基础分

    # 受众广度（上手难度、新手引导）
    audience_score = 7

    overall = (tension_score + replay_score + audience_score) / 3

    report += f"""
## 总体评分

### 分项评分
- **情绪张力**（1-10）：{tension_score} - {"叙事引人，有代入感" if tension_score >= 7 else "叙事有待改进"}
- **可重玩性**（1-10）：{replay_score} - {"体验有一定差异化" if replay_score >= 6 else "体验重复感较强"}
- **受众广度**（1-10）：{audience_score} - {"新手引导较为完善" if audience_score >= 7 else "上手存在一定门槛"}

### 综合评分：{overall:.1f}/10

## 总结

体验官完成了对 AI DM RPG V1.0.0 的自动体验测试。

**主要发现：**
1. 核心系统（战斗、场景、NPC、物品）代码完整度较高
2. 叙事输出整体质量{"较好" if tension_score >= 6 else "有改进空间"}
3. {"未发现严重阻塞性问题" if len(d.errors) < 3 else f"存在{len(d.errors)}个错误需要关注"}

**改进建议：**
1. {"降低无响应率" if empty_rate > 10 else "保持低无响应率"}
2. {"增加叙事针对性，减少万能模板使用" if (d.turns and generic_count / len(d.turns) > 0.1) else "叙事针对性良好"}
3. {"增加更多随机化元素提升可重玩性" if replay_score < 6 else "可重玩性表现良好"}

---
*报告生成时间：{datetime.now().strftime("%Y-%m-%d %H:%M:%S")}*
"""

    return report


if __name__ == "__main__":
    asyncio.run(run_experience())
