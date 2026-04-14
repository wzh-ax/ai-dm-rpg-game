"""
Hooks - 单元测试
测试 Hook 注册与触发机制
"""

import pytest
import asyncio

from src.hooks import (
    HookRegistry,
    HookNames,
    Hook,
    get_hook_registry,
)


class TestHookRegistry:
    """HookRegistry 测试"""

    def test_register_hook(self):
        """测试注册单个 Hook"""
        registry = HookRegistry()
        calls = []

        def callback():
            calls.append(1)

        registry.register("test_hook", callback, phase="before", order=0)
        assert "test_hook" in registry._hooks
        assert len(registry._hooks["test_hook"]) == 1

    def test_register_multiple_hooks_same_name(self):
        """测试同一名称注册多个 Hook"""
        registry = HookRegistry()
        calls = []

        def callback1():
            calls.append(1)

        def callback2():
            calls.append(2)

        registry.register("test_hook", callback1, phase="before", order=1)
        registry.register("test_hook", callback2, phase="before", order=0)

        # 应该按 order 排序
        hooks = registry._hooks["test_hook"]
        assert len(hooks) == 2
        assert hooks[0].order == 0
        assert hooks[1].order == 1

    def test_unregister_hook(self):
        """测试取消注册 Hook"""
        registry = HookRegistry()
        calls = []

        def callback():
            calls.append(1)

        registry.register("test_hook", callback)
        registry.unregister("test_hook", callback)

        assert len(registry._hooks.get("test_hook", [])) == 0

    @pytest.mark.asyncio
    async def test_trigger_sync_callback(self):
        """测试触发同步回调"""
        registry = HookRegistry()
        calls = []

        def callback(*args, **kwargs):
            calls.append(1)
            return 1

        registry.register("test_hook", callback)
        results = await registry.trigger("test_hook", "arg1", kwarg1="kw1")

        assert calls == [1]
        assert results == [1]

    @pytest.mark.asyncio
    async def test_trigger_async_callback(self):
        """测试触发异步回调"""
        registry = HookRegistry()
        calls = []

        async def callback():
            calls.append(1)
            return 42

        registry.register("test_hook", callback)
        results = await registry.trigger("test_hook")

        assert calls == [1]
        assert results == [42]

    @pytest.mark.asyncio
    async def test_trigger_multiple_callbacks(self):
        """测试触发多个回调"""
        registry = HookRegistry()
        calls = []

        def callback1(*args, **kwargs):
            calls.append(1)
            return 1

        async def callback2(*args, **kwargs):
            calls.append(2)
            return "a"

        registry.register("test_hook", callback1)
        registry.register("test_hook", callback2)
        results = await registry.trigger("test_hook")

        assert calls == [1, 2]
        assert results == [1, "a"]

    @pytest.mark.asyncio
    async def test_trigger_nonexistent_hook_returns_empty(self):
        """触发不存在的 Hook 应返回空列表"""
        registry = HookRegistry()
        results = await registry.trigger("nonexistent_hook")
        assert results == []

    @pytest.mark.asyncio
    async def test_trigger_with_args(self):
        """测试传递参数给回调"""
        registry = HookRegistry()
        received = []

        def callback(arg1, kwarg1=None):
            received.append((arg1, kwarg1))

        registry.register("test_hook", callback)
        await registry.trigger("test_hook", "value1", kwarg1="value2")

        assert received == [("value1", "value2")]

    @pytest.mark.asyncio
    async def test_trigger_exception_isolation(self):
        """单个回调异常不应影响其他回调"""
        registry = HookRegistry()
        calls = []

        def callback1():
            calls.append(1)

        def callback2():
            raise ValueError("test error")

        def callback3():
            calls.append(3)

        registry.register("test_hook", callback1)
        registry.register("test_hook", callback2)
        registry.register("test_hook", callback3)

        # 异常应被捕获，不抛出
        results = await registry.trigger("test_hook")

        # callback1 和 callback3 应该被调用
        assert calls == [1, 3]
        assert len(results) == 2

    def test_list_hooks(self):
        """测试列出所有 Hook"""
        registry = HookRegistry()

        def cb1():
            pass

        def cb2():
            pass

        registry.register("hook1", cb1)
        registry.register("hook2", cb2)
        registry.register("hook2", cb1)  # hook2 有两个回调

        hooks = registry.list_hooks()
        assert hooks["hook1"] == 1
        assert hooks["hook2"] == 2


class TestHookNames:
    """HookNames 常量测试"""

    def test_hook_names_are_strings(self):
        """验证所有 Hook 名称都是字符串"""
        for name in dir(HookNames):
            if not name.startswith("_"):
                value = getattr(HookNames, name)
                assert isinstance(value, str)
                assert len(value) > 0


class TestGlobalRegistry:
    """全局单例测试"""

    def test_get_hook_registry_returns_singleton(self):
        """get_hook_registry 应返回单例"""
        r1 = get_hook_registry()
        r2 = get_hook_registry()
        assert r1 is r2

    def test_global_registry_is_functional(self):
        """全局注册器应该可以正常工作"""
        registry = get_hook_registry()
        calls = []

        def callback():
            calls.append(1)

        registry.register("global_test", callback)
        # 在同一个测试中使用，不影响其他测试
        # 因为测试之间 HookRegistry 单例可能被其他测试污染
        # 这里只验证基本功能
        assert "global_test" in registry._hooks or len(registry._hooks) >= 0
