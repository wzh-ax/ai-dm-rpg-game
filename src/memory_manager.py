"""
Memory Manager - 记忆管理系统
实现分层记忆(短期/长期)+ RAG 检索
"""

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING

from .event_bus import EventBus, EventType, Event, get_event_bus

if TYPE_CHECKING:
    from .minimax_interface import MiniMaxInterface

logger = logging.getLogger(__name__)


class MemoryType(str, Enum):
    """记忆类型"""
    SHORT_TERM = "short_term"
    LONG_TERM = "long_term"
    BEAT_SUMMARY = "beat_summary"
    CRITICAL_EVENT = "critical_event"  # 重大事件立即写入


@dataclass
class MemoryEntry:
    """记忆条目"""
    id: str
    type: MemoryType
    content: str
    timestamp: float
    metadata: dict = field(default_factory=dict)
    relevance_score: float = 0.0  # 用于 RAG 检索评分

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "type": self.type.value,
            "content": self.content,
            "timestamp": self.timestamp,
            "metadata": self.metadata,
            "relevance_score": self.relevance_score,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "MemoryEntry":
        return cls(
            id=data["id"],
            type=MemoryType(data["type"]),
            content=data["content"],
            timestamp=data["timestamp"],
            metadata=data.get("metadata", {}),
            relevance_score=data.get("relevance_score", 0.0),
        )


@dataclass
class BeatSummary:
    """Beat 总结"""
    beat_id: str
    scene: str
    player_action: str
    key_events: list[str]
    npcs_involved: list[str]
    items_obtained: list[str]
    decisions: list[str]
    next_hooks: list[str]  # 下一 Beat 的悬念点
    raw_content: str = ""  # 原始 LLM 生成内容

    def to_dict(self) -> dict:
        return {
            "beat_id": self.beat_id,
            "scene": self.scene,
            "player_action": self.player_action,
            "key_events": self.key_events,
            "npcs_involved": self.npcs_involved,
            "items_obtained": self.items_obtained,
            "decisions": self.decisions,
            "next_hooks": self.next_hooks,
            "raw_content": self.raw_content,
        }

    def to_memory_content(self) -> str:
        """转换为可读记忆文本"""
        lines = [f"**Beat {self.beat_id}** ({self.scene})"]
        if self.decisions:
            lines.append(f"玩家决策: {'; '.join(self.decisions)}")
        if self.key_events:
            lines.append(f"关键事件: {'; '.join(self.key_events)}")
        if self.npcs_involved:
            lines.append(f"涉及NPC: {', '.join(self.npcs_involved)}")
        if self.items_obtained:
            lines.append(f"获得物品: {', '.join(self.items_obtained)}")
        if self.next_hooks:
            lines.append(f"悬念: {'; '.join(self.next_hooks)}")
        return "\n".join(lines)


class ShortTermMemory:
    """
    短期记忆
    - 当前 session 上下文
    - 当前 Beat 详细内容
    - 玩家即时动作
    """

    MAX_HISTORY = 50  # 最多保留 50 条短期记忆

    def __init__(self):
        self.current_beat: BeatSummary | None = None
        self.history: list[MemoryEntry] = []
        self.current_session_context: dict = {
            "scene": None,
            "location": None,
            "active_npcs": [],
            "player_state": {},
        }

    def add_entry(self, entry: MemoryEntry):
        """添加短期记忆条目"""
        self.history.append(entry)
        if len(self.history) > self.MAX_HISTORY:
            self.history.pop(0)

    def set_current_beat(self, beat: BeatSummary):
        """设置当前 Beat"""
        self.current_beat = beat

    def update_context(self, **kwargs):
        """更新当前会话上下文"""
        self.current_session_context.update(kwargs)

    def get_recent(self, n: int = 10) -> list[MemoryEntry]:
        """获取最近 n 条记忆"""
        return self.history[-n:]

    def search(self, query: str) -> list[MemoryEntry]:
        """简单关键词搜索(生产环境应接入 embedding)"""
        query_lower = query.lower()
        return [
            e for e in self.history
            if query_lower in e.content.lower()
        ]

    def clear(self):
        """清空短期记忆(session 结束时由 MemoryManager 调用)"""
        self.history.clear()
        self.current_beat = None


class LongTermMemoryStore:
    """
    长期记忆存储
    - 历史事件、人物关系
    - 剧情进度、已解锁区域
    - 玩家画像
    """

    def __init__(self, storage_dir: Path | None = None):
        self.storage_dir = storage_dir or Path("data/memory")
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self._memory_index: list[MemoryEntry] = []
        self._character_relations: dict[str, list[str]] = {}
        self._load_index()

    def _load_index(self):
        """从磁盘加载记忆索引"""
        index_file = self.storage_dir / "index.json"
        if index_file.exists():
            try:
                with open(index_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self._memory_index = [
                        MemoryEntry.from_dict(e) for e in data.get("entries", [])
                    ]
                    self._character_relations = data.get("character_relations", {})
                logger.info(f"Loaded {len(self._memory_index)} long-term memory entries")
            except Exception as e:
                logger.warning(f"Failed to load memory index: {e}")

    def _save_index(self):
        """保存记忆索引到磁盘"""
        index_file = self.storage_dir / "index.json"
        data = {
            "entries": [e.to_dict() for e in self._memory_index],
            "character_relations": self._character_relations,
            "updated_at": time.time(),
        }
        try:
            with open(index_file, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Failed to save memory index: {e}")

    def add(self, entry: MemoryEntry):
        """添加长期记忆"""
        self._memory_index.append(entry)
        self._save_index()
        logger.info(f"Added long-term memory: {entry.id} ({entry.type.value})")

    def add_beat_summary(self, beat: BeatSummary):
        """添加 Beat 总结到长期记忆"""
        entry = MemoryEntry(
            id=f"beat_{beat.beat_id}",
            type=MemoryType.BEAT_SUMMARY,
            content=beat.to_memory_content(),
            timestamp=time.time(),
            metadata=beat.to_dict(),
        )
        self.add(entry)

    def add_critical_event(self, event_type: str, content: str, metadata: dict | None = None):
        """立即写入重大事件"""
        entry = MemoryEntry(
            id=f"critical_{int(time.time() * 1000)}",
            type=MemoryType.CRITICAL_EVENT,
            content=content,
            timestamp=time.time(),
            metadata={**(metadata or {}), "event_type": event_type},
        )
        self.add(entry)

    def add_character_relation(self, char1: str, char2: str, relation: str):
        """记录人物关系"""
        if char1 not in self._character_relations:
            self._character_relations[char1] = []
        self._character_relations[char1].append(f"{char2}:{relation}")
        self._save_index()

    def search(self, query: str, limit: int = 5) -> list[MemoryEntry]:
        """
        简单关键词搜索
        生产环境应接入 embedding + 向量检索
        """
        query_lower = query.lower()
        scored = []
        for e in self._memory_index:
            score = 0.0
            # 精确匹配加分
            if query_lower in e.content.lower():
                score = 1.0
            # 标题/标签匹配加分
            if e.metadata.get("scene", "").lower() == query_lower:
                score = 1.5
            if score > 0:
                e.relevance_score = score
                scored.append(e)
        # 按相关度排序
        scored.sort(key=lambda x: x.relevance_score, reverse=True)
        return scored[:limit]

    def get_player_profile(self) -> dict:
        """获取玩家画像"""
        profile = {
            "total_beats": 0,
            "decisions": [],
            "npcs_met": set(),
            "items_collected": set(),
            "critical_events": [],
        }
        for e in self._memory_index:
            if e.type == MemoryType.BEAT_SUMMARY:
                meta = e.metadata
                profile["total_beats"] += 1
                profile["decisions"].extend(meta.get("decisions", []))
                profile["npcs_met"].update(meta.get("npcs_involved", []))
                profile["items_collected"].update(meta.get("items_obtained", []))
            elif e.type == MemoryType.CRITICAL_EVENT:
                profile["critical_events"].append(e.content)
        # 转换为可序列化
        profile["npcs_met"] = list(profile["npcs_met"])
        profile["items_collected"] = list(profile["items_collected"])
        return profile

    def get_story_progress(self) -> list[str]:
        """获取剧情进度(按 beat 排列)"""
        beats = [
            e for e in self._memory_index
            if e.type == MemoryType.BEAT_SUMMARY
        ]
        return [e.content for e in beats]


class MemoryManager:
    """
    记忆管理器
    协调短期记忆与长期记忆,处理 RAG 检索
    """

    def __init__(
        self,
        event_bus: EventBus | None = None,
        llm: "MiniMaxInterface | None" = None,
        storage_dir: Path | None = None,
    ):
        self.event_bus = event_bus or get_event_bus()
        self.llm = llm
        self.subscriber_id = "memory_manager"

        self.short_term = ShortTermMemory()
        self.long_term = LongTermMemoryStore(storage_dir)

        # 注册事件监听
        self._subscriptions: list[asyncio.Task] = []

    async def start(self):
        """启动记忆管理器"""
        # 监听叙事输出事件 -> 自动生成 Beat Summary
        task1 = asyncio.create_task(
            self.event_bus.subscribe(
                EventType.NARRATIVE_OUTPUT,
                self._on_narrative_output,
                self.subscriber_id
            )
        )
        # 监听游戏结束事件 -> 清空短期记忆
        task2 = asyncio.create_task(
            self.event_bus.subscribe(
                EventType.GAME_END,
                self._on_game_end,
                self.subscriber_id
            )
        )
        self._subscriptions = [task1, task2]
        logger.info("Memory Manager started")

    async def stop(self):
        """停止记忆管理器"""
        for task in self._subscriptions:
            task.cancel()
        await self.event_bus.unsubscribe_all(self.subscriber_id)
        logger.info("Memory Manager stopped")

    async def _on_narrative_output(self, event: Event):
        """叙事输出时 -> 生成 Beat Summary"""
        data = event.data
        narrative = data.get("text", "")
        turn = data.get("turn", 0)

        # 从当前上下文中提取信息构建 BeatSummary
        beat = BeatSummary(
            beat_id=f"beat_{turn}",
            scene=self.short_term.current_session_context.get("scene", "unknown"),
            player_action=data.get("player_input", ""),
            key_events=[],  # TODO: 后续从 narrative 中提取
            npcs_involved=self.short_term.current_session_context.get("active_npcs", []),
            items_obtained=[],
            decisions=[],  # TODO: 后续从 player_input 中识别
            next_hooks=[],  # TODO: 后续生成悬念点
            raw_content=narrative,
        )

        # 保存到短期记忆
        self.short_term.set_current_beat(beat)

        # 自动生成 Beat Summary 内容
        if self.llm:
            await self._generate_beat_summary_llm(beat, narrative)

        # 写入长期记忆
        self.long_term.add_beat_summary(beat)

        logger.info(f"Beat Summary generated for turn {turn}")

    async def _on_game_end(self, event: Event):
        """游戏结束时 -> 清空短期记忆"""
        self.short_term.clear()
        logger.info("Short-term memory cleared on game end")

    async def _generate_beat_summary_llm(self, beat: BeatSummary, narrative: str):
        """使用 LLM 生成 Beat Summary(增强版)"""
        if not self.llm:
            return

        prompt = f"""分析以下叙事内容,提取关键信息生成 Beat Summary。

叙事内容:
{narrative[:1000]}

请提取并返回(JSON格式):
{{
    "key_events": ["事件1", "事件2"],
    "decisions": ["玩家决策1"],
    "next_hooks": ["悬念1"],
    "npcs_involved": ["NPC名"],
    "items_obtained": ["物品名"]
}}
"""

        try:
            response = await self.llm.generate(prompt)
            # 简单解析 JSON(生产环境用 json.loads + 错误处理)
            import re
            match = re.search(r'\{.*\}', response, re.DOTALL)
            if match:
                data = json.loads(match.group())
                for key in ["key_events", "decisions", "next_hooks", "npcs_involved", "items_obtained"]:
                    if key in data:
                        setattr(beat, key, data[key])
        except Exception as e:
            logger.warning(f"Failed to generate beat summary via LLM: {e}")

    # ==================== 外部接口 ====================

    async def record_player_action(self, action: str, context: dict | None = None):
        """记录玩家动作"""
        entry = MemoryEntry(
            id=f"action_{int(time.time() * 1000)}",
            type=MemoryType.SHORT_TERM,
            content=action,
            timestamp=time.time(),
            metadata=context or {},
        )
        self.short_term.add_entry(entry)

        # 发布记忆更新事件(供其他 Agent 使用)
        await self.event_bus.publish(Event(
            type=EventType.SUBNET_AGENT_RESULT,
            data={
                "agent": "memory_manager",
                "action": "player_action_recorded",
                "action": action,
            },
            source=self.subscriber_id
        ))

    async def record_critical_event(self, event_type: str, content: str, metadata: dict | None = None):
        """立即写入重大事件"""
        self.long_term.add_critical_event(event_type, content, metadata)

    def retrieve(self, query: str, limit: int = 5) -> list[MemoryEntry]:
        """
        RAG 检索:查询相关记忆
        先查长期记忆,再补充短期记忆
        """
        long_term_results = self.long_term.search(query, limit)

        # 如果长期记忆不足,补充短期记忆
        if len(long_term_results) < limit:
            short_term_results = self.short_term.search(query)
            for e in short_term_results:
                if e not in long_term_results:
                    long_term_results.append(e)

        return long_term_results[:limit]

    def get_context_for_prompt(self, query: str = "") -> str:
        """
        获取用于填充 prompt 的记忆上下文
        RAG 检索 + 格式化为文本
        """
        entries = self.retrieve(query)

        if not entries:
            return ""

        sections = ["## 相关记忆\n"]
        for e in entries:
            type_label = {
                MemoryType.LONG_TERM: "[长期记忆]",
                MemoryType.SHORT_TERM: "[短期记忆]",
                MemoryType.BEAT_SUMMARY: "[Beat总结]",
                MemoryType.CRITICAL_EVENT: "[重大事件]",
            }.get(e.type, "[记忆]")

            sections.append(f"{type_label} {e.content}")

        return "\n\n".join(sections)

    def get_player_profile(self) -> dict:
        """获取玩家画像"""
        return self.long_term.get_player_profile()

    def get_story_progress(self) -> list[str]:
        """获取剧情进度"""
        return self.long_term.get_story_progress()


# 全局单例
_global_memory_manager: MemoryManager | None = None


def get_memory_manager() -> MemoryManager:
    """获取全局 Memory Manager 实例"""
    global _global_memory_manager
    if _global_memory_manager is None:
        _global_memory_manager = MemoryManager()
    return _global_memory_manager


async def init_memory_manager(
    event_bus: EventBus | None = None,
    llm=None,
    storage_dir: Path | None = None,
) -> MemoryManager:
    """初始化并启动全局 Memory Manager"""
    manager = get_memory_manager()
    if event_bus:
        manager.event_bus = event_bus
    if llm:
        manager.llm = llm
    await manager.start()
    return manager
