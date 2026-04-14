"""
Fallback 策略单元测试

测试：
1. 错误分类 (classify_exception)
2. Fallback 档次选择 (FallbackTier)
3. Fallback 场景生成 (get_fallback_scene)
4. 降级模式跟踪 (DegradationTracker)
5. Fallback 场景不持久化
"""

import pytest
import asyncio
import json
import tempfile
import shutil
from pathlib import Path
import sys
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.scene_agent import (
    SceneAgent,
    SceneRegistry,
    SceneMetadata,
    FailureType,
    FallbackTier,
    DegradationTracker,
    classify_exception,
    should_fallback,
    should_retry,
    get_fallback_scene,
)


class TestFailureClassification:
    """测试异常分类"""

    def test_network_error_timeout(self):
        """超时错误应该被识别为网络错误"""
        e = asyncio.TimeoutError("Request timed out")
        failure_type, msg = classify_exception(e)
        assert failure_type == FailureType.NETWORK_ERROR

    def test_network_error_connection(self):
        """连接错误应该被识别为网络错误"""
        e = ConnectionError("Connection refused")
        failure_type, msg = classify_exception(e)
        assert failure_type == FailureType.NETWORK_ERROR

    def test_credentials_error(self):
        """API Key 错误应该被识别为凭证错误"""
        e = Exception("Invalid API key")
        failure_type, msg = classify_exception(e)
        assert failure_type == FailureType.CREDENTIALS_ERROR

    def test_content_filter_error(self):
        """内容安全错误应该被识别为内容过滤"""
        e = Exception("Content filter triggered")
        failure_type, msg = classify_exception(e)
        assert failure_type == FailureType.CONTENT_FILTER

    def test_format_error(self):
        """JSON 解析错误应该被识别为格式错误"""
        e = json.JSONDecodeError("Expecting value", "", 0)
        failure_type, msg = classify_exception(e)
        assert failure_type == FailureType.FORMAT_ERROR

    def test_unknown_error(self):
        """未知异常应该被识别为未知错误"""
        e = RuntimeError("Some unexpected error")
        failure_type, msg = classify_exception(e)
        assert failure_type == FailureType.UNKNOWN_ERROR


class TestFallbackDecision:
    """测试 Fallback 决策"""

    def test_network_can_fallback(self):
        """网络错误应该可以使用 fallback"""
        assert should_fallback(FailureType.NETWORK_ERROR) is True

    def test_unknown_can_fallback(self):
        """未知错误应该可以使用 fallback"""
        assert should_fallback(FailureType.UNKNOWN_ERROR) is True

    def test_format_no_fallback(self):
        """格式错误不应该 fallback"""
        assert should_fallback(FailureType.FORMAT_ERROR) is False

    def test_credentials_no_fallback(self):
        """凭证错误不应该 fallback"""
        assert should_fallback(FailureType.CREDENTIALS_ERROR) is False

    def test_content_can_retry(self):
        """内容安全错误应该可以重试"""
        assert should_retry(FailureType.CONTENT_FILTER) is True

    def test_network_no_retry(self):
        """网络错误不应该重试（应该 fallback）"""
        assert should_retry(FailureType.NETWORK_ERROR) is False


class TestFallbackTier:
    """测试 Fallback 档次"""

    def test_fallback_tier_light(self):
        """轻度降级档次"""
        scene = get_fallback_scene("酒馆", FallbackTier.LIGHT)
        assert "description" in scene
        assert len(scene["description"]) > 10
        # 轻度降级不应有 NPC
        assert scene["npcs"] == []

    def test_fallback_tier_medium(self):
        """中度降级档次"""
        scene = get_fallback_scene("森林", FallbackTier.MEDIUM)
        assert "description" in scene
        assert len(scene["description"]) > 10
        # 中度降级应有基本 NPC
        assert len(scene["npcs"]) >= 1

    def test_fallback_tier_heavy(self):
        """重度降级档次"""
        scene = get_fallback_scene("村庄", FallbackTier.HEAVY)
        assert "description" in scene
        assert len(scene["description"]) > 50  # 重度降级描述更长
        # 重度降级应有完整 NPC + 物品
        assert len(scene["npcs"]) >= 2
        assert "objects" in scene

    def test_fallback_scene_with_quest_hint(self):
        """带任务线索的 Fallback"""
        scene = get_fallback_scene("酒馆", FallbackTier.MEDIUM, quest_hint="有人说森林里有宝藏")
        assert "description" in scene
        # 描述中应包含任务线索
        assert "森林" in scene["description"] or "有人说" in scene["description"]

    def test_fallback_unknown_scene_type(self):
        """未定义的场景类型应使用默认 Fallback"""
        scene = get_fallback_scene("魔法学校", FallbackTier.HEAVY)
        assert "description" in scene
        assert len(scene["description"]) > 10


class TestDegradationTracker:
    """测试降级模式跟踪器"""

    def test_tracker_initial_state(self):
        """初始状态"""
        tracker = DegradationTracker()
        assert tracker.consecutive_count == 0

    def test_record_fallback(self):
        """记录一次 fallback"""
        tracker = DegradationTracker()
        count, should_alert = tracker.record_fallback("酒馆")
        assert count == 1
        assert should_alert is False

    def test_record_three_fallbacks_triggers_alert(self):
        """连续 3 次 fallback 触发告警"""
        tracker = DegradationTracker(alert_threshold=3)
        scene_type = "酒馆"
        
        # 前两次不应告警
        for i in range(2):
            count, should_alert = tracker.record_fallback(scene_type)
            assert count == i + 1
            assert should_alert is False
        
        # 第三次应触发告警
        count, should_alert = tracker.record_fallback(scene_type)
        assert count == 3
        assert should_alert is True

    def test_different_scene_resets_count(self):
        """不同场景类型重置计数"""
        tracker = DegradationTracker()
        
        tracker.record_fallback("酒馆")
        assert tracker.consecutive_count == 1
        
        tracker.record_fallback("森林")
        assert tracker.consecutive_count == 0  # 重置了

    def test_reset(self):
        """重置跟踪器"""
        tracker = DegradationTracker()
        tracker.record_fallback("酒馆")
        tracker.record_fallback("酒馆")
        
        tracker.reset()
        assert tracker.consecutive_count == 0

    def test_should_force_rebuild_after_threshold(self):
        """连续 3 次 fallback 后 should_force_rebuild() 返回 True"""
        tracker = DegradationTracker(alert_threshold=3)
        scene_type = "酒馆"
        
        # 前两次不应触发 force rebuild
        tracker.record_fallback(scene_type)
        assert tracker.should_force_rebuild() is False
        tracker.record_fallback(scene_type)
        assert tracker.should_force_rebuild() is False
        
        # 第三次触发
        tracker.record_fallback(scene_type)
        assert tracker.should_force_rebuild() is True

    def test_should_force_rebuild_false_before_threshold(self):
        """未达到阈值时 should_force_rebuild() 返回 False"""
        tracker = DegradationTracker(alert_threshold=3)
        
        tracker.record_fallback("酒馆")
        assert tracker.should_force_rebuild() is False
        
        tracker.record_fallback("酒馆")
        assert tracker.should_force_rebuild() is False

    def test_should_force_rebuild_cleared_after_reset(self):
        """reset() 后 should_force_rebuild() 返回 False"""
        tracker = DegradationTracker(alert_threshold=3)
        scene_type = "酒馆"
        
        # 触发 force rebuild
        tracker.record_fallback(scene_type)
        tracker.record_fallback(scene_type)
        tracker.record_fallback(scene_type)
        assert tracker.should_force_rebuild() is True
        
        # reset 后清除
        tracker.reset()
        assert tracker.should_force_rebuild() is False
        assert tracker.consecutive_count == 0

    def test_should_force_rebuild_after_different_scene(self):
        """不同场景类型切换时，force_rebuild_pending 应保留（连续计数才重置）"""
        tracker = DegradationTracker(alert_threshold=3)
        
        # 连续 3 次同一场景触发
        tracker.record_fallback("酒馆")
        tracker.record_fallback("酒馆")
        tracker.record_fallback("酒馆")
        assert tracker.should_force_rebuild() is True
        
        # 切换到不同场景，连续计数重置为 0，但 force_rebuild_pending 仍为 True
        # 因为 _force_rebuild_pending 是跨场景的标记
        tracker.record_fallback("森林")
        assert tracker.consecutive_count == 0  # 不同场景，重置计数
        # force_rebuild_pending 仍为 True（需要显式 reset 清除）
        assert tracker.should_force_rebuild() is True

    def test_force_rebuild_persistent_until_reset(self):
        """force_rebuild 标记持续有效，直到显式 reset"""
        tracker = DegradationTracker(alert_threshold=3)
        scene_type = "酒馆"
        
        # 触发
        tracker.record_fallback(scene_type)
        tracker.record_fallback(scene_type)
        tracker.record_fallback(scene_type)
        assert tracker.should_force_rebuild() is True
        
        # 继续调用 record_fallback（同一场景），force_rebuild_pending 保持 True
        tracker.record_fallback(scene_type)  # count=1 again after reset
        assert tracker.should_force_rebuild() is True
        
        # 只有 reset 才能清除
        tracker.reset()
        assert tracker.should_force_rebuild() is False


class TestSceneAgentFallback:
    """测试 SceneAgent Fallback 行为"""

    @pytest.fixture
    def agent(self):
        """创建 Agent（使用临时存储）"""
        temp_dir = Path(tempfile.mkdtemp(prefix="scene_agent_fallback_test_"))
        registry = SceneRegistry(storage_path=str(temp_dir / "scenes"))
        agent = SceneAgent(registry=registry)
        agent._temp_dir = temp_dir
        yield agent
        shutil.rmtree(temp_dir, ignore_errors=True)

    @pytest.mark.asyncio
    async def test_fallback_not_persisted_to_registry(self, agent):
        """Fallback 场景不应持久化到 registry"""
        # Mock LLM to raise network error
        async def mock_detail(*args, **kwargs):
            raise asyncio.TimeoutError("Network timeout")
        
        # Mock the event bus
        mock_bus = AsyncMock()
        mock_bus.publish = AsyncMock()
        agent._event_bus = mock_bus
        
        # Mock hooks
        mock_hooks = MagicMock()
        mock_hooks.trigger = AsyncMock()
        agent._hooks = mock_hooks
        
        # Mock LLM
        agent.llm = MagicMock()
        agent.llm.generate_differentiation = AsyncMock(return_value="Test concept")
        agent.llm.generate_synopsis = AsyncMock(return_value={
            "atmosphere": "神秘",
            "danger_level": "mid",
            "synopsis": "一个测试场景",
            "tags": ["测试"],
            "unique_features": []
        })
        agent.llm.generate_detail = mock_detail
        
        # 生成场景（会触发 fallback）
        scene = await agent.generate_scene("酒馆", "测试需求")
        
        # 验证使用了 fallback
        assert agent._last_scene_fallback is True
        assert agent._last_fallback_tier is not None
        
        # 验证场景没有注册到 registry
        registered_scene = agent.registry.get_by_type("酒馆")
        # Fallback 场景不应被注册，所以应该为空
        assert len(registered_scene) == 0

    @pytest.mark.asyncio
    async def test_normal_scene_persisted_to_registry(self, agent):
        """正常场景应该持久化到 registry"""
        # Mock the event bus
        mock_bus = AsyncMock()
        mock_bus.publish = AsyncMock()
        agent._event_bus = mock_bus
        
        # Mock hooks
        mock_hooks = MagicMock()
        mock_hooks.trigger = AsyncMock()
        agent._hooks = mock_hooks
        
        # Mock LLM to return valid data
        agent.llm = MagicMock()
        agent.llm.generate_differentiation = AsyncMock(return_value="Test concept")
        agent.llm.generate_synopsis = AsyncMock(return_value={
            "atmosphere": "神秘",
            "danger_level": "mid",
            "synopsis": "一个测试场景",
            "tags": ["测试"],
            "unique_features": []
        })
        agent.llm.generate_detail = AsyncMock(return_value={
            "description": "这是一个正常的测试场景",
            "npcs": [],
            "events": [],
            "objects": []
        })
        
        # 生成场景（正常流程）
        scene = await agent.generate_scene("酒馆", "测试需求")
        
        # 验证没有使用 fallback
        assert agent._last_scene_fallback is False
        
        # 验证场景已注册到 registry
        registered_scene = agent.registry.get_by_type("酒馆")
        assert len(registered_scene) == 1

    @pytest.mark.asyncio
    async def test_credentials_error_raises(self, agent):
        """凭证错误应该抛出异常，不使用 fallback"""
        async def mock_detail(*args, **kwargs):
            raise Exception("Invalid API key: wrong key")
        
        # Mock the event bus
        mock_bus = AsyncMock()
        mock_bus.publish = AsyncMock()
        agent._event_bus = mock_bus
        
        # Mock hooks
        mock_hooks = MagicMock()
        mock_hooks.trigger = AsyncMock()
        agent._hooks = mock_hooks
        
        # Mock LLM
        agent.llm = MagicMock()
        agent.llm.generate_differentiation = AsyncMock(return_value="Test concept")
        agent.llm.generate_synopsis = AsyncMock(return_value={
            "atmosphere": "神秘",
            "danger_level": "mid",
            "synopsis": "一个测试场景",
            "tags": ["测试"],
            "unique_features": []
        })
        agent.llm.generate_detail = mock_detail
        
        # 应该抛出异常
        with pytest.raises(Exception) as exc_info:
            await agent.generate_scene("酒馆", "测试需求")
        
        assert "Invalid API key" in str(exc_info.value)


class TestFallbackSceneQuality:
    """测试 Fallback 场景质量"""

    def test_fallback_descriptions_are_immersive(self):
        """Fallback 描述应该有沉浸感，不是简单的占位符"""
        for tier in FallbackTier:
            for scene_type in ["酒馆", "森林", "村庄", "城镇"]:
                scene = get_fallback_scene(scene_type, tier)
                desc = scene["description"]
                
                # 描述应该足够长
                assert len(desc) > 20, f"{scene_type} {tier} 描述太短"
                
                # 不应该只是"你身处某地"
                assert desc != f"你身处{scene_type}。", f"{scene_type} {tier} 是占位符"

    def test_fallback_different_tiers_different_quality(self):
        """不同档次的 Fallback 质量应该不同"""
        light = get_fallback_scene("酒馆", FallbackTier.LIGHT)
        heavy = get_fallback_scene("酒馆", FallbackTier.HEAVY)
        
        # 重度降级描述应该更长
        assert len(heavy["description"]) > len(light["description"])
        
        # 重度降级 NPC 应该更多
        assert len(heavy["npcs"]) > len(light["npcs"])


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
