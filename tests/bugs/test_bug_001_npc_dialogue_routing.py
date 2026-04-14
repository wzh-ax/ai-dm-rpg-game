"""
Bug #001 - NPC对话路由
问题：酒馆老板（Innkeeper）对话在所有轮次均无响应，进入万能敷衍

测试场景：
1. 进入酒馆场景
2. 触发「和酒馆老板说话」「Talk to innkeeper」等命令
3. 期望：返回有意义的 NPC 对话，而非万能敷衍

验收标准：
- 「和酒馆老板说话」能触发 NPC 对话
- 「Talk to innkeeper」能触发 NPC 对话
- 返回内容包含具体 NPC 名称和对话，而非"万能敷衍"类内容
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from src.game_master import GameMaster, GameMode
from src.event_bus import EventBus


class TestNpcDialogueRouting:
    """NPC对话路由测试 - Bug #001"""

    @pytest.fixture
    async def gm_with_tavern(self):
        """创建已加载酒馆场景的 GameMaster"""
        event_bus = EventBus()
        gm = GameMaster(event_bus=event_bus)
        gm.llm = None  # 禁用 LLM，使用 fallback

        # 初始化酒馆场景
        gm.current_scene = {
            "type": "酒馆",
            "name": "月光酒馆",
            "atmosphere": "热闹温馨",
            "npcs": [
                {"name": "酒馆老板", "role": "innkeeper", "description": "一个矮胖的中年人"}
            ],
        }
        # 必须设置 GameMaster.active_npcs 实例变量，否则 NPC 不会被识别
        gm.active_npcs = {
            "酒馆老板::innkeeper": {
                "name": "酒馆老板",
                "role": "innkeeper",
                "dialogue_style": "friendly",
                "personality": "helpful",
                "id": "npc_innkeeper_001"
            }
        }
        gm.game_state = {
            "mode": "exploration",
            "active_combat": False,
            "current_location": "月光酒馆",
            "active_npcs_per_scene": {},
        }
        return gm

    @pytest.mark.asyncio
    async def test_talk_to_innkeeper_chinese(self, gm_with_tavern):
        """中文命令「和酒馆老板说话」应触发 NPC 对话"""
        result = await gm_with_tavern._check_npc_interaction("和酒馆老板说话")
        assert result is not None, "酒馆老板对话返回 None，触发了万能敷衍"
        # 返回 str（对话内容），不应该是万能敷衍
        assert not ("万能" in str(result) or "敷衍" in str(result)), \
            f"返回了万能敷衍，实际: {result}"

    @pytest.mark.asyncio
    async def test_talk_to_innkeeper_english(self, gm_with_tavern):
        """英文命令「talk to innkeeper」应触发 NPC 对话"""
        result = await gm_with_tavern._check_npc_interaction("talk to innkeeper")
        assert result is not None, "talk to innkeeper 返回 None，触发了万能敷衍"
        assert not ("万能" in str(result) or "敷衍" in str(result)), \
            f"返回了万能敷衍，实际: {result}"

    @pytest.mark.asyncio
    async def test_talk_to_innkeeper_lowercase(self, gm_with_tavern):
        """小写命令「talk to the innkeeper」应触发 NPC 对话"""
        result = await gm_with_tavern._check_npc_interaction("talk to the innkeeper")
        assert result is not None, "talk to the innkeeper 返回 None，触发了万能敷衍"
        assert not ("万能" in str(result) or "敷衍" in str(result)), \
            f"返回了万能敷衍，实际: {result}"
