"""测试 Event Bus"""
import asyncio
import pytest

from src.event_bus import EventBus, EventType, Event, get_event_bus


@pytest.mark.asyncio
async def test_event_bus_basic():
    """测试基本发布/订阅"""
    bus = EventBus()
    await bus.start()
    
    results = []
    
    async def handler(event: Event):
        results.append(event.data.get("value"))
        
    await bus.subscribe(EventType.PLAYER_INPUT, handler, "test_subscriber")
    
    await bus.publish(Event(
        type=EventType.PLAYER_INPUT,
        data={"value": 42}
    ))
    
    # 等待事件处理
    await asyncio.sleep(0.1)
    
    assert 42 in results
    assert bus.get_subscription_count(EventType.PLAYER_INPUT) == 1
    
    await bus.stop()


@pytest.mark.asyncio
async def test_event_bus_multiple_subscribers():
    """测试多个订阅者"""
    bus = EventBus()
    await bus.start()
    
    results1 = []
    results2 = []
    
    async def handler1(event: Event):
        results1.append(1)
        
    async def handler2(event: Event):
        results2.append(2)
        
    await bus.subscribe(EventType.PLAYER_INPUT, handler1, "sub1")
    await bus.subscribe(EventType.PLAYER_INPUT, handler2, "sub2")
    
    await bus.publish(Event(type=EventType.PLAYER_INPUT, data={}))
    await asyncio.sleep(0.1)
    
    assert len(results1) == 1
    assert len(results2) == 1
    
    await bus.stop()


@pytest.mark.asyncio  
async def test_unsubscribe():
    """测试取消订阅"""
    bus = EventBus()
    await bus.start()
    
    call_count = [0]
    
    async def handler(event: Event):
        call_count[0] += 1
        
    await bus.subscribe(EventType.PLAYER_INPUT, handler, "sub")
    await bus.publish(Event(type=EventType.PLAYER_INPUT, data={}))
    await asyncio.sleep(0.1)
    
    await bus.unsubscribe(EventType.PLAYER_INPUT, "sub")
    await bus.publish(Event(type=EventType.PLAYER_INPUT, data={}))
    await asyncio.sleep(0.1)
    
    assert call_count[0] == 1  # 只有第一次被调用
    
    await bus.stop()


@pytest.mark.asyncio
async def test_filter_fn():
    """测试过滤器函数"""
    bus = EventBus()
    await bus.start()
    
    results = []
    
    async def handler(event: Event):
        results.append(event.data.get("value"))
        
    async def filter_even(event: Event):
        return event.data.get("value", 0) % 2 == 0
        
    await bus.subscribe(
        EventType.PLAYER_INPUT, 
        handler, 
        "sub",
        filter_fn=filter_even
    )
    
    await bus.publish(Event(type=EventType.PLAYER_INPUT, data={"value": 2}))
    await bus.publish(Event(type=EventType.PLAYER_INPUT, data={"value": 3}))
    await asyncio.sleep(0.1)
    
    assert results == [2]  # 只处理了偶数
    
    await bus.stop()


@pytest.mark.asyncio
async def test_global_singleton():
    """测试全局单例"""
    bus1 = get_event_bus()
    bus2 = get_event_bus()
    
    assert bus1 is bus2
