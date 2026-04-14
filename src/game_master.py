"""
GameMaster - 游戏主持人，协调所有子 Agent

职责：
1. 管理游戏状态（当前场景、活跃 NPC、玩家状态）
2. 协调 Scene Agent 生成场景
3. 协调 NPC Agent 生成 NPC 对话
4. 管理探索模式与战斗模式切换
5. 生成最终叙事（整合子 Agent 结果）
"""

import asyncio
import logging
import random
import uuid
from typing import Any, Tuple
import re

from .event_bus import EventBus, EventType, Event, get_event_bus
from .hooks import HookRegistry, get_hook_registry, HookNames
from .scene_agent import SceneAgent, get_scene_agent, generate_dynamic_atmosphere, generate_atmosphere_v2
from .npc_agent import NPCAgent, get_npc_agent
from .memory_manager import MemoryManager
from .combat_system import CombatSystem, CombatState, Combatant, CombatantType, StatusEffect, ActionType, CombatAction, EnemyFactory, Difficulty, DIFFICULTY_SCALING
from .minimax_interface import MiniMaxInterface, get_minimax_interface
from .equipment_system import get_equipment_manager, reset_equipment_manager, EquipmentSlot
from .save_manager import SaveManager, get_save_manager, AUTO_SAVE_SLOT
from .quest_state import QuestState, QuestStage, QUEST_NAME
from .scene_objects import SceneObject, ExamineResult, PickupResult, UseResult, get_scene_object_registry
from .logging_system import get_logger, init_game_log

logger = logging.getLogger(__name__)


class GameMode:
    """游戏模式"""
    EXPLORATION = "exploration"  # 探索模式
    COMBAT = "combat"           # 战斗模式
    DIALOGUE = "dialogue"       # 对话模式


class GameMaster:
    """
    游戏主持人（GameMaster）

    协调所有子 Agent，管理游戏状态，生成叙事
    """

    def __init__(
        self,
        event_bus: EventBus | None = None,
        hook_registry: HookRegistry | None = None,
    ):
        self.event_bus = event_bus or get_event_bus()
        self.hooks = hook_registry or get_hook_registry()

        # 子 Agent
        self.scene_agent: SceneAgent | None = None
        self.npc_agent: NPCAgent | None = None

        # 游戏系统
        self.memory = MemoryManager()
        self.combat = CombatSystem(self.event_bus)
        self.save_manager: SaveManager = get_save_manager()

        # 游戏状态
        self.mode = GameMode.EXPLORATION  # 当前模式
        self.current_scene: dict[str, Any] = {}
        self.active_npcs: dict[str, dict] = {}
        self._current_npc_id: str | None = None  # 当前对话中的 NPC ID
        self.combat_turn = 0  # 战斗回合数
        self.game_state: dict[str, Any] = {
            "turn": 0,
            "location": "未知",
            "player_stats": {
                "hp": 30,
                "max_hp": 30,
                "ac": 12,
                "xp": 0,
                "level": 1,
                "gold": 0,
                "inventory": [],
            },
            "game_over": False,
            "quest_stage": "not_started",
            "quest_active": False,
            "quest_name": QUEST_NAME,
            "player_choices": [],  # 玩家关键选择记录
            "difficulty": "normal",  # 难度模式: easy / normal / hard
            "active_npcs": {},  # NPC 场景状态继承：初始化为空
            "active_npcs_per_scene": {},  # NPC 场景状态继承：按场景存储 NPC
            "accessibility_options": {
                "color_contrast": "normal",  # 颜色对比度: "normal" | "high_contrast"
                "damage_colors": True,       # 战斗伤害数字着色: True | False
            },
        }

        # 难度描述（用于 UI 显示）
        self.DIFFICULTY_DESCRIPTIONS = {
            "easy": "简单 - 敌人较弱，掉落更多",
            "normal": "普通 - 标准挑战",
            "hard": "困难 - 敌人更强，掉落更少，无法借逃跑加成逃离",
        }

        # LLM（可外部设置，初始化时不依赖）
        self.llm: MiniMaxInterface | None = None
        self._llm_initialized = False

        # 战斗相关状态保存（用于战斗后场景恢复）
        self._pre_combat_scene: dict[str, Any] | None = None
        self._pre_combat_location: str = "未知"
        self._pre_combat_narrative: str = ""  # 战斗前正在发生的事
        self._last_enemy_name: str = "未知敌人"  # 最后击败的敌人名称（用于奖励生成）

        # 主动战斗状态标记（场景切换时需重置）
        self.active_combat: bool = False

        # 订阅 ID
        self._subscriber_id = "game_master"
        self._running = False

        # 游戏结束标记
        self.game_over = False

        # 任务系统
        self.quest_state = QuestState()

        # ========== Fallback 降级模式跟踪 ==========
        # 连续 3 次降级模式触发告警
        from .scene_agent import DegradationTracker
        self._degradation_tracker = DegradationTracker(alert_threshold=3)
        # 当前是否处于降级模式
        self._in_degradation_mode = False
        # 降级警告是否已显示（避免重复显示）
        self._degradation_alert_shown = False

    async def initialize(self):
        """初始化所有子 Agent"""
        logger.info("GameMaster initializing...")

        # 初始化子 Agent
        self.scene_agent = get_scene_agent()
        await self.scene_agent.initialize()

        self.npc_agent = get_npc_agent()
        await self.npc_agent.initialize()

        # 注册 GameMaster 的 hook
        self._register_hooks()

        # 订阅事件
        await self._subscribe_events()

        # 启动记忆管理器
        await self.memory.start()

        # 初始化 LLM（用于战斗叙事生成）
        try:
            self.llm = get_minimax_interface()
            self._llm_initialized = True
            logger.info("GameMaster LLM initialized")
        except Exception as e:
            logger.warning(f"GameMaster LLM init failed (will use fallback): {e}")
            self._llm_initialized = False

        self._running = True
        logger.info("GameMaster initialized")

    def _register_hooks(self):
        """注册 GameMaster 的中央 hook"""
        self.hooks.register(
            HookNames.BEFORE_SCENE_UPDATE,
            self._on_before_scene_update,
            phase="before",
            order=0
        )

        self.hooks.register(
            HookNames.BEFORE_NPC_GENERATION,
            self._on_before_npc_generation,
            phase="before",
            order=0
        )

    async def _subscribe_events(self):
        """订阅事件"""
        await self.event_bus.subscribe(
            EventType.PLAYER_INPUT,
            self._on_player_input,
            self._subscriber_id
        )

        await self.event_bus.subscribe(
            EventType.NARRATIVE_OUTPUT,
            self._on_narrative_output,
            self._subscriber_id
        )

        await self.event_bus.subscribe(
            EventType.COMBAT_START,
            self._on_combat_start,
            self._subscriber_id
        )
        await self.event_bus.subscribe(
            EventType.COMBAT_END,
            self._on_combat_end,
            self._subscriber_id
        )

    async def _on_before_scene_update(self, scene_type: str, requirements: str):
        """场景更新前的 hook"""
        existing = self.scene_agent.get_existing_scene(scene_type)
        if existing:
            return existing
        return None

    async def _on_before_npc_generation(self, role: str, requirements: str):
        """NPC 生成前的 hook - 注入场景上下文"""
        # npc_agent 传入 (role, requirements)，构建 context 并返回
        context = {
            "role": role,
            "requirements": requirements,
        }
        if self.current_scene:
            context["scene_context"] = self.current_scene.get("description", "")
            context["scene_type"] = self.current_scene.get("type", "")
        return context

    async def _on_combat_start(self, event: Event):
        """战斗开始"""
        get_logger().info("game_master", f"Combat started - mode changed to COMBAT")
        self.mode = GameMode.COMBAT
        self.active_combat = True

    async def _on_combat_end(self, event: Event):
        """战斗结束 - 恢复探索模式"""
        self.mode = GameMode.EXPLORATION
        self.active_combat = False

        # 恢复战斗前的场景
        if self._pre_combat_scene is not None:
            self.current_scene = self._pre_combat_scene
            self.game_state["location"] = self._pre_combat_location

        # 设置战斗后 atmosphere 标记（玩家胜利时触发特殊 atmosphere）
        data = event.data or {}
        winner = data.get("winner", "unknown")
        if winner == "players":
            self.game_state["_post_combat_scene"] = True

        # 同步玩家HP从战斗状态回到game_state（战斗后HP变化需要持久化）
        combat = self.combat.get_active_combat()
        if combat:
            player = combat.combatants.get("player")
            if player:
                self.game_state["player_stats"]["hp"] = player.current_hp
                self.game_state["player_stats"]["max_hp"] = player.max_hp
        else:
            # combat已经是None（已结束），从事件state_data中恢复HP
            state_data = (event.data or {}).get("state", {})
            for c_data in state_data.get("active_combatants", []):
                if c_data.get("type") == "player":
                    self.game_state["player_stats"]["hp"] = c_data.get("hp", self.game_state["player_stats"]["hp"])
                    self.game_state["player_stats"]["max_hp"] = c_data.get("max_hp", self.game_state["player_stats"]["max_hp"])
                    break

        # 从事件中获取战斗结果
        data = event.data or {}
        state_data = data.get("state", {})
        winner = data.get("winner", "unknown")
        reason = data.get("reason", "")
        
        get_logger().info("game_master", f"Combat result: winner={winner}, reason={reason}")

        # 追踪战斗统计（用于多结局评定）
        if winner == "players":
            self.quest_state.combat_count += 1
            # 追踪对怪物造成的伤害（通过敌人HP变化估算）
            enemies_hp_lost = 0
            for c_data in state_data.get("active_combatants", []):
                if c_data.get("type") == "enemy":
                    max_hp = c_data.get("max_hp", 0)
                    hp = c_data.get("hp", max_hp)
                    enemies_hp_lost += (max_hp - hp)
            if enemies_hp_lost > 0:
                self.quest_state.monster_hp_dealt += enemies_hp_lost

        # 生成战斗结束叙事（探索恢复）
        recovery_narrative = await self._generate_combat_recovery_narrative(
            winner, reason, state_data
        )
        
        # 发布场景恢复事件
        await self.event_bus.publish(Event(
            type=EventType.SCENE_UPDATE,
            data={
                "scene": self.current_scene,
                "is_recovery": True,
                "combat_result": {"winner": winner, "reason": reason},
                "recovery_narrative": recovery_narrative,
            },
            source=self._subscriber_id
        ))

        # 同时发布叙事输出（让玩家看到战斗结束后的场景恢复叙事）
        await self.event_bus.publish(Event(
            type=EventType.NARRATIVE_OUTPUT,
            data={
                "text": recovery_narrative,
                "turn": self.game_state.get("turn", 0),
                "scene": self.current_scene,
                "mode": self.mode,
                "is_combat_recovery": True,
            },
            source=self._subscriber_id
        ))

        # 如果玩家胜利，生成奖励
        if winner == "players":
            rewards = await self._generate_rewards(self._last_enemy_name)
            rewards_narrative = await self._generate_rewards_narrative(self._last_enemy_name, rewards)

            # 发布奖励叙事
            await self.event_bus.publish(Event(
                type=EventType.NARRATIVE_OUTPUT,
                data={
                    "text": rewards_narrative,
                    "turn": self.game_state.get("turn", 0),
                    "scene": self.current_scene,
                    "mode": self.mode,
                    "is_rewards": True,
                    "rewards": rewards,
                },
                source=self._subscriber_id
            ))

            # 任务系统：如果击败了影狼且任务阶段为 DEFEAT_MONSTER，推进到 RETURN_TO_MAYOR
            if (self.quest_state.stage == QuestStage.DEFEAT_MONSTER
                    and self._last_enemy_name in ["影狼", "狼"]):
                self.quest_state.advance_to(QuestStage.RETURN_TO_MAYOR)
                self.game_state["quest_stage"] = QuestStage.RETURN_TO_MAYOR.value
                quest_advance_narrative = "\n📜 任务更新：影狼已被击败！是时候回去向镇长报告了。"
                await self.event_bus.publish(Event(
                    type=EventType.NARRATIVE_OUTPUT,
                    data={
                        "text": quest_advance_narrative,
                        "turn": self.game_state.get("turn", 0),
                        "scene": self.current_scene,
                        "mode": self.mode,
                        "is_quest_advance": True,
                    },
                    source=self._subscriber_id
                ))
            
            # 自动存档（战斗胜利后）
            await self._auto_save()
            
            # 清理
            self._last_enemy_name = "未知敌人"

        # 清理预保存状态
        self._pre_combat_scene = None
        self._pre_combat_location = "未知"
        self._pre_combat_narrative = ""
        # 清理 NPC 对话上下文
        self._current_npc_id = None

    async def _on_narrative_output(self, event: Event):
        """叙事输出后的处理"""
        pass

    # --------------------------------------------------------------------------
    # 探索模式 - 核心方法
    # --------------------------------------------------------------------------

    def _record_choice(self, choice_type: str, choice_value: str, details: str = "") -> None:
        """
        记录玩家的关键选择到 game_state 和 quest_state
        
        Args:
            choice_type: 选择类型 (dialogue/combat/exploration/item/skill)
            choice_value: 选择的具体值
            details: 额外描述
        """
        choice_entry = {
            "type": choice_type,
            "value": choice_value,
            "details": details,
            "stage": self.quest_state.stage.value,
            "turn": self.game_state.get("turn", 0),
        }
        # 记录到 game_state
        self.game_state.setdefault("player_choices", []).append(choice_entry)
        # 记录到 quest_state
        self.quest_state.record_choice(choice_type, choice_value, details)
        logger.debug(f"Choice recorded: [{choice_type}] {choice_value}")

    # -------------------------------------------------------------------------
    # 命令归一化层
    # -------------------------------------------------------------------------

    # 英文敌人名 → 中文敌人名 映射
    ENEMY_NAME_EN_TO_CN = {
        "goblin": "哥布林",
        "goblins": "哥布林",
        "dragon": "龙",
        "wolf": "狼",
        "skeleton": "骷髅",
        "slime": "史莱姆",
        "troll": "巨魔",
        "giant dragon": "巨龙",
        "zombie": "僵尸",
        "vampire": "吸血鬼",
        "ghost": "幽灵",
        "shadow wolf": "影狼",
        "werewolf": "狼人",
        "giant spider": "巨蛛",
        "spider": "蜘蛛",
        "orc": "兽人",
        "bandit": "盗贼",
        "bat": "蝙蝠",
        "rat": "老鼠",
        "snake": "蛇",
    }

    # 中文敌人名列表（用于提取）
    ENEMY_NAMES_CN = [
        "哥布林", "龙", "狼", "骷髅", "史莱姆", "巨魔", "巨龙",
        "僵尸", "吸血鬼", "幽灵", "影狼", "狼人", "巨蛛", "蜘蛛",
        "兽人", "盗贼", "蝙蝠", "老鼠", "蛇",
    ]

    # ========== NPC 命令归一化层 ==========
    # 同义命令 → 统一意图的映射表
    _COMMAND_SYNONYMS = {
        # NPC 对话类
        "和老板聊聊天": ("npc_talk", "酒馆老板"),
        "和酒馆老板说话": ("npc_talk", "酒馆老板"),
        "和酒馆老板交谈": ("npc_talk", "酒馆老板"),
        "找酒馆老板聊聊": ("npc_talk", "酒馆老板"),
        "询问任务": ("npc_quest", "酒馆老板"),
        "问任务": ("npc_quest", "酒馆老板"),
        "向酒馆老板询问任务": ("npc_quest", "酒馆老板"),
        "和老板聊聊天": ("npc_talk", "酒馆老板"),
        "找人聊聊天": ("npc_chat", None),
    }

    # 场景主 NPC 查找表（场景ID → 主 NPC 名称）
    _SCENE_PRIMARY_NPC = {
        "酒馆": "酒馆老板",
        "绿叶村": "村长",
        "森林": None,
        "广场": "市场商人",
    }

    def _normalize_command(self, raw_input: str) -> dict:
        """
        将玩家原始输入归一化为标准命令 dict。

        返回 dict，包含以下字段：
          action (str | None): 归一化后的动作（"attack", "dialogue" 等）
          cmd_type (str | None): NPC 路由类型（"npc_talk", "npc_quest", "npc_chat"）
          params (dict): 附加参数（npc_name, target, raw 等）
        """
        raw = raw_input.strip()
        low = raw.lower()

        # Step 0: 攻击命令归一化（中英文）
        _ATTACK_KEYWORDS_CN = ("攻击", "打", "砍", "揍", "击", "杀")
        _ATTACK_KEYWORDS_EN = ("attack", "fight", "kill", "strike", "hit", "slay")
        if any(low.startswith(kw) or kw in low for kw in _ATTACK_KEYWORDS_CN + _ATTACK_KEYWORDS_EN):
            return {"action": "attack", "cmd_type": None, "params": {"raw": raw}}

        # Step 1: 精确匹配 synonym 表
        if raw in self._COMMAND_SYNONYMS:
            cmd_type, npc_name = self._COMMAND_SYNONYMS[raw]
            if npc_name is None and cmd_type == "npc_chat":
                current_location = self.game_state.get("location", "绿叶村")
                npc_name = self._SCENE_PRIMARY_NPC.get(current_location, "酒馆老板")
            return {"action": None, "cmd_type": cmd_type, "params": {"npc_name": npc_name}}

        # Step 2: 正则模式匹配
        match = re.match(r"和(.+?)(说话|聊天|交谈|聊聊)", raw)
        if match:
            npc_name = match.group(1).strip()
            intent = match.group(2)
            cmd_type = "npc_talk" if intent in ("说话", "交谈") else "npc_chat"
            return {"action": None, "cmd_type": cmd_type, "params": {"npc_name": npc_name}}

        match = re.match(r"向(.+?)询问任务|问(.+?)任务|询问(.+?)任务", raw)
        if match:
            npc_name = match.group(1) or match.group(2) or match.group(3)
            return {"action": None, "cmd_type": "npc_quest", "params": {"npc_name": npc_name.strip()}}

        # Step 3: 回退到原有 LLM 解析
        return {"action": None, "cmd_type": None, "params": {"raw": raw}}

    def _is_location_change_command(self, raw_input: str) -> bool:
        """检测是否为场景切换命令。"""
        raw = raw_input.strip()
        LOCATION_COMMANDS = {
            "前往酒馆", "去酒馆", "进酒馆", "进入酒馆", "进 tavern",
            "离开酒馆", "出酒馆", "退出酒馆", "出 tavern",
            "前往森林", "去森林", "进森林", "进入森林",
            "前往广场", "去广场", "进广场", "进入广场",
            "回村庄", "回绿叶村", "回村",
            "进入城镇", "去城镇", "前往城镇",
        }
        if raw in LOCATION_COMMANDS:
            return True
        # 泛化匹配（包含移动动词+位置名）
        MOVE_VERBS = ["前往", "去", "进", "进入", "离开", "出", "回"]
        LOCATIONS = ["酒馆", "森林", "广场", "村庄", "城镇", "洞穴", "山洞", "平原", "绿叶村"]
        for verb in MOVE_VERBS:
            for loc in LOCATIONS:
                if verb + loc in raw:
                    return True
        return False

    def _clear_combat_state(self):
        """
        强制清除战斗状态。
        """
        self.game_state["active_combat"] = None
        self.active_combat = False
        self.game_state["current_enemy"] = None
        self.game_state["combat_rounds"] = 0
        self.mode = GameMode.EXPLORATION
        self._pre_combat_scene = None
        self._pre_combat_location = "未知"
        self._pre_combat_narrative = ""
        logger.info("Combat state cleared on scene transition")

    def _is_shop_command(self, raw_input: str) -> bool:
        """检测是否为商店命令。"""
        SHOP_KEYWORDS = ["买", "购买", "商店", "买药水", "买武器", "买装备", "商品", "shopping", "buy"]
        return any(kw in raw_input for kw in SHOP_KEYWORDS)

    # ========== 战斗命令归一化层 ==========
    def _normalize_combat_command(self, input_text: str) -> dict:
        """
        归一化玩家战斗命令，将同义词/中英文变体统一映射到标准 action，并提取目标。

        归一化规则：
        - 中文攻击关键词（攻击、打、砍、揍）→ action="attack"
        - 英文攻击关键词（attack、fight、kill）→ action="attack"
        - 中文对话关键词（说、问、交谈）→ action="dialogue"
        - 英文对话关键词（talk、speak、ask）→ action="dialogue"
        - 同时提取攻击/对话目标（中文或英文敌人名）

        Returns:
            dict with keys:
                action (str): 归一化后的动作类型
                target (str | None): 提取的目标名称（统一为中文）
                original_target (str | None): 原始文本中的目标名称
                normalized_text (str): 原始输入（保留供上游使用）
        """
        text = input_text.strip().lower()
        original = input_text.strip()

        # === 1. 提取目标（先于 action 判断，确保攻击和对话都能拿到 target） ===
        target = None
        original_target = None

        # 1a. 尝试从原始文本中匹配中文敌人名
        for name in self.ENEMY_NAMES_CN:
            if name in original:
                target = name
                original_target = name
                break

        # 1b. 如果没找到中文名，尝试英文敌人名 → 映射为中文
        if target is None:
            for en_name, cn_name in self.ENEMY_NAME_EN_TO_CN.items():
                if en_name in text:
                    target = cn_name
                    original_target = en_name
                    break

        # === 2. 归一化 action ===
        action = "unknown"

        # 中文攻击关键词 → action="attack"
        cn_attack_keywords = ["攻击", "打", "砍", "揍", "刺", "战斗", "打架"]
        for kw in cn_attack_keywords:
            if kw in original:
                action = "attack"
                break

        # 英文攻击关键词 → action="attack"
        if action == "unknown":
            en_attack_keywords = ["attack", "fight", "kill", "hit", "strike"]
            for kw in en_attack_keywords:
                if kw in text:
                    action = "attack"
                    break

        # 中文对话关键词 → action="dialogue"
        if action == "unknown":
            cn_dialogue_keywords = ["说", "问", "交谈", "对话", "聊", "谈"]
            for kw in cn_dialogue_keywords:
                if kw in original:
                    action = "dialogue"
                    break

        # 英文对话关键词 → action="dialogue"
        if action == "unknown":
            en_dialogue_keywords = ["talk", "speak", "ask", "chat", "greet"]
            for kw in en_dialogue_keywords:
                if kw in text:
                    action = "dialogue"
                    break

        return {
            "action": action,
            "target": target,
            "original_target": original_target,
            "normalized_text": original,
        }

    def _check_combat_trigger(self, player_text: str) -> dict | None:
        """
        检查是否触发战斗

        归一化层优先：使用 _normalize_command 提取 action 和 target，
        保证中英文输入（攻击哥布林 / attack goblin）路由到相同的战斗触发。

        Returns:
            dict with keys: trigger (str), enemy_data (dict), enemy_id (str)
            or None if不触发战斗
        """
        text = player_text.lower()

        # 友好 NPC/商人 不触发战斗（优先排除）
        friendly_keywords = ["商人", "NPC", "友好", "npc"]
        for kw in friendly_keywords:
            if kw in text:
                return None

        # === 归一化层：提取 action 和 target ===
        norm = self._normalize_combat_command(player_text)
        action = norm["action"]
        target = norm["target"]  # 可能是中文名（如「哥布林」）或 None

        # === 基于归一化 action 判断是否攻击 ===
        if action == "attack":
            # 使用归一化提取的 target
            enemy_name = target if target else "未知敌人"
            return {
                "trigger": "aggressive",
                "enemy_data": {"name": enemy_name, "role": "怪物"},
                "enemy_id": f"enemy_{enemy_name}",
            }

        # === 以下处理非攻击类的战斗触发（突袭/敌人出现）===
        # 突袭（敌人主动偷袭玩家）- 优先检测
        ambush_keywords = ["袭击", "突袭", "ambush", "偷袭"]
        for kw in ambush_keywords:
            if kw in text:
                enemy_name = self._extract_enemy_name(player_text) or "未知敌人"
                return {
                    "trigger": "ambush",
                    "enemy_data": {"name": enemy_name, "role": "怪物"},
                    "enemy_id": f"enemy_{enemy_name}",
                }

        # 敌人出现关键词（敌人主动出现/攻击玩家）
        enemy_appear_keywords = [
            "敌人出现", "怪物出现", "遭遇", "遇到敌人",
            "向我攻击", "朝我冲来", "扑过来", "冲过来",
            "怪物", "遭遇战"
        ]
        for kw in enemy_appear_keywords:
            if kw in text:
                enemy_name = self._extract_enemy_name(player_text) or "未知敌人"
                return {
                    "trigger": "encounter",
                    "enemy_data": {"name": enemy_name, "role": "怪物"},
                    "enemy_id": f"enemy_{enemy_name}",
                }

        return None

    def _extract_enemy_name(self, text: str) -> str | None:
        """
        从文本中提取敌人名称（支持中英文）。

        优先匹配中文敌人名；未匹配到则尝试英文名→中文映射。
        """
        # 1. 匹配中文敌人名
        for name in self.ENEMY_NAMES_CN:
            if name in text:
                return name

        # 2. 尝试英文敌人名 → 映射为中文
        lower_text = text.lower()
        for en_name, cn_name in self.ENEMY_NAME_EN_TO_CN.items():
            if en_name in lower_text:
                return cn_name

        return None

    def _parse_combat_action(self, player_text: str) -> str:
        """
        解析玩家输入为战斗动作

        Returns:
            "attack", "defend", "skill", "item", or "attack" (default)
        """
        text = player_text.lower()

        # 攻击
        attack_keywords = ["攻击", "打", "砍", "揍", "attack", "hit"]
        for kw in attack_keywords:
            if kw in text:
                return "attack"

        # 防御
        defend_keywords = ["防御", "防守", "defend", "block", "盾牌"]
        for kw in defend_keywords:
            if kw in text:
                return "defend"

        # 技能
        skill_keywords = ["技能", "魔法", "spell", "skill", "施展", "使用魔法"]
        for kw in skill_keywords:
            if kw in text:
                return "skill"

        # 道具
        item_keywords = ["道具", "物品", "item", "使用", "药水", "药", "吃"]
        for kw in item_keywords:
            if kw in text:
                return "item"

        # 默认攻击
        return "attack"

    # --------------------------------------------------------------------------
    # 战斗模式 - 核心方法
    # --------------------------------------------------------------------------

    async def _enter_combat(self, player_input: str, enemy_info: dict) -> str:
        """
        进入战斗 - 从探索模式切换到战斗模式

        Args:
            player_input: 玩家输入
            enemy_info: 敌人信息 dict

        Returns:
            叙事文本
        """
        self.mode = GameMode.COMBAT

        # 保存战斗前的场景状态（用于战斗后恢复）
        self._pre_combat_scene = dict(self.current_scene) if self.current_scene else {}
        self._pre_combat_location = self.game_state.get("location", "未知")
        self._pre_combat_narrative = player_input

        enemy_name = enemy_info.get("enemy_data", {}).get("name", "敌人")
        enemy_role = enemy_info.get("enemy_data", {}).get("role", "怪物")
        trigger = enemy_info.get("trigger", "aggressive")
        get_logger().info("game_master", f"=== Combat START: enemy={enemy_name}, role={enemy_role}, trigger={trigger} ===")

        # 创建玩家战斗者（应用装备加成）
        player_stats = self.game_state.get("player_stats", {})
        equip_mgr = get_equipment_manager()
        armor_bonus = equip_mgr.get_armor_bonus()
        max_hp_bonus = equip_mgr.get_max_hp_bonus()
        player = Combatant(
            id="player",
            name="冒险者",
            combatant_type=CombatantType.PLAYER,
            max_hp=player_stats.get("hp", 30) + max_hp_bonus,
            current_hp=player_stats.get("hp", 30) + max_hp_bonus,
            armor_class=player_stats.get("ac", 12) + armor_bonus,
            attack_bonus=equip_mgr.get_attack_bonus(),
            flee_bonus=equip_mgr.get_flee_bonus(),
        )

        # 使用 EnemyFactory 创建敌人
        player_level = self.game_state["player_stats"].get("level", 1)
        location = self.game_state.get("location", "")
        difficulty_str = self.game_state.get("difficulty", "normal")
        difficulty = Difficulty(difficulty_str) if difficulty_str in ("easy", "normal", "hard") else Difficulty.NORMAL
        diff_cfg = DIFFICULTY_SCALING[difficulty]

        # 是否为通用怪物兜底（未知NPC触发的战斗）
        is_generic_fallback = False

        # 尝试用 EnemyFactory 创建（支持新敌人类型）
        # 优先使用 enemy_info 中指定的敌人名称；未知名称才用随机
        try:
            if enemy_name in EnemyFactory.list_templates():
                enemy = EnemyFactory.create_enemy(enemy_name, player_level, difficulty)
                is_generic_fallback = False
            else:
                enemy, is_generic_fallback = EnemyFactory.create_random_enemy(
                    level=player_level, location=location, difficulty=difficulty
                )
            enemy.id = enemy_info.get("enemy_id", enemy.id)
            enemy_hp = enemy.max_hp
            enemy_ac = enemy.armor_class
        except (ValueError, KeyError):
            # Fallback: 使用旧的手动映射方式（也需要应用难度缩放）
            enemy_hp_map = {
                "哥布林": 15, "狼": 12, "骷髅": 18, "史莱姆": 8,
                "巨魔": 35, "巨龙": 50, "龙": 50,
            }
            enemy_ac_map = {
                "哥布林": 10, "狼": 11, "骷髅": 12, "史莱姆": 8,
                "巨魔": 14, "巨龙": 18, "龙": 18,
            }
            base_enemy_hp = enemy_hp_map.get(enemy_name, 20)
            base_enemy_ac = enemy_ac_map.get(enemy_name, 10)

            # 等级缩放 + 难度缩放
            scale_factor = 1.0 + (player_level - 1) * 0.15
            enemy_hp = max(1, int(base_enemy_hp * scale_factor * diff_cfg["hp_mult"]))
            enemy_ac = base_enemy_ac + (player_level - 1)

            enemy = Combatant(
                id=enemy_info.get("enemy_id", "enemy_1"),
                name=enemy_name,
                combatant_type=CombatantType.ENEMY,
                max_hp=enemy_hp,
                current_hp=enemy_hp,
                armor_class=enemy_ac,
                attack_bonus=3,
                description=f"{enemy_role}，{enemy_name}",
            )
            enemy.damage_base = 3
            enemy.damage_dice = 6
            enemy.damage_mult = diff_cfg["damage_mult"]
            enemy.special_ability = "normal"
            is_generic_fallback = True

        # 保存敌人名称（用于奖励系统）
        self._last_enemy_name = enemy.name

        # 沉浸式战斗开始叙事
        if is_generic_fallback:
            # 未知NPC触发战斗，使用场景通用怪物
            unexpected_intro = [
                f"就在你准备动手的瞬间，空气中弥漫起一股危险的气息——一个不速之客突然出现！",
                f"战斗一触即发！但从阴影中出现的并非你预期的对手……",
                f"你攻击了，但回应你的不是那个NPC——一头野兽从暗处扑出！",
            ]
            narrative = "\n" + random.choice(unexpected_intro) + "\n"
        elif trigger == "ambush":
            start_narratives = [
                f"你还没反应过来，一阵阴风袭来——{enemy.name}突然从暗处扑出！",
                f"危险！你被{enemy.name}偷袭了！",
            ]
            narrative = "\n" + random.choice(start_narratives) + "\n"
        else:
            start_narratives = [
                f"你抽出武器，{enemy.name}也亮出了獠牙。剑拔弩张！",
                f"{enemy.name}发出低沉的咆哮，挡住了你的去路——战斗不可避免！",
                f"你的攻击激怒了{enemy.name}，它转身迎战，眼中满是杀意！",
            ]
            narrative = "\n" + random.choice(start_narratives) + "\n"

        # 开始战斗
        import uuid
        combat_id = f"combat_{uuid.uuid4().hex[:8]}"
        await self.combat.start_combat(combat_id, [player, enemy])

        # 战斗信息展示
        narrative += f"\n{'='*40}\n"
        narrative += f"⚔️  战斗开始！\n"
        narrative += f"{'='*40}\n"
        narrative += f"敌人: {enemy.name} ({enemy_role})\n"
        narrative += f"HP: {enemy_hp} | AC: {enemy_ac}\n"
        narrative += f"\n你的状态: HP {player.current_hp}/{player.max_hp} | AC {player.armor_class}\n"
        narrative += f"{'='*40}\n"
        narrative += "可用动作: 攻击 / 防御 / 技能 / 道具 / 逃跑\n"

        return narrative

    async def _try_flee(self, player_text: str, turn: int) -> str:
        """尝试逃跑（兼容旧调用）"""
        return await self._execute_flee(turn)

    # --------------------------------------------------------------------------
    # 主输入处理
    # --------------------------------------------------------------------------

    async def _on_player_input(self, event: Event):
        """处理玩家输入"""
        player_text = event.data.get("text", "")
        logger.info(f"GameMaster: processing player input: {player_text[:50]}...")

        self.game_state["turn"] += 1
        turn = self.game_state["turn"]

        await self.hooks.trigger(HookNames.BEFORE_INPUT_PROCESSING, event)

        if self.mode == GameMode.COMBAT:
            narrative = await self._handle_combat_input(player_text, turn)
        else:
            narrative = await self._handle_exploration_input(player_text, turn)

        await self.event_bus.publish(Event(
            type=EventType.NARRATIVE_OUTPUT,
            data={
                "text": narrative,
                "turn": turn,
                "scene": self.current_scene,
                "mode": self.mode,
            },
            source=self._subscriber_id
        ))

        await self.hooks.trigger(HookNames.AFTER_NARRATIVE_OUTPUT, event)

    # --------------------------------------------------------------------------
    # 系统命令内联处理（不走 LLM）
    # --------------------------------------------------------------------------

    def _check_system_command(self, player_text: str) -> str | None:
        """
        检查并处理系统命令，优先于 LLM 叙事生成。

        Windows 环境下不使用 .lower() 做中文匹配，直接用原始字符串比较。

        Returns:
            命令响应的叙事文本，如果未匹配任何命令则返回 None
        """
        text = player_text.strip()

        # === 状态命令：状态 / status ===
        if text in ("状态", "status", "查看状态"):
            return self._format_status()

        # === 背包命令：背包 / inventory ===
        if text in ("背包", "inventory", "背包列表", "物品"):
            return self._format_inventory()

        # === 商店命令：商店 / shop ===
        if text in ("商店", "shop", "商店列表", "商品"):
            return self._format_shop()

        # === 任务命令：任务 / quest ===
        if text in ("任务", "quest", "任务详情"):
            return self._format_quest()

        # === 帮助命令：帮助 / help ===
        if text in ("帮助", "help", "帮助信息", "?"):
            return self._format_help()

        return None

    def _format_status(self) -> str:
        """格式化玩家状态输出"""
        stats = self.game_state["player_stats"]
        location = self.game_state.get("location", "未知")
        turn = self.game_state.get("turn", 0)
        mode = self.mode
        mode_display = {
            "exploration": "探索模式",
            "combat": "战斗模式",
            "dialogue": "对话模式",
        }.get(mode, mode)

        items = stats.get("inventory", [])

        lines = []
        lines.append(f"\n{'='*50}")
        lines.append(f"📊 回合 {turn}  |  📍 {location}  |  🎮 {mode_display}")
        lines.append(f"{'-'*50}")
        lines.append(f"❤️  HP: {stats['hp']}/{stats['max_hp']}  🛡️ AC: {stats['ac']}  ⚔️ Lv.{stats['level']}")
        lines.append(f"🌟 XP: {stats['xp']}  🪙 Gold: {stats['gold']}  🎒 物品: {len(items)} 件")

        char_name = stats.get("name", "")
        if char_name:
            race = stats.get("race", "")
            class_ = stats.get("class", "")
            lines.append(f"🧙 角色: {char_name}  {race} {class_}")

        if items:
            item_names = [it.get("name", "?") for it in items[-5:]]
            lines.append(f"   近来获得: {', '.join(item_names)}")
        lines.append(f"{'='*50}")
        return "\n".join(lines)

    def _format_inventory(self) -> str:
        """格式化背包物品输出"""
        stats = self.game_state["player_stats"]
        items = stats.get("inventory", [])
        gold = stats.get("gold", 0)

        rarity_names = {
            "common": "普通",
            "uncommon": "优秀",
            "rare": "稀有",
            "epic": "史诗",
            "legendary": "传说",
        }
        rarity_icons = {
            "common": "",
            "uncommon": "✨",
            "rare": "💎",
            "epic": "🔮",
            "legendary": "🌟",
        }

        lines = []
        lines.append(f"\n{'='*50}")
        lines.append(f"🎒 背包")
        lines.append(f"{'='*50}")
        lines.append(f"💰 金币: {gold}")
        lines.append(f"{'-'*50}")

        if not items:
            lines.append("  背包空空如也，快去收集些物品吧！")
        else:
            lines.append(f"  共 {len(items)} 件物品：")
            for it in items:
                name = it.get("name", "?")
                rarity = it.get("rarity", "common")
                icon = rarity_icons.get(rarity, "")
                rarity_label = rarity_names.get(rarity, "普通")
                lines.append(f"  • {name} {icon} ({rarity_label})")
        lines.append(f"{'='*50}")
        return "\n".join(lines)

    def _format_shop(self) -> str:
        """格式化商店物品列表输出"""
        from .item_system import get_item_registry

        stats = self.game_state.get("player_stats", {})
        gold = stats.get("gold", 0)

        registry = get_item_registry()
        all_items = registry.get_all()

        type_names = {
            "consumable": "消耗品",
            "weapon": "武器",
            "armor": "防具",
            "accessory": "饰品",
            "quest": "任务物品",
            "misc": "杂物",
        }
        rarity_names = {
            "common": "普通",
            "uncommon": "优秀",
            "rare": "稀有",
            "epic": "史诗",
            "legendary": "传说",
        }
        rarity_colors = {
            "common": "灰色",
            "uncommon": "绿色",
            "rare": "蓝色",
            "epic": "紫色",
            "legendary": "橙色",
        }

        purchasable = [it for it in all_items if not it.is_quest_item and it.price > 0]

        lines = []
        lines.append(f"\n{'='*50}")
        lines.append(f"🏪 商店 - 月光杂货铺")
        lines.append(f"{'='*50}")
        lines.append(f"💰 你的金币: {gold}")
        lines.append(f"{'-'*50}")

        if not purchasable:
            lines.append("  暂无商品")
        else:
            for item in purchasable:
                rarity_str = rarity_colors.get(item.rarity.value, "灰色")
                type_str = type_names.get(item.item_type.value, "杂物")
                effect_desc = ""
                for effect in item.effects:
                    if effect.effect_type.value == "heal":
                        effect_desc = f" 恢复 {effect.value} HP"
                    elif effect.effect_type.value == "damage":
                        effect_desc = f" 造成 {effect.value} 伤害"
                    elif effect.effect_type.value == "buff_defense":
                        effect_desc = f" 防御 +{effect.value}"
                    elif effect.effect_type.value == "buff_speed":
                        effect_desc = f" 速度 +{effect.value}"
                    elif effect.effect_type.value == "debuff":
                        effect_desc = f" 减益"
                    elif effect.effect_type.value == "cure":
                        effect_desc = f" 解除异常"
                    else:
                        effect_desc = f" 效果 {effect.value}"

                can_afford = gold >= item.price
                afford_str = "" if can_afford else " [金币不足]"
                lines.append(f"  • {item.name} ({rarity_str})")
                lines.append(f"    类型: {type_str} | 价格: {item.price} 金币{afford_str}")
                if effect_desc:
                    lines.append(f"    效果:{effect_desc}")

        lines.append(f"{'-'*50}")
        lines.append(f"💡 输入「买 + 物品名」即可购买（如：买治疗药水）")
        lines.append(f"{'='*50}")
        return "\n".join(lines)

    async def _handle_shop_command(self, raw_input: str) -> str:
        """
        处理商店购买命令。

        优先级高于战斗状态判断——确保 Buy-Potion 在战斗结束后
        能正确路由到购买叙事而非防御叙事。
        """
        from .item_system import get_item_registry

        stats = self.game_state.get("player_stats", {})
        gold = stats.get("gold", 0)
        inventory = stats.get("inventory", [])

        registry = get_item_registry()
        all_items = registry.get_all()
        purchasable = [it for it in all_items if not it.is_quest_item and it.price > 0]

        # 从输入中提取物品名称
        item_name = None
        raw = raw_input.strip()
        # 去掉"买"字，尝试匹配剩余部分
        for kw in ["买", "购买", "shop", "shopping", "buy"]:
            if kw in raw:
                rest = raw.replace(kw, "").strip()
                if rest:
                    item_name = rest
                    break

        if not item_name:
            # 没有指定物品，显示商店列表
            return self._format_shop()

        # 模糊匹配物品
        matched_item = None
        for item in purchasable:
            if item_name in item.name or item.name in item_name:
                matched_item = item
                break

        if matched_item is None:
            return f"\n⚠️ 商店里没有「{item_name}」这种商品。\n请查看商店列表：输入「商店」查看所有商品。"

        # 检查金币是否足够
        if gold < matched_item.price:
            return (f"\n⚠️ 你的金币不足！\n"
                    f"  「{matched_item.name}」需要 {matched_item.price} 金币，"
                    f"你只有 {gold} 金币。\n"
                    f"击败敌人或完成任务来赚取金币吧！")

        # 执行购买
        gold -= matched_item.price
        inventory.append({
            "name": matched_item.name,
            "item_id": matched_item.id,
            "rarity": matched_item.rarity.value,
        })
        stats["gold"] = gold
        stats["inventory"] = inventory

        # 记录购买选择
        self._record_choice("item", f"购买{matched_item.name}", f"花费{matched_item.price}金币")

        # 生成购买叙事
        effect_lines = []
        for effect in matched_item.effects:
            if effect.effect_type.value == "heal":
                effect_lines.append(f"恢复 {effect.value} HP")
            elif effect.effect_type.value == "damage":
                effect_lines.append(f"造成 {effect.value} 伤害")
            elif effect.effect_type.value == "buff_defense":
                effect_lines.append(f"防御 +{effect.value}")
            elif effect.effect_type.value == "buff_speed":
                effect_lines.append(f"速度 +{effect.value}")
            elif effect.effect_type.value == "cure":
                effect_lines.append("解除异常状态")
            else:
                effect_lines.append(f"效果 {effect.value}")

        effect_str = "；".join(effect_lines) if effect_lines else "特殊效果"
        rarity_icons = {
            "common": "",
            "uncommon": " ✨",
            "rare": " 💎",
            "epic": " 🔮",
            "legendary": " 🌟",
        }
        icon = rarity_icons.get(matched_item.rarity.value, "")

        return (f"\n✅ 购买成功！\n"
                f"  你花费了 {matched_item.price} 金币购买了「{matched_item.name}」{icon}。\n"
                f"  效果：{effect_str}\n"
                f"  剩余金币：{gold}")

    def _format_quest(self) -> str:
        """格式化任务详情输出"""
        from .quest_state import QuestStage, QUEST_NAME

        lines = []
        lines.append(f"\n{'='*50}")
        lines.append(f"📜 任务详情")
        lines.append(f"{'='*50}")

        if not self.quest_state.is_active():
            if self.quest_state.stage == QuestStage.QUEST_COMPLETE:
                lines.append(f"🎉 主线任务「{QUEST_NAME}」已完成！")
                lines.append("  感谢你的冒险，期待下次旅程。")
            else:
                lines.append("❗ 当前没有进行中的任务。")
                lines.append("  探索世界，与NPC交谈，或许能发现新的任务。")
            lines.append(f"{'='*50}")
            return "\n".join(lines)

        quest_info = self.quest_state.get_quest_info()
        lines.append(f"📖 主线：{quest_info['name']}")
        lines.append(f"📍 阶段：{quest_info['stage_display']}")
        lines.append(f"{'-'*50}")
        lines.append(f"💡 {quest_info['hint']}")

        stages = [
            (QuestStage.FIND_MAYOR, "寻找镇长"),
            (QuestStage.TALK_TO_MAYOR, "与镇长对话"),
            (QuestStage.GO_TO_TAVERN, "前往酒馆"),
            (QuestStage.GATHER_INFO, "打听情报"),
            (QuestStage.GO_TO_FOREST, "进入森林"),
            (QuestStage.DEFEAT_MONSTER, "击败影狼"),
            (QuestStage.RETURN_TO_MAYOR, "回报镇长"),
        ]

        lines.append(f"{'-'*50}")
        lines.append("📋 任务进度：")
        current_stage = self.quest_state.stage
        for stage_enum, stage_name in stages:
            if stage_enum == current_stage:
                marker = "👉"
            elif stage_enum.value in self.quest_state.quest_log:
                marker = "✅"
            else:
                marker = "⬜"
            lines.append(f"  {marker} {stage_name}")

        if self.quest_state.quest_log:
            lines.append(f"\n  已完成阶段数: {len(self.quest_state.quest_log)}/{len(stages)}")

        lines.append(f"{'='*50}")

        if current_stage == QuestStage.NOT_STARTED:
            lines.append("💡 输入「接受任务」开始主线任务！")
        elif current_stage == QuestStage.DEFEAT_MONSTER:
            lines.append("💡 勇敢面对影狼，击败它以完成任务！")
        elif current_stage == QuestStage.QUEST_COMPLETE:
            lines.append("🎉 恭喜完成任务！回去找镇长领取奖励吧！")
        else:
            lines.append("💡 按提示前往目的地，推进任务进度。")

        return "\n".join(lines)

    def _format_help(self) -> str:
        """格式化帮助信息输出"""
        lines = []
        lines.append(f"\n{'='*50}")
        lines.append(f"📖 命令帮助")
        lines.append(f"{'='*50}")
        lines.append("【系统命令】")
        lines.append("  status / 状态   - 查看当前状态")
        lines.append("  inventory / 背包 - 查看背包物品")
        lines.append("  shop / 商店      - 查看商店商品")
        lines.append("  quest / 任务    - 查看任务进度")
        lines.append("  help / 帮助      - 显示此帮助")
        lines.append(f"{'='*50}")
        lines.append("【游戏命令】")
        lines.append("  自由输入你的行动，DM 会为你叙述结果")
        lines.append("  示例：")
        lines.append("    · 我走进酒馆")
        lines.append("    · 我和酒馆老板说话")
        lines.append("    · 攻击哥布林")
        lines.append("    · 我使用治疗药水")
        lines.append("    · 我防御")
        lines.append(f"{'='*50}")
        return "\n".join(lines)

    # --------------------------------------------------------------------------
    # 探索模式 - 核心方法
    # --------------------------------------------------------------------------

    async def _handle_exploration_input(self, player_text: str, turn: int) -> str:
        """处理探索模式下的玩家输入"""

        # ========== 0. 命令归一化 ==========
        _norm = self._normalize_command(player_text)
        cmd_type = _norm.get("cmd_type")
        params = _norm.get("params", {})

        # 如果归一化命中了 NPC 对话命令，直接路由
        if cmd_type in ("npc_talk", "npc_quest", "npc_chat"):
            return await self._handle_npc_command(cmd_type, params)

        # ========== 场景切换时强制重置战斗状态 ==========
        if self._is_location_change_command(player_text):
            self._clear_combat_state()

        # === 0. 系统命令内联处理（优先于所有 LLM 处理） ===
        system_response = self._check_system_command(player_text)
        if system_response:
            return system_response

        # ========== 商店/购买命令（优先级高于战斗状态判断）============
        if self._is_shop_command(player_text):
            return await self._handle_shop_command(player_text)

        narrative_parts = []

        # 0.5 检查探索指令（look/search/move/talk - 显式探索命令优先检测）
        explore_response = await self._check_exploration_command(player_text, turn)
        if explore_response:
            return explore_response

        # 1. 检查是否需要场景更新
        scene_update = await self._check_scene_update(player_text)
        if scene_update:
            narrative_parts.append(scene_update)

        # 2. 检查是否有 NPC 对话
        npc_response = await self._check_npc_interaction(player_text)
        if npc_response:
            narrative_parts.append(npc_response)

        # 3. 检查场景物品交互（检查/拾取/使用）
        object_response = await self._check_object_interaction(player_text)
        if object_response:
            narrative_parts.append(object_response)

        # 3.5 检查任务触发（对话/场景相关的任务阶段推进）
        quest_advance = await self._check_quest_trigger(player_text, npc_response)
        if quest_advance:
            narrative_parts.insert(0, quest_advance)

        # 4. 检查是否触发战斗
        combat_trigger = self._check_combat_trigger(player_text)
        if combat_trigger:
            combat_narrative = await self._enter_combat(player_text, combat_trigger)
            narrative_parts.append(combat_narrative)

        # 5. 生成主叙事
        main_narrative = await self._generate_main_narrative(player_text, turn)
        narrative_parts.append(main_narrative)

        return "\n\n".join(filter(None, narrative_parts))

    async def _handle_combat_input(self, player_text: str, turn: int) -> str:
        """处理战斗模式下的玩家输入"""
        # 检查玩家是否眩晕
        combat = self.combat.get_active_combat()
        if combat:
            player = combat.combatants.get("player")
            if player and player.status.value == "stunned":
                player.status = StatusEffect.NORMAL
                narrative = f"[回合 {turn}] 你被眩晕了,头晕目眩,无法行动!"
                # 敌人仍然攻击
                enemies = [c for c in combat.get_active_combatants() if c.combatant_type == CombatantType.ENEMY]
                if enemies and enemies[0].is_active:
                    enemy_result = await self._execute_enemy_turn(enemies[0], turn)
                    narrative += "\n\n" + enemy_result
                narrative += self._format_combat_status()
                return narrative
        
        action = self._parse_combat_action(player_text)

        # 逃跑
        if "逃跑" in player_text or "flee" in player_text.lower():
            return await self._execute_flee(turn)

        # 防御
        if action == "defend":
            return await self._execute_defend(turn)

        # 攻击
        if action == "attack":
            narrative = await self._execute_player_attack(turn)
            return narrative

        # 技能
        if action == "skill":
            return await self._execute_skill(player_text, turn)

        # 道具
        if action == "item":
            return await self._execute_item(player_text, turn)

        return f"[回合 {turn}] 你犹豫了一下..."

    def _format_combat_status(self) -> str:
        """格式化战斗状态显示"""
        combat = self.combat.get_active_combat()
        if not combat:
            return ""

        # 使用 combat_system 的集中化状态 emoji 映射
        from .combat_system import get_status_emoji

        lines = ["\n【战斗状态】"]
        for c in combat.get_active_combatants():
            hp_bar = self._make_hp_bar(c.current_hp, c.max_hp)
            type_icon = "🗡️" if c.combatant_type == CombatantType.ENEMY else "⚔️"
            status_icon = get_status_emoji(c.status)
            status_str = f" {status_icon}" if status_icon else ""
            lines.append(f"  {type_icon} {c.name}: {hp_bar} {c.current_hp}/{c.max_hp} HP{status_str}")
        
        enemies = [c for c in combat.get_active_combatants() if c.combatant_type == CombatantType.ENEMY]
        if enemies:
            enemy = enemies[0]
            lines.append(f"\n  敌人状态: {enemy.name}")
            lines.append(f"  HP: {enemy.current_hp}/{enemy.max_hp} | AC: {enemy.armor_class}")

        return "\n".join(lines)

    def _make_hp_bar(self, current: int, maximum: int, length: int = 10) -> str:
        """生成 ASCII HP 条"""
        filled = int((current / maximum) * length)
        empty = length - filled
        bar = "█" * filled + "░" * empty
        return f"[{bar}]"

    async def _execute_player_attack(self, turn: int) -> str:
        """执行玩家攻击"""
        combat = self.combat.get_active_combat()
        if not combat:
            return f"[回合 {turn}] 当前不在战斗中。"

        # 记录战斗选择
        enemies = [c for c in combat.get_active_combatants() if c.combatant_type == CombatantType.ENEMY]
        enemy_name = enemies[0].name if enemies else "敌人"
        self._record_choice("combat", f"攻击{enemy_name}", f"回合{turn}")

        enemies = [c for c in combat.get_active_combatants() if c.combatant_type == CombatantType.ENEMY]
        if not enemies:
            return f"[回合 {turn}] 没有敌人了。"

        player = combat.combatants.get("player")
        enemy = enemies[0]
        roll = random.randint(1, 20)
        attack_roll = roll + player.attack_bonus  # 玩家 attack_bonus（含装备加成）

        hit = attack_roll >= enemy.armor_class
        damage = 0
        if hit:
            damage = random.randint(1, 6) + player.attack_bonus  # 1d6 + attack_bonus
            actual_damage = enemy.take_damage(damage)
            damage = actual_damage  # 使用实际伤害（不会超过当前HP）

        # 用 LLM 生成沉浸式战斗叙事
        narrative = await self._generate_combat_narrative(
            attacker_name="你",
            target_name=enemy.name,
            action="attack",
            hit=hit,
            damage=damage,
            attack_roll=attack_roll,
            target_ac=enemy.armor_class,
            target_hp=enemy.current_hp,
            target_max_hp=enemy.max_hp,
            turn=turn,
        )

        # 检查敌人是否被击败
        if not enemy.is_active:
            narrative += "\n\n⚔️ {} 倒下了！".format(enemy.name)
            # 敌人不反击，直接结束战斗
            await self._end_combat("players")
            narrative += self._format_combat_status()
            return narrative

        # 敌人反击（如果还活着）
        if enemy.is_active and self.mode == GameMode.COMBAT:
            enemy_result = await self._execute_enemy_turn(enemy, turn)
            narrative += "\n\n" + enemy_result

        # 显示状态
        narrative += self._format_combat_status()

        return narrative

    async def _execute_enemy_turn(self, enemy: Combatant, turn: int) -> str:
        """执行敌人回合 - 带战术AI"""
        combat = self.combat.get_active_combat()
        if not combat:
            return ""

        player = combat.combatants.get("player")
        if not player or not player.is_active:
            return ""

        # ---------- 战术AI:根据HP和状态决定动作 ----------
        hp_percent = enemy.current_hp / enemy.max_hp if enemy.max_hp > 0 else 1.0
        player_hp_percent = player.current_hp / player.max_hp if player.max_hp > 0 else 1.0

        # 低HP时可能防御或逃跑
        enemy_action = "attack"  # 默认攻击
        if hp_percent <= 0.25:
            # 危险：30%概率防御，10%概率尝试逃跑
            roll = random.randint(1, 10)
            if roll <= 3:
                enemy_action = "defend"
            elif roll == 4:
                enemy_action = "flee"
        elif hp_percent <= 0.5:
            # 受伤：15%概率防御
            if random.randint(1, 10) <= 2:
                enemy_action = "defend"

        # 敌人使用防御
        if enemy_action == "defend":
            enemy.apply_status(StatusEffect.DEFENDING)
            narrative = f"【{enemy.name} 战术】{enemy.name}受了伤，摆出防御姿态，蓄势待发！"
            narrative += self._format_combat_status()
            return narrative

        # 敌人尝试逃跑（借机攻击失效）
        if enemy_action == "flee":
            flee_roll = random.randint(1, 20)
            if flee_roll >= 14:  # 敌人逃跑更难（需要14+）
                # 敌人逃跑成功，战斗以敌人逃跑结束
                narrative = f"【{enemy.name} 战术】{enemy.name}看到形势不利，试图逃跑！"
                narrative += f"\n🎲 逃跑检定: {flee_roll} vs 14 = 成功！"
                await self._end_combat("players", reason="敌人逃跑")
                return narrative + "\n" + self._format_combat_status()
            else:
                narrative = f"【{enemy.name} 战术】{enemy.name}试图逃跑，但被拦截！\n"
                narrative += f"🎲 逃跑检定: {flee_roll} vs 14 = 失败！\n"

        # ---------- 正常攻击 ----------
        roll = random.randint(1, 20)
        enemy_atk_bonus = getattr(enemy, 'attack_bonus', 3)
        attack_roll = roll + enemy_atk_bonus

        # 防御姿态:玩家AC+3
        effective_ac = player.armor_class
        is_defending = player.status.value == "defending"
        if is_defending:
            effective_ac += 3

        hit = attack_roll >= effective_ac
        damage = 0
        if hit:
            enemy_dice = getattr(enemy, 'damage_dice', 6)
            enemy_base = getattr(enemy, 'damage_base', 1)
            damage = random.randint(1, enemy_dice) + enemy_base
            actual_damage = player.take_damage(damage)
            damage = actual_damage
            if is_defending:
                player.status = StatusEffect.NORMAL
        elif is_defending:
            player.status = StatusEffect.NORMAL

        # 检查玩家是否倒下
        if not player.is_active:
            self.game_over = True
            self.game_state["game_over"] = True
            await self._end_combat("enemies")
            return f"[回合 {turn}] 你倒下了！战斗结束..."

        # 用 LLM 生成敌人反击叙事
        action_name = "counter_attack" if enemy_action == "attack" else "counter_attack"
        narrative_text = await self._generate_combat_narrative(
            attacker_name=enemy.name,
            target_name="你",
            action=action_name,
            hit=hit,
            damage=damage,
            attack_roll=attack_roll,
            target_ac=player.armor_class,
            target_hp=player.current_hp,
            target_max_hp=player.max_hp,
            turn=turn,
        )

        return narrative_text

    async def _end_combat(self, winner: str, reason: str = "敌人被击败"):
        """主动结束战斗"""
        if self.mode != GameMode.COMBAT:
            return
        await self.combat.end_combat(reason=reason)

    # --------------------------------------------------------------------------
    # 防御/技能/道具/逃跑 - LLM 叙事生成
    # --------------------------------------------------------------------------

    async def _execute_defend(self, turn: int) -> str:
        """执行防御动作"""
        combat = self.combat.get_active_combat()
        if not combat:
            return f"[回合 {turn}] 当前不在战斗中。"

        # 记录防御选择
        enemies = [c for c in combat.get_active_combatants() if c.combatant_type == CombatantType.ENEMY]
        enemy_name = enemies[0].name if enemies else "敌人"
        self._record_choice("skill", "防御", f"回合{turn}对{enemy_name}")

        # 提交防御动作到战斗系统
        from .combat_system import CombatAction, ActionType
        action = CombatAction(
            combatant_id="player",
            action_type=ActionType.DEFEND,
        )
        await self.combat.submit_action("player", action)

        # 获取敌人用于叙事
        enemies = [c for c in combat.get_active_combatants() if c.combatant_type == CombatantType.ENEMY]
        enemy = enemies[0] if enemies else None
        enemy_name = enemy.name if enemy else "敌人"

        # 生成防御叙事
        narrative = await self._generate_defend_narrative(enemy_name, turn)
        narrative += self._format_combat_status()

        # 敌人回合
        if enemy and enemy.is_active and self.mode == GameMode.COMBAT:
            enemy_result = await self._execute_enemy_turn(enemy, turn)
            narrative += "\n\n" + enemy_result

        return narrative

    async def _execute_skill(self, player_text: str, turn: int) -> str:
        """
        执行技能动作 - 根据玩家输入选择技能

        技能表:
        - 魔法攻击 / 火球: 2d6 伤害
        - 治疗: 恢复 2d4 HP
        - 重击: 3d6 伤害（命中-3惩罚）
        - 眩晕: 1d6 伤害 + 敌人跳过下回合（50%概率）
        """
        combat = self.combat.get_active_combat()
        if not combat:
            return f"[回合 {turn}] 当前不在战斗中。"

        enemies = [c for c in combat.get_active_combatants() if c.combatant_type == CombatantType.ENEMY]
        enemy = enemies[0] if enemies else None
        enemy_name = enemy.name if enemy else "未知敌人"
        player = combat.combatants.get("player")

        import random

        # 根据玩家输入解析技能类型
        text = player_text.lower()
        if any(kw in text for kw in ["治疗", "恢复", "heal"]):
            skill_name = "治疗术"
            self._record_choice("skill", skill_name, f"回合{turn}")
            heal = random.randint(1, 4) + random.randint(1, 4)
            if player:
                old_hp = player.current_hp
                player.current_hp = min(player.max_hp, player.current_hp + heal)
                actual_heal = player.current_hp - old_hp
            else:
                actual_heal = 0

            narrative = await self._generate_skill_narrative(
                skill_name=skill_name,
                target_name="你",
                damage=-actual_heal,
                hit=True,
                target_hp=player.current_hp if player else 0,
                target_max_hp=player.max_hp if player else 1,
                turn=turn,
            )
            narrative += self._format_combat_status()
            # 治疗后敌人仍可反击
            if enemy and enemy.is_active and self.mode == GameMode.COMBAT:
                enemy_result = await self._execute_enemy_turn(enemy, turn)
                narrative += "\n\n" + enemy_result
            return narrative

        elif any(kw in text for kw in ["重击", "猛击", "power"]):
            skill_name = "重击"
            self._record_choice("skill", skill_name, f"回合{turn}")
            # 重击: 3d6 但AC-3（更难命中）
            roll = random.randint(1, 20)
            attack_roll = roll - 3 + 5  # 玩家 attack_bonus=5, -3命中惩罚
            hit = True
            if enemy:
                effective_ac = enemy.armor_class
                if enemy.status == StatusEffect.DEFENDING:
                    effective_ac += 3
                hit = roll + 5 - 3 >= effective_ac or roll == 20

            damage = 0
            if hit:
                damage = random.randint(1, 6) + random.randint(1, 6) + random.randint(1, 6)
                if enemy:
                    actual_damage = enemy.take_damage(damage)
                    damage = actual_damage
            else:
                if enemy and enemy.status == StatusEffect.DEFENDING:
                    enemy.status = StatusEffect.NORMAL

            if enemy and not enemy.is_active:
                narrative = await self._generate_skill_narrative(
                    skill_name=skill_name,
                    target_name=enemy_name,
                    damage=damage,
                    hit=hit,
                    target_hp=0,
                    target_max_hp=enemy.max_hp if enemy else 1,
                    turn=turn,
                )
                narrative += f"\n\n⚔️ {enemy_name} 倒下了！"
                await self._end_combat("players")
                narrative += self._format_combat_status()
                return narrative

            narrative = await self._generate_skill_narrative(
                skill_name=skill_name,
                target_name=enemy_name,
                damage=damage,
                hit=hit,
                target_hp=enemy.current_hp if enemy else 0,
                target_max_hp=enemy.max_hp if enemy else 1,
                turn=turn,
            )

            if enemy and enemy.is_active and self.mode == GameMode.COMBAT:
                enemy_result = await self._execute_enemy_turn(enemy, turn)
                narrative += "\n\n" + enemy_result
            narrative += self._format_combat_status()
            return narrative

        elif any(kw in text for kw in ["眩晕", "晕", "stun"]):
            skill_name = "眩晕术"
            self._record_choice("skill", skill_name, f"回合{turn}")
            # 眩晕术: 1d6 伤害 + 50%几率眩晕敌人
            damage = random.randint(1, 6)
            stun_effect = random.randint(1, 2) == 1  # 50%
            if enemy:
                actual_damage = enemy.take_damage(damage)
                damage = actual_damage
                if stun_effect and enemy.is_active:
                    enemy.apply_status(StatusEffect.STUNNED)

            if enemy and not enemy.is_active:
                narrative = await self._generate_skill_narrative(
                    skill_name=skill_name,
                    target_name=enemy_name,
                    damage=damage,
                    hit=True,
                    target_hp=0,
                    target_max_hp=enemy.max_hp if enemy else 1,
                    turn=turn,
                )
                narrative += f"\n\n⚔️ {enemy_name} 倒下了！"
                await self._end_combat("players")
                narrative += self._format_combat_status()
                return narrative

            stun_msg = f" 并陷入眩晕状态（下回合无法行动）！" if stun_effect else "！"
            narrative = await self._generate_skill_narrative(
                skill_name=skill_name,
                target_name=enemy_name,
                damage=damage,
                hit=True,
                target_hp=enemy.current_hp if enemy else 0,
                target_max_hp=enemy.max_hp if enemy else 1,
                turn=turn,
            )
            narrative = narrative + f"\n✨ 眩晕效果:{enemy_name}{stun_msg}" if stun_effect else narrative

            if enemy and enemy.is_active and self.mode == GameMode.COMBAT:
                enemy_result = await self._execute_enemy_turn(enemy, turn)
                narrative += "\n\n" + enemy_result
            narrative += self._format_combat_status()
            return narrative

        else:
            # 默认: 魔法攻击 2d6
            skill_name = "魔法攻击"
            self._record_choice("skill", skill_name, f"回合{turn}")
            damage = random.randint(1, 6) + random.randint(1, 6)
            hit = True

            if enemy:
                actual_damage = enemy.take_damage(damage)
                damage = actual_damage

            # 检查敌人是否被击败
            if enemy and not enemy.is_active:
                narrative = await self._generate_skill_narrative(
                    skill_name=skill_name,
                    target_name=enemy_name,
                    damage=damage,
                    hit=hit,
                    target_hp=0,
                    target_max_hp=enemy.max_hp if enemy else 1,
                    turn=turn,
                )
                narrative += f"\n\n⚔️ {enemy_name} 倒下了！"
                await self._end_combat("players")
                narrative += self._format_combat_status()
                return narrative

            # 生成默认技能叙事
            narrative = await self._generate_skill_narrative(
                skill_name=skill_name,
                target_name=enemy_name,
                damage=damage,
                hit=hit,
                target_hp=enemy.current_hp if enemy else 0,
                target_max_hp=enemy.max_hp if enemy else 1,
                turn=turn,
            )

        # 敌人反击
        if enemy and enemy.is_active and self.mode == GameMode.COMBAT:
            enemy_result = await self._execute_enemy_turn(enemy, turn)
            narrative += "\n\n" + enemy_result

        narrative += self._format_combat_status()
        return narrative

    async def _execute_item(self, player_text: str, turn: int) -> str:
        """执行道具动作"""
        combat = self.combat.get_active_combat()
        if not combat:
            return f"[回合 {turn}] 当前不在战斗中。"

        # 简单道具实现：治疗药水，恢复 2d6 HP
        import random
        heal_amount = random.randint(1, 6) + random.randint(1, 6)

        # 记录道具选择
        self._record_choice("item", "治疗药水", f"回合{turn}")

        player = combat.combatants.get("player")
        if player:
            old_hp = player.current_hp
            player.current_hp = min(player.max_hp, player.current_hp + heal_amount)
            actual_heal = player.current_hp - old_hp

        # 生成道具叙事
        narrative = await self._generate_item_narrative(
            item_name="治疗药水",
            target_name="你",
            heal_amount=actual_heal,
            new_hp=player.current_hp if player else 0,
            max_hp=player.max_hp if player else 1,
            turn=turn,
        )

        # 敌人反击
        enemies = [c for c in combat.get_active_combatants() if c.combatant_type == CombatantType.ENEMY]
        enemy = enemies[0] if enemies else None
        if enemy and enemy.is_active and self.mode == GameMode.COMBAT:
            enemy_result = await self._execute_enemy_turn(enemy, turn)
            narrative += "\n\n" + enemy_result

        narrative += self._format_combat_status()
        return narrative

    async def _execute_flee(self, turn: int) -> str:
        """执行逃跑动作"""
        combat = self.combat.get_active_combat()
        if not combat:
            self.mode = GameMode.EXPLORATION
            return f"[回合 {turn}] 你不在战斗中，直接离开了。"

        enemies = [c for c in combat.get_active_combatants() if c.combatant_type == CombatantType.ENEMY]
        enemy = enemies[0] if enemies else None
        enemy_name = enemy.name if enemy else "敌人"

        # 使用战斗系统的逃跑判定
        from .combat_system import CombatAction, ActionType
        action = CombatAction(
            combatant_id="player",
            action_type=ActionType.FLEE,
        )

        import random
        flee_roll = random.randint(1, 20)
        
        # 检查难度：困难模式下无逃跑加成
        difficulty_str = self.game_state.get("difficulty", "normal")
        difficulty = Difficulty(difficulty_str) if difficulty_str in ("easy", "normal", "hard") else Difficulty.NORMAL
        diff_cfg = DIFFICULTY_SCALING[difficulty]
        
        if diff_cfg["flee_bonus"]:
            # 有逃跑加成：装备提供的 flee_bonus 是百分比
            flee_bonus = get_equipment_manager().get_flee_bonus()
            flee_threshold = max(2, 10 - (flee_bonus // 5))
        else:
            # 困难模式：无逃跑加成
            flee_threshold = 10
        flee_success = flee_roll >= flee_threshold

        # 记录逃跑选择
        self._record_choice("combat", "逃跑", f"回合{turn}逃离{enemy_name}")

        if flee_success:
            self.mode = GameMode.EXPLORATION
            # 恢复场景
            if self._pre_combat_scene is not None:
                self.current_scene = self._pre_combat_scene
                self.game_state["location"] = self._pre_combat_location
            narrative = f"[回合 {turn}] 你转身逃跑！{enemy_name}的追击落了空。"
            narrative += "\n\n你成功脱离了战斗。"
            # 清理预保存状态
            self._pre_combat_scene = None
            self._pre_combat_location = "未知"
            self._pre_combat_narrative = ""
        else:
            # 逃跑失败 - 生成叙事
            narrative = await self._generate_flee_fail_narrative(enemy_name, turn)
            # 敌人反击（借机攻击）
            if enemy and enemy.is_active:
                enemy_result = await self._execute_enemy_turn(enemy, turn)
                narrative += "\n\n" + enemy_result

        narrative += self._format_combat_status()
        return narrative

    # --------------------------------------------------------------------------
    # LLM 战斗叙事生成
    # --------------------------------------------------------------------------

    async def _generate_combat_narrative(
        self,
        attacker_name: str,
        target_name: str,
        action: str,
        hit: bool,
        damage: int,
        attack_roll: int,
        target_ac: int,
        target_hp: int,
        target_max_hp: int,
        turn: int,
    ) -> str:
        """
        使用 LLM 生成沉浸式战斗叙事

        Args:
            attacker_name: 攻击者名称
            target_name: 目标名称
            action: 动作类型 (attack, counter_attack, skill, etc.)
            hit: 是否命中
            damage: 造成的伤害
            attack_roll: 攻击投掷结果
            target_ac: 目标护甲等级
            target_hp: 目标当前HP
            target_max_hp: 目标最大HP
            turn: 当前回合

        Returns:
            沉浸式战斗叙事文本
        """
        get_logger().debug("game_master", f"LLM API call: _generate_combat_narrative (attacker={attacker_name}, target={target_name}, action={action}, hit={hit}, damage={damage}, turn={turn})")
        # 构建战斗上下文
        combat = self.combat.get_active_combat()
        scene_desc = self._pre_combat_scene.get("description", "激烈战斗正在进行") if self._pre_combat_scene else "激烈战斗正在进行"
        location = self._pre_combat_location or "未知地点"

        hp_percent = (target_hp / target_max_hp * 100) if target_max_hp > 0 else 0
        if hp_percent > 66:
            hp_status = "状态良好"
        elif hp_percent > 33:
            hp_status = "受了轻伤"
        else:
            hp_status = "伤痕累累"

        if self.llm and self._llm_initialized:
            system = """你是一个沉浸式TRPG战斗叙事专家。你为AI DM RPG生成生动、紧张、细节丰富的战斗叙事。

【硬约束 - 禁止】
- 禁止使用"玩家正在..."、"玩家可以..."、"玩家选择..."等第三人称描述
- 禁止使用"作为你的 DM..."、"作为游戏主持人..."、"作为AI..."等暴露AI身份的话
- 禁止使用"AI"、"人工智能"、"语言模型"等暴露技术身份的字眼
- 禁止元叙事或跳出角色的评论
- 叙事中不得出现"DM认为"、"DM觉得"等表述

写作要求：
- 第二人称视角（"你砍向敌人"或"敌人扑向你"）
- 使用生动有力的动词
- 每次攻击/受伤都要有身体反应和环境细节
- 战斗节奏要紧凑、有张力
- 50-150字的段落
- 中文输出
- 结尾显示数值变化: 命中/未命中、伤害值"""
            
            prompt = f"""【战斗场景】{location}
当前场景: {scene_desc}

【回合 {turn}】{attacker_name} 对 {target_name} 发起{action}

攻击详情:
- 攻击投掷: d20{attack_roll-5:+d} = {attack_roll}
- 目标AC: {target_ac}
- 命中结果: {'命中！' if hit else '未命中！'}
- 造成伤害: {damage}点
- 目标当前状态: {target_name} {hp_status} ({target_hp}/{target_max_hp} HP)
- 目标是否倒下: {'是 - 战斗即将结束！' if target_hp <= 0 else '否'}

请生成一段沉浸式战斗叙事，描述攻击的过程、命中/闪避的身体反应、受伤后的状态变化。"""

            try:
                narrative = await self.llm.generate(
                    prompt,
                    system=system,
                    temperature=0.8,
                )
                if narrative and len(narrative) > 10:
                    return narrative
            except Exception as e:
                logger.warning(f"LLM combat narrative failed: {e}")

        # LLM 不可用时的 fallback 叙事
        return self._fallback_combat_narrative(
            attacker_name, target_name, action, hit, damage, attack_roll, target_ac, target_hp, target_max_hp, turn
        )

    def _fallback_combat_narrative(
        self,
        attacker_name: str,
        target_name: str,
        action: str,
        hit: bool,
        damage: int,
        attack_roll: int,
        target_ac: int,
        target_hp: int,
        target_max_hp: int,
        turn: int,
    ) -> str:
        """Fallback 战斗叙事（当 LLM 不可用时）"""
        attack_verbs = ["猛烈地砍向", "用力劈向", "挥刀斩向", "突刺向", "狠狠击中"]
        counter_verbs = ["猛地扑向", "挥爪抓来", "狠狠咬下", "发动猛烈攻势"]
        
        verbs = counter_verbs if action == "counter_attack" else attack_verbs
        verb = random.choice(verbs)
        
        if hit:
            hurt_reactions = ["痛苦地咆哮", "踉跄后退", "愤怒地瞪着你", "发出低沉的怒吼", "鲜血飞溅"]
            hurt = random.choice(hurt_reactions)
            result = f"[回合 {turn}][{'你的攻击' if attacker_name == '你' else f'{attacker_name}的反击'}] {attacker_name}{verb}{target_name}！\n"
            result += f"  🎲 攻击投掷: {attack_roll} vs AC {target_ac} → 命中！\n"
            result += f"  💥 造成 {damage} 点伤害！ {target_name} {hurt}。"
            if target_hp <= 0:
                result += f"\n⚔️ {target_name} 倒下了！"
        else:
            result = f"[回合 {turn}][{'你的攻击' if attacker_name == '你' else f'{attacker_name}的反击'}] {attacker_name}{verb}{target_name}，被敏捷地躲开！\n"
            result += f"  🎲 攻击投掷: {attack_roll} vs AC {target_ac} → 未命中"
        
        return result

    # --------------------------------------------------------------------------
    # 防御/技能/道具/逃跑 - LLM 叙事生成
    # --------------------------------------------------------------------------

    async def _generate_defend_narrative(self, enemy_name: str, turn: int) -> str:
        """生成防御叙事"""
        get_logger().debug("game_master", f"LLM API call: _generate_defend_narrative (enemy={enemy_name}, turn={turn})")
        location = self._pre_combat_location or "未知地点"
        scene_desc = self._pre_combat_scene.get("description", "") if self._pre_combat_scene else "战斗正在进行"

        if self.llm and self._llm_initialized:
            system = """你是一个沉浸式TRPG战斗叙事专家。你为AI DM RPG生成防御动作的沉浸式叙事。

【硬约束 - 禁止】
- 禁止使用"玩家正在..."、"玩家可以..."、"玩家选择..."等第三人称描述
- 禁止使用"作为你的 DM..."、"作为游戏主持人..."、"作为AI..."等暴露AI身份的话
- 禁止使用"AI"、"人工智能"、"语言模型"等暴露技术身份的字眼
- 禁止元叙事或跳出角色的评论

写作要求：
- 第二人称视角（"你举起盾牌"）
- 描写防御姿态的身体感觉和视觉效果
- 敌人看到你防御时的反应
- 紧张感，蓄势待发的氛围
- 50-100字，中文输出"""

            prompt = f"""【战斗场景】{location}
当前场景: {scene_desc}

【回合 {turn}】你进入防御姿态

请生成一段叙事，描述你举起武器/盾牌准备防御的情景，以及{enemy_name}看到你防御时的反应。"""

            try:
                narrative = await self.llm.generate(prompt, system=system, temperature=0.7)
                if narrative and len(narrative) > 10:
                    return narrative
            except Exception as e:
                logger.warning(f"LLM defend narrative failed: {e}")

        # Fallback
        verbs = ["举起盾牌", "摆出防御架势", "严阵以待", "护住身前"]
        return f"[回合 {turn}][防御] 你{random.choice(verbs)}，准备迎接{enemy_name}的攻击！\n  🛡️ 进入防御姿态！"

    async def _generate_skill_narrative(
        self,
        skill_name: str,
        target_name: str,
        damage: int,
        hit: bool,
        target_hp: int,
        target_max_hp: int,
        turn: int,
    ) -> str:
        """生成技能叙事"""
        get_logger().debug("game_master", f"LLM API call: _generate_skill_narrative (skill={skill_name}, target={target_name}, damage={damage}, turn={turn})")
        location = self._pre_combat_location or "未知地点"
        scene_desc = self._pre_combat_scene.get("description", "") if self._pre_combat_scene else "战斗正在进行"

        hp_percent = (target_hp / target_max_hp * 100) if target_max_hp > 0 else 0
        if hp_percent > 66:
            hp_status = "似乎没有受到太大影响"
        elif hp_percent > 33:
            hp_status = "明显受了伤"
        else:
            hp_status = "岌岌可危"

        if self.llm and self._llm_initialized:
            system = """你是一个沉浸式TRPG战斗叙事专家。你为AI DM RPG生成魔法/技能攻击的沉浸式叙事。

【硬约束 - 禁止】
- 禁止使用"玩家正在..."、"玩家可以..."、"玩家选择..."等第三人称描述
- 禁止使用"作为你的 DM..."、"作为游戏主持人..."、"作为AI..."等暴露AI身份的话
- 禁止使用"AI"、"人工智能"、"语言模型"等暴露技术身份的字眼
- 禁止元叙事或跳出角色的评论

写作要求：
- 第二人称视角
- 描写魔法的视觉效果和施法过程
- 技能命中的身体反应和环境变化
- 50-150字，中文输出"""

            prompt = f"""【战斗场景】{location}
当前场景: {scene_desc}

【回合 {turn}】你对 {target_name} 施放了 {skill_name}

攻击详情:
- 造成伤害: {damage}点
- 目标状态: {target_name} {hp_status} ({target_hp}/{target_max_hp} HP)
- 目标是否倒下: {'是 - 即将倒下！' if target_hp <= 0 else '否'}

请生成一段沉浸式叙事，描述你施展魔法的过程、命中效果和目标的反应。"""

            try:
                narrative = await self.llm.generate(prompt, system=system, temperature=0.8)
                if narrative and len(narrative) > 10:
                    return narrative
            except Exception as e:
                logger.warning(f"LLM skill narrative failed: {e}")

        # Fallback
        effects = [
            f"魔法能量从你手中爆发，击中{target_name}！",
            f"你吟唱咒语，一道闪光击中{target_name}！",
            f"你施展技能，{target_name}被魔法击中！",
        ]
        result = f"[回合 {turn}][技能] {random.choice(effects)}\n"
        result += f"  ✨ 造成 {damage} 点伤害！ {target_name} 受到了重创。"
        if target_hp <= 0:
            result += f"\n⚔️ {target_name} 摇摇欲坠！"
        return result

    async def _generate_item_narrative(
        self,
        item_name: str,
        target_name: str,
        heal_amount: int,
        new_hp: int,
        max_hp: int,
        turn: int,
    ) -> str:
        """生成道具使用叙事"""
        get_logger().debug("game_master", f"LLM API call: _generate_item_narrative (item={item_name}, target={target_name}, heal={heal_amount}, turn={turn})")
        location = self._pre_combat_location or "未知地点"

        if self.llm and self._llm_initialized:
            system = """你是一个沉浸式TRPG战斗叙事专家。你为AI DM RPG生成使用道具的沉浸式叙事。

【硬约束 - 禁止】
- 禁止使用"玩家正在..."、"玩家可以..."、"玩家选择..."等第三人称描述
- 禁止使用"作为你的 DM..."、"作为游戏主持人..."、"作为AI..."等暴露AI身份的话
- 禁止使用"AI"、"人工智能"、"语言模型"等暴露技术身份的字眼
- 禁止元叙事或跳出角色的评论

写作要求：
- 第二人称视角
- 描写使用道具的动作和效果
- 治疗/增益的感觉，身体的恢复
- 紧张的战斗中使用道具的紧迫感
- 50-100字，中文输出"""

            prompt = f"""【战斗场景】{location}

【回合 {turn}】{target_name} 使用了 {item_name}

效果:
- 恢复生命: {heal_amount}点
- 当前HP: {new_hp}/{max_hp}

请生成一段叙事，描述{target_name}使用{item_name}的过程和效果。"""

            try:
                narrative = await self.llm.generate(prompt, system=system, temperature=0.7)
                if narrative and len(narrative) > 10:
                    return narrative
            except Exception as e:
                logger.warning(f"LLM item narrative failed: {e}")

        # Fallback
        return (f"[回合 {turn}][道具] 你快速灌下一瓶{item_name}！\n"
                f"  💚 恢复了 {heal_amount} 点HP！当前: {new_hp}/{max_hp}")

    async def _generate_flee_fail_narrative(self, enemy_name: str, turn: int) -> str:
        """生成逃跑失败叙事"""
        get_logger().debug("game_master", f"LLM API call: _generate_flee_fail_narrative (enemy={enemy_name}, turn={turn})")
        location = self._pre_combat_location or "未知地点"

        if self.llm and self._llm_initialized:
            system = """你是一个沉浸式TRPG战斗叙事专家。你为AI DM RPG生成逃跑失败时的紧张叙事。

【硬约束 - 禁止】
- 禁止使用"玩家正在..."、"玩家可以..."、"玩家选择..."等第三人称描述
- 禁止使用"作为你的 DM..."、"作为游戏主持人..."、"作为AI..."等暴露AI身份的话
- 禁止使用"AI"、"人工智能"、"语言模型"等暴露技术身份的字眼
- 禁止元叙事或跳出角色的评论

写作要求：
- 第二人称视角
- 描写逃跑失败被拦截的紧张感
- 敌人趁机发动攻击
- 50-100字，中文输出"""

            prompt = f"""【战斗场景】{location}

【回合 {turn}】你试图逃跑，但被 {enemy_name} 拦截！

请生成一段叙事，描述你转身逃跑时被{enemy_name}拦住、陷入更危险境地的情景。"""

            try:
                narrative = await self.llm.generate(prompt, system=system, temperature=0.8)
                if narrative and len(narrative) > 10:
                    return narrative
            except Exception as e:
                logger.warning(f"LLM flee fail narrative failed: {e}")

        # Fallback
        return f"[回合 {turn}][逃跑] 你试图逃跑，但{enemy_name}挡在了你面前！\n  ❌ 逃跑失败！"

    async def _generate_combat_recovery_narrative(
        self,
        winner: str,
        reason: str,
        state_data: dict,
    ) -> str:
        """
        生成战斗结束后的场景恢复叙事

        Args:
            winner: 胜利方 (players/enemies)
            reason: 结束原因
            state_data: 战斗状态数据

        Returns:
            场景恢复叙事
        """
        get_logger().debug("game_master", f"LLM API call: _generate_combat_recovery_narrative (winner={winner}, reason={reason})")
        location = self._pre_combat_location or "未知地点"
        scene_desc = self._pre_combat_scene.get("description", "") if self._pre_combat_scene else ""
        
        if self.llm and self._llm_initialized:
            system = """你是一个沉浸式TRPG叙事专家。你为AI DM RPG生成战斗结束后的场景恢复叙事。

【硬约束 - 禁止】
- 禁止使用"玩家正在..."、"玩家可以..."、"玩家选择..."等第三人称描述
- 禁止使用"作为你的 DM..."、"作为游戏主持人..."、"作为AI..."等暴露AI身份的话
- 禁止使用"AI"、"人工智能"、"语言模型"等暴露技术身份的字眼
- 禁止元叙事或跳出角色的评论

写作要求：
- 第二人称视角
- 描写战斗结束后，玩家回到探索场景的氛围
- 可以描写战利品、敌人留下的东西、场景的变化
- 紧张过后的喘息感
- 50-150字，中文输出"""
            
            prompt = f"""【战斗结束 - 场景恢复】

战斗结果: {'你获得了胜利！' if winner == 'players' else '你被打败了...'}
结束原因: {reason}
战斗地点: {location}
战前场景描述: {scene_desc or '无'}

请生成一段叙事，描述战斗结束后玩家回到探索场景的情景。"""

            try:
                narrative = await self.llm.generate(
                    prompt,
                    system=system,
                    temperature=0.7,
                )
                if narrative and len(narrative) > 10:
                    return narrative
            except Exception as e:
                logger.warning(f"LLM combat recovery narrative failed: {e}")

        # Fallback
        if winner == "players":
            return f"\n⚔️ 战斗结束！{'你获得了胜利！' if reason != '玩家逃跑' else '你成功逃离了战斗！'}\n\n你回到{location}，周围恢复了平静..."
        else:
            return f"\n☠️ 战斗结束... 你倒在了{location}。\n\n意识模糊中，你勉强站起身来..."

    async def _check_scene_update(self, player_text: str) -> str | None:
        """检查是否需要更新场景"""
        # 扩展场景关键词：包含移动方向词和目的地检测
        movement_keywords = [
            "去", "走进", "进入", "离开", "前往", "来到", "去到", "走到",
            "向", "奔赴", "闯", "探索", "前往"
        ]
        location_keywords = ["酒馆", "森林", "城堡", "城镇", "村庄", "洞穴", "河流", "山洞", "平原"]

        text = player_text.lower()

        # 尝试检测目的地（在移动词之后出现的位置）
        for mov_kw in movement_keywords:
            mov_pos = text.find(mov_kw)
            if mov_pos >= 0:
                # 在移动词之后找位置
                remaining = text[mov_pos + len(mov_kw):]
                for loc in location_keywords:
                    if loc in remaining:
                        return await self._generate_scene(loc)
                # 如果移动词后面没有明确位置，但找到了位置，也用位置
                for loc in location_keywords:
                    if loc in text:
                        return await self._generate_scene(loc)

        # 如果没有移动词，但有明确的"在X里"描述当前场景
        for loc in location_keywords:
            if f"在{loc}" in text or loc in text:
                # 检查是否是进入新场景（而不是描述当前场景）
                if self.current_scene and self.game_state.get("location") == loc:
                    return None  # 已经在这里，不重复生成
                return await self._generate_scene(loc)

        # 探索指令
        if "探索" in text or "查看" in text or "搜索" in text:
            if not self.current_scene:
                return await self._generate_scene("森林")

        return None

    # --------------------------------------------------------------------------
    # 场景切换过渡叙事
    # --------------------------------------------------------------------------

    async def _generate_transition_narrative(self, from_scene: str, to_scene: str) -> str:
        """
        生成场景切换时的过渡叙事

        Args:
            from_scene: 原场景名称
            to_scene: 目标场景名称

        Returns:
            1-3句过渡叙事，描述从 from_scene 到 to_scene 的旅途
        """
        if not from_scene or from_scene == to_scene:
            return ""

        get_logger().debug("game_master", f"LLM API call: _generate_transition_narrative (from={from_scene}, to={to_scene})")
        # 用 LLM 生成沉浸式过渡叙事（优先）
        if self.llm and self._llm_initialized:
            system = """你是一个沉浸式TRPG叙事专家。你为AI DM RPG生成场景切换时的过渡叙事。

【硬约束 - 禁止】
- 禁止使用"玩家正在..."、"玩家可以..."、"玩家选择..."等第三人称描述
- 禁止使用"作为你的 DM..."、"作为游戏主持人..."、"作为AI..."等暴露AI身份的话
- 禁止使用"AI"、"人工智能"、"语言模型"等暴露技术身份的字眼
- 禁止元叙事或跳出角色的评论

写作要求：
- 第二人称视角，描述旅途的过程
- 1-3句话，简洁有力，不要喧宾夺主
- 包含距离感（近/远）、路途景色变化
- 可以有小插曲或随机事件（天气、路人、声响等）
- 营造氛围感，让玩家感受到空间的转换
- 中文输出"""

            prompt = f"""【场景切换】

从场景: {from_scene}
目标场景: {to_scene}

请生成一段过渡叙事，描述玩家从{from_scene}前往{to_scene}的路途。
要点：
- 距离感（近处还是远处，走多久）
- 路途景色变化（从{from_scene}的环境如何过渡到{to_scene}的环境）
- 可选的随机小插曲（天气、路人、声响、奇怪的东西）
- 保持简洁，1-3句话"""

            try:
                narrative = await self.llm.generate(prompt, system=system, temperature=0.8)
                if narrative and len(narrative) > 5:
                    return narrative.strip()
            except Exception as e:
                logger.warning(f"LLM transition narrative failed: {e}")

        # Fallback: 模板 + 随机变量生成过渡叙事
        return self._fallback_transition_narrative(from_scene, to_scene)

    def _fallback_transition_narrative(self, from_scene: str, to_scene: str) -> str:
        """
        Fallback 过渡叙事（当 LLM 不可用时）

        使用场景类型映射生成符合氛围的过渡叙事
        """
        # 场景距离映射：同一区域（近）vs 不同区域（远）
        same_area_pairs = {
            ("酒馆", "森林"): True,
            ("森林", "酒馆"): True,
            ("村庄", "平原"): True,
            ("平原", "村庄"): True,
            ("城镇", "城堡"): True,
            ("城堡", "城镇"): True,
            ("洞穴", "山洞"): True,
            ("山洞", "洞穴"): True,
            ("月叶镇广场", "月光酒馆"): True,
            ("月光酒馆", "月叶镇广场"): True,
        }

        is_near = same_area_pairs.get((from_scene, to_scene), False)
        if not is_near:
            # 检查是否都在"野外"区域
            wild_scenes = {"森林", "平原", "洞穴", "山洞", "河流"}
            if from_scene in wild_scenes and to_scene in wild_scenes:
                is_near = True

        distance_desc = random.choice([
            "走了一段路",
            "穿过一片区域",
            "经过一段路程",
            "花了些时间",
        ]) if not is_near else random.choice([
            "走了一小段路",
            "没走多远",
            "转过街角",
            "穿过小路",
        ])

        # 场景转换的典型过渡
        tavern_forest = (from_scene in ["酒馆", "月光酒馆"] and to_scene in ["森林", "幽影森林"]) or \
                        (from_scene in ["森林", "幽影森林"] and to_scene in ["酒馆", "月光酒馆"])
        village_tavern = (from_scene in ["月叶镇广场", "村庄", "城镇"] and to_scene in ["酒馆", "月光酒馆"]) or \
                         (from_scene in ["酒馆", "月光酒馆"] and to_scene in ["月叶镇广场", "村庄", "城镇"])

        if tavern_forest:
            templates = [
                "你走出酒馆大门，清凉的夜风拂面而来。穿过镇子边缘的小径，树木渐渐变得茂密幽暗……",
                "离开喧嚣的酒馆，你沿着林间小道前行。脚下的落叶沙沙作响，空气中开始弥漫着森林特有的潮湿气息……",
                "从酒馆出来，你踏上了通往幽影森林的小路。月光逐渐被密集的树冠遮挡，四周越发幽暗……",
            ]
        elif village_tavern:
            templates = [
                "你穿过镇子的青石板路，没走多远，就看到了月光酒馆的招牌在微风中轻轻晃动……",
                "从镇子广场沿着小路走了一会儿，一扇温暖的木门出现在眼前——月光酒馆到了……",
                "穿过几条安静的巷弄，一座古朴的木质建筑矗立在眼前，门口挂着的灯笼散发着柔和的光……",
            ]
        else:
            # 通用过渡模板
            templates = [
                f"你离开{from_scene}，{distance_desc}，终于来到了{to_scene}……",
                f"从{from_scene}出发，{distance_desc}，{to_scene}的轮廓渐渐出现在眼前……",
                f"你踏上了前往{to_scene}的路。{distance_desc}，新的场景在眼前展开……",
                f"穿过一片区域，你从{from_scene}来到了{to_scene}。{distance_desc}，路途上的风景不断变化……",
            ]

        return random.choice(templates)

    async def _generate_scene(self, scene_type: str) -> str:
        """
        生成或获取场景
        
        打通场景→探索流程的关键方法:
        1. 优先从 registry 查找已有场景（懒生成原则）
        2. 若无则直接调用 scene_agent.generate_scene() 生成并等待
        3. 将场景数据持久化到 current_scene 和 game_state
        4. 触发 NPC 集成，将场景 NPC 注册为可交互对象
        5. 返回格式化场景叙事
        
        NPC 场景状态继承:
        - 场景切换时，将当前 active_npcs 按场景类型存储到 game_state["active_npcs_per_scene"]
        - 进入场景时，优先从 game_state["active_npcs_per_scene"][scene_type] 恢复 NPC
        - 这样返回场景时可以看到同一个 NPC（同 name+role，同状态）
        """
        get_logger().info("game_master", f"Scene transition: {self.game_state.get('location', '未知')} → {scene_type}")
        get_logger().debug("game_master", f"GameMaster: generating/fetching scene - type={scene_type}")

        scene = None

        # NPC 场景状态继承 - 保存前一个场景的 NPC（跨场景持久化）
        if self.current_scene and self.game_state.get("location"):
            old_scene_type = self.game_state["location"]
            if old_scene_type and old_scene_type != scene_type:
                self.game_state.setdefault("active_npcs_per_scene", {})[old_scene_type] = dict(self.active_npcs)
                logger.debug(f"Saved NPCs for scene '{old_scene_type}': {list(self.active_npcs.keys())}")

        # NPC 场景状态继承 - 恢复当前场景的 NPC（如果之前访问过）
        if scene_type in self.game_state.get("active_npcs_per_scene", {}):
            restored = self.game_state["active_npcs_per_scene"][scene_type]
            self.active_npcs = dict(restored)
            logger.info(f"Restored {len(self.active_npcs)} NPCs for scene '{scene_type}'")
        else:
            # 首次进入此场景，清空旧的
            self.active_npcs = {}

        # 获取当前任务线索（用于融入场景叙事）
        # 传入 scene_type 作为 current_location，使提示能根据玩家是否已到达该地点动态调整
        quest_hint = self.quest_state.get_stage_hint(current_location=scene_type) if self.quest_state.is_active() else ""

        # scene_agent 可能未初始化（测试场景）
        _is_fallback = False
        _fallback_tier = None
        
        if self.scene_agent is not None:
            # Step 1: 尝试获取已有场景（懒生成：优先复用）
            scene = self.scene_agent.get_existing_scene(scene_type)
            
            if scene is None:
                # Step 2: 没有已有场景，直接生成（阻塞等待完成）
                logger.info(f"No existing scene for '{scene_type}', generating new...")
                try:
                    scene = await self.scene_agent.generate_scene(
                        scene_type=scene_type,
                        requirements=f"玩家正在寻找一个{scene_type}",
                        quest_hint=quest_hint,
                    )
                    # 检查 scene_agent 是否使用了 fallback
                    if self.scene_agent._last_scene_fallback:
                        _is_fallback = True
                        _fallback_tier = self.scene_agent._last_fallback_tier
                        # 跟踪降级模式
                        consecutive, should_alert = self._degradation_tracker.record_fallback(scene_type)
                        logger.info(f"SceneAgent fallback detected for '{scene_type}' (consecutive={consecutive}, tier={_fallback_tier})")
                        # 标记降级模式
                        self._in_degradation_mode = True
                except Exception as e:
                    logger.warning(f"Scene generation failed: {e}, using fallback")
                    scene = None
        
        # ========== 降级恢复机制: 连续3次降级后强制重建 ==========
        # 如果连续3次降级，尝试一次完整的 LLM 生成（不走 fallback）
        if scene is None and self._degradation_tracker.should_force_rebuild():
            logger.info(f"Force rebuild triggered: consecutive={self._degradation_tracker.consecutive_count}, retrying full LLM generation...")
            # 重置降级模式标记，让 scene_agent 重新尝试完整生成
            self._in_degradation_mode = False
            try:
                scene = await self.scene_agent.generate_scene(
                    scene_type=scene_type,
                    requirements=f"玩家正在寻找一个{scene_type}",
                    quest_hint=quest_hint,
                )
                if scene is not None:
                    # 重建成功，重置降级计数器
                    self._degradation_tracker.reset()
                    logger.info(f"Force rebuild succeeded, degradation counter reset")
                    _is_fallback = False  # 标记为非降级
            except Exception as e:
                logger.warning(f"Force rebuild failed: {e}, using fallback")
                scene = None
        
        # Fallback: 完全没有 scene_agent 或生成失败时
        if scene is None:
            _is_fallback = True
            _fallback_tier = "heavy"  # GameMaster 直接 fallback 使用重度降级
            
            # ========== Fallback 降级模式跟踪 ==========
            consecutive, should_alert = self._degradation_tracker.record_fallback(scene_type)
            logger.info(f"Fallback scene used for '{scene_type}' (consecutive={consecutive})")
            
            # 生成沉浸式的 fallback 场景描述（包含任务线索）
            fallback_desc = self._generate_fallback_scene_description(scene_type, quest_hint)
            # 生成 fallback NPCs（修复：确保 fallback 路径也有 NPC）
            if self.scene_agent:
                fallback_npcs = self.scene_agent._generate_fallback_npcs(scene_type)
            else:
                # 紧急 fallback：当 scene_agent 也缺失时使用硬编码 NPC
                import uuid
                fallback_npcs = [{
                    "id": f"npc_{uuid.uuid4().hex[:8]}",
                    "name": f"{scene_type} NPC",
                    "role": "villager",
                    "personality": "helpful",
                    "dialogue_style": "friendly"
                }]
            
            # Fallback 也生成动态 atmosphere（V2版本,支持 consecutive_rounds 差异化）
            # 计算连续探索轮次
            # BUG FIX: scene is None here, use scene_type as registry lookup key
            fallback_registry_key = f"fallback_{scene_type}"  # scene.id 不可用，用类型作 key
            fallback_consecutive_rounds = 1
            fallback_current_state = None
            if self.scene_agent and hasattr(self.scene_agent, 'registry'):
                # 使用 fallback_registry_key 而非 scene.id（scene 为 None 会导致 AttributeError）
                atm_count = self.scene_agent.registry.get_atmosphere_count(fallback_registry_key)
                fallback_consecutive_rounds = atm_count + 1
                scene_obj = self.scene_agent.registry.get_by_id(fallback_registry_key)
                if scene_obj and scene_obj.atmosphere_history:
                    last_entry = scene_obj.atmosphere_history[-1]
                    fallback_current_state = last_entry.get("state")
            # 添加上下文状态日志（用于排查场景切换后的命令路由问题）
            logger.info(f"[SceneCtx] Fallback scene init: scene_type={scene_type}, atm_rounds={fallback_consecutive_rounds}, is_fallback={_is_fallback}, has_registry={self.scene_agent is not None and hasattr(self.scene_agent, 'registry')}")
            
            atm_result = generate_atmosphere_v2(
                scene_type=scene_type,
                consecutive_rounds=fallback_consecutive_rounds,
                current_state=fallback_current_state,
            )
            
            # 构建 atm_data 以保持向后兼容
            atm_data = {
                "atmosphere": atm_result["atmosphere"],
                "atmosphere_desc": atm_result["atmosphere_str"],
                "atmosphere_tags": atm_result["atmosphere_tags"],
                "light": atm_result.get("light", ""),
                "sound": atm_result.get("sound", ""),
                "smell": atm_result.get("smell", ""),
                "temperature": atm_result.get("temperature", ""),
                "mood": atm_result.get("mood", ""),
                "state": atm_result["state"],
            }
            
            # BUG FIX: 添加 id 和 name 字段（与 scene.to_dict() 保持一致）
            fallback_scene_id = f"fallback_{scene_type}_{uuid.uuid4().hex[:8]}"
            self.current_scene = {
                "id": fallback_scene_id,
                "name": f"{scene_type}（降级模式）",
                "type": scene_type,
                "description": fallback_desc,
                "npcs": fallback_npcs,
                "atmosphere": atm_result["atmosphere"],
                "atmosphere_desc": atm_result["atmosphere_str"],
                "atmosphere_light": atm_result.get("light", ""),
                "atmosphere_sound": atm_result.get("sound", ""),
                "atmosphere_smell": atm_result.get("smell", ""),
                "atmosphere_temperature": atm_result.get("temperature", ""),
                "atmosphere_mood": atm_result.get("mood", ""),
                "atmosphere_state": atm_result["state"],
            }
            self.game_state["location"] = scene_type
            # 场景切换时重置战斗状态
            self._clear_combat_state()
            # 标记降级模式（让 _format_scene_narrative 显示警告）
            self._in_degradation_mode = True
            # 更新 active_npcs（preserve_existing=True 因为已从 game_state 恢复过）
            self._update_active_npcs_from_scene(preserve_existing=True)
            # 同步 active_npcs 到 game_state（持久化，支持场景切换后恢复）
            self.game_state["active_npcs_per_scene"][scene_type] = dict(self.active_npcs)
            self.game_state["active_npcs"] = self.active_npcs
            # Fallback 也检测场景切换
            old_location = self.game_state.get("location", "")
            is_transition = old_location and old_location != scene_type and old_location != "未知"
            
            # 构建 fallback 叙事（包含降级警告）
            fallback_narrative_parts = []
            fallback_narrative_parts.append(f"\n{'='*40}")
            fallback_narrative_parts.append(f"📍 场景: {scene_type}")
            fallback_narrative_parts.append(f"{'='*40}")
            fallback_narrative_parts.append(f"\n{fallback_desc}")
            fallback_narrative_parts.append(f"\n🌤️ {atm_data['atmosphere_desc']}")
            
            # 添加降级警告
            consecutive = self._degradation_tracker.consecutive_count
            if consecutive >= 3:
                fallback_narrative_parts.append(f"\n⚠️⚠️⚠️ 警告：系统已连续 {consecutive} 次使用简化叙事模式！")
                fallback_narrative_parts.append(f"   请检查网络连接或 API 配置。")
                fallback_narrative_parts.append(f"   如果问题持续存在，场景质量可能会下降。")
                fallback_narrative_parts.append(f"⚠️⚠️⚠️")
            else:
                fallback_narrative_parts.append(f"\n⚠️ 当前为简化叙事模式（降级 {consecutive} 次）")
            
            fallback_narrative_parts.append(f"{'='*40}\n")
            fallback_narrative = "\n".join(fallback_narrative_parts)

            # Fallback 路径也添加到 atmosphere 历史
            # BUG FIX: scene is None here, use fallback_scene_id instead
            if self.scene_agent and hasattr(self.scene_agent, 'registry'):
                self.scene_agent.registry.add_atmosphere_to_history(fallback_scene_id, atm_data)
            
            if is_transition:
                transition = await self._generate_transition_narrative(old_location, scene_type)
                return f"{transition}\n\n{fallback_narrative}"
            return fallback_narrative

        # Step 3: 场景获取成功，持久化到 game_state
        self.current_scene = scene.to_dict()
        self.game_state["location"] = scene_type
        
        # ========== 场景切换初始化完整性检查 ==========
        # 确保 current_scene 包含必要字段（防止路径敏感性导致的上下文 bug）
        _required_fields = ["id", "type", "description"]
        _missing_fields = [f for f in _required_fields if f not in self.current_scene]
        if _missing_fields:
            logger.warning(f"[SceneCtx] current_scene 缺少字段: {_missing_fields}, scene_type={scene_type}, 尝试修复...")
            # 修复缺失字段
            if "id" not in self.current_scene:
                self.current_scene["id"] = scene.id
            if "type" not in self.current_scene:
                self.current_scene["type"] = scene_type
            if "description" not in self.current_scene:
                self.current_scene["description"] = getattr(scene, "description", "") or ""
        # 记录场景切换后的上下文状态（用于排查命令路由问题）
        logger.info(f"[SceneCtx] Scene init OK: type={scene_type}, id={self.current_scene.get('id','?')}, npcs={len(self.current_scene.get('npcs',[]))}, location={self.game_state.get('location','?')}")
        # 场景切换时重置战斗状态
        self._clear_combat_state()
        
        # 成功生成场景，重置降级模式状态（除非 scene_agent 刚报告了 fallback）
        if not _is_fallback:
            self._in_degradation_mode = False
            self._degradation_alert_shown = False
        
        # Step 3.5: 生成动态 atmosphere（V2版本,支持 consecutive_rounds 差异化）
        # 计算连续探索轮次
        consecutive_rounds = 1
        current_state = None
        if self.scene_agent and hasattr(self.scene_agent, 'registry'):
            atm_count = self.scene_agent.registry.get_atmosphere_count(scene.id)
            consecutive_rounds = atm_count + 1  # 历史条目数+1 = 当前轮次
            # 从历史中提取当前状态
            scene_obj = self.scene_agent.registry.get_by_id(scene.id)
            if scene_obj and scene_obj.atmosphere_history:
                last_entry = scene_obj.atmosphere_history[-1]
                current_state = last_entry.get("state")
        
        # 构建游戏状态上下文（用于战斗后/任务阶段的特殊 atmosphere）
        atmosphere_context = {}
        atmosphere_context["quest_stage"] = self.quest_state.stage.value if self.quest_state.is_active() else ""
        # 检查是否刚从战斗恢复（post_combat 标记由 _on_combat_end 设置）
        if self.game_state.get("_post_combat_scene"):
            atmosphere_context["post_combat"] = True
            self.game_state["_post_combat_scene"] = False  # 清除标记
        
        # 生成动态 atmosphere（V2版本,使用 consecutive_rounds 差异化策略）
        atm_result = generate_atmosphere_v2(
            scene_type=scene_type,
            consecutive_rounds=consecutive_rounds,
            current_state=current_state,
        )
        
        # 构建 atm_data 以保持向后兼容（用于添加到历史记录）
        atm_data = {
            "atmosphere": atm_result["atmosphere"],
            "atmosphere_desc": atm_result["atmosphere_str"],
            "atmosphere_tags": atm_result["atmosphere_tags"],
            "light": atm_result.get("light", ""),
            "sound": atm_result.get("sound", ""),
            "smell": atm_result.get("smell", ""),
            "temperature": atm_result.get("temperature", ""),
            "mood": atm_result.get("mood", ""),
            "state": atm_result["state"],  # 保存5维度状态
        }
        
        # 更新 current_scene 中的 atmosphere 数据
        self.current_scene["atmosphere"] = atm_result["atmosphere"]
        self.current_scene["atmosphere_desc"] = atm_result["atmosphere_str"]
        self.current_scene["atmosphere_light"] = atm_result.get("light", "")
        self.current_scene["atmosphere_sound"] = atm_result.get("sound", "")
        self.current_scene["atmosphere_smell"] = atm_result.get("smell", "")
        self.current_scene["atmosphere_temperature"] = atm_result.get("temperature", "")
        self.current_scene["atmosphere_mood"] = atm_result.get("mood", "")
        self.current_scene["atmosphere_state"] = atm_result["state"]  # 保存当前状态到场景
        
        # 将 atmosphere 添加到场景历史记录
        if self.scene_agent and hasattr(self.scene_agent, 'registry'):
            self.scene_agent.registry.add_atmosphere_to_history(scene.id, atm_data)
        
        # ========== Atmosphere 更新后的完整性检查 ==========
        # 确保 current_scene 包含必要的 atmosphere 字段
        _atm_fields = ["atmosphere", "atmosphere_desc", "atmosphere_light", "atmosphere_sound", "atmosphere_smell", "atmosphere_temperature", "atmosphere_mood"]
        _missing_atm = [f for f in _atm_fields if f not in self.current_scene]
        if _missing_atm:
            logger.warning(f"[SceneCtx] current_scene atmosphere 字段缺失: {_missing_atm}, 使用默认值填充")
            for f in _missing_atm:
                self.current_scene[f] = ""
        logger.info(f"[SceneCtx] Atmosphere updated: atm={self.current_scene.get('atmosphere','?')}, state={self.current_scene.get('atmosphere_state','?')}")
        
        # Step 4: 深度集成：将场景中的 NPC 自动添加到活跃 NPC 列表
        # NPC 场景状态继承：保留已有 NPC，新场景 NPC 按 name+role 匹配
        self._update_active_npcs_from_scene(preserve_existing=True)
        
        # Step 5: 同步 active_npcs 到 game_state（持久化，支持场景切换后恢复）
        # 使用 per_scene 存储，这样返回场景时可以正确恢复
        self.game_state["active_npcs_per_scene"][scene_type] = dict(self.active_npcs)
        self.game_state["active_npcs"] = self.active_npcs
        
        # Step 6: 检测场景切换，生成过渡叙事
        old_location = self.game_state.get("location", "")
        is_transition = old_location and old_location != scene_type and old_location != "未知"

        scene_narrative = self._format_scene_narrative(scene)

        if is_transition:
            # 场景切换：先输出过渡叙事，再输出新场景
            transition = await self._generate_transition_narrative(old_location, scene_type)
            return f"{transition}\n\n{scene_narrative}"
        else:
            # 首次进入场景或当前位置就是目标场景，无过渡
            return scene_narrative

    def _update_active_npcs_from_scene(self, preserve_existing: bool = False):
        """
        深度集成：从当前场景的 NPC 列表自动填充 active_npcs
        
        确保进入场景时，场景中的 NPC 被自动注册为可交互对象。
        同时将这些 NPC 注册到 NPC Agent（如果可用），以便进行真实对话。
        
        Args:
            preserve_existing: 如果为 True，会保留已存在的 NPC 数据。
                通过 name+role 匹配来确定是否是同一个 NPC。
                这样场景切换后，NPC 的状态（如对话历史）可以保持。
                
        Note: 使用 name+role 作为 active_npcs 的 key，确保跨场景的稳定身份。
        """
        scene_npcs = self.current_scene.get("npcs", [])
        
        # 如果需要保留已有 NPC，构建 name+role -> old_npc_data 的映射
        old_npcs_by_key = {}
        if preserve_existing:
            for npc_id, npc_data in self.active_npcs.items():
                key = self._npc_key(npc_data)
                if key:
                    old_npcs_by_key[key] = npc_data
        
        # 重要：如果场景没有 NPC 且没有可保留的旧 NPC，才清空并返回
        # 如果场景没有 NPC 但有待保留的旧 NPC（已恢复的），仍需处理保留逻辑
        if not scene_npcs:
            if not preserve_existing:
                self.active_npcs = {}
            # Bug 修复：如果有待保留的 NPC（来自 restore），在清空前先保留
            # 但如果 scene_npcs 为空且 preserve_existing=True，说明是"场景无 NPC"的情况，
            # 此时 restored NPCs 应该保留（因为它们已在上层 restore 中恢复到 active_npcs）
            # 只有当没有任何 NPC 来源时才需要处理
            if preserve_existing and old_npcs_by_key:
                # 有可保留的 NPC，确保它们在 active_npcs 中（它们应该已经在里面了，因为 restore）
                pass
            return
        
        # 如果需要保留已有 NPC，构建 name+role -> old_npc_data 的映射
        old_npcs_by_key = {}
        if preserve_existing:
            for npc_id, npc_data in self.active_npcs.items():
                key = self._npc_key(npc_data)
                if key:
                    old_npcs_by_key[key] = npc_data
        
        # 清空旧的，填充新的（保留匹配到的旧 NPC 数据）
        # 重要：使用 name+role 作为 key，确保跨场景身份稳定
        self.active_npcs = {}
        # 追踪已处理的 key（避免重复添加）
        processed_keys = set()
        
        for npc in scene_npcs:
            npc_id = npc.get("id") or npc.get("name")
            if npc_id:
                key = self._npc_key(npc)
                if not key:
                    # 没有有效的 name+role，使用 id 作为 key
                    key = npc_id
                
                if preserve_existing and key in old_npcs_by_key:
                    # 找到匹配的旧 NPC，保留状态
                    old_data = old_npcs_by_key[key]
                    merged = dict(npc)  # 新 NPC 数据作为基础
                    # 保留旧数据中的额外字段（如对话历史）
                    for k, v in old_data.items():
                        if k not in merged or not merged[k]:
                            merged[k] = v
                    # 保留旧数据的 id（用于 registry 查找）
                    merged["_id"] = old_data.get("id", npc_id)
                    self.active_npcs[key] = merged
                    logger.debug(f"Preserved NPC data for {key}")
                else:
                    # 新 NPC 或没有旧数据，使用 name+role 作为 key
                    self.active_npcs[key] = npc
                    logger.debug(f"Added new NPC: {key}")
                processed_keys.add(key)
        
        # 补充保留已被恢复但未被新场景替换的 NPC
        # 这确保了场景切换后，即使新场景没有某些旧 NPC，这些 NPC 仍然保留
        if preserve_existing:
            for key, old_data in old_npcs_by_key.items():
                if key not in processed_keys:
                    # 这个旧 NPC 在新场景中不存在，但仍需保留
                    self.active_npcs[key] = old_data
                    logger.debug(f"Retained restored NPC not in new scene: {key}")
        
        # 将场景 NPC 注册到 NPC Agent（如果 NPC agent 可用）
        # 这样后续对话可以使用完整的 NPC Agent 功能
        if self.npc_agent:
            try:
                from .npc_agent import NPCMetadata
                for npc_id, npc in self.active_npcs.items():
                    # 优先使用保留的旧 id
                    registry_id = npc.get("_id") or npc_id
                    # 检查是否已注册
                    existing = self.npc_agent.get_npc(registry_id)
                    if existing is None:
                        # 将 scene NPC dict 转换为 NPCMetadata 并注册
                        metadata = NPCMetadata(
                            id=registry_id,
                            name=npc.get("name", npc_id),
                            role=npc.get("role", "villager"),
                            disposition="neutral",
                            core_concept=npc.get("personality", ""),
                            tags=[],
                            appearance="",
                            personality=npc.get("personality", ""),
                            speech_style=npc.get("dialogue_style", ""),
                            secrets=[],
                            knowledge=[],
                            quests=[],
                            dialogue="",
                            created_at=0.0
                        )
                        self.npc_agent.registry.register(metadata)
            except Exception as e:
                logger.warning(f"Failed to register scene NPCs with NPC agent: {e}")
        
        logger.info(f"Scene NPC integration: {len(self.active_npcs)} NPCs active in {self.current_scene.get('type', 'unknown')} scene")
    
    def _npc_key(self, npc_data: dict) -> str | None:
        """
        生成 NPC 的唯一标识键（用于跨场景匹配同一个 NPC）
        
        使用 name + role 组合，因为这两个字段在场景切换时保持稳定。
        UUID 每次都会变，所以不能用于匹配。
        """
        name = npc_data.get("name", "")
        role = npc_data.get("role", "")
        if name and role:
            return f"{name}::{role}"
        return None
    
    def _format_scene_narrative(self, scene) -> str:
        """
        格式化场景叙事，包含 NPC 介绍和随机事件

        让玩家知道场景中有哪些可交互的 NPC，以及随机发生的事件
        """
        lines = []
        lines.append(f"\n{'='*40}")
        lines.append(f"📍 场景: {scene.type}")
        lines.append(f"{'='*40}")
        # 使用 current_scene 中的动态 atmosphere 描述（如果有）
        scene_desc = self.current_scene.get("description") or getattr(scene, "description", "")
        lines.append(f"\n{scene_desc}")
        
        # 添加动态 atmosphere 描述
        atm_desc = self.current_scene.get("atmosphere_desc", "")
        if atm_desc:
            lines.append(f"\n🌤️ {atm_desc}")

        # 展示随机注入的事件（场景差异化增强）
        scene_random_events = []
        if hasattr(scene, "random_events"):
            scene_random_events = scene.random_events
        else:
            scene_random_events = self.current_scene.get("random_events", [])
        
        if scene_random_events:
            lines.append(f"\n💫 正在发生的事:")
            for evt in scene_random_events:
                trigger = evt.get("trigger", "")
                event_text = evt.get("event", "")
                if trigger and event_text:
                    lines.append(f"  {trigger}，{event_text}")
                elif event_text:
                    lines.append(f"  {event_text}")

        # 介绍场景中的 NPC
        scene_npcs = scene.npcs if hasattr(scene, "npcs") else self.current_scene.get("npcs", [])
        if scene_npcs:
            lines.append(f"\n👥 场景中的人物:")
            for npc in scene_npcs:
                name = npc.get("name", "???")
                role = npc.get("role", "")
                personality = npc.get("personality", "")
                lines.append(f"  • {name} ({role}) - {personality}")
            lines.append(f"\n你可以与这些人交谈。")
        else:
            lines.append(f"\n这里似乎没有人。")

        # 介绍场景中的可交互物品
        scene_objs = scene.objects if hasattr(scene, "objects") else self.current_scene.get("objects", [])
        if scene_objs:
            lines.append(f"\n🔍 场景中似乎有些东西可以探索：")
            for obj in scene_objs:
                name = obj.get("name", "???")
                lines.append(f"  • {name}")
            lines.append(f"\n你可以「检查」「拾取」或「使用」这些东西。")
        else:
            lines.append(f"\n这里看起来没有特别值得探索的东西。")

        # ========== Fallback 降级模式警告 ==========
        # 检查是否需要显示降级警告
        if self._in_degradation_mode and not self._degradation_alert_shown:
            # 检查是否应该触发告警（连续 3 次降级）
            consecutive = self._degradation_tracker.consecutive_count
            if consecutive >= 3:
                lines.append(f"\n⚠️⚠️⚠️ 警告：系统已连续 {consecutive} 次使用简化叙事模式！")
                lines.append(f"   请检查网络连接或 API 配置。")
                lines.append(f"   如果问题持续存在，场景质量可能会下降。")
                lines.append(f"⚠️⚠️⚠️")
                self._degradation_alert_shown = True  # 避免重复显示
            else:
                lines.append(f"\n⚠️ 当前为简化叙事模式（降级 {consecutive} 次）")
        
        lines.append(f"{'='*40}\n")
        return "\n".join(lines)

    def _generate_fallback_scene_description(self, scene_type: str, quest_hint: str = "") -> str:
        """
        生成沉浸式的 fallback 场景描述（用于 scene_agent 不可用时）

        当 LLM API 不可用或 scene_agent 未初始化时，
        生成有沉浸感的场景描述，并将任务线索自然融入。
        """
        import random

        # 场景类型 → 沉浸式描述池
        scene_descriptions = {
            "酒馆": [
                "温暖的烛光在木质墙壁上投下摇曳的光影。空气中弥漫着麦酒和烤肉的香气，旅人们围坐在橡木桌旁，低声交谈。壁炉中的火焰噼啪作响，为整个空间增添了几分温馨。",
                "推开厚重的木门，一股混杂着麦酒香气的暖流扑面而来。酒馆内人声鼎沸，有人正在角落里弹奏着古老的民谣。老板是位圆胖的中年人，正熟练地擦拭着酒杯。",
                "昏黄的灯光下，酒客们的谈笑声此起彼伏。空气中飘荡着烟草和麦酒的味道，墙上的鹿头装饰在火光中显得格外神秘。",
            ],
            "森林": [
                "高大的古树遮天蔽日，阳光只能通过层层枝叶的缝隙洒下斑驳的光点。脚下是松软的落叶，踩上去发出轻微的沙沙声。远处传来不知名鸟儿的啼鸣。",
                "幽暗的树林中，迷雾在树干间缓缓流动。巨大的树根如同沉睡的巨兽，盘踞在蜿蜒的小径两旁。偶尔有不知名的小动物从灌木丛中窜过。",
                "穿过密集的灌木丛，眼前豁然开朗。古老的树木高耸入云，树干上爬满了青苔。空气中弥漫着泥土和野花的清香，让人心旷神怡。",
            ],
            "村庄": [
                "宁静的小村庄坐落在起伏的丘陵之间，石墙茅舍错落有致。村口的老槐树下，几位老人正在对弈，孩童们在巷弄间追逐嬉戏。炊烟从各家的烟囱中升起。",
                "月叶镇的街道由青石板铺成，两旁是木质结构的民居。镇子虽小，却透着一股温馨的生活气息。村民们各自忙碌着自己的事务。",
                "阳光洒在村庄的屋顶上，鸡犬相闻，孩童的笑声在巷弄间回荡。村口的小溪潺潺流过，几只鸭子在水中悠闲地游弋。",
            ],
            "城镇": [
                "宽阔的街道两旁商铺林立，旗幡在微风中轻轻飘动。城门口人来人往，商队的马车正在卸货，吆喝声此起彼伏。远处的钟楼传来悠长的钟声。",
            ],
            "城堡": [
                "巍峨的城堡矗立在山崖之上，灰色的石墙在阳光下显得庄严肃穆。穿过吊桥，映入眼帘的是宽阔的庭院，侍卫们身着铠甲在各个要道站岗。",
            ],
            "洞穴": [
                "幽暗的洞穴中只有零星的磷光照亮前路，冰冷的水珠从洞顶滴落。空气中弥漫着潮湿的霉味，隐约能听到深处传来的水流声。",
            ],
            "平原": [
                "一望无际的平原上，青草随风摇曳，形成层层波浪。远处的地平线与天空融为一体，几朵白云懒洋洋地飘在空中。",
            ],
            "河流": [
                "清澈的河水潺潺流过，河岸两侧长满了野花和灌木。河面上偶尔有鱼儿跃出水面，溅起晶莹的水花。",
            ],
        }

        default_descs = [
            "你来到了一片陌生的区域，四周静悄悄的，只有风吹过树叶的沙沙声。远处隐约可见一些建筑的轮廓。",
            "这里似乎是一个偏远的角落。地面上散落着一些奇怪的痕迹，似乎不久前有人经过。空气中弥漫着一股难以名状的气息。",
        ]

        base_desc = random.choice(scene_descriptions.get(scene_type, default_descs))

        # 将任务线索自然融入场景
        if quest_hint:
            hint_sentences = [
                f"就在这时，你注意到路边有人正在低声议论：{quest_hint}",
                f"你隐约听到过路的旅人说：「{quest_hint}」",
                f"一张破旧的告示贴在墙上：「{quest_hint}」",
                f"一位好心的村民提醒你：「{quest_hint}」",
                f"你回想起人们常说的一句话：{quest_hint}",
            ]
            hint_sentence = random.choice(hint_sentences)
            return f"{base_desc}\n\n{hint_sentence}"

        return base_desc

    # --------------------------------------------------------------------------
    # 探索指令处理 - look / search / move / talk
    # --------------------------------------------------------------------------

    async def _check_exploration_command(self, player_text: str, turn: int) -> str | None:
        """
        检查并处理显式探索指令：look / search / move / talk

        这些指令在检测到时直接返回叙事，不走通用叙事生成流程。
        只有在有当前场景时才处理这些指令。

        Returns:
            探索叙事文本，如果未匹配任何探索指令则返回 None
        """
        if not self.current_scene:
            return None

        text = player_text.strip().lower()
        original_text = player_text.strip()

        # === look: 查看周围环境 ===
        look_keywords = ["look", "查看", "环顾", "观察", "看四周", "看看周围", "看看这里"]
        if text in look_keywords or original_text in look_keywords:
            return await self._do_look(turn)

        # === search: 搜索场景中的隐藏事物 ===
        search_keywords = ["search", "搜索", "搜查", "搜寻", "找找", "搜索一下"]
        if text in search_keywords or original_text in search_keywords:
            return await self._do_search(turn)

        # === move: 移动（显式指令，优先级高于隐式场景切换）===
        # 只有当输入是纯粹的移动指令时（不含其他游戏动作）才走这个分支
        move_keywords = ["move", "移动", "走动", "前往"]
        # 检查是否只包含移动指令（不含交谈、攻击等）
        has_other_intent = any(kw in original_text for kw in ["交谈", "对话", "问", "和", "攻击", "打", "战斗"])
        if not has_other_intent and (text in move_keywords or original_text in move_keywords):
            return await self._do_move(original_text, turn)

        # === talk: 与NPC交谈（显式指令）===
        talk_keywords = ["talk", "交谈", "对话", "谈话"]
        if text in talk_keywords or original_text in talk_keywords:
            return await self._do_talk(original_text, turn)

        return None

    async def _do_look(self, turn: int) -> str:
        """执行 look 指令：详细描述当前场景"""
        scene = self.current_scene
        scene_type = scene.get("type", "未知")
        description = scene.get("description", "这里什么都没有。")
        atmosphere = scene.get("atmosphere", "")
        danger = scene.get("danger_level", "unknown")
        synopsis = scene.get("synopsis", "")

        lines = []
        lines.append(f"\n{'='*40}")
        lines.append(f"📍 场景: {scene_type}")
        if atmosphere:
            lines.append(f"🌙 氛围: {atmosphere}")
        lines.append(f"⚠️ 危险等级: {danger}")
        lines.append(f"{'='*40}")
        lines.append(f"\n{synopsis}")
        lines.append(f"\n{description}")

        # 介绍场景中的 NPC
        scene_npcs = scene.get("npcs", [])
        if scene_npcs:
            lines.append(f"\n👥 这里有:")
            for npc in scene_npcs:
                name = npc.get("name", "???")
                role = npc.get("role", "")
                personality = npc.get("personality", "")
                lines.append(f"  • {name} - {role}，{personality}")
        else:
            lines.append(f"\n👥 这里似乎没有人。")

        # 场景物品/特征
        unique_features = scene.get("unique_features", [])
        if unique_features:
            lines.append(f"\n🔍 值得注意的事物:")
            for feature in unique_features[:3]:
                lines.append(f"  • {feature}")

        lines.append(f"{'='*40}\n")
        return "\n".join(lines)

    async def _do_search(self, turn: int) -> str:
        """执行 search 指令：在场景中搜索隐藏事物"""
        import random

        scene = self.current_scene
        scene_type = scene.get("type", "unknown")
        unique_features = scene.get("unique_features", [])
        events = scene.get("events", [])
        danger = scene.get("danger_level", "mid")

        # 基于场景类型和危险等级决定搜索结果
        search_results_pool = []

        # 场景特定发现物
        scene_specific_findings = {
            "酒馆": [
                ("你在角落发现了一封被遗忘的信件，里面提到了一笔宝藏的线索。", "clue", "uncommon"),
                ("吧台下面藏着一枚古老的硬币，似乎是稀有文物。", "item", "common"),
                ("你注意到墙上有一块松动的砖块，后面似乎有东西...", "secret", "rare"),
                ("酒馆老板似乎对你多看了两眼，像是在打量你。", "social", "common"),
            ],
            "森林": [
                ("你拨开灌木丛，发现了一些可食用的浆果。", "item", "common"),
                ("地上有新鲜的脚印，似乎有人或野兽最近经过这里。", "clue", "common"),
                ("你在一棵老树上发现了一个隐藏的树洞，里面有一些金币。", "item", "uncommon"),
                ("你听到远处有水流的声音，似乎附近有溪流。", "clue", "common"),
            ],
            "村庄": [
                ("村口张贴着一张悬赏令，描述了一个通缉犯的特征。", "clue", "uncommon"),
                ("你注意到一个鬼鬼祟祟的身影溜进了小巷。", "clue", "common"),
                ("村长的家门口放着几束鲜花，似乎有人来探望过。", "social", "common"),
            ],
            "城镇": [
                ("广场公告板上有一张泛黄的地图，标注了一处遗迹的位置。", "clue", "uncommon"),
                ("你看到守卫在盘问一个行迹可疑的商人。", "social", "common"),
                ("街角有人在低声叫卖，似乎是违禁品。", "clue", "rare"),
            ],
            "城堡": [
                ("走廊的尽头有一扇半掩的门，里面传来微弱的光。", "clue", "uncommon"),
                ("墙上的一幅画像眼睛似乎会动...你再看时又恢复了正常。", "secret", "rare"),
                ("你发现地板有一块砖比其他的颜色略浅，似乎可以移动。", "secret", "rare"),
            ],
            "洞穴": [
                ("你注意到地面上有一些金属碎片，是武器的残骸。", "clue", "common"),
                ("洞壁上有人用矿石划出的记号，似乎在标记什么。", "clue", "uncommon"),
                ("角落里有一堆白骨，旁边散落着一个破旧的背包。", "item", "uncommon"),
            ],
        }

        findings = scene_specific_findings.get(scene_type, scene_specific_findings.get("村庄"))

        # 根据危险等级决定是否发现危险
        danger_findings = []
        if danger in ("high", "mid"):
            danger_findings = [
                ("你感觉到背后有目光在注视着你，一阵寒意袭来。", "danger", "common"),
                ("你注意到地上的痕迹变得混乱，似乎有东西在跟踪你。", "danger", "common"),
            ]

        all_findings = findings + danger_findings

        # 随机选择1-2个发现
        num_findings = random.randint(1, min(2, len(all_findings)))
        selected = random.sample(all_findings, num_findings)

        lines = []
        lines.append(f"\n{'='*40}")
        lines.append(f"🔍 搜索结果 (回合 {turn})")
        lines.append(f"{'='*40}")
        lines.append(f"\n你在{scene_type}中仔细搜索...")

        rarity_emoji = {"common": "📗", "uncommon": "📙", "rare": "📕", "danger": "⚠️"}

        for narrative, finding_type, rarity in selected:
            emoji = rarity_emoji.get(rarity, "📗")
            lines.append(f"\n{emoji} {narrative}")

        # 如果场景有独特特征，也可以作为搜索结果
        if unique_features and random.random() < 0.3:
            feature = random.choice(unique_features)
            lines.append(f"\n📍 你还注意到了: {feature}")

        lines.append(f"{'='*40}\n")
        return "\n".join(lines)

    async def _do_move(self, player_text: str, turn: int) -> str:
        """执行 move 指令：在场景中移动或前往新地点"""
        # 移动指令复用场景更新逻辑
        return await self._check_scene_update(player_text) or (
            f"\n[回合 {turn}] 你在原地待了一会儿。"
            f"\n如果想要前往其他地方，可以说「去酒馆」「前往森林」等。"
        )

    async def _do_talk(self, player_text: str, turn: int) -> str:
        """执行 talk 指令：与NPC交谈"""
        # 复用 NPC 交互检查
        npc_response = await self._check_npc_interaction(player_text)
        if npc_response:
            return npc_response

        # 如果没有检测到 NPC，返回提示
        scene_npcs = self.current_scene.get("npcs", []) if self.current_scene else []
        if scene_npcs:
            npc_names = [npc.get("name", "???") for npc in scene_npcs]
            names_str = "、".join(npc_names)
            return (
                f"\n[回合 {turn}] 你想和谁交谈？"
                f"\n这里有: {names_str}"
                f"\n可以说「和{npc_names[0]}交谈」来开始对话。"
            )
        else:
            return f"\n[回合 {turn}] 这里似乎没有人可以交谈。"

    async def _check_npc_interaction(self, player_text: str) -> str | None:
        """检查是否有 NPC 交互并生成 NPC 对话"""
        # 扩展关键词：不仅包括动作词，还包括称呼/打招呼类
        npc_keywords = [
            # 动作词
            "问", "和", "对", "说", "交谈", "对话", "询问", "跟",
            # 称呼/打招呼
            "你好", "打招呼", "搭讪", "称呼", "叫", "问好",
            # 针对某人的表达
            "老板", "老板说", "人说话", "跟他说", "跟它说",
            # 明确说要和人说话
            "和人", "和NPC", "和角色",
            # 英文动作词（修复 NPC 对话路由）
            "talk", "speak", "ask", "chat", "converse", "greet",
        ]

        text = player_text.lower()
        has_npc_intent = any(kw in text for kw in npc_keywords)

        # 如果没有匹配动作关键词，但场景中有 NPC，也尝试触发对话
        # （玩家可能在用简单的方式尝试和 NPC 说话）
        scene_has_npc = False
        if not has_npc_intent:
            scene_npcs = self.current_scene.get("npcs", []) if self.current_scene else []
            active_npc_count = len(self.active_npcs) if self.active_npcs else 0
            if scene_npcs or active_npc_count > 0:
                scene_has_npc = True

        if not has_npc_intent and not scene_has_npc:
            return None

        # NPC交互触发
        get_logger().info("game_master", f"NPC interaction triggered: player_input='{player_text[:50]}...'")

        # 如果有 NPC 但没有明确动作关键词，使用默认第一个 NPC
        # （场景中的匿名 NPC）
        npc_id = self._current_npc_id
        npc_name = None
        npc_data = None

        # 尝试确定目标 NPC
        npc_id = self._current_npc_id
        npc_name = None
        npc_data = None

        # 从当前场景的 NPC 列表中查找
        scene_npcs = self.current_scene.get("npcs", [])
        if not npc_id and scene_npcs:
            # 默认选择第一个 NPC
            npc_data = scene_npcs[0]
            npc_id = npc_data.get("id") or npc_data.get("name")
            npc_name = npc_data.get("name")

        # 从活跃 NPC 列表中查找
        if not npc_id and self.active_npcs:
            npc_data = next(iter(self.active_npcs.values()), None)
            npc_id = npc_data.get("id")
            npc_name = npc_data.get("name")

        # 如果没有 NPC，生成一个场景中的匿名 NPC
        if not npc_id:
            scene_type = self.current_scene.get("type", "村庄") if self.current_scene else "村庄"
            role_map = {
                "酒馆": "merchant", "城镇": "villager", "村庄": "villager",
                "森林": "mystic", "城堡": "guard", "洞穴": "criminal"
            }
            role = role_map.get(scene_type, "villager")
            scene_desc = self.current_scene.get("description", "") if self.current_scene else ""

            try:
                if self.npc_agent:
                    npc = await self.npc_agent.generate_npc(
                        role=role,
                        requirements="场景中的对话NPC",
                        scene_context=scene_desc
                    )
                    npc_id = npc.id
                    npc_name = npc.name
                    # 添加到活跃 NPC
                    self.active_npcs[npc_id] = npc.to_dict()
            except Exception as e:
                logger.warning(f"NPC generation failed: {e}")
                return f"\n[NPC] 一个身影回应道：\"有什么事？\"\n"

        # 使用 NPC Agent 生成对话
        if npc_id and self.npc_agent:
            try:
                npc = self.npc_agent.get_npc(npc_id)
                if npc:
                    # 记录NPC对话选择
                    self._record_choice("dialogue", f"与{npc.name}对话", player_text[:50])
                    # 追踪对话过的NPC
                    if npc.name not in self.quest_state.talked_to_npcs:
                        self.quest_state.talked_to_npcs.append(npc.name)
                    # 获取玩家画像（用于NPC对话调整）
                    player_profile = self.quest_state.get_player_profile()
                    result = await self.npc_agent.handle_dialogue(
                        npc, player_text,
                        context={
                            "scene": self.current_scene,
                            "location": self.game_state.get("location", "未知"),
                            "player_profile": player_profile,
                        }
                    )
                    response = result.get("response", "")
                    name = result.get("npc_name", npc_name or "???")
                    self._current_npc_id = npc_id  # 保持对话连贯
                    return f"\n【{name}】{response}\n"
            except Exception as e:
                logger.warning(f"NPC dialogue failed: {e}")

        # Fallback（无 NPC Agent 或 NPC 未注册时）- 使用场景 NPC 的上下文信息
        if npc_data:
            # 记录NPC对话选择
            name = npc_data.get("name", "???")
            self._record_choice("dialogue", f"与{name}对话", player_text[:50])
            personality = npc_data.get("personality", "")
            dialogue_style = npc_data.get("dialogue_style", "")
            role = npc_data.get("role", "")
            
            # 基于 personality 和 role 生成更贴合的 fallback 回复
            fallback_by_personality = {
                "merchant": ["「这可是好东西啊...」", "「你想要的，我这里都有。」", "「价格公道，童叟无欺。」"],
                "mystic": ["「命运的齿轮开始转动了...」", "「冥冥之中，自有定数。」", "「有些事...知道太多并非好事。」"],
                "guard": ["「站住！报上名来！」", "「城门规矩，不得擅离。」", "「小心行事，这里不太平。」"],
                "villager": ["「哎，最近不太平啊...」", "「你说的这事儿，我没听说过。」", "「有什么事吗，过路人？」"],
                "village_elder": ["「年轻后生，有何贵干？」", "「让我想想...」", "「此事说来话长。」"],
                "blacksmith": ["「哈！要打造什么？」", "「我这手艺，方圆百里数一数二！」", "「稍等，让我先看看这材料。」"],
                "child": ["「哇！你从哪里来的？」", "「我好无聊啊...」", "「妈妈说不要跟陌生人说话...」"],
            }
            
            responses = fallback_by_personality.get(role, fallback_by_personality.get("villager"))
            response_text = random.choice(responses)
            return f"\n【{name}】（{role}）{response_text}\n"
        
        fallback_responses = [
            "一个身影回应道：「嗯，让我想想...」",
            "神秘的声音响起：「这件事说来话长...」",
            "一个路人点点头：「你说的有道理。」",
        ]
        return f"\n[NPC] {random.choice(fallback_responses)}\n"

    # --------------------------------------------------------------------------
    # NPC 命令归一化路由
    # --------------------------------------------------------------------------

    def _format_npc_not_found(self) -> str:
        """格式化 NPC 未找到响应"""
        return "\n这里没有这个人...也许你可以描述得更具体一些？\n"

    async def _build_npc_context(self, npc_name: str) -> dict | None:
        """
        构建 NPC 上下文。
        
        Args:
            npc_name: NPC 名称
            
        Returns:
            NPC 数据字典，如果未找到则返回 None
        """
        # 先从 active_npcs 中查找（name+role 作为 key）
        for npc_id, npc_data in self.active_npcs.items():
            if npc_data.get("name") == npc_name:
                return npc_data
        
        # 从 current_scene 的 npcs 列表中查找
        scene_npcs = self.current_scene.get("npcs", []) if self.current_scene else []
        for npc in scene_npcs:
            if npc.get("name") == npc_name:
                return npc
        
        # 从 npc_agent 获取
        if self.npc_agent:
            npc = self.npc_agent.get_npc(npc_name)
            if npc:
                return npc.to_dict()
        
        return None

    async def _handle_npc_command(self, cmd_type: str, params: dict) -> str:
        """
        处理归一化后的 NPC 对话命令。
        """
        npc_name = params.get("npc_name")
        if not npc_name:
            return self._format_npc_not_found()

        npc_context = await self._build_npc_context(npc_name)
        if npc_context is None:
            return self._format_npc_not_found()

        if cmd_type == "npc_quest":
            return await self._handle_npc_quest(npc_name, npc_context)
        elif cmd_type == "npc_talk":
            return await self._handle_npc_talk(npc_name, npc_context)
        else:
            return await self._handle_npc_chat(npc_name, npc_context)

    async def _handle_npc_talk(self, npc_name: str, npc_context: dict) -> str:
        """处理 npc_talk 命令"""
        self._record_choice("dialogue", f"与{npc_name}交谈", f"命令类型=npc_talk")
        if npc_name not in self.quest_state.talked_to_npcs:
            self.quest_state.talked_to_npcs.append(npc_name)

        # 构建 prompt 让 NPC 自我介绍
        role = npc_context.get("role", "villager")
        personality = npc_context.get("personality", "friendly")
        scene_desc = self.current_scene.get("description", "") if self.current_scene else ""
        location = self.game_state.get("location", "未知")

        prompt = f"一个{npc_name}（身份：{role}，性格：{personality}）在{location}。"
        prompt += f"\n场景：{scene_desc}"
        prompt += f"\n玩家说：「和{npc_name}说话」。"
        prompt += f"\n请以{npc_name}的身份，生成一段自然的自我介绍或招呼。"

        try:
            if self.npc_agent:
                npc = self.npc_agent.get_npc(npc_context.get("id") or npc_name)
                if npc:
                    player_profile = self.quest_state.get_player_profile()
                    result = await self.npc_agent.handle_dialogue(
                        npc, f"和{npc_name}说话",
                        context={
                            "scene": self.current_scene,
                            "location": location,
                            "player_profile": player_profile,
                        }
                    )
                    response = result.get("response", "")
                    name = result.get("npc_name", npc_name)
                    self._current_npc_id = npc.id
                    return f"\n【{name}】{response}\n"
        except Exception as e:
            logger.warning(f"NPC talk failed: {e}")

        # Fallback
        role_greetings = {
            "酒馆老板": ["「哟，冒险者！欢迎光临月光酒馆！想喝点什么？」", "「哈哈，你来得正好，今天生意不错！」"],
            "merchant": ["「哟，想看看我的货物吗？」"],
            "guard": ["「站住！报上名来。」", "「嗯...有什么事？」"],
            "villager": ["「你好啊，陌生人。」", "「今天天气真不错。」"],
        }
        greetings = role_greetings.get(npc_name) or role_greetings.get(role, ["「你好。」"])
        return f"\n【{npc_name}】{random.choice(greetings)}\n"

    async def _handle_npc_quest(self, npc_name: str, npc_context: dict) -> str:
        """处理 npc_quest 命令"""
        self._record_choice("quest", f"向{npc_name}询问任务", f"命令类型=npc_quest")
        location = self.game_state.get("location", "未知")

        try:
            if self.npc_agent:
                npc = self.npc_agent.get_npc(npc_context.get("id") or npc_name)
                if npc:
                    player_profile = self.quest_state.get_player_profile()
                    result = await self.npc_agent.handle_dialogue(
                        npc, f"向{npc_name}询问任务",
                        context={
                            "scene": self.current_scene,
                            "location": location,
                            "player_profile": player_profile,
                        }
                    )
                    response = result.get("response", "")
                    name = result.get("npc_name", npc_name)
                    self._current_npc_id = npc.id
                    return f"\n【{name}】{response}\n"
        except Exception as e:
            logger.warning(f"NPC quest failed: {e}")

        # Fallback
        role_quests = {
            "酒馆老板": ["「要说任务...我确实听说森林里有狼出没。」", "「你可以去和酒客们聊聊，说不定能打听到什么。」"],
            "村长": ["「我们村子正受到森林怪物的威胁...」", "「如果你愿意帮忙，我会很感激。」"],
            "merchant": ["「任务？我这里可没有任务给你。」", "「去别处看看吧。」"],
        }
        quests = role_quests.get(npc_name) or ["「现在没有什么特别的事情。」"]
        return f"\n【{npc_name}】{random.choice(quests)}\n"

    async def _handle_npc_chat(self, npc_name: str, npc_context: dict) -> str:
        """处理 npc_chat 命令（闲聊）"""
        self._record_choice("dialogue", f"和{npc_name}聊天", f"命令类型=npc_chat")
        if npc_name not in self.quest_state.talked_to_npcs:
            self.quest_state.talked_to_npcs.append(npc_name)

        location = self.game_state.get("location", "未知")
        try:
            if self.npc_agent:
                npc = self.npc_agent.get_npc(npc_context.get("id") or npc_name)
                if npc:
                    player_profile = self.quest_state.get_player_profile()
                    result = await self.npc_agent.handle_dialogue(
                        npc, f"和{npc_name}聊聊天",
                        context={
                            "scene": self.current_scene,
                            "location": location,
                            "player_profile": player_profile,
                        }
                    )
                    response = result.get("response", "")
                    name = result.get("npc_name", npc_name)
                    self._current_npc_id = npc.id
                    return f"\n【{name}】{response}\n"
        except Exception as e:
            logger.warning(f"NPC chat failed: {e}")

        # Fallback
        role_chats = {
            "酒馆老板": ["「哈哈，聊聊天？好啊，今天生意不错！」", "「最近镇子里挺平静的。」"],
            "merchant": ["「哦？有什么想聊的吗？」"],
            "villager": ["「好啊，聊些什么呢？」", "「今天天气真不错。」"],
        }
        chats = role_chats.get(npc_name) or ["「嗯，聊聊天也不错。」"]
        return f"\n【{npc_name}】{random.choice(chats)}\n"

    async def _check_quest_trigger(self, player_text: str, npc_response: str | None) -> str | None:
        """
        检查并推进任务阶段

        Args:
            player_text: 玩家输入
            npc_response: NPC 响应（如果有）

        Returns:
            任务阶段推进的叙事（如果有）
        """
        if not self.quest_state.is_active():
            return None

        stage = self.quest_state.stage
        text_lower = player_text.lower()
        location = self.game_state.get("location", "")

        # ---- 阶段1: TALK_TO_MAYOR -> 对话后进入 GO_TO_TAVERN ----
        if stage == QuestStage.TALK_TO_MAYOR:
            # 检测到与镇长相关对话（镇长关键词或酒馆相关意图）
            mayor_keywords = ["镇长", "村长", " mayor", "village", "帮忙", "帮助", "森林", "怪物", "威胁"]
            tavern_keywords = ["酒馆", " tavern", "月光", "打听", "消息"]
            if any(kw in text_lower for kw in mayor_keywords + tavern_keywords):
                if npc_response:
                    self.quest_state.advance_to(QuestStage.GO_TO_TAVERN)
                    self.game_state["quest_stage"] = QuestStage.GO_TO_TAVERN.value
                    return "\n📜 任务更新：你决定前往月光酒馆打听情报。"

        # ---- 阶段2: GO_TO_TAVERN -> 到达酒馆后进入 GATHER_INFO ----
        if stage == QuestStage.GO_TO_TAVERN:
            tavern_locations = ["月光酒馆", "酒馆"]
            if any(loc in location for loc in tavern_locations) or any(loc in text_lower for loc in tavern_locations):
                self.quest_state.advance_to(QuestStage.GATHER_INFO)
                self.game_state["quest_stage"] = QuestStage.GATHER_INFO.value
                return "\n📜 任务更新：你已进入月光酒馆，可以向酒客打听森林的情报了。"

        # ---- 阶段3: GATHER_INFO -> 打听后进入 GO_TO_FOREST ----
        if stage == QuestStage.GATHER_INFO:
            gather_keywords = ["森林", "怪物", "情报", "消息", "打听", "问问", "问", "影狼", "危险"]
            if any(kw in text_lower for kw in gather_keywords) and npc_response:
                self.quest_state.advance_to(QuestStage.GO_TO_FOREST)
                self.game_state["quest_stage"] = QuestStage.GO_TO_FOREST.value
                self.quest_state.tavern_info_gathered = True
                return "\n📜 任务更新：获得了森林情报！是时候前往幽影森林了。"

        # ---- 阶段4: GO_TO_FOREST -> 进入森林后进入 DEFEAT_MONSTER ----
        if stage == QuestStage.GO_TO_FOREST:
            forest_locations = ["幽影森林", "森林"]
            if any(loc in location for loc in forest_locations) or any(loc in text_lower for loc in forest_locations):
                self.quest_state.advance_to(QuestStage.DEFEAT_MONSTER)
                self.game_state["quest_stage"] = QuestStage.DEFEAT_MONSTER.value
                return "\n📜 任务更新：你踏入了幽影森林！一头凶猛的影狼挡在了前方！准备战斗！"

        # ---- 阶段6: RETURN_TO_MAYOR -> 回到广场完成任务 ----
        if stage == QuestStage.RETURN_TO_MAYOR:
            plaza_locations = ["月叶镇广场", "广场", "月叶镇"]
            if any(loc in location for loc in plaza_locations) or any(loc in text_lower for loc in plaza_locations):
                # 检测对话意图
                if npc_response or any(kw in text_lower for kw in ["报告", "回报", "完成", "击败", "狼"]):
                    return await self._complete_quest()

        return None

    async def _complete_quest(self) -> str:
        """完成任务的奖励结算 + 多结局评定"""
        self.quest_state.advance_to(QuestStage.QUEST_COMPLETE)
        self.quest_state.completed = True
        self.game_state["quest_stage"] = QuestStage.QUEST_COMPLETE.value
        self.game_state["quest_active"] = False

        # 根据玩家选择链评定结局类型
        ending = self.quest_state.evaluate_ending()
        ending_narrative = self.quest_state.get_ending_narrative(ending)

        # 任务奖励（根据结局类型调整）
        reward_xp = 100
        reward_gold = 30

        player_stats = self.game_state["player_stats"]
        old_xp = player_stats["xp"]
        old_gold = player_stats["gold"]
        old_level = player_stats["level"]

        player_stats["xp"] += reward_xp
        player_stats["gold"] += reward_gold

        # 检查升级
        new_xp = player_stats["xp"]
        new_level = old_level
        for lvl in range(old_level + 1, len(self._LEVEL_XP_REQUIREMENTS)):
            if new_xp >= self._LEVEL_XP_REQUIREMENTS[lvl - 1]:
                new_level = lvl

        leveled_up = new_level > old_level
        if leveled_up:
            player_stats["level"] = new_level
            player_stats["max_hp"] = 30 + (new_level - 1) * 10
            player_stats["hp"] = player_stats["max_hp"]
            player_stats["ac"] = 12 + (new_level - 1) * 2

        level_msg = f"\n🎉 升级了！等级 {old_level} → {new_level}！" if leveled_up else ""

        # 结局叙事（取代固定的击败影狼叙事）
        return (
            f"\n{'='*40}\n"
            f"🎊 任务完成：《{QUEST_NAME}》\n"
            f"{'='*40}\n"
            f"{ending_narrative}\n"
            f"{'='*40}\n"
            f"🌟 经验值: +{reward_xp} XP (共 {player_stats['xp']} XP)\n"
            f"🪙 金币: +{reward_gold} 枚 (共 {player_stats['gold']} 枚)\n"
            f"{level_msg}\n"
            f"{'='*40}\n"
            f"📜 玩家选择记录: {len(self.game_state.get('player_choices', []))} 项\n"
            f"{'='*40}\n"
        )

    # --------------------------------------------------------------------------
    # 场景物品交互
    # --------------------------------------------------------------------------

    async def _check_object_interaction(self, player_text: str) -> str | None:
        """
        检查并处理场景物品交互（检查/拾取/使用）

        Returns:
            交互叙事文本，或 None（未触发物品交互）
        """
        text = player_text.strip()

        # 从当前场景获取物品列表
        scene_objs = self.current_scene.get("objects", []) if self.current_scene else []
        if not scene_objs:
            return None

        # 解析交互意图
        action = None  # "examine", "pickup", "use"
        object_name = None

        # 优先匹配最具体的模式
        examine_patterns = ["检查", "查看", "打量", "观察", "看", "look", "examine", "inspect"]
        pickup_patterns = ["拾取", "捡起", "拿起", "pick up", "pickup", "take"]
        use_patterns = ["使用", "用", "使用", "use", "interact"]

        for kw in examine_patterns:
            if kw in text:
                action = "examine"
                break
        for kw in pickup_patterns:
            if kw in text:
                action = "pickup"
                break
        for kw in use_patterns:
            if kw in text:
                action = "use"
                break

        if action is None:
            return None

        # 提取物品名称（去掉交互关键词后的文本）
        name_text = text
        for kw_list in [examine_patterns, pickup_patterns, use_patterns]:
            for kw in kw_list:
                if kw in name_text:
                    name_text = name_text.replace(kw, "")
                    break

        name_text = name_text.strip().strip('"').strip("'").strip("「").strip("」")

        if not name_text:
            return None

        # 模糊匹配物品（包含匹配，不区分大小写）
        target_obj = None
        name_lower = name_text.lower()
        for obj_data in scene_objs:
            obj_name = obj_data.get("name", "")
            if name_lower in obj_name.lower() or obj_name.lower() in name_lower:
                target_obj = obj_data
                break

        if target_obj is None:
            return None

        obj_name = target_obj.get("name", "???")
        obj_id = target_obj.get("id", "")

        # 格式化输出
        rarity_icons = {
            "common": "",
            "uncommon": "✨",
            "rare": "💎",
            "epic": "🔮",
            "legendary": "🌟",
        }
        rarity_icon = rarity_icons.get(target_obj.get("rarity", "common"), "")

        if action == "examine":
            # 检查物品
            base_desc = target_obj.get("description", "")
            extra = target_obj.get("on_examine", "")
            # 描述物品的状态
            lines = []
            lines.append(f"\n🔍 你仔细查看「{obj_name}」{rarity_icon}：")
            lines.append(f"  {base_desc}")
            if extra:
                lines.append(f"\n  {extra}")
            interaction_hints = []
            if target_obj.get("can_pickup"):
                interaction_hints.append("可以拾取")
            if target_obj.get("can_use"):
                interaction_hints.append("可以使用")
            if interaction_hints:
                lines.append(f"\n  💡 你发现：{'，'.join(interaction_hints)}")
            return "\n".join(lines)

        elif action == "pickup":
            if not target_obj.get("can_pickup", False):
                return f"\n📦 你试图拾取「{obj_name}」，但它不能被拾取。"

            pickup_narrative = target_obj.get("on_pickup", "")
            pickup_item = target_obj.get("pickup_item", "")
            pickup_gold = target_obj.get("pickup_gold", 0)

            lines = []
            lines.append(f"\n📦 你拾取了「{obj_name}」{rarity_icon}！")

            # 应用拾取效果
            if pickup_gold > 0:
                self.game_state["player_stats"]["gold"] += pickup_gold
                lines.append(f"💰 金币 +{pickup_gold}！")

            if pickup_item:
                inventory = self.game_state["player_stats"].get("inventory", [])
                inventory.append({"name": pickup_item, "rarity": target_obj.get("rarity", "common")})
                self.game_state["player_stats"]["inventory"] = inventory
                lines.append(f"📦 背包新增：{pickup_item}")

            if pickup_narrative:
                lines.append(f"\n  {pickup_narrative}")

            return "\n".join(lines)

        elif action == "use":
            if not target_obj.get("can_use", False):
                return f"\n✨ 你试着使用「{obj_name}」，但它似乎没有什么反应。"

            use_narrative = target_obj.get("on_use", "")
            effects = target_obj.get("effects", [])

            lines = []
            lines.append(f"\n✨ 你使用了「{obj_name}」{rarity_icon}：")

            # 应用效果
            for effect in effects:
                effect_type = effect.get("effect_type", "")
                value = effect.get("value", 0)
                if effect_type == "heal":
                    player_stats = self.game_state["player_stats"]
                    old_hp = player_stats["hp"]
                    player_stats["hp"] = min(player_stats["max_hp"], player_stats["hp"] + value)
                    actual_heal = player_stats["hp"] - old_hp
                    lines.append(f"💚 HP 恢复了 {actual_heal} 点！（当前 {player_stats['hp']}/{player_stats['max_hp']}）")
                elif effect_type == "add_gold":
                    self.game_state["player_stats"]["gold"] += value
                    lines.append(f"💰 金币 +{value}！")
                elif effect_type == "xp":
                    self.game_state["player_stats"]["xp"] += value
                    lines.append(f"🌟 经验 +{value} XP！")
                elif effect_type == "buff_attack":
                    lines.append(f"⚔️ 攻击力临时提升 +{value}！")
                elif effect_type == "buff_defense":
                    lines.append(f"🛡️ 防御力临时提升 +{value}！")
                elif effect_type == "reveal":
                    lines.append(f"👁️ 你获得了新的发现！")
                elif effect_type == "cure":
                    lines.append(f"💊 异常状态被解除！")

            if use_narrative:
                lines.append(f"\n  {use_narrative}")

            return "\n".join(lines)

        return None

    async def _generate_main_narrative(self, player_input: str, turn: int) -> str:
        """生成主叙事"""
        # 获取当前任务提示（传入当前 location，使提示能根据位置动态调整）
        quest_hint = ""
        if self.quest_state.is_active():
            current_location = self.current_scene.get("type", "") if self.current_scene else ""
            quest_hint = self.quest_state.get_stage_hint(current_location=current_location)

        base_narrative = f"[回合 {turn}] 你说道：\"{player_input}\"\n\n"

        if quest_hint:
            base_narrative += f"📜 任务提示：{quest_hint}\n\n"

        if self.current_scene:
            # 动态生成 atmosphere（不再是硬编码的静态值）
            # 计算连续探索轮次（用于 V2 差异化策略）
            consecutive_rounds = 1
            current_atm_state = None
            scene_type = self.current_scene.get("type", "")
            scene_id = self.current_scene.get("id", "")
            if self.scene_agent and hasattr(self.scene_agent, 'registry') and scene_id:
                atm_count = self.scene_agent.registry.get_atmosphere_count(scene_id)
                consecutive_rounds = atm_count + 1
                scene_obj = self.scene_agent.registry.get_by_id(scene_id)
                if scene_obj and scene_obj.atmosphere_history:
                    last_entry = scene_obj.atmosphere_history[-1]
                    current_atm_state = last_entry.get("state")
            
            # 调用 generate_atmosphere_v2 动态生成
            atm_result = generate_atmosphere_v2(
                scene_type=scene_type,
                consecutive_rounds=consecutive_rounds,
                current_state=current_atm_state,
            )
            atmosphere = atm_result.get("atmosphere", "神秘")
            
            # 如果没有其他具体的叙事内容，描述场景而不是简单地说"声音回荡"
            scene_name = self.current_scene.get("name", "")
            scene_desc = self.current_scene.get("description", "")

            # 场景描述更生动
            scene_details = []
            if scene_name and scene_name != scene_type:
                scene_details.append(f"在{scene_name}里")
            if atmosphere:
                scene_details.append(f"空气中弥漫着{atmosphere}的气息")

            if scene_details:
                base_narrative += "，".join(scene_details) + "。"
            else:
                base_narrative += "场景中的细节在你眼前展开..."
            
            # 将本次动态 atmosphere 记录到场景历史（用于下次差异化）
            if self.scene_agent and hasattr(self.scene_agent, 'registry') and scene_id:
                atm_data = {
                    "atmosphere": atm_result.get("atmosphere", ""),
                    "atmosphere_desc": atm_result.get("atmosphere_str", ""),
                    "atmosphere_tags": atm_result.get("atmosphere_tags", []),
                    "light": atm_result.get("light", ""),
                    "sound": atm_result.get("sound", ""),
                    "smell": atm_result.get("smell", ""),
                    "temperature": atm_result.get("temperature", ""),
                    "mood": atm_result.get("mood", ""),
                    "state": atm_result.get("state", {}),
                }
                self.scene_agent.registry.add_atmosphere_to_history(scene_id, atm_data)
        else:
            base_narrative += "..."

        return base_narrative

    # --------------------------------------------------------------------------
    # 存档系统
    # --------------------------------------------------------------------------

    def save(self, slot_id: int = 1) -> bool:
        """
        手动保存游戏
        
        Args:
            slot_id: 存档槽位 (1-4，默认 1)
            
        Returns:
            是否保存成功
        """
        if slot_id < 1 or slot_id >= AUTO_SAVE_SLOT:
            slot_id = 1  # 默认槽位
        return self.save_manager.save_game(self.game_state, slot_id)

    def load(self, slot_id: int) -> bool:
        """
        从存档加载游戏
        
        Args:
            slot_id: 存档槽位 ID
            
        Returns:
            是否加载成功
        """
        loaded_state = self.save_manager.load_game(slot_id)
        if loaded_state is None:
            return False
        
        self.game_state = loaded_state
        self.mode = GameMode.EXPLORATION
        self.current_scene = {}
        # 恢复 active_npcs（从 game_state 中取出，NPC 场景状态继承的关键）
        self.active_npcs = self.game_state.get("active_npcs", {})
        # 恢复按场景存储的 NPC（用于跨场景 NPC 持久化）
        self.game_state.setdefault("active_npcs_per_scene", {})
        self._current_npc_id = None
        self.combat_turn = 0
        self._pre_combat_scene = None
        self._pre_combat_location = "未知"
        self._pre_combat_narrative = ""
        self.game_over = self.game_state.get("game_over", False)
        # 恢复任务状态
        quest_stage_str = self.game_state.get("quest_stage", "not_started")
        try:
            self.quest_state = QuestState()
            self.quest_state.stage = QuestStage(quest_stage_str)
            self.quest_state.completed = quest_stage_str == QuestStage.QUEST_COMPLETE.value
        except ValueError:
            self.quest_state = QuestState()
        return True

    def new_game(self) -> None:
        """
        开始新游戏，重置所有状态
        """
        # 初始化新的游戏日志（每次 new_game 创建新的日志文件）
        log_file = init_game_log()
        get_logger().info("game_master", f"=== new_game() called, log file: {log_file} ===")
        
        self.mode = GameMode.EXPLORATION
        self.current_scene = {}
        self.active_npcs = {}
        self._current_npc_id = None
        self.combat_turn = 0
        self.game_state = {
            "turn": 0,
            "location": "未知",
            "player_stats": {
                "hp": 30,
                "max_hp": 30,
                "ac": 12,
                "xp": 0,
                "level": 1,
                "gold": 0,
                "inventory": [],
            },
            "game_over": False,
            "quest_stage": "not_started",
            "quest_active": False,
            "quest_name": QUEST_NAME,
            "difficulty": "normal",
            "player_choices": [],  # 玩家关键选择记录
            "active_npcs": {},  # NPC 场景状态继承：初始化为空
            "active_npcs_per_scene": {},  # NPC 场景状态继承：按场景存储 NPC
            "accessibility_options": {
                "color_contrast": "normal",  # 颜色对比度: "normal" | "high_contrast"
                "damage_colors": True,       # 战斗伤害数字着色: True | False
            },
        }
        self._pre_combat_scene = None
        self._pre_combat_location = "未知"
        self._pre_combat_narrative = ""
        self._last_enemy_name = "未知敌人"
        self.game_over = False
        self.quest_state = QuestState()
        self._pre_combat_scene = None
        self._pre_combat_location = "未知"
        self._pre_combat_narrative = ""
        self._last_enemy_name = "未知敌人"
        # 重置装备系统
        reset_equipment_manager()
        
        get_logger().info("game_master", "new_game() completed, game state reset")

    def set_difficulty(self, difficulty: str) -> bool:
        """
        设置游戏难度
        
        Args:
            difficulty: 难度名称 ("easy", "normal", "hard")
            
        Returns:
            是否设置成功
        """
        if difficulty not in ("easy", "normal", "hard"):
            return False
        self.game_state["difficulty"] = difficulty
        return True

    def get_difficulty(self) -> str:
        """获取当前难度"""
        return self.game_state.get("difficulty", "normal")

    def get_difficulty_info(self) -> dict[str, str]:
        """获取难度信息（用于 UI 显示）"""
        return {
            "easy": "简单：敌人 HP-30%，伤害-20%，掉落倍率×1.5",
            "normal": "普通：标准难度",
            "hard": "困难：敌人 HP+50%，伤害+30%，掉落倍率×0.5，无法逃跑",
        }

    # --------------------------------------------------------------------------
    # Accessibility（无障碍选项）
    # --------------------------------------------------------------------------

    def get_accessibility_options(self) -> dict:
        """获取无障碍选项"""
        return self.game_state.get("accessibility_options", {
            "color_contrast": "normal",
            "damage_colors": True,
        })

    def set_accessibility_option(self, key: str, value) -> bool:
        """
        设置无障碍选项

        Args:
            key: 选项名 ("color_contrast" | "damage_colors")
            value: 选项值

        Returns:
            是否设置成功
        """
        opts = self.game_state.setdefault("accessibility_options", {
            "color_contrast": "normal",
            "damage_colors": True,
        })
        if key == "color_contrast":
            if value not in ("normal", "high_contrast"):
                return False
            opts["color_contrast"] = value
            return True
        elif key == "damage_colors":
            opts["damage_colors"] = bool(value)
            return True
        return False

    def is_high_contrast(self) -> bool:
        """是否启用高对比度模式"""
        return self.game_state.get("accessibility_options", {}).get("color_contrast") == "high_contrast"

    def is_damage_colors_enabled(self) -> bool:
        """是否启用伤害数字着色"""
        return self.game_state.get("accessibility_options", {}).get("damage_colors", True)

    def get_save_info(self) -> list[dict]:
        """获取所有存档槽位的信息"""
        return self.save_manager.list_saves()

    def has_auto_save(self) -> bool:
        """检查是否存在自动存档"""
        return self.save_manager.has_auto_save()

    def get_auto_save_info(self) -> dict | None:
        """获取自动存档信息"""
        return self.save_manager.get_auto_save_info()

    async def _auto_save(self) -> None:
        """自动存档（在重要事件触发）"""
        self.save_manager.save_game(self.game_state, AUTO_SAVE_SLOT)
        logger.info("Auto-save triggered")

    # --------------------------------------------------------------------------
    # 奖励系统 - 战利品、经验值、升级
    # --------------------------------------------------------------------------

    # 敌人 XP 奖励表
    _XP_TABLE: dict[str, int] = {
        "史莱姆": 10,
        "哥布林": 25,
        "影狼": 30,
        "狼": 30,
        "骷髅": 35,
        "巨魔": 75,
        "森林巨魔": 80,
        "暗影盗贼": 55,
        "沼泽毒蟾": 40,
        "龙": 150,
        "巨龙": 200,
        "未知敌人": 20,
        "enemy_ambush": 20,
    }

    # 敌人金币奖励表
    _GOLD_TABLE: dict[str, tuple[int, int]] = {
        "史莱姆": (1, 5),
        "哥布林": (5, 15),
        "影狼": (5, 12),
        "狼": (3, 10),
        "骷髅": (8, 20),
        "巨魔": (20, 50),
        "森林巨魔": (25, 55),
        "暗影盗贼": (18, 40),
        "沼泽毒蟾": (10, 25),
        "龙": (50, 100),
        "巨龙": (80, 150),
        "未知敌人": (5, 15),
        "enemy_ambush": (5, 15),
    }

    # 敌人掉落物品表（物品名称 → 掉落权重 1-9）
    _LOOT_TABLE: dict[str, list[tuple[str, int]]] = {
        "史莱姆": [
            ("黏液精华", 5),  # 稀有度: uncommon
            ("治疗药水", 3),
            ("发霉的布料", 7),
        ],
        "哥布林": [
            ("生锈的短剑", 4),
            ("哥布林护符", 3),
            ("金币袋", 6),
            ("治疗药水", 4),
        ],
        "影狼": [
            ("狼皮", 5),
            ("锋利狼牙", 4),
            ("治疗药水", 3),
        ],
        "狼": [
            ("狼皮", 5),
            ("锋利狼牙", 4),
            ("治疗药水", 3),
        ],
        "骷髅": [
            ("骨头碎片", 5),
            ("骷髅指骨", 4),
            ("暗淡的戒指", 3),
            ("治疗药水", 4),
        ],
        "巨魔": [
            ("巨魔肉", 3),
            ("巨魔之牙", 4),
            ("治疗药水", 5),
            ("强力解毒剂", 3),
        ],
        "森林巨魔": [
            ("巨魔肉", 4),
            ("巨魔之牙", 5),
            ("治疗药水", 5),
            ("分裂碎片", 3),  # 稀有素材
        ],
        "暗影盗贼": [
            ("暗影匕首", 4),
            ("盗窃赃物", 5),
            ("治疗药水", 4),
            ("黑曜石戒指", 3),
        ],
        "沼泽毒蟾": [
            ("毒蟾蜍皮", 4),
            ("蟾毒素液", 5),
            ("治疗药水", 4),
            ("解毒剂", 3),
        ],
        "龙": [
            ("龙鳞", 5),
            ("龙血精华", 4),
            ("传说金币", 6),
            ("龙息药水", 3),
        ],
        "巨龙": [
            ("龙鳞", 4),
            ("龙血精华", 5),
            ("传说金币", 7),
            ("龙息药水", 4),
        ],
        "未知敌人": [
            ("战利品", 6),
            ("治疗药水", 4),
        ],
        "enemy_ambush": [
            ("战利品", 6),
            ("治疗药水", 4),
        ],
    }

    # 升级 XP 需求表（level → required XP cumulative）
    _LEVEL_XP_REQUIREMENTS: list[int] = [
        0,      # level 1
        50,     # level 2
        120,    # level 3
        250,    # level 4
        500,    # level 5
        1000,   # level 6
        2000,   # level 7
        4000,   # level 8
        8000,   # level 9
        15000,  # level 10
    ]

    async def _generate_rewards(self, enemy_name: str) -> dict[str, Any]:
        """
        生成战斗奖励（XP、金币、掉落物品）

        Args:
            enemy_name: 敌人名称

        Returns:
            dict with xp, gold, loot, leveled_up, new_level
        """
        xp_reward = self._XP_TABLE.get(enemy_name, 20)
        gold_min, gold_max = self._GOLD_TABLE.get(enemy_name, (5, 15))
        
        # 获取难度缩放配置
        difficulty_str = self.game_state.get("difficulty", "normal")
        difficulty = Difficulty(difficulty_str) if difficulty_str in ("easy", "normal", "hard") else Difficulty.NORMAL
        diff_cfg = DIFFICULTY_SCALING[difficulty]
        drop_mult = diff_cfg["drop_mult"]
        
        # 金币奖励也受难度影响（困难时减少，简单时增加）
        raw_gold = random.randint(gold_min, gold_max)
        gold_reward = max(1, int(raw_gold * drop_mult))

        # 升级检查
        player_stats = self.game_state["player_stats"]
        old_level = player_stats.get("level", 1)
        old_xp = player_stats.get("xp", 0)
        new_xp = old_xp + xp_reward
        new_level = old_level

        # 检查是否升级
        for lvl in range(old_level + 1, len(self._LEVEL_XP_REQUIREMENTS)):
            if new_xp >= self._LEVEL_XP_REQUIREMENTS[lvl - 1]:
                new_level = lvl

        # 计算升级奖励
        leveled_up = new_level > old_level

        # 掉落物品（应用难度掉落倍率）
        loot = self._roll_loot(enemy_name, drop_mult)

        # 更新玩家状态
        player_stats["xp"] = new_xp
        player_stats["gold"] = player_stats.get("gold", 0) + gold_reward
        if leveled_up:
            player_stats["level"] = new_level
            player_stats["max_hp"] = 30 + (new_level - 1) * 10
            player_stats["hp"] = player_stats["max_hp"]
            player_stats["ac"] = 12 + (new_level - 1) * 2

        # 添加掉落物品到背包
        inventory = player_stats.get("inventory", [])
        for item_name, rarity in loot:
            inventory.append({"name": item_name, "rarity": rarity})
        player_stats["inventory"] = inventory

        return {
            "xp": xp_reward,
            "gold": gold_reward,
            "loot": loot,
            "total_xp": new_xp,
            "leveled_up": leveled_up,
            "old_level": old_level,
            "new_level": new_level,
        }

    def _roll_loot(self, enemy_name: str, drop_mult: float = 1.0) -> list[tuple[str, str]]:
        """根据敌人类型掷骰掉落物品（受难度掉落倍率影响）"""
        loot_entries = self._LOOT_TABLE.get(enemy_name, [("战利品", 6)])
        loot = []
        for item_name, weight in loot_entries:
            # 应用掉落倍率：简单时更容易掉落，困难时更难掉落
            effective_weight = max(1, min(9, int(weight * drop_mult)))
            roll = random.randint(1, 9)
            if roll <= effective_weight:
                # 确定稀有度
                rarity_map = {
                    "黏液精华": "uncommon",
                    "发霉的布料": "common",
                    "治疗药水": "common",
                    "生锈的短剑": "common",
                    "哥布林护符": "uncommon",
                    "金币袋": "common",
                    "狼皮": "common",
                    "锋利狼牙": "uncommon",
                    "骨头碎片": "common",
                    "骷髅指骨": "uncommon",
                    "暗淡的戒指": "rare",
                    "巨魔肉": "uncommon",
                    "巨魔之牙": "rare",
                    "强力解毒剂": "uncommon",
                    "龙鳞": "epic",
                    "龙血精华": "legendary",
                    "传说金币": "epic",
                    "龙息药水": "epic",
                    "战利品": "common",
                }
                rarity = rarity_map.get(item_name, "common")
                loot.append((item_name, rarity))
        return loot

    async def _generate_rewards_narrative(
        self,
        enemy_name: str,
        rewards: dict[str, Any],
    ) -> str:
        """使用 LLM 生成奖励叙事"""
        xp = rewards["xp"]
        gold = rewards["gold"]
        loot = rewards["loot"]
        leveled_up = rewards["leveled_up"]
        new_level = rewards["new_level"]
        old_level = rewards["old_level"]
        total_xp = rewards["total_xp"]
        loot_str = "、".join([f"【{rarity.upper()}】{name}" for name, rarity in loot]) if loot else "无"

        next_level_xp = "已满级"
        if new_level < len(self._LEVEL_XP_REQUIREMENTS):
            next_level_xp = f"{self._LEVEL_XP_REQUIREMENTS[new_level] - total_xp} XP"

        get_logger().debug("game_master", f"LLM API call: _generate_rewards_narrative (enemy={enemy_name}, xp={xp}, gold={gold}, leveled_up={leveled_up})")

        if self.llm and self._llm_initialized:
            system = """你是一个沉浸式TRPG叙事专家。你为战斗胜利后的奖励生成生动的叙事。

【硬约束 - 禁止】
- 禁止使用"玩家正在..."、"玩家可以..."、"玩家选择..."等第三人称描述
- 禁止使用"作为你的 DM..."、"作为游戏主持人..."、"作为AI..."等暴露AI身份的话
- 禁止使用"AI"、"人工智能"、"语言模型"等暴露技术身份的字眼
- 禁止元叙事或跳出角色的评论

写作要求：
- 第二人称视角，庆祝胜利的兴奋感
- XP 和金币要有具体数字
- 物品掉落要标注稀有度颜色
- 升级要有仪式感和成就感
- 50-100字，中文输出"""

            prompt = f"""【战斗胜利】你击败了 {enemy_name}！

战利品清单:
- 经验值: +{xp} XP (总共 {total_xp} XP)
- 金币: +{gold} 枚金币
- 掉落物品: {loot_str}
- 距离下一级还需: {next_level_xp}
- {'🎉 升级了！' if leveled_up else '继续加油！'}

请生成一段庆祝胜利的奖励叙事，充满成就感。"""

            try:
                narrative = await self.llm.generate(prompt, system=system, temperature=0.6)
                if narrative and len(narrative) > 10:
                    return narrative
            except Exception as e:
                logger.warning(f"LLM rewards narrative failed: {e}")

        # Fallback 叙事
        loot_desc = ""
        if loot:
            loot_items = "、".join([name for name, _ in loot])
            loot_desc = f"\n📦 掉落物品: {loot_items}"

        level_msg = ""
        if leveled_up:
            old_max_hp = 30 + (old_level - 1) * 10
            new_max_hp = 30 + (new_level - 1) * 10
            old_ac = 12 + (old_level - 1) * 2
            new_ac = 12 + (new_level - 1) * 2
            level_msg = (
                f"\n🎉 升级了！等级 {old_level} → {new_level}！\n"
                f"   🩸 最大HP: {old_max_hp} → {new_max_hp}\n"
                f"   🛡️  护甲等级: {old_ac} → {new_ac}"
            )

        return (
            f"\n{'='*40}\n"
            f"⚔️  战斗胜利！\n"
            f"{'='*40}\n"
            f"🌟 经验值: +{xp} XP (共 {total_xp} XP){level_msg}\n"
            f"🪙 金币: +{gold} 枚 (共 {self.game_state['player_stats'].get('gold', 0)} 枚)\n"
            f"{loot_desc}\n"
            f"{'='*40}\n"
        )

    async def handle_player_message(self, text: str):
        """外部接口：处理玩家消息"""
        await self.event_bus.publish(Event(
            type=EventType.PLAYER_INPUT,
            data={"text": text},
            source="player"
        ))

    async def stop(self):
        """停止 GameMaster"""
        self._running = False
        await self.event_bus.unsubscribe_all(self._subscriber_id)
        logger.info("GameMaster stopped")


# 全局实例
_global_master: GameMaster | None = None


def get_game_master() -> GameMaster:
    """获取全局 GameMaster 实例"""
    global _global_master
    if _global_master is None:
        _global_master = GameMaster()
    return _global_master


async def init_game_master() -> GameMaster:
    """初始化全局 GameMaster"""
    master = get_game_master()
    await master.initialize()
    return master
