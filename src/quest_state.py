"""
QuestState - 任务状态管理

《月叶镇危机》主线任务状态追踪
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class QuestStage(Enum):
    """任务阶段枚举"""
    NOT_STARTED = "not_started"
    FIND_MAYOR = "find_mayor"               # 找镇长
    TALK_TO_MAYOR = "talk_to_mayor"         # 与镇长对话
    GO_TO_TAVERN = "go_to_tavern"           # 去酒馆
    GATHER_INFO = "gather_info"             # 打听情报
    GO_TO_FOREST = "go_to_forest"           # 进入森林
    DEFEAT_MONSTER = "defeat_monster"       # 击败怪物
    RETURN_TO_MAYOR = "return_to_mayor"     # 回报镇长
    QUEST_COMPLETE = "quest_complete"       # 任务完成


class EndingType(Enum):
    """结局类型枚举"""
    HEROIC = "heroic"           # 英雄结局:正面击败怪物,镇长嘉奖
    PEACEFUL = "peaceful"       # 和平结局:未战或劝退怪物,和平解决
    TRAGIC = "tragic"           # 悲剧结局:玩家或NPC牺牲
    MYSTERIOUS = "mysterious"   # 神秘结局:发现更深层的阴谋
    COMMERCIAL = "commercial"   # 商人之道:用交易解决问题


# 任务名称
QUEST_NAME = "月叶镇危机"


@dataclass
class QuestState:
    """任务状态"""
    stage: QuestStage = QuestStage.NOT_STARTED
    quest_log: list[str] = field(default_factory=list)
    tavern_info_gathered: bool = False
    monster_hp_dealt: int = 0  # 记录对怪物造成的伤害
    completed: bool = False

    # 多结局相关追踪
    player_choices: list[dict] = field(default_factory=list)  # 玩家关键选择记录
    combat_count: int = 0  # 战斗次数
    talked_to_npcs: list[str] = field(default_factory=list)  # 对话过的NPC
    used_skills: list[str] = field(default_factory=list)  # 使用过的技能
    ending_type: EndingType | None = None  # 结局类型

    def record_choice(self, choice_type: str, choice_value: str, details: str = "") -> None:
        """
        记录玩家的关键选择

        Args:
            choice_type: 选择类型 (dialogue/combat/exploration/item/skill)
            choice_value: 选择的具体值
            details: 额外描述
        """
        self.player_choices.append({
            "type": choice_type,
            "value": choice_value,
            "details": details,
            "stage": self.stage.value,
        })

    def evaluate_ending(self) -> EndingType:
        """
        根据玩家选择链评定结局类型

        评定规则:
        - HEROIC: 正面战斗击败怪物 (>5次攻击 or monster_hp_dealt > 50)
        - PEACEFUL: 零战斗通关 or 劝退怪物 (combat_count == 0)
        - TRAGIC: 玩家HP低于20%时完成
        - MYSTERIOUS: 发现了隐藏信息 (talked_to_npcs 包含特定NPC)
        - COMMERCIAL: 用交易/金币解决问题 (choice_value 包含"买"或"交易")

        Returns:
            EndingType: 结局类型
        """
        # 商人之道：优先检测交易选择
        for choice in self.player_choices:
            if choice["type"] in ("dialogue", "item") and any(kw in str(choice["value"]) for kw in ["买", "交易", "sell", "buy", "trade", "购买"]):
                self.ending_type = EndingType.COMMERCIAL
                return self.ending_type

        # 和平结局：零战斗通关
        if self.combat_count == 0:
            self.ending_type = EndingType.PEACEFUL
            return self.ending_type

        # 悲剧结局：使用了眩晕/高伤害技能且玩家自己受伤严重
        # (通过 monster_hp_dealt 和战斗次数推算)
        if self.stage == QuestStage.QUEST_COMPLETE:
            # 英雄结局：正面战斗击败
            if self.monster_hp_dealt > 30 or self.combat_count >= 3:
                self.ending_type = EndingType.HEROIC
            else:
                # 神秘结局：快速解决，可能发现了什么
                self.ending_type = EndingType.MYSTERIOUS

        if self.ending_type is None:
            self.ending_type = EndingType.HEROIC

        return self.ending_type

    def get_ending_narrative(self, ending: EndingType) -> str:
        """根据结局类型生成叙事"""
        narratives = {
            EndingType.HEROIC: (
                "🏆 【英雄结局】\n\n"
                "你凭借勇气和实力正面击败了幽影森林的影狼,威名传遍了整个月叶镇。\n"
                "镇长亲自出迎,授予你「勇者」称号,村民们夹道欢呼。\n"
                "你成为了月叶镇的传奇英雄!"
            ),
            EndingType.PEACEFUL: (
                "🌿 【和平结局】\n\n"
                "你没有选择暴力,而是用智慧和影狼达成了和解。\n"
                "原来影狼只是守护森林的灵兽,你与它建立了奇妙的信任。\n"
                "镇长得知真相后,邀请你参加了一场盛大的庆典。\n"
                "你用和平的方式赢得了所有人的尊重!"
            ),
            EndingType.TRAGIC: (
                "💀 【悲剧结局】\n\n"
                "战斗虽然胜利了,但你付出了惨痛的代价。\n"
                "影狼倒下了,你也身负重伤,意识渐渐模糊...\n"
                "镇长为你请来了最好的医师,你的英勇事迹在月叶镇流传。\n"
                "虽然活了下来,但这片森林留下了太多的回忆..."
            ),
            EndingType.MYSTERIOUS: (
                "🔮 【神秘结局】\n\n"
                "击败影狼后,你发现它的身上有一枚奇怪的徽章--\n"
                "那是某个神秘组织的标志。影狼之死,似乎只是更大阴谋的冰山一角...\n"
                "镇长看那枚徽章时,脸色突变,欲言又止。\n"
                "月叶镇的故事,远未结束..."
            ),
            EndingType.COMMERCIAL: (
                "💰 【商人之道结局】\n\n"
                "你没有选择战斗,而是用金币解决了问题。\n"
                "从商人那里购得的稀有物品,意外地让影狼平静了下来。\n"
                "原来这头影狼曾受过伤,那物品的气味让它回忆起了什么。\n"
                "你用交易的艺术,书写了属于自己的传奇!"
            ),
        }
        return narratives.get(ending, narratives[EndingType.HEROIC])

    def get_player_profile(self) -> dict:
        """获取玩家画像摘要(用于NPC对话调整)"""
        # 统计选择类型分布
        choice_types = {}
        for choice in self.player_choices:
            ct = choice["type"]
            choice_types[ct] = choice_types.get(ct, 0) + 1

        # 战斗风格
        combat_ratio = choice_types.get("combat", 0) / max(len(self.player_choices), 1)
        diplomatic_ratio = choice_types.get("dialogue", 0) / max(len(self.player_choices), 1)

        if combat_ratio > 0.6:
            combat_style = "好战型"
        elif diplomatic_ratio > 0.5:
            combat_style = "外交型"
        else:
            combat_style = "均衡型"

        return {
            "total_choices": len(self.player_choices),
            "combat_count": self.combat_count,
            "npc_interactions": len(self.talked_to_npcs),
            "combat_style": combat_style,
            "choice_breakdown": choice_types,
        }

    def advance_to(self, new_stage: QuestStage) -> None:
        """推进任务阶段"""
        self.stage = new_stage
        self.quest_log.append(f"[{new_stage.value}]")
        if new_stage == QuestStage.QUEST_COMPLETE:
            self.completed = True

    def is_active(self) -> bool:
        """任务是否处于活跃状态"""
        return self.stage not in (QuestStage.NOT_STARTED, QuestStage.QUEST_COMPLETE)

    def get_stage_hint(self, current_location: str = "") -> str:
        """
        获取当前阶段的叙事提示

        Args:
            current_location: 玩家当前所在地点（场景类型，如"酒馆"、"森林"等）
                              用于判断玩家是否已处于提示指向的地点，从而切换到动作提示
        """
        # 地点触发映射：阶段 -> (在正确地点时的提示, 前往该地点时的提示)
        hints = {
            QuestStage.FIND_MAYOR: (
                "镇中心似乎有人聚集,过去看看?",
                "镇中心似乎有人聚集,过去看看?",
            ),
            QuestStage.TALK_TO_MAYOR: (
                "镇长正焦急地在广场中央等待,他似乎有话要对你说。",
                "镇长正焦急地在广场中央等待,他似乎有话要对你说。",
            ),
            QuestStage.GO_TO_TAVERN: (
                "月光酒馆就在街道尽头,温暖的灯光从窗户透出,里面传来热闹的人声。",
                "月光酒馆就在街道尽头,温暖的灯光从窗户透出,里面传来热闹的人声。",
            ),
            QuestStage.GATHER_INFO: (
                # 玩家已在酒馆：提示下一步动作，而非重复指向酒馆
                "酒馆里人声鼎沸,是时候向酒客打听森林的情报了。",
                "月光酒馆就在街道尽头,温暖的灯光从窗户透出,里面传来热闹的人声。",
            ),
            QuestStage.GO_TO_FOREST: (
                "幽影森林就在镇子北边入口,入口处弥漫着淡淡的雾气...",
                "幽影森林就在镇子北边入口,入口处弥漫着淡淡的雾气...",
            ),
            QuestStage.DEFEAT_MONSTER: (
                # 玩家已在森林：提示战斗准备，而非重复描述森林
                "幽影森林中,影狼就在前方!准备好你的武器!",
                "幽影森林就在镇子北边入口,入口处弥漫着淡淡的雾气...",
            ),
            QuestStage.RETURN_TO_MAYOR: (
                "影狼已被击败,是时候回去向镇长报告好消息了!",
                "影狼已被击败,是时候回去向镇长报告好消息了!",
            ),
            QuestStage.QUEST_COMPLETE: (
                "任务完成!镇长对你的英勇表示赞赏。",
                "任务完成!镇长对你的英勇表示赞赏。",
            ),
            QuestStage.NOT_STARTED: ("", ""),
        }

        hint_pair = hints.get(self.stage, ("", ""))
        if len(hint_pair) != 2:
            return hint_pair[0] if hint_pair else ""

        at_location_hint, go_to_hint = hint_pair

        # 检查玩家当前是否已处于该阶段的触发地点
        if current_location and self.check_location_trigger(current_location):
            return at_location_hint

        return go_to_hint

    def get_location_trigger(self) -> dict:
        """获取地点触发信息"""
        triggers = {
            QuestStage.TALK_TO_MAYOR: ["月叶镇广场", "月叶镇", "广场"],
            QuestStage.GO_TO_TAVERN: ["月光酒馆", "酒馆"],
            QuestStage.GATHER_INFO: ["月光酒馆", "酒馆"],
            QuestStage.GO_TO_FOREST: ["幽影森林", "森林"],
            QuestStage.RETURN_TO_MAYOR: ["月叶镇广场", "月叶镇", "广场"],
        }
        return triggers.get(self.stage, {})

    def check_location_trigger(self, location: str) -> bool:
        """检查是否到达了触发地点"""
        triggers = self.get_location_trigger()
        if not triggers:
            return False
        location_lower = location.lower()
        return any(trigger.lower() in location_lower or location_lower in trigger.lower()
                   for trigger in triggers)

    def get_monster_name(self) -> str:
        """获取当前/目标怪物名称"""
        return "影狼"

    def get_quest_info(self) -> dict:
        """获取任务信息摘要"""
        return {
            "name": QUEST_NAME,
            "stage": self.stage.value,
            "stage_display": self._stage_to_display(),
            "hint": self.get_stage_hint(),
            "completed": self.completed,
            "is_active": self.is_active(),
        }

    def _stage_to_display(self) -> str:
        """阶段中文显示"""
        names = {
            QuestStage.NOT_STARTED: "未开始",
            QuestStage.FIND_MAYOR: "寻找镇长",
            QuestStage.TALK_TO_MAYOR: "与镇长对话",
            QuestStage.GO_TO_TAVERN: "前往酒馆",
            QuestStage.GATHER_INFO: "打听情报",
            QuestStage.GO_TO_FOREST: "进入森林",
            QuestStage.DEFEAT_MONSTER: "击败影狼",
            QuestStage.RETURN_TO_MAYOR: "回报镇长",
            QuestStage.QUEST_COMPLETE: "任务完成",
        }
        return names.get(self.stage, "未知")
