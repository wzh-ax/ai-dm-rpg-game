"""
NPC Agent 单元测试
"""

import pytest
import asyncio
import json
from pathlib import Path
import sys
from unittest.mock import AsyncMock, MagicMock, patch
import tempfile
import os

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# 使用绝对导入
from src.npc_agent import (
    NPCAgent, NPCRegistry, NPCMetadata,
    NPCRole, NPCDisposition,
    get_npc_agent, init_npc_agent
)
from src.event_bus import EventType, get_event_bus


@pytest.fixture
def event_loop():
    """创建事件循环"""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


def _make_registry():
    """创建临时注册表（不使用 tmp_path fixture）"""
    tmp = tempfile.mkdtemp()
    return NPCRegistry(storage_path=os.path.join(tmp, "npcs"))


class TestNPCRegistry:
    """测试 NPC 注册表"""

    def test_register(self):
        """测试 NPC 注册"""
        registry = _make_registry()
        npc = NPCMetadata(
            id="test_npc_001",
            name="测试NPC",
            role=NPCRole.MERCHANT.value,
            disposition=NPCDisposition.FRIENDLY.value,
            core_concept="友好的商人"
        )

        registry.register(npc)

        assert registry.get_by_id("test_npc_001") is not None
        assert registry.get_by_id("test_npc_001").name == "测试NPC"

    def test_get_by_role(self):
        """测试按角色查询"""
        registry = _make_registry()
        npc1 = NPCMetadata(
            id="merchant_001",
            name="商人A",
            role=NPCRole.MERCHANT.value,
            disposition=NPCDisposition.NEUTRAL.value,
            core_concept="精明的商人"
        )
        npc2 = NPCMetadata(
            id="merchant_002",
            name="商人B",
            role=NPCRole.MERCHANT.value,
            disposition=NPCDisposition.GREEDY.value,
            core_concept="贪心的商人"
        )

        registry.register(npc1)
        registry.register(npc2)

        merchants = registry.get_by_role(NPCRole.MERCHANT.value)
        assert len(merchants) == 2

    def test_search(self):
        """测试搜索功能"""
        registry = _make_registry()
        npc = NPCMetadata(
            id="guard_001",
            name="守卫长",
            role=NPCRole.GUARD.value,
            disposition=NPCDisposition.HOSTILE.value,
            core_concept="严格的守卫"
        )

        registry.register(npc)

        results = registry.search("守卫")
        assert len(results) == 1
        assert results[0].name == "守卫长"

    def test_to_dict_from_dict(self):
        """测试序列化/反序列化"""
        npc = NPCMetadata(
            id="test_001",
            name="测试",
            role=NPCRole.VILLAGER.value,
            disposition=NPCDisposition.CURIOUS.value,
            core_concept="好奇的村民",
            tags=["勇敢", "冒险"],
            appearance="健壮的年轻人",
            personality="对新鲜事物充满好奇",
            speech_style="活泼开朗",
            secrets=["知道一个秘密"],
            knowledge=["了解本地传说"],
            quests=[{"title": "找猫", "description": "帮村长找走失的猫"}],
            dialogue="你好啊，陌生人！"
        )

        data = npc.to_dict()
        restored = NPCMetadata.from_dict(data)

        assert restored.id == npc.id
        assert restored.name == npc.name
        assert restored.tags == npc.tags
        assert restored.secrets == npc.secrets


class TestNPCMetadata:
    """测试 NPC 元数据"""

    def test_disposition_affects_sharing(self):
        """测试态度影响信息分享意愿"""
        friendly_npc = NPCMetadata(
            id="npc_001",
            name="友好NPC",
            role=NPCRole.VILLAGER.value,
            disposition=NPCDisposition.FRIENDLY.value,
            core_concept="友好",
            knowledge=["有用的信息"]
        )

        # 友好 NPC 应该更愿意分享
        sharing_count = 0
        for _ in range(20):
            if friendly_npc.can_share_info("有用的信息"):
                sharing_count += 1

        # 友好 NPC 分享概率应该较高（>70%）
        assert sharing_count >= 14


class TestNPCCreation:
    """测试 NPC Agent 创建（无 LLM）"""

    @pytest.mark.asyncio
    async def test_agent_init(self):
        """测试 Agent 初始化"""
        registry = _make_registry()
        agent = NPCAgent(registry=registry)
        await agent.initialize()

        assert agent.registry is not None
        assert agent._event_bus is not None

    @pytest.mark.asyncio
    async def test_fallback_profile(self):
        """测试备用 profile 生成"""
        registry = _make_registry()
        agent = NPCAgent(registry=registry)

        profile = agent._fallback_profile("merchant", "精明的交易者")

        assert "name" in profile
        assert "disposition" in profile
        assert "personality" in profile

    @pytest.mark.asyncio
    async def test_fallback_response(self):
        """测试备用对话响应"""
        registry = _make_registry()
        agent = NPCAgent(registry=registry)

        friendly_npc = NPCMetadata(
            id="test_001",
            name="友好NPC",
            role=NPCRole.VILLAGER.value,
            disposition=NPCDisposition.FRIENDLY.value,
            core_concept="友好"
        )

        response = agent._fallback_response(friendly_npc, "你好")
        assert len(response) > 0


class TestDialogueCache:
    """测试对话缓存"""

    @pytest.mark.asyncio
    async def test_cache_grows(self):
        """测试缓存增长（mock LLM 避免真实 API 调用）"""
        registry = _make_registry()
        agent = NPCAgent(registry=registry)

        npc = NPCMetadata(
            id="test_001",
            name="测试NPC",
            role=NPCRole.VILLAGER.value,
            disposition=NPCDisposition.NEUTRAL.value,
            core_concept="测试"
        )
        agent.registry.register(npc)

        # Mock LLM to avoid real API calls
        async def mock_response(*args, **kwargs):
            return "这是一个测试回复。"

        with patch.object(agent.llm, 'generate', new=AsyncMock(side_effect=mock_response)):
            # 模拟多轮对话
            for i in range(15):
                await agent.handle_dialogue(npc, f"玩家输入{i}", {})

        # 缓存应该被限制
        assert len(agent._dialogue_cache["test_001"]) <= 20  # max_cache_size * 2


class TestNPCGenerateWithMock:
    """测试 NPC 生成（mock LLM）"""

    @pytest.mark.asyncio
    async def test_generate_npc_full_pipeline_mock(self):
        """测试 NPC 四步生成流程（mock LLM）"""
        registry = _make_registry()
        agent = NPCAgent(registry=registry)
        await agent.initialize()

        mock_differentiation = "一个贪婪但有原则的商人"
        mock_profile = json.dumps({
            "name": "老陈",
            "disposition": "greedy",
            "tags": ["商人", "精明"],
            "appearance": "圆润的中年男子",
            "personality": "精明、狡猾但守信",
            "speech_style": "圆滑老练",
            "secrets": ["走私商人"],
            "knowledge": ["本地黑市"],
            "quests": [{"title": "黑市交易", "description": "帮他完成黑市交易"}]
        })
        mock_dialogue = "哟，客人来了！看看我这里的好货？"

        async def mock_generate(prompt, system_prompt=None, temperature=None):
            if "差异化" in prompt or "differentiation" in prompt.lower():
                return mock_differentiation
            elif "档案" in prompt or "profile" in prompt.lower():
                return mock_profile
            elif "开场白" in prompt or "dialogue" in prompt.lower():
                return mock_dialogue
            return "{}"

        with patch.object(agent.llm, 'generate', new=AsyncMock(side_effect=mock_generate)):
            npc = await agent.generate_npc("merchant", "贪婪的商人", "酒馆场景")
            assert npc is not None
            assert npc.name == "老陈"
            assert npc.role == "merchant"
            assert "走私商人" in npc.secrets

    @pytest.mark.asyncio
    async def test_handle_dialogue_mock(self):
        """测试对话处理（mock LLM）"""
        registry = _make_registry()
        agent = NPCAgent(registry=registry)
        await agent.initialize()

        npc = NPCMetadata(
            id="test_001",
            name="友好NPC",
            role=NPCRole.VILLAGER.value,
            disposition=NPCDisposition.FRIENDLY.value,
            core_concept="友好村民",
            dialogue="你好啊，陌生人！"
        )
        agent.registry.register(npc)

        mock_response = "很高兴认识你！这里是平静的小村庄。"

        async def mock_generate(prompt, system_prompt=None, temperature=None):
            return mock_response

        with patch.object(agent.llm, 'generate', new=AsyncMock(side_effect=mock_generate)):
            result = await agent.handle_dialogue(npc, "你好", {"location": "村庄"})
            assert result is not None
            assert "response" in result


class TestNPCCacheLimit:
    """测试 NPC 缓存限制"""

    @pytest.mark.asyncio
    async def test_cache_limit_enforced(self):
        """对话超过缓存限制时旧条目应被移除"""
        registry = _make_registry()
        agent = NPCAgent(registry=registry)
        agent._max_cache_size = 3  # 小缓存用于测试

        npc = NPCMetadata(
            id="cache_test",
            name="测试NPC",
            role=NPCRole.VILLAGER.value,
            disposition=NPCDisposition.CURIOUS.value,
            core_concept="测试"
        )
        agent.registry.register(npc)

        async def mock_response(*args, **kwargs):
            return "测试回复。"

        with patch.object(agent.llm, 'generate', new=AsyncMock(side_effect=mock_response)):
            # 模拟多轮对话
            for i in range(10):
                await agent.handle_dialogue(npc, f"玩家输入{i}", {})

        # 缓存大小不应超过限制
        cache_size = len(agent._dialogue_cache.get("cache_test", []))
        assert cache_size <= agent._max_cache_size * 2


class TestNPCSearch:
    """测试 NPC 搜索"""

    @pytest.mark.asyncio
    async def test_search_npc(self):
        """测试 NPC 搜索功能"""
        registry = _make_registry()
        agent = NPCAgent(registry=registry)
        await agent.initialize()

        npc1 = NPCMetadata(
            id="guard_001",
            name="城门守卫",
            role=NPCRole.GUARD.value,
            disposition=NPCDisposition.HOSTILE.value,
            core_concept="严格守卫"
        )
        npc2 = NPCMetadata(
            id="merchant_001",
            name="流动商人",
            role=NPCRole.MERCHANT.value,
            disposition=NPCDisposition.GREEDY.value,
            core_concept="精明的商人"
        )
        agent.registry.register(npc1)
        agent.registry.register(npc2)

        results = agent.search_npc("守卫")
        assert len(results) >= 1


class TestNPCEventHandling:
    """测试 NPC 事件处理"""

    @pytest.mark.asyncio
    async def test_on_npc_dialogue_event(self):
        """测试 NPC 对话事件处理"""
        registry = _make_registry()
        agent = NPCAgent(registry=registry)
        await agent.initialize()

        npc = NPCMetadata(
            id="event_test",
            name="测试NPC",
            role=NPCRole.VILLAGER.value,
            disposition=NPCDisposition.NEUTRAL.value,
            core_concept="测试"
        )
        agent.registry.register(npc)

        from src.event_bus import Event
        event = Event(
            type=None,  # 不重要
            data={
                "npc_id": "event_test",
                "player_input": "你好",
                "context": {}
            },
            source="test"
        )

        # 应该不报错
        result = await agent._on_npc_dialogue(event)
        # fallback 情况下可能返回 None 或 dict


class TestNPCFallback:
    """测试 NPC fallback 方法"""

    @pytest.mark.asyncio
    async def test_fallback_profile_structure(self):
        """fallback profile 应有正确结构"""
        registry = _make_registry()
        agent = NPCAgent(registry=registry)
        profile = agent._fallback_profile("merchant", "精明的交易者")
        assert "name" in profile
        assert "disposition" in profile
        assert "personality" in profile
        assert "speech_style" in profile

    @pytest.mark.asyncio
    async def test_generate_initial_dialogue_fallback(self):
        """初始对话 fallback"""
        registry = _make_registry()
        agent = NPCAgent(registry=registry)
        dialogue = await agent._generate_initial_dialogue(
            "老王", "圆滑老练", "说话很有商人风范"
        )
        assert isinstance(dialogue, str)
        assert len(dialogue) > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
