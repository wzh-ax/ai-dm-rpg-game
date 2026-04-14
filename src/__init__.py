"""
AI DM RPG - 核心模块
"""

from .event_bus import EventBus, EventType, Event, EventPriority, get_event_bus, get_event_bus_async, init_event_bus
from .main_dm import MainDM, get_main_dm, init_main_dm
from .game_master import GameMaster, get_game_master, init_game_master
from .hooks import HookRegistry, HookNames, get_hook_registry
from .scene_agent import SceneAgent, SceneRegistry, SceneMetadata, get_scene_agent, init_scene_agent
from .npc_agent import NPCAgent, NPCRegistry, NPCMetadata, get_npc_agent, init_npc_agent
from .memory_manager import (
    MemoryManager,
    ShortTermMemory,
    LongTermMemoryStore,
    MemoryEntry,
    BeatSummary,
    MemoryType,
    get_memory_manager,
    init_memory_manager,
)
from .combat_system import (
    CombatSystem,
    CombatState,
    Combatant,
    CombatantType,
    CombatAction,
    ActionType,
    StatusEffect,
    CombatPhase,
    CombatEventType,
    Difficulty,
    DIFFICULTY_SCALING,
    STATUS_EFFECT_EMOJI,
    get_status_emoji,
    get_combat_system,
    init_combat_system,
)
from .item_system import (
    Item,
    ItemType,
    ItemEffect,
    ItemEffectType,
    ItemRarity,
    ItemRegistry,
    Inventory,
    InventoryManager,
    InventorySlot,
    ItemEventType,
    get_item_registry,
    init_item_registry,
    get_inventory_manager,
    init_inventory_manager,
)
from .save_manager import (
    SaveManager,
    get_save_manager,
    AUTO_SAVE_SLOT,
    MAX_SLOTS,
    SAVE_VERSION,
)
from .character_creator import (
    CharacterCreator,
    Character,
    RaceDefinition,
    ClassDefinition,
    RACES,
    CLASSES,
    get_character_creator,
)
from .tutorial_system import (
    TutorialSystem,
    TutorialState,
    TutorialMode,
    WORLD_INTRO,
    COMMANDS_INTRO,
    FIRST_TASK_INTRO,
    get_tutorial_system,
)
from .quest_state import (
    QuestState,
    QuestStage,
    QUEST_NAME,
)
from .logging_system import (
    GameLogger,
    get_logger,
    init_game_log,
    log_call,
)

__all__ = [
    # Event Bus
    "EventBus",
    "EventType",
    "Event",
    "EventPriority",
    "get_event_bus",
    "get_event_bus_async",
    "init_event_bus",
    # Main DM
    "MainDM",
    "get_main_dm",
    "init_main_dm",
    # GameMaster
    "GameMaster",
    "get_game_master",
    "init_game_master",
    # Hooks
    "HookRegistry",
    "HookNames",
    "get_hook_registry",
    # Scene Agent
    "SceneAgent",
    "SceneRegistry",
    "SceneMetadata",
    "get_scene_agent",
    "init_scene_agent",
    # NPC Agent
    "NPCAgent",
    "NPCRegistry",
    "NPCMetadata",
    "get_npc_agent",
    "init_npc_agent",
    # Memory Manager
    "MemoryManager",
    "ShortTermMemory",
    "LongTermMemoryStore",
    "MemoryEntry",
    "BeatSummary",
    "MemoryType",
    "get_memory_manager",
    "init_memory_manager",
    # Combat System
    "CombatSystem",
    "CombatState",
    "Combatant",
    "CombatantType",
    "CombatAction",
    "ActionType",
    "StatusEffect",
    "CombatPhase",
    "CombatEventType",
    "Difficulty",
    "DIFFICULTY_SCALING",
    "get_combat_system",
    "init_combat_system",
    # Item System
    "Item",
    "ItemType",
    "ItemEffect",
    "ItemEffectType",
    "ItemRarity",
    "ItemRegistry",
    "Inventory",
    "InventoryManager",
    "InventorySlot",
    "ItemEventType",
    "get_item_registry",
    "init_item_registry",
    "get_inventory_manager",
    "init_inventory_manager",
    # Save Manager
    "SaveManager",
    "get_save_manager",
    "AUTO_SAVE_SLOT",
    "MAX_SLOTS",
    "SAVE_VERSION",
    # Character Creator
    "CharacterCreator",
    "Character",
    "RaceDefinition",
    "ClassDefinition",
    "RACES",
    "CLASSES",
    "get_character_creator",
    # Tutorial System
    "TutorialSystem",
    "TutorialState",
    "WORLD_INTRO",
    "COMMANDS_INTRO",
    "FIRST_TASK_INTRO",
    "get_tutorial_system",
    # Quest System
    "QuestState",
    "QuestStage",
    "QUEST_NAME",
    # Logging System
    "GameLogger",
    "get_logger",
    "init_game_log",
    "log_call",
]
