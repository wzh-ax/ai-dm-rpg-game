"""
Pytest 配置和共享 fixtures
"""
import pytest
import asyncio
import sys
from pathlib import Path

# 确保项目根目录在路径中
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


@pytest.fixture
def event_loop():
    """创建事件循环（解决 asyncio fixture 兼容性问题）"""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def mock_event_bus():
    """创建 mock EventBus 用于测试"""
    from src.event_bus import EventBus
    bus = EventBus()
    return bus
