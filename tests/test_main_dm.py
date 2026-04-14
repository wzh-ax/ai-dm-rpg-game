# -*- coding: utf-8 -*-
"""
MainDM Unit Tests
"""

import pytest
import asyncio
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.main_dm import MainDM, get_main_dm, init_main_dm
from src.event_bus import EventBus, EventType, Event
from src.hooks import HookRegistry


@pytest.fixture
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def event_bus():
    return EventBus()


@pytest.fixture
def dm(event_bus):
    return MainDM(event_bus=event_bus)


class TestMainDMStartStop:
    @pytest.mark.asyncio
    async def test_start_registers_subscriptions(self, dm, event_bus):
        await dm.start()
        assert dm._running == True
        await dm.stop()

    @pytest.mark.asyncio
    async def test_start_idempotent(self, dm):
        await dm.start()
        await dm.start()
        assert dm._running == True
        await dm.stop()

    @pytest.mark.asyncio
    async def test_stop_clears_subscriptions(self, dm, event_bus):
        await dm.start()
        await dm.stop()
        assert dm._running == False

    @pytest.mark.asyncio
    async def test_stop_idempotent(self, dm):
        await dm.start()
        await dm.stop()
        await dm.stop()


class TestMainDMHooks:
    @pytest.mark.asyncio
    async def test_set_hooks(self, dm):
        hooks = HookRegistry()
        dm.set_hooks(hooks)
        assert dm.hooks is hooks

    @pytest.mark.asyncio
    async def test_set_hooks_with_mock(self, dm):
        hooks = MagicMock(spec=HookRegistry)
        dm.set_hooks(hooks)
        assert dm.hooks is not None


class TestMainDMOnPlayerInput:
    @pytest.mark.asyncio
    async def test_on_player_input_increments_turn(self, dm):
        await dm.start()
        initial_turn = dm.game_state["turn"]

        event = Event(
            type=EventType.PLAYER_INPUT,
            data={"text": "test input"},
            source="test"
        )
        await dm._on_player_input(event)

        assert dm.game_state["turn"] == initial_turn + 1
        await dm.stop()

    @pytest.mark.asyncio
    async def test_on_player_input_calls_generate_narrative(self, dm):
        await dm.start()

        with patch.object(dm, '_generate_narrative', new=AsyncMock(return_value="test narrative")) as mock_gen:
            event = Event(
                type=EventType.PLAYER_INPUT,
                data={"text": "test input"},
                source="test"
            )
            await dm._on_player_input(event)
            mock_gen.assert_called_once()

        await dm.stop()

    @pytest.mark.asyncio
    async def test_on_player_input_with_hooks(self, dm, event_bus):
        hooks = MagicMock(spec=HookRegistry)
        hooks.trigger = AsyncMock()
        dm.set_hooks(hooks)

        await dm.start()

        event = Event(
            type=EventType.PLAYER_INPUT,
            data={"text": "test"},
            source="test"
        )
        await dm._on_player_input(event)

        hooks.trigger.assert_called()
        await dm.stop()


class TestMainDMOnSubagentResult:
    @pytest.mark.asyncio
    async def test_on_subagent_result_receives_event(self, dm):
        event = Event(
            type=EventType.SUBNET_AGENT_RESULT,
            data={"agent": "scene_agent", "result": {"status": "success"}},
            source="test"
        )
        await dm._on_subagent_result(event)

    @pytest.mark.asyncio
    async def test_on_subagent_result_handles_missing_fields(self, dm):
        event = Event(
            type=EventType.SUBNET_AGENT_RESULT,
            data={},
            source="test"
        )
        await dm._on_subagent_result(event)


class TestMainDMGenerateNarrative:
    @pytest.mark.asyncio
    async def test_generate_narrative_returns_string(self, dm):
        result = await dm._generate_narrative("test input", 1)
        assert isinstance(result, str)
        assert len(result) > 0

    @pytest.mark.asyncio
    async def test_generate_narrative_contains_input(self, dm):
        result = await dm._generate_narrative("test input", 1)
        assert "test input" in result

    @pytest.mark.asyncio
    async def test_generate_narrative_different_turns(self, dm):
        result1 = await dm._generate_narrative("test", 1)
        result2 = await dm._generate_narrative("test", 2)
        result3 = await dm._generate_narrative("test", 3)
        assert len({result1, result2, result3}) > 1


class TestMainDMGameState:
    def test_game_state_initialization(self, dm):
        assert "turn" in dm.game_state
        assert "story_history" in dm.game_state
        assert dm.game_state["turn"] == 0

    def test_current_scene_initialization(self, dm):
        assert dm.current_scene == {}

    def test_current_scene_can_be_set(self, dm):
        dm.current_scene = {"type": "forest", "core_concept": "dark forest"}
        assert dm.current_scene["type"] == "forest"


class TestMainDMHandlePlayerMessage:
    @pytest.mark.asyncio
    async def test_handle_player_message_calls_event_bus_publish(self, dm):
        with patch.object(dm.event_bus, 'publish', new=AsyncMock()) as mock_publish:
            await dm.handle_player_message("test message")
            mock_publish.assert_called_once()
            call_args = mock_publish.call_args[0][0]
            assert call_args.data["text"] == "test message"


class TestMainDMGlobalInstance:
    def test_get_main_dm_returns_same_instance(self):
        import src.main_dm as main_dm_module
        main_dm_module._global_dm = None

        dm1 = get_main_dm()
        dm2 = get_main_dm()
        assert dm1 is dm2

    @pytest.mark.asyncio
    async def test_init_main_dm(self):
        import src.main_dm as main_dm_module
        main_dm_module._global_dm = None

        dm = await init_main_dm()
        assert dm._running == True
        await dm.stop()




if __name__ == "__main__":
    pytest.main([__file__, "-v"])
