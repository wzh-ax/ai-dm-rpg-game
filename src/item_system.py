"""
Item System - 道具/物品系统
支持物品管理、效果应用、战斗中的物品使用

设计原则:
- 与战斗系统解耦,通过 EventBus 交互
- 物品分类型:消耗品、装备、任务道具、杂项
- 支持物品效果:治疗、伤害、增益、减益
- 物品可被发现、可被购买、可被使用
"""

import asyncio
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable

from .event_bus import EventBus, EventType, Event, get_event_bus

logger = logging.getLogger(__name__)


# ============================================================================
# 数据模型
# ============================================================================

class ItemType(str, Enum):
    """物品类型"""
    CONSUMABLE = "consumable"      # 消耗品(药水、食物)
    WEAPON = "weapon"              # 武器
    ARMOR = "armor"                # 护甲
    ACCESSORY = "accessory"        # 配饰
    QUEST = "quest"                # 任务道具(不可丢弃)
    MISC = "misc"                  # 杂项


class ItemEffectType(str, Enum):
    """物品效果类型"""
    HEAL = "heal"                  # 治疗
    DAMAGE = "damage"              # 伤害
    BUFF_ATTACK = "buff_attack"    # 攻击增益
    BUFF_DEFENSE = "buff_defense"  # 防御增益
    BUFF_SPEED = "buff_speed"      # 速度增益
    DEBUFF = "debuff"              # 减益
    CURE = "cure"                  # 解除状态
    REVEAL = "reveal"              # 揭示/侦查
    TELEPORT = "teleport"          # 传送
    SUMMON = "summon"              # 召唤


class ItemRarity(str, Enum):
    """物品稀有度"""
    COMMON = "common"              # 普通(白色)
    UNCOMMON = "uncommon"          # 优秀(绿色)
    RARE = "rare"                  # 稀有(蓝色)
    EPIC = "epic"                  # 史诗(紫色)
    LEGENDARY = "legendary"        # 传说(橙色)


@dataclass
class ItemEffect:
    """
    物品效果
    
    Attributes:
        effect_type: 效果类型
        value: 效果数值(治疗量、伤害量、增益百分比等)
        target_scope: 目标范围(SELF, SINGLE, AREA, ALL_ALLIES, ALL_ENEMIES)
        duration: 持续时间(回合),0表示立即生效
        description: 效果描述(用于叙事)
    """
    effect_type: ItemEffectType
    value: int = 0
    target_scope: str = "SELF"  # SELF, SINGLE, AREA, ALL_ALLIES, ALL_ENEMIES
    duration: int = 0            # 0 = immediate
    description: str = ""


@dataclass
class Item:
    """
    物品
    
    Attributes:
        id: 唯一标识
        name: 名称
        item_type: 类型
        description: 描述
        effects: 效果列表
        rarity: 稀有度
        stackable: 是否可堆叠
        quantity: 数量(可堆叠物品)
        price: 价格(游戏中货币)
        is_quest_item: 是否为任务道具
        usage_hint: 使用提示(用于叙事)
    """
    id: str
    name: str
    item_type: ItemType
    description: str = ""
    effects: list[ItemEffect] = field(default_factory=list)
    rarity: ItemRarity = ItemRarity.COMMON
    stackable: bool = False
    quantity: int = 1
    price: int = 0
    is_quest_item: bool = False
    usage_hint: str = ""


@dataclass
class InventorySlot:
    """物品栏格子"""
    index: int
    item: Item | None = None

    @property
    def is_empty(self) -> bool:
        return self.item is None


@dataclass
class Inventory:
    """
    物品栏
    
    Attributes:
        slots: 格子列表
        max_slots: 最大格子数
        gold: 货币数量
    """
    slots: list[InventorySlot] = field(default_factory=list)
    max_slots: int = 20
    gold: int = 0

    def __post_init__(self):
        if not self.slots:
            self.slots = [InventorySlot(index=i) for i in range(self.max_slots)]

    @property
    def used_slots(self) -> int:
        return sum(1 for s in self.slots if not s.is_empty)

    @property
    def free_slots(self) -> int:
        return sum(1 for s in self.slots if s.is_empty)

    @property
    def is_full(self) -> bool:
        return self.free_slots == 0


# ============================================================================
# 事件类型
# ============================================================================

class ItemEventType(str, Enum):
    """物品相关事件"""
    ITEM_ACQUIRED = "item_acquired"
    ITEM_USED = "item_used"
    ITEM_DISCARDED = "item_discarded"
    ITEM_EQUIPPED = "item_equipped"
    ITEM_UNEQUIPPED = "item_unequipped"
    INVENTORY_FULL = "inventory_full"


# ============================================================================
# 物品注册表
# ============================================================================

class ItemRegistry:
    """
    物品注册表
    
    管理所有已知物品模板,支持:
    - 按 ID 查询物品
    - 按类型筛选
    - 按标签筛选
    - 生成物品实例
    """

    def __init__(self):
        self._items: dict[str, Item] = {}
        self._hooks: dict[str, list[Callable]] = {
            "before_item_generation": [],
            "after_item_generation": [],
            "before_item_use": [],
            "after_item_use": [],
        }

    # --------------------------------------------------------------------------
    # 注册 & 查询
    # --------------------------------------------------------------------------

    def register(self, item: Item) -> None:
        """注册物品模板"""
        self._items[item.id] = item
        logger.debug(f"Registered item: {item.name} ({item.id})")

    def register_bulk(self, items: list[Item]) -> None:
        """批量注册物品"""
        for item in items:
            self.register(item)

    def get(self, item_id: str) -> Item | None:
        """按 ID 获取物品模板"""
        return self._items.get(item_id)

    def get_all(self) -> list[Item]:
        """获取所有物品"""
        return list(self._items.values())

    def get_by_type(self, item_type: ItemType) -> list[Item]:
        """按类型筛选"""
        return [i for i in self._items.values() if i.item_type == item_type]

    def get_by_rarity(self, rarity: ItemRarity) -> list[Item]:
        """按稀有度筛选"""
        return [i for i in self._items.values() if i.rarity == rarity]

    def get_quest_items(self) -> list[Item]:
        """获取所有任务道具"""
        return [i for i in self._items.values() if i.is_quest_item]

    def create_instance(self, item_id: str, quantity: int = 1) -> Item | None:
        """
        创建物品实例(从模板复制)
        
        Args:
            item_id: 物品模板 ID
            quantity: 数量
            
        Returns:
            新的物品实例,模板不存在返回 None
        """
        template = self.get(item_id)
        if not template:
            logger.warning(f"Item template not found: {item_id}")
            return None

        instance = Item(
            id=f"{template.id}_{id(self)}",
            name=template.name,
            item_type=template.item_type,
            description=template.description,
            effects=template.effects.copy(),
            rarity=template.rarity,
            stackable=template.stackable,
            quantity=quantity if template.stackable else 1,
            price=template.price,
            is_quest_item=template.is_quest_item,
            usage_hint=template.usage_hint,
        )
        return instance

    # --------------------------------------------------------------------------
    # 物品生成(LLM 驱动)
    # --------------------------------------------------------------------------

    async def generate_item(
        self,
        context: dict,
        item_type: ItemType | None = None,
        rarity: ItemRarity | None = None,
    ) -> Item | None:
        """
        LLM 驱动的物品生成
        
        Args:
            context: 生成上下文(场景信息、NPC 等)
            item_type: 指定类型(可选)
            rarity: 指定稀有度(可选)
            
        Returns:
            生成的物品实例
        """
        from .minimax_interface import get_llm_interface

        llm = get_llm_interface()
        if not llm:
            logger.error("LLM interface not available")
            return None

        # 构建 prompt
        type_hint = f"类型:{item_type.value}," if item_type else ""
        rarity_hint = f"稀有度:{rarity.value}," if rarity else ""

        prompt = f"""你是一个 RPG 游戏物品设计专家。

根据以下上下文,生成一个合理的游戏物品:

{type_hint}{rarity_hint}
场景:{context.get('scene_description', '未知')}
NPC:{context.get('npc_name', '无')}
玩家等级:{context.get('player_level', 1)}

要求:
1. 物品名称独特、有意义
2. 描述简洁但有画面感
3. 效果符合物品类型和稀有度
4. 物品要有 usage_hint(使用时的叙事提示)

以 JSON 格式返回:
{{
    "name": "物品名称",
    "item_type": "consumable|weapon|armor|accessory|quest|misc",
    "description": "物品描述",
    "effects": [
        {{
            "effect_type": "heal|damage|buff_attack|buff_defense|debuff|cure",
            "value": 数值,
            "target_scope": "SELF|SINGLE|AREA|ALL_ALLIES|ALL_ENEMIES",
            "duration": 0,
            "description": "效果叙事描述"
        }}
    ],
    "rarity": "common|uncommon|rare|epic|legendary",
    "stackable": true或false,
    "price": 价格数值,
    "usage_hint": "使用时的叙事提示"
}}
"""

        # 调用 LLM
        response = await llm.generate(prompt, [])
        if not response:
            return None

        # 解析 JSON
        import json
        try:
            data = json.loads(response)
        except json.JSONDecodeError:
            logger.error(f"Failed to parse item JSON: {response[:200]}")
            return None

        # 创建实例
        item = Item(
            id=f"generated_{id(self)}_{len(self._items)}",
            name=data.get("name", "未知物品"),
            item_type=ItemType(data.get("item_type", "misc")),
            description=data.get("description", ""),
            effects=[
                ItemEffect(
                    effect_type=ItemEffectType(e.get("effect_type", "misc")),
                    value=e.get("value", 0),
                    target_scope=e.get("target_scope", "SELF"),
                    duration=e.get("duration", 0),
                    description=e.get("description", ""),
                )
                for e in data.get("effects", [])
            ],
            rarity=ItemRarity(data.get("rarity", "common")),
            stackable=data.get("stackable", False),
            price=data.get("price", 0),
            is_quest_item=data.get("is_quest_item", False),
            usage_hint=data.get("usage_hint", ""),
        )

        self.register(item)
        return item

    # --------------------------------------------------------------------------
    # Hooks
    # --------------------------------------------------------------------------

    def add_hook(self, name: str, handler: Callable) -> None:
        """添加 Hook"""
        if name in self._hooks:
            self._hooks[name].append(handler)

    async def _emit_hook(self, name: str, context: dict) -> dict:
        """触发 Hook"""
        ctx = context.copy()
        for handler in self._hooks.get(name, []):
            try:
                if asyncio.iscoroutinefunction(handler):
                    ctx = await handler(ctx)
                else:
                    ctx = handler(ctx)
            except Exception as e:
                logger.error(f"Hook {name} failed: {e}")
        return ctx


# ============================================================================
# 物品栏管理器
# ============================================================================

class InventoryManager:
    """
    物品栏管理器
    
    管理玩家物品栏,支持:
    - 添加/移除物品
    - 使用物品
    - 整理物品栏
    - 与战斗系统联动
    """

    def __init__(self, inventory: Inventory | None = None):
        self.inventory = inventory or Inventory()
        self._event_bus = get_event_bus()
        self._equipped: dict[str, Item] = {}  # slot_name -> item

    # --------------------------------------------------------------------------
    # 基础操作
    # --------------------------------------------------------------------------

    def add_item(self, item: Item) -> bool:
        """
        添加物品到物品栏
        
        Returns:
            True if added, False if inventory full
        """
        # 可堆叠物品尝试合并
        if item.stackable:
            for slot in self.inventory.slots:
                if slot.item and slot.item.id == item.id:
                    slot.item.quantity += item.quantity
                    self._publish_event(ItemEventType.ITEM_ACQUIRED, {
                        "item": slot.item,
                        "quantity": item.quantity,
                    })
                    return True

        # 找空位
        if self.inventory.is_full:
            self._publish_event(ItemEventType.INVENTORY_FULL, {
                "item": item,
            })
            return False

        for slot in self.inventory.slots:
            if slot.is_empty:
                slot.item = item
                self._publish_event(ItemEventType.ITEM_ACQUIRED, {
                    "item": item,
                    "slot": slot.index,
                })
                return True

        return False

    def remove_item(self, item_id: str, quantity: int = 1) -> bool:
        """
        从物品栏移除物品
        
        Returns:
            True if removed, False if not found
        """
        for slot in self.inventory.slots:
            if slot.item and slot.item.id == item_id:
                if slot.item.quantity <= quantity:
                    slot.item = None
                else:
                    slot.item.quantity -= quantity
                self._publish_event(ItemEventType.ITEM_DISCARDED, {
                    "item_id": item_id,
                    "quantity": quantity,
                })
                return True
        return False

    def get_item(self, item_id: str) -> Item | None:
        """获取物品(按实例 ID)"""
        for slot in self.inventory.slots:
            if slot.item and slot.item.id == item_id:
                return slot.item
        return None

    def get_items_by_type(self, item_type: ItemType) -> list[Item]:
        """按类型获取物品"""
        return [
            slot.item
            for slot in self.inventory.slots
            if slot.item and slot.item.item_type == item_type
        ]

    def has_item(self, item_id: str) -> bool:
        """检查是否拥有某物品"""
        return self.get_item(item_id) is not None

    def has_quest_item(self, quest_item_id: str) -> bool:
        """检查是否拥有任务道具"""
        for slot in self.inventory.slots:
            if slot.item and slot.item.is_quest_item and slot.item.id == quest_item_id:
                return True
        return False

    # --------------------------------------------------------------------------
    # 物品使用
    # --------------------------------------------------------------------------

    async def use_item(self, item_id: str, target_id: str | None = None) -> dict:
        """
        使用物品
        
        Args:
            item_id: 物品实例 ID
            target_id: 目标 ID(玩家自己或敌人)
            
        Returns:
            使用结果字典
        """
        item = self.get_item(item_id)
        if not item:
            return {"success": False, "reason": "item_not_found"}

        if item.is_quest_item:
            return {"success": False, "reason": "quest_item_cannot_be_used"}

        results = []
        for effect in item.effects:
            result = await self._apply_effect(effect, target_id)
            results.append(result)

        # 消耗品使用后移除
        if item.item_type == ItemType.CONSUMABLE:
            self.remove_item(item_id, 1)

        self._publish_event(ItemEventType.ITEM_USED, {
            "item": item,
            "target_id": target_id,
            "results": results,
        })

        return {
            "success": True,
            "item": item,
            "results": results,
        }

    async def _apply_effect(self, effect: ItemEffect, target_id: str | None) -> dict:
        """应用物品效果"""
        result = {
            "effect_type": effect.effect_type,
            "value": effect.value,
            "success": True,
        }

        # 发布效果事件,供其他系统(如战斗系统)处理
        self._event_bus.publish(Event(
            type=EventType.ITEM_EFFECT,
            data={
                "effect_type": effect.effect_type,
                "value": effect.value,
                "target_id": target_id,
                "target_scope": effect.target_scope,
                "duration": effect.duration,
                "description": effect.description,
            },
        ))

        return result

    # --------------------------------------------------------------------------
    # 装备管理
    # --------------------------------------------------------------------------

    def equip_item(self, item_id: str, slot: str) -> bool:
        """
        装备物品
        
        Args:
            item_id: 物品实例 ID
            slot: 装备槽(weapon, armor, accessory_1, accessory_2)
        """
        item = self.get_item(item_id)
        if not item:
            return False

        if item.item_type not in (ItemType.WEAPON, ItemType.ARMOR, ItemType.ACCESSORY):
            return False

        # 卸下原装备
        if slot in self._equipped:
            old_item = self._equipped[slot]
            self._equipped[slot] = item
            self._publish_event(ItemEventType.ITEM_EQUIPPED, {
                "item": item,
                "slot": slot,
                "replaced": old_item,
            })
        else:
            self._equipped[slot] = item
            self._publish_event(ItemEventType.ITEM_EQUIPPED, {
                "item": item,
                "slot": slot,
            })
        return True

    def unequip_item(self, slot: str) -> Item | None:
        """卸下装备"""
        item = self._equipped.pop(slot, None)
        if item:
            self._publish_event(ItemEventType.ITEM_UNEQUIPPED, {
                "item": item,
                "slot": slot,
            })
        return item

    def get_equipped(self, slot: str) -> Item | None:
        """获取已装备物品"""
        return self._equipped.get(slot)

    def get_all_equipped(self) -> dict[str, Item]:
        """获取所有已装备物品"""
        return self._equipped.copy()

    # --------------------------------------------------------------------------
    # 辅助
    # --------------------------------------------------------------------------

    def _publish_event(self, event_type: ItemEventType, data: dict) -> None:
        """发布事件到事件总线(异步,不阻塞)"""
        # Map ItemEventType to EventType
        event_type_map = {
            ItemEventType.ITEM_ACQUIRED: EventType.ITEM_ACQUIRED,
            ItemEventType.ITEM_USED: EventType.ITEM_USED,
            ItemEventType.ITEM_DISCARDED: EventType.ITEM_DISCARDED,
            ItemEventType.ITEM_EQUIPPED: EventType.ITEM_EQUIPPED,
            ItemEventType.ITEM_UNEQUIPPED: EventType.ITEM_UNEQUIPPED,
            ItemEventType.INVENTORY_FULL: EventType.INVENTORY_FULL,
        }
        evt_type = event_type_map.get(event_type, EventType.GENERIC)
        # Fire-and-forget: schedule the coroutine as a task
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(self._event_bus.publish(Event(
                type=evt_type,
                data=data,
            )))
        except RuntimeError:
            # No running loop (tests), skip event publishing
            pass

    def to_dict(self) -> dict:
        """序列化为字典"""
        return {
            "inventory": {
                "slots": [
                    {"index": s.index, "item": {
                        "id": s.item.id,
                        "name": s.item.name,
                        "quantity": s.item.quantity,
                    } if s.item else None}
                    for s in self.inventory.slots
                ],
                "max_slots": self.inventory.max_slots,
                "gold": self.inventory.gold,
            },
            "equipped": {
                slot: {"id": item.id, "name": item.name}
                for slot, item in self._equipped.items()
            },
        }


# ============================================================================
# 全局实例
# ============================================================================

_item_registry: ItemRegistry | None = None
_inventory_manager: InventoryManager | None = None


def get_item_registry() -> ItemRegistry:
    """获取物品注册表全局实例"""
    global _item_registry
    if _item_registry is None:
        _item_registry = ItemRegistry()
    return _item_registry


def init_item_registry() -> ItemRegistry:
    """初始化物品注册表(带默认物品)"""
    registry = get_item_registry()

    # 注册默认物品模板
    default_items = [
        # 消耗品
        Item(
            id="health_potion_small",
            name="小型治疗药水",
            item_type=ItemType.CONSUMABLE,
            description="散发着温暖光芒的小瓶子,能恢复少量生命。",
            effects=[ItemEffect(
                effect_type=ItemEffectType.HEAL,
                value=20,
                target_scope="SELF",
                description="生命值恢复 20 点",
            )],
            rarity=ItemRarity.COMMON,
            stackable=True,
            price=10,
            usage_hint="你拧开瓶盖,淡蓝色的液体滑入喉咙,温暖在体内蔓延。",
        ),
        Item(
            id="health_potion_large",
            name="大型治疗药水",
            item_type=ItemType.CONSUMABLE,
            description="蕴含充沛生命力的金色药水。",
            effects=[ItemEffect(
                effect_type=ItemEffectType.HEAL,
                value=50,
                target_scope="SELF",
                description="生命值恢复 50 点",
            )],
            rarity=ItemRarity.UNCOMMON,
            stackable=True,
            price=30,
            usage_hint="你一饮而尽,金色的能量在血管中奔涌,伤口以肉眼可见的速度愈合。",
        ),
        Item(
            id="antidote",
            name="解毒剂",
            item_type=ItemType.CONSUMABLE,
            description="能解除中毒状态的药草精华。",
            effects=[ItemEffect(
                effect_type=ItemEffectType.CURE,
                value=0,
                target_scope="SELF",
                description="解除中毒状态",
            )],
            rarity=ItemRarity.COMMON,
            stackable=True,
            price=15,
            usage_hint="苦涩的药水吞下,体内的毒素被一点点中和。",
        ),
        Item(
            id="bomb",
            name="炸弹",
            item_type=ItemType.CONSUMABLE,
            description="简陋但有效的爆炸物。",
            effects=[ItemEffect(
                effect_type=ItemEffectType.DAMAGE,
                value=30,
                target_scope="AREA",
                description="对区域内所有敌人造成 30 点伤害",
            )],
            rarity=ItemRarity.UNCOMMON,
            stackable=True,
            price=25,
            usage_hint="你拉开引信,将炸弹投入敌群。轰然作响!",
        ),
        # 武器
        Item(
            id="rusty_sword",
            name="生锈长剑",
            item_type=ItemType.WEAPON,
            description="一把年久失修的剑,剑身布满锈迹。",
            effects=[ItemEffect(
                effect_type=ItemEffectType.DAMAGE,
                value=5,
                target_scope="SINGLE",
                description="+5 攻击伤害",
            )],
            rarity=ItemRarity.COMMON,
            stackable=False,
            price=5,
            usage_hint="你挥动生锈的长剑砍向敌人。",
        ),
        Item(
            id="steel_sword",
            name="精钢长剑",
            item_type=ItemType.WEAPON,
            description="工艺精良的钢制长剑,剑刃锋利。",
            effects=[ItemEffect(
                effect_type=ItemEffectType.DAMAGE,
                value=12,
                target_scope="SINGLE",
                description="+12 攻击伤害",
            )],
            rarity=ItemRarity.UNCOMMON,
            stackable=False,
            price=50,
            usage_hint="寒光一闪,精钢长剑划破空气。",
        ),
        Item(
            id="flame_blade",
            name="焰息长剑",
            item_type=ItemType.WEAPON,
            description="剑身缠绕着永恒燃烧的火焰。",
            effects=[
                ItemEffect(
                    effect_type=ItemEffectType.DAMAGE,
                    value=15,
                    target_scope="SINGLE",
                    description="+15 攻击伤害",
                ),
                ItemEffect(
                    effect_type=ItemEffectType.DEBUFF,
                    value=5,
                    target_scope="SINGLE",
                    duration=2,
                    description="附加灼烧,每回合 5 点伤害",
                ),
            ],
            rarity=ItemRarity.RARE,
            stackable=False,
            price=150,
            usage_hint="火焰随着剑锋舞动,炽热的气息扑面而来。",
        ),
        # 护甲
        Item(
            id="leather_armor",
            name="皮甲",
            item_type=ItemType.ARMOR,
            description="基础的皮革护甲。",
            effects=[ItemEffect(
                effect_type=ItemEffectType.BUFF_DEFENSE,
                value=3,
                target_scope="SELF",
                description="+3 护甲等级",
            )],
            rarity=ItemRarity.COMMON,
            stackable=False,
            price=20,
            usage_hint="你穿上皮甲,皮革的气息环绕周身。",
        ),
        Item(
            id="chainmail",
            name="锁子甲",
            item_type=ItemType.ARMOR,
            description="金属环编织而成的护甲,防护性不错。",
            effects=[ItemEffect(
                effect_type=ItemEffectType.BUFF_DEFENSE,
                value=6,
                target_scope="SELF",
                description="+6 护甲等级",
            )],
            rarity=ItemRarity.UNCOMMON,
            stackable=False,
            price=80,
            usage_hint="锁子甲的金属环哗啦作响,你感受到坚实的防护。",
        ),
        # 配饰
        Item(
            id="ring_of_speed",
            name="敏捷戒指",
            item_type=ItemType.ACCESSORY,
            description="刻有风系符文的银戒指。",
            effects=[ItemEffect(
                effect_type=ItemEffectType.BUFF_SPEED,
                value=2,
                target_scope="SELF",
                description="+2 先攻值",
            )],
            rarity=ItemRarity.RARE,
            stackable=False,
            price=100,
            usage_hint="戒指戴上手指,你感到身轻如燕。",
        ),
        # 任务道具
        Item(
            id="old_letter",
            name="泛黄的信",
            item_type=ItemType.QUEST,
            description="一封年代久远的信,上面的字迹已经模糊不清。",
            rarity=ItemRarity.RARE,
            stackable=False,
            price=0,
            is_quest_item=True,
            usage_hint="你展开信纸,试图辨认上面的文字...",
        ),
    ]

    registry.register_bulk(default_items)
    return registry


def get_inventory_manager() -> InventoryManager:
    """获取物品栏管理器全局实例"""
    global _inventory_manager
    if _inventory_manager is None:
        _inventory_manager = InventoryManager()
    return _inventory_manager


def init_inventory_manager() -> InventoryManager:
    """初始化物品栏管理器"""
    global _inventory_manager
    _inventory_manager = InventoryManager()
    return _inventory_manager
