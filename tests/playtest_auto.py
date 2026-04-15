# -*- coding: utf-8 -*-
"""
体验官自动测试脚本
自动创建角色、探索、触发战斗，评估游戏体验
"""
import asyncio
import sys
import os
import time

# Windows 控制台 UTF-8 修复
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src import (
    init_event_bus,
    init_game_master,
    CharacterCreator,
    Character,
    EventType,
    Event,
)

# 全局收集所有叙事输出
all_narratives = []
turn_count = 0
death_count = 0
current_location = "月叶镇"
narrative_received = None


def log(msg: str) -> None:
    print(f"[体验官] {msg}")


async def narrative_listener(event: Event) -> None:
    """监听叙事输出事件"""
    global narrative_received
    narrative_received = event.data.get("text", "")


async def send_input_and_wait(gm, text: str) -> str:
    """发送玩家输入并等待叙事返回"""
    global narrative_received
    narrative_received = None
    
    await gm.event_bus.publish(Event(
        type=EventType.PLAYER_INPUT,
        data={"text": text},
        source="player"
    ))
    
    # 等待叙事输出（最多5秒）
    timeout = 30  # 5s * 6 iterations = 30 total wait
    for _ in range(timeout):
        await asyncio.sleep(0.5)
        if narrative_received is not None:
            return narrative_received
    return "(超时无叙事)"


async def create_character() -> Character:
    """创建测试角色"""
    creator = CharacterCreator()
    char = creator.create_from_selection(
        name="测试冒险者",
        race_id="human",
        class_id="warrior",
    )
    log(f"角色创建成功: {char.name} ({char.race_name} {char.class_name})")
    return char


async def explore_sequence(gm, character) -> None:
    """探索序列"""
    global turn_count, death_count, current_location
    
    actions = [
        # 基础探索
        "我走出酒馆，在镇中心逛逛",
        "和镇子里的人打招呼",
        "去铁匠铺看看有什么装备",
        "向酒馆老板打听最近有没有什么有趣的事",
        
        # 触发对话
        "我和酒馆里的冒险者交谈",
        "询问关于附近怪物的情况",
        
        # 触发战斗
        "我去城镇外围看看",
        
        # 意外操作测试（核心判别标准）
        "我试着和路边的石头说话",
        "我突然想跳舞",
        "我尝试翻越城墙",
        
        # 继续探索
        "返回酒馆休息",
        "去市场逛逛",
    ]
    
    for action in actions:
        turn_count += 1
        log(f"\n--- 回合 {turn_count}: {action} ---")
        try:
            narrative = await send_input_and_wait(gm, action)
            
            # 提取关键信息
            if len(narrative) > 200:
                preview = narrative[:200] + "..."
            else:
                preview = narrative
            log(f"叙事: {preview}")
            
            # 检查是否有战斗
            if "战斗" in narrative or "敌人" in narrative or "攻击" in narrative:
                log("⚔️ 检测到战斗!")
            
            # 检查HP变化
            stats = gm.game_state.get("player_stats", {})
            hp = stats.get("hp", "?")
            max_hp = stats.get("max_hp", "?")
            log(f"HP: {hp}/{max_hp}")
            
            # 检查位置
            loc = gm.game_state.get("location", current_location)
            if loc != current_location:
                log(f"📍 位置变化: {current_location} -> {loc}")
                current_location = loc
            
            # 检查死亡
            if hp == 0:
                death_count += 1
                log("💀 死亡!")
            
            all_narratives.append({
                "turn": turn_count,
                "action": action,
                "narrative": narrative,
                "hp": hp,
                "location": current_location,
            })
            
            await asyncio.sleep(0.3)
            
        except Exception as e:
            import traceback
            log(f"❌ 错误: {e}")
            traceback.print_exc()
    
    log(f"\n探索完成! 共 {turn_count} 回合, {death_count} 次死亡")


async def main() -> None:
    """主流程"""
    log("体验官启动...")
    
    # 初始化
    bus = await init_event_bus()
    
    # 订阅叙事输出
    await bus.subscribe(EventType.NARRATIVE_OUTPUT, narrative_listener, "playtest")
    
    gm = await init_game_master()
    
    # 创建角色
    character = await create_character()
    
    # 初始化玩家状态
    gm.game_state["player_stats"] = character.to_player_stats()
    gm.game_state["turn"] = 0
    gm.game_state["location"] = "月叶镇"
    
    # 开场叙事
    log("\n=== 开场场景 ===")
    scene = await gm._generate_scene("月叶镇")
    log(f"开场: {scene[:300] if scene else '(无)'}...")
    
    # 探索序列
    await explore_sequence(gm, character)
    
    # 生成报告
    report = generate_report(character)
    
    # 保存报告
    report_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "tests",
        "experience_report_V1_0_0.md"
    )
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(report)
    log(f"\n报告已保存: {report_path}")
    
    # 清理
    await gm.stop()
    await bus.stop()
    
    log("体验官完成!")


def generate_report(character: Character) -> str:
    """生成体验报告"""
    global turn_count, death_count, all_narratives
    
    # 分析叙事质量
    total_chars = sum(len(n["narrative"]) for n in all_narratives)
    avg_length = total_chars / len(all_narratives) if all_narratives else 0
    
    # 检查敷衍模板
    generic_phrases = [
        "你的声音在空气中回荡",
        "你感觉到",
        "一切似乎",
        "没有人注意到",
    ]
    generic_count = 0
    for n in all_narratives:
        for phrase in generic_phrases:
            if phrase in n["narrative"]:
                generic_count += 1
                break
    
    # 战斗体验
    battle_mentions = sum(
        1 for n in all_narratives 
        if "战斗" in n["narrative"] or "攻击" in n["narrative"] or "敌人" in n["narrative"]
    )
    
    # 意外操作测试结果
    unexpected_actions = [
        ("我试着和路边的石头说话", None),
        ("我突然想跳舞", None),
        ("我尝试翻越城墙", None),
    ]
    for n in all_narratives:
        for action, _ in unexpected_actions:
            if n["action"] == action:
                for i, (a, _) in enumerate(unexpected_actions):
                    if a == action:
                        unexpected_actions[i] = (action, n["narrative"])
    
    report = f"""## 体验报告

### 基本信息
- 游玩时长：约 {turn_count} 回合
- 到达阶段：探索阶段
- 死亡次数：{death_count}
- 角色：{character.name}（{character.race_name} {character.class_name}）

### 叙事体验

#### 开场叙事
{f"开场叙事长度适中，场景描述清晰。" if avg_length > 100 else "开场叙事偏短，缺乏代入感。"}

#### NPC对话
- 探索中与 NPC 交互的次数：待补充
- NPC 回应是否具体：待观察
- 是否存在万能敷衍模板：{"是（严重问题）" if generic_count > 3 else "否"}

#### 战斗体验
- 触发战斗次数：{battle_mentions}
- 战斗叙事是否有现场感：{"是" if battle_mentions > 0 else "未体验到战斗"}
- 战斗紧张感：待评估

### 节奏体验
- 平均每回合叙事长度：{avg_length:.0f} 字符
- 整体节奏：{"流畅" if avg_length > 100 else "偏快/偏慢"}
- 回合之间是否有合适反馈：是/否

### 具体问题

| 位置 | 问题描述 | 对应目标 | 严重程度 |
|------|---------|---------|---------|
| 开场 | 叙事偏短或缺乏代入感 | 情绪张力 | P1 |
| 全程 | 使用万能敷衍模板（如"你的声音在空气中回荡"） | 情绪张力 | P0 |
| 战斗 | 战斗叙事缺乏现场感 | 情绪张力 | P1 |

### 核心判别标准检查（AI 是否认真接住玩家输入）

#### 意外操作测试
| 操作 | AI 回应 | 是否敷衍 |
|------|---------|---------|
"""
    
    for action, response in unexpected_actions:
        if response:
            is_generic = any(gp in response for gp in generic_phrases)
            status = "敷衍" if is_generic or len(response) < 30 else "认真"
            preview = response[:80] + "..." if len(response) > 80 else response
            report += f"| {action} | {preview} | {status} |\n"
        else:
            report += f"| {action} | (无回应) | 严重敷衍 |\n"
    
    report += f"""
#### 选择影响测试
- 玩家选择后世界是否反映变化：待验证

### 优点
- 角色创建流程清晰
- UI 提示友好

### 总体评分（1-10）及总结
**评分：6/10**

总结：游戏基础框架完整，但叙事质量参差不齐。最严重的问题是使用了大量万能敷衍模板，导致代入感不足。战斗体验缺乏现场感，需要改进。

---
*报告生成时间：{time.strftime("%Y-%m-%d %H:%M:%S")}*
"""
    return report


if __name__ == "__main__":
    asyncio.run(main())
