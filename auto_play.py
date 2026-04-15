# -*- coding: utf-8 -*-
"""
体验官自动游戏脚本 V5
使用 GameMaster + EventBus + 异步等待模式
"""
import asyncio
import logging
import sys
import os
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Windows PowerShell 环境 UTF-8 输出修复
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

logging.basicConfig(
    level=logging.WARNING,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class NarrativeCollector:
    """收集 NARRATIVE_OUTPUT 事件的辅助类"""
    def __init__(self, bus, event_type):
        self.bus = bus
        self.event_type = event_type
        self.results = []
        self.future = asyncio.get_event_loop().create_future()
        self.handler = None
        self.sub_id = None
    
    async def start(self):
        """开始订阅"""
        self.sub_id = f"collector_{id(self)}"
        
        async def handler(event):
            self.results.append(event.data)
            # 收到一条结果就认为完成了（简化处理）
            if not self.future.done():
                self.future.set_result(True)
        
        await self.bus.subscribe(self.event_type, handler, self.sub_id)
        return self
    
    async def wait(self, timeout=15.0):
        """等待结果或超时"""
        try:
            await asyncio.wait_for(self.future, timeout=timeout)
            return True
        except asyncio.TimeoutError:
            return False
    
    async def stop(self):
        """停止订阅"""
        if self.sub_id:
            await self.bus.unsubscribe(self.event_type, self.sub_id)
    
    def get_results(self):
        return self.results


async def call_with_retry(coro, max_retries=3, wait_seconds=30):
    """带重试的 API 调用"""
    for attempt in range(max_retries):
        try:
            return await coro
        except Exception as e:
            error_str = str(e)
            is_rate_limit = "529" in error_str or "overload" in error_str.lower()
            if is_rate_limit and attempt < max_retries - 1:
                print(f"  API 限流，等待 {wait_seconds}s 重试（第 {attempt+1}/{max_retries} 次）...")
                await asyncio.sleep(wait_seconds)
                continue
            raise


async def main():
    """主流程"""
    print("=" * 60)
    print("[体验官] 自动游戏开始")
    print("=" * 60)
    start_time = datetime.now()
    
    # 初始化
    from src import init_event_bus, init_game_master, EventType
    
    print("\n[1/5] 初始化系统...")
    bus = await init_event_bus()
    master = await init_game_master()
    
    # ===== 角色创建 =====
    print("\n[2/5] 创建角色...")
    from src.character_creator import get_character_creator
    creator = get_character_creator()
    char = creator.create_from_selection(
        name="体验官",
        race_id="human",
        class_id="warrior"
    )
    print(f"角色创建成功: {char.name} ({char.race_name}/{char.class_name})")
    print(f"HP: {char.current_hp}/{char.max_hp}, AC: {char.armor_class}, Gold: {char.gold}")
    
    # 初始化游戏状态
    master.game_state["player_stats"] = char.to_player_stats()
    master.game_state["turn"] = 0
    master.game_state["location"] = "月叶镇"
    
    # ===== 体验记录 =====
    experience_log = []
    turn_count = 0
    death_count = 0
    all_narratives = []
    
    def log(text):
        timestamp = datetime.now().strftime("%H:%M:%S")
        line = f"[{timestamp}] {text}"
        print(line)
        experience_log.append(line)
    
    # ===== 模拟玩家操作序列 =====
    actions = [
        ("去镇中心看看", "探索"),
        ("和周围的人说话", "NPC交互"),
        ("去酒馆坐坐", "场景切换"),
        ("查看状态", "系统命令"),
        ("去酒馆和老板聊天", "NPC深入对话"),
        ("走出镇子", "探索新区域"),
        ("攻击路边的野狼", "战斗"),
        ("使用生命药水", "道具使用"),
        ("去市场买装备", "商店交互"),
        ("四处逛逛看看有什么", "自由探索"),
    ]
    
    # ===== 开始游戏循环 =====
    print("\n[3/5] 开始游戏循环...")
    log("=== 游戏开始 ===")
    
    for action, action_type in actions:
        turn_count += 1
        print(f"\n--- 回合 {turn_count}: {action_type} ---")
        print(f"行动: {action}")
        
        # 创建收集器并开始订阅
        collector = NarrativeCollector(bus, EventType.NARRATIVE_OUTPUT)
        await collector.start()
        
        try:
            # 发送玩家输入
            await call_with_retry(master.handle_player_message(action))
            
            # 等待叙事结果（带超时）
            received = await collector.wait(timeout=15.0)
            
        except Exception as e:
            log(f"错误: {e}")
            received = False
        finally:
            await collector.stop()
        
        # 提取叙事结果
        results = collector.get_results()
        if results:
            for result in results:
                text = result.get("text", "")
                turn = result.get("turn", "?")
                mode = result.get("mode", "?")
                if text:
                    all_narratives.append({
                        "turn": turn,
                        "action": action,
                        "action_type": action_type,
                        "mode": mode,
                        "text": text
                    })
                    # 截取前300字
                    display_text = text[:300] + "..." if len(text) > 300 else text
                    log(f"叙事 [T{turn}][{mode}]: {display_text}")
        else:
            log(f"⚠️ 无叙事输出 (received={received})")
        
        # 短暂延迟
        await asyncio.sleep(1)
    
    # ===== 最终状态 =====
    print("\n" + "=" * 60)
    end_time = datetime.now()
    duration = (end_time - start_time).total_seconds()
    
    log("=== 游戏结束 ===")
    log(f"总回合数: {turn_count}")
    log(f"总时长: {duration:.1f}秒")
    log(f"死亡次数: {death_count}")
    log(f"有效叙事数: {len(all_narratives)}")
    
    # 清理
    await master.stop()
    await bus.stop()
    
    log("✅ 自动游戏完成")
    
    # 返回记录供报告生成
    return {
        "experience_log": experience_log,
        "turn_count": turn_count,
        "duration": duration,
        "death_count": death_count,
        "all_narratives": all_narratives,
    }


if __name__ == "__main__":
    try:
        result = asyncio.run(main())
        print(f"\n回合: {result['turn_count']}, 时长: {result['duration']:.1f}s, 死亡: {result['death_count']}")
        print(f"有效叙事: {len(result['all_narratives'])}")
    except Exception as e:
        print(f"\n❌ 运行错误: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
