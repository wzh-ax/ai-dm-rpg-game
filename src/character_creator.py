"""
CharacterCreator - 角色创建系统

职责：
1. 管理角色创建流程（种族、职业、名字）
2. 根据种族/职业自动分配属性
3. 生成角色背景故事
4. 与 GameMaster 集成，初始化玩家状态
"""

import random
import uuid
from dataclasses import dataclass, field
from typing import Any

from .minimax_interface import MiniMaxInterface, get_minimax_interface


# =============================================================================
# 种族定义
# =============================================================================

@dataclass(frozen=True)
class RaceDefinition:
    """种族定义"""
    id: str
    name: str
    description: str
    attribute_bonuses: dict[str, int]  # 属性加成
    base_hp: int
    base_ac: int
    base_attack_bonus: int
    special_ability: str  # 种族特殊能力名称


RACES: dict[str, RaceDefinition] = {
    "human": RaceDefinition(
        id="human",
        name="人类",
        description="适应性强，均衡发展。在陌生的土地上，人类总能凭借智慧和韧性找到生存之道。",
        attribute_bonuses={"str": 0, "dex": 0, "con": 0, "int": 0, "wis": 0, "cha": 1},
        base_hp=20,
        base_ac=10,
        base_attack_bonus=1,
        special_ability="命运眷顾 - 关键时刻可以重掷一颗骰子（每日一次）",
    ),
    "elf": RaceDefinition(
        id="elf",
        name="精灵",
        description="优雅敏捷，与森林和魔法有着天然的亲和力。尖耳是他们最显著的特征。",
        attribute_bonuses={"str": -1, "dex": 3, "con": 0, "int": 1, "wis": 0, "cha": 1},
        base_hp=18,
        base_ac=11,
        base_attack_bonus=2,
        special_ability="精灵视域 - 在光线昏暗的环境中获得优势",
    ),
    "dwarf": RaceDefinition(
        id="dwarf",
        name="矮人",
        description="矮壮坚韧，天生是矿工和战士。胡子是矮人尊严的象征。",
        attribute_bonuses={"str": 2, "dex": -1, "con": 3, "int": 0, "wis": 1, "cha": -1},
        base_hp=22,
        base_ac=12,
        base_attack_bonus=0,
        special_ability="矮人坚韧 - 毒素抗性，抵抗疾病",
    ),
    "orc": RaceDefinition(
        id="orc",
        name="兽人",
        description="强壮凶猛，拥有惊人的战斗本能。绿色皮肤和獠牙是他们的标志。",
        attribute_bonuses={"str": 3, "dex": 0, "con": 2, "int": -2, "wis": 0, "cha": 0},
        base_hp=24,
        base_ac=9,
        base_attack_bonus=1,
        special_ability="狂暴 - 生命值低于一半时，伤害+3",
    ),
}


# =============================================================================
# 职业定义
# =============================================================================

@dataclass(frozen=True)
class ClassDefinition:
    """职业定义"""
    id: str
    name: str
    description: str
    attribute_focus: dict[str, int]  # 主属性加成
    ac_bonus: int
    attack_bonus: int
    primary_skill: str  # 主技能名称
    skill_description: str  # 技能描述
    starting_items: list[dict]  # 初始物品


CLASSES: dict[str, ClassDefinition] = {
    "warrior": ClassDefinition(
        id="warrior",
        name="战士",
        description="精通各类武器与防具，是战场上的中流砥柱。",
        attribute_focus={"str": 2, "dex": 1, "con": 1, "int": 0, "wis": 0, "cha": 0},
        ac_bonus=2,
        attack_bonus=2,
        primary_skill="重击",
        skill_description="全力攻击，造成双倍伤害，但本回合AC-3",
        starting_items=[
            {"id": "rusty_sword", "name": "生锈长剑", "quantity": 1},
            {"id": "potion_healing", "name": "治疗药水", "quantity": 2},
        ],
    ),
    "ranger": ClassDefinition(
        id="ranger",
        name="游侠",
        description="擅长远程攻击和追踪，与自然和谐共处。",
        attribute_focus={"str": 1, "dex": 3, "con": 1, "int": 0, "wis": 1, "cha": 0},
        ac_bonus=1,
        attack_bonus=3,
        primary_skill="双重射击",
        skill_description="连续发射两箭，每箭造成正常伤害",
        starting_items=[
            {"id": "shortbow", "name": "短弓", "quantity": 1},
            {"id": "arrow_bundle", "name": "箭矢（束）", "quantity": 10},
            {"id": "potion_healing", "name": "治疗药水", "quantity": 2},
        ],
    ),
    "mage": ClassDefinition(
        id="mage",
        name="法师",
        description="操控魔法的智者，能够施展强大的法术。",
        attribute_focus={"str": 0, "dex": 0, "con": 0, "int": 3, "wis": 1, "cha": 0},
        ac_bonus=0,
        attack_bonus=1,
        primary_skill="火球术",
        skill_description="发射火球，对敌人造成2d6火焰伤害",
        starting_items=[
            {"id": "quarterstaff", "name": "法杖", "quantity": 1},
            {"id": "spellbook", "name": "法术书（入门）", "quantity": 1},
            {"id": "potion_healing", "name": "治疗药水", "quantity": 1},
            {"id": "scroll_fireball", "name": "火球术卷轴", "quantity": 1},
        ],
    ),
    "rogue": ClassDefinition(
        id="rogue",
        name="盗贼",
        description="潜行与偷袭的大师，擅长从阴影中发动致命一击。",
        attribute_focus={"str": 0, "dex": 3, "con": 1, "int": 1, "wis": 0, "cha": 1},
        ac_bonus=1,
        attack_bonus=2,
        primary_skill="背刺",
        skill_description="从背后偷袭，造成双倍伤害",
        starting_items=[
            {"id": "dagger", "name": "匕首", "quantity": 2},
            {"id": "lockpick_set", "name": "开锁工具", "quantity": 1},
            {"id": "potion_healing", "name": "治疗药水", "quantity": 2},
        ],
    ),
}


# =============================================================================
# 角色数据模型
# =============================================================================

@dataclass
class Character:
    """角色数据"""
    id: str
    name: str
    race_id: str
    race_name: str
    class_id: str
    class_name: str

    # 六项基础属性（STR/DEX/CON/INT/WIS/CHA）
    attributes: dict[str, int] = field(default_factory=dict)

    # 战斗属性
    max_hp: int = 20
    current_hp: int = 20
    armor_class: int = 10
    attack_bonus: int = 1

    # 角色信息
    level: int = 1
    xp: int = 0
    gold: int = 10

    # 背包和技能
    inventory: list[dict] = field(default_factory=list)
    primary_skill: str = ""
    skill_description: str = ""

    # 背景
    background: str = ""
    special_ability: str = ""

    def to_player_stats(self) -> dict[str, Any]:
        """转换为 GameMaster 的 player_stats 格式"""
        return {
            "hp": self.current_hp,
            "max_hp": self.max_hp,
            "ac": self.armor_class,
            "xp": self.xp,
            "level": self.level,
            "gold": self.gold,
            "inventory": list(self.inventory),
            # 扩展字段（用于存档兼容）
            "character_id": self.id,
            "name": self.name,
            "race": self.race_name,
            "class": self.class_name,
            "attributes": dict(self.attributes),
            "primary_skill": self.primary_skill,
            "special_ability": self.special_ability,
        }

    def to_dict(self) -> dict[str, Any]:
        """序列化为字典"""
        return {
            "id": self.id,
            "name": self.name,
            "race_id": self.race_id,
            "race_name": self.race_name,
            "class_id": self.class_id,
            "class_name": self.class_name,
            "attributes": dict(self.attributes),
            "max_hp": self.max_hp,
            "current_hp": self.current_hp,
            "armor_class": self.armor_class,
            "attack_bonus": self.attack_bonus,
            "level": self.level,
            "xp": self.xp,
            "gold": self.gold,
            "inventory": list(self.inventory),
            "primary_skill": self.primary_skill,
            "skill_description": self.skill_description,
            "background": self.background,
            "special_ability": self.special_ability,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Character":
        """从字典反序列化"""
        return cls(
            id=data.get("id", str(uuid.uuid4())),
            name=data.get("name", "无名冒险者"),
            race_id=data.get("race_id", "human"),
            race_name=data.get("race_name", "人类"),
            class_id=data.get("class_id", "warrior"),
            class_name=data.get("class_name", "战士"),
            attributes=data.get("attributes", {}),
            max_hp=data.get("max_hp", 20),
            current_hp=data.get("current_hp", 20),
            armor_class=data.get("armor_class", 10),
            attack_bonus=data.get("attack_bonus", 1),
            level=data.get("level", 1),
            xp=data.get("xp", 0),
            gold=data.get("gold", 10),
            inventory=data.get("inventory", []),
            primary_skill=data.get("primary_skill", ""),
            skill_description=data.get("skill_description", ""),
            background=data.get("background", ""),
            special_ability=data.get("special_ability", ""),
        )


# =============================================================================
# 角色创建器
# =============================================================================

class CharacterCreator:
    """
    角色创建器

    支持：
    - 种族选择
    - 职业选择
    - 自定义名字
    - 自动属性分配
    - 背景故事生成
    """

    # 种族选择菜单
    RACE_MENU = """
╔══════════════════════════════════════════════════════════════╗
║                     ⚔️  选择你的种族                          ║
╠══════════════════════════════════════════════════════════════╣
║  1. 人类 (Human)                                               ║
║     「命运眷顾」 - 关键时刻可重掷骰子                         ║
║     特点：均衡全能，适应性强                                   ║
║                                                                  ║
║  2. 精灵 (Elf)                                                ║
║     「精灵视域」 - 昏暗环境中获得优势                           ║
║     特点：敏捷灵巧，魔法亲和                                   ║
║                                                                  ║
║  3. 矮人 (Dwarf)                                              ║
║     「矮人坚韧」 - 毒素与疾病抗性                               ║
║     特点：坚韧耐久，战斗顽强                                   ║
║                                                                  ║
║  4. 兽人 (Orc)                                                ║
║     「狂暴」 - 生命值低时伤害+3                                 ║
║     特点：强壮凶猛，战斗本能                                   ║
╚══════════════════════════════════════════════════════════════╝"""

    # 职业选择菜单
    CLASS_MENU = """
╔══════════════════════════════════════════════════════════════╗
║                     ⚔️  选择你的职业                          ║
╠══════════════════════════════════════════════════════════════╣
║  1. 战士 (Warrior)                                            ║
║     技能：重击 - 全力攻击，双倍伤害（AC-3）                     ║
║     特点：高生命值，高护甲，擅长近战                           ║
║                                                                  ║
║  2. 游侠 (Ranger)                                             ║
║     技能：双重射击 - 连续发射两箭                               ║
║     特点：远程攻击，追踪专家                                   ║
║                                                                  ║
║  3. 法师 (Mage)                                               ║
║     技能：火球术 - 2d6火焰伤害                                   ║
║     特点：强大魔法，脆弱体质                                   ║
║                                                                  ║
║  4. 盗贼 (Rogue)                                              ║
║     技能：背刺 - 背后偷袭，双倍伤害                             ║
║     特点：潜行高手，爆发力强                                   ║
╚══════════════════════════════════════════════════════════════╝"""

    def __init__(self):
        self.llm: MiniMaxInterface | None = None
        self._llm_initialized = False

    def _init_llm(self):
        """延迟初始化 LLM"""
        if not self._llm_initialized:
            try:
                self.llm = get_minimax_interface()
                self._llm_initialized = True
            except Exception:
                self.llm = None
                self._llm_initialized = True  # 只尝试一次

    # --------------------------------------------------------------------------
    # 核心创建流程
    # --------------------------------------------------------------------------

    def create_from_selection(
        self,
        name: str,
        race_id: str,
        class_id: str,
    ) -> Character:
        """
        根据选择创建角色（用于异步/外部调用）

        Args:
            name: 角色名
            race_id: 种族ID (human/elf/dwarf/orc)
            class_id: 职业ID (warrior/ranger/mage/rogue)

        Returns:
            创建好的 Character 对象
        """
        # 验证并填充默认值
        race = RACES.get(race_id, RACES["human"])
        cls = CLASSES.get(class_id, CLASSES["warrior"])

        # 计算属性（种族加成 + 职业加成，基础值10）
        attrs = {}
        for attr in ["str", "dex", "con", "int", "wis", "cha"]:
            base = 10
            race_bonus = race.attribute_bonuses.get(attr, 0)
            class_bonus = cls.attribute_focus.get(attr, 0)
            attrs[attr] = base + race_bonus + class_bonus

        # 计算战斗属性
        max_hp = race.base_hp + cls.attribute_focus.get("con", 0) * 2
        armor_class = race.base_ac + cls.ac_bonus
        attack_bonus = race.base_attack_bonus + cls.attack_bonus

        character = Character(
            id=str(uuid.uuid4()),
            name=name.strip(),
            race_id=race.id,
            race_name=race.name,
            class_id=cls.id,
            class_name=cls.name,
            attributes=attrs,
            max_hp=max_hp,
            current_hp=max_hp,
            armor_class=armor_class,
            attack_bonus=attack_bonus,
            level=1,
            xp=0,
            gold=10,
            inventory=list(cls.starting_items),
            primary_skill=cls.primary_skill,
            skill_description=cls.skill_description,
            special_ability=race.special_ability,
        )

        return character

    async def generate_background(self, character: Character) -> str:
        """
        使用 LLM 生成角色背景故事

        Args:
            character: 已创建的角色对象

        Returns:
            背景故事文本
        """
        self._init_llm()

        race = RACES.get(character.race_id, RACES["human"])
        cls = CLASSES.get(character.class_id, CLASSES["warrior"])

        if self.llm and self._llm_initialized:
            system = """你是一个TRPG背景故事作家。你为AI DM RPG生成角色的背景故事。

写作要求：
- 3-5段，第一人称视角
- 包含角色出身、为什么成为冒险者、性格特点
- 与选择的种族和职业相关联
- 150-300字
- 中文输出
- 文学性强，有情感"""
            
            prompt = f"""为以下角色撰写背景故事：

角色信息：
- 名字：{character.name}
- 种族：{race.name}
- 职业：{cls.name}
- 性格关键词：勇敢、机智、坚韧

请生成一段引人入胜的背景故事，解释{{character.name}}是如何踏上冒险之路的。"""

            try:
                background = await self.llm.generate(prompt, system=system, temperature=0.85)
                if background and len(background) > 30:
                    return background.strip()
            except Exception:
                pass

        # Fallback：使用规则生成基础背景
        return self._generate_fallback_background(character)

    def _generate_fallback_background(self, character: Character) -> str:
        """生成基础背景（当 LLM 不可用时）"""
        race = RACES.get(character.race_id, RACES["human"])
        cls = CLASSES.get(character.class_id, CLASSES["warrior"])

        backgrounds = {
            "human_warrior": f"在边境小镇长大，{character.name}从小就梦想着成为传奇英雄。当战火燃起家园，他/她拿起了武器，誓言保护所爱之人。",
            "human_ranger": f"{character.name}曾是王国边境的巡逻兵，在一次任务中发现了神秘的古老遗迹，从此踏上了探索未知世界的旅程。",
            "human_mage": f"出生在书香门第，{character.name}在祖父的藏书阁中发现了魔法奥秘。如今他/她游历四方，寻找失落的法术知识。",
            "human_rogue": f"在城市的阴影中长大，{character.name}学会了生存的艺术。一次偶然的机会，他/她决定用这些技能做更有意义的事。",
            "elf_warrior": f"作为精灵族的末裔，{character.name}见证了太多战争与失去。当森林再次受到威胁，他/她选择站了出来。",
            "elf_mage": f"{character.name}是精灵议会的年轻学徒，渴望证明自己。他/她离开故乡，来到人类世界寻找失落的魔法遗迹。",
            "dwarf_warrior": f"矮人王国的矿山被怪物侵占，{character.name}作为护卫队成员追击敌人，却意外卷入了一场更大的冒险。",
            "dwarf_ranger": f"矮人工匠世家出身，{character.name}厌倦了地下生活，决定去地表世界寻找传说中的锻造秘方。",
            "orc_warrior": f"{character.name}出生于兽人部落，在弱肉强食的环境中艰难求生。当他/她遇到一队友善的冒险者后，命运开始改变。",
            "orc_rogue": f"作为兽人中少有的智者，{character.name}被族群流放。他/她选择用自己的方式——潜入与侦察——来证明自己的价值。",
        }

        key = f"{character.race_id}_{character.class_id}"
        return backgrounds.get(key, f"{character.name}是一个来自{race.name}的{cls.name}，他/她的冒险故事才刚刚开始……")

    # --------------------------------------------------------------------------
    # 交互式创建流程（用于控制台输入）
    # --------------------------------------------------------------------------

    def prompt_name(self) -> str:
        """提示输入角色名"""
        while True:
            name = input("\n🧙 你的名字是？> ").strip()
            if name:
                return name
            print("⚠️ 名字不能为空，请输入你的冒险者名字。")

    def prompt_race(self) -> str:
        """提示选择种族"""
        print(self.RACE_MENU)
        valid_choices = {"1": "human", "2": "elf", "3": "dwarf", "4": "orc"}
        while True:
            choice = input("\n📋 请选择种族（输入数字 1-4）> ").strip()
            if choice in valid_choices:
                return valid_choices[choice]
            print("⚠️ 无效选择，请输入 1-4 之间的数字。")

    def prompt_class(self) -> str:
        """提示选择职业"""
        print(self.CLASS_MENU)
        valid_choices = {"1": "warrior", "2": "ranger", "3": "mage", "4": "rogue"}
        while True:
            choice = input("\n📋 请选择职业（输入数字 1-4）> ").strip()
            if choice in valid_choices:
                return valid_choices[choice]
            print("⚠️ 无效选择，请输入 1-4 之间的数字。")

    def interactive_create(self) -> Character:
        """
        交互式角色创建（同步，阻塞式输入）

        Returns:
            创建好的 Character 对象
        """
        print("\n" + "=" * 60)
        print("⚔️  AI DM RPG - 创建你的冒险者")
        print("=" * 60)

        name = self.prompt_name()
        race_id = self.prompt_race()
        class_id = self.prompt_class()

        # 创建角色
        character = self.create_from_selection(name, race_id, class_id)

        # 展示角色信息
        self.display_character(character)

        return character

    def display_character(self, character: Character) -> None:
        """展示角色信息"""
        race = RACES.get(character.race_id, RACES["human"])
        cls = CLASSES.get(character.class_id, CLASSES["warrior"])

        print(f"\n{'='*60}")
        print(f"✅ {character.name}（{race.name} {cls.name}）创建完成！")
        print(f"{'='*60}")
        print(f"\n📊 基础属性")
        attr_names = {"str": "力量", "dex": "敏捷", "con": "体质", "int": "智力", "wis": "感知", "cha": "魅力"}
        for attr, value in character.attributes.items():
            modifier = (value - 10) // 2
            sign = f"+{modifier}" if modifier >= 0 else str(modifier)
            print(f"  {attr_names.get(attr, attr):>4}: {value:>3} ({sign})")

        print(f"\n⚔️  战斗属性")
        print(f"  ❤️  HP: {character.current_hp}/{character.max_hp}")
        print(f"  🛡️  AC: {character.armor_class}")
        print(f"  ⚔️  攻击加成: +{character.attack_bonus}")

        print(f"\n🌟 特殊能力")
        print(f"  种族: {race.special_ability}")
        print(f"  职业: {cls.primary_skill} - {cls.skill_description}")

        print(f"\n🎒 初始物品")
        for item in character.inventory:
            print(f"  • {item['name']} x{item['quantity']}")

        print(f"\n💰 初始金币: {character.gold}")
        print(f"{'='*60}")


# =============================================================================
# 全局实例
# =============================================================================

_global_creator: CharacterCreator | None = None


def get_character_creator() -> CharacterCreator:
    """获取全局 CharacterCreator 实例"""
    global _global_creator
    if _global_creator is None:
        _global_creator = CharacterCreator()
    return _global_creator
