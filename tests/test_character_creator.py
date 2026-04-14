"""
CharacterCreator - 单元测试
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, patch

from src.character_creator import (
    CharacterCreator,
    Character,
    RaceDefinition,
    ClassDefinition,
    RACES,
    CLASSES,
    get_character_creator,
)


class TestRaceAndClassDefinitions:
    """测试种族和职业定义"""

    def test_all_races_defined(self):
        """所有种族都应该有定义"""
        assert "human" in RACES
        assert "elf" in RACES
        assert "dwarf" in RACES
        assert "orc" in RACES

    def test_all_classes_defined(self):
        """所有职业都应该有定义"""
        assert "warrior" in CLASSES
        assert "ranger" in CLASSES
        assert "mage" in CLASSES
        assert "rogue" in CLASSES

    def test_race_has_required_fields(self):
        """种族定义应该包含所有必需字段"""
        for race_id, race in RACES.items():
            assert race.id == race_id
            assert race.name
            assert race.description
            assert race.attribute_bonuses
            assert race.base_hp > 0
            assert race.base_ac > 0
            assert race.special_ability

    def test_class_has_required_fields(self):
        """职业定义应该包含所有必需字段"""
        for class_id, cls in CLASSES.items():
            assert cls.id == class_id
            assert cls.name
            assert cls.description
            assert cls.attribute_focus
            assert cls.primary_skill
            assert cls.skill_description
            assert cls.starting_items

    def test_human_is_balanced(self):
        """人类应该是均衡的"""
        human = RACES["human"]
        bonuses = human.attribute_bonuses
        # 人类没有惩罚，应该有合理的加成分布
        assert human.base_hp == 20
        assert human.base_ac == 10

    def test_elf_is_dexterous(self):
        """精灵应该有敏捷加成"""
        elf = RACES["elf"]
        assert elf.attribute_bonuses["dex"] >= 2
        assert elf.attribute_bonuses["str"] <= 0

    def test_dwarf_is_tough(self):
        """矮人应该有体质加成"""
        dwarf = RACES["dwarf"]
        assert dwarf.attribute_bonuses["con"] >= 2
        assert dwarf.attribute_bonuses["dex"] <= 0

    def test_orc_is_strong(self):
        """兽人应该有力量加成"""
        orc = RACES["orc"]
        assert orc.attribute_bonuses["str"] >= 2
        assert orc.attribute_bonuses["con"] >= 1


class TestCharacterCreation:
    """测试角色创建"""

    @pytest.fixture
    def creator(self):
        return CharacterCreator()

    def test_create_human_warrior(self, creator):
        """创建人类战士"""
        char = creator.create_from_selection("张三", "human", "warrior")
        assert char.name == "张三"
        assert char.race_id == "human"
        assert char.class_id == "warrior"
        assert char.max_hp > 20
        assert char.armor_class >= 10

    def test_create_elf_mage(self, creator):
        """创建精灵法师"""
        char = creator.create_from_selection("精灵法师", "elf", "mage")
        assert char.name == "精灵法师"
        assert char.race_id == "elf"
        assert char.class_id == "mage"
        assert char.attributes["dex"] > char.attributes["str"]

    def test_create_dwarf_warrior(self, creator):
        """创建矮人战士（高HP高AC）"""
        char = creator.create_from_selection("矮人王", "dwarf", "warrior")
        assert char.race_id == "dwarf"
        assert char.class_id == "warrior"
        assert char.max_hp >= 22  # 矮人基础HP + 战士体质加成

    def test_create_orc_rogue(self, creator):
        """创建兽人盗贼"""
        char = creator.create_from_selection("兽人刺客", "orc", "rogue")
        assert char.race_id == "orc"
        assert char.class_id == "rogue"
        assert char.attributes["str"] >= char.attributes["int"]

    def test_attributes_are_reasonable(self, creator):
        """属性值应该在合理范围内"""
        for race_id in RACES:
            for class_id in CLASSES:
                char = creator.create_from_selection("Test", race_id, class_id)
                for attr, value in char.attributes.items():
                    assert 3 <= value <= 20, f"{race_id}/{class_id} {attr}={value} out of range"

    def test_default_inventory(self, creator):
        """每个职业应该有默认物品"""
        char = creator.create_from_selection("Test", "human", "warrior")
        assert len(char.inventory) > 0

        char = creator.create_from_selection("Test", "human", "mage")
        assert any("法杖" in item["name"] or "spell" in item["id"] for item in char.inventory)

    def test_level_starts_at_1(self, creator):
        """角色初始等级应为1"""
        char = creator.create_from_selection("Test", "human", "warrior")
        assert char.level == 1
        assert char.xp == 0

    def test_gold_starts_at_10(self, creator):
        """角色初始金币应为10"""
        char = creator.create_from_selection("Test", "human", "warrior")
        assert char.gold == 10

    def test_invalid_race_defaults_to_human(self, creator):
        """无效种族应该默认为人类"""
        char = creator.create_from_selection("Test", "invalid", "warrior")
        assert char.race_id == "human"

    def test_invalid_class_defaults_to_warrior(self, creator):
        """无效职业应该默认为战士"""
        char = creator.create_from_selection("Test", "human", "invalid")
        assert char.class_id == "warrior"


class TestCharacterSerialization:
    """测试角色序列化"""

    @pytest.fixture
    def creator(self):
        return CharacterCreator()

    @pytest.fixture
    def sample_char(self, creator):
        return creator.create_from_selection("测试角色", "elf", "ranger")

    def test_to_dict(self, sample_char):
        """角色可以序列化为字典"""
        data = sample_char.to_dict()
        assert data["name"] == "测试角色"
        assert data["race_id"] == "elf"
        assert data["class_id"] == "ranger"
        assert "attributes" in data
        assert "max_hp" in data

    def test_from_dict(self, sample_char):
        """角色可以从字典反序列化"""
        data = sample_char.to_dict()
        restored = Character.from_dict(data)
        assert restored.name == sample_char.name
        assert restored.race_id == sample_char.race_id
        assert restored.class_id == sample_char.class_id
        assert restored.max_hp == sample_char.max_hp

    def test_to_player_stats(self, sample_char):
        """角色可以转换为 GameMaster 的 player_stats 格式"""
        stats = sample_char.to_player_stats()
        assert stats["hp"] == sample_char.current_hp
        assert stats["max_hp"] == sample_char.max_hp
        assert stats["ac"] == sample_char.armor_class
        assert stats["name"] == sample_char.name
        assert stats["race"] == sample_char.race_name
        assert stats["class"] == sample_char.class_name


class TestCharacterCreatorSingleton:
    """测试全局单例"""

    def test_get_character_creator_returns_same_instance(self):
        """get_character_creator 应该返回同一个实例"""
        c1 = get_character_creator()
        c2 = get_character_creator()
        assert c1 is c2


class TestBackgroundGeneration:
    """测试背景故事生成"""

    @pytest.fixture
    def creator(self):
        return CharacterCreator()

    @pytest.fixture
    def sample_char(self, creator):
        return creator.create_from_selection("测试", "human", "warrior")

    @pytest.mark.asyncio
    async def test_generate_background_returns_string(self, creator, sample_char):
        """背景生成应返回字符串"""
        background = await creator.generate_background(sample_char)
        assert isinstance(background, str)
        assert len(background) > 10

    @pytest.mark.asyncio
    async def test_generate_background_has_content(self, creator, sample_char):
        """背景生成应有实际内容"""
        background = await creator.generate_background(sample_char)
        # 不应该只是通用占位符
        assert len(background) > 30

    @pytest.mark.asyncio
    async def test_generate_fallback_background(self, creator):
        """当LLM不可用时应生成fallback背景"""
        creator.llm = None  # 确保LLM不可用
        creator._llm_initialized = False
        char = creator.create_from_selection("Test", "dwarf", "warrior")
        background = await creator.generate_background(char)
        assert isinstance(background, str)
        assert len(background) > 5
