# -*- coding: utf-8 -*-
"""
AI DM RPG - 交互式入口 (Interactive Master)

职责：
1. 提供命令行主循环，等待玩家输入指令
2. 解析并分发指令到对应模块
3. 支持：开始游戏、创建角色、查看状态、继续游戏、帮助、退出
4. 对接 CharacterCreator、GameMaster、SaveManager

编码：UTF-8
"""

from __future__ import annotations

import asyncio
import logging
import sys
import os

# Windows PowerShell 环境 UTF-8 输出修复
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass  # 已在不支持 reconfigure 的旧版 Python 上忽略

# 确保 src 模块可导入（兼容不同运行目录）
_sys_path = os.path.dirname(os.path.abspath(__file__))
if _sys_path not in sys.path:
    sys.path.insert(0, _sys_path)

from src import (
    CharacterCreator,
    Character,
    GameMaster,
    init_game_master,
    get_save_manager,
    RACES,
    CLASSES,
    AUTO_SAVE_SLOT,
)
from src.character_creator import RaceDefinition, ClassDefinition

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


# =============================================================================
# 命令提示符
# =============================================================================

WELCOME_BANNER = r"""
╔══════════════════════════════════════════════════════════════╗
║                                                              ║
║          ⚔️  AI DM RPG - 交互式冒险入口  ⚔️                  ║
║                                                              ║
║              你的故事，由你书写                                ║
║                                                              ║
╚══════════════════════════════════════════════════════════════╝
"""

HELP_TEXT = r"""
╔══════════════════════════════════════════════════════════════╗
║                        📖 可用指令                            ║
╠══════════════════════════════════════════════════════════════╣
║  new / 开始游戏    - 创建新角色，开始全新冒险                 ║
║  continue / 继续   - 继续上一次的冒险（自动存档）             ║
║  status / 状态     - 查看当前角色状态                         ║
║  save / 保存       - 保存当前游戏到指定槽位                   ║
║  load / 读取       - 从存档槽位读取游戏                       ║
║  help / 帮助       - 显示此帮助信息                          ║
║  quit / 退出       - 退出游戏                                 ║
╚══════════════════════════════════════════════════════════════╝
"""

STATUS_TEMPLATE = r"""
╔══════════════════════════════════════════════════════════════╗
║                      📊 角色状态                              ║
╠══════════════════════════════════════════════════════════════╣
║  名字：{name}          种族：{race}  职业：{char_class}           ║
║  等级：LV.{level}      经验：{xp}/{xp_needed}                 ║
╠══════════════════════════════════════════════════════════════╣
║  ❤️  生命：{current_hp}/{max_hp}                                ║
║  🛡️  护甲：{ac}                                              ║
║  ⚔️  攻击加成：+{attack_bonus}                                  ║
║  💰  金币：{gold}                                               ║
╠══════════════════════════════════════════════════════════════╣
║  📦 属性：                                                    ║
║     力{str}  敏{dex}  体质{con}  智力{int}  感知{wis}  魅力{cha}        ║
╠══════════════════════════════════════════════════════════════╣
║  🌟 特殊能力：{special_ability}                         ║
║  🎯 主技能：{primary_skill}                                    ║
║     {skill_description}                                       ║
╚══════════════════════════════════════════════════════════════╝
"""

MAIN_PROMPT = "\n📜 > "


# =============================================================================
# 交互式角色创建流程
# =============================================================================

def _print_centered_border(width: int = 66, char: str = "═") -> None:
    print(char * width)


def _print_header(title: str, width: int = 66) -> None:
    padding = max(0, width - len(title) - 4)
    left_pad = padding // 2
    right_pad = padding - left_pad
    print(f"║{' ' * left_pad}{title}{' ' * right_pad}║")


class InteractiveCharacterCreator:
    """交互式角色创建引导"""

    def __init__(self):
        self.creator = CharacterCreator()

    def run(self) -> Character | None:
        """运行完整的角色创建流程"""
        print("\n" + "⚔️  角色创建  ⚔️".center(66))
        _print_centered_border()

        # ---- 步骤1：输入名字 ----
        name = self._ask_name()
        if name is None:
            return None

        # ---- 步骤2：选择种族 ----
        race_id = self._ask_race()
        if race_id is None:
            return None

        # ---- 步骤3：选择职业 ----
        class_id = self._ask_class()
        if class_id is None:
            return None

        # ---- 步骤4：确认 ----
        race_def: RaceDefinition = RACES[race_id]
        class_def: ClassDefinition = CLASSES[class_id]

        print(f"\n📋 请确认你的角色：")
        _print_centered_border()
        print(f"║  名字：{name}")
        print(f"║  种族：{race_def.name}  |  职业：{class_def.name}")
        _print_centered_border()

        confirm = input("✅ 确认创建？（输入 yes 确认，其他键取消）：").strip().lower()
        if confirm != "yes":
            print("❌ 角色创建已取消。")
            return None

        # ---- 创建角色 ----
        character = self.creator.create_from_selection(
            name=name,
            race_id=race_id,
            class_id=class_id,
        )
        print(f"\n🎉 角色「{name}」创建成功！")
        return character

    def _ask_name(self) -> str | None:
        while True:
            print()
            name = input("📛 请为你的冒险者取一个名字：").strip()
            if not name:
                print("⚠️  名字不能为空，请重新输入。")
                continue
            if len(name) > 20:
                print("⚠️  名字太长，请控制在20个字符以内。")
                continue
            return name

    def _ask_race(self) -> str | None:
        print(CharacterCreator.RACE_MENU)
        race_map = {
            "1": "human",
            "2": "elf",
            "3": "dwarf",
            "4": "orc",
        }
        while True:
            choice = input("\n🔹 请选择种族（输入数字 1-4，或 q 取消）：").strip()
            if choice.lower() == "q":
                return None
            race_id = race_map.get(choice)
            if race_id is None:
                print("⚠️  无效选择，请输入 1 到 4 之间的数字。")
                continue
            return race_id

    def _ask_class(self) -> str | None:
        print(CharacterCreator.CLASS_MENU)
        class_map = {
            "1": "warrior",
            "2": "ranger",
            "3": "mage",
            "4": "rogue",
        }
        while True:
            choice = input("\n🔹 请选择职业（输入数字 1-4，或 q 取消）：").strip()
            if choice.lower() == "q":
                return None
            class_id = class_map.get(choice)
            if class_id is None:
                print("⚠️  无效选择，请输入 1 到 4 之间的数字。")
                continue
            return class_id


# =============================================================================
# 交互式状态查看
# =============================================================================

def show_character_status(character: Character) -> None:
    """格式化展示角色状态"""
    attrs = character.attributes
    # 计算升级所需经验（简单公式：level * 100）
    xp_needed = character.level * 100

    print(STATUS_TEMPLATE.format(
        name=character.name,
        race=character.race_name,
        char_class=character.class_name,
        level=character.level,
        xp=character.xp,
        xp_needed=xp_needed,
        current_hp=character.current_hp,
        max_hp=character.max_hp,
        ac=character.armor_class,
        attack_bonus=character.attack_bonus,
        gold=character.gold,
        str=attrs.get("str", 0),
        dex=attrs.get("dex", 0),
        con=attrs.get("con", 0),
        int=attrs.get("int", 0),
        wis=attrs.get("wis", 0),
        cha=attrs.get("cha", 0),
        special_ability=character.special_ability or "无",
        primary_skill=character.primary_skill or "无",
        skill_description=character.skill_description or "-",
    ))


def show_inventory(character: Character) -> None:
    """展示背包物品"""
    inv = character.inventory
    if not inv:
        print("\n📦 背包是空的。")
        return
    print("\n📦 背包物品：")
    for item in inv:
        qty = item.get("quantity", 1)
        print(f"   • {item.get('name', item.get('id', '未知物品'))} x{qty}")
    print(f"\n💰 金币：{character.gold}")


# =============================================================================
# 主交互循环（探索/对话模式）
# =============================================================================

async def run_game_loop(gm: GameMaster, character: Character) -> None:
    """
    探索/对话模式的主输入循环。
    将玩家输入发送给 GameMaster，并输出叙事结果。
    """
    # 初始化游戏状态
    gm.game_state["player_stats"] = character.to_player_stats()

    # 初始叙事：酒馆开场
    print("\n🌟 正在生成初始场景……\n")
    initial_narrative = (
        "你睁开眼睛，发现自己正坐在「醉梦酒馆」的一张木桌旁。"
        "窗外是黄昏的余晖，空气中弥漫着麦酒和烤肉的气息。"
        "酒馆里人声鼎沸，角落里有几个冒险者在低声交谈。"
        "你握紧腰间的武器，决定先四处看看，了解一下情况。"
    )
    print(f"📜 {initial_narrative}\n")

    while True:
        try:
            raw = input(MAIN_PROMPT).strip()
        except (EOFError, KeyboardInterrupt):
            print("\n\n👋 检测到退出信号，正在保存……")
            await _auto_save(gm, character)
            break

        if not raw:
            continue

        cmd = raw.lower()

        # ---- 内置指令（不在游戏主循环中处理）----
        if cmd in ("quit", "q", "exit"):
            print("\n👋 正在保存并退出……")
            await _auto_save(gm, character)
            break

        if cmd in ("status", "st", "状态"):
            show_character_status(character)
            show_inventory(character)
            continue

        if cmd in ("help", "h", "帮助"):
            print(HELP_TEXT)
            continue

        if cmd in ("save", "s", "保存"):
            await _do_save(gm, character)
            continue

        if cmd in ("load", "l", "读取"):
            loaded_char = await _do_load(gm)
            if loaded_char is not None:
                character = loaded_char
                gm.game_state["player_stats"] = character.to_player_stats()
            continue

        # ---- 游戏主输入 ----
        print(f"\n🎲 正在处理：{raw}\n")
        try:
            result = await gm.handle_player_input(raw)
            narrative = result.get("narrative", "")
            if narrative:
                print(f"📜 {narrative}\n")
            else:
                print("📜 （暂无叙事输出）\n")
        except Exception as e:
            logger.exception("处理玩家输入时出错")
            print(f"\n❌ 处理输入时出错：{e}\n")


async def _auto_save(gm: GameMaster, character: Character) -> None:
    """自动保存到 AUTO_SAVE_SLOT"""
    try:
        save_mgr = get_save_manager()
        save_data = {
            "character": character.to_dict(),
            "game_state": gm.game_state,
            "mode": gm.mode,
        }
        await save_mgr.save(AUTO_SAVE_SLOT, save_data)
        print(f"💾 已自动保存到槽位 {AUTO_SAVE_SLOT}。")
    except Exception as e:
        logger.warning(f"自动保存失败：{e}")


async def _do_save(gm: GameMaster, character: Character) -> None:
    """交互式保存"""
    save_mgr = get_save_manager()
    try:
        slot = input(f"📂 请输入存档槽位（1-{save_mgr.max_slots}），默认{AUTO_SAVE_SLOT}：").strip()
        slot = int(slot) if slot else AUTO_SAVE_SLOT
    except ValueError:
        slot = AUTO_SAVE_SLOT

    try:
        save_data = {
            "character": character.to_dict(),
            "game_state": gm.game_state,
            "mode": gm.mode,
        }
        await save_mgr.save(slot, save_data)
        print(f"💾 已保存到槽位 {slot}。")
    except Exception as e:
        print(f"❌ 保存失败：{e}")


async def _do_load(gm: GameMaster) -> Character | None:
    """交互式读取"""
    save_mgr = get_save_manager()
    try:
        slot_str = input(f"📂 请输入要读取的存档槽位（1-{save_mgr.max_slots}）：").strip()
        slot = int(slot_str) if slot_str else None
    except ValueError:
        slot = None

    if slot is None:
        print("⚠️  无效槽位。")
        return None

    try:
        data = await save_mgr.load(slot)
        if data is None:
            print("⚠️  该槽位没有存档。")
            return None
        character = Character.from_dict(data["character"])
        gm.game_state = data.get("game_state", gm.game_state)
        gm.mode = data.get("mode", gm.mode)
        print(f"✅ 已从槽位 {slot} 读取存档！")
        return character
    except Exception as e:
        print(f"❌ 读取失败：{e}")
        return None


# =============================================================================
# 主入口
# =============================================================================

async def async_main() -> None:
    """异步主流程"""
    print(WELCOME_BANNER)
    print(HELP_TEXT)

    # 全局角色实例（跨状态使用）
    character: Character | None = None
    gm: GameMaster | None = None

    while True:
        cmd = input(MAIN_PROMPT).strip().lower()

        # ---- 开始新游戏 ----
        if cmd in ("new", "开始游戏"):
            print("\n🔄 开始新游戏……")
            creator = InteractiveCharacterCreator()
            character = creator.run()
            if character is None:
                print("⚠️  角色创建未完成，请重新选择操作。\n")
                continue

            # 初始化 GameMaster
            gm = await init_game_master()
            gm.game_state["player_stats"] = character.to_player_stats()
            print(f"\n🎮 游戏开始！「{character.name}」的冒险即将展开……\n")
            await run_game_loop(gm, character)
            continue

        # ---- 继续游戏 ----
        if cmd in ("continue", "继续", "c"):
            print("\n🔄 正在加载存档……")
            save_mgr = get_save_manager()
            try:
                data = await save_mgr.load(AUTO_SAVE_SLOT)
            except Exception:
                data = None

            if data is None:
                print("⚠️  没有找到自动存档，请先「开始游戏」。\n")
                continue

            try:
                character = Character.from_dict(data["character"])
                gm = await init_game_master()
                gm.game_state = data.get("game_state", gm.game_state)
                gm.mode = data.get("mode", gm.mode)
            except Exception as e:
                print(f"❌ 读取存档失败：{e}\n")
                continue

            print(f"\n✅ 存档加载成功！欢迎回来，「{character.name}」！\n")
            await run_game_loop(gm, character)
            continue

        # ---- 查看状态 ----
        if cmd in ("status", "st", "状态"):
            if character is None:
                print("⚠️  还没有创建角色，请先「开始游戏」。\n")
            else:
                show_character_status(character)
                show_inventory(character)
            continue

        # ---- 保存 ----
        if cmd in ("save", "s", "保存"):
            if gm is None or character is None:
                print("⚠️  没有正在进行的游戏，无法保存。\n")
            else:
                await _do_save(gm, character)
            continue

        # ---- 读取 ----
        if cmd in ("load", "l", "读取"):
            if gm is None:
                print("⚠️  没有正在进行的游戏，请先「开始游戏」。\n")
            else:
                loaded_char = await _do_load(gm)
                if loaded_char is not None:
                    character = loaded_char
                    gm.game_state["player_stats"] = character.to_player_stats()
            continue

        # ---- 帮助 ----
        if cmd in ("help", "h", "帮助"):
            print(HELP_TEXT)
            continue

        # ---- 退出 ----
        if cmd in ("quit", "q", "exit", "退出"):
            print("\n👋 感谢游玩 AI DM RPG！下次见，冒险者！\n")
            break

        # ---- 无效指令 ----
        print(f"⚠️  未知指令：{cmd}，输入「help」查看可用命令。\n")


def main() -> None:
    """同步入口"""
    try:
        asyncio.run(async_main())
    except KeyboardInterrupt:
        print("\n\n👋 强制退出。再见！\n")
        sys.exit(0)


if __name__ == "__main__":
    main()
