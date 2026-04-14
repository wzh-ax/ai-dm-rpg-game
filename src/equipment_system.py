"""
Equipment System - 装备系统

为玩家提供装备槽位（武器、护甲、饰品），
影响 Combatant 的 attack_bonus 和 armor_class。

设计原则：
- 与战斗系统解耦，通过事件总线交互
- 装备槽：武器（Weapon）、护甲（Armor）、饰品（Accessory）
- 装备效果在战斗判定时应用
"""

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


# ============================================================================
# 装备槽
# ============================================================================

class EquipmentSlot(str, Enum):
    """装备槽类型"""
    WEAPON = "weapon"
    ARMOR = "armor"
    ACCESSORY = "accessory"


@dataclass
class EquipmentStats:
    """装备提供的属性加成"""
    attack_bonus: int = 0   # 攻击加成
    armor_bonus: int = 0    # 护甲加成
    max_hp_bonus: int = 0   # 最大生命加成
    flee_bonus: int = 0     # 逃跑成功率加成（百分比）


@dataclass
class Equipment:
    """
    装备物品
    
    Attributes:
        id: 唯一标识
        name: 名称
        slot: 装备槽
        stats: 属性加成
        description: 描述
    """
    id: str
    name: str
    slot: EquipmentSlot
    stats: EquipmentStats
    description: str = ""

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "slot": self.slot.value,
            "stats": {
                "attack_bonus": self.stats.attack_bonus,
                "armor_bonus": self.stats.armor_bonus,
                "max_hp_bonus": self.stats.max_hp_bonus,
                "flee_bonus": self.stats.flee_bonus,
            },
            "description": self.description,
        }


# ============================================================================
# 默认装备模板
# ============================================================================

DEFAULT_EQUIPMENT: dict[str, Equipment] = {
    # 新手短剑：+2 攻击
    "starter_sword": Equipment(
        id="starter_sword",
        name="新手短剑",
        slot=EquipmentSlot.WEAPON,
        stats=EquipmentStats(attack_bonus=2),
        description="一把朴素的新手短剑，虽不锋利但足以防身。",
    ),
    # 皮甲：+1 AC
    "leather_armor_piece": Equipment(
        id="leather_armor_piece",
        name="皮甲",
        slot=EquipmentSlot.ARMOR,
        stats=EquipmentStats(armor_bonus=1),
        description="简陋的皮革护甲，能提供基本的防护。",
    ),
    # 幸运护符：+5% 逃跑成功率
    "lucky_charm": Equipment(
        id="lucky_charm",
        name="幸运护符",
        slot=EquipmentSlot.ACCESSORY,
        stats=EquipmentStats(flee_bonus=5),
        description="一枚磨损的护符，据说能带来好运。",
    ),
    # 铁剑：+5 攻击
    "iron_sword": Equipment(
        id="iron_sword",
        name="铁剑",
        slot=EquipmentSlot.WEAPON,
        stats=EquipmentStats(attack_bonus=5),
        description="标准的铁制长剑，锋利耐用。",
    ),
    # 锁甲：+3 AC
    "chainmail_piece": Equipment(
        id="chainmail_piece",
        name="锁子甲",
        slot=EquipmentSlot.ARMOR,
        stats=EquipmentStats(armor_bonus=3),
        description="金属环编织而成，防护性不错。",
    ),
    # 敏捷护符：+2 先攻
    "swift_charm": Equipment(
        id="swift_charm",
        name="敏捷护符",
        slot=EquipmentSlot.ACCESSORY,
        stats=EquipmentStats(attack_bonus=1, flee_bonus=10),
        description="刻有风系符文的护符，让你身轻如燕。",
    ),
}


# ============================================================================
# 装备管理器
# ============================================================================

class EquipmentManager:
    """
    装备管理器
    
    管理玩家的装备槽，应用装备加成到战斗属性。
    """

    def __init__(self):
        # 装备槽: slot -> Equipment
        self._equipped: dict[EquipmentSlot, Equipment] = {}
        # 初始装备（新手装备）
        self._apply_default_equipment()

    def _apply_default_equipment(self):
        """给新玩家装备默认的新手装备"""
        self._equipped[EquipmentSlot.WEAPON] = DEFAULT_EQUIPMENT["starter_sword"]
        self._equipped[EquipmentSlot.ARMOR] = DEFAULT_EQUIPMENT["leather_armor_piece"]
        self._equipped[EquipmentSlot.ACCESSORY] = DEFAULT_EQUIPMENT["lucky_charm"]

    def equip(self, equipment: Equipment) -> bool:
        """
        装备物品
        
        Args:
            equipment: 装备物品
            
        Returns:
            True if equipped successfully
        """
        self._equipped[equipment.slot] = equipment
        logger.info(f"Equipped: {equipment.name} ({equipment.slot.value})")
        return True

    def unequip(self, slot: EquipmentSlot) -> Equipment | None:
        """卸下装备"""
        return self._equipped.pop(slot, None)

    def get_equipped(self, slot: EquipmentSlot) -> Equipment | None:
        """获取指定槽的已装备物品"""
        return self._equipped.get(slot)

    def get_all_equipped(self) -> dict[EquipmentSlot, Equipment]:
        """获取所有已装备物品"""
        return self._equipped.copy()

    def get_total_stats(self) -> EquipmentStats:
        """计算所有装备提供的总属性加成"""
        total = EquipmentStats()
        for eq in self._equipped.values():
            total.attack_bonus += eq.stats.attack_bonus
            total.armor_bonus += eq.stats.armor_bonus
            total.max_hp_bonus += eq.stats.max_hp_bonus
            total.flee_bonus += eq.stats.flee_bonus
        return total

    def get_attack_bonus(self) -> int:
        """获取总攻击加成"""
        return self.get_total_stats().attack_bonus

    def get_armor_bonus(self) -> int:
        """获取总护甲加成"""
        return self.get_total_stats().armor_bonus

    def get_flee_bonus(self) -> int:
        """获取逃跑加成（百分比）"""
        return self.get_total_stats().flee_bonus

    def get_max_hp_bonus(self) -> int:
        """获取最大生命加成"""
        return self.get_total_stats().max_hp_bonus

    def get_equipment_summary(self) -> list[dict[str, Any]]:
        """获取装备状态摘要（用于显示）"""
        result = []
        for slot in EquipmentSlot:
            eq = self._equipped.get(slot)
            if eq:
                result.append({
                    "slot": slot.value,
                    "name": eq.name,
                    "description": eq.description,
                    "stats": {
                        "attack_bonus": eq.stats.attack_bonus,
                        "armor_bonus": eq.stats.armor_bonus,
                        "max_hp_bonus": eq.stats.max_hp_bonus,
                        "flee_bonus": eq.stats.flee_bonus,
                    },
                })
            else:
                result.append({
                    "slot": slot.value,
                    "name": "无",
                    "description": "",
                    "stats": {},
                })
        return result

    def to_dict(self) -> dict:
        """序列化为字典"""
        return {
            slot.value: eq.to_dict()
            for slot, eq in self._equipped.items()
        }


# ============================================================================
# 全局实例
# ============================================================================

_equipment_manager: EquipmentManager | None = None


def get_equipment_manager() -> EquipmentManager:
    """获取全局装备管理器实例"""
    global _equipment_manager
    if _equipment_manager is None:
        _equipment_manager = EquipmentManager()
    return _equipment_manager


def reset_equipment_manager() -> EquipmentManager:
    """重置装备管理器（新游戏时调用）"""
    global _equipment_manager
    _equipment_manager = EquipmentManager()
    return _equipment_manager
