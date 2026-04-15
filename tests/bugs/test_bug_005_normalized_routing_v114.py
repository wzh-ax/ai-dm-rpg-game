# -*- coding: utf-8 -*-
"""
Bug #005 - NPC关键词匹配覆盖不足（V1_1_4新问题）
问题：`_normalize_command` 和 `_check_npc_interaction` 是两条独立路径，
     归一化结果没有传递给关键词检测层，导致同一个输入在不同阶段被不同处理

验收标准：
1. _normalize_command 返回的 cmd_type/npc_name 能在 _check_npc_interaction 中正确路由
2. 归一化层提取的 NPC 名称，在关键词检测层应被复用（而非重新提取）
3. 中英文命令走相同路径
"""
import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from src.game_master import GameMaster, GameMode
from src.event_bus import EventBus


class TestBug005NormalizedRouting:
    """NPC关键词匹配覆盖测试 - Bug #005"""

    @pytest.fixture
    def gm(self):
        """创建 GameMaster"""
        event_bus = EventBus()
        gm = GameMaster(event_bus=event_bus)
        gm.llm = None  # 禁用 LLM
        gm.npc_agent = None
        
        gm.current_scene = {
            "type": "酒馆",
            "name": "月光酒馆",
            "atmosphere": "热闹温馨",
            "npcs": [
                {"id": "npc_001", "name": "酒馆老板", "role": "merchant"}
            ],
        }
        gm.active_npcs = {"npc_001": {"id": "npc_001", "name": "酒馆老板", "role": "merchant"}}
        gm.game_state = {
            "mode": "exploration",
            "active_combat": False,
            "current_location": "月光酒馆",
            "turn": 0,
        }
        gm.mode = GameMode.EXPLORATION
        return gm

    def test_normalize_command_extracts_npc_name(self, gm):
        """验证 _normalize_command 能正确提取 NPC 名称"""
        result = gm._normalize_command("和酒馆老板说话")
        assert result.get("cmd_type") == "npc_talk", f"期望 npc_talk，实际: {result.get('cmd_type')}"
        assert result.get("params", {}).get("npc_name") == "酒馆老板", \
            f"期望 酒馆老板，实际: {result.get('params', {}).get('npc_name')}"

    def test_normalize_command_chinese_and_english_same_type(self, gm):
        """验证中英文命令归一化到相同类型"""
        cn = gm._normalize_command("和酒馆老板说话")
        en = gm._normalize_command("talk to innkeeper")
        assert cn.get("cmd_type") == "npc_talk", "中文命令应归一化为 npc_talk"
        assert en.get("cmd_type") == "npc_talk", "英文命令应归一化为 npc_talk"
        assert cn.get("params", {}).get("npc_name") == "酒馆老板"
        assert en.get("params", {}).get("npc_name") == "innkeeper"

    def test_normalized_result_passed_to_check_npc_interaction(self, gm):
        """
        B005 核心验证：_check_npc_interaction 接收并使用 normalized 参数
        而非独立重新解析输入
        """
        # 构造一个 normalized 结果
        normalized = {
            "action": None,
            "cmd_type": "npc_talk",
            "params": {"npc_name": "酒馆老板"}
        }
        
        # 直接测试 _check_npc_interaction 是否优先使用 normalized
        # 由于 gm._handle_npc_command 内部会调用 _build_npc_context
        # 我们 mock _build_npc_context 来隔离测试
        async def mock_build_npc(name):
            return {"id": "npc_001", "name": name, "role": "merchant"}
        
        gm._build_npc_context = mock_build_npc
        
        result = asyncio.get_event_loop().run_until_complete(
            gm._check_npc_interaction("和酒馆老板说话", normalized=normalized)
        )
        
        # 验证：即使输入是"和酒馆老板说话"，也应该用 normalized 中的 npc_name
        assert result is not None, "normalized 已提供时，_check_npc_interaction 不应返回 None"

    @pytest.mark.asyncio
    async def test_check_npc_interaction_with_normalized_avoids_keyword_reparse(self, gm):
        """
        验证：传递 normalized 后，不走关键词重解析路径
        模拟一个场景：输入是纯文本不含 NPC 关键词，但 normalized 包含 NPC 命令
        """
        # 使用一个没有 NPC 关键词的输入
        player_text = "酒馆老板"  # 只有名字，没有"和...说话"
        
        # 但 normalized 告诉它是 NPC 对话
        normalized = {
            "action": None,
            "cmd_type": "npc_talk",
            "params": {"npc_name": "酒馆老板"}
        }
        
        # Mock _handle_npc_command 来避免实际 LLM 调用
        async def mock_handle(cmd_type, params):
            return f"[NPC对话] {params.get('npc_name')}"
        
        gm._handle_npc_command = mock_handle
        
        result = await gm._check_npc_interaction(player_text, normalized=normalized)
        
        # 关键验证：即使 player_text 没有 NPC 关键词，
        # 有了 normalized 也应该正确路由
        assert result is not None, \
            "Bug #005 未修复：normalized 包含 npc_talk 时应正确路由"

    @pytest.mark.asyncio
    async def test_normalized_routing_chinese_talk(self, gm):
        """验证中文 NPC 对话归一化路由"""
        normalized = gm._normalize_command("和酒馆老板说话")
        assert normalized["cmd_type"] == "npc_talk"
        
        async def mock_handle(cmd_type, params):
            return f"[对话] {params.get('npc_name')}"
        gm._handle_npc_command = mock_handle
        
        result = await gm._check_npc_interaction("和酒馆老板说话", normalized=normalized)
        assert result is not None

    @pytest.mark.asyncio
    async def test_normalized_routing_quest(self, gm):
        """验证 NPC 任务查询归一化路由"""
        normalized = gm._normalize_command("向酒馆老板询问任务")
        assert normalized["cmd_type"] == "npc_quest"
        
        async def mock_handle(cmd_type, params):
            return f"[任务] {params.get('npc_name')}"
        gm._handle_npc_command = mock_handle
        
        result = await gm._check_npc_interaction("向酒馆老板询问任务", normalized=normalized)
        assert result is not None

    @pytest.mark.asyncio
    async def test_check_npc_interaction_without_normalized_still_works(self, gm):
        """验证不传 normalized 时，降级到关键词检测仍能工作"""
        # 当前场景有 NPC，即使不传 normalized 也应能工作
        gm._current_npc_id = "npc_001"
        
        result = await gm._check_npc_interaction("和酒馆老板说话", normalized=None)
        # 降级路径：走关键词检测
        assert result is not None, "不传 normalized 时关键词检测路径应正常工作"


class TestBug005NaturalLanguageVariants:
    """B005: 自然语言变体验证"""

    @pytest.fixture
    def gm(self):
        event_bus = EventBus()
        gm = GameMaster(event_bus=event_bus)
        gm.llm = None
        gm.npc_agent = None
        gm.current_scene = {
            "type": "酒馆", "name": "月光酒馆", "atmosphere": "热闹", "npcs": []
        }
        gm.active_npcs = {}
        gm.game_state = {
            "mode": "exploration", "active_combat": False,
            "current_location": "月光酒馆", "turn": 0
        }
        gm.mode = GameMode.EXPLORATION
        return gm

    def test_various_npc_phrasings_normalize_correctly(self, gm):
        """验证各种 NPC 对话说法都能归一化"""
        test_cases = [
            ("和酒馆老板说话", "npc_talk", "酒馆老板"),
            ("向老板询问任务", "npc_quest", "老板"),
            ("跟酒馆老板聊天", "npc_chat", "酒馆老板"),
            ("和铁匠交谈", "npc_chat", "铁匠"),
        ]
        
        for text, expected_type, expected_name in test_cases:
            result = gm._normalize_command(text)
            assert result.get("cmd_type") == expected_type, \
                f"'{text}' 应归一化为 {expected_type}，实际: {result.get('cmd_type')}"
            assert result.get("params", {}).get("npc_name") == expected_name, \
                f"'{text}' npc_name 应为 {expected_name}，实际: {result.get('params', {}).get('npc_name')}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
