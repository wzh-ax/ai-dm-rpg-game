"""
SceneAgent 单元测试
"""

import pytest
import asyncio
import json
import tempfile
import shutil
from pathlib import Path
import sys
from unittest.mock import AsyncMock, MagicMock, patch

# 添加 src 目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.scene_agent import SceneAgent, SceneRegistry, SceneMetadata


class TestSceneRegistry:
    """SceneRegistry 测试"""

    @pytest.fixture
    def registry(self):
        """使用临时存储（避免Windows tmp_path权限问题）"""
        temp_dir = Path(tempfile.mkdtemp(prefix="scene_test_"))
        registry = SceneRegistry(storage_path=str(temp_dir / "scenes"))
        yield registry
        # Cleanup
        shutil.rmtree(temp_dir, ignore_errors=True)

    def test_register_scene(self, registry):
        scene = SceneMetadata(
            id="test_001",
            type="forest",
            core_concept="Test concept",
            tags=["test", "forest"]
        )
        registry.register(scene)

        assert registry.get_by_id("test_001") == scene
        assert len(registry.get_by_type("forest")) == 1

    def test_get_all_tags(self, registry):
        scene1 = SceneMetadata(
            id="forest_001",
            type="forest",
            core_concept="Ancient battlefield",
            tags=["haunted", "gloomy"]
        )
        scene2 = SceneMetadata(
            id="forest_002",
            type="forest",
            core_concept="Elf ruins",
            tags=["magical", "mysterious"]
        )

        registry.register(scene1)
        registry.register(scene2)

        tags = registry.get_all_tags("forest")
        assert "haunted" in tags
        assert "gloomy" in tags
        assert "magical" in tags
        assert "mysterious" in tags

    def test_get_by_type_empty(self, registry):
        result = registry.get_by_type("village")
        assert result == []

    def test_get_by_id_not_found(self, registry):
        result = registry.get_by_id("nonexistent")
        assert result is None

    def test_save_and_load(self, registry):
        """测试场景保存和加载"""
        scene1 = SceneMetadata(
            id="tavern_001",
            type="tavern",
            core_concept="Cozy tavern",
            tags=["warm", "social"]
        )
        scene2 = SceneMetadata(
            id="forest_001",
            type="forest",
            core_concept="Dark forest",
            tags=["dangerous", "mysterious"]
        )
        registry.register(scene1)
        registry.register(scene2)

        asyncio.run(registry.save())

        # 新建 registry 并加载（使用同一个 storage_path）
        new_registry = SceneRegistry(storage_path=registry.storage_path)
        asyncio.run(new_registry.load())

        assert new_registry.get_by_id("tavern_001") is not None
        assert new_registry.get_by_id("tavern_001").core_concept == "Cozy tavern"
        assert len(new_registry.get_by_type("forest")) == 1


class TestSceneMetadata:
    """SceneMetadata 测试"""

    def test_to_dict(self):
        scene = SceneMetadata(
            id="test_001",
            type="village",
            core_concept="Abandoned mining town",
            tags=["deserted", "dangerous"],
            danger_level="high"
        )

        data = scene.to_dict()
        assert data["id"] == "test_001"
        assert data["type"] == "village"
        assert data["danger_level"] == "high"

    def test_from_dict(self):
        data = {
            "id": "test_002",
            "type": "dungeon",
            "core_concept": "Ancient crypt",
            "tags": ["undead", "trapped"],
            "unique_features": [],
            "danger_level": "high",
            "atmosphere": "eerie",
            "synopsis": "...",
            "description": "...",
            "npcs": [],
            "events": [],
            "created_at": 0.0
        }

        scene = SceneMetadata.from_dict(data)
        assert scene.id == "test_002"
        assert scene.type == "dungeon"

    def test_to_dict_roundtrip(self):
        """测试序列化往返"""
        scene = SceneMetadata(
            id="roundtrip_001",
            type="castle",
            core_concept="Haunted castle",
            tags=["spooky", "medieval"],
            danger_level="deadly",
            atmosphere="eerie",
        )
        data = scene.to_dict()
        restored = SceneMetadata.from_dict(data)
        assert restored.id == scene.id
        assert restored.type == scene.type
        assert restored.danger_level == scene.danger_level


class TestSceneAgent:
    """SceneAgent 测试"""

    @pytest.fixture
    def agent(self):
        """创建 Agent（使用临时存储避免Windows权限问题）"""
        temp_dir = Path(tempfile.mkdtemp(prefix="scene_agent_test_"))
        registry = SceneRegistry(storage_path=str(temp_dir / "scenes"))
        agent = SceneAgent(registry=registry)
        # Store temp_dir for cleanup
        agent._temp_dir = temp_dir
        yield agent
        # Cleanup
        shutil.rmtree(temp_dir, ignore_errors=True)

    def test_agent_initialization(self, agent):
        assert agent.registry is not None
        assert agent.llm is not None

    def test_get_existing_scene_empty(self, agent):
        result = agent.get_existing_scene("forest")
        assert result is None

    @pytest.mark.asyncio
    async def test_get_existing_scene_with_registered(self, agent):
        """已注册场景应返回"""
        scene = SceneMetadata(
            id="forest_001",
            type="forest",
            core_concept="Dark forest",
            tags=["mysterious"]
        )
        agent.registry.register(scene)
        result = agent.get_existing_scene("forest")
        assert result is not None

    @pytest.mark.asyncio
    async def test_generate_scene_with_mock_llm(self, agent):
        """测试场景生成（mock LLM）"""
        # Mock generate_differentiation to return just the core concept (not JSON)
        async def mock_differentiation(scene_type, existing_tags, requirements):
            return "古老森林"

        # Mock generate_synopsis to return a dict
        async def mock_synopsis(core_concept, scene_type):
            return {
                "atmosphere": "神秘幽静",
                "danger_level": "medium",
                "synopsis": "一片充满神秘气息的古老森林。",
                "tags": ["神秘", "古老", "幽静"],
                "unique_features": ["发光的苔藓", "巨大的古树"],
            }

        # Mock generate_detail to return a dict
        async def mock_detail(synopsis, scene_type, atmosphere):
            return {
                "description": "你走进了一片古老的森林...",
                "npcs": [],
                "events": [],
            }

        # Mock the event bus publish to avoid AttributeError when _event_bus is None
        mock_bus = AsyncMock()
        mock_bus.publish = AsyncMock()
        agent._event_bus = mock_bus

        with patch.object(agent.llm, 'generate_differentiation', new=AsyncMock(side_effect=mock_differentiation)), \
             patch.object(agent.llm, 'generate_synopsis', new=AsyncMock(side_effect=mock_synopsis)), \
             patch.object(agent.llm, 'generate_detail', new=AsyncMock(side_effect=mock_detail)):
            scene = await agent.generate_scene("forest", "神秘冒险")
            assert scene is not None
            assert scene.core_concept == "古老森林"
            assert "神秘" in scene.tags

    @pytest.mark.asyncio
    async def test_generate_fallback_npcs_tavern(self, agent):
        """酒馆 fallback NPC 生成"""
        npcs = agent._generate_fallback_npcs("酒馆")
        assert isinstance(npcs, list)
        assert len(npcs) >= 1
        assert npcs[0]["name"]  # 应该有名字

    @pytest.mark.asyncio
    async def test_generate_fallback_npcs_forest(self, agent):
        """森林 fallback NPC 生成"""
        npcs = agent._generate_fallback_npcs("森林")
        assert isinstance(npcs, list)
        assert len(npcs) >= 1

    @pytest.mark.asyncio
    async def test_generate_fallback_npcs_unknown(self, agent):
        """未知类型 fallback NPC"""
        npcs = agent._generate_fallback_npcs("未知区域")
        assert isinstance(npcs, list)

    def test_scene_agent_has_required_methods(self, agent):
        """SceneAgent 应该有必需的方法"""
        assert hasattr(agent, 'generate_scene')
        assert hasattr(agent, 'get_existing_scene')
        assert hasattr(agent, '_generate_fallback_npcs')


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
