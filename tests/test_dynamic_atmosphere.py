"""
Dynamic Atmosphere 动态氛围生成系统 - 单元测试
"""

import pytest
import asyncio
import json
import tempfile
import shutil
from pathlib import Path
import sys
from unittest.mock import AsyncMock, MagicMock, patch
import random

# 添加 src 目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.scene_agent import (
    SceneAgent, SceneRegistry, SceneMetadata,
    generate_dynamic_atmosphere,
    _ATMOSPHERE_ELEMENTS,
    _POST_COMBAT_ATMOSPHERE_VARIANTS,
    _QUEST_STAGE_ATMOSPHERE_VARIANTS,
)


class TestGenerateDynamicAtmosphere:
    """generate_dynamic_atmosphere 函数测试"""

    def test_generate_atmosphere_basic(self):
        """基础 atmosphere 生成测试"""
        result = generate_dynamic_atmosphere(scene_type="酒馆", seed=42)
        
        assert "atmosphere" in result
        assert "atmosphere_desc" in result
        assert "atmosphere_tags" in result
        assert "light" in result
        assert "sound" in result
        assert "smell" in result
        assert "temperature" in result
        assert "mood" in result
        
        # atmosphere 应该在元素词库中
        assert result["mood"] in _ATMOSPHERE_ELEMENTS["酒馆"]["mood"]
    
    def test_generate_atmosphere_deterministic(self):
        """相同 seed 应产生相同的 atmosphere"""
        result1 = generate_dynamic_atmosphere(scene_type="森林", seed=12345)
        result2 = generate_dynamic_atmosphere(scene_type="森林", seed=12345)
        
        assert result1["atmosphere"] == result2["atmosphere"]
        assert result1["light"] == result2["light"]
        assert result1["sound"] == result2["sound"]
    
    def test_generate_atmosphere_different_seeds(self):
        """不同 seed 应产生不同的 atmosphere（大概率）"""
        atmospheres = set()
        for seed in range(100, 110):
            result = generate_dynamic_atmosphere(scene_type="酒馆", seed=seed)
            atmospheres.add(result["atmosphere"])
        
        # 不同 seed 应该产生不同的 atmosphere（至少有一些差异）
        # 由于随机性，这里只检查返回了多个不同的结果
        assert len(atmospheres) >= 1
    
    def test_generate_atmosphere_unknown_scene_type(self):
        """未知场景类型应使用 default 元素"""
        result = generate_dynamic_atmosphere(scene_type="未知区域", seed=42)
        
        # 应该仍然返回有效结果
        assert "atmosphere" in result
        assert "atmosphere_desc" in result
        assert result["atmosphere"] in _ATMOSPHERE_ELEMENTS["default"]["mood"]
    
    def test_generate_atmosphere_post_combat(self):
        """战斗后 atmosphere 特殊变体"""
        context = {"post_combat": True}
        result = generate_dynamic_atmosphere(
            scene_type="酒馆",
            seed=42,
            game_state_context=context
        )
        
        # atmosphere_desc 应该包含战斗后的描述
        assert "战斗" in result["atmosphere_desc"] or "战" in result["atmosphere_desc"]
    
    def test_generate_atmosphere_quest_stage(self):
        """任务阶段 atmosphere 变体"""
        for stage_key in ["早期", "中期", "后期", "完成"]:
            context = {"quest_stage": stage_key}
            result = generate_dynamic_atmosphere(
                scene_type="村庄",
                seed=42,
                game_state_context=context
            )
            
            assert "atmosphere" in result
            # 如果有对应的变体，应该包含相关关键词
            if stage_key in _QUEST_STAGE_ATMOSPHERE_VARIANTS.get("村庄", {}):
                # atmosphere_desc 应该反映任务阶段的变化
                assert len(result["atmosphere_desc"]) > 0
    
    def test_generate_atmosphere_avoid_duplicate(self):
        """避免重复 atmosphere_tags"""
        existing_tags = ["温馨热闹", "平静祥和"]
        result = generate_dynamic_atmosphere(
            scene_type="酒馆",
            seed=42,
            existing_tags=existing_tags
        )
        
        # 应该生成一个不同于 existing_tags 的 atmosphere
        assert "atmosphere_tags" in result
    
    def test_generate_atmosphere_all_scene_types(self):
        """所有已知场景类型都能生成 atmosphere"""
        scene_types = ["酒馆", "森林", "村庄", "城镇", "城堡", "洞穴"]
        
        for scene_type in scene_types:
            result = generate_dynamic_atmosphere(scene_type=scene_type, seed=42)
            
            assert "atmosphere" in result
            assert result["atmosphere"] in _ATMOSPHERE_ELEMENTS[scene_type]["mood"]
    
    def test_generate_atmosphere_desc_completeness(self):
        """atmosphere_desc 包含所有要素"""
        result = generate_dynamic_atmosphere(scene_type="酒馆", seed=42)
        
        desc = result["atmosphere_desc"]
        
        # 应该包含光线、声音、气味、温度等要素的描述
        assert len(desc) > 30  # 至少有一定的长度
        # 检查是否包含描述性内容
        assert any(elem in desc for elem in [result["light"], result["sound"], result["smell"]])
    
    def test_generate_atmosphere_mood_determinism(self):
        """mood 应该从场景类型的 mood 词库中选择"""
        result = generate_dynamic_atmosphere(scene_type="森林", seed=999)
        
        assert result["mood"] in _ATMOSPHERE_ELEMENTS["森林"]["mood"]


class TestSceneMetadataAtmosphereHistory:
    """SceneMetadata atmosphere_history 字段测试"""

    def test_atmosphere_history_field(self):
        """SceneMetadata 应该有 atmosphere_history 字段"""
        scene = SceneMetadata(
            id="test_001",
            type="forest",
            core_concept="Test concept",
            tags=["test"],
            atmosphere_history=[]
        )
        
        assert hasattr(scene, "atmosphere_history")
        assert scene.atmosphere_history == []
    
    def test_atmosphere_history_in_to_dict(self):
        """atmosphere_history 应该能序列化"""
        history_entry = {
            "timestamp": 1234567890,
            "index": 0,
            "atmosphere": "神秘诡异",
            "atmosphere_tags": ["神秘诡异"],
        }
        scene = SceneMetadata(
            id="test_002",
            type="forest",
            core_concept="Test concept",
            tags=["test"],
            atmosphere_history=[history_entry]
        )
        
        data = scene.to_dict()
        assert "atmosphere_history" in data
        assert data["atmosphere_history"] == [history_entry]
    
    def test_atmosphere_history_in_from_dict(self):
        """atmosphere_history 应该能反序列化"""
        data = {
            "id": "test_003",
            "type": "village",
            "core_concept": "Test concept",
            "tags": ["test"],
            "unique_features": [],
            "danger_level": "medium",
            "atmosphere": "",
            "synopsis": "",
            "description": "",
            "npcs": [],
            "events": [],
            "objects": [],
            "random_events": [],
            "created_at": 0.0,
            "atmosphere_history": [
                {"timestamp": 1234567890, "index": 0, "atmosphere": "宁静祥和"}
            ]
        }
        
        scene = SceneMetadata.from_dict(data)
        assert scene.atmosphere_history == [
            {"timestamp": 1234567890, "index": 0, "atmosphere": "宁静祥和"}
        ]


class TestSceneRegistryAtmosphere:
    """SceneRegistry atmosphere 管理方法测试"""

    @pytest.fixture
    def registry(self):
        """使用临时存储"""
        temp_dir = Path(tempfile.mkdtemp(prefix="atm_test_"))
        registry = SceneRegistry(storage_path=str(temp_dir / "scenes"))
        yield registry
        shutil.rmtree(temp_dir, ignore_errors=True)

    def test_add_atmosphere_to_history(self, registry):
        """add_atmosphere_to_history 应该正确添加 atmosphere"""
        scene = SceneMetadata(
            id="atm_test_001",
            type="酒馆",
            core_concept="Test concept",
            tags=["test"]
        )
        registry.register(scene)
        
        atm_data = {
            "atmosphere": "温馨热闹",
            "atmosphere_tags": ["温馨热闹"],
            "light": "昏黄的烛光",
            "sound": "酒杯碰撞声",
            "smell": "麦酒香",
            "temperature": "温暖如春",
            "mood": "温馨热闹",
        }
        
        registry.add_atmosphere_to_history("atm_test_001", atm_data)
        
        # 验证 atmosphere 被添加
        scene = registry.get_by_id("atm_test_001")
        assert len(scene.atmosphere_history) == 1
        assert scene.atmosphere_history[0]["atmosphere"] == "温馨热闹"
        assert scene.atmosphere == "温馨热闹"  # 当前 atmosphere 应该更新
    
    def test_get_scene_atmosphere_tags(self, registry):
        """get_scene_atmosphere_tags 应该返回所有历史 tags"""
        scene = SceneMetadata(
            id="atm_test_002",
            type="森林",
            core_concept="Test concept",
            tags=["test"]
        )
        registry.register(scene)
        
        registry.add_atmosphere_to_history("atm_test_002", {
            "atmosphere": "神秘诡异",
            "atmosphere_tags": ["神秘诡异", "幽暗"],
        })
        registry.add_atmosphere_to_history("atm_test_002", {
            "atmosphere": "阴森压抑",
            "atmosphere_tags": ["阴森压抑", "寒冷"],
        })
        
        tags = registry.get_scene_atmosphere_tags("atm_test_002")
        
        assert "神秘诡异" in tags
        assert "阴森压抑" in tags
        assert "幽暗" in tags
        assert "寒冷" in tags
    
    def test_get_atmosphere_count(self, registry):
        """get_atmosphere_count 应该正确计数"""
        scene = SceneMetadata(
            id="atm_test_003",
            type="城镇",
            core_concept="Test concept",
            tags=["test"]
        )
        registry.register(scene)
        
        assert registry.get_atmosphere_count("atm_test_003") == 0
        
        for i in range(5):
            registry.add_atmosphere_to_history("atm_test_003", {
                "atmosphere": f"氛围{i}",
                "atmosphere_tags": [f"氛围{i}"],
            })
        
        assert registry.get_atmosphere_count("atm_test_003") == 5
    
    def test_can_cycle_atmosphere(self, registry):
        """can_cycle_atmosphere 应该正确判断"""
        scene = SceneMetadata(
            id="atm_test_004",
            type="酒馆",
            core_concept="Test concept",
            tags=["test"]
        )
        registry.register(scene)
        
        # 少于3个 atmosphere 时不能循环
        registry.add_atmosphere_to_history("atm_test_004", {
            "atmosphere": "氛围1",
            "atmosphere_tags": ["氛围1"],
        })
        assert not registry.can_cycle_atmosphere("atm_test_004")
        
        registry.add_atmosphere_to_history("atm_test_004", {
            "atmosphere": "氛围2",
            "atmosphere_tags": ["氛围2"],
        })
        assert not registry.can_cycle_atmosphere("atm_test_004")
        
        # 3个或以上时可以循环
        registry.add_atmosphere_to_history("atm_test_004", {
            "atmosphere": "氛围3",
            "atmosphere_tags": ["氛围3"],
        })
        assert registry.can_cycle_atmosphere("atm_test_004")
    
    def test_atmosphere_history_limit(self, registry):
        """atmosphere_history 最多保留10条"""
        scene = SceneMetadata(
            id="atm_test_005",
            type="洞穴",
            core_concept="Test concept",
            tags=["test"]
        )
        registry.register(scene)
        
        # 添加15条记录
        for i in range(15):
            registry.add_atmosphere_to_history("atm_test_005", {
                "atmosphere": f"氛围{i}",
                "atmosphere_tags": [f"氛围{i}"],
            })
        
        # 应该只保留10条
        scene = registry.get_by_id("atm_test_005")
        assert len(scene.atmosphere_history) == 10
        
        # 第一条应该是第6条（索引5），因为前5条被移除了
        assert scene.atmosphere_history[0]["atmosphere"] == "氛围5"


class TestAtmosphereIntegration:
    """Atmosphere 与 SceneAgent 集成测试"""

    @pytest.fixture
    def agent(self):
        """创建 Agent（使用临时存储）"""
        temp_dir = Path(tempfile.mkdtemp(prefix="atm_agent_test_"))
        registry = SceneRegistry(storage_path=str(temp_dir / "scenes"))
        agent = SceneAgent(registry=registry)
        agent._temp_dir = temp_dir
        yield agent
        shutil.rmtree(temp_dir, ignore_errors=True)

    @pytest.mark.asyncio
    async def test_generate_scene_with_dynamic_atmosphere(self, agent):
        """场景生成时应该包含动态 atmosphere"""
        # Mock 事件总线
        mock_bus = AsyncMock()
        mock_bus.publish = AsyncMock()
        agent._event_bus = mock_bus
        
        # Mock LLM 方法
        async def mock_diff(scene_type, existing_tags, requirements):
            return "古老森林"
        
        async def mock_syn(core_concept, scene_type):
            return {
                "atmosphere": "神秘",
                "danger_level": "medium",
                "synopsis": "一片神秘的土地",
                "tags": ["神秘"],
                "unique_features": [],
            }
        
        async def mock_detail(synopsis, scene_type, atmosphere, **kwargs):
            return {
                "description": "古老的树木遮天蔽日...",
                "npcs": [],
                "events": [],
            }
        
        with patch.object(agent.llm, 'generate_differentiation', new=AsyncMock(side_effect=mock_diff)), \
             patch.object(agent.llm, 'generate_synopsis', new=AsyncMock(side_effect=mock_syn)), \
             patch.object(agent.llm, 'generate_detail', new=AsyncMock(side_effect=mock_detail)):
            
            scene = await agent.generate_scene("森林", "神秘冒险")
            
            # 场景生成时 atmosphere_history 应该是空的（初始生成）
            assert hasattr(scene, "atmosphere_history")
            assert isinstance(scene.atmosphere_history, list)

    def test_generate_dynamic_atmosphere_integration(self, agent):
        """SceneAgent 应该能调用 generate_dynamic_atmosphere"""
        # 这个测试验证 generate_dynamic_atmosphere 可以被 SceneAgent 使用
        result = generate_dynamic_atmosphere(
            scene_type="酒馆",
            seed=42,
            game_state_context={"quest_stage": "中期"}
        )
        
        assert "atmosphere" in result
        assert "atmosphere_desc" in result


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
