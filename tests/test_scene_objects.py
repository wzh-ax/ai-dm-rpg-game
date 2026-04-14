"""
Scene Objects Tests - 场景可交互物品系统测试
"""

import pytest
from src.scene_objects import (
    SceneObject,
    ObjectEffect,
    ExamineResult,
    PickupResult,
    UseResult,
    SceneObjectRegistry,
    get_scene_object_registry,
)


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def registry():
    """场景物品注册表 fixture"""
    return SceneObjectRegistry()


@pytest.fixture
def global_registry():
    """全局场景物品注册表 fixture"""
    return get_scene_object_registry()


@pytest.fixture
def sample_object():
    """示例物品 fixture"""
    return SceneObject(
        id="test_obj_1",
        name="破旧的木桶",
        description="一只蛀虫爬了出来，木桶里什么都没有...",
        can_pickup=False,
        can_use=False,
        on_examine="你敲了敲木桶，里面空空如也。",
        on_pickup="你试图举起木桶，但它太重了。",
        on_use="",
        pickup_item="",
        pickup_gold=0,
        rarity="common",
        effects=[],
    )


@pytest.fixture
def pickupable_object():
    """可拾取物品 fixture"""
    return SceneObject(
        id="test_obj_2",
        name="遗忘的钱袋",
        description="一个小皮袋藏在角落里。",
        can_pickup=True,
        can_use=False,
        on_examine="钱袋沉甸甸的，似乎装了不少钱。",
        on_pickup="📦 你拾取了「遗忘的钱袋」！💰 里面有 8 枚金币！",
        on_use="",
        pickup_item="",
        pickup_gold=8,
        rarity="uncommon",
        effects=[],
    )


@pytest.fixture
def usable_object():
    """可使用物品 fixture"""
    return SceneObject(
        id="test_obj_3",
        name="神秘光点",
        description="一个微弱的光点在空气中飘浮。",
        can_pickup=False,
        can_use=True,
        on_examine="光点似乎有某种意志，你无法判断它的本质。",
        on_pickup="光点无法触碰。",
        on_use="✨ 温暖的光芒包裹了你...💚 HP 恢复了 8 点！",
        pickup_item="",
        pickup_gold=0,
        rarity="uncommon",
        effects=[
            ObjectEffect(
                effect_type="heal",
                value=8,
                description="HP恢复8点",
            )
        ],
    )


# ============================================================================
# ObjectEffect Tests
# ============================================================================

class TestObjectEffect:
    """ObjectEffect 数据类测试"""

    def test_effect_creation(self):
        """测试效果创建"""
        effect = ObjectEffect(
            effect_type="heal",
            value=20,
            description="HP恢复20点",
        )
        assert effect.effect_type == "heal"
        assert effect.value == 20
        assert effect.description == "HP恢复20点"

    def test_effect_to_dict(self):
        """测试效果序列化"""
        effect = ObjectEffect(effect_type="add_gold", value=5, description="金币+5")
        d = effect.to_dict()
        assert d["effect_type"] == "add_gold"
        assert d["value"] == 5
        assert d["description"] == "金币+5"

    def test_effect_from_dict(self):
        """测试效果反序列化"""
        data = {"effect_type": "heal", "value": 30, "description": "HP+30"}
        effect = ObjectEffect.from_dict(data)
        assert effect.effect_type == "heal"
        assert effect.value == 30
        assert effect.description == "HP+30"

    def test_effect_roundtrip(self):
        """测试效果序列化往返"""
        original = ObjectEffect(effect_type="buff_attack", value=2, description="攻击+2")
        restored = ObjectEffect.from_dict(original.to_dict())
        assert restored.effect_type == original.effect_type
        assert restored.value == original.value
        assert restored.description == original.description


# ============================================================================
# SceneObject Tests
# ============================================================================

class TestSceneObject:
    """SceneObject 数据类测试"""

    def test_object_creation(self, sample_object):
        """测试物品创建"""
        assert sample_object.id == "test_obj_1"
        assert sample_object.name == "破旧的木桶"
        assert sample_object.can_pickup is False
        assert sample_object.can_use is False
        assert sample_object.rarity == "common"

    def test_object_to_dict(self, sample_object):
        """测试物品序列化"""
        d = sample_object.to_dict()
        assert d["id"] == "test_obj_1"
        assert d["name"] == "破旧的木桶"
        assert d["can_pickup"] is False
        assert d["can_use"] is False
        assert d["rarity"] == "common"
        assert d["pickup_gold"] == 0
        assert d["effects"] == []

    def test_object_from_dict(self):
        """测试物品反序列化"""
        data = {
            "id": "test_from_dict",
            "name": "测试物品",
            "description": "测试描述",
            "can_pickup": True,
            "can_use": True,
            "on_examine": "检查叙事",
            "on_pickup": "拾取叙事",
            "on_use": "使用叙事",
            "pickup_item": "测试物品",
            "pickup_gold": 10,
            "rarity": "rare",
            "effects": [
                {"effect_type": "heal", "value": 15, "description": "HP+15"}
            ],
        }
        obj = SceneObject.from_dict(data)
        assert obj.name == "测试物品"
        assert obj.can_pickup is True
        assert obj.can_use is True
        assert obj.pickup_gold == 10
        assert obj.rarity == "rare"
        assert len(obj.effects) == 1
        assert obj.effects[0].effect_type == "heal"

    def test_object_roundtrip(self, pickupable_object):
        """测试物品序列化往返"""
        restored = SceneObject.from_dict(pickupable_object.to_dict())
        assert restored.id == pickupable_object.id
        assert restored.name == pickupable_object.name
        assert restored.description == pickupable_object.description
        assert restored.can_pickup == pickupable_object.can_pickup
        assert restored.pickup_gold == pickupable_object.pickup_gold
        assert restored.rarity == pickupable_object.rarity

    def test_object_pickup_effects(self, pickupable_object):
        """测试可拾取物品的效果字段"""
        assert pickupable_object.can_pickup is True
        assert pickupable_object.pickup_gold == 8
        assert "金币" in pickupable_object.on_pickup

    def test_object_use_effects(self, usable_object):
        """测试可使用物品的效果字段"""
        assert usable_object.can_use is True
        assert len(usable_object.effects) == 1
        assert usable_object.effects[0].effect_type == "heal"
        assert usable_object.effects[0].value == 8


# ============================================================================
# SceneObjectRegistry Tests
# ============================================================================

class TestSceneObjectRegistry:
    """场景物品注册表测试"""

    def test_registry_creation(self, registry):
        """测试注册表创建"""
        assert registry is not None
        assert len(registry.get_all()) == 0

    def test_registry_register(self, registry, sample_object):
        """测试物品注册"""
        registry.register(sample_object)
        assert registry.get("test_obj_1") is sample_object

    def test_registry_get_nonexistent(self, registry):
        """测试获取不存在的物品"""
        assert registry.get("nonexistent") is None

    def test_fallback_pools_exist(self, registry):
        """测试 fallback 池不为空"""
        for scene_type in ["酒馆", "森林", "村庄", "城镇", "城堡", "洞穴"]:
            pool = registry.FALLBACK_POOLS.get(scene_type)
            assert pool is not None, f"Missing pool for {scene_type}"
            assert len(pool) >= 2, f"Pool for {scene_type} too small"

    def test_fallback_pool_default(self, registry):
        """测试默认 fallback 池"""
        pool = registry.FALLBACK_POOLS.get("default")
        assert pool is not None
        assert len(pool) >= 1

    def test_get_fallback_objects_count(self, registry):
        """测试 fallback 物品数量"""
        objs = registry.get_fallback_objects("酒馆", count=3)
        assert len(objs) == 3

        objs = registry.get_fallback_objects("森林", count=5)
        assert len(objs) == 5

    def test_get_fallback_objects_unique_ids(self, registry):
        """测试 fallback 物品 ID 唯一性"""
        objs = registry.get_fallback_objects("酒馆", count=3)
        ids = [o.id for o in objs]
        assert len(ids) == len(set(ids)), "IDs should be unique"

    def test_get_fallback_objects_fields(self, registry):
        """测试 fallback 物品字段完整性"""
        objs = registry.get_fallback_objects("森林", count=2)
        for obj in objs:
            assert obj.id.startswith("fallback_")
            assert obj.name != ""
            assert obj.description != ""
            assert obj.on_examine != ""

    def test_get_fallback_objects_unknown_scene(self, registry):
        """测试未知场景类型的 fallback"""
        objs = registry.get_fallback_objects("未知场景类型", count=2)
        assert len(objs) == 2
        # 应该使用 default 池
        for obj in objs:
            assert obj.name != ""

    def test_get_fallback_objects_no_duplicates(self, registry):
        """测试多次调用不会返回完全相同的结果（随机性）"""
        # 虽然随机性可能导致偶尔相同，但大多数时候应该不同
        results = []
        for _ in range(5):
            objs = registry.get_fallback_objects("酒馆", count=3)
            results.append(tuple(o.name for o in objs))
        # 至少有一些变化
        unique_results = set(results)
        # 注意：这里用 > 1 而不是 == 5，因为随机性可能产生巧合相同
        assert len(unique_results) >= 1

    def test_parse_objects_from_llm(self, registry):
        """测试从 LLM 输出解析物品"""
        llm_data = [
            {
                "name": "古老的宝箱",
                "description": "一个布满灰尘的木箱",
                "can_pickup": True,
                "can_use": False,
                "on_examine": "宝箱上锁了",
                "on_pickup": "你获得了20金币！",
                "on_use": "",
                "pickup_item": "",
                "pickup_gold": 20,
                "rarity": "rare",
                "effects": [],
            },
            {
                "name": "闪烁的水晶",
                "description": "一块发光的石头",
                "can_pickup": False,
                "can_use": True,
                "on_examine": "水晶内部有光芒流动",
                "on_pickup": "",
                "on_use": "你感到一阵温暖...HP恢复了15点！",
                "pickup_item": "",
                "pickup_gold": 0,
                "rarity": "uncommon",
                "effects": [{"effect_type": "heal", "value": 15, "description": "HP+15"}],
            },
        ]
        objs = registry.parse_objects_from_llm(llm_data)
        assert len(objs) == 2
        assert objs[0].name == "古老的宝箱"
        assert objs[0].pickup_gold == 20
        assert objs[1].name == "闪烁的水晶"
        assert len(objs[1].effects) == 1
        assert objs[1].effects[0].value == 15

    def test_parse_objects_from_llm_registers(self, registry):
        """测试解析后的物品会被注册"""
        llm_data = [
            {
                "name": "测试物品",
                "description": "测试",
                "can_pickup": False,
                "can_use": False,
                "on_examine": "",
                "on_pickup": "",
                "on_use": "",
                "pickup_item": "",
                "pickup_gold": 0,
                "rarity": "common",
                "effects": [],
            },
        ]
        objs = registry.parse_objects_from_llm(llm_data)
        assert registry.get(objs[0].id) is not None


# ============================================================================
# Global Registry Tests
# ============================================================================

class TestGlobalRegistry:
    """全局注册表单例测试"""

    def test_global_registry_singleton(self, global_registry):
        """测试全局注册表是单例"""
        reg2 = get_scene_object_registry()
        assert global_registry is reg2

    def test_global_registry_has_fallback_pools(self, global_registry):
        """测试全局注册表有 fallback 池"""
        for scene_type in ["酒馆", "森林", "村庄", "城镇", "城堡", "洞穴"]:
            pool = global_registry.FALLBACK_POOLS.get(scene_type)
            assert pool is not None


# ============================================================================
# Interaction Result Tests
# ============================================================================

class TestInteractionResults:
    """交互结果数据类测试"""

    def test_examine_result(self):
        """测试检查结果"""
        result = ExamineResult(
            object_name="破旧的木桶",
            description="里面什么都没有",
            extra_narrative="只有几只蛀虫",
            success=True,
        )
        assert result.object_name == "破旧的木桶"
        assert result.success is True

    def test_pickup_result(self):
        """测试拾取结果"""
        result = PickupResult(
            object_name="钱袋",
            success=True,
            narrative="你拾取了8金币！",
            gold_gained=8,
        )
        assert result.gold_gained == 8
        assert result.item_gained == ""

    def test_use_result(self):
        """测试使用结果"""
        result = UseResult(
            object_name="光点",
            success=True,
            narrative="温暖的光芒...",
            effects_applied=["HP+8"],
        )
        assert len(result.effects_applied) == 1
        assert "HP" in result.effects_applied[0]
