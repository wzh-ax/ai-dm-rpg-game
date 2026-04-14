"""测试 SaveManager - 存档管理系统"""
import json
import os
import tempfile
from pathlib import Path

import pytest

from src.save_manager import SaveManager, AUTO_SAVE_SLOT, MAX_SLOTS, SAVE_VERSION


@pytest.fixture
def temp_save_dir():
    """创建临时存档目录"""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def save_manager(temp_save_dir):
    """创建 SaveManager 实例（使用临时目录）"""
    return SaveManager(save_dir=temp_save_dir)


@pytest.fixture
def sample_game_state():
    """示例游戏状态"""
    return {
        "turn": 10,
        "location": "酒馆",
        "mode": "exploration",
        "player_stats": {
            "hp": 25,
            "max_hp": 30,
            "ac": 12,
            "xp": 50,
            "level": 2,
            "gold": 100,
            "inventory": [
                {"name": "治疗药水", "rarity": "common"},
                {"name": "生锈的短剑", "rarity": "common"},
            ],
        },
        "active_npcs": {"npc1": {"name": "酒馆老板", "role": "merchant"}},
    }


class TestSaveManagerBasics:
    """测试 SaveManager 基本功能"""

    def test_get_save_path(self, save_manager, temp_save_dir):
        """测试获取存档路径"""
        path = save_manager.get_save_path(1)
        assert path == temp_save_dir / "save_1.json"
        
        auto_path = save_manager.get_save_path(AUTO_SAVE_SLOT)
        assert auto_path == temp_save_dir / "save_0.json"

    def test_save_game(self, save_manager, sample_game_state):
        """测试保存游戏"""
        result = save_manager.save_game(sample_game_state, 1)
        assert result is True
        
        # 验证文件存在
        save_path = save_manager.get_save_path(1)
        assert save_path.exists()

    def test_load_game(self, save_manager, sample_game_state):
        """测试加载游戏"""
        # 先保存
        save_manager.save_game(sample_game_state, 1)
        
        # 再加载
        loaded = save_manager.load_game(1)
        assert loaded is not None
        assert loaded["turn"] == 10
        assert loaded["location"] == "酒馆"
        assert loaded["player_stats"]["hp"] == 25
        assert loaded["player_stats"]["level"] == 2
        assert loaded["player_stats"]["gold"] == 100

    def test_save_load_roundtrip(self, save_manager, sample_game_state):
        """测试存档/读档往返"""
        # 保存
        save_manager.save_game(sample_game_state, 2)
        
        # 加载
        loaded = save_manager.load_game(2)
        
        # 验证关键字段
        assert loaded["turn"] == sample_game_state["turn"]
        assert loaded["location"] == sample_game_state["location"]
        assert loaded["player_stats"]["hp"] == sample_game_state["player_stats"]["hp"]
        assert loaded["player_stats"]["max_hp"] == sample_game_state["player_stats"]["max_hp"]
        assert loaded["player_stats"]["ac"] == sample_game_state["player_stats"]["ac"]
        assert loaded["player_stats"]["xp"] == sample_game_state["player_stats"]["xp"]
        assert loaded["player_stats"]["level"] == sample_game_state["player_stats"]["level"]
        assert loaded["player_stats"]["gold"] == sample_game_state["player_stats"]["gold"]
        assert loaded["player_stats"]["inventory"] == sample_game_state["player_stats"]["inventory"]

    def test_load_nonexistent(self, save_manager):
        """测试加载不存在的存档"""
        result = save_manager.load_game(99)
        assert result is None

    def test_delete_save(self, save_manager, sample_game_state):
        """测试删除存档"""
        # 先保存
        save_manager.save_game(sample_game_state, 1)
        assert save_manager.get_save_path(1).exists()
        
        # 删除
        result = save_manager.delete_save(1)
        assert result is True
        assert not save_manager.get_save_path(1).exists()

    def test_delete_nonexistent(self, save_manager):
        """测试删除不存在的存档"""
        result = save_manager.delete_save(99)
        assert result is False


class TestSaveManagerSlots:
    """测试多存档槽位"""

    def test_multiple_slots(self, save_manager, sample_game_state):
        """测试多个存档槽位"""
        # 保存到不同槽位
        save_manager.save_game(sample_game_state, 1)
        
        modified_state = dict(sample_game_state)
        modified_state["turn"] = 20
        modified_state["player_stats"]["gold"] = 200
        save_manager.save_game(modified_state, 2)
        
        # 加载验证
        loaded1 = save_manager.load_game(1)
        loaded2 = save_manager.load_game(2)
        
        assert loaded1["turn"] == 10
        assert loaded1["player_stats"]["gold"] == 100
        assert loaded2["turn"] == 20
        assert loaded2["player_stats"]["gold"] == 200

    def test_list_saves(self, save_manager, sample_game_state):
        """测试列出存档"""
        # 保存两个槽位
        save_manager.save_game(sample_game_state, 1)
        
        modified_state = dict(sample_game_state)
        modified_state["location"] = "森林"
        save_manager.save_game(modified_state, 2)
        
        saves = save_manager.list_saves()
        
        assert len(saves) == MAX_SLOTS
        
        # 槽位 1 和 2 应该有存档
        slot1_info = next(s for s in saves if s["slot_id"] == 1)
        slot2_info = next(s for s in saves if s["slot_id"] == 2)
        
        assert slot1_info["slot_type"] == "manual"
        assert slot1_info["location"] == "酒馆"
        assert slot2_info["slot_type"] == "manual"
        assert slot2_info["location"] == "森林"
        
        # 空槽位
        empty_slot = next(s for s in saves if s["slot_id"] == 3)
        assert empty_slot["slot_type"] == "empty"

    def test_auto_save_slot(self, save_manager, sample_game_state):
        """测试自动存档槽位"""
        save_manager.save_game(sample_game_state, AUTO_SAVE_SLOT)
        
        loaded = save_manager.load_game(AUTO_SAVE_SLOT)
        assert loaded is not None
        assert loaded["turn"] == 10
        
        saves = save_manager.list_saves()
        auto_save_info = next(s for s in saves if s["slot_id"] == AUTO_SAVE_SLOT)
        assert auto_save_info["slot_type"] == "auto"


class TestSaveManagerAutoCreate:
    """测试自动创建存档目录"""

    def test_auto_create_save_dir(self):
        """测试自动创建存档目录"""
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            temp_path = Path(tmpdir) / "saves"
            # 目录不存在
            assert not temp_path.exists()
            
            # 创建 SaveManager 时应该自动创建目录
            sm = SaveManager(save_dir=temp_path)
            sm._ensure_save_dir()
            
            assert temp_path.exists()
            assert temp_path.is_dir()


class TestSaveManagerVersioning:
    """测试存档版本兼容性"""

    def test_version_in_save_data(self, save_manager, sample_game_state):
        """测试存档中包含版本信息"""
        save_manager.save_game(sample_game_state, 1)
        
        save_path = save_manager.get_save_path(1)
        with open(save_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        assert data["version"] == SAVE_VERSION
        assert "timestamp" in data
        assert "slot_id" in data
        assert data["slot_id"] == 1

    def test_version_compatible_current(self, save_manager):
        """测试当前版本兼容"""
        assert save_manager._check_version_compatible("1.0") is True
        assert save_manager._check_version_compatible("1.1") is True
        assert save_manager._check_version_compatible("1.9") is True

    def test_version_compatible_old(self, save_manager):
        """测试旧版本不兼容"""
        assert save_manager._check_version_compatible("0.9") is False
        assert save_manager._check_version_compatible("2.0") is False


class TestSaveManagerAutoSave:
    """测试自动存档功能"""

    def test_has_auto_save(self, save_manager, sample_game_state):
        """测试检查自动存档"""
        assert save_manager.has_auto_save() is False
        
        save_manager.save_game(sample_game_state, AUTO_SAVE_SLOT)
        assert save_manager.has_auto_save() is True

    def test_get_auto_save_info(self, save_manager, sample_game_state):
        """测试获取自动存档信息"""
        # 无自动存档时
        info = save_manager.get_auto_save_info()
        assert info is None
        
        # 有自动存档时
        save_manager.save_game(sample_game_state, AUTO_SAVE_SLOT)
        info = save_manager.get_auto_save_info()
        assert info is not None
        assert info["slot_id"] == AUTO_SAVE_SLOT
        assert info["location"] == "酒馆"
        assert info["level"] == 2
        assert info["turn"] == 10


class TestSaveManagerEdgeCases:
    """测试边界情况"""

    def test_empty_inventory(self, save_manager):
        """测试空背包"""
        state = {
            "turn": 1,
            "location": "起点",
            "player_stats": {
                "hp": 30,
                "max_hp": 30,
                "ac": 12,
                "xp": 0,
                "level": 1,
                "gold": 0,
                "inventory": [],
            },
        }
        
        save_manager.save_game(state, 1)
        loaded = save_manager.load_game(1)
        
        assert loaded["player_stats"]["inventory"] == []

    def test_special_characters_in_location(self, save_manager):
        """测试位置名称包含特殊字符"""
        state = {
            "turn": 5,
            "location": "酒馆「醉生梦死」",
            "player_stats": {
                "hp": 30,
                "max_hp": 30,
                "ac": 12,
                "xp": 0,
                "level": 1,
                "gold": 0,
                "inventory": [],
            },
        }
        
        save_manager.save_game(state, 1)
        loaded = save_manager.load_game(1)
        
        assert loaded["location"] == "酒馆「醉生梦死」"

    def test_overwrite_save(self, save_manager, sample_game_state):
        """测试覆盖存档"""
        save_manager.save_game(sample_game_state, 1)
        
        modified_state = dict(sample_game_state)
        modified_state["turn"] = 999
        save_manager.save_game(modified_state, 1)
        
        loaded = save_manager.load_game(1)
        assert loaded["turn"] == 999
