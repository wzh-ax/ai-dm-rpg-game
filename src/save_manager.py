"""
SaveManager - 存档管理系统

职责：
1. 管理玩家状态的 JSON 文件持久化
2. 支持多存档槽位（默认 5 个槽位）
3. 自动创建存档目录
4. 存档版本兼容性
"""

import json
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# 存档目录
SAVE_DIR = Path(__file__).parent.parent / "saves"
SAVE_VERSION = "1.0"
AUTO_SAVE_SLOT = 0  # 自动存档槽位
MAX_SLOTS = 5


class SaveManager:
    """
    存档管理器
    
    支持：
    - 手动存档/读档
    - 自动存档（战斗胜利后触发）
    - 多存档槽位
    """

    def __init__(self, save_dir: Path | None = None):
        self.save_dir = save_dir or SAVE_DIR
        self._ensure_save_dir()

    def _ensure_save_dir(self) -> None:
        """确保存档目录存在"""
        self.save_dir.mkdir(parents=True, exist_ok=True)

    def get_save_path(self, slot_id: int) -> Path:
        """
        获取存档文件路径
        
        Args:
            slot_id: 存档槽位 ID (0 = 自动存档, 1-4 = 手动存档)
            
        Returns:
            存档文件 Path 对象
        """
        return self.save_dir / f"save_{slot_id}.json"

    def _create_save_data(self, game_state: dict, slot_id: int) -> dict[str, Any]:
        """
        创建存档数据结构
        
        Args:
            game_state: 游戏状态字典
            slot_id: 存档槽位 ID
            
        Returns:
            格式化后的存档数据
        """
        return {
            "version": SAVE_VERSION,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "slot_id": slot_id,
            "slot_type": "auto" if slot_id == AUTO_SAVE_SLOT else "manual",
            "player_stats": game_state.get("player_stats", {}),
            "inventory": game_state.get("player_stats", {}).get("inventory", []),
            "location": game_state.get("location", "未知"),
            "turn": game_state.get("turn", 0),
            "mode": game_state.get("mode", "exploration"),
            "active_npcs": game_state.get("active_npcs", {}),
            "active_npcs_per_scene": game_state.get("active_npcs_per_scene", {}),
            "game_progress": {
                "level": game_state.get("player_stats", {}).get("level", 1),
                "xp": game_state.get("player_stats", {}).get("xp", 0),
                "gold": game_state.get("player_stats", {}).get("gold", 0),
            },
            "combat_state": None,  # 战斗状态不持久化，重新开始时为空
        }

    def save_game(self, game_state: dict, slot_id: int) -> bool:
        """
        保存游戏到指定槽位
        
        Args:
            game_state: 游戏状态字典
            slot_id: 存档槽位 ID
            
        Returns:
            是否保存成功
        """
        try:
            save_path = self.get_save_path(slot_id)
            save_data = self._create_save_data(game_state, slot_id)
            
            # 原子写入：先写临时文件，再重命名
            temp_path = save_path.with_suffix(".tmp")
            with open(temp_path, "w", encoding="utf-8") as f:
                json.dump(save_data, f, ensure_ascii=False, indent=2)
            
            temp_path.replace(save_path)
            
            logger.info(f"Game saved to slot {slot_id}: {save_path}")
            return True
        except Exception as e:
            logger.error(f"Failed to save game to slot {slot_id}: {e}")
            return False

    def load_game(self, slot_id: int) -> dict[str, Any] | None:
        """
        从指定槽位加载游戏
        
        Args:
            slot_id: 存档槽位 ID
            
        Returns:
            游戏状态字典，失败返回 None
        """
        try:
            save_path = self.get_save_path(slot_id)
            if not save_path.exists():
                logger.warning(f"Save file not found: {save_path}")
                return None
            
            with open(save_path, "r", encoding="utf-8") as f:
                save_data = json.load(f)
            
            # 版本兼容性检查
            version = save_data.get("version", "0.0")
            if not self._check_version_compatible(version):
                logger.warning(f"Save version {version} may not be compatible with {SAVE_VERSION}")
            
            # 重建 game_state 结构
            game_state = self._reconstruct_game_state(save_data)
            
            logger.info(f"Game loaded from slot {slot_id}: {save_path}")
            return game_state
        except Exception as e:
            logger.error(f"Failed to load game from slot {slot_id}: {e}")
            return None

    def _reconstruct_game_state(self, save_data: dict) -> dict[str, Any]:
        """
        从存档数据重建 game_state 结构
        
        Args:
            save_data: 存档数据字典
            
        Returns:
            符合 GameMaster 预期的 game_state 字典
        """
        player_stats = save_data.get("player_stats", {})
        
        game_state = {
            "turn": save_data.get("turn", 0),
            "location": save_data.get("location", "未知"),
            "mode": save_data.get("mode", "exploration"),
            "active_npcs": save_data.get("active_npcs", {}),  # Restore active NPCs
            "active_npcs_per_scene": save_data.get("active_npcs_per_scene", {}),  # Restore per-scene NPCs
            "player_stats": {
                "hp": player_stats.get("hp", 30),
                "max_hp": player_stats.get("max_hp", 30),
                "ac": player_stats.get("ac", 12),
                "xp": player_stats.get("xp", 0),
                "level": player_stats.get("level", 1),
                "gold": player_stats.get("gold", 0),
                "inventory": player_stats.get("inventory", []),
            },
        }
        return game_state

    def _check_version_compatible(self, version: str) -> bool:
        """
        检查存档版本是否兼容
        
        Args:
            version: 存档版本号
            
        Returns:
            是否兼容
        """
        # 当前版本 1.0，只支持 1.x
        try:
            major = int(version.split(".")[0])
            return major == 1
        except (ValueError, IndexError):
            return False

    def list_saves(self) -> list[dict[str, Any]]:
        """
        列出所有存档槽位的信息
        
        Returns:
            存档信息列表，包含 slot_id, timestamp, version, location, level, turn
        """
        saves = []
        for slot_id in range(MAX_SLOTS):
            save_path = self.get_save_path(slot_id)
            if save_path.exists():
                try:
                    with open(save_path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    
                    slot_type = data.get("slot_type", "unknown")
                    location = data.get("location", "未知")
                    turn = data.get("turn", 0)
                    level = data.get("game_progress", {}).get("level", "?")
                    gold = data.get("game_progress", {}).get("gold", 0)
                    
                    # 格式化时间
                    timestamp = data.get("timestamp", "")
                    if timestamp:
                        try:
                            dt = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
                            # 转换为本地时间
                            local_dt = dt.astimezone()
                            time_str = local_dt.strftime("%Y-%m-%d %H:%M")
                        except ValueError:
                            time_str = timestamp[:16] if len(timestamp) > 16 else timestamp
                    else:
                        time_str = "未知"
                    
                    saves.append({
                        "slot_id": slot_id,
                        "slot_type": slot_type,
                        "timestamp": time_str,
                        "version": data.get("version", "?"),
                        "location": location,
                        "level": level,
                        "gold": gold,
                        "turn": turn,
                    })
                except Exception as e:
                    logger.warning(f"Failed to read save info from slot {slot_id}: {e}")
                    saves.append({
                        "slot_id": slot_id,
                        "slot_type": "unknown",
                        "timestamp": "读取失败",
                        "version": "?",
                        "location": "未知",
                        "level": "?",
                        "gold": 0,
                        "turn": 0,
                        "error": str(e),
                    })
            else:
                saves.append({
                    "slot_id": slot_id,
                    "slot_type": "empty",
                    "timestamp": "空",
                    "version": SAVE_VERSION,
                    "location": "-",
                    "level": "-",
                    "gold": 0,
                    "turn": 0,
                })
        
        return saves

    def delete_save(self, slot_id: int) -> bool:
        """
        删除指定槽位的存档
        
        Args:
            slot_id: 存档槽位 ID
            
        Returns:
            是否删除成功
        """
        try:
            save_path = self.get_save_path(slot_id)
            if save_path.exists():
                save_path.unlink()
                logger.info(f"Save deleted from slot {slot_id}")
                return True
            else:
                logger.warning(f"No save to delete in slot {slot_id}")
                return False
        except Exception as e:
            logger.error(f"Failed to delete save from slot {slot_id}: {e}")
            return False

    def has_auto_save(self) -> bool:
        """
        检查是否存在自动存档
        
        Returns:
            是否存在
        """
        return self.get_save_path(AUTO_SAVE_SLOT).exists()

    def get_auto_save_info(self) -> dict[str, Any] | None:
        """
        获取自动存档的信息（不加载完整数据）
        
        Returns:
            自动存档基本信息，失败返回 None
        """
        try:
            save_path = self.get_save_path(AUTO_SAVE_SLOT)
            if not save_path.exists():
                return None
            
            with open(save_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            return {
                "slot_id": AUTO_SAVE_SLOT,
                "timestamp": data.get("timestamp", ""),
                "location": data.get("location", "未知"),
                "level": data.get("game_progress", {}).get("level", "?"),
                "turn": data.get("turn", 0),
            }
        except Exception as e:
            logger.warning(f"Failed to read auto-save info: {e}")
            return None


# 全局实例
_global_save_manager: SaveManager | None = None


def get_save_manager() -> SaveManager:
    """获取全局 SaveManager 实例"""
    global _global_save_manager
    if _global_save_manager is None:
        _global_save_manager = SaveManager()
    return _global_save_manager
