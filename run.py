"""
AI DM RPG - 入口脚本
用于测试和演示
"""
import asyncio
import logging

from src import (
    init_event_bus,
    init_main_dm,
    get_hook_registry,
    HookNames,
    EventType,
    Event,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)


async def demo_hook(event: Event):
    """演示 Hook"""
    print(f"[Hook] before_input_processing triggered with: {event.data}")


async def main():
    """主函数"""
    print("=" * 50)
    print("AI DM RPG - 启动")
    print("=" * 50)
    
    # 初始化 Event Bus
    bus = await init_event_bus()
    
    # 设置 Hook
    hooks = get_hook_registry()
    hooks.register(HookNames.BEFORE_INPUT_PROCESSING, demo_hook)
    
    # 初始化 Main DM
    dm = await init_main_dm()
    dm.set_hooks(hooks)
    
    print("\n事件总线订阅状态:")
    print(f"  - PLAYER_INPUT: {bus.get_subscription_count(EventType.PLAYER_INPUT)}")
    print(f"  - NARRATIVE_OUTPUT: {bus.get_subscription_count(EventType.NARRATIVE_OUTPUT)}")
    
    print("\n已注册的 Hooks:")
    for name, count in hooks.list_hooks().items():
        print(f"  - {name}: {count}")
    
    # 模拟玩家输入
    print("\n" + "-" * 50)
    print("模拟玩家输入...")
    
    # 订阅叙事输出
    results = []
    async def output_handler(event: Event):
        results.append(event.data)
        
    await bus.subscribe(
        EventType.NARRATIVE_OUTPUT, 
        output_handler, 
        "demo_output"
    )
    
    await dm.handle_player_message("我走进酒馆，环顾四周")
    await asyncio.sleep(0.5)  # 等待处理
    
    print("\n叙事输出:")
    for r in results:
        print(f"  Turn {r.get('turn')}: {r.get('text')[:60]}...")
    
    print("\n" + "=" * 50)
    print("演示完成！")
    print("=" * 50)
    
    # 清理
    await dm.stop()
    await bus.stop()


if __name__ == "__main__":
    asyncio.run(main())
