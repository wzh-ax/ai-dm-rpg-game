"""
Scene Agent - 场景生成子 Agent

实现四步场景生成流程:
1. 场景登记查询(查询同类场景索引)
2. 差异化定位(LLM)
3. 场景纲要生成(LLM)
4. 详细内容生成(LLM)

懒生成原则:只生成玩家即将到达的那个节点,不递归扩展

场景差异化增强:
- 随机开场模板: 同一地点不同次进入有不同的开场叙述
- 随机事件注入: 场景生成时注入随机事件(天气/路人/突发事件)
- 场景变体: 同一地点生成时在描述、结构上有差异
"""

import asyncio
import logging
import json
import random
import uuid
from enum import Enum
from typing import Any
from dataclasses import dataclass, field
from pathlib import Path

from .event_bus import Event, EventType, get_event_bus
from .hooks import get_hook_registry, HookNames
from .minimax_interface import MiniMaxInterface
from .logging_system import get_logger

logger = logging.getLogger(__name__)


# ============================================================================
# Fallback 降级策略 - 从 fallback_strategy 模块导入
# ============================================================================

from .fallback_strategy import (
    FailureType,
    FallbackTier,
    classify_exception,
    should_fallback,
    should_retry,
    DegradationTracker,
    get_fallback_scene,
    _FALLBACK_SCENES,
    _DEFAULT_FALLBACK_SCENES,
)

# ============================================================================
# 随机开场模板 - 避免千篇一律的「推开大门,看到...」模板
# ============================================================================


# ============================================================================
# 随机开场模板 - 避免千篇一律的「推开大门,看到...」模板
# ============================================================================

_OPENING_TEMPLATES: dict[str, list[str]] = {
    "酒馆": [
        "推开厚重的橡木门，{香气}扑面而来。",
        "你踏入酒馆，一股{气味}立刻包裹了你。",
        "酒馆的门在你身后关上，隔绝了外面的喧嚣。{环境}占据了你的视野。",
        "还没进门，你就听到了{声音}。踏入酒馆，{氛围}。",
        "木门吱呀一声，你走进{地点}。{感官}——这里是旅人们交流情报的地方。",
        "一阵{气象}中，你推开了酒馆的门。{开场}立刻映入眼帘。",
        "你推门而入。{第一感受}——{地点}内人声鼎沸，{特色}。",
        "穿过嘈杂的街道，你来到了一家酒馆前。{描述}门后似乎别有洞天。",
    ],
    "森林": [
        "穿过最后一片灌木丛，眼前的景象让你屏住呼吸——{景象}。",
        "幽暗的{特点}中，{发现}。",
        "当你踏入这片森林，{感受}。{特殊}。",
        "{气象}透过层层枝叶洒下，在{环境}中，{细节}。",
        "古树的{形态}如同沉睡的守卫，{描述}。",
        "你深入林中，{感受}。{事件}。",
        "脚下是{地面}，四周是{环境}。{氛围}。",
        "迷雾在树干间缓缓流动。{感官}——这里似乎远离了人世。",
    ],
    "村庄": [
        "袅袅炊烟升起，你走进了{名称}。{景象}。",
        "鸡犬相闻中，{感受}。这里是{特点}的{地点}。",
        "青石板路在脚下延伸，你来到了一处{风格}的村庄。{细节}。",
        "还未进村，{特点}就先传入了你的感知。{场景}。",
        "村口的老树投下斑驳阴影，{描述}。",
        "阳光洒在屋顶上，{感受}。{名称}是个{氛围}的地方。",
        "你踏入村中，{第一感受}——{环境}。",
        "{气象}中，{地点}的轮廓渐渐清晰。{特色}。",
    ],
    "城镇": [
        "穿过城门，{感受}。宽阔的街道两旁{特点}。",
        "熙熙攘攘的人群中，{描述}。这是{名称}。",
        "城门口的守卫打量着你，而你则被眼前的{景象}所吸引。{环境}。",
        "你踏入{名称}，{感受}。{细节}。",
        "街道上{声音}此起彼伏，{特点}。",
        "城墙之内，{氛围}。{地点}的{特色}引人注目。",
        "穿过拥挤的市集，{感受}。{描述}。",
        "{气象}中，你来到了{名称}。{特色}。",
    ],
    "城堡": [
        "巍峨的城墙在阳光下投下巨大阴影，{感受}。",
        "穿过吊桥，{环境}。这里是{特点}的城堡。",
        "沉重的木门在身后关上，{描述}。",
        "石墙冰冷而庄严，{氛围}。{细节}。",
        "你踏入城堡庭院，{感受}。{特殊}。",
        "铠甲的反光在走廊尽头闪烁，{描述}。",
        "{气象}中，城堡的{特点}显得格外{氛围}。",
        "城门大开，{感受}。{名称}在等待着访客。",
    ],
    "洞穴": [
        "冰冷的水珠从洞顶滴落，{感受}。幽暗的洞穴中只有{特点}。",
        "你踏入洞口，{环境}。一股{气味}扑面而来。",
        "磷火摇曳，{描述}。这里是{特点}的洞穴。",
        "黑暗中似乎有什么在注视着你的到来，{感受}。",
        "狭窄的通道豁然开朗，眼前的景象让你{反应}——{场景}。",
        "洞壁上闪烁着奇异的{矿物}，{氛围}。",
        "水滴声在寂静中回响，{感受}。{特殊}。",
        "阴冷的空气让你打了个寒颤，{描述}。",
    ],
}


# ============================================================================
# 随机事件池 - 场景生成时注入的随机事件
# ============================================================================

_RANDOM_EVENT_POOL: dict[str, list[dict]] = {
    # 天气相关事件
    "weather": [
        {"type": "weather", "trigger": "突然", "event": "一阵突如其来的暴雨倾盆而下，你匆忙寻找遮蔽处。", "impact": "气氛骤然紧张"},
        {"type": "weather", "trigger": "正当", "event": "细雨开始飘落，给周围笼上一层朦胧的雾气。", "impact": "氛围变得神秘"},
        {"type": "weather", "trigger": "忽然", "event": "一阵狂风卷过，尘土飞扬中你眯起了眼睛。", "impact": "平添几分萧瑟"},
        {"type": "weather", "trigger": "就在这时", "event": "雪花开始飘落——明明是盛夏，这里却异常寒冷。", "impact": "透着一丝诡异"},
        {"type": "weather", "trigger": "骤然", "event": "乌云遮蔽了阳光，天色瞬间暗了下来。", "impact": "压迫感油然而生"},
    ],
    # 路人/角色事件
    "passerby": [
        {"type": "passerby", "trigger": "正当你", "event": "一个匆匆而过的旅人与你擦肩，低声咕哝着什么。", "impact": "引起了你的好奇"},
        {"type": "passerby", "trigger": "忽然", "event": "一个衣衫褴褛的孩子从巷子里窜出，撞了你一下就跑了。", "impact": "消失在人群中"},
        {"type": "passerby", "trigger": "就在这时", "event": "一位身着长袍的老者从你身旁经过，目光深邃地看了你一眼。", "impact": "意味深长"},
        {"type": "passerby", "trigger": "忽然", "event": "一阵喧哗声从远处传来——似乎有人在追逐。", "impact": "打破了周围的宁静"},
        {"type": "passerby", "trigger": "正当你", "event": "一个戴着面具的陌生人在角落里注视着人群，看不清表情。", "impact": "令人不安"},
    ],
    # 突发事件
    "incident": [
        {"type": "incident", "trigger": "忽然", "event": "「砰」的一声，某处传来玻璃破碎的声响！", "impact": "人群一阵骚动"},
        {"type": "incident", "trigger": "就在这时", "event": "远处传来一阵惊呼——似乎发生了什么事故。", "impact": "众人的目光纷纷投去"},
        {"type": "incident", "trigger": "骤然", "event": "地面微微震动，片刻后恢复平静。", "impact": "像是某种预兆"},
        {"type": "incident", "trigger": "忽然", "event": "一声尖锐的口哨响起——你警觉地环顾四周。", "impact": "似乎有什么即将发生"},
        {"type": "incident", "trigger": "正当你", "event": "一封信不知从何处飘落在你脚边，似乎有人故意丢下的。", "impact": "上面写着什么？"},
    ],
    # 环境细节事件
    "ambient": [
        {"type": "ambient", "trigger": "你注意到", "event": "墙上的一张告示已经泛黄，似乎很久没人看过了。", "impact": "但内容依稀可辨"},
        {"type": "ambient", "trigger": "就在这时", "event": "角落里的烛火摇曳了一下，投下诡异的影子。", "impact": "气氛微妙地变化了"},
        {"type": "ambient", "trigger": "忽然", "event": "空气中飘来一丝异样的气味——不是这里该有的味道。", "impact": "你警觉地嗅了嗅"},
        {"type": "ambient", "trigger": "你听到", "event": "远处传来钟声，沉闷而悠长——似乎在提醒着什么。", "impact": "钟声回荡在空气中"},
        {"type": "ambient", "trigger": "你发现", "event": "地面上有一串奇怪的脚印，似乎通向某个方向。", "impact": "有人从这里经过"},
    ],
}

# 随机事件气味词库
_EVENT_SMELLS = ["烤肉香", "酒香", "泥土腥", "腐叶", "金属味", "花香", "烟尘", "潮湿霉味", "香料味", "松脂香"]
_EVENT_SOUNDS = ["旅人的笑声", "酒杯碰撞声", "低沉的交谈", "远处的琴声", "孩子的嬉闹", "马蹄声", "磨刀声", "风铃声", "骰子滚动声", "窃窃私语"]
_EVENT_ATMOSPHERE = ["温馨热闹", "低沉压抑", "神秘诡异", "紧张不安", "平静祥和", "躁动不安", "阴郁沉闷", "欢快轻松", "诡异寂静", "喧嚣嘈杂"]


# ============================================================================
# 动态 Atmosphere 生成系统
# ============================================================================

# Atmosphere 元素词库 - 按场景类型分组
_ATMOSPHERE_ELEMENTS: dict[str, dict[str, list[str]]] = {
    "酒馆": {
        "light": ["昏黄的烛光摇曳", "温暖的壁炉火光", "油灯散发的柔和光芒", "透过窗缝的月光", "火光在墙壁上投下跳动的影子"],
        "sound": ["酒杯碰撞的叮当声", "旅人的谈笑声此起彼伏", "角落里流浪歌手的琴声", "骰子在木桌上滚动的声音", "壁炉中木柴燃烧的噼啪声"],
        "smell": ["麦酒和烤肉的香气", "烟草和汗水的混合气味", "香料热红酒的甜香", "陈年木桶散发的醇厚酒香", "壁炉烤肉的诱人香味"],
        "temperature": ["温暖如春", "有些闷热", "凉爽宜人", "壁炉旁热烘烘的", "门口透进一丝凉意"],
        "mood": ["温馨热闹", "喧嚣嘈杂", "低沉压抑", "躁动不安", "平静祥和"],
    },
    "森林": {
        "light": ["斑驳的阳光透过树叶缝隙洒落", "幽暗的树冠遮蔽了大部分光线", "迷雾中透出诡异的微光", "傍晚的余晖将树影拉得很长", "磷火在黑暗中闪烁"],
        "sound": ["风吹过树叶的沙沙声", "不知名鸟儿的啼鸣", "远处溪流的潺潺水声", "脚踩落叶的轻微碎裂声", "猫头鹰的低沉叫声"],
        "smell": ["泥土和腐叶的气息", "野花的淡淡清香", "潮湿苔藓的味道", "松脂的清冽香气", "雨后森林的清新气息"],
        "temperature": ["阴凉湿润", "温暖而潮湿", "寒冷刺骨", "清爽宜人", "雾气中带着凉意"],
        "mood": ["幽静神秘", "阴森诡异", "宁静祥和", "危机四伏", "诡异寂静"],
    },
    "村庄": {
        "light": ["清晨的阳光洒在屋顶上", "夕阳将村庄染成金色", "炊烟在光线中袅袅升起", "灯笼在暮色中亮起柔和的光", "阴雨天的灰蒙蒙光线"],
        "sound": ["鸡鸣犬吠此起彼伏", "孩童在巷弄间嬉闹的笑声", "铁匠敲打铁器的叮当声", "牛羊归圈的嘈杂声", "村民们的闲聊声"],
        "smell": ["饭菜的诱人香味", "泥土和青草的气息", "牲畜棚散发的气味", "新鲜出炉面包的麦香", "炊烟的气味"],
        "temperature": ["温暖舒适", "清晨有些凉意", "午后阳光暖洋洋的", "傍晚凉风习习", "阴天让人感到阴冷"],
        "mood": ["宁静祥和", "温馨热闹", "繁忙充实", "悠闲自得", "平静如水"],
    },
    "城镇": {
        "light": ["阳光明媚,街道明亮", "市集的旗帜在光中飘动", "城门的火把照亮入口", "傍晚的街道渐暗,店铺灯火渐亮", "雨后的街道反射着灰白的光"],
        "sound": ["商贩的吆喝声此起彼伏", "马车经过石板路的辘辘声", "人群嘈杂的交谈声", "远处钟楼的报时声", "工匠工具敲打的声音"],
        "smell": ["各种食物混合的香气", "皮革和马匹的气味", "香水和化妆品的气息", "铁匠铺的金属味道", "面包房飘出的香味"],
        "temperature": ["热闹而温暖", "阳光暴晒下有些炎热", "阴凉处清爽宜人", "傍晚凉风习习", "雨后空气清新"],
        "mood": ["繁华热闹", "喧嚣嘈杂", "繁忙紧张", "熙熙攘攘", "活力四射"],
    },
    "城堡": {
        "light": ["透过彩色玻璃窗的光线", "火把在走廊墙壁上投下光影", "阴暗大厅中微弱的光", "庭院中被阳光照耀的盔甲", "月光照进高耸的窗户"],
        "sound": ["铠甲碰撞的铿锵声", "卫兵换岗的口号声", "远处大厅传来的宴会声", "脚步在石板上回响", "风吹过走廊的呜咽声"],
        "smell": ["石墙的潮湿霉味", "金属和皮革的气息", "陈年木材的味道", "地下室散发的阴冷气息", "炉火燃烧的烟熏味"],
        "temperature": ["阴冷潮湿", "大厅里炉火温暖", "石墙透着凉意", "走廊里寒风阵阵", "地下牢房阴冷刺骨"],
        "mood": ["庄严威压", "阴森诡异", "戒备森严", "沉闷压抑", "神秘幽暗"],
    },
    "洞穴": {
        "light": ["零星的磷光照亮周围", "水珠反射着微弱的光", "黑暗几乎伸手不见五指", "洞口透进一缕光线", "钟乳石上的矿物闪烁"],
        "sound": ["水滴从洞顶滴落的回声", "远处水流的声音", "蝙蝠翅膀拍打的细微声响", "风穿过狭窄通道的呼啸", "自己脚步声的回响"],
        "smell": ["潮湿阴冷的霉味", "地下水流的腥味", "蝙蝠粪便的气味", "地下真菌的气息", "矿物质散发的气味"],
        "temperature": ["冰冷刺骨", "阴冷潮湿", "有些闷热潮湿", "洞口凉意袭人", "深处寒气逼人"],
        "mood": ["幽暗恐怖", "诡异寂静", "阴森压抑", "神秘莫测", "死寂沉沉"],
    },
    "default": {
        "light": ["普通的光线", "柔和的光照", "昏暗的光线", "明亮的光线", "朦胧的光线"],
        "sound": ["寂静无声", "微弱的声音", "远处传来的声响", "周围环境的声响", "令人不安的沉默"],
        "smell": ["普通的气味", "淡淡的异味", "难以名状的气味", "潮湿的气息", "金属的味道"],
        "temperature": ["温度适宜", "有些寒冷", "有些闷热", "阴凉", "凉爽"],
        "mood": ["普通", "平静", "紧张", "压抑", "神秘"],
    },
}

# 战斗后 atmosphere 变体
_POST_COMBAT_ATMOSPHERE_VARIANTS: dict[str, list[str]] = {
    "酒馆": ["战后余生的紧张气氛尚未散去", "酒客们窃窃私语,似乎在议论刚才的战斗", "空气中弥漫着战斗后的硝烟味"],
    "森林": ["战斗的痕迹还留在林间——折断的树枝、散落的羽毛", "战后一片狼藉,空气中仍有血腥味", "树木的伤痕诉说着刚才的激战"],
    "村庄": ["村民们惊恐地探出头来,战斗让他们人心惶惶", "战后村庄陷入一片死寂,村民们紧闭门窗", "战斗的喧嚣平息了,但紧张的气氛仍在"],
    "城镇": ["战后街道一片狼藉,行人匆匆而过", "战斗的消息很快传遍了整个城镇", "幸存者们开始从躲藏处走出来"],
    "城堡": ["战后城堡恢复了表面的平静", "卫兵们加强了巡逻,空气中弥漫着紧张", "战斗的痕迹被迅速清理干净"],
    "洞穴": ["战后洞穴恢复了死寂", "战斗中惊动了洞穴深处的某些东西", "战斗的声响在洞穴中回荡"],
    "default": ["战斗的痕迹随处可见", "空气中弥漫着战后的气息", "危险的气息尚未完全消散"],
}

# 任务阶段 atmosphere 变体
_QUEST_STAGE_ATMOSPHERE_VARIANTS: dict[str, dict[str, list[str]]] = {
    "村庄": {
        "早期": ["村民们神色紧张,似乎在担忧什么", "镇子笼罩在一种不安的氛围中", "村民们议论纷纷,气氛有些凝重"],
        "中期": ["村民们开始活跃起来,似乎看到了希望", "镇子里多了些外地来的旅人", "村民们对冒险者充满好奇"],
        "后期": ["村民们欢声笑语,充满庆祝的气氛", "镇子恢复了往日的生机", "村民们对冒险者充满感激"],
        "完成": ["村庄沉浸在胜利的喜悦中", "庆祝的气氛弥漫整个镇子", "村民们举行了简单的庆祝活动"],
    },
    "酒馆": {
        "早期": ["酒馆里气氛低沉,旅人们不愿多谈", "酒馆老板神情紧张,似乎有所顾虑", "角落里有人在低声议论"],
        "中期": ["酒馆里开始流传各种情报和传言", "旅人们变得健谈起来,愿意分享信息", "酒馆比之前热闹了不少"],
        "后期": ["酒馆里人声鼎沸,似乎在庆祝什么", "旅人们对即将到来的冒险充满期待", "酒馆老板终于露出了笑容"],
        "完成": ["酒馆里举杯庆祝,气氛热烈", "旅人们分享着胜利的故事", "月光酒馆充满了欢声笑语"],
    },
    "森林": {
        "早期": ["森林笼罩在神秘而危险的气息中", "古树的枝叶遮蔽了天空,气氛压抑", "林中弥漫着令人不安的寂静"],
        "中期": ["深入森林后,危险的气息更浓了", "树木间似乎有目光在注视着", "战斗的痕迹开始出现在周围"],
        "后期": ["森林中的气息变得狂暴而危险", "阴影中似乎隐藏着什么东西", "敌人就在附近,气氛极度紧张"],
        "完成": ["森林恢复了平静,危险已经解除", "阳光重新透过树冠洒下", "林中恢复了往日的祥和"],
    },
    "default": {
        "早期": ["气氛有些紧张", "空气中弥漫着不安", "周围环境透着一丝异样"],
        "中期": ["情况似乎有了变化", "周围开始有了不同的气息", "事情正在发生转折"],
        "后期": ["气氛变得紧张起来", "危险正在逼近", "关键时刻即将到来"],
        "完成": ["一切都结束了", "气氛终于缓和下来", "新的篇章开始了"],
    },
}

# 特殊 atmosphere 变体（天气系统等）
_SPECIAL_ATMOSPHERE_VARIANTS: dict[str, list[str]] = {
    "雨": ["细雨绵绵,空气中弥漫着潮湿的气息", "雨水顺着屋檐滴落,发出轻微的声响", "雨中的世界显得格外朦胧"],
    "雾": ["浓雾弥漫,视野受到严重限制", "雾气在地面缓缓流动,透着诡异", "朦胧中看不清周围的环境"],
    "风": ["强风呼啸,卷起尘土和落叶", "风中带着一股不祥的气息", "狂风让周围的一切都显得更加阴森"],
    "雪": ["雪花纷纷扬扬,世界被白色覆盖", "寒风中,雪地闪着冰冷的光", "雪后的寂静让人心生寒意"],
    "夜": ["夜幕降临,黑暗吞噬了一切", "月光洒下,将一切染成银白色", "夜晚的寂静透着危险"],
    "黎明": ["第一缕曙光划破黑暗", "清晨的露珠在微光中闪烁", "黎明带来新的希望"],
    "黄昏": ["夕阳西下,余晖将一切染红", "暮色渐浓,世界陷入朦胧", "黄昏的宁静中暗藏危机"],
}


# ============================================================================
# Atmosphere 动态生成系统 V2 - 按任务规格实现
# ============================================================================
# Atmosphere 元素词库 V2（每种场景类型 × 5 个维度：光线/温度/声音/气味/情绪）
# 用于 generate_atmosphere_v2() 函数，支持 consecutive_rounds 差异化策略

_ATMOSPHERE_ELEMENTS_V2: dict[str, dict[str, list[str]]] = {
    "酒馆": {
        "光线": ["昏黄烛光摇曳", "炉火噼啪作响", "油灯忽明忽暗", "窗外月光斜照"],
        "温度": ["温暖如春", "炉火烘得人昏昏欲睡", "热浪夹杂着酒香", "微凉的夜风从门缝渗入"],
        "声音": ["觥筹交错", "吟游诗人弹唱", "角落里的窃窃私语", "酒杯碰撞的清脆声", "木柴燃烧的噼啪声"],
        "气味": ["陈年麦酒香", "烤肉的油烟味", "潮湿木头的霉味", "壁炉的烟熏香", "香料热红酒的甜香"],
        "情绪": ["热闹欢快", "慵懒惬意", "暗流涌动", "神秘低沉", "躁动不安"],
    },
    "森林": {
        "光线": ["斑驳阳光透过树叶", "幽暗的树冠覆盖", "雾气中透出微光", "暮色四合", "磷火在黑暗中闪烁"],
        "温度": ["清凉宜人", "湿气弥漫", "阳光直射闷热", "夜间的寒意", "雾气中带着凉意"],
        "声音": ["鸟鸣啾啾", "树叶沙沙作响", "远处溪水流淌", "风吹过树梢的呼啸", "猫头鹰的低沉叫声"],
        "气味": ["泥土芬芳", "野花清香", "腐叶的气息", "松脂的清香", "雨后森林的清新"],
        "情绪": ["宁静祥和", "阴森诡异", "充满生机", "神秘莫测", "危机四伏"],
    },
    "村庄": {
        "光线": ["袅袅炊烟", "夕阳余晖", "清晨薄雾", "灯火初上", "灯笼在暮色中摇曳"],
        "温度": ["温暖平和", "傍晚的凉意", "正午的炎热", "夜间的寒气", "炉火的温暖"],
        "声音": ["鸡鸣狗吠", "孩童嬉闹", "牛羊归圈", "磨坊的风车声", "村民们的闲聊声"],
        "气味": ["家常饭菜香", "青草气息", "泥土味", "炊烟的味道", "新鲜面包的麦香"],
        "情绪": ["淳朴宁静", "忙碌充实", "温馨祥和", "静谧安详", "悠闲自得"],
    },
    "城镇": {
        "光线": ["繁华灯火", "正午阳光", "霓虹闪烁", "晨曦微露", "夕阳将街道染成金色"],
        "温度": ["人来人往的热气", "阴影处的凉意", "午后的燥热", "夜间的清冷", "阳光暴晒下炎热"],
        "声音": ["商贩吆喝", "马车辘辘", "人声鼎沸", "远处钟声", "工匠工具敲打声"],
        "气味": ["烤肉的香气", "香水的味道", "皮革和铁器", "鲜花的芬芳", "各种食物混合的香气"],
        "情绪": ["繁华热闹", "熙熙攘攘", "生机勃勃", "光怪陆离", "繁忙紧张"],
    },
    "城堡": {
        "光线": ["火把跳动", "高窗透光", "烛光摇曳", "月光倾泻", "彩色玻璃窗的光线"],
        "温度": ["阴冷潮湿", "壁炉的温暖", "石墙的寒意", "地下室阴森", "走廊里寒风阵阵"],
        "声音": ["脚步回响", "铠甲碰撞", "侍从低语", "远处宴会喧嚣", "卫兵换岗的口号声"],
        "气味": ["石壁的霉味", "蜡烛的烟熏味", "美酒的香气", "皮革和铁锈", "陈年木材的味道"],
        "情绪": ["威严压抑", "奢华庄严", "暗藏杀机", "肃穆沉重", "戒备森严"],
    },
    "洞穴": {
        "光线": ["漆黑一片", "磷火微光", "水珠反光", "裂缝透光", "钟乳石上的矿物闪烁"],
        "温度": ["阴冷刺骨", "潮湿闷热", "温泉的暖意", "通风口的凉风", "深处寒气逼人"],
        "声音": ["水滴回响", "风在洞穴中呼啸", "远处有未知声响", "地下水声潺潺", "蝙蝠翅膀拍打的细微声响"],
        "气味": ["潮湿霉味", "蝙蝠粪便的腥味", "地下水的清冽", "矿物的气息", "地下真菌的气息"],
        "情绪": ["幽暗恐惧", "压抑紧张", "神秘诡异", "危机四伏", "死寂沉沉"],
    },
    "平原": {
        "光线": ["一览无余", "夕阳西下", "乌云密布", "星光满天", "烈日当空"],
        "温度": ["温差极大", "烈日炎炎", "夜风凛冽", "正午酷热", "清晨的凉爽"],
        "声音": ["风声呼啸", "草浪沙沙", "远处狼嚎", "昆虫鸣叫", "老鹰的叫声"],
        "气味": ["青草香", "泥土气息", "野花芬芳", "远方炊烟", "干燥的尘土味"],
        "情绪": ["心旷神怡", "荒凉孤寂", "暴风雨前的压抑", "宁静广阔", "苍茫萧瑟"],
    },
    "河流": {
        "光线": ["波光粼粼", "水面反射月光", "阳光穿透清澈的水流", "雾气笼罩", "晨曦中的水面"],
        "温度": ["清凉透骨", "温暖适中", "水汽氤氲", "傍晚的凉意", "温泉的暖意"],
        "声音": ["水流潺潺", "瀑布轰鸣", "鱼儿跃出水面的声音", "青蛙鸣叫", "水车转动的吱呀声"],
        "气味": ["水草清香", "湿润的泥土味", "鱼腥味", "两岸花香", "清冽的水气"],
        "情绪": ["宁静惬意", "清凉舒爽", "神秘幽深", "生机盎然", "波光粼粼的愉悦"],
    },
}


def generate_atmosphere_v2(
    scene_type: str,
    consecutive_rounds: int = 1,
    current_state: dict[str, str] | None = None,
) -> dict[str, Any]:
    """
    动态生成差异化的 atmosphere（V2版本，按 consecutive_rounds 差异化策略）

    Args:
        scene_type: 场景类型 (酒馆/森林/村庄/城镇/城堡/洞穴/平原/河流)
        consecutive_rounds: 连续探索轮次（从进入场景开始计数）
        current_state: 当前的5维度状态 dict(光线/温度/声音/气味/情绪)，
                      用于第3+轮时基于当前状态修改

    Returns:
        dict with keys:
        - atmosphere_str: str, 完整的 atmosphere 描述字符串
        - atmosphere: str, 氛围词
        - atmosphere_tags: list[str], atmosphere 标签列表
        - light, sound, smell, temperature, mood: 各维度描述
        - state: dict, 更新后的5维度状态（用于下次调用传入）
    """
    rng = random.Random()

    if scene_type not in _ATMOSPHERE_ELEMENTS_V2:
        return {
            "atmosphere_str": f"你身处{scene_type}，周围一切平静。",
            "atmosphere": "平静",
            "atmosphere_tags": ["平静"],
            "light": "普通光线",
            "sound": "寂静无声",
            "smell": "普通气味",
            "temperature": "温度适宜",
            "mood": "平静",
            "state": {"光线": "普通光线", "温度": "温度适宜", "声音": "寂静无声", "气味": "普通气味", "情绪": "平静"},
        }

    elements = _ATMOSPHERE_ELEMENTS_V2[scene_type]
    dims = ["光线", "温度", "声音", "气味", "情绪"]

    if consecutive_rounds == 1:
        # 第1轮：完整 atmosphere，随机选择所有5个维度
        state = {dim: rng.choice(elements[dim]) for dim in dims}
        atmosphere = state["情绪"]
        atmosphere_str = f"{scene_type}中，{state['光线']}，{state['温度']}，{state['声音']}，{state['气味']}，{atmosphere}。"
        return {
            "atmosphere_str": atmosphere_str,
            "atmosphere": atmosphere,
            "atmosphere_tags": [atmosphere, state["温度"].split("的")[0] if "的" in state["温度"] else state["温度"]],
            **state,
            "state": state,
        }

    elif consecutive_rounds == 2:
        # 第2轮：省略一个维度（随机）
        omit_dim = rng.choice(dims)
        # 构建完整的 state（5个维度，但省略的维度为空字符串）
        state = {dim: "" for dim in dims}
        for dim in dims:
            if dim != omit_dim:
                state[dim] = rng.choice(elements[dim])
        atmosphere = state.get("情绪", rng.choice(elements["情绪"]))
        # 构建省略后的字符串
        parts = [state[d] for d in dims if d != omit_dim and state[d]]
        atmosphere_str = f"{scene_type}中，{'，'.join(parts)}，{atmosphere}。"
        return {
            "atmosphere_str": atmosphere_str,
            "atmosphere": atmosphere,
            "atmosphere_tags": [atmosphere],
            **{k: state.get(k, "") for k in dims},
            "state": state,
        }

    else:
        # 第3+轮：基于 current_state 只变化一个维度
        if current_state is None:
            # 无 current_state，降级到第1轮
            return generate_atmosphere_v2(scene_type, 1, None)

        # 深拷贝当前状态
        state = dict(current_state)

        # 随机选择一个维度进行变化
        change_dim = rng.choice(dims)
        new_element = rng.choice(elements[change_dim])
        old_element = state.get(change_dim, "")

        # 确保新元素与旧元素不同
        for _ in range(10):  # 最多重试10次确保真正变化
            if new_element != old_element:
                break
            new_element = rng.choice(elements[change_dim])

        state[change_dim] = new_element
        atmosphere = state.get("情绪", rng.choice(elements["情绪"]))

        # 变化后的完整描述
        parts = [state[d] for d in dims if d in state]
        atmosphere_str = f"{scene_type}中，{'，'.join(parts)}，{atmosphere}。"

        return {
            "atmosphere_str": atmosphere_str,
            "atmosphere": atmosphere,
            "atmosphere_tags": [atmosphere, state["温度"].split("的")[0] if "的" in state.get("温度", "") else state.get("温度", "")],
            **{k: state.get(k, "") for k in dims},
            "state": state,
        }


def generate_dynamic_atmosphere(
    scene_type: str,
    seed: int | None = None,
    game_state_context: dict | None = None,
    existing_tags: list[str] | None = None,
) -> dict[str, Any]:
    """
    生成动态 atmosphere（轻量级,无 LLM 调用）
    
    使用模板 + 随机变量组合,通过 seed 控制变体差异。\n\nArgs:\nscene_type: 场景类型 (酒馆/森林/村庄/城镇/城堡/洞穴)\nseed: 随机种子,相同种子产生相同 atmosphere\ngame_state_context: 游戏状态上下文 (用于战斗后/任务阶段等特殊 atmosphere)\nexisting_tags: 已存在的 atmosphere_tags (用于避免重复)\n\nReturns:\ndict with keys:\n- atmosphere: str, 氛围词 (如 "神秘诡异")\n- atmosphere_desc: str, 完整的 atmosphere 描述\n- atmosphere_tags: list[str], atmosphere 标签列表\n- light: str, 光线描述\n- sound: str, 声音描述\n- smell: str, 气味描述\n- temperature: str, 温度描述\n- mood: str, 氛围词
    """
    if seed is not None:
        rng = random.Random(seed)
    else:
        rng = random.Random()
    
    scene_type = scene_type if scene_type in _ATMOSPHERE_ELEMENTS else "default"
    elements = _ATMOSPHERE_ELEMENTS[scene_type]
    
    # 从游戏状态上下文判断是否需要特殊 atmosphere
    special_modifier = None
    quest_stage = None
    
    if game_state_context:
        # 战斗后 atmosphere
        if game_state_context.get("post_combat"):
            variants = _POST_COMBAT_ATMOSPHERE_VARIANTS.get(scene_type, _POST_COMBAT_ATMOSPHERE_VARIANTS["default"])
            special_modifier = rng.choice(variants)
        
        # 任务阶段 atmosphere
        quest_stage = game_state_context.get("quest_stage", "")
        if quest_stage and not special_modifier:
            stage_variants = _QUEST_STAGE_ATMOSPHERE_VARIANTS.get(scene_type, _QUEST_STAGE_ATMOSPHERE_VARIANTS["default"])
            if quest_stage in stage_variants:
                special_modifier = rng.choice(stage_variants[quest_stage])
    
    # 选择基础 atmosphere 元素
    light = rng.choice(elements["light"])
    sound = rng.choice(elements["sound"])
    smell = rng.choice(elements["smell"])
    temperature = rng.choice(elements["temperature"])
    mood = rng.choice(elements["mood"])
    
    # 构建 atmosphere_tags (用于重复检测)
    atmosphere_tags = [mood, temperature.split("的")[0] if "的" in temperature else temperature]
    if special_modifier:
        atmosphere_tags.append(special_modifier[:10])
    
    # 避免重复：如果 tag 已在 existing_tags 中,换一个 mood
    if existing_tags:
        for _ in range(10):  # 最多重试10次
            if mood in existing_tags:
                mood = rng.choice(elements["mood"])
                atmosphere_tags = [mood, temperature.split("的")[0] if "的" in temperature else temperature]
                if special_modifier:
                    atmosphere_tags.append(special_modifier[:10])
            else:
                break
    
    # 构建完整的 atmosphere 描述
    if special_modifier:
        atmosphere_desc = f"{light}。{sound}。空气中混着{smell}，让人感到{temperature}。{special_modifier}。整体氛围{mood}。"
    else:
        atmosphere_desc = f"{light}。{sound}。空气中混着{smell}，让人感到{temperature}。整体氛围{mood}。"
    
    return {
        "atmosphere": mood,
        "atmosphere_desc": atmosphere_desc,
        "atmosphere_tags": atmosphere_tags,
        "light": light,
        "sound": sound,
        "smell": smell,
        "temperature": temperature,
        "mood": mood,
    }


@dataclass
class SceneMetadata:
    """场景元数据"""
    id: str
    type: str  # forest, village, dungeon, etc.
    core_concept: str  # 核心思想
    tags: list[str] = field(default_factory=list)
    unique_features: list[str] = field(default_factory=list)
    danger_level: str = "medium"  # low, mid, high
    atmosphere: str = ""
    synopsis: str = ""  # 纲要(约50-100字)
    description: str = ""  # 详细内容
    npcs: list[dict] = field(default_factory=list)  # 常驻NPC
    events: list[dict] = field(default_factory=list)  # 可触发事件
    objects: list[dict] = field(default_factory=list)  # 场景可交互物品
    random_events: list[dict] = field(default_factory=list)  # 随机注入的事件(天气/路人/突发事件)
    created_at: float = 0.0
    atmosphere_history: list[dict] = field(default_factory=list)  # 动态 atmosphere 历史记录
    
    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "type": self.type,
            "core_concept": self.core_concept,
            "tags": self.tags,
            "unique_features": self.unique_features,
            "danger_level": self.danger_level,
            "atmosphere": self.atmosphere,
            "synopsis": self.synopsis,
            "description": self.description,
            "npcs": self.npcs,
            "events": self.events,
            "objects": self.objects,
            "random_events": self.random_events,
            "created_at": self.created_at,
            "atmosphere_history": self.atmosphere_history,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "SceneMetadata":
        return cls(**data)


class SceneRegistry:
    """
    场景注册表
    
    管理所有已生成场景的索引,支持按类型和标签查询
    """
    
    def __init__(self, storage_path: str = "data/scenes"):
        self.storage_path = Path(storage_path)
        self.storage_path.mkdir(parents=True, exist_ok=True)
        self._index: dict[str, list[str]] = {}  # type -> [scene_id, ...]
        self._scenes: dict[str, SceneMetadata] = {}
        
    def _get_index_file(self) -> Path:
        return self.storage_path / "index.json"
        
    def _get_scene_file(self, scene_id: str) -> Path:
        return self.storage_path / f"{scene_id}.json"
    
    async def load(self):
        """从磁盘加载索引"""
        index_file = self._get_index_file()
        if index_file.exists():
            with open(index_file, "r", encoding="utf-8") as f:
                self._index = json.load(f)
        
        # 加载所有场景元数据
        for scene_ids in self._index.values():
            for scene_id in scene_ids:
                scene_file = self._get_scene_file(scene_id)
                if scene_file.exists():
                    with open(scene_file, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        self._scenes[scene_id] = SceneMetadata.from_dict(data)
        
        logger.info(f"Loaded {len(self._scenes)} scenes from registry")
    
    async def save(self):
        """保存索引到磁盘"""
        # 保存索引
        with open(self._get_index_file(), "w", encoding="utf-8") as f:
            json.dump(self._index, f, ensure_ascii=False, indent=2)
        
        # 保存每个场景
        for scene_id, scene in self._scenes.items():
            with open(self._get_scene_file(scene_id), "w", encoding="utf-8") as f:
                json.dump(scene.to_dict(), f, ensure_ascii=False, indent=2)
        
        logger.debug(f"Saved {len(self._scenes)} scenes to registry")
    
    def register(self, scene: SceneMetadata):
        """注册新场景"""
        self._scenes[scene.id] = scene
        
        if scene.type not in self._index:
            self._index[scene.type] = []
        if scene.id not in self._index[scene.type]:
            self._index[scene.type].append(scene.id)
        
        logger.debug(f"Registered scene: {scene.id} (type={scene.type})")
    
    def get_by_id(self, scene_id: str) -> SceneMetadata | None:
        """通过ID获取场景"""
        return self._scenes.get(scene_id)
    
    def get_by_type(self, scene_type: str) -> list[SceneMetadata]:
        """获取指定类型的所有场景"""
        scene_ids = self._index.get(scene_type, [])
        return [self._scenes[sid] for sid in scene_ids if sid in self._scenes]
    
    def get_all_tags(self, scene_type: str) -> list[str]:
        """获取同类场景的所有标签(用于差异化)"""
        scenes = self.get_by_type(scene_type)
        all_tags = []
        for scene in scenes:
            all_tags.extend(scene.tags)
        return list(set(all_tags))
    
    def get_scene_atmosphere_tags(self, scene_id: str) -> list[str]:
        """获取场景的所有 atmosphere_tags（用于避免重复）"""
        scene = self._scenes.get(scene_id)
        if not scene:
            return []
        all_tags = []
        for hist in scene.atmosphere_history:
            all_tags.extend(hist.get("atmosphere_tags", []))
        return all_tags
    
    def add_atmosphere_to_history(self, scene_id: str, atmosphere_data: dict) -> None:
        """添加新的 atmosphere 到场景历史"""
        scene = self._scenes.get(scene_id)
        if not scene:
            return
        
        # 限制历史记录数量（最多保留10条）
        if len(scene.atmosphere_history) >= 10:
            scene.atmosphere_history.pop(0)
        
        # 使用时间戳和索引作为唯一标识
        import time
        entry = {
            "timestamp": time.time(),
            "index": len(scene.atmosphere_history),
            **atmosphere_data,
        }
        scene.atmosphere_history.append(entry)
        
        # 更新当前 atmosphere 为最新的
        scene.atmosphere = atmosphere_data.get("atmosphere", scene.atmosphere)
        
        logger.debug(f"Added atmosphere to scene {scene_id}: {atmosphere_data.get('atmosphere', 'unknown')}")
    
    def get_atmosphere_count(self, scene_id: str) -> int:
        """获取场景已生成的不同 atmosphere 数量"""
        scene = self._scenes.get(scene_id)
        if not scene:
            return 0
        return len(scene.atmosphere_history)
    
    def can_cycle_atmosphere(self, scene_id: str) -> bool:
        """检查是否可以循环使用 atmosphere（超过3个不同 atmosphere）"""
        return self.get_atmosphere_count(scene_id) >= 3


class LLMInterface(MiniMaxInterface):
    """
    LLM 接口抽象(基于 MiniMax API)
    
    继承自 MiniMaxInterface,复用其全部实现
    """
    
    def __init__(self, api_key: str | None = None):
        super().__init__(api_key=api_key)
    
    async def generate(
        self,
        prompt: str,
        system: str = "",
        temperature: float = 0.7,
    ) -> str:
        """调用 LLM 生成内容"""
        return await MiniMaxInterface.generate(self, prompt, system, temperature=temperature)


class SceneAgent:
    """
    场景生成子 Agent
    
    实现懒生成原则:玩家探索到未定义区域时,触发四步生成流程
    """
    
    def __init__(
        self,
        registry: SceneRegistry | None = None,
        llm: LLMInterface | None = None,
        api_key: str | None = None,
    ):
        self.registry = registry or SceneRegistry()
        self.llm = llm or LLMInterface(api_key=api_key)
        self._event_bus = None
        self._hooks = None
        self._subscriber_id = f"scene_agent_{id(self)}"
        
        # ========== Fallback 降级跟踪 ==========
        # 最近一次场景生成的 fallback 信息（供 GameMaster 查询）
        self._last_scene_fallback: bool = False
        self._last_fallback_tier: str | None = None
        
    async def initialize(self):
        """初始化:注册事件订阅"""
        self._event_bus = get_event_bus()
        self._hooks = get_hook_registry()
        
        # 加载已有场景
        await self.registry.load()
        
        # 注册事件订阅
        await self._event_bus.subscribe(
            EventType.SCENE_UPDATE,
            self._on_scene_update,
            self._subscriber_id,
            filter_fn=lambda e: "generate_new" in e.data
        )
        
        logger.info("SceneAgent initialized")
    
    async def _on_scene_update(self, event: Event):
        """处理场景更新事件(懒生成入口)"""
        data = event.data
        if data.get("generate_new"):
            scene_type = data.get("scene_type", "unknown")
            requirements = data.get("requirements", "")
            result = await self.generate_scene(scene_type, requirements)
            return result
        return None
    
    async def generate_scene(
        self,
        scene_type: str,
        requirements: str,
        quest_hint: str = "",
    ) -> SceneMetadata:
        """
        四步场景生成流程
        
        Args:
            scene_type: 场景类型(如 forest, village)
            requirements: 场景需求描述
            
        Returns:
            生成的场景元数据
        """
        get_logger().info("scene_agent", f"=== Scene generation START: scene_type={scene_type}, requirements={requirements[:50]}... ===")
        
        # 重置 fallback 跟踪（每次生成新场景时）
        self._last_scene_fallback = False
        self._last_fallback_tier = None
        
        # Step 1: 场景登记查询
        existing_tags = self.registry.get_all_tags(scene_type)
        logger.info(f"Step 1: Found {len(existing_tags)} existing tags for {scene_type}")
        
        # Hook: before scene generation
        if self._hooks:
            await self._hooks.trigger(HookNames.BEFORE_SCENE_UPDATE, scene_type, requirements)
        
        # Step 2: 差异化定位
        try:
            get_logger().debug("scene_agent", f"LLM API call: generate_differentiation (scene_type={scene_type})")
            core_concept = await self.llm.generate_differentiation(
                scene_type, existing_tags, requirements
            )
            logger.info(f"Step 2: Differentiation = {core_concept}")
        except Exception as e:
            # API 不可用时,使用占位符
            core_concept = f"Unique {scene_type} location: {requirements}"
            logger.warning(f"Using placeholder core_concept (API error: {type(e).__name__})")
            get_logger().warning("scene_agent", f"LLM API call failed for generate_differentiation: {type(e).__name__}")

        # Step 3: 场景纲要生成
        try:
            get_logger().debug("scene_agent", f"LLM API call: generate_synopsis (core_concept={core_concept[:30]}...)")
            synopsis_data = await self.llm.generate_synopsis(core_concept, scene_type)
            logger.info(f"Step 3: Synopsis generated")
        except Exception as e:
            # Fallback: 动态生成 atmosphere（替代硬编码 "mysterious"）
            fallback_atmosphere = generate_atmosphere_v2(scene_type, consecutive_rounds=1)
            synopsis_data = {
                "atmosphere": fallback_atmosphere.get("atmosphere", "平静"),
                "danger_level": "mid",
                "synopsis": f"一个{scene_type}类型的地点:{requirements}",
                "tags": [scene_type],
                "unique_features": []
            }
            logger.warning(f"Using placeholder synopsis with dynamic atmosphere (API error: {type(e).__name__})")
            get_logger().warning("scene_agent", f"LLM API call failed for generate_synopsis: {type(e).__name__}")
        
        # Step 4: 详细内容生成（带错误分类的 Fallback 策略）
        detail_data = None
        is_fallback = False
        fallback_tier = None
        
        try:
            detail_prompt_hint = ""
            if quest_hint:
                detail_prompt_hint = f"\n\n【任务线索】请将以下提示自然融入场景描述中：{quest_hint}"
            get_logger().debug("scene_agent", f"LLM API call: generate_detail (scene_type={scene_type})")
            detail_data = await self.llm.generate_detail(
                synopsis_data["synopsis"] + detail_prompt_hint,
                scene_type,
                synopsis_data["atmosphere"],
                core_concept=core_concept,  # 传递差异化核心概念，提供具体方向
                existing_tags=existing_tags  # 传递已有标签，用于避免重复
            )
            logger.info(f"Step 4: Detail generated")
        except Exception as e:
            # ========== 新的 Fallback 错误处理策略 ==========
            failure_type, error_msg = classify_exception(e)
            logger.warning(f"Step 4 Detail generation failed: {error_msg}")
            get_logger().warning("scene_agent", f"LLM API call failed for generate_detail: {failure_type.value} - {error_msg}")
            
            if should_fallback(failure_type):
                # 网络错误 / 未知错误 → 使用 Fallback
                is_fallback = True
                
                # 根据请求复杂度选择 Fallback 档次
                # 复杂度 = synopsis长度 + requirements长度 + 是否有quest_hint
                complexity_score = len(synopsis_data.get("synopsis", "")) + len(requirements)
                if quest_hint:
                    complexity_score += 20
                
                # 选择降级档次：复杂度越高，使用越高级的 fallback
                if complexity_score < 50:
                    fallback_tier = FallbackTier.LIGHT
                elif complexity_score < 120:
                    fallback_tier = FallbackTier.MEDIUM
                else:
                    fallback_tier = FallbackTier.HEAVY
                
                # ========== 场景语义最低 tier 保障 ==========
                # 酒馆/城堡 ≥ MEDIUM（需要更多 NPC/社交内容）
                # 洞穴/危险区域 ≥ MEDIUM（需要更丰富的描写）
                # 森林/平原/河流 ≥ LIGHT（当前最小粒度，始终满足）
                # 村庄/城镇 ≥ LOW（LOW 不存在，等效于无约束）
                # Tier 优先级：HEAVY > MEDIUM > LIGHT
                _MIN_TIER_BY_TYPE = {
                    "酒馆": FallbackTier.MEDIUM,
                    "城堡": FallbackTier.MEDIUM,
                    "洞穴": FallbackTier.MEDIUM,
                    "森林": FallbackTier.LIGHT,
                    "平原": FallbackTier.LIGHT,
                    "河流": FallbackTier.LIGHT,
                    "村庄": FallbackTier.LIGHT,  # LOW 不存在，用 LIGHT 代替（实际无约束）
                    "城镇": FallbackTier.LIGHT,  # LOW 不存在，用 LIGHT 代替（实际无约束）
                }
                min_tier = _MIN_TIER_BY_TYPE.get(scene_type, FallbackTier.LIGHT)
                # Tier 优先级排序: LIGHT=0, MEDIUM=1, HEAVY=2
                tier_priority = {FallbackTier.LIGHT: 0, FallbackTier.MEDIUM: 1, FallbackTier.HEAVY: 2}
                if tier_priority.get(fallback_tier, 0) < tier_priority.get(min_tier, 0):
                    fallback_tier = min_tier
                    logger.info(f"Fallback tier upgraded to {fallback_tier.value} (scene type {scene_type} requires ≥ {min_tier.value})")
                # ========== 场景语义最低 tier 保障结束 ==========
                
                logger.info(f"Using fallback tier={fallback_tier.value} (complexity={complexity_score})")
                get_logger().warning("scene_agent", f"⚠️ 当前为简化叙事模式 (Fallback tier={fallback_tier.value})")
                
                # 使用新的 fallback 系统
                detail_data = get_fallback_scene(scene_type, fallback_tier, quest_hint)
                
                # 更新实例变量，供 GameMaster 查询
                self._last_scene_fallback = True
                self._last_fallback_tier = fallback_tier.value
                
            elif should_retry(failure_type):
                # 内容安全过滤 → 不 fallback，抛出异常让上层处理
                logger.error(f"Content filter error - user should retry: {error_msg}")
                raise e
            else:
                # 格式错误 / Credentials 错误 → 不 fallback，报错
                logger.error(f"Non-retryable error: {failure_type.value} - {error_msg}")
                raise e
            # ========== Fallback 策略结束 ==========
        
        # 注入随机事件（场景差异化增强）
        injected_events = self._inject_random_events(scene_type)
        
        # 组装场景元数据
        scene = SceneMetadata(
            id=f"{scene_type}_{uuid.uuid4().hex[:8]}",
            type=scene_type,
            core_concept=core_concept,
            tags=synopsis_data.get("tags", []),
            unique_features=synopsis_data.get("unique_features", []),
            danger_level=synopsis_data.get("danger_level", "mid"),
            atmosphere=synopsis_data.get("atmosphere", ""),
            synopsis=synopsis_data.get("synopsis", ""),
            description=detail_data.get("description", ""),
            # Use fallback NPCs if LLM returns empty list (bug fix for NPC scene state inheritance)
            npcs=detail_data.get("npcs", []) or self._generate_fallback_npcs(scene_type),
            events=detail_data.get("events", []) + injected_events,
            objects=detail_data.get("objects", []),
            random_events=injected_events,
            created_at=asyncio.get_event_loop().time()
        )
        
        # ========== Fallback 场景不持久化 ==========
        # Fallback 仅用于当前回合输出，下次同一场景请求时重新尝试 LLM 生成
        if is_fallback:
            # 不注册到 SceneRegistry，不保存到磁盘
            logger.info(f"Fallback scene generated (not persisted): {scene.id}, tier={fallback_tier.value}")
            get_logger().info("scene_agent", f"=== Fallback scene generated (tier={fallback_tier.value}): scene_id={scene.id} ===")
        else:
            # 正常场景：注册场景
            self.registry.register(scene)
            await self.registry.save()
            logger.info(f"Scene generated and registered: {scene.id}")
            get_logger().info("scene_agent", f"=== Scene generation END: scene_id={scene.id}, scene_type={scene_type}, core_concept={core_concept[:30]}... ===")
        
        # Hook: after scene generation
        if self._hooks:
            await self._hooks.trigger(HookNames.AFTER_SCENE_UPDATE, scene)
        
        # 发布事件（包含 fallback 标记，让 GameMaster 可以追踪）
        event_data = {
            "scene": scene.to_dict(),
            "is_new": True,
            "is_fallback": is_fallback,
            "fallback_tier": fallback_tier.value if fallback_tier else None,
        }
        await self._event_bus.publish(Event(
            type=EventType.SCENE_UPDATE,
            data=event_data,
            source=self._subscriber_id
        ))
        
        return scene

    def _generate_fallback_npcs(self, scene_type: str) -> list[dict]:
        """
        基于场景类型生成合理的 fallback NPC 列表
        
        当 LLM API 不可用时，为场景生成有意义的占位符 NPC
        """
        import random
        
        # 场景类型 → NPC 配置
        scene_npc_configs = {
            "酒馆": [
                {"name": "酒馆老板", "role": "merchant", "personality": "精明世故，善于经商", "dialogue_style": "圆滑老练"},
                {"name": "流浪歌手", "role": "bard", "personality": "热情开朗，喜欢讲故事", "dialogue_style": "吟游诗人般"},
                {"name": "神秘陌生人", "role": "mysterious_wanderer", "personality": "沉默寡言，眼神深邃", "dialogue_style": "低沉神秘"},
            ],
            "森林": [
                {"name": "森林精灵", "role": "elf", "personality": "高傲优雅，熟悉自然", "dialogue_style": "优雅缓慢"},
                {"name": "年迈猎人", "role": "hunter", "personality": "沉稳可靠，经验丰富", "dialogue_style": "简洁有力"},
                {"name": "迷路的旅人", "role": "traveler", "personality": "焦虑不安，渴望帮助", "dialogue_style": "急促紧张"},
            ],
            "村庄": [
                {"name": "村长", "role": "village_elder", "personality": "德高望重，关心村民", "dialogue_style": "稳重慈祥"},
                {"name": "铁匠", "role": "blacksmith", "personality": "豪爽直率，手艺精湛", "dialogue_style": "洪亮有力"},
                {"name": "小女孩", "role": "child", "personality": "天真活泼，好奇心强", "dialogue_style": "稚嫩清脆"},
            ],
            "城镇": [
                {"name": "守卫队长", "role": "guard_captain", "personality": "尽职尽责，警惕性高", "dialogue_style": "严肃正式"},
                {"name": "商人", "role": "merchant", "personality": "精明能干，消息灵通", "dialogue_style": "礼貌热情"},
                {"name": "贵族小姐", "role": "noble", "personality": "娇生惯养，举止端庄", "dialogue_style": "优雅矜持"},
            ],
            "城堡": [
                {"name": "皇家卫兵", "role": "royal_guard", "personality": "忠诚勇敢，纪律严明", "dialogue_style": "正式威严"},
                {"name": "宫廷侍女", "role": "handmaiden", "personality": "细心周到，谨慎低调", "dialogue_style": "柔和恭敬"},
                {"name": "落魄骑士", "role": "fallen_knight", "personality": "意志消沉，怀念过去", "dialogue_style": "低沉忧郁"},
            ],
            "洞穴": [
                {"name": "洞穴隐士", "role": "hermit", "personality": "独来独往，知识渊博", "dialogue_style": "平静深邃"},
                {"name": "逃跑的矿工", "role": "miner", "personality": "惊恐万分，心有余悸", "dialogue_style": "颤抖急促"},
                {"name": "黑暗精灵", "role": "dark_elf", "personality": "神秘莫测，居无定所", "dialogue_style": "阴冷低沉"},
            ],
        }
        
        npc_pool = scene_npc_configs.get(scene_type, scene_npc_configs["村庄"])
        # 随机选择 1-2 个 NPC
        num_npcs = random.randint(1, 2)
        selected = random.sample(npc_pool, min(num_npcs, len(npc_pool)))
        
        # 为每个 NPC 添加唯一 ID
        for npc in selected:
            npc["id"] = f"npc_{uuid.uuid4().hex[:8]}"
        
        return selected

    def _inject_random_events(self, scene_type: str) -> list[dict]:
        """
        注入随机事件 - 场景差异化增强核心
        
        每次生成场景时，随机选择 1-2 个事件注入，增加场景的变化性和重玩性。\n同一地点不同次进入会有不同的事件。\n\nArgs:\nscene_type: 场景类型\n\nReturns:\n注入的随机事件列表
        """
        # 随机选择事件类型组合
        event_types = list(_RANDOM_EVENT_POOL.keys())
        num_events = random.randint(1, 2)
        selected_types = random.sample(event_types, min(num_events, len(event_types)))
        
        injected = []
        for event_type in selected_types:
            pool = _RANDOM_EVENT_POOL[event_type]
            # 每次从池中随机选择（避免重复）
            chosen = random.choice(pool)
            injected.append(chosen)
        
        logger.debug(f"Injected {len(injected)} random events for {scene_type}")
        return injected

    def _apply_opening_template(self, scene_type: str, base_description: str) -> str:
        """
        应用随机开场模板 - 避免千篇一律的「推开大门，看到...」开场
        
        每次进入同一场景，使用不同的开场叙述方式。\n\nArgs:\nscene_type: 场景类型\nbase_description: 基础场景描述\n\nReturns:\n应用了随机开场的完整描述
        """
        templates = _OPENING_TEMPLATES.get(scene_type)
        if not templates:
            return base_description
        
        # 随机选择开场模板
        template = random.choice(templates)
        
        # 准备替换词
        smell = random.choice(_EVENT_SMELLS)
        sound = random.choice(_EVENT_SOUNDS)
        atmosphere = random.choice(_EVENT_ATMOSPHERE)
        
        # 场景特色词
        scene_keywords = {
            "酒馆": {"地点": "酒馆", "特色": "麦酒香气", "氛围": "温暖热闹"},
            "森林": {"地点": "森林", "特色": "古树参天", "氛围": "幽静神秘"},
            "村庄": {"地点": "村庄", "特色": "炊烟袅袅", "氛围": "宁静祥和"},
            "城镇": {"地点": "城镇", "特色": "商铺林立", "氛围": "繁华热闹"},
            "城堡": {"地点": "城堡", "特色": "石墙高耸", "氛围": "庄严威压"},
            "洞穴": {"地点": "洞穴", "特色": "磷光摇曳", "氛围": "阴冷幽暗"},
        }
        keywords = scene_keywords.get(scene_type, {"地点": scene_type, "特色": "普通", "氛围": "一般"})
        
        # 替换模板中的占位符
        replacements = {
            "{香气}": smell,
            "{气味}": smell,
            "{声音}": sound,
            "{环境}": base_description[:50] + "...",
            "{氛围}": atmosphere,
            "{特点}": keywords["特色"],
            "{地点}": keywords["地点"],
            "{景象}": base_description[:60] + "...",
            "{感受}": random.choice(["你感到一阵恍惚", "你屏住呼吸", "你不由自主地停下脚步", "你的直觉告诉你这里不简单", "你的心跳加快了"]),
            "{特殊}": random.choice(["空气中似乎有什么在注视着你", "你隐约感觉到某种危险", "这里的一切都透着古怪", "某种预感在你心头升起"]),
            "{气象}": random.choice(["薄雾", "细雨", "斜阳", "月光", "星光", "阴云", "晚霞"]),
            "{感官}": random.choice([f"空气中弥漫着{smell}", f"远处传来{sound}", f"整体{atmosphere}"]),
            "{细节}": random.choice(["墙角的烛火摇曳不定", "地上散落着一些奇怪的痕迹", "空气中有一股异样的气息", "某处传来轻微的响动"]),
            "{描述}": base_description[:40] + "...",
            "{特色}": keywords["特色"],
            "{名称}": random.choice(["月叶镇", "星光酒馆", "迷雾森林", "寒铁堡", "碧溪村", "银溪镇"]),
            "{场景}": base_description[:50] + "...",
            "{反应}": random.choice(["屏住呼吸", "倒吸一口凉气", "不自觉地握紧武器", "心跳加速", "瞳孔收缩"]),
            "{开门}": random.choice(["推门而入", "踏入", "走进", "穿过人群进入"]),
            "{第一感受}": random.choice(["喧闹扑面而来", "温暖包围了你", "一股气息扑面而来", "昏暗而拥挤"]),
            "{反应}": random.choice(["惊讶", "警惕", "好奇", "不安", "兴奋"]),
            "{反应}": random.choice(["你屏住呼吸", "你的手按上了剑柄", "你不自觉地后退一步", "你定睛打量四周"]),
            "{反应}": random.choice(["让你心头一紧", "让你感到不安", "引起了你的警觉", "让你放松了警惕"]),
        }
        
        result = template
        for placeholder, value in replacements.items():
            result = result.replace(placeholder, value)
        
        # 如果没有完全替换，返回原始模板+基础描述
        if "{" in result:
            result = base_description
        
        return f"{result}\n\n{base_description}"

    def _generate_fallback_description(self, scene_type: str, quest_hint: str = "") -> str:
        """
        生成沉浸式的 fallback 场景描述 - 场景差异化增强版

        当 LLM API 不可用时，生成有沉浸感的场景描述，\n并将任务线索自然融入场景之中。使用随机开场模板，\n同一地点每次进入有不同的开场叙述。
        """
        # 场景类型 → 氛围描述模板
        scene_descriptions = {
            "酒馆": [
                "温暖的烛光在木质墙壁上投下摇曳的影子。空气中弥漫着麦酒和烤肉混合的香气，旅人们围坐在橡木桌旁，低声交谈着各种传闻。壁炉中的火焰噼啪作响，为整个空间增添了几分温馨。",
                "推开厚重的木门，一股混杂着麦酒香气的暖流扑面而来。酒馆内人声鼎沸，旅人们大声谈笑，有人正在角落里弹奏着古老的民谣。老板是一位圆胖的中年人，正熟练地擦拭着酒杯。",
                "昏黄的灯光下，酒客们的谈笑声此起彼伏。空气中飘荡着烟草和麦酒的味道，墙上的鹿头装饰在火光中显得格外神秘。",
            ],
            "森林": [
                "高大的古树遮天蔽日，阳光只能通过层层枝叶的缝隙洒下斑驳的光点。脚下是松软的落叶，踩上去发出轻微的沙沙声。远处传来不知名鸟儿的啼鸣，空气中弥漫着泥土和青草的气息。",
                "幽暗的树林中，迷雾在树干间缓缓流动。巨大的树根如同沉睡的巨兽，盘踞在蜿蜒的小径两旁。偶尔有不知名的小动物从灌木丛中窜过，发出窸窣的声响。",
                "穿过密集的灌木丛，眼前豁然开朗。古老的树木高耸入云，树干上爬满了青苔。空气中弥漫着泥土和野花的清香，让人心旷神怡。",
            ],
            "村庄": [
                "宁静的小村庄坐落在起伏的丘陵之间，石墙茅舍错落有致。村口的老槐树下，几位老人正在对弈，孩童们在巷弄间追逐嬉戏。炊烟从各家的烟囱中升起，空气中飘来饭菜的香味。",
                "月叶镇的街道由青石板铺成，两旁是木质结构的民居。镇子虽小，却透着一股温馨的生活气息。村民们各自忙碌着自己的事务，偶尔有人向你投来好奇的目光。",
                "阳光洒在村庄的屋顶上，鸡犬相闻，孩童的笑声在巷弄间回荡。村口的小溪潺潺流过，几只鸭子在水中悠闲地游弋。",
            ],
            "城镇": [
                "宽阔的街道两旁商铺林立，旗幡在微风中轻轻飘动。城门口人来人往，商队的马车正在卸货，吆喝声此起彼伏。远处的钟楼传来悠长的钟声，提醒着时间的流逝。",
                "穿过拥挤的人群，你来到了城镇的广场。这里商贩云集，各种口音的叫卖声不绝于耳。",
            ],
            "城堡": [
                "巍峨的城堡矗立在山崖之上，灰色的石墙在阳光下显得庄严肃穆。穿过吊桥，映入眼帘的是宽阔的庭院，侍卫们身着铠甲在各个要道站岗。",
                "沉重的铁门在身后缓缓关闭。城堡内部的走廊昏暗而狭长，只有零星的火把照亮前路。",
            ],
            "洞穴": [
                "幽暗的洞穴中只有零星的磷光照亮前路，冰冷的水珠从洞顶滴落。空气中弥漫着潮湿的霉味，隐约能听到深处传来的水流声。",
                "穿过狭窄的入口，眼前豁然开朗。一个巨大的地下溶洞展现在你面前，钟乳石从洞顶垂下，在磷光中显得格外诡异。",
            ],
        }

        default_descs = [
            "你来到了一片陌生的区域，四周静悄悄的，只有风吹过树叶的沙沙声。远处隐约可见一些建筑的轮廓。",
            "这里似乎是一个偏远的角落。地面上散落着一些奇怪的痕迹，似乎不久前有人经过。空气中弥漫着一股难以名状的气息。",
        ]

        base_descs = scene_descriptions.get(scene_type, default_descs)
        base_desc = random.choice(base_descs)

        # 应用随机开场模板（差异化增强）
        base_desc = self._apply_opening_template(scene_type, base_desc)

        # 如果有任务线索，将其自然融入场景描述
        if quest_hint:
            hint_integration_templates = {
                "酒馆": [
                    f"人群中有人低声议论着：「{quest_hint}」",
                    f"酒馆老板一边擦杯子一边随口说道：「{quest_hint}」",
                ],
                "森林": [
                    f"在林间小道上，你隐约听到有人说起：「{quest_hint}」",
                    f"一棵古老的树干上刻着模糊的字迹，似乎在暗示：{quest_hint}",
                ],
                "村庄": [
                    f"村口的公告栏上写着：「{quest_hint}」",
                    f"一位村民见你走来，好心地提醒道：「{quest_hint}」",
                ],
                "城镇": [
                    f"城门口的告示牌上写着：「{quest_hint}」",
                    f"街道上有人正在议论：「{quest_hint}」",
                ],
            }
            templates = hint_integration_templates.get(scene_type, [f"你隐约感觉到：{quest_hint}"])
            hint_integration = random.choice(templates)
            return f"{base_desc}\n\n{hint_integration}"
        else:
            return base_desc

    def get_existing_scene(self, scene_type: str, query: str = "") -> SceneMetadata | None:
        """
        查询已有场景(懒生成:优先复用)
        
        Args:
            scene_type: 场景类型
            query: 查询描述(未来可用于语义匹配)
            
        Returns:
            匹配的场景或 None
        """
        scenes = self.registry.get_by_type(scene_type)
        if not scenes:
            return None
        # TODO: 未来实现语义匹配
        return scenes[0] if scenes else None


# 全局实例
_global_agent: SceneAgent | None = None


def get_scene_agent() -> SceneAgent:
    """获取全局 SceneAgent 实例"""
    global _global_agent
    if _global_agent is None:
        _global_agent = SceneAgent()
    return _global_agent


async def init_scene_agent() -> SceneAgent:
    """初始化全局 SceneAgent"""
    agent = get_scene_agent()
    await agent.initialize()
    return agent
