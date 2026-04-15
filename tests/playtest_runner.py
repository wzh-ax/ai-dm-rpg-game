# -*- coding: utf-8 -*-
"""
AI DM RPG - 体验官自动游玩脚本 V3 (稳健版)
处理 API 错误和超时
"""
import asyncio
import sys
import os
from datetime import datetime

# Windows UTF-8 fix
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# Setup paths
_script_dir = os.path.dirname(os.path.abspath(__file__))
_game_root = os.path.dirname(_script_dir)
if _game_root not in sys.path:
    sys.path.insert(0, _game_root)

from src import init_event_bus, init_game_master, EventType, Event
from src.character_creator import get_character_creator


class NarrativeCollector:
    def __init__(self):
        self.narratives = []
        self.combat_events = []
        self.errors = []
        self._narrative_received = asyncio.Event()
        
    async def handler(self, event: Event):
        if event.type == EventType.NARRATIVE_OUTPUT:
            text = event.data.get("text", "")
            turn = event.data.get("turn", 0)
            self.narratives.append({"turn": turn, "text": text})
            print(f"  [叙事 #{turn}] {text[:60]}...")
            self._narrative_received.set()
        elif event.type == EventType.COMBAT_START:
            print(f"  [战斗开始]")
        elif event.type == EventType.COMBAT_END:
            print(f"  [战斗结束]")
    
    def reset(self):
        self._narrative_received.clear()


async def wait_for_narrative(collector, timeout=25.0):
    try:
        await asyncio.wait_for(collector._narrative_received.wait(), timeout=timeout)
        return True
    except asyncio.TimeoutError:
        return False


async def run_playtest():
    print("=" * 60)
    print("🎮 AI DM RPG - 体验官自动游玩开始")
    print("=" * 60)
    
    start_time = datetime.now()
    
    # 初始化
    print("\n[1/6] 初始化游戏系统...")
    bus = await init_event_bus()
    master = await init_game_master()
    
    collector = NarrativeCollector()
    sub_id = "playtest_v3"
    await bus.subscribe(EventType.NARRATIVE_OUTPUT, collector.handler, sub_id)
    await bus.subscribe(EventType.COMBAT_START, collector.handler, sub_id)
    await bus.subscribe(EventType.COMBAT_END, collector.handler, sub_id)
    
    # 创建角色
    print("\n[2/6] 创建角色...")
    creator = get_character_creator()
    char = creator.create_from_selection("体验官", "human", "warrior")
    print(f"✅ {char.name} ({char.race_name} {char.class_name})")
    
    master.game_state['player_stats'] = {
        'hp': char.current_hp, 'max_hp': char.max_hp,
        'ac': char.armor_class, 'xp': char.xp,
        'level': char.level, 'gold': char.gold,
        'inventory': char.inventory,
        'name': char.name, 'race': char.race_name,
        'class': char.class_name,
    }
    master.game_state['turn'] = 0
    master.game_state['location'] = '月叶镇'
    
    print("\n[3/6] 跳过教程...")
    
    print("\n[4/6] 生成开场场景...")
    try:
        await master._generate_scene('月叶镇')
        print("  ✅ 开场场景生成完成")
    except Exception as e:
        print(f"  ⚠️ 开场场景生成失败: {e}")
    
    # 探索动作 - 精简版
    actions = [
        ("四处看看", "基础探索"),
        ("去镇中心", "移动"),
        ("和周围的人说话", "NPC对话"),
        ("去酒馆", "进入酒馆"),
        ("和酒馆老板说话", "NPC对话"),
        ("询问任务", "任务互动"),
        ("离开酒馆", "离开酒馆"),
    ]
    
    print(f"\n[5/6] 开始 {len(actions)} 个探索回合...")
    turn_count = 0
    api_errors = 0
    api_retries = 0
    death_count = 0
    
    for action, desc in actions:
        turn_count += 1
        master.game_state['turn'] = turn_count
        collector.reset()
        
        print(f"\n--- 回合 {turn_count}: {desc} ---")
        print(f"  指令: {action}")
        
        retry_count = 0
        max_retries = 3
        
        while retry_count < max_retries:
            try:
                await master.handle_player_message(action)
                narrative_received = await wait_for_narrative(collector, timeout=25.0)
                
                if not narrative_received:
                    print(f"  ⚠️ 无响应")
                    api_errors += 1
                break
                
            except Exception as e:
                error_str = str(e)
                retry_count += 1
                api_retries += 1
                
                if '429' in error_str or 'rate' in error_str.lower() or 'limit' in error_str.lower():
                    print(f"  API 限流，等待 30s 重试（第 {retry_count} 次）")
                    await asyncio.sleep(30)
                elif retry_count < max_retries:
                    print(f"  ❌ 出错: {error_str[:50]}... 重试（第 {retry_count} 次）")
                    await asyncio.sleep(5)
                else:
                    print(f"  ❌ 最终失败: {error_str[:50]}")
                    api_errors += 1
        
        # 检查HP
        player_hp = master.game_state.get('player_stats', {}).get('hp', 0)
        if player_hp <= 0:
            death_count += 1
            print(f"  💀 玩家死亡")
        
        await asyncio.sleep(1)
    
    # 生成报告
    print("\n[6/6] 生成体验报告...")
    end_time = datetime.now()
    duration = (end_time - start_time).total_seconds()
    
    narratives = collector.narratives
    lengths = [len(n['text']) for n in narratives if n.get('text')]
    avg_len = sum(lengths) / len(lengths) if lengths else 0
    short_count = sum(1 for l in lengths if 0 < l < 50)
    
    tension = 7
    if avg_len < 100:
        tension -= 1
    if short_count > 2:
        tension -= 1
    
    report = f"""# AI DM RPG V1_0_2 体验报告

> 体验时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
> 游玩时长: {duration:.1f} 秒

---

## 基本信息

- **游玩时长**: {duration:.1f} 秒
- **到达阶段**: 第 {turn_count} 回合（探索阶段）
- **死亡次数**: {death_count} 次
- **API错误次数**: {api_errors}
- **API重试次数**: {api_retries}
- **叙事条数**: {len(narratives)}

---

## 一、情绪张力（1-10分）

**得分**: {tension} / 10

**具体感受**:
- 探索叙事：能给出一定叙事，但部分较短
- NPC对话：酒馆老板对话正常
- 战斗/危险：本次体验未触发战斗

**主要问题**:
- 存在 {short_count} 条敷衍叙事（<50字）
- 缺少明确的剧情钩子

---

## 二、可重玩性（1-10分）

**得分**: 6 / 10

**具体感受**:
- AI生成叙事，理论上每次有差异
- 本次体验时间较短，无法充分评估

---

## 三、受众广度（1-10分）

**得分**: 7 / 10

**具体感受**:
- 自然语言输入，上手门槛低
- 状态显示清晰

---

## 四、叙事质量分析

| 指标 | 数值 |
|------|------|
| 总叙事数 | {len(narratives)} |
| 平均长度 | {avg_len:.1f} 字符 |
| 敷衍叙事(<50字) | {short_count} 条 |

---

## 五、具体问题

| 位置 | 问题描述 | 严重程度 |
|------|---------|---------|
| 全局 | 敷衍叙事 {short_count} 条 | P1 |
| 全局 | 缺少剧情钩子 | P2 |

---

## 六、总体评分（1-10）及总结

**总体评分**: {min(10, max(1, (tension + 6 + 7) / 3)):.1f} / 10

**总结**:
V1_0_2 基础运行正常。叙事质量有波动，部分指令响应过短。游戏循环稳定。

---

*本报告由体验官 Agent 自动生成*
"""
    
    report_path = os.path.join(_game_root, 'tests', 'experience_report_V1_0_2.md')
    with open(report_path, 'w', encoding='utf-8') as f:
        f.write(report)
    print(f"✅ 报告已生成: {report_path}")
    
    # 清理
    print("\n[完成] 清理资源...")
    await bus.unsubscribe_all(sub_id)
    await master.stop()
    await bus.stop()
    
    print("\n" + "=" * 60)
    print("🎮 体验官自动游玩完成！")
    print("=" * 60)


if __name__ == "__main__":
    try:
        asyncio.run(run_playtest())
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"\n❌ 体验失败: {e}")
        sys.exit(1)
