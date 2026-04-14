"""
Test: NPC Scene State Inheritance (Bug Fix Verification)

This test validates that the bug fix for NPC scene state inheritance works correctly.

Bug: When LLM returned empty NPCs list, the scene was saved without NPCs.
Fix: Use fallback NPCs when LLM returns empty list.

Acceptance Criteria:
1. Player enters tavern → NPCs present
2. Player talks to NPC
3. Player leaves tavern
4. Player returns to tavern → NPCs STILL present and can be talked to
"""

import pytest
import asyncio
import tempfile
import os
from unittest.mock import AsyncMock, patch

import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.scene_agent import SceneAgent, SceneRegistry, SceneMetadata
from src.game_master import GameMaster
from src.event_bus import EventBus


class MockLLM:
    """Mock LLM that can return empty NPCs to trigger the bug"""
    def __init__(self, return_empty_npcs=False):
        self.return_empty_npcs = return_empty_npcs
    
    async def generate(self, prompt, system=""):
        return "Test response"
    
    async def generate_differentiation(self, scene_type, existing_tags, requirements):
        return f"Test {scene_type}"
    
    async def generate_synopsis(self, core_concept, scene_type):
        return {
            "atmosphere": "mysterious",
            "danger_level": "medium",
            "synopsis": f"A {scene_type}",
            "tags": ["test"],
            "unique_features": [],
        }
    
    async def generate_detail(self, synopsis, scene_type, atmosphere, existing_tags=None, core_concept=None):
        # BUG TRIGGER: Return empty NPCs to test the fix
        if self.return_empty_npcs:
            return {
                "description": f"This is {scene_type}",
                "npcs": [],  # Empty NPCs - triggers the bug!
                "events": [],
                "objects": [],
            }
        else:
            return {
                "description": f"This is {scene_type}",
                "npcs": [{"id": "npc_owner", "name": "Tavern Owner", "role": "merchant", "personality": "friendly", "dialogue_style": "warm"}],
                "events": [],
                "objects": [],
            }


class MockNPCAgent:
    def __init__(self):
        self.registry = AsyncMock()
        self.registry.get_by_id = lambda x: None
    
    async def initialize(self):
        pass
    
    def get_npc(self, npc_id):
        return self.registry.get_by_id(npc_id)
    
    async def handle_dialogue(self, npc, player_input, context):
        return {"response": f"{npc.name} says hello!", "npc_name": npc.name}


@pytest.mark.asyncio
async def test_npc_scene_inheritance_with_empty_npcs():
    """
    Test that fallback NPCs are used when LLM returns empty list.
    
    This is the core bug fix test: previously, when LLM returned {"npcs": []},
    the scene was saved with empty NPCs. Now it uses fallback NPCs.
    """
    event_bus = EventBus()
    tmp = tempfile.mkdtemp()
    
    # Create scene agent with mock LLM that returns empty NPCs
    registry = SceneRegistry(storage_path=os.path.join(tmp, 'scenes'))
    agent = SceneAgent(registry=registry)
    agent._event_bus = AsyncMock()
    agent._event_bus.publish = AsyncMock()
    agent.llm = MockLLM(return_empty_npcs=True)  # Triggers the bug
    await agent.initialize()
    
    # Create GM
    gm = GameMaster(event_bus=event_bus)
    gm.llm = None
    gm.scene_agent = agent
    gm.npc_agent = MockNPCAgent()
    
    # Generate scene - should use fallback NPCs due to empty LLM response
    await gm._generate_scene("tavern")
    
    # Verify NPCs are present (should use fallback, not empty list)
    assert len(gm.active_npcs) > 0, "Fallback NPCs should be generated when LLM returns empty list"
    
    # Verify NPCs are in current_scene
    assert len(gm.current_scene.get("npcs", [])) > 0, "current_scene should have fallback NPCs"


@pytest.mark.asyncio  
async def test_npc_persistence_after_save_load():
    """
    Test that NPCs persist in scenes after save/load cycle.
    """
    event_bus = EventBus()
    tmp = tempfile.mkdtemp()
    
    # Create and setup agent
    registry = SceneRegistry(storage_path=os.path.join(tmp, 'scenes'))
    agent = SceneAgent(registry=registry)
    agent._event_bus = AsyncMock()
    agent._event_bus.publish = AsyncMock()
    agent.llm = MockLLM()  # Normal LLM with NPCs
    await agent.initialize()
    
    gm = GameMaster(event_bus=event_bus)
    gm.llm = None
    gm.scene_agent = agent
    gm.npc_agent = MockNPCAgent()
    
    # Generate scene with NPCs
    await gm._generate_scene("tavern")
    original_npc_count = len(gm.active_npcs)
    assert original_npc_count > 0, "Should have NPCs initially"
    
    # Save registry
    await registry.save()
    
    # Create new registry and load
    new_registry = SceneRegistry(storage_path=os.path.join(tmp, 'scenes'))
    await new_registry.load()
    
    # Verify loaded scene has NPCs
    tavern_scenes = new_registry.get_by_type("tavern")
    assert len(tavern_scenes) > 0, "Should have tavern scene after load"
    assert len(tavern_scenes[0].npcs) > 0, "Loaded scene should have NPCs"


@pytest.mark.asyncio
async def test_fallback_path_has_npcs():
    """
    Test that the fallback path in _generate_scene also generates NPCs.
    
    Previously, the fallback path set NPCs to [] directly.
    Now it uses _generate_fallback_npcs.
    """
    event_bus = EventBus()
    
    # Create GM without scene_agent (triggers fallback path)
    gm = GameMaster(event_bus=event_bus)
    gm.llm = None
    gm.scene_agent = None  # Forces fallback path
    gm.npc_agent = MockNPCAgent()
    
    # Generate scene via fallback
    result = await gm._generate_scene("tavern")
    
    # Verify fallback NPCs are present
    assert len(gm.active_npcs) > 0, "Fallback path should generate NPCs"
    assert len(gm.current_scene.get("npcs", [])) > 0, "Fallback path should set NPCs in current_scene"


@pytest.mark.asyncio
async def test_npc_persists_across_scene_switches():
    """
    Test the core bug fix: NPC persists when switching between scenes.
    
    Scenario:
    1. Player enters tavern → NPC appears
    2. Player switches to forest → NPC should persist for tavern
    3. Player returns to tavern → Same NPC (by name+role) with state preserved
    
    Note: UUID may change across visits (scene regenerates NPCs), but semantic
    identity (name+role) and state are preserved.
    """
    event_bus = EventBus()
    tmp = tempfile.mkdtemp()
    
    # Create scene agent with normal NPCs
    registry = SceneRegistry(storage_path=os.path.join(tmp, 'scenes'))
    agent = SceneAgent(registry=registry)
    agent._event_bus = AsyncMock()
    agent._event_bus.publish = AsyncMock()
    agent.llm = MockLLM()
    await agent.initialize()
    
    gm = GameMaster(event_bus=event_bus)
    gm.llm = None
    gm.scene_agent = agent
    gm.npc_agent = MockNPCAgent()
    
    # Step 1: Enter tavern - get initial NPCs
    await gm._generate_scene("tavern")
    tavern_npcs_before = dict(gm.active_npcs)
    assert len(tavern_npcs_before) > 0, "Tavern should have NPCs"
    
    # Extract name+role keys before leaving
    names_roles_before = {gm._npc_key(npc) for npc in tavern_npcs_before.values() if gm._npc_key(npc)}
    
    # Step 2: Switch to forest (tavern NPCs should be saved to per_scene storage)
    await gm._generate_scene("forest")
    assert "tavern" in gm.game_state.get("active_npcs_per_scene", {}), \
        "Tavern NPCs should be saved when leaving"
    saved_tavern_npcs = gm.game_state["active_npcs_per_scene"]["tavern"]
    assert len(saved_tavern_npcs) > 0, "Saved tavern NPCs should have entries"
    
    # Step 3: Return to tavern - should have semantically same NPCs
    await gm._generate_scene("tavern")
    restored_npcs = gm.active_npcs
    
    # Check: per_scene storage should be updated with restored NPCs
    assert "tavern" in gm.game_state.get("active_npcs_per_scene", {}), \
        "active_npcs_per_scene should have tavern entry after return"
    
    # The key acceptance criterion: ALL original NPCs should be preserved (subset check)
    # New NPCs may appear (scene can generate new NPCs), but original ones must remain
    names_roles_after = {gm._npc_key(npc) for npc in restored_npcs.values() if gm._npc_key(npc)}
    missing_npcs = names_roles_before - names_roles_after
    assert len(missing_npcs) == 0, \
        f"Original NPCs should be preserved. Missing: {missing_npcs}. Before: {names_roles_before}, After: {names_roles_after}"


@pytest.mark.asyncio
async def test_npc_state_preserved_across_scenes():
    """
    Test that NPC state (dialogue history) is preserved across scene switches.
    
    Scenario:
    1. Enter tavern, add state to NPC
    2. Leave tavern, go to forest
    3. Return to tavern - NPC should remember the state
    """
    event_bus = EventBus()
    
    gm = GameMaster(event_bus=event_bus)
    gm.llm = None
    gm.scene_agent = None  # Use fallback path for deterministic UUIDs
    gm.npc_agent = MockNPCAgent()
    
    # Enter tavern
    await gm._generate_scene("tavern")
    tavern_npc_key = None
    tavern_npc_data = None
    for npc_id, npc_data in gm.active_npcs.items():
        key = gm._npc_key(npc_data)
        if key:
            tavern_npc_key = key
            tavern_npc_data = npc_data
            break
    assert tavern_npc_key is not None, "Should have tavern NPC with valid name+role"
    
    # Simulate NPC state/dialogue history being added
    gm.active_npcs[tavern_npc_key]["_dialogue_history"] = ["Hello", "How are you?"]
    gm.active_npcs[tavern_npc_key]["_affinity"] = 50
    
    # Switch to forest (this saves tavern NPCs to per_scene)
    await gm._generate_scene("forest")
    
    # Return to tavern
    await gm._generate_scene("tavern")
    
    # Check state preserved - find NPC by name+role key
    restored_npc = None
    for npc_data in gm.active_npcs.values():
        if gm._npc_key(npc_data) == tavern_npc_key:
            restored_npc = npc_data
            break
    
    assert restored_npc is not None, f"Should have restored NPC with key '{tavern_npc_key}'"
    assert "_dialogue_history" in restored_npc, "Dialogue history should be preserved"
    assert restored_npc["_dialogue_history"] == ["Hello", "How are you?"], \
        f"Dialogue history content should match. Got: {restored_npc.get('_dialogue_history')}"
    assert restored_npc["_affinity"] == 50, "Affinity should be preserved"


@pytest.mark.asyncio
async def test_npc_first_time_scene_has_npcs():
    """
    Test that entering a scene for the first time still generates/loads NPCs.
    """
    event_bus = EventBus()
    
    gm = GameMaster(event_bus=event_bus)
    gm.llm = None
    gm.scene_agent = None  # Forces fallback
    gm.npc_agent = MockNPCAgent()
    
    # Enter tavern for first time
    await gm._generate_scene("tavern")
    
    # Should have NPCs
    assert len(gm.active_npcs) > 0, "First visit to tavern should have NPCs"
    # Per-scene storage should be populated
    assert "tavern" in gm.game_state.get("active_npcs_per_scene", {}), \
        "Per-scene storage should be populated after first visit"


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
