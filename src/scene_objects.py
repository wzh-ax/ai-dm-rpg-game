"""
Scene Objects - 场景可交互物品系统

在探索模式中，让玩家可以「检查物品」「拾取物品」「使用物品」，
丰富场景体验，解决「Tutorial 后首个场景空洞」的问题。

核心类：
- SceneObject：可交互物品的数据结构
- SceneObjectRegistry：场景物品注册表（含 fallback 物品池）

物品效果设计原则：
- 简单明确（加HP、加金币、简单buff）
- 不破坏现有战斗/任务系统
"""

import logging
import random
import uuid
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


# ============================================================================
# 物品效果类型
# ============================================================================

class ObjectEffectType:
    """物品效果类型（字符串枚举，用于序列化）"""
    HEAL = "heal"                      # 恢复 HP
    ADD_GOLD = "add_gold"              # 增加金币
    BUFF_ATTACK = "buff_attack"        # 攻击增益（战斗中）
    BUFF_DEFENSE = "buff_defense"      # 防御增益（战斗中）
    CURE = "cure"                      # 解除异常状态
    REVEAL = "reveal"                  # 揭示隐藏信息
    XP = "xp"                          # 增加经验值


# ============================================================================
# 数据模型
# ============================================================================

@dataclass
class ObjectEffect:
    """
    物品效果

    Attributes:
        effect_type: 效果类型 (heal/add_gold/buff_attack/...)
        value: 效果数值
        description: 效果描述（用于叙事）
    """
    effect_type: str = "heal"
    value: int = 0
    description: str = ""

    def to_dict(self) -> dict:
        return {
            "effect_type": self.effect_type,
            "value": self.value,
            "description": self.description,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ObjectEffect":
        return cls(
            effect_type=data.get("effect_type", "heal"),
            value=data.get("value", 0),
            description=data.get("description", ""),
        )


@dataclass
class SceneObject:
    """
    场景可交互物品

    Attributes:
        id: 唯一标识
        name: 物品名称（如「破旧的木桶」「桌上的烛台」）
        description: 默认描述
        can_pickup: 能否拾取
        can_use: 能否使用
        on_examine: 检查时的额外叙事（固定文本或 LLM 占位符）
        on_pickup: 拾取后的叙事 + 获得的物品/金币
        on_use: 使用后的效果叙事
        effects: 使用效果列表
        pickup_item: 拾取时获得的物品名称（如「铜币×3」）
        pickup_gold: 拾取时获得的金币数量
        rarity: 稀有度（common/uncommon/rare）
    """
    id: str
    name: str
    description: str = ""
    can_pickup: bool = False
    can_use: bool = False
    on_examine: str = ""
    on_pickup: str = ""
    on_use: str = ""
    effects: list[ObjectEffect] = field(default_factory=list)
    pickup_item: str = ""      # 拾取时获得的物品名称
    pickup_gold: int = 0       # 拾取时获得的金币
    rarity: str = "common"     # common, uncommon, rare

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "can_pickup": self.can_pickup,
            "can_use": self.can_use,
            "on_examine": self.on_examine,
            "on_pickup": self.on_pickup,
            "on_use": self.on_use,
            "effects": [e.to_dict() for e in self.effects],
            "pickup_item": self.pickup_item,
            "pickup_gold": self.pickup_gold,
            "rarity": self.rarity,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "SceneObject":
        return cls(
            id=data.get("id", ""),
            name=data.get("name", ""),
            description=data.get("description", ""),
            can_pickup=data.get("can_pickup", False),
            can_use=data.get("can_use", False),
            on_examine=data.get("on_examine", ""),
            on_pickup=data.get("on_pickup", ""),
            on_use=data.get("on_use", ""),
            effects=[ObjectEffect.from_dict(e) for e in data.get("effects", [])],
            pickup_item=data.get("pickup_item", ""),
            pickup_gold=data.get("pickup_gold", 0),
            rarity=data.get("rarity", "common"),
        )


# ============================================================================
# 交互结果
# ============================================================================

@dataclass
class ExamineResult:
    """检查物品的结果"""
    object_name: str
    description: str
    extra_narrative: str
    success: bool = True


@dataclass
class PickupResult:
    """拾取物品的结果"""
    object_name: str
    success: bool
    narrative: str
    item_gained: str = ""
    gold_gained: int = 0
    reason: str = ""


@dataclass
class UseResult:
    """使用物品的结果"""
    object_name: str
    success: bool
    narrative: str
    effects_applied: list[str] = field(default_factory=list)
    reason: str = ""


# ============================================================================
# 场景物品注册表（含 Fallback 物品池）
# ============================================================================

class SceneObjectRegistry:
    """
    场景物品注册表

    管理场景中可交互物品的模板，提供：
    - 按场景类型获取 fallback 物品池
    - 从 LLM 输出解析物品列表
    - 随机生成指定数量的场景物品
    """

    # 每个场景类型的 Fallback 物品池
    # 每个物品包含: name, description, can_pickup, pickup_item/pickup_gold, on_examine, on_pickup
    FALLBACK_POOLS: dict[str, list[dict]] = {
        "酒馆": [
            {
                "name": "破旧的木桶",
                "description": "一只蛀虫爬了出来，木桶里什么都没有...",
                "can_pickup": False,
                "can_use": False,
                "on_examine": "你敲了敲木桶，里面空空如也，只有几只蛀虫惊慌地逃窜。",
                "on_pickup": "你试图举起木桶，但它太重了，只能作罢。",
                "on_use": "",
                "pickup_item": "",
                "pickup_gold": 0,
                "rarity": "common",
                "effects": [],
            },
            {
                "name": "桌上的烛台",
                "description": "一盏造型古朴的铜制烛台，烛泪凝固在底座上。",
                "can_pickup": True,
                "can_use": False,
                "on_examine": "烛台在微弱的烛光下泛着温暖的光泽，雕刻着已经模糊的藤蔓纹饰。",
                "on_pickup": "你将烛台收入背包，铜的重量让人安心。",
                "on_pickup": "📦 你拾取了「铜烛台」！它虽然不值钱，但或许日后能派上用场。",
                "on_use": "",
                "pickup_item": "铜烛台",
                "pickup_gold": 2,
                "rarity": "common",
                "effects": [],
            },
            {
                "name": "墙角的旧布告",
                "description": "一张泛黄的布告贴在墙角，边缘已经卷起。",
                "can_pickup": False,
                "can_use": True,
                "on_examine": "布告上的字迹已经模糊，只能依稀辨认出「...悬赏...森林...狼...」几个字。",
                "on_pickup": "你试着撕下布告，但它粘得太牢，只能作罢。",
                "on_use": "✨ 你仔细阅读了布告：「幽影森林中有凶猛的影狼出没，困扰村民已久...」\n这似乎是一条任务线索！",
                "pickup_item": "",
                "pickup_gold": 0,
                "rarity": "uncommon",
                "effects": [{"effect_type": "reveal", "value": 0, "description": "揭示任务线索"}],
            },
            {
                "name": "吧台下的钱袋",
                "description": "一个小皮袋藏在吧台下的阴影里，似乎有人遗忘在这里。",
                "can_pickup": True,
                "can_use": False,
                "on_examine": "你悄悄伸手探入吧台下，摸到了一个沉甸甸的小皮袋。",
                "on_pickup": "📦 你拾取了「遗忘的钱袋」！\n💰 里面有 8 枚金币！",
                "on_use": "",
                "pickup_item": "",
                "pickup_gold": 8,
                "rarity": "uncommon",
                "effects": [],
            },
            {
                "name": "墙上的鹿角装饰",
                "description": "一对风干的鹿角挂在墙上，已经失去了光泽。",
                "can_pickup": False,
                "can_use": False,
                "on_examine": "鹿角的纹理依然清晰，可以感受到它曾经主人的雄健。你注意到鹿角上刻着一个小小的符文...似乎没有任何实际作用。",
                "on_pickup": "鹿角挂得太高，你够不到。",
                "on_use": "",
                "pickup_item": "",
                "pickup_gold": 0,
                "rarity": "common",
                "effects": [],
            },
        ],
        "森林": [
            {
                "name": "空心的树洞",
                "description": "一棵老树的树干上有一个黑洞洞的树洞，不知通向何处。",
                "can_pickup": False,
                "can_use": True,
                "on_examine": "树洞口散发着潮湿的腐叶气息，你隐约听到深处有水滴的声音。伸手进去...摸到了一些凉凉的东西。",
                "on_pickup": "你的手臂不够长，够不到树洞深处。",
                "on_use": "你将手臂伸入树洞深处，指尖触碰到了冰凉的金属——是一枚硬币！\n💰 你从树洞中获得了 3 枚金币！",
                "pickup_item": "",
                "pickup_gold": 3,
                "rarity": "common",
                "effects": [{"effect_type": "add_gold", "value": 3, "description": "金币+3"}],
            },
            {
                "name": "地上的野莓丛",
                "description": "一丛低矮的灌木，上面挂着红彤彤的野莓。",
                "can_pickup": True,
                "can_use": True,
                "on_examine": "野莓饱满多汁，散发着淡淡的甜香。你认出这是可以食用的山莓。",
                "on_pickup": "📦 你拾取了「新鲜野莓」！\n✨ 你吃了一颗野莓，恢复了 5 点 HP！",
                "on_pickup": "📦 你拾取了「新鲜野莓」！它可以在休息时食用。",
                "on_use": "✨ 你吃了几颗野莓，清甜的味道在口中散开。\n💚 HP 恢复了 5 点！",
                "pickup_item": "新鲜野莓",
                "pickup_gold": 0,
                "rarity": "common",
                "effects": [{"effect_type": "heal", "value": 5, "description": "HP+5"}],
            },
            {
                "name": "倒下的枯木",
                "description": "一棵巨大的枯木横卧在林间，树干上长满了青苔和蘑菇。",
                "can_pickup": False,
                "can_use": False,
                "on_examine": "枯木的树皮已经完全腐烂，一簇簇白色的蘑菇从缝隙中钻出。你注意到蘑菇丛中有些不对劲的光泽——是蘑菇在发光。",
                "on_pickup": "你试着搬动枯木，但它太重了。",
                "on_use": "",
                "pickup_item": "",
                "pickup_gold": 0,
                "rarity": "common",
                "effects": [],
            },
            {
                "name": "灌木丛后的宝箱",
                "description": "一个被藤蔓覆盖的旧木箱，半埋在落叶之下。",
                "can_pickup": True,
                "can_use": False,
                "on_examine": "宝箱的锁已经锈蚀，但似乎还能打开。你屏住呼吸，轻轻掀开箱盖...",
                "on_pickup": "📦 你拾取了「旧宝箱」！\n💰 箱子里有 15 枚金币和一瓶治疗药水！",
                "on_use": "",
                "pickup_item": "旧宝箱",
                "pickup_gold": 15,
                "rarity": "rare",
                "effects": [],
            },
            {
                "name": "树干上的刻痕",
                "description": "有人在树干上刻下了一串模糊的符号。",
                "can_pickup": False,
                "can_use": True,
                "on_examine": "刻痕已经很旧，边缘已经被树脂覆盖。你仔细辨认...似乎是一个箭头，指向北方。",
                "on_pickup": "你试着刮下树皮，但这些刻痕已经和树融为一体了。",
                "on_use": "✨ 你顺着箭头的方向看去——北方似乎有什么东西在反光...那是一条被遗忘的小路。",
                "pickup_item": "",
                "pickup_gold": 0,
                "rarity": "uncommon",
                "effects": [{"effect_type": "reveal", "value": 0, "description": "揭示隐藏路径"}],
            },
        ],
        "村庄": [
            {
                "name": "井边的石制水槽",
                "description": "一口古老的水井旁边有一个石头凿成的水槽，积满了雨水。",
                "can_pickup": False,
                "can_use": True,
                "on_examine": "水槽里的雨水清澈见底，水面上漂浮着几片落叶。你注意到水底有一些闪烁的东西...",
                "on_pickup": "水槽太重了，无法搬动。",
                "on_use": "✨ 你俯身在水槽中洗了把脸，清凉的井水让你精神一振。\n同时，你从水底捞起了 2 枚被遗弃的铜币！",
                "pickup_item": "",
                "pickup_gold": 2,
                "rarity": "common",
                "effects": [{"effect_type": "add_gold", "value": 2, "description": "金币+2"}],
            },
            {
                "name": "村口的旧邮箱",
                "description": "一个褪色的木质邮箱立在村口，上面布满了灰尘。",
                "can_pickup": False,
                "can_use": True,
                "on_examine": "邮箱的门已经打不开了，但透过缝隙，你看到里面似乎有一张折叠的纸。",
                "on_pickup": "邮箱钉死在木桩上，无法取下。",
                "on_use": "✨ 你用力拉开邮箱门，干涩的铰链发出吱呀声。你取出了里面的纸条...\n上面潦草地写着：「如果有人看到这张纸条，请告诉镇长，森林里的狼...」后面的字迹被水渍模糊了。",
                "pickup_item": "",
                "pickup_gold": 0,
                "rarity": "uncommon",
                "effects": [{"effect_type": "reveal", "value": 0, "description": "揭示任务线索"}],
            },
            {
                "name": "晾晒的草药束",
                "description": "几束用绳子扎好的草药挂在屋檐下，风干后呈现出深褐色。",
                "can_pickup": True,
                "can_use": False,
                "on_examine": "这些是药草商人常用的品种——薄荷、甘草和一些你叫不出名字的草药。散发着淡淡的清香。",
                "on_pickup": "📦 你拾取了「风干草药」！\n🪙 卖了 5 枚金币！",
                "on_use": "",
                "pickup_item": "风干草药",
                "pickup_gold": 5,
                "rarity": "common",
                "effects": [],
            },
            {
                "name": "地上的奇怪脚印",
                "description": "泥地上有一串奇怪的脚印，比人的脚大得多，似乎是什么大型动物留下的。",
                "can_pickup": False,
                "can_use": False,
                "on_examine": "脚印延伸向村庄外的方向，从大小和深度来看，这个生物体型巨大且步伐沉重。你注意到脚印之间还夹杂着一些毛发——黑色的、粗硬的毛。",
                "on_pickup": "脚印和毛发无法拾取。",
                "on_use": "",
                "pickup_item": "",
                "pickup_gold": 0,
                "rarity": "common",
                "effects": [],
            },
            {
                "name": "墙角的老旧木箱",
                "description": "一只积满灰尘的木箱靠在墙角，盖子微微翘起。",
                "can_pickup": True,
                "can_use": False,
                "on_examine": "你轻轻掀开箱盖，里面是一些破旧的衣物和几枚被遗忘在口袋里的硬币。",
                "on_pickup": "📦 你翻找了旧衣物，找到了一些零钱。\n💰 获得了 4 枚铜币！",
                "on_use": "",
                "pickup_item": "",
                "pickup_gold": 4,
                "rarity": "common",
                "effects": [],
            },
        ],
        "城镇": [
            {
                "name": "喷泉中央的雕像",
                "description": "城镇广场中央的喷泉中矗立着一座青铜雕像，雕的是一个披甲的骑士。",
                "can_pickup": False,
                "can_use": False,
                "on_examine": "骑士雕像的面容已经被岁月侵蚀，但依然能感受到他当年的威严。骑士手中握着一柄断剑，剑尖指向天空。雕像基座上刻着一行字：「为守护者而立」。",
                "on_pickup": "雕像太重了，而且它是城镇的公共财产。",
                "on_use": "",
                "pickup_item": "",
                "pickup_gold": 0,
                "rarity": "common",
                "effects": [],
            },
            {
                "name": "台阶上的钱袋",
                "description": "一个鼓鼓囊囊的皮袋被人遗忘在台阶上。",
                "can_pickup": True,
                "can_use": False,
                "on_examine": "钱袋很沉，似乎装了不少钱。你四下张望——没有人注意到这里。",
                "on_pickup": "📦 你迅速将钱袋收入背包！\n💰 里面有 20 枚银币！算是一笔不小的横财！",
                "on_use": "",
                "pickup_item": "",
                "pickup_gold": 20,
                "rarity": "uncommon",
                "effects": [],
            },
            {
                "name": "墙角的流浪猫",
                "description": "一只瘦骨嶙峋的橘猫蜷缩在墙角，警惕地看着你。",
                "can_pickup": False,
                "can_use": True,
                "on_examine": "猫咪脏兮兮的，毛发打着结，但眼睛依然明亮。它对你喵了一声，声音沙哑而微弱。",
                "on_pickup": "猫咪警惕地跳开了，你抓不到它。",
                "on_use": "✨ 你从背包里拿出一小块干粮放在地上。猫咪犹豫了一下，最终还是靠了过来...\n它蹭了蹭你的手，然后心满意足地跑开了，却留下了...一枚被它压在身下的古老硬币？\n💰 获得了「古银币」×1（收藏价值 6 金币）！",
                "pickup_item": "",
                "pickup_gold": 6,
                "rarity": "rare",
                "effects": [{"effect_type": "add_gold", "value": 6, "description": "金币+6"}],
            },
            {
                "name": "地摊上的商品",
                "description": "一个简陋的地摊上摆满了各种小物件：贝壳、石头、旧纽扣...",
                "can_pickup": False,
                "can_use": True,
                "on_examine": "摊主是个眯着眼睛的老婆婆，正在打盹。摊子上的东西都不太值钱，但你注意到角落里有一颗略微发光的蓝色小石头...",
                "on_pickup": "这些都是老婆婆的货物，你不能直接拿走。",
                "on_use": "✨ 你轻轻拿起那颗蓝色小石头...\n老婆婆忽然睁开眼睛：「哦，那是海玻璃，我年轻时在海边捡的。你要喜欢的话...5个铜币就拿走。」",
                "pickup_item": "",
                "pickup_gold": 0,
                "rarity": "uncommon",
                "effects": [],
            },
        ],
        "城堡": [
            {
                "name": "墙上的铠甲架",
                "description": "一套落满灰尘的旧铠甲被挂在墙上，尺寸似乎刚好适合你。",
                "can_pickup": False,
                "can_use": True,
                "on_examine": "铠甲的关节处已经锈蚀，但主体结构依然坚固。头盔的面罩微微敞开，里面一片漆黑。你把手伸进去...触感冰凉。",
                "on_pickup": "铠甲太大了，无法装进背包。",
                "on_use": "✨ 你试着穿上这副铠甲——竟然出奇地合身！\n虽然它已经破旧，但你感受到了一丝额外的安全感。\n🛡️ 临时防御 +1（离开场景后消失）",
                "pickup_item": "",
                "pickup_gold": 0,
                "rarity": "uncommon",
                "effects": [{"effect_type": "buff_defense", "value": 1, "description": "临时防御+1"}],
            },
            {
                "name": "窗台上的花瓶",
                "description": "一个布满裂纹的陶瓷花瓶立在窗台上，里面插着几朵干枯的花。",
                "can_pickup": True,
                "can_use": False,
                "on_examine": "花瓶上的釉彩已经剥落大半，但依然能看出曾经的精美图案。干枯的花朵一碰就碎成了粉末。",
                "on_pickup": "📦 你小心翼翼地将花瓶收入背包。\n虽然它并不值钱，但造型还算别致。",
                "on_use": "",
                "pickup_item": "旧花瓶",
                "pickup_gold": 3,
                "rarity": "common",
                "effects": [],
            },
            {
                "name": "王座上的裂缝",
                "description": "大厅尽头的高大王座上雕刻着繁复的花纹，但座面上有一道明显的裂缝。",
                "can_pickup": False,
                "can_use": True,
                "on_examine": "你走近王座，仔细观察那道裂缝...裂缝里似乎卡着什么东西。伸手进去，你摸到了一个硬硬的、金属质地的东西。",
                "on_pickup": "你无法只取出裂缝里的东西而移动王座。",
                "on_use": "✨ 你用手指抠出卡在裂缝里的东西——是一枚古老的金币！\n💰 获得了「古王冠金币」×1（价值 10 金币）！\n这枚金币的边缘有锯齿，正面是一个你不认识的国王头像。",
                "pickup_item": "",
                "pickup_gold": 10,
                "rarity": "rare",
                "effects": [{"effect_type": "add_gold", "value": 10, "description": "金币+10"}],
            },
        ],
        "洞穴": [
            {
                "name": "潮湿的石壁",
                "description": "洞穴的石壁上长满了发光的苔藓，散发着幽幽的绿光。",
                "can_pickup": False,
                "can_use": True,
                "on_examine": "苔藓摸上去软绵绵的，有一股潮湿的腥味。微弱的绿光让你的手呈现出一种病态的颜色。",
                "on_pickup": "苔藓扎根在石壁上，无法摘取。",
                "on_use": "✨ 你用手掌贴上苔藓，一股奇异的凉意从掌心传来...\n你的眼睛似乎适应了黑暗，能看得更清楚了一些！\n👁️ 临时感知+1（离开场景后消失）",
                "pickup_item": "",
                "pickup_gold": 0,
                "rarity": "uncommon",
                "effects": [{"effect_type": "reveal", "value": 0, "description": "临时感知提升"}],
            },
            {
                "name": "地上的矿脉",
                "description": "地面上露出一段闪烁的矿脉，零星地反射着火光。",
                "can_pickup": True,
                "can_use": False,
                "on_examine": "你蹲下身仔细观察——这是一条天然的铜矿矿脉，夹杂着一些闪亮的云母碎片。",
                "on_pickup": "📦 你敲下了一块矿石样本。\n🪙 矿脉样本可以卖几个铜币！",
                "on_use": "",
                "pickup_item": "铜矿石",
                "pickup_gold": 4,
                "rarity": "common",
                "effects": [],
            },
            {
                "name": "蝙蝠粪便堆",
                "description": "墙角有一堆深褐色的堆积物，散发着刺鼻的臭味。",
                "can_pickup": False,
                "can_use": False,
                "on_examine": "你捏着鼻子凑近一看——这是蝙蝠粪便，在中医中被称为「夜明砂」，据说有一定的药用价值...但现在这不是重点。",
                "on_pickup": "你不打算收集这个。",
                "on_use": "",
                "pickup_item": "",
                "pickup_gold": 0,
                "rarity": "common",
                "effects": [],
            },
            {
                "name": "地下水源",
                "description": "岩壁缝隙中有一股细小的水流渗出，汇聚成一个小水洼。",
                "can_pickup": True,
                "can_use": True,
                "on_examine": "水洼里的水清澈透明，你能看到水底有一层细沙。伸手进去，水很凉，但不刺骨。",
                "on_pickup": "📦 你用水壶装了满满一壶地下水。",
                "on_pickup": "📦 你喝了几口水洼里的水，清凉解渴！\n💚 HP 恢复了 3 点！",
                "on_use": "✨ 你饮了几口清凉的地下水，干渴感消失了。\n💚 HP 恢复了 3 点！",
                "pickup_item": "水壶",
                "pickup_gold": 0,
                "rarity": "common",
                "effects": [{"effect_type": "heal", "value": 3, "description": "HP+3"}],
            },
        ],
        # 默认池（用于未知场景类型）
        "default": [
            {
                "name": "地上的碎石",
                "description": "几块不起眼的碎石散落在地上。",
                "can_pickup": False,
                "can_use": False,
                "on_examine": "只是普通的石头，没什么特别的。",
                "on_pickup": "石头太重了，你不想搬。",
                "on_use": "",
                "pickup_item": "",
                "pickup_gold": 0,
                "rarity": "common",
                "effects": [],
            },
            {
                "name": "破旧的布袋",
                "description": "一个被人遗忘的破布袋，半埋在尘土中。",
                "can_pickup": True,
                "can_use": False,
                "on_examine": "布袋已经破损严重，但里面似乎还有东西。",
                "on_pickup": "📦 你翻找布袋，找到了一些零钱。\n💰 获得了 3 枚铜币！",
                "on_use": "",
                "pickup_item": "",
                "pickup_gold": 3,
                "rarity": "common",
                "effects": [],
            },
            {
                "name": "神秘的光点",
                "description": "一个微弱的光点在空气中飘浮，忽明忽暗。",
                "can_pickup": False,
                "can_use": True,
                "on_examine": "光点似乎有某种意志，你无法判断它是生物还是魔法造物。当你靠近时，它会微微后退。",
                "on_pickup": "光点无法触碰。",
                "on_use": "✨ 你对光点伸出手，它犹豫了一下，然后飘落在你的掌心，化作一缕温暖...\n💚 HP 恢复了 8 点！\n光点消散了，但你觉得这可能是某个灵魂最后的安息。",
                "pickup_item": "",
                "pickup_gold": 0,
                "rarity": "uncommon",
                "effects": [{"effect_type": "heal", "value": 8, "description": "HP+8"}],
            },
        ],
    }

    def __init__(self):
        self._objects: dict[str, SceneObject] = {}

    # --------------------------------------------------------------------------
    # 注册 & 查询
    # --------------------------------------------------------------------------

    def register(self, obj: SceneObject) -> None:
        """注册物品模板"""
        self._objects[obj.id] = obj
        logger.debug(f"Registered scene object: {obj.name} ({obj.id})")

    def get(self, obj_id: str) -> SceneObject | None:
        """按 ID 获取物品"""
        return self._objects.get(obj_id)

    def get_all(self) -> list[SceneObject]:
        """获取所有物品"""
        return list(self._objects.values())

    # --------------------------------------------------------------------------
    # Fallback 物品池
    # --------------------------------------------------------------------------

    def get_fallback_objects(self, scene_type: str, count: int = 3) -> list[SceneObject]:
        """
        从 fallback 池中随机获取指定数量的物品

        Args:
            scene_type: 场景类型
            count: 需要物品数量

        Returns:
            SceneObject 列表
        """
        pool = self.FALLBACK_POOLS.get(scene_type, self.FALLBACK_POOLS["default"])
        # 随机选择 count 个（不重复）
        selected = random.sample(pool, min(count, len(pool)))
        result = []
        for item_data in selected:
            obj = SceneObject(
                id=f"fallback_{scene_type}_{uuid.uuid4().hex[:6]}",
                name=item_data["name"],
                description=item_data["description"],
                can_pickup=item_data.get("can_pickup", False),
                can_use=item_data.get("can_use", False),
                on_examine=item_data.get("on_examine", ""),
                on_pickup=item_data.get("on_pickup", ""),
                on_use=item_data.get("on_use", ""),
                pickup_item=item_data.get("pickup_item", ""),
                pickup_gold=item_data.get("pickup_gold", 0),
                rarity=item_data.get("rarity", "common"),
                effects=[
                    ObjectEffect(
                        effect_type=e.get("effect_type", "heal"),
                        value=e.get("value", 0),
                        description=e.get("description", ""),
                    )
                    for e in item_data.get("effects", [])
                ],
            )
            result.append(obj)
        return result

    # --------------------------------------------------------------------------
    # LLM 解析
    # --------------------------------------------------------------------------

    def parse_objects_from_llm(self, objects_data: list[dict]) -> list[SceneObject]:
        """
        从 LLM 输出解析物品列表

        Args:
            objects_data: LLM 返回的 objects 数组

        Returns:
            SceneObject 列表
        """
        result = []
        for item_data in objects_data:
            try:
                effects = [
                    ObjectEffect(
                        effect_type=e.get("effect_type", "heal"),
                        value=e.get("value", 0),
                        description=e.get("description", ""),
                    )
                    for e in item_data.get("effects", [])
                ]
                obj = SceneObject(
                    id=f"llm_{uuid.uuid4().hex[:8]}",
                    name=item_data.get("name", "未知物品"),
                    description=item_data.get("description", ""),
                    can_pickup=item_data.get("can_pickup", False),
                    can_use=item_data.get("can_use", False),
                    on_examine=item_data.get("on_examine", ""),
                    on_pickup=item_data.get("on_pickup", ""),
                    on_use=item_data.get("on_use", ""),
                    pickup_item=item_data.get("pickup_item", ""),
                    pickup_gold=item_data.get("pickup_gold", 0),
                    rarity=item_data.get("rarity", "common"),
                    effects=effects,
                )
                result.append(obj)
                self.register(obj)
            except Exception as e:
                logger.warning(f"Failed to parse scene object from LLM: {e}")
        return result


# ============================================================================
# 全局实例
# ============================================================================

_object_registry: SceneObjectRegistry | None = None


def get_scene_object_registry() -> SceneObjectRegistry:
    """获取全局 SceneObjectRegistry 实例"""
    global _object_registry
    if _object_registry is None:
        _object_registry = SceneObjectRegistry()
    return _object_registry
