"""
叙事 AI 防自爆测试

验证叙事生成过程中不暴露 AI 身份:
- 不使用"玩家正在..."、"玩家可以..."等第三人称描述
- 不使用"作为你的 DM..."、"作为游戏主持人..."等暴露AI身份的话
- 不使用"AI..."、"人工智能..."等技术身份字眼
- 使用第一人称沉浸式叙事风格

测试策略: Mock LLM, 捕获生成的 prompt, 验证约束存在
"""

import pytest
import asyncio
import re
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.npc_agent import NPCAgent, NPCRegistry, NPCMetadata, NPCRole, NPCDisposition
from src.game_master import GameMaster
from src.minimax_interface import MiniMaxInterface


# ============================================================================
# 禁止模式列表
# ============================================================================

# 第三人称描述（禁止）
THIRD_PERSON_PATTERNS = [
    r"玩家正在",
    r"玩家可以",
    r"玩家选择",
    r"玩家想",
    r"玩家打算",
    r"玩家试图",
    r"作为你的\s*DM",
    r"作为游戏主持人",
    r"作为AI",
    r"AI助手",
    r"人工智能",
    r"语言模型",
    r"DM认为",
    r"DM觉得",
    r"DM想",
]

# 匹配任何禁止模式的正则
COMPILED_FORBIDDEN_RE = re.compile(
    "|".join(f"({p})" for p in THIRD_PERSON_PATTERNS),
    re.IGNORECASE
)


def check_forbidden(text: str) -> list[str]:
    """检查文本中是否包含禁止模式,返回匹配的列表"""
    matches = COMPILED_FORBIDDEN_RE.findall(text)
    # flatten and filter None
    return [m for m in matches if m]


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def event_loop():
    """创建事件循环"""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def npc_agent():
    """创建 NPC Agent 实例（使用 mock registry 避免 tmp_path 权限问题）"""
    mock_registry = MagicMock(spec=NPCRegistry)
    agent = NPCAgent(
        registry=mock_registry,
        api_key="test-key"
    )
    return agent


@pytest.fixture
def sample_npc():
    """创建示例 NPC"""
    return NPCMetadata(
        id="test_npc_001",
        name="老王",
        role=NPCRole.MERCHANT.value,
        disposition=NPCDisposition.FRIENDLY.value,
        core_concept="精明的商人",
        personality="圆滑老练",
        speech_style="说话滴水不漏",
        secrets=["走私商人"],
        knowledge=["本地黑市"]
    )


# ============================================================================
# 测试: NPC Agent Prompt 约束
# ============================================================================

class TestNPCAgentPrompts:
    """测试 NPC Agent 的 LLM 调用包含防自爆约束"""

    @pytest.mark.asyncio
    async def test_generate_npc_response_has_constraint(self, npc_agent, sample_npc):
        """验证 NPC 对话生成的 system prompt 包含防自爆约束"""
        captured_prompts = []

        async def mock_generate(prompt, system="", temperature=0.7):
            captured_prompts.append({"prompt": prompt, "system": system})
            return "测试回复"

        sample_npc.dialogue = "你好啊，陌生人！"

        with patch.object(npc_agent.llm, 'generate', new=AsyncMock(side_effect=mock_generate)):
            await npc_agent.handle_dialogue(
                sample_npc, "你好", {"location": "酒馆"}
            )

        assert len(captured_prompts) > 0, "应该有 LLM 调用"

        # 检查所有 system prompt 都包含防自爆约束
        for call in captured_prompts:
            system = call["system"]
            # 必须包含"禁止"关键字（我们的约束以【硬约束 - 禁止】开头）
            assert "禁止" in system, f"System prompt 缺少防自爆约束:\n{system[:200]}"

    @pytest.mark.asyncio
    async def test_generate_npc_differentiation_has_constraint(self, npc_agent):
        """验证 NPC 差异化定位的 system prompt 包含防自爆约束"""
        captured_systems = []

        async def mock_generate(prompt, system="", temperature=0.7):
            captured_systems.append(system)
            return "测试概念"

        with patch.object(npc_agent.llm, 'generate', new=AsyncMock(side_effect=mock_generate)):
            await npc_agent._generate_npc_differentiation(
                "merchant", [], "贪婪的商人", "酒馆场景"
            )

        assert len(captured_systems) > 0
        for system in captured_systems:
            assert "禁止" in system, "差异化定位 prompt 缺少防自爆约束"

    @pytest.mark.asyncio
    async def test_generate_npc_profile_has_constraint(self, npc_agent):
        """验证 NPC 人设生成的 system prompt 包含防自爆约束"""
        captured_systems = []

        async def mock_generate(prompt, system="", temperature=0.7):
            captured_systems.append(system)
            return '{"name":"测试","disposition":"friendly","tags":[],"appearance":"","personality":"","speech_style":"","secrets":[],"knowledge":[],"quests":[]}'

        with patch.object(npc_agent.llm, 'generate', new=AsyncMock(side_effect=mock_generate)):
            await npc_agent._generate_npc_profile("merchant", "精明的商人", "酒馆")

        assert len(captured_systems) > 0
        for system in captured_systems:
            assert "禁止" in system, "NPC人设生成 prompt 缺少防自爆约束"

    @pytest.mark.asyncio
    async def test_generate_initial_dialogue_has_constraint(self, npc_agent):
        """验证 NPC 初始对话的 system prompt 包含防自爆约束"""
        captured_systems = []

        async def mock_generate(prompt, system="", temperature=0.7):
            captured_systems.append(system)
            return "测试对话"

        with patch.object(npc_agent.llm, 'generate', new=AsyncMock(side_effect=mock_generate)):
            await npc_agent._generate_initial_dialogue(
                "老王", "圆滑老练", "说话滴水不漏"
            )

        assert len(captured_systems) > 0
        for system in captured_systems:
            assert "禁止" in system, "初始对话 prompt 缺少防自爆约束"


# ============================================================================
# 测试: GameMaster Prompt 约束
# ============================================================================

class TestGameMasterPrompts:
    """测试 GameMaster 的 LLM 调用包含防自爆约束"""

    @pytest.mark.asyncio
    async def test_generate_combat_narrative_has_constraint(self):
        """验证战斗叙事生成的 system prompt 包含防自爆约束"""
        master = GameMaster()
        master._llm_initialized = True
        captured_systems = []

        async def mock_generate(prompt, system="", temperature=0.7):
            captured_systems.append(system)
            return "你砍向敌人，造成了伤害！"

        with patch.object(master, 'llm', create=True):
            master.llm = MagicMock()
            master.llm.generate = AsyncMock(side_effect=mock_generate)

            await master._generate_combat_narrative(
                attacker_name="你",
                target_name="哥布林",
                action="attack",
                hit=True,
                damage=5,
                attack_roll=15,
                target_ac=10,
                target_hp=10,
                target_max_hp=15,
                turn=1,
            )

        assert len(captured_systems) > 0
        for system in captured_systems:
            assert "禁止" in system, "战斗叙事 prompt 缺少防自爆约束"

    @pytest.mark.asyncio
    async def test_generate_defend_narrative_has_constraint(self):
        """验证防御叙事生成的 system prompt 包含防自爆约束"""
        master = GameMaster()
        master._llm_initialized = True
        captured_systems = []

        async def mock_generate(prompt, system="", temperature=0.7):
            captured_systems.append(system)
            return "你举起盾牌准备防御！"

        with patch.object(master, 'llm', create=True):
            master.llm = MagicMock()
            master.llm.generate = AsyncMock(side_effect=mock_generate)

            await master._generate_defend_narrative("哥布林", 1)

        assert len(captured_systems) > 0
        for system in captured_systems:
            assert "禁止" in system, "防御叙事 prompt 缺少防自爆约束"

    @pytest.mark.asyncio
    async def test_generate_skill_narrative_has_constraint(self):
        """验证技能叙事生成的 system prompt 包含防自爆约束"""
        master = GameMaster()
        master._llm_initialized = True
        captured_systems = []

        async def mock_generate(prompt, system="", temperature=0.7):
            captured_systems.append(system)
            return "你施放魔法攻击！"

        with patch.object(master, 'llm', create=True):
            master.llm = MagicMock()
            master.llm.generate = AsyncMock(side_effect=mock_generate)

            await master._generate_skill_narrative(
                skill_name="魔法攻击",
                target_name="哥布林",
                damage=8,
                hit=True,
                target_hp=7,
                target_max_hp=15,
                turn=1,
            )

        assert len(captured_systems) > 0
        for system in captured_systems:
            assert "禁止" in system, "技能叙事 prompt 缺少防自爆约束"

    @pytest.mark.asyncio
    async def test_generate_item_narrative_has_constraint(self):
        """验证道具叙事生成的 system prompt 包含防自爆约束"""
        master = GameMaster()
        master._llm_initialized = True
        captured_systems = []

        async def mock_generate(prompt, system="", temperature=0.7):
            captured_systems.append(system)
            return "你喝下治疗药水！"

        with patch.object(master, 'llm', create=True):
            master.llm = MagicMock()
            master.llm.generate = AsyncMock(side_effect=mock_generate)

            await master._generate_item_narrative(
                item_name="治疗药水",
                target_name="你",
                heal_amount=10,
                new_hp=20,
                max_hp=30,
                turn=1,
            )

        assert len(captured_systems) > 0
        for system in captured_systems:
            assert "禁止" in system, "道具叙事 prompt 缺少防自爆约束"

    @pytest.mark.asyncio
    async def test_generate_flee_fail_narrative_has_constraint(self):
        """验证逃跑失败叙事生成的 system prompt 包含防自爆约束"""
        master = GameMaster()
        master._llm_initialized = True
        captured_systems = []

        async def mock_generate(prompt, system="", temperature=0.7):
            captured_systems.append(system)
            return "你试图逃跑但被拦截！"

        with patch.object(master, 'llm', create=True):
            master.llm = MagicMock()
            master.llm.generate = AsyncMock(side_effect=mock_generate)

            await master._generate_flee_fail_narrative("哥布林", 1)

        assert len(captured_systems) > 0
        for system in captured_systems:
            assert "禁止" in system, "逃跑失败叙事 prompt 缺少防自爆约束"

    @pytest.mark.asyncio
    async def test_generate_combat_recovery_narrative_has_constraint(self):
        """验证战斗恢复叙事生成的 system prompt 包含防自爆约束"""
        master = GameMaster()
        master._llm_initialized = True
        captured_systems = []

        async def mock_generate(prompt, system="", temperature=0.7):
            captured_systems.append(system)
            return "战斗结束，你回到探索场景。"

        with patch.object(master, 'llm', create=True):
            master.llm = MagicMock()
            master.llm.generate = AsyncMock(side_effect=mock_generate)

            await master._generate_combat_recovery_narrative(
                winner="players",
                reason="敌人被击败",
                state_data={},
            )

        assert len(captured_systems) > 0
        for system in captured_systems:
            assert "禁止" in system, "战斗恢复叙事 prompt 缺少防自爆约束"

    @pytest.mark.asyncio
    async def test_generate_rewards_narrative_has_constraint(self):
        """验证奖励叙事生成的 system prompt 包含防自爆约束"""
        master = GameMaster()
        master._llm_initialized = True
        captured_systems = []

        async def mock_generate(prompt, system="", temperature=0.7):
            captured_systems.append(system)
            return "你获得了经验值和金币！"

        with patch.object(master, 'llm', create=True):
            master.llm = MagicMock()
            master.llm.generate = AsyncMock(side_effect=mock_generate)

            await master._generate_rewards_narrative(
                enemy_name="哥布林",
                rewards={
                    "xp": 25,
                    "gold": 10,
                    "loot": [],
                    "leveled_up": False,
                    "old_level": 1,
                    "new_level": 1,
                    "total_xp": 25,
                },
            )

        assert len(captured_systems) > 0
        for system in captured_systems:
            assert "禁止" in system, "奖励叙事 prompt 缺少防自爆约束"


# ============================================================================
# 测试: MiniMax Interface Prompt 约束
# ============================================================================

class TestMiniMaxInterfacePrompts:
    """测试 MiniMax Interface 的 LLM 调用包含防自爆约束"""

    @pytest.mark.asyncio
    async def test_generate_differentiation_has_constraint(self):
        """验证场景差异化定位的 system prompt 包含防自爆约束"""
        iface = MiniMaxInterface(api_key="test-key")
        captured_systems = []

        async def mock_generate(prompt, system="", temperature=0.7):
            captured_systems.append(system)
            return "测试核心概念"

        with patch.object(iface, 'generate', new=AsyncMock(side_effect=mock_generate)):
            await iface.generate_differentiation(
                scene_type="酒馆",
                existing_tags=["温暖", "热闹"],
                new_requirements="玩家正在寻找一个休息的地方"
            )

        assert len(captured_systems) > 0
        for system in captured_systems:
            assert "禁止" in system, "场景差异化定位 prompt 缺少防自爆约束"

    @pytest.mark.asyncio
    async def test_generate_synopsis_has_constraint(self):
        """验证场景纲要生成的 system prompt 包含防自爆约束"""
        iface = MiniMaxInterface(api_key="test-key")
        captured_systems = []

        async def mock_generate(prompt, system="", temperature=0.7):
            captured_systems.append(system)
            return '{"atmosphere":"温暖热闹","danger_level":"low","synopsis":"测试场景","tags":["测试"],"unique_features":[]}'

        with patch.object(iface, '_parse_json_response', return_value={
            "atmosphere": "温暖热闹",
            "danger_level": "low",
            "synopsis": "测试场景",
            "tags": ["测试"],
            "unique_features": []
        }):
            with patch.object(iface, 'generate', new=AsyncMock(side_effect=mock_generate)):
                await iface.generate_synopsis(
                    core_concept="温暖的酒馆",
                    scene_type="酒馆"
                )

        assert len(captured_systems) > 0
        for system in captured_systems:
            assert "禁止" in system, "场景纲要生成 prompt 缺少防自爆约束"

    @pytest.mark.asyncio
    async def test_generate_detail_has_constraint(self):
        """验证场景详细内容生成的 system prompt 包含防自爆约束"""
        iface = MiniMaxInterface(api_key="test-key")
        captured_systems = []

        async def mock_generate(prompt, system="", temperature=0.7):
            captured_systems.append(system)
            return '{"description":"测试描述","npcs":[],"events":[],"objects":[]}'

        with patch.object(iface, '_parse_json_response', return_value={
            "description": "测试描述",
            "npcs": [],
            "events": [],
            "objects": []
        }):
            with patch.object(iface, 'generate', new=AsyncMock(side_effect=mock_generate)):
                await iface.generate_detail(
                    synopsis="测试场景",
                    scene_type="酒馆",
                    atmosphere="温暖"
                )

        assert len(captured_systems) > 0
        for system in captured_systems:
            assert "禁止" in system, "场景详细内容生成 prompt 缺少防自爆约束"


# ============================================================================
# 测试: Mock LLM 输出不包含禁止模式
# ============================================================================

class TestMockOutputNoForbiddenPatterns:
    """验证 Mock LLM 输出的叙事不包含禁止模式"""

    @pytest.mark.asyncio
    async def test_npc_response_no_third_person(self, npc_agent, sample_npc):
        """验证 NPC 响应不包含第三人称描述"""
        sample_npc.dialogue = "你好啊，陌生人！"

        # 模拟一个符合约束的 LLM 响应
        correct_response = "老王笑着说：'哎呀，欢迎欢迎！来来来，坐下喝一杯？'"

        async def mock_generate(prompt, system="", temperature=0.7):
            return correct_response

        with patch.object(npc_agent.llm, 'generate', new=AsyncMock(side_effect=mock_generate)):
            result = await npc_agent.handle_dialogue(
                sample_npc, "你好", {"location": "酒馆"}
            )

        # 验证输出不包含禁止模式
        violations = check_forbidden(result["response"])
        assert len(violations) == 0, f"发现禁止模式: {violations}"

    @pytest.mark.asyncio
    async def test_npc_response_detects_third_person(self):
        """验证能检测到第三人称描述（负面测试）"""
        # 模拟一个违规的 LLM 响应
        bad_response = "玩家正在寻找一个可以帮助他们的商人..."

        violations = check_forbidden(bad_response)
        assert len(violations) > 0, "应该能检测到'玩家正在'这种违规模式"

    @pytest.mark.asyncio
    async def test_npc_response_detects_dm_reference(self):
        """验证能检测到 DM 引用（负面测试）"""
        violations = check_forbidden("作为你的 DM，我想说...")
        assert len(violations) > 0, "应该能检测到'作为你的 DM'违规模式"

    @pytest.mark.asyncio
    async def test_npc_response_detects_ai_reference(self):
        """验证能检测到 AI 引用（负面测试）"""
        violations = check_forbidden("作为AI助手，我可以帮你...")
        assert len(violations) > 0, "应该能检测到'AI'违规模式"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
