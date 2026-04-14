"""
Scene Differentiation Test - 验证场景差异化生成效果

测试同一场景类型多次调用能生成不同内容。
"""

import pytest
import asyncio
import sys
import tempfile
import shutil
from pathlib import Path
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.scene_agent import SceneAgent, SceneRegistry, SceneMetadata


class TestSceneDifferentiation:
    """场景差异化测试"""

    @pytest.fixture
    def registry(self):
        """使用临时存储（避免Windows tmp_path权限问题）"""
        temp_dir = Path(tempfile.mkdtemp(prefix="scene_test_"))
        registry = SceneRegistry(storage_path=str(temp_dir / "scenes"))
        yield registry
        # Cleanup
        shutil.rmtree(temp_dir, ignore_errors=True)

    @pytest.fixture
    def agent(self, registry):
        """创建 Agent"""
        return SceneAgent(registry=registry)

    @pytest.mark.asyncio
    async def test_same_forest_multiple_generations(self, agent):
        """
        测试同一森林类型多次生成是否有差异化
        
        验收标准：同一场景类型（森林）多次调用应生成不同内容
        """
        # Mock LLM to return controlled but different outputs
        call_count = 0
        
        async def mock_differentiation(scene_type, existing_tags, requirements):
            nonlocal call_count
            call_count += 1
            variants = [
                "古老密林\n藤蔓从高处垂落如帘，昏暗的光线在腐叶气息中穿透进来，远处有不知名鸟类的低沉鸣叫，脚下的泥土湿润而松软。\n幽暗, 潮湿, 藤蔓, 腐叶气息, 鸟鸣",
                "阳光斑驳的林间空地\n阳光透过树冠的缝隙洒下斑驳的光点，空气中弥漫着野花和青草混合的清香，蝴蝶在光柱中起舞，地面是柔软的苔藓覆盖的泥土。\n明亮, 花香, 蝴蝶, 苔藓, 温暖",
                "迷雾笼罩的森林深处\n浓雾将一切轮廓都模糊成阴影，潮湿的冷意渗入骨髓，树木的形态扭曲成奇异的形状，没有任何动物的声音，只有雾滴从叶片滑落的声音。\n迷雾, 死寂, 扭曲, 冰冷, 诡异"
            ]
            return variants[(call_count - 1) % len(variants)]
        
        async def mock_synopsis(core_concept, scene_type):
            return {
                "atmosphere": "神秘",
                "danger_level": "mid",
                "synopsis": f"一个{scene_type}场景，包含丰富的感官细节。",
                "tags": ["测试"],
                "unique_features": ["测试特色"]
            }
        
        async def mock_detail(synopsis, scene_type, atmosphere, core_concept="", existing_tags=None):
            return {
                "description": f"详细描述 - 变体{call_count}：这是一片独特的{scene_type}...",
                "npcs": [],
                "events": [],
                "objects": []
            }
        
        mock_bus = AsyncMock()
        mock_bus.publish = AsyncMock()
        agent._event_bus = mock_bus
        
        with patch.object(agent.llm, 'generate_differentiation', new=AsyncMock(side_effect=mock_differentiation)), \
             patch.object(agent.llm, 'generate_synopsis', new=AsyncMock(side_effect=mock_synopsis)), \
             patch.object(agent.llm, 'generate_detail', new=AsyncMock(side_effect=mock_detail)):
            
            # 生成3次森林场景
            scene1 = await agent.generate_scene("森林", "测试需求1")
            scene2 = await agent.generate_scene("森林", "测试需求2")
            scene3 = await agent.generate_scene("森林", "测试需求3")
            
            # 验证：每次 core_concept 不同
            assert scene1.core_concept != scene2.core_concept, "第1次和第2次 core_concept 应该不同"
            assert scene2.core_concept != scene3.core_concept, "第2次和第3次 core_concept 应该不同"
            assert scene1.core_concept != scene3.core_concept, "第1次和第3次 core_concept 应该不同"
            
            # 验证：每次 description 不同
            assert scene1.description != scene2.description, "第1次和第2次 description 应该不同"
            assert scene2.description != scene3.description, "第2次和第3次 description 应该不同"

    @pytest.mark.asyncio
    async def test_different_scene_types_have_unique_features(self, agent):
        """
        测试不同场景类型有不同的 unique_features
        """
        async def mock_differentiation(scene_type, existing_tags, requirements):
            differentiation_map = {
                "酒馆": "喧嚣大厅\n铜制酒杯在火把下闪烁，空气中麦酒和烤肉的香气混杂，骰子和硬币的碰撞声此起彼伏，厚底靴踩在泥土地面上发出沉闷的声音。\n喧嚣, 琥珀色火光, 麦酒烤肉香, 骰子声",
                "森林": "幽暗密林\n藤蔓从高处垂落如帘，昏暗的光线在腐叶气息中穿透进来，远处有不知名鸟类的低沉鸣叫，脚下的泥土湿润而松软。\n幽暗, 潮湿, 藤蔓, 腐叶气息",
                "洞穴": "磷光溶洞\n水滴从钟乳石滴落，磷光在洞壁上投下蓝绿色的诡异光影，空气中弥漫着潮湿的矿物气息，寒意从石壁渗出。\n磷光, 寒冷, 矿物, 水滴声, 诡异"
            }
            return differentiation_map.get(scene_type, f"独特的{scene_type}")
        
        async def mock_synopsis(core_concept, scene_type):
            return {
                "atmosphere": f"{scene_type}氛围",
                "danger_level": "mid",
                "synopsis": f"一个{scene_type}场景",
                "tags": [scene_type],
                "unique_features": [f"{scene_type}特色1", f"{scene_type}特色2"]
            }
        
        async def mock_detail(synopsis, scene_type, atmosphere, core_concept=""):
            return {
                "description": f"这是{scene_type}的详细描述...",
                "npcs": [],
                "events": [],
                "objects": []
            }
        
        mock_bus = AsyncMock()
        mock_bus.publish = AsyncMock()
        agent._event_bus = mock_bus
        
        with patch.object(agent.llm, 'generate_differentiation', new=AsyncMock(side_effect=mock_differentiation)), \
             patch.object(agent.llm, 'generate_synopsis', new=AsyncMock(side_effect=mock_synopsis)), \
             patch.object(agent.llm, 'generate_detail', new=AsyncMock(side_effect=mock_detail)):
            
            tavern = await agent.generate_scene("酒馆", "测试")
            forest = await agent.generate_scene("森林", "测试")
            cave = await agent.generate_scene("洞穴", "测试")
            
            # 验证不同场景类型有不同的标签
            assert "酒馆" in tavern.tags
            assert "森林" in forest.tags
            assert "洞穴" in cave.tags
            
            # 验证 unique_features 不同
            assert tavern.unique_features != forest.unique_features
            assert forest.unique_features != cave.unique_features

    @pytest.mark.asyncio
    async def test_random_events_are_injected(self, agent):
        """
        测试随机事件注入
        """
        async def mock_differentiation(scene_type, existing_tags, requirements):
            return f"{scene_type}核心概念"
        
        async def mock_synopsis(core_concept, scene_type):
            return {
                "atmosphere": "测试",
                "danger_level": "low",
                "synopsis": "测试场景",
                "tags": ["测试"],
                "unique_features": []
            }
        
        async def mock_detail(synopsis, scene_type, atmosphere, core_concept=""):
            return {
                "description": "测试描述",
                "npcs": [],
                "events": [],
                "objects": []
            }
        
        mock_bus = AsyncMock()
        mock_bus.publish = AsyncMock()
        agent._event_bus = mock_bus
        
        with patch.object(agent.llm, 'generate_differentiation', new=AsyncMock(side_effect=mock_differentiation)), \
             patch.object(agent.llm, 'generate_synopsis', new=AsyncMock(side_effect=mock_synopsis)), \
             patch.object(agent.llm, 'generate_detail', new=AsyncMock(side_effect=mock_detail)):
            
            scene = await agent.generate_scene("酒馆", "测试")
            
            # 验证随机事件被注入
            assert hasattr(scene, 'random_events')
            # random_events 应该是 1-2 个事件
            assert len(scene.random_events) >= 1
            
            # 验证事件格式正确
            for evt in scene.random_events:
                assert "type" in evt
                assert "trigger" in evt
                assert "event" in evt

    @pytest.mark.asyncio
    async def test_opening_template_not_applied_to_llm_description(self, agent):
        """
        测试：验证 LLM 生成的 description 不应该应用开场模板
        
        原因：LLM 已经生成了沉浸式的开场叙述，再加开场模板会重复
        开场模板只应该用于 fallback 场景
        """
        async def mock_differentiation(scene_type, existing_tags, requirements):
            return f"独特{scene_type}\nLLM生成的核心描述，包含丰富的感官细节。\n独特, 感官丰富"
        
        async def mock_synopsis(core_concept, scene_type):
            return {
                "atmosphere": "沉浸",
                "danger_level": "mid",
                "synopsis": "沉浸式场景描述",
                "tags": ["沉浸"],
                "unique_features": ["特色1"]
            }
        
        async def mock_detail(synopsis, scene_type, atmosphere, core_concept=""):
            return {
                "description": "这是LLM生成的沉浸式描述，直接以场景画面开头，没有任何「推开大门」类型的模板式开场。",
                "npcs": [],
                "events": [],
                "objects": []
            }
        
        mock_bus = AsyncMock()
        mock_bus.publish = AsyncMock()
        agent._event_bus = mock_bus
        
        with patch.object(agent.llm, 'generate_differentiation', new=AsyncMock(side_effect=mock_differentiation)), \
             patch.object(agent.llm, 'generate_synopsis', new=AsyncMock(side_effect=mock_synopsis)), \
             patch.object(agent.llm, 'generate_detail', new=AsyncMock(side_effect=mock_detail)):
            
            scene = await agent.generate_scene("酒馆", "测试")
            
            # LLM 描述不应包含开场模板的特征词
            # 开场模板包含: "推开", "踏入", "推门而入" 等
            forbidden_openers = ["推开厚重的橡木门", "你踏入酒馆", "木门吱呀一声", "穿过嘈杂的街道"]
            for opener in forbidden_openers:
                assert opener not in scene.description, f"LLM描述不应包含开场模板: {opener}"

    @pytest.mark.asyncio
    async def test_fallback_description_uses_opening_template(self, agent):
        """
        测试：验证 fallback 描述使用开场模板
        
        当 LLM 不可用时，fallback 应该使用开场模板来增加变化
        """
        # Mock LLM to raise exception (force fallback)
        async def mock_llm_raises(*args, **kwargs):
            raise Exception("LLM不可用")
        
        mock_bus = AsyncMock()
        mock_bus.publish = AsyncMock()
        agent._event_bus = mock_bus
        
        with patch.object(agent.llm, 'generate_differentiation', new=AsyncMock(side_effect=mock_llm_raises)), \
             patch.object(agent.llm, 'generate_synopsis', new=AsyncMock(side_effect=mock_llm_raises)), \
             patch.object(agent.llm, 'generate_detail', new=AsyncMock(side_effect=mock_llm_raises)):
            
            # 生成多次，使用 fallback
            scenes = []
            for _ in range(5):
                scene = await agent.generate_scene("酒馆", "测试")
                scenes.append(scene.description)
            
            # Fallback 描述应该使用开场模板，所以每次应该略有不同
            # 至少有一次应该包含开场模板的特征
            has_template = False
            template_indicators = ["推开", "踏入", "一阵", "穿过", "你推门而入"]
            for desc in scenes:
                for indicator in template_indicators:
                    if indicator in desc:
                        has_template = True
                        break
                if has_template:
                    break
            
            assert has_template, "Fallback 描述应该使用开场模板"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
