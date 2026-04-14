"""
TutorialSystem - 新手冒险引导系统

职责：
1. 向新玩家介绍世界观和基本操作
2. 提供新手指南场景（新手村）
3. 引导玩家完成第一个任务
4. 管理教程状态，确保只在新游戏时触发
"""

import asyncio
from enum import Enum
from typing import Any

from .minimax_interface import MiniMaxInterface, get_minimax_interface


class TutorialState(Enum):
    """教程状态"""
    NOT_STARTED = "not_started"
    WELCOME = "welcome"
    WORLD_INTRO = "world_intro"
    COMMANDS = "commands"
    FIRST_SCENE = "first_scene"
    FIRST_TASK = "first_task"
    COMPLETED = "completed"


class TutorialMode(Enum):
    """新手引导模式"""
    FULL = "full"    # 完整教程
    QUICK = "quick"  # 快速入门
    SKIP = "skip"    # 跳过


# 世界观设定
WORLD_INTRO = """
═══════════════════════════════════════════════════════════════
🌍 艾瑟拉大陆 - 世界观简介
═══════════════════════════════════════════════════════════════

【地理】
你所在的土地叫做艾瑟拉大陆——一个由人类、精灵、矮人、兽人等种族共同生活的世界。
王国之间时有冲突，荒野之中怪物横行，但冒险者们从未停止探索的脚步。

【月叶镇】
你目前身处月叶镇——边境地带的一个宁静小镇，
位于人类王国「银翼王国」与精灵领地「翡翠森林」的交界处。
这里曾是商旅往来的要道，如今却因附近的怪物活动而日渐萧条。

【冒险者公会】
镇上的冒险者公会是冒险者们接取任务、组队合作的场所。
从送信到讨伐怪物，公会任务五花八门，报酬丰厚。
据说最近镇子附近出现了异常强大的怪物，许多老练的冒险者都铩羽而归……

【四大种族】
  🧑 人类 - 适应性强，善于交际，是大陆上数量最多的种族
  🧝 精灵 - 优雅长寿，与魔法和自然有着深厚联系
  🪓 矮人 - 坚韧顽强，擅长锻造和矿业
  👹 兽人 - 强壮凶猛，拥有惊人的战斗天赋

【职业道路】
  ⚔️ 战士 - 战场主力，武器与防具大师
  🏹 游侠 - 荒野生存专家，弓箭手
  🔮 法师 - 操控魔法的智者
  🗡️ 盗贼 - 潜行与偷袭的大师

═══════════════════════════════════════════════════════════════
"""


# 基本操作说明
COMMANDS_INTRO = """
═══════════════════════════════════════════════════════════════
📖 基本操作说明
═══════════════════════════════════════════════════════════════

【探索场景】
  「我去酒馆」「探索森林」「进入城堡」
  → 描述你想去的地方，DM会为你生成场景

【与NPC对话】
  「我和老板说话」「询问酒馆老板关于任务的事」
  → 告诉DM你想和谁交谈

【战斗】
  「攻击哥布林」「我使用火球术」「防御」
  → 直接描述你的战斗动作

【使用物品】
  「使用治疗药水」「我吃药」
  → 使用背包中的物品

【查看状态】
  输入「status」查看当前状态

【系统命令】
  /save [槽位]  - 保存游戏（1-4槽位）
  /load [槽位]  - 加载存档
  /saves        - 查看所有存档
  /new          - 开始新游戏
  help          - 显示帮助信息

═══════════════════════════════════════════════════════════════
"""


# 新手任务
FIRST_TASK_INTRO = """
═══════════════════════════════════════════════════════════════
🎯 新手任务：酒馆探秘
═══════════════════════════════════════════════════════════════

老板娘提到的「新鲜消息」，听起来很有趣……
据说镇上的「醉梦酒馆」是冒险者们交换情报的地方。
也许那里能找到关于最近怪物活动的线索。

【任务目标】
  前往镇上的酒馆（醉梦酒馆），打听最近的消息
  你可以尝试：
  · 「我去酒馆」
  · 「前往醉梦酒馆」
  · 「走进镇上的酒馆」

═══════════════════════════════════════════════════════════════
"""


class TutorialSystem:
    """
    新手引导系统

    管理教程流程：
    1. 欢迎界面（角色介绍）
    2. 世界观简介
    3. 基本操作说明
    4. 第一个场景介绍
    5. 新手任务引导
    """

    def __init__(self):
        self.state = TutorialState.NOT_STARTED
        self.mode = TutorialMode.FULL  # 默认完整教程
        self.llm: MiniMaxInterface | None = None
        self._llm_initialized = False

    def set_mode(self, mode: TutorialMode) -> None:
        """设置新手引导模式"""
        self.mode = mode

    def get_mode(self) -> TutorialMode:
        """获取当前新手引导模式"""
        return self.mode

    def _init_llm(self):
        """延迟初始化 LLM"""
        if not self._llm_initialized:
            try:
                self.llm = get_minimax_interface()
                self._llm_initialized = True
            except Exception:
                self.llm = None
                self._llm_initialized = True

    def start_tutorial(self, character_name: str) -> str:
        """
        开始教程流程第一步（欢迎界面）

        Args:
            character_name: 角色名

        Returns:
            欢迎叙事文本
        """
        self.state = TutorialState.WELCOME
        return self._build_welcome(character_name)

    def _build_welcome(self, name: str) -> str:
        """构建欢迎叙事"""
        return f"""
═══════════════════════════════════════════════════════════════
📖 序章 - 新的冒险者
═══════════════════════════════════════════════════════════════

{name}，欢迎来到艾瑟拉大陆！

当你睁开眼睛，陌生的木质天花板映入眼帘。
阳光透过窗帘的缝隙洒入房间，空气中弥漫着淡淡的麦香和远处酒馆的喧嚣声。

这里是月叶镇——边境地带的一个宁静小镇，
位于银翼王国与翡翠森林的交界处。
你只记得自己收到了一封信，信中提到这里有重要的冒险机会……

「嘿，冒险者！」客栈老板娘的声音从楼下传来，
「有封信放在柜台上，像是给你的。还有——今晚酒馆有新鲜消息，去听听吧！」

═══════════════════════════════════════════════════════════════
"""

    def get_world_intro(self) -> str:
        """
        获取世界观简介

        Returns:
            世界观叙事文本
        """
        if self.state == TutorialState.WELCOME:
            self.state = TutorialState.WORLD_INTRO
        return WORLD_INTRO

    def get_commands_intro(self) -> str:
        """
        获取基本操作说明

        Returns:
            操作说明文本
        """
        if self.state == TutorialState.WORLD_INTRO:
            self.state = TutorialState.COMMANDS
        return COMMANDS_INTRO

    def get_first_scene_intro(self) -> str:
        """
        获取第一个场景介绍

        Returns:
            第一场景叙事文本
        """
        if self.state in (TutorialState.WELCOME, TutorialState.WORLD_INTRO, TutorialState.COMMANDS):
            self.state = TutorialState.FIRST_SCENE
        return self._build_first_scene_intro()

    def _build_first_scene_intro(self) -> str:
        """构建第一个场景介绍"""
        return f"""
═══════════════════════════════════════════════════════════════
🌅 月叶镇 - 清晨
═══════════════════════════════════════════════════════════════

你推开客栈的窗户，清晨的阳光洒在脸上。

窗外是月叶镇的主街——鹅卵石铺就的路面，两旁是错落有致的木质建筑。
远处的醉梦酒馆招牌在晨风中轻轻摇晃。
镇上的居民开始了一天的劳作，炊烟从各处升起。

街上偶尔有冒险者打扮的人匆匆走过，似乎在赶往什么地方。
最近镇子附近确实不太平……

═══════════════════════════════════════════════════════════════
"""

    def get_first_task(self) -> str:
        """
        获取新手任务引导

        Returns:
            任务叙事文本
        """
        if self.state in (
            TutorialState.WELCOME,
            TutorialState.WORLD_INTRO,
            TutorialState.COMMANDS,
            TutorialState.FIRST_SCENE,
        ):
            self.state = TutorialState.FIRST_TASK
        return FIRST_TASK_INTRO

    async def generate_welcome_narrative(self, character_data: dict[str, Any]) -> str:
        """
        使用 LLM 生成沉浸式欢迎叙事

        Args:
            character_data: 角色数据

        Returns:
            沉浸式欢迎叙事
        """
        self._init_llm()

        name = character_data.get("name", "冒险者")
        race = character_data.get("race_name", "人类")
        class_name = character_data.get("class_name", "战士")
        special_ability = character_data.get("special_ability", "")

        if self.llm and self._llm_initialized:
            system = """你是一个沉浸式TRPG叙事专家。你为AI DM RPG生成新游戏开始时的欢迎叙事。

写作要求：
- 第二人称视角
- 描写角色醒来的场景，融合角色背景
- 客栈氛围描写（声音、气味、温度）
- 暗示即将到来的冒险
- 200-300字
- 中文输出
- 文学性强，有画面感"""
            
            prompt = f"""为以下角色生成一段欢迎叙事（游戏开场）：

角色信息：
- 名字：{name}
- 种族：{race}
- 职业：{class_name}
- 特殊能力：{special_ability}

场景设定：
- 地点：月叶镇客栈（清晨）
- 环境：阳光透过窗帘，远处有酒馆喧嚣声
- 引导事件：老板娘喊话，有信，有消息

请生成一段沉浸式的开场叙事，描写{name}醒来的情景和氛围。"""

            try:
                narrative = await self.llm.generate(prompt, system=system, temperature=0.8)
                if narrative and len(narrative) > 50:
                    return self._wrap_welcome(narrative, name)
            except Exception:
                pass

        # Fallback
        return self._build_welcome(name)

    def _wrap_welcome(self, narrative: str, name: str) -> str:
        """包装欢迎叙事"""
        header = f"""
═══════════════════════════════════════════════════════════════
📖 序章 - 新的冒险者：{name}
═══════════════════════════════════════════════════════════════

"""
        footer = f"""
═══════════════════════════════════════════════════════════════
🎯 当前目标：前往镇上的酒馆，打听最近的消息
   提示：输入「我去酒馆」开始探索
═══════════════════════════════════════════════════════════════
"""
        return header + narrative.strip() + footer

    def complete_tutorial(self) -> None:
        """标记教程完成"""
        self.state = TutorialState.COMPLETED

    def is_completed(self) -> bool:
        """检查教程是否已完成"""
        return self.state == TutorialState.COMPLETED

    def get_state(self) -> TutorialState:
        """获取当前教程状态"""
        return self.state

    def reset(self) -> None:
        """重置教程状态"""
        self.state = TutorialState.NOT_STARTED


# =============================================================================
# 全局实例
# =============================================================================

_global_tutorial: TutorialSystem | None = None


def get_tutorial_system() -> TutorialSystem:
    """获取全局 TutorialSystem 实例"""
    global _global_tutorial
    if _global_tutorial is None:
        _global_tutorial = TutorialSystem()
    return _global_tutorial
