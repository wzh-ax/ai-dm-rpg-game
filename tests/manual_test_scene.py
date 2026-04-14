"""Manual test for SceneAgent"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.scene_agent import SceneAgent, SceneRegistry, SceneMetadata

# Test registry
registry = SceneRegistry(storage_path="data/scenes")
scene = SceneMetadata(
    id="test_001",
    type="forest",
    core_concept="Test concept",
    tags=["test", "forest"]
)
registry.register(scene)
print(f"Registered scene: {registry.get_by_id('test_001').id}")
print(f"Tags: {registry.get_all_tags('forest')}")

# Test SceneAgent instantiation
agent = SceneAgent(registry=registry)
print(f"SceneAgent initialized: {agent is not None}")
print("All imports and basic tests passed!")
