"""
Memory Manager 单元测试
"""

import asyncio
import tempfile
import pytest
from pathlib import Path

from src.memory_manager import (
    MemoryManager,
    ShortTermMemory,
    LongTermMemoryStore,
    MemoryEntry,
    BeatSummary,
    MemoryType,
)


class TestShortTermMemory:
    """短期记忆测试"""

    def test_add_entry(self):
        mem = ShortTermMemory()
        entry = MemoryEntry(
            id="test1",
            type=MemoryType.SHORT_TERM,
            content="玩家拿起了一把剑",
            timestamp=0.0,
        )
        mem.add_entry(entry)
        assert len(mem.history) == 1
        assert mem.history[0].content == "玩家拿起了一把剑"

    def test_history_limit(self):
        mem = ShortTermMemory()
        for i in range(60):
            entry = MemoryEntry(
                id=f"test{i}",
                type=MemoryType.SHORT_TERM,
                content=f"动作{i}",
                timestamp=float(i),
            )
            mem.add_entry(entry)
        # 超过 MAX_HISTORY(50) 应该移除最旧的
        assert len(mem.history) == 50
        assert mem.history[0].id == "test10"

    def test_set_current_beat(self):
        mem = ShortTermMemory()
        beat = BeatSummary(
            beat_id="beat_1",
            scene="古老城堡",
            player_action="进入大门",
            key_events=["发现暗门"],
            npcs_involved=["守卫"],
            items_obtained=[],
            decisions=["探索暗门"],
            next_hooks=["暗门后是什么？"],
        )
        mem.set_current_beat(beat)
        assert mem.current_beat is not None
        assert mem.current_beat.scene == "古老城堡"

    def test_update_context(self):
        mem = ShortTermMemory()
        mem.update_context(scene="酒馆", location="下城区")
        assert mem.current_session_context["scene"] == "酒馆"
        assert mem.current_session_context["location"] == "下城区"

    def test_search(self):
        mem = ShortTermMemory()
        mem.add_entry(MemoryEntry("1", MemoryType.SHORT_TERM, "玩家攻击了怪物", 0.0))
        mem.add_entry(MemoryEntry("2", MemoryType.SHORT_TERM, "玩家进入酒馆", 0.0))
        results = mem.search("攻击")
        assert len(results) == 1
        assert "攻击" in results[0].content


class TestLongTermMemoryStore:
    """长期记忆存储测试"""

    def test_add_and_search(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = LongTermMemoryStore(Path(tmpdir))
            entry = MemoryEntry(
                id="test_long_1",
                type=MemoryType.LONG_TERM,
                content="玩家与酒馆老板交谈",
                timestamp=0.0,
                metadata={"scene": "酒馆"},
            )
            store.add(entry)

            results = store.search("酒馆")
            assert len(results) >= 1

    def test_add_beat_summary(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = LongTermMemoryStore(Path(tmpdir))
            beat = BeatSummary(
                beat_id="beat_1",
                scene="酒馆",
                player_action="与老板交谈",
                key_events=["获得任务线索"],
                npcs_involved=["酒馆老板"],
                items_obtained=[],
                decisions=["接受任务"],
                next_hooks=["任务目标在哪？"],
            )
            store.add_beat_summary(beat)

            results = store.search("酒馆老板")
            assert len(results) >= 1
            assert results[0].type == MemoryType.BEAT_SUMMARY

    def test_add_critical_event(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = LongTermMemoryStore(Path(tmpdir))
            store.add_critical_event(
                event_type="character_death",
                content="守卫队长战死",
                metadata={"location": "城门"},
            )

            results = store.search("战死")
            assert len(results) >= 1
            assert results[0].type == MemoryType.CRITICAL_EVENT

    def test_player_profile(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = LongTermMemoryStore(Path(tmpdir))

            beat1 = BeatSummary(
                beat_id="beat_1",
                scene="酒馆",
                player_action="进入",
                key_events=["遇见老板"],
                npcs_involved=["酒馆老板"],
                items_obtained=["情报"],
                decisions=["询问任务"],
                next_hooks=[],
            )
            store.add_beat_summary(beat1)

            profile = store.get_player_profile()
            assert profile["total_beats"] == 1
            assert "酒馆老板" in profile["npcs_met"]
            assert "情报" in profile["items_collected"]

    def test_persistence(self):
        """测试数据持久化"""
        with tempfile.TemporaryDirectory() as tmpdir:
            store1 = LongTermMemoryStore(Path(tmpdir))
            store1.add(MemoryEntry("p1", MemoryType.LONG_TERM, "持久化测试", 0.0))

            # 重新创建 store，应该能读到数据
            store2 = LongTermMemoryStore(Path(tmpdir))
            results = store2.search("持久化测试")
            assert len(results) >= 1


class TestBeatSummary:
    """Beat Summary 测试"""

    def test_to_memory_content(self):
        beat = BeatSummary(
            beat_id="beat_5",
            scene="地下城",
            player_action="探索房间",
            key_events=["触发陷阱", "发现宝箱"],
            npcs_involved=["无"],
            items_obtained=["魔法钥匙"],
            decisions=["解除陷阱"],
            next_hooks=["钥匙有什么用？"],
        )
        content = beat.to_memory_content()
        assert "Beat beat_5" in content
        assert "地下城" in content
        assert "魔法钥匙" in content
        assert "解除陷阱" in content

    def test_to_dict(self):
        beat = BeatSummary(
            beat_id="beat_1",
            scene="酒馆",
            player_action="进入",
            key_events=["遇见老板"],
            npcs_involved=["老板"],
            items_obtained=[],
            decisions=[],
            next_hooks=["接下来做什么？"],
        )
        d = beat.to_dict()
        assert d["beat_id"] == "beat_1"
        assert d["scene"] == "酒馆"
        assert d["key_events"] == ["遇见老板"]


class TestMemoryManager:
    """Memory Manager 测试（集成 EventBus）"""

    @pytest.mark.asyncio
    async def test_init(self):
        from src.event_bus import EventBus
        eb = EventBus()
        mm = MemoryManager(event_bus=eb)
        assert mm.event_bus is eb
        assert mm.short_term is not None
        assert mm.long_term is not None

    @pytest.mark.asyncio
    async def test_record_player_action(self):
        from src.event_bus import EventBus
        eb = EventBus()
        mm = MemoryManager(event_bus=eb)
        await mm.record_player_action("攻击史莱姆", {"damage": 10})
        assert len(mm.short_term.history) == 1
        assert "攻击史莱姆" in mm.short_term.history[0].content

    @pytest.mark.asyncio
    async def test_retrieve(self):
        from src.event_bus import EventBus
        eb = EventBus()
        with tempfile.TemporaryDirectory() as tmpdir:
            mm = MemoryManager(event_bus=eb, storage_dir=Path(tmpdir))
            mm.long_term.add(MemoryEntry(
                "r1",
                MemoryType.LONG_TERM,
                "玩家获得了一把传说之剑",
                0.0,
            ))

            results = mm.retrieve("传说之剑")
            assert len(results) >= 1

    @pytest.mark.asyncio
    async def test_get_context_for_prompt(self):
        from src.event_bus import EventBus
        eb = EventBus()
        with tempfile.TemporaryDirectory() as tmpdir:
            mm = MemoryManager(event_bus=eb, storage_dir=Path(tmpdir))
            mm.long_term.add(MemoryEntry(
                "ctx1",
                MemoryType.BEAT_SUMMARY,
                "玩家在酒馆接受了任务",
                0.0,
                metadata={"scene": "酒馆"},
            ))

            context = mm.get_context_for_prompt("酒馆")
            assert "酒馆" in context
            assert "记忆" in context or "Beat" in context


# ============ pytest 配置 ============

@pytest.fixture
def event_loop():
    """提供事件循环用于异步测试"""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()
