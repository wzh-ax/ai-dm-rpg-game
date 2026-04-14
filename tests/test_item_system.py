"""
Item System Tests - 道具/物品系统测试
"""

import pytest
from src.item_system import (
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
    init_item_registry,
    init_inventory_manager,
    get_item_registry,
    get_inventory_manager,
)


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def registry():
    """物品注册表 fixture"""
    return ItemRegistry()


@pytest.fixture
def inventory():
    """物品栏 fixture"""
    return Inventory(max_slots=5)


@pytest.fixture
def manager(inventory):
    """物品栏管理器 fixture"""
    return InventoryManager(inventory)


@pytest.fixture
def full_registry():
    """带默认物品的注册表"""
    return init_item_registry()


@pytest.fixture
def full_manager():
    """带默认物品的物品栏管理器"""
    init_inventory_manager()
    return get_inventory_manager()


# ============================================================================
# Item Model Tests
# ============================================================================

class TestItemModel:
    """Item 数据模型测试"""

    def test_create_basic_item(self):
        item = Item(
            id="test_sword",
            name="测试剑",
            item_type=ItemType.WEAPON,
        )
        assert item.id == "test_sword"
        assert item.name == "测试剑"
        assert item.item_type == ItemType.WEAPON
        assert item.quantity == 1
        assert item.stackable is False

    def test_create_item_with_effects(self):
        effects = [
            ItemEffect(
                effect_type=ItemEffectType.HEAL,
                value=30,
                target_scope="SELF",
            ),
            ItemEffect(
                effect_type=ItemEffectType.BUFF_ATTACK,
                value=5,
                target_scope="SELF",
                duration=3,
            ),
        ]
        item = Item(
            id="magic_potion",
            name="魔法药水",
            item_type=ItemType.CONSUMABLE,
            effects=effects,
            stackable=True,
            quantity=3,
        )
        assert len(item.effects) == 2
        assert item.effects[0].effect_type == ItemEffectType.HEAL
        assert item.effects[0].value == 30
        assert item.stackable is True
        assert item.quantity == 3

    def test_quest_item_flag(self):
        item = Item(
            id="key",
            name="神秘钥匙",
            item_type=ItemType.QUEST,
            is_quest_item=True,
        )
        assert item.is_quest_item is True
        assert item.item_type == ItemType.QUEST


# ============================================================================
# Inventory Tests
# ============================================================================

class TestInventory:
    """物品栏测试"""

    def test_create_inventory(self):
        inv = Inventory(max_slots=10)
        assert len(inv.slots) == 10
        assert inv.max_slots == 10
        assert inv.used_slots == 0
        assert inv.free_slots == 10
        assert inv.is_full is False

    def test_inventory_slots_empty(self):
        inv = Inventory(max_slots=5)
        assert all(slot.is_empty for slot in inv.slots)

    def test_inventory_is_full(self):
        inv = Inventory(max_slots=2)
        inv.slots[0].item = Item(id="a", name="A", item_type=ItemType.MISC)
        inv.slots[1].item = Item(id="b", name="B", item_type=ItemType.MISC)
        assert inv.is_full is True
        assert inv.free_slots == 0

    def test_inventory_used_slots_count(self):
        inv = Inventory(max_slots=5)
        inv.slots[0].item = Item(id="a", name="A", item_type=ItemType.MISC)
        inv.slots[2].item = Item(id="b", name="B", item_type=ItemType.MISC)
        assert inv.used_slots == 2
        assert inv.free_slots == 3


# ============================================================================
# ItemRegistry Tests
# ============================================================================

class TestItemRegistry:
    """物品注册表测试"""

    def test_register_item(self, registry):
        item = Item(id="potion", name="治疗药水", item_type=ItemType.CONSUMABLE)
        registry.register(item)
        assert registry.get("potion") == item

    def test_register_bulk(self, registry):
        items = [
            Item(id="sword", name="剑", item_type=ItemType.WEAPON),
            Item(id="shield", name="盾", item_type=ItemType.ARMOR),
        ]
        registry.register_bulk(items)
        assert len(registry.get_all()) == 2
        assert registry.get("sword") is not None
        assert registry.get("shield") is not None

    def test_get_nonexistent_item(self, registry):
        assert registry.get("nonexistent") is None

    def test_get_by_type(self, registry):
        registry.register_bulk([
            Item(id="potion", name="药水", item_type=ItemType.CONSUMABLE),
            Item(id="sword", name="剑", item_type=ItemType.WEAPON),
            Item(id="hp_potion", name="治疗药水", item_type=ItemType.CONSUMABLE),
        ])
        consumables = registry.get_by_type(ItemType.CONSUMABLE)
        assert len(consumables) == 2

    def test_get_by_rarity(self, registry):
        registry.register_bulk([
            Item(id="common_item", name="普通物品", item_type=ItemType.MISC, rarity=ItemRarity.COMMON),
            Item(id="rare_item", name="稀有物品", item_type=ItemType.MISC, rarity=ItemRarity.RARE),
        ])
        rare_items = registry.get_by_rarity(ItemRarity.RARE)
        assert len(rare_items) == 1
        assert rare_items[0].id == "rare_item"

    def test_get_quest_items(self, registry):
        registry.register_bulk([
            Item(id="normal_item", name="普通物品", item_type=ItemType.MISC),
            Item(id="quest_item", name="任务道具", item_type=ItemType.QUEST, is_quest_item=True),
        ])
        quest_items = registry.get_quest_items()
        assert len(quest_items) == 1
        assert quest_items[0].id == "quest_item"

    def test_create_instance(self, registry):
        template = Item(
            id="health_potion",
            name="治疗药水",
            item_type=ItemType.CONSUMABLE,
            stackable=True,
            price=10,
        )
        registry.register(template)

        instance = registry.create_instance("health_potion", quantity=5)
        assert instance is not None
        assert instance.name == "治疗药水"
        assert instance.quantity == 5
        assert instance.id != "health_potion"  # 新实例 ID 不同

    def test_create_instance_stackable_quantity(self, registry):
        template = Item(
            id="arrow",
            name="箭",
            item_type=ItemType.MISC,
            stackable=True,
        )
        registry.register(template)

        # 可堆叠物品创建实例，quantity 保持传入值
        instance = registry.create_instance("arrow", quantity=10)
        assert instance is not None
        assert instance.quantity == 10


# ============================================================================
# InventoryManager Tests
# ============================================================================

class TestInventoryManager:
    """物品栏管理器测试"""

    def test_add_item(self, manager):
        item = Item(id="sword", name="剑", item_type=ItemType.WEAPON)
        result = manager.add_item(item)
        assert result is True
        assert manager.has_item("sword") is True

    def test_add_item_to_full_inventory(self, manager):
        # 物品栏只有 5 格，全部占满
        for i in range(5):
            manager.add_item(Item(id=f"item_{i}", name=f"物品{i}", item_type=ItemType.MISC))

        # 尝试添加第 6 个物品
        new_item = Item(id="overflow", name="溢出物品", item_type=ItemType.MISC)
        result = manager.add_item(new_item)
        assert result is False

    def test_add_stackable_item(self, manager):
        """可堆叠物品应合并"""
        item1 = Item(id="potion", name="药水", item_type=ItemType.CONSUMABLE, stackable=True, quantity=2)
        item2 = Item(id="potion", name="药水", item_type=ItemType.CONSUMABLE, stackable=True, quantity=3)

        manager.add_item(item1)
        manager.add_item(item2)

        # 两次添加同一个可堆叠物品，应该合并
        found = manager.get_item("potion")
        assert found is not None
        assert found.quantity == 5  # 2 + 3 = 5

    def test_remove_item(self, manager):
        item = Item(id="sword", name="剑", item_type=ItemType.WEAPON)
        manager.add_item(item)

        result = manager.remove_item("sword")
        assert result is True
        assert manager.has_item("sword") is False

    def test_remove_item_partial_quantity(self, manager):
        item = Item(id="arrow", name="箭", item_type=ItemType.MISC, stackable=True, quantity=10)
        manager.add_item(item)

        manager.remove_item("arrow", quantity=3)
        remaining = manager.get_item("arrow")
        assert remaining is not None
        assert remaining.quantity == 7

    def test_get_items_by_type(self, manager):
        manager.add_item(Item(id="sword", name="剑", item_type=ItemType.WEAPON))
        manager.add_item(Item(id="potion", name="药水", item_type=ItemType.CONSUMABLE))
        manager.add_item(Item(id="shield", name="盾", item_type=ItemType.ARMOR))

        weapons = manager.get_items_by_type(ItemType.WEAPON)
        assert len(weapons) == 1
        assert weapons[0].id == "sword"

    def test_has_quest_item(self, manager):
        manager.add_item(Item(id="letter", name="信", item_type=ItemType.QUEST, is_quest_item=True))
        assert manager.has_quest_item("letter") is True
        assert manager.has_quest_item("nonexistent") is False

    def test_equip_weapon(self, manager):
        item = Item(id="steel_sword", name="钢剑", item_type=ItemType.WEAPON)
        manager.add_item(item)

        result = manager.equip_item("steel_sword", "weapon")
        assert result is True
        assert manager.get_equipped("weapon") == item

    def test_equip_non_equipment_item_fails(self, manager):
        item = Item(id="potion", name="药水", item_type=ItemType.CONSUMABLE)
        manager.add_item(item)

        result = manager.equip_item("potion", "weapon")
        assert result is False

    def test_unequip_item(self, manager):
        item = Item(id="steel_sword", name="钢剑", item_type=ItemType.WEAPON)
        manager.add_item(item)
        manager.equip_item("steel_sword", "weapon")

        unequipped = manager.unequip_item("weapon")
        assert unequipped == item
        assert manager.get_equipped("weapon") is None

    def test_to_dict(self, manager):
        item = Item(id="sword", name="剑", item_type=ItemType.WEAPON)
        manager.add_item(item)
        manager.equip_item("sword", "weapon")

        data = manager.to_dict()
        assert "inventory" in data
        assert "equipped" in data
        assert data["equipped"]["weapon"]["name"] == "剑"


# ============================================================================
# Default Items Tests
# ============================================================================

class TestDefaultItems:
    """默认物品测试"""

    def test_default_items_registered(self, full_registry):
        """验证默认物品已注册"""
        assert full_registry.get("health_potion_small") is not None
        assert full_registry.get("health_potion_large") is not None
        assert full_registry.get("antidote") is not None
        assert full_registry.get("bomb") is not None
        assert full_registry.get("rusty_sword") is not None
        assert full_registry.get("steel_sword") is not None
        assert full_registry.get("flame_blade") is not None
        assert full_registry.get("leather_armor") is not None
        assert full_registry.get("chainmail") is not None
        assert full_registry.get("ring_of_speed") is not None
        assert full_registry.get("old_letter") is not None

    def test_default_items_have_descriptions(self, full_registry):
        """默认物品应有描述"""
        for item in full_registry.get_all():
            assert item.description, f"Item {item.id} has no description"

    def test_default_items_have_usage_hint(self, full_registry):
        """非任务默认物品应有使用提示"""
        for item in full_registry.get_all():
            if not item.is_quest_item:
                assert item.usage_hint, f"Item {item.id} has no usage_hint"

    def test_quest_item_not_stackable(self, full_registry):
        """任务道具不可堆叠"""
        quest_items = full_registry.get_quest_items()
        for item in quest_items:
            assert item.stackable is False

    def test_consumables_are_stackable(self, full_registry):
        """消耗品应可堆叠"""
        consumables = full_registry.get_by_type(ItemType.CONSUMABLE)
        for item in consumables:
            assert item.stackable is True

    def test_weapons_not_stackable(self, full_registry):
        """武器不可堆叠"""
        weapons = full_registry.get_by_type(ItemType.WEAPON)
        for item in weapons:
            assert item.stackable is False


# ============================================================================
# Edge Cases
# ============================================================================

class TestEdgeCases:
    """边界情况测试"""

    @pytest.mark.asyncio
    async def test_use_item_not_found(self, manager):
        result = await manager.use_item("nonexistent_item")
        assert result["success"] is False
        assert result["reason"] == "item_not_found"

    @pytest.mark.asyncio
    async def test_use_quest_item_fails(self, manager):
        item = Item(id="quest_key", name="钥匙", item_type=ItemType.QUEST, is_quest_item=True)
        manager.add_item(item)

        result = await manager.use_item("quest_key")
        assert result["success"] is False
        assert result["reason"] == "quest_item_cannot_be_used"

    def test_create_instance_nonexistent_template(self, registry):
        """从不存在的模板创建实例应返回 None"""
        instance = registry.create_instance("nonexistent")
        assert instance is None

    def test_manager_with_no_items(self, manager):
        """空物品栏状态"""
        assert manager.inventory.used_slots == 0
        assert manager.inventory.is_full is False
        assert manager.get_all_equipped() == {}

    def test_remove_item_not_found(self, manager):
        """移除不存在的物品"""
        result = manager.remove_item("nonexistent")
        assert result is False
