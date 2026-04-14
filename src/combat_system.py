"""
Combat System - 战斗系统
支持探索模式到战斗模式的切换,Round-based 严格回合制

设计原则(来自 gameplay/COMBAT.md):
- 独立于叙事系统,作为特色功能
- 初期简化版本,纯叙事 + 技能检定
- 后期扩展:LLM 生成战斗场景、动态事件
"""

import asyncio
import logging
import random
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable
from collections import deque

from .event_bus import EventBus, EventType, Event, get_event_bus
from .logging_system import get_logger

logger = logging.getLogger(__name__)


# ============================================================================
# 难度模式
# ============================================================================

class Difficulty(str, Enum):
    """游戏难度"""
    EASY = "easy"    # 简单：敌人 HP-30%，伤害-20%，掉落倍率×1.5
    NORMAL = "normal"  # 普通：标准数值
    HARD = "hard"    # 困难：敌人 HP+50%，伤害+30%，掉落倍率×0.5，无逃跑加成


# 难度缩放配置
DIFFICULTY_SCALING = {
    Difficulty.EASY: {
        "hp_mult": 0.7,      # HP ×0.7
        "damage_mult": 0.8,  # 伤害 ×0.8
        "drop_mult": 1.5,    # 掉落倍率 ×1.5
        "flee_bonus": True,  # 有逃跑加成
    },
    Difficulty.NORMAL: {
        "hp_mult": 1.0,
        "damage_mult": 1.0,
        "drop_mult": 1.0,
        "flee_bonus": True,
    },
    Difficulty.HARD: {
        "hp_mult": 1.5,      # HP ×1.5
        "damage_mult": 1.3,  # 伤害 ×1.3
        "drop_mult": 0.5,    # 掉落倍率 ×0.5
        "flee_bonus": False, # 无逃跑加成
    },
}


# ============================================================================
# 数据模型
# ============================================================================

class CombatantType(str, Enum):
    """战斗者类型"""
    PLAYER = "player"
    ENEMY = "enemy"
    ALLY = "ally"  # 后期扩展:友军NPC


class StatusEffect(str, Enum):
    """状态效果"""
    NORMAL = "normal"
    STUNNED = "stunned"
    POISONED = "poisoned"
    BLEEDING = "bleeding"
    DEFENDING = "defending"
    INVISIBLE = "invisible"


# 状态效果 emoji 标签（用于 UI 显示）
STATUS_EFFECT_EMOJI = {
    "stunned": "💫",
    "poisoned": "😈",
    "bleeding": "🩸",
    "defending": "🛡️",
    "invisible": "👻",
    "normal": "",
}


def get_status_emoji(status: StatusEffect) -> str:
    """获取状态效果对应的 emoji 标签"""
    return STATUS_EFFECT_EMOJI.get(status.value, "")


class ActionType(str, Enum):
    """战斗动作类型"""
    ATTACK = "attack"
    DEFEND = "defend"
    SKILL = "skill"
    ITEM = "item"
    FLEE = "flee"
    WAIT = "wait"


@dataclass
class Combatant:
    """
    战斗参与者
    
    Attributes:
        id: 唯一标识
        name: 名称
        combatant_type: 类型(玩家/敌人/友军)
        max_hp: 最大生命值
        current_hp: 当前生命值
        initiative: 先攻值(决定行动顺序)
        armor_class: 护甲等级(AC),攻击需要超过此值才能命中
        status: 当前状态效果
        is_active: 是否在场(False = 已被击败)
        description: 描述(用于叙事生成)
    """
    id: str
    name: str
    combatant_type: CombatantType
    max_hp: int
    current_hp: int
    initiative: int = 0
    armor_class: int = 10
    attack_bonus: int = 0  # 攻击加成（装备/等级提供）
    flee_bonus: int = 0   # 逃跑成功率加成（装备提供）
    status: StatusEffect = StatusEffect.NORMAL
    is_active: bool = True
    description: str = ""

    def __post_init__(self):
        # 如果初始HP为0,则视为已被击败
        if self.current_hp <= 0:
            self.is_active = False

    def take_damage(self, damage: int) -> int:
        """受到伤害,返回实际受到的伤害值(不低于0)"""
        actual = min(damage, self.current_hp)
        self.current_hp = max(0, self.current_hp - damage)
        if self.current_hp == 0:
            self.is_active = False
            self.status = StatusEffect.NORMAL
        return actual

    def heal(self, amount: int) -> int:
        """治疗,恢复生命值"""
        old_hp = self.current_hp
        self.current_hp = min(self.max_hp, self.current_hp + amount)
        return self.current_hp - old_hp

    def apply_status(self, status: StatusEffect):
        """应用状态效果"""
        self.status = status

    def is_alive(self) -> bool:
        return self.current_hp > 0 and self.is_active


@dataclass
class EnemyTemplate:
    """
    敌人模板定义
    
    Attributes:
        name: 敌人名称
        max_hp: 最大生命值
        armor_class: 护甲等级
        attack_bonus: 攻击加成
        damage_base: 基础伤害（1dX）
        damage_dice: 伤害骰子（如 6 表示 1d6）
        special_ability: 特殊能力名称
        special_params: 特殊能力参数
        xp_reward: 经验值奖励
        gold_min: 金币奖励最小值
        gold_max: 金币奖励最大值
        status_effect: 攻击时可能附加的状态效果
        description: 敌人描述
    """
    name: str
    max_hp: int
    armor_class: int
    attack_bonus: int = 0
    damage_base: int = 3
    damage_dice: int = 6
    special_ability: str = "normal"  # normal, split, ambush, poison
    special_params: dict = field(default_factory=dict)
    xp_reward: int = 20
    gold_min: int = 5
    gold_max: int = 15
    status_effect: StatusEffect | None = None
    description: str = ""


class EnemyFactory:
    """
    敌人工厂
    
    根据场景/等级生成不同类型的敌人。
    支持特殊能力（分裂、偷袭、中毒等）。
    """
    
    # 敌人类型注册表
    _templates: dict[str, EnemyTemplate] = {}
    
    @classmethod
    def register(cls, template: EnemyTemplate):
        """注册敌人模板"""
        cls._templates[template.name] = template
        logger.debug(f"Registered enemy template: {template.name}")
    
    @classmethod
    def get_template(cls, name: str) -> EnemyTemplate | None:
        """获取敌人模板"""
        return cls._templates.get(name)
    
    @classmethod
    def list_templates(cls) -> list[str]:
        """列出所有已注册的敌人模板"""
        return list(cls._templates.keys())
    
    @classmethod
    def create_enemy(cls, name: str, level: int = 1, difficulty: Difficulty = Difficulty.NORMAL) -> Combatant:
        """
        根据模板创建敌人实例（带等级缩放和难度缩放）
        
        Args:
            name: 敌人模板名称
            level: 玩家等级（用于缩放属性）
            difficulty: 游戏难度
            
        Returns:
            Combatant 实例
        """
        template = cls._templates.get(name)
        if not template:
            # Fallback: 使用默认狼属性
            template = cls._templates.get("影狼")
            if not template:
                raise ValueError(f"Unknown enemy: {name}")
        
        # 获取难度缩放
        diff_cfg = DIFFICULTY_SCALING.get(difficulty, DIFFICULTY_SCALING[Difficulty.NORMAL])
        
        # 等级缩放: HP +15%/级, AC +1/2级, 攻击 +1/2级
        scale_hp = 1.0 + (level - 1) * 0.15
        scale_ac = (level - 1) // 2
        scale_atk = (level - 1) // 2
        
        # 应用难度缩放（HP 在等级缩放之后乘以难度系数）
        scaled_hp = max(1, int(template.max_hp * scale_hp * diff_cfg["hp_mult"]))
        scaled_ac = template.armor_class + scale_ac
        scaled_atk = template.attack_bonus + scale_atk
        
        enemy = Combatant(
            id=f"enemy_{name}_{id(object())}",
            name=template.name,
            combatant_type=CombatantType.ENEMY,
            max_hp=scaled_hp,
            current_hp=scaled_hp,
            armor_class=scaled_ac,
            description=template.description,
        )
        # 扩展属性（战斗系统外部使用）
        enemy.attack_bonus = scaled_atk
        enemy.damage_base = template.damage_base
        enemy.damage_dice = template.damage_dice
        enemy.damage_mult = diff_cfg["damage_mult"]  # 难度伤害倍率
        enemy.special_ability = template.special_ability
        enemy.special_params = template.special_params
        enemy.xp_reward = template.xp_reward
        enemy.gold_min = template.gold_min
        enemy.gold_max = template.gold_max
        enemy.status_effect = template.status_effect
        enemy._template_name = template.name
        
        return enemy
    
    # 场景类型 → 通用怪物模板名称映射
    # 用于未知敌人触发战斗时的场景兜底
    _SCENE_GENERIC_ENEMY_MAP: dict[str, str] = {
        "森林": "森林狼",
        "洞穴": "蝙蝠",
        "酒馆": "野猪",
        "村庄": "野猪",
        "城镇": "野猪",
        "平原": "狼人",
        "城堡": "骷髅战士",
    }

    @classmethod
    def create_random_enemy(cls, level: int = 1, location: str = "", difficulty: Difficulty = Difficulty.NORMAL) -> tuple[Combatant, bool]:
        """
        根据场景随机创建敌人

        Args:
            level: 玩家等级
            location: 当前位置（影响敌人类型）
            difficulty: 游戏难度

        Returns:
            (Combatant, is_generic_fallback): 敌人实例，以及是否为通用怪物兜底
        """
        # 根据位置选择敌人池
        location_pools = {
            "森林": ["影狼", "森林巨魔"],
            "洞穴": ["暗影盗贼", "沼泽毒蟾"],
            "城镇": ["影狼"],
            "酒馆": ["影狼"],
            "平原": ["影狼"],
            "城堡": ["森林巨魔", "暗影盗贼"],
        }

        pool = ["影狼"]  # 默认
        is_generic = False

        # 先尝试用 location 匹配敌人池
        matched = False
        for loc_key, loc_pool in location_pools.items():
            if loc_key in location:
                pool = loc_pool
                matched = True
                break

        # 如果 location 没有匹配敌人池，尝试场景→通用怪物映射
        if not matched:
            generic_name = cls._SCENE_GENERIC_ENEMY_MAP.get(location)
            if generic_name:
                try:
                    enemy = cls.create_enemy(generic_name, level, difficulty)
                    return enemy, True  # is_generic=True
                except ValueError:
                    pass  # 模板不存在，回退到默认池

        name = random.choice(pool)
        enemy = cls.create_enemy(name, level, difficulty)
        return enemy, is_generic


# 注册默认敌人模板
def _register_default_enemies():
    """注册所有默认敌人模板"""
    templates = [
        # 影狼：速度快，中等攻击，低HP
        EnemyTemplate(
            name="影狼",
            max_hp=12,
            armor_class=11,
            attack_bonus=3,
            damage_base=2,
            damage_dice=6,
            special_ability="normal",
            xp_reward=30,
            gold_min=3,
            gold_max=10,
            description="幽暗的树林中，一双泛着绿光的眼睛盯着你。",
        ),
        # 森林巨魔：慢速，高攻击，高HP，会分裂
        EnemyTemplate(
            name="森林巨魔",
            max_hp=35,
            armor_class=14,
            attack_bonus=5,
            damage_base=4,
            damage_dice=8,
            special_ability="split",
            special_params={"split_hp": 15, "split_count": 2},
            xp_reward=75,
            gold_min=20,
            gold_max=50,
            description="身形巨大的绿色生物，肌肉虬结，再生能力惊人。",
        ),
        # 暗影盗贼：中等速度，中等攻击，先制攻击和偷袭（双倍伤害）
        EnemyTemplate(
            name="暗影盗贼",
            max_hp=22,
            armor_class=12,
            attack_bonus=4,
            damage_base=3,
            damage_dice=6,
            special_ability="ambush",
            special_params={"ambush_damage_mult": 2.0},
            xp_reward=50,
            gold_min=15,
            gold_max=35,
            description="潜伏在黑暗中的身影，手中匕首寒光闪烁。",
        ),
        # 沼泽毒蟾：低攻击，喷毒（每回合掉血debuff）
        EnemyTemplate(
            name="沼泽毒蟾",
            max_hp=18,
            armor_class=9,
            attack_bonus=2,
            damage_base=1,
            damage_dice=4,
            special_ability="poison",
            special_params={"poison_damage": 3, "poison_duration": 2},
            xp_reward=35,
            gold_min=8,
            gold_max=20,
            status_effect=StatusEffect.POISONED,
            description="浑身覆盖着粘稠毒液的巨大蟾蜍，令人作呕。",
        ),
        # 哥布林（原有）
        EnemyTemplate(
            name="哥布林",
            max_hp=15,
            armor_class=10,
            attack_bonus=2,
            damage_base=2,
            damage_dice=6,
            special_ability="normal",
            xp_reward=25,
            gold_min=5,
            gold_max=15,
            description="一个矮小但凶残的绿皮生物。",
        ),
        # 骷髅（原有）
        EnemyTemplate(
            name="骷髅",
            max_hp=18,
            armor_class=12,
            attack_bonus=3,
            damage_base=2,
            damage_dice=8,
            special_ability="normal",
            xp_reward=35,
            gold_min=8,
            gold_max=20,
            description="空洞的眼窝中闪烁着幽蓝的光芒。",
        ),
        # 史莱姆（原有）
        EnemyTemplate(
            name="史莱姆",
            max_hp=8,
            armor_class=8,
            attack_bonus=1,
            damage_base=1,
            damage_dice=4,
            special_ability="normal",
            xp_reward=10,
            gold_min=1,
            gold_max=5,
            description="一团黏糊糊的胶质生物，缓缓蠕动。",
        ),
        # 巨魔（原有）
        EnemyTemplate(
            name="巨魔",
            max_hp=35,
            armor_class=14,
            attack_bonus=5,
            damage_base=4,
            damage_dice=8,
            special_ability="normal",
            xp_reward=75,
            gold_min=20,
            gold_max=50,
            description="身形巨大的生物，皮肤坚韧如树皮。",
        ),
        # === 通用兜底怪物模板 ===
        # 森林狼：森林场景的兜底通用怪物
        EnemyTemplate(
            name="森林狼",
            max_hp=14,
            armor_class=11,
            attack_bonus=3,
            damage_base=2,
            damage_dice=6,
            special_ability="normal",
            xp_reward=28,
            gold_min=3,
            gold_max=10,
            description="一头灰色的森林狼，眼中闪烁着捕猎者的寒光。",
        ),
        # 蝙蝠：洞穴场景的兜底通用怪物
        EnemyTemplate(
            name="蝙蝠",
            max_hp=6,
            armor_class=8,
            attack_bonus=1,
            damage_base=1,
            damage_dice=4,
            special_ability="normal",
            xp_reward=8,
            gold_min=1,
            gold_max=4,
            description="成群的蝙蝠倒挂在洞顶，发出尖锐的吱吱声。",
        ),
        # 野猪：酒馆/村庄/城镇场景的兜底通用怪物
        EnemyTemplate(
            name="野猪",
            max_hp=18,
            armor_class=11,
            attack_bonus=3,
            damage_base=2,
            damage_dice=8,
            special_ability="normal",
            xp_reward=22,
            gold_min=4,
            gold_max=12,
            description="一头凶猛的野猪，獠牙闪着寒光，怒目圆睁。",
        ),
        # 狼人：平原场景的兜底通用怪物
        EnemyTemplate(
            name="狼人",
            max_hp=22,
            armor_class=12,
            attack_bonus=4,
            damage_base=3,
            damage_dice=6,
            special_ability="normal",
            xp_reward=40,
            gold_min=8,
            gold_max=18,
            description="月光下，一个身形魁梧的狼人缓缓站起，浑身散发着危险的气息。",
        ),
        # 骷髅战士：城堡场景的兜底通用怪物
        EnemyTemplate(
            name="骷髅战士",
            max_hp=20,
            armor_class=13,
            attack_bonus=4,
            damage_base=2,
            damage_dice=8,
            special_ability="normal",
            xp_reward=38,
            gold_min=8,
            gold_max=20,
            description="一副生锈铠甲包裹的骷髅，手持腐朽的剑柄，眼窝中幽火跳动。",
        ),
    ]
    
    for t in templates:
        EnemyFactory.register(t)


# 注册默认敌人
_register_default_enemies()


@dataclass
class CombatAction:
    """
    战斗动作
    
    Attributes:
        combatant_id: 动作发起者ID
        action_type: 动作类型
        target_id: 目标ID(攻击/治疗时)
        description: 动作描述(用于叙事)
        damage: 伤害值(攻击时)
        hit: 是否命中
        effect: 附加效果
    """
    combatant_id: str
    action_type: ActionType
    target_id: str | None = None
    description: str = ""
    damage: int = 0
    hit: bool = False
    effect: str = ""


# ============================================================================
# 战斗状态与事件
# ============================================================================

class CombatPhase(str, Enum):
    """战斗阶段"""
    NOT_STARTED = "not_started"
    INITIATIVE = "initiative"     # 先攻排序阶段
    IN_PROGRESS = "in_progress"   # 战斗中
    PLAYER_TURN = "player_turn"   # 玩家行动阶段
    ENEMY_TURN = "enemy_turn"     # 敌人行动阶段
    ROUND_END = "round_end"       # 回合结算
    COMBAT_END = "combat_end"     # 战斗结束


class CombatEventType(str, Enum):
    """战斗相关事件类型"""
    COMBAT_START = "combat_start"
    COMBAT_END = "combat_end"
    ROUND_START = "round_start"
    ROUND_END = "round_end"
    TURN_START = "turn_start"
    TURN_END = "turn_end"
    ACTION_RESOLVED = "action_resolved"
    COMBATANT_DOWN = "combatant_down"
    STATUS_APPLIED = "status_applied"


@dataclass
class CombatState:
    """
    战斗全局状态
    
    Attributes:
        combat_id: 战斗唯一ID
        phase: 当前阶段
        round: 当前轮次
        combatants: 所有参与者 {id: Combatant}
        turn_order: 当前轮次行动顺序(按initiative排序的ID列表)
        current_turn_index: 当前行动者在 turn_order 中的索引
        narrative_log: 叙事记录(最近20条)
        metadata: 附加元数据(场景描述等)
    """
    combat_id: str
    phase: CombatPhase = CombatPhase.NOT_STARTED
    round: int = 0
    combatants: dict[str, Combatant] = field(default_factory=dict)
    turn_order: list[str] = field(default_factory=list)
    current_turn_index: int = 0
    narrative_log: deque[str] = field(default_factory=lambda: deque(maxlen=20))
    metadata: dict = field(default_factory=dict)
    # WAIT action: 记录本轮执行过观望的 combatant(每人每轮只能观望一次)
    _waited_this_round: set[str] = field(default_factory=set)
    # WAIT action: 待执行的延迟行动者ID(观望后会在下一行动者之后再次行动)
    _pending_delayed_combatant_id: str | None = field(default=None)
    # 敌人特殊能力状态: {combatant_id: {"ambush_used": bool, "split_hp_tracked": int}}
    _enemy_special_state: dict[str, dict] = field(default_factory=dict)
    # 装备提供的逃跑加成(百分比): 战斗开始时从 Combatant 获取
    _flee_bonus: int = 0

    def add_narrative(self, text: str):
        """添加叙事记录"""
        self.narrative_log.append(text)

    def get_current_combatant(self) -> Combatant | None:
        """获取当前行动者"""
        if 0 <= self.current_turn_index < len(self.turn_order):
            cid = self.turn_order[self.current_turn_index]
            return self.combatants.get(cid)
        return None

    def get_active_combatants(self) -> list[Combatant]:
        """获取所有活跃参与者"""
        return [c for c in self.combatants.values() if c.is_active]

    def is_player_team_alive(self) -> bool:
        """玩家队伍是否还有人存活"""
        return any(
            c.is_active and c.combatant_type in (CombatantType.PLAYER, CombatantType.ALLY)
            for c in self.combatants.values()
        )

    def is_enemy_team_alive(self) -> bool:
        """敌人队伍是否还有人存活"""
        return any(
            c.is_active and c.combatant_type == CombatantType.ENEMY
            for c in self.combatants.values()
        )

    def get_summary(self) -> dict:
        """获取战斗状态摘要(用于叙事生成)"""
        return {
            "combat_id": self.combat_id,
            "round": self.round,
            "phase": self.phase.value,
            "current_turn": self.get_current_combatant().name if self.get_current_combatant() else None,
            "active_combatants": [
                {
                    "id": c.id,
                    "name": c.name,
                    "type": c.combatant_type.value,
                    "hp": c.current_hp,
                    "max_hp": c.max_hp,
                    "status": c.status.value,
                }
                for c in self.get_active_combatants()
            ],
            "narrative_log": list(self.narrative_log),
        }


# ============================================================================
# 战斗系统核心
# ============================================================================

class CombatSystem:
    """
    战斗系统主控
    
    负责:
    - 战斗初始化(先攻排序)
    - 回合流程控制
    - 动作结算(命中/伤害判定)
    - 状态效果处理
    - 战斗结束判定
    """

    def __init__(self, event_bus: EventBus | None = None):
        self._event_bus = event_bus or get_event_bus()
        self._active_combat: CombatState | None = None
        self._action_resolver: Callable[[CombatState, CombatAction], CombatAction] | None = None
        self._narrative_generator: Callable[[CombatState, CombatAction], str] | None = None
        self._running = False
        self._turn_task: asyncio.Task | None = None

    # ------------------------------------------------------------------------
    # 核心接口
    # ------------------------------------------------------------------------

    async def start_combat(
        self,
        combat_id: str,
        combatants: list[Combatant],
        metadata: dict | None = None,
    ) -> CombatState:
        """
        开始一场战斗
        
        Args:
            combat_id: 战斗唯一ID
            combatants: 参与者列表
            metadata: 附加元数据(场景描述等)
        
        Returns:
            初始化后的 CombatState
        """
        logger.info(f"Starting combat {combat_id} with {len(combatants)} combatants")
        get_logger().info("combat_system", f"=== Combat START: combat_id={combat_id}, combatants_count={len(combatants)}, combatants={[c.name for c in combatants]} ===")
        
        state = CombatState(
            combat_id=combat_id,
            phase=CombatPhase.INITIATIVE,
            combatants={c.id: c for c in combatants},
            metadata=metadata or {},
        )
        
        # 先攻排序
        await self._roll_initiative(state)
        
        state.phase = CombatPhase.IN_PROGRESS
        state.round = 1
        
        # 触发战斗开始事件
        await self._publish_combat_event(
            CombatEventType.COMBAT_START,
            {"state": state.get_summary()}
        )
        
        # 开始第一轮
        await self._start_round(state)
        
        self._active_combat = state
        return state

    async def submit_action(self, combatant_id: str, action: CombatAction) -> CombatState:
        """
        提交战斗动作(玩家/AI调用)
        
        Args:
            combatant_id: 动作发起者ID
            action: 战斗动作
        
        Returns:
            更新后的 CombatState
        """
        if not self._active_combat:
            raise RuntimeError("No active combat")
        
        if action.combatant_id != combatant_id:
            action.combatant_id = combatant_id
        
        # 解析动作
        resolved = await self._resolve_action(self._active_combat, action)
        
        # 触发动作结算事件
        await self._publish_combat_event(
            CombatEventType.ACTION_RESOLVED,
            {
                "action": {
                    "combatant_id": resolved.combatant_id,
                    "type": resolved.action_type.value,
                    "hit": resolved.hit,
                    "damage": resolved.damage,
                    "description": resolved.description,
                },
                "state": self._active_combat.get_summary(),
            }
        )
        
        # 推进到下一个行动者
        await self._advance_turn(self._active_combat)
        
        return self._active_combat

    async def end_combat(self, reason: str = "") -> CombatState | None:
        """
        结束当前战斗
        """
        if not self._active_combat:
            return None
        
        self._active_combat.phase = CombatPhase.COMBAT_END
        
        winner = "players" if self._active_combat.is_player_team_alive() else "enemies"
        
        await self._publish_combat_event(
            CombatEventType.COMBAT_END,
            {
                "state": self._active_combat.get_summary(),
                "winner": winner,
                "reason": reason,
            }
        )
        
        logger.info(f"Combat {self._active_combat.combat_id} ended: {winner} won")
        get_logger().info("combat_system", f"=== Combat END: combat_id={self._active_combat.combat_id}, winner={winner}, reason={reason} ===")
        
        result = self._active_combat
        self._active_combat = None
        return result

    def get_active_combat(self) -> CombatState | None:
        """获取当前活跃战斗状态"""
        return self._active_combat

    # ------------------------------------------------------------------------
    # 内部方法
    # ------------------------------------------------------------------------

    async def _roll_initiative(self, state: CombatState):
        """
        先攻排序
        
        每个 Combatant 有 initiative 值:
        - 玩家可手动输入或使用默认值
        - 敌人由系统随机生成(1d20 + 调整值)
        
        规则(简化版):
        - 按 initiative 从高到低排序
        - 同等级时玩家优先
        """
        import random
        
        for c in state.combatants.values():
            if c.initiative == 0:
                # 敌人随机生成先攻值
                if c.combatant_type == CombatantType.ENEMY:
                    c.initiative = random.randint(1, 20) + (c.armor_class // 3)
                else:
                    # 玩家默认10
                    c.initiative = 10
        
        # 排序:先攻值高的在前,同值时玩家优先
        state.turn_order = sorted(
            state.combatants.keys(),
            key=lambda cid: (
                state.combatants[cid].initiative,
                0 if state.combatants[cid].combatant_type == CombatantType.PLAYER else 1
            ),
            reverse=True
        )
        
        state.add_narrative(
            f"先攻顺序:{' → '.join(state.combatants[cid].name for cid in state.turn_order)}"
        )

    async def _start_round(self, state: CombatState):
        """开始新的一轮"""
        state.phase = CombatPhase.IN_PROGRESS
        state.round += 1
        state.current_turn_index = 0
        
        await self._publish_combat_event(
            CombatEventType.ROUND_START,
            {"round": state.round, "state": state.get_summary()}
        )
        
        await self._start_turn(state)

    async def _start_turn(self, state: CombatState):
        """开始单个行动者的回合"""
        combatant = state.get_current_combatant()
        if not combatant:
            logger.warning("No current combatant, ending round")
            await self._end_round(state)
            return
        
        # 眩晕效果:跳过本回合
        if combatant.status == StatusEffect.STUNNED:
            state.add_narrative(f"{combatant.name} 眩晕中,无法行动!")
            combatant.status = StatusEffect.NORMAL  # 眩晕解除
            await self._advance_turn(state)
            return
        
        state.phase = CombatPhase.PLAYER_TURN if combatant.combatant_type != CombatantType.ENEMY else CombatPhase.ENEMY_TURN
        
        await self._publish_combat_event(
            CombatEventType.TURN_START,
            {
                "combatant_id": combatant.id,
                "combatant_name": combatant.name,
                "state": state.get_summary(),
            }
        )

    async def _advance_turn(self, state: CombatState):
        """推进到下一个行动者"""
        state.current_turn_index += 1
        
        # 处理 WAIT 延迟:如果在下一行动者之后有待执行的延迟者,插入到当前位置
        if state._pending_delayed_combatant_id and state._pending_delayed_combatant_id not in state.turn_order[state.current_turn_index:]:
            delayed_id = state._pending_delayed_combatant_id
            # 在当前位置插入延迟者
            state.turn_order.insert(state.current_turn_index, delayed_id)
            state._pending_delayed_combatant_id = None
            # 注意:不立即开始他的回合,而是先让当前本来应该是下一个的行动者开始
            # 所以不 return,继续流程
        
        # 检查是否需要结束本轮
        if state.current_turn_index >= len(state.turn_order):
            await self._end_round(state)
            return
        
        # 检查战斗是否结束
        if not state.is_player_team_alive() or not state.is_enemy_team_alive():
            await self.end_combat()
            return
        
        await self._start_turn(state)

    async def _end_round(self, state: CombatState):
        """结束本轮"""
        state.phase = CombatPhase.ROUND_END
        
        # 触发回合结束事件(可用于处理持续状态效果等)
        await self._publish_combat_event(
            CombatEventType.ROUND_END,
            {"round": state.round, "state": state.get_summary()}
        )
        
        # 处理状态效果(每轮结束时的效果)
        await self._process_status_effects(state)
        
        # 重置本轮观望状态
        state._waited_this_round.clear()
        state._pending_delayed_combatant_id = None
        
        # 开始新的一轮
        await self._start_round(state)

    async def _process_status_effects(self, state: CombatState):
        """处理状态效果(回合结束时)"""
        for c in state.get_active_combatants():
            if c.status == StatusEffect.POISONED:
                dmg = max(1, c.max_hp // 10)
                c.take_damage(dmg)
                state.add_narrative(f"{c.name} 受到中毒伤害 {dmg} 点")
            elif c.status == StatusEffect.BLEEDING:
                dmg = max(1, c.max_hp // 20)
                c.take_damage(dmg)
                state.add_narrative(f"{c.name} 受到流血伤害 {dmg} 点")
            
            if not c.is_alive():
                await self._publish_combat_event(
                    CombatEventType.COMBATANT_DOWN,
                    {"combatant_id": c.id, "name": c.name}
                )

    async def _resolve_action(self, state: CombatState, action: CombatAction) -> CombatAction:
        """
        解析战斗动作(命中/伤害判定)
        
        简化规则(来自 COMBAT.md):
        - 攻击需要投骰 vs AC
        - 伤害 = 基础伤害 + 骰子结果
        """
        import random
        
        attacker = state.combatants.get(action.combatant_id)
        if not attacker:
            action.description = f"动作失败:{action.combatant_id} 不存在"
            return action
        
        get_logger().debug("combat_system", f"Combat action: combatant={attacker.name}, action_type={action.action_type.value}")
        
        if action.action_type == ActionType.ATTACK and action.target_id:
            target = state.combatants.get(action.target_id)
            if not target:
                action.description = f"动作失败:目标 {action.target_id} 不存在"
                return action
            
            # 命中判定:1d20 + 攻击加成 vs AC
            attack_roll = random.randint(1, 20)
            # 使用攻击者的 attack_bonus (含装备加成)
            attack_bonus = max(1, attacker.attack_bonus)
            # 防御姿态:目标AC+3
            effective_ac = target.armor_class
            if target.status == StatusEffect.DEFENDING:
                effective_ac += 3
            hit = attack_roll + attack_bonus >= effective_ac or attack_roll == 20
            # 重击:自然20必然命中且双倍伤害
            is_critical = attack_roll == 20
            action.hit = hit
            
            # --- 特殊能力处理: ambush (暗影盗贼) ---
            ambush_used = False
            special_state = state._enemy_special_state.get(attacker.id, {})
            if getattr(attacker, 'special_ability', None) == 'ambush':
                if not special_state.get('ambush_used', False):
                    # 偷袭:第一次攻击双倍伤害
                    ambush_used = True
                    special_state['ambush_used'] = True
                    state._enemy_special_state[attacker.id] = special_state
            
            if hit:
                # 难度伤害缩放（仅对敌人生效）
                damage_mult = getattr(attacker, 'damage_mult', 1.0)
                # 伤害计算:基础伤害 + 1d6
                base_damage = max(1, int((attacker.max_hp // 6) * damage_mult))
                damage_roll = random.randint(1, 6)
                total_damage = base_damage + damage_roll
                # 偷袭双倍
                if ambush_used:
                    total_damage *= 2
                    action.description += f"【偷袭!】"
                # 重击双倍
                if is_critical:
                    total_damage *= 2
                action.damage = total_damage
                
                actual = target.take_damage(action.damage)
                
                # --- 特殊能力处理: poison (沼泽毒蟾) ---
                if getattr(attacker, 'special_ability', None) == 'poison' and target.is_alive():
                    poison_params = getattr(attacker, 'special_params', {})
                    poison_dmg = poison_params.get('poison_damage', 3)
                    poison_dur = poison_params.get('poison_duration', 2)
                    target.apply_status(StatusEffect.POISONED)
                    state.add_narrative(f"【中毒】{target.name} 受到毒素侵蚀，每回合损失 {poison_dmg} HP，持续 {poison_dur} 回合!")
                
                # --- 特殊能力处理: split (森林巨魔) ---
                # 分裂：当森林巨魔击杀目标后分裂成小巨魔
                if getattr(attacker, 'special_ability', None) == 'split' and not target.is_alive():
                    split_params = getattr(attacker, 'special_params', {})
                    split_hp = split_params.get('split_hp', 15)
                    split_count = split_params.get('split_count', 2)
                    state.add_narrative(f"【分裂!】{attacker.name} 击杀 {target.name} 后身体分裂成 {split_count} 只小巨魔!")
                    for i in range(split_count):
                        small_troll_hp = split_hp // split_count
                        small_troll = Combatant(
                            id=f"enemy_小巨魔_{attacker.id}_{i}",
                            name=f"小巨魔",
                            combatant_type=CombatantType.ENEMY,
                            max_hp=small_troll_hp,
                            current_hp=small_troll_hp,
                            armor_class=max(8, attacker.armor_class - 3),
                            attack_bonus=max(0, attacker.attack_bonus - 2),
                        )
                        state.combatants[small_troll.id] = small_troll
                        state.turn_order.append(small_troll.id)
                    # 森林巨魔击杀后也倒下
                    attacker.take_damage(attacker.current_hp)
                
                if is_critical:
                    effect_tag = "【偷袭!】" if ambush_used else ""
                    crit_tag = "(重击!)" if is_critical else ""
                    action.description = (
                        f"{attacker.name} 重击 {target.name}! "
                        f"掷骰 {attack_roll}(重击!)+{attack_bonus} vs AC{effective_ac} = "
                        f"命中! {effect_tag}造成 {actual} 点伤害{crit_tag}"
                    )
                else:
                    effect_tag = "【偷袭!】" if ambush_used else ""
                    action.description = (
                        f"{attacker.name} 攻击 {target.name}!"
                        f"掷骰 {attack_roll}+{attack_bonus} vs AC{effective_ac} = "
                        f"命中,{effect_tag}造成 {actual} 点伤害"
                    )
                
                if not target.is_alive():
                    state.add_narrative(f"{target.name} 倒下了!")
                    await self._publish_combat_event(
                        CombatEventType.COMBATANT_DOWN,
                        {"combatant_id": target.id, "name": target.name}
                    )
            else:
                # 防御姿态:被攻击后解除防御
                if target.status == StatusEffect.DEFENDING:
                    target.status = StatusEffect.NORMAL
                action.description = (
                    f"{attacker.name} 攻击 {target.name}!"
                    f"掷骰 {attack_roll}+{attack_bonus} vs AC{effective_ac} = 未命中"
                )
        
        elif action.action_type == ActionType.DEFEND:
            attacker.apply_status(StatusEffect.DEFENDING)
            action.description = f"{attacker.name} 进入防御姿态(+3 AC)"
        
        elif action.action_type == ActionType.WAIT:
            # 观望:本回合什么都不做,在下一行动者之后再次行动
            # 每人每轮只能观望一次
            cid = action.combatant_id
            if cid in state._waited_this_round:
                action.description = f"{attacker.name} 已经观望过了,本轮无法再次观望"
            else:
                state._waited_this_round.add(cid)
                state._pending_delayed_combatant_id = cid
                action.description = f"{attacker.name} 观望局势,蓄势待发——将在下个行动者之后再次行动!"
        
        elif action.action_type == ActionType.FLEE:
            # 逃跑判定:1d20 + 逃跑加成 vs 10
            # 装备提供的 flee_bonus 是百分比，这里转换为加值
            flee_bonus = getattr(attacker, 'flee_bonus', 0)  # 装备加的逃跑加成
            base_threshold = 10
            effective_threshold = max(3, base_threshold - flee_bonus // 10)  # 每10%加成降低1点阈值
            flee_roll = random.randint(1, 20)
            if flee_roll >= effective_threshold:
                action.description = f"{attacker.name} 成功逃离战斗!"
                await self.end_combat(reason="玩家逃跑")
            else:
                action.description = f"{attacker.name} 逃跑失败!"
                # 逃跑失败会引发借机攻击,这里简化处理
        
        else:
            action.description = f"{attacker.name} 进行了 {action.action_type.value}"
        
        state.add_narrative(action.description)
        return action

    async def _publish_combat_event(self, event_type: CombatEventType, data: dict):
        """发布战斗事件到事件总线"""
        # 映射到 EventType(如果事件总线不支持 CombatEventType,用自定义类型)
        try:
            evt_type = EventType(event_type.value)
        except ValueError:
            # 自定义事件类型,尝试直接使用字符串
            evt_type = EventType.NARRATIVE_OUTPUT
        
        event = Event(
            type=evt_type,
            data=data,
            source="combat_system",
        )
        await self._event_bus.publish(event)

    # ------------------------------------------------------------------------
    # 可选:设置自定义解析器
    # ------------------------------------------------------------------------

    def set_action_resolver(self, resolver: Callable[[CombatState, CombatAction], CombatAction]):
        """设置自定义动作解析器(用于扩展LLM解析)"""
        self._action_resolver = resolver

    def set_narrative_generator(self, generator: Callable[[CombatState, CombatAction], str]):
        """设置自定义叙事生成器"""
        self._narrative_generator = generator


# ============================================================================
# 全局单例
# ============================================================================

_global_combat_system: CombatSystem | None = None


def get_combat_system() -> CombatSystem:
    """获取全局战斗系统实例"""
    global _global_combat_system
    if _global_combat_system is None:
        _global_combat_system = CombatSystem()
    return _global_combat_system


async def init_combat_system(event_bus: EventBus | None = None) -> CombatSystem:
    """初始化全局战斗系统"""
    global _global_combat_system
    _global_combat_system = CombatSystem(event_bus or get_event_bus())
    return _global_combat_system
