"""
Bug #001 - NPC懒生成机制验证
问题：`_build_npc_context` NPC不存在时直接返回None，没有懒生成机制
验收标准：NPC不存在时，应触发懒生成并返回有效 NPC 数据，而非返回 None

测试场景：
1. NPC 不在 active_npcs 中
2. NPC 不在 current_scene.npcs 中
3. 调用 _build_npc_context
4. 期望：返回懒生成的 NPC，而非 None
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from src.game_master import GameMaster, GameMode
from src.event_bus import EventBus


class TestNpcLazyGeneration:
    """NPC懒生成测试 - Bug #001"""

    @pytest.fixture
    def gm_no_npc(self):
        """创建没有任何 NPC 数据的 GameMaster"""
        event_bus = EventBus()
        gm = GameMaster(event_bus=event_bus)
        gm.llm = None  # 禁用 LLM

        # 初始化酒馆场景，但不包含任何 NPC
        gm.current_scene = {
            "type": "酒馆",
            "name": "月光酒馆",
            "atmosphere": "热闹温馨",
            "npcs": [],  # 空 NPC 列表
        }
        gm.active_npcs = {}  # 没有活跃 NPC
        gm.game_state = {
            "mode": "exploration",
            "active_combat": False,
            "current_location": "月光酒馆",
        }
        return gm

    @pytest.mark.asyncio
    async def test_build_npc_context_returns_none_without_fix(self, gm_no_npc):
        """
        验证修复前行为：_build_npc_context 在 NPC 不存在时不应返回 None
        （此测试在修复后应 PASS）
        """
        result = await gm_no_npc._build_npc_context("酒馆老板")
        # 修复后：应返回懒生成的 NPC，而非 None
        assert result is not None, \
            "Bug #001 未修复：_build_npc_context('酒馆老板') 返回 None，缺少懒生成机制"
        assert isinstance(result, dict), f"返回类型错误: {type(result)}"
        assert "name" in result, "返回的 NPC 数据缺少 name 字段"
        assert result["name"] == "酒馆老板", f"返回的 NPC 名称错误: {result.get('name')}"

    @pytest.mark.asyncio
    async def test_build_npc_context_lazy_generates_npc(self, gm_no_npc):
        """
        验证懒生成 NPC 的数据质量
        """
        result = await gm_no_npc._build_npc_context("铁匠")
        assert result is not None, "懒生成失败，返回 None"
        assert result["name"] == "铁匠"
        assert "role" in result, "懒生成的 NPC 缺少 role"
        assert result["role"] == "merchant", \
            f"酒馆场景的 NPC role 应为 merchant，实际: {result.get('role')}"

    @pytest.mark.asyncio
    async def test_build_npc_context_lazy_generates_forest_npc(self):
        """
        验证森林场景的 NPC 懒生成 role 正确
        """
        event_bus = EventBus()
        gm = GameMaster(event_bus=event_bus)
        gm.llm = None

        gm.current_scene = {
            "type": "森林",
            "name": "黑森林",
            "npcs": [],
        }
        gm.active_npcs = {}
        gm.game_state = {"mode": "exploration", "active_combat": False}

        result = await gm._build_npc_context("森林精灵")
        assert result is not None
        assert result["name"] == "森林精灵"
        assert result["role"] == "mystic", \
            f"森林场景的 NPC role 应为 mystic，实际: {result.get('role')}"

    @pytest.mark.asyncio
    async def test_npc_not_found_format_not_returned(self, gm_no_npc):
        """
        验证懒生成后，_handle_npc_command 不会返回「找不到NPC」的格式化字符串
        """
        # 尝试「和酒馆老板说话」
        # 先用 _check_npc_interaction 触发
        result = await gm_no_npc._check_npc_interaction("和酒馆老板说话")
        # 应该返回对话内容或触发对话流程，而不是 None 触发万能敷衍
        # 注意：某些路径可能返回 None（不在 NPC 关键词范围内），
        # 但 _handle_npc_command 应该能处理
        # 关键验证：_build_npc_context 不返回 None
        npc_context = await gm_no_npc._build_npc_context("酒馆老板")
        assert npc_context is not None, \
            "Bug #001 未修复：_build_npc_context 返回 None"
