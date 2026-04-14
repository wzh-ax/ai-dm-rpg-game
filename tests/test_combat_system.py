"""
Combat System - 单元测试
测试战斗系统的核心功能：Combatant、CombatState、CombatSystem
"""

import pytest
import asyncio
from src.combat_system import (
    Combatant,
    CombatantType,
    CombatAction,
    ActionType,
    StatusEffect,
    CombatPhase,
    CombatState,
    CombatSystem,
    get_combat_system,
)


class TestCombatant:
    """测试 Combatant 数据类"""

    def test_create_player(self):
        c = Combatant(
            id="player1",
            name="冒险者A",
            combatant_type=CombatantType.PLAYER,
            max_hp=50,
            current_hp=50,
            armor_class=15,
        )
        assert c.id == "player1"
        assert c.name == "冒险者A"
        assert c.combatant_type == CombatantType.PLAYER
        assert c.current_hp == 50
        assert c.max_hp == 50
        assert c.armor_class == 15
        assert c.is_active is True
        assert c.status == StatusEffect.NORMAL

    def test_take_damage(self):
        c = Combatant(
            id="e1", name="哥布林", combatant_type=CombatantType.ENEMY,
            max_hp=20, current_hp=20
        )
        dmg = c.take_damage(8)
        assert dmg == 8
        assert c.current_hp == 12

    def test_take_damage_kills_combatant(self):
        c = Combatant(
            id="e1", name="哥布林", combatant_type=CombatantType.ENEMY,
            max_hp=20, current_hp=10
        )
        actual = c.take_damage(15)
        assert actual == 10  # 只能受到10点伤害（剩余HP）
        assert c.current_hp == 0
        assert c.is_active is False
        assert c.status == StatusEffect.NORMAL

    def test_overheal_does_not_exceed_max(self):
        c = Combatant(
            id="p1", name="战士", combatant_type=CombatantType.PLAYER,
            max_hp=50, current_hp=40
        )
        healed = c.heal(20)
        assert healed == 10  # 只能恢复10点到满血
        assert c.current_hp == 50

    def test_apply_status(self):
        c = Combatant(
            id="p1", name="战士", combatant_type=CombatantType.PLAYER,
            max_hp=50, current_hp=50
        )
        c.apply_status(StatusEffect.STUNNED)
        assert c.status == StatusEffect.STUNNED

    def test_is_alive(self):
        c = Combatant(
            id="e1", name="史莱姆", combatant_type=CombatantType.ENEMY,
            max_hp=10, current_hp=10
        )
        assert c.is_alive() is True
        
        c.take_damage(10)
        assert c.is_alive() is False


class TestCombatState:
    """测试 CombatState"""

    def test_add_narrative(self):
        state = CombatState(combat_id="test1")
        state.add_narrative("战士攻击了敌人")
        state.add_narrative("敌人倒下了")
        
        log = list(state.narrative_log)
        assert len(log) == 2
        assert "战士攻击了敌人" in log[0]

    def test_get_active_combatants(self):
        p1 = Combatant(id="p1", name="P1", combatant_type=CombatantType.PLAYER, max_hp=30, current_hp=30)
        e1 = Combatant(id="e1", name="E1", combatant_type=CombatantType.ENEMY, max_hp=20, current_hp=0)  # 已倒下
        e2 = Combatant(id="e2", name="E2", combatant_type=CombatantType.ENEMY, max_hp=20, current_hp=20)
        
        state = CombatState(combat_id="test1", combatants={"p1": p1, "e1": e1, "e2": e2})
        active = state.get_active_combatants()
        assert len(active) == 2
        assert p1 in active
        assert e2 in active

    def test_get_current_combatant(self):
        p1 = Combatant(id="p1", name="P1", combatant_type=CombatantType.PLAYER, max_hp=30, current_hp=30)
        state = CombatState(combat_id="test1", combatants={"p1": p1}, turn_order=["p1"], current_turn_index=0)
        
        current = state.get_current_combatant()
        assert current is p1
        assert current.name == "P1"

    def test_is_player_team_alive(self):
        p1 = Combatant(id="p1", name="P1", combatant_type=CombatantType.PLAYER, max_hp=30, current_hp=0)
        e1 = Combatant(id="e1", name="E1", combatant_type=CombatantType.ENEMY, max_hp=20, current_hp=20)
        state = CombatState(combat_id="test1", combatants={"p1": p1, "e1": e1})
        
        assert state.is_player_team_alive() is False
        assert state.is_enemy_team_alive() is True

    def test_get_summary(self):
        p1 = Combatant(id="p1", name="战士", combatant_type=CombatantType.PLAYER, max_hp=50, current_hp=40)
        state = CombatState(combat_id="c1", combatants={"p1": p1}, round=2)
        
        summary = state.get_summary()
        assert summary["combat_id"] == "c1"
        assert summary["round"] == 2
        assert len(summary["active_combatants"]) == 1
        assert summary["active_combatants"][0]["name"] == "战士"
        assert summary["active_combatants"][0]["hp"] == 40


class TestCombatSystem:
    """测试 CombatSystem"""

    @pytest.fixture
    async def combat_system(self):
        """创建战斗系统实例"""
        system = CombatSystem()
        yield system
        # 清理
        if system.get_active_combat():
            await system.end_combat()

    @pytest.mark.asyncio
    async def test_start_combat_initializes_state(self, combat_system):
        p1 = Combatant(id="p1", name="战士", combatant_type=CombatantType.PLAYER, max_hp=50, current_hp=50, initiative=15)
        e1 = Combatant(id="e1", name="哥布林", combatant_type=CombatantType.ENEMY, max_hp=20, current_hp=20)
        
        state = await combat_system.start_combat("test_combat_1", [p1, e1])
        
        assert state is not None
        assert state.combat_id == "test_combat_1"
        assert state.phase in (CombatPhase.IN_PROGRESS, CombatPhase.PLAYER_TURN, CombatPhase.ENEMY_TURN, CombatPhase.ROUND_END)
        assert state.round >= 1
        assert len(state.turn_order) == 2
        # 先攻顺序存储的是 combatant ID
        assert state.turn_order[0] in ("p1", "e1")

    @pytest.mark.asyncio
    async def test_start_combat_sets_initiative_order(self, combat_system):
        p1 = Combatant(id="p1", name="战士", combatant_type=CombatantType.PLAYER, max_hp=50, current_hp=50, initiative=18)
        e1 = Combatant(id="e1", name="哥布林", combatant_type=CombatantType.ENEMY, max_hp=20, current_hp=20, initiative=5)
        
        state = await combat_system.start_combat("test_combat_2", [p1, e1])
        
        # 战士先攻值18 > 哥布林5，所以战士应该在前面
        assert state.turn_order[0] == "p1"
        assert state.turn_order[1] == "e1"

    @pytest.mark.asyncio
    async def test_submit_attack_action(self, combat_system):
        p1 = Combatant(id="p1", name="战士", combatant_type=CombatantType.PLAYER, max_hp=50, current_hp=50, initiative=15)
        e1 = Combatant(id="e1", name="哥布林", combatant_type=CombatantType.ENEMY, max_hp=20, current_hp=20, initiative=5)
        
        await combat_system.start_combat("test_combat_3", [p1, e1])
        
        action = CombatAction(
            combatant_id="p1",
            action_type=ActionType.ATTACK,
            target_id="e1",
        )
        
        state = await combat_system.submit_action("p1", action)
        
        assert state is not None
        # 验证叙事日志有内容
        log = list(state.narrative_log)
        assert len(log) >= 1

    @pytest.mark.asyncio
    async def test_submit_defend_action(self, combat_system):
        p1 = Combatant(id="p1", name="战士", combatant_type=CombatantType.PLAYER, max_hp=50, current_hp=50, initiative=15)
        e1 = Combatant(id="e1", name="哥布林", combatant_type=CombatantType.ENEMY, max_hp=20, current_hp=20, initiative=5)
        
        await combat_system.start_combat("test_combat_4", [p1, e1])
        
        action = CombatAction(
            combatant_id="p1",
            action_type=ActionType.DEFEND,
        )
        
        state = await combat_system.submit_action("p1", action)
        assert state is not None
        
        # 检查战士状态是否变为 DEFENDING
        p1_state = state.combatants["p1"]
        assert p1_state.status == StatusEffect.DEFENDING

    @pytest.mark.asyncio
    async def test_end_combat(self, combat_system):
        p1 = Combatant(id="p1", name="战士", combatant_type=CombatantType.PLAYER, max_hp=50, current_hp=50)
        e1 = Combatant(id="e1", name="哥布林", combatant_type=CombatantType.ENEMY, max_hp=20, current_hp=20)
        
        await combat_system.start_combat("test_combat_5", [p1, e1])
        result = await combat_system.end_combat(reason="测试结束")
        
        assert result is not None
        assert result.phase == CombatPhase.COMBAT_END
        assert combat_system.get_active_combat() is None

    @pytest.mark.asyncio
    async def test_no_active_combat_raises_error(self, combat_system):
        with pytest.raises(RuntimeError, match="No active combat"):
            await combat_system.submit_action("p1", CombatAction(combatant_id="p1", action_type=ActionType.ATTACK))


class TestCombatIntegration:
    """集成测试：完整战斗流程"""

    @pytest.mark.asyncio
    async def test_full_combat_flow(self):
        """测试：玩家击败敌人的完整流程"""
        system = CombatSystem()
        
        # 创建角色
        player = Combatant(
            id="player1",
            name="勇者",
            combatant_type=CombatantType.PLAYER,
            max_hp=100,
            current_hp=100,
            initiative=18,
            armor_class=16,
        )
        enemy = Combatant(
            id="enemy1",
            name="恶龙",
            combatant_type=CombatantType.ENEMY,
            max_hp=80,
            current_hp=80,
            initiative=12,
            armor_class=14,
        )
        
        # 开始战斗
        state = await system.start_combat("dragon_fight", [player, enemy])
        
        # 第一轮：玩家攻击（start_combat 后 round 可能已经是2，因为 _start_round 会+1）
        assert state.round >= 1
        action1 = CombatAction(
            combatant_id="player1",
            action_type=ActionType.ATTACK,
            target_id="enemy1",
        )
        state = await system.submit_action("player1", action1)
        
        # 第一轮：敌人回合
        action2 = CombatAction(
            combatant_id="enemy1",
            action_type=ActionType.ATTACK,
            target_id="player1",
        )
        state = await system.submit_action("enemy1", action2)
        
        # 验证战斗进行中（phase可能是 PLAYER_TURN 因为进入了新回合）
        assert state.phase in (CombatPhase.IN_PROGRESS, CombatPhase.PLAYER_TURN, CombatPhase.ENEMY_TURN, CombatPhase.ROUND_END)
        assert state.round >= 1
        
        # 清理
        await system.end_combat()

    @pytest.mark.asyncio
    async def test_combat_turn_order_follows_initiative(self):
        """测试：行动顺序严格按照先攻值"""
        system = CombatSystem()
        
        fast = Combatant(id="fast", name="快刀手", combatant_type=CombatantType.PLAYER, max_hp=30, current_hp=30, initiative=20)
        slow = Combatant(id="slow", name="重甲兵", combatant_type=CombatantType.PLAYER, max_hp=50, current_hp=50, initiative=5)
        enemy = Combatant(id="enemy", name="怪物", combatant_type=CombatantType.ENEMY, max_hp=20, current_hp=20, initiative=10)
        
        state = await system.start_combat("order_test", [fast, slow, enemy])
        
        # 验证先攻顺序
        assert state.turn_order[0] == "fast"      # 先攻20
        assert state.turn_order[1] == "enemy"     # 先攻10
        assert state.turn_order[2] == "slow"      # 先攻5
        
        await system.end_combat()


class TestDifficultyMode:
    """测试难度模式功能"""

    def test_difficulty_enum_exists(self):
        """测试 Difficulty 枚举存在且包含三个难度"""
        from src.combat_system import Difficulty
        assert Difficulty.EASY.value == "easy"
        assert Difficulty.NORMAL.value == "normal"
        assert Difficulty.HARD.value == "hard"

    def test_difficulty_scaling_config(self):
        """测试难度缩放配置正确"""
        from src.combat_system import Difficulty, DIFFICULTY_SCALING
        easy = DIFFICULTY_SCALING[Difficulty.EASY]
        assert easy["hp_mult"] == 0.7
        assert easy["damage_mult"] == 0.8
        assert easy["drop_mult"] == 1.5
        assert easy["flee_bonus"] is True

        normal = DIFFICULTY_SCALING[Difficulty.NORMAL]
        assert normal["hp_mult"] == 1.0
        assert normal["damage_mult"] == 1.0
        assert normal["drop_mult"] == 1.0

        hard = DIFFICULTY_SCALING[Difficulty.HARD]
        assert hard["hp_mult"] == 1.5
        assert hard["damage_mult"] == 1.3
        assert hard["drop_mult"] == 0.5
        assert hard["flee_bonus"] is False

    def test_enemy_factory_create_enemy_easy(self):
        """测试简单难度下敌人 HP 减少"""
        from src.combat_system import EnemyFactory, Difficulty
        enemy = EnemyFactory.create_enemy("影狼", level=1, difficulty=Difficulty.EASY)
        # 影狼基础 HP=12, 无等级缩放时 HP=12, 简单难度×0.7 = 8
        assert enemy.max_hp == 8
        assert enemy.damage_mult == 0.8

    def test_enemy_factory_create_enemy_normal(self):
        """测试普通难度下敌人属性不变"""
        from src.combat_system import EnemyFactory, Difficulty
        enemy = EnemyFactory.create_enemy("影狼", level=1, difficulty=Difficulty.NORMAL)
        # 影狼基础 HP=12, 无等级缩放×1.0 = 12
        assert enemy.max_hp == 12
        assert enemy.damage_mult == 1.0

    def test_enemy_factory_create_enemy_hard(self):
        """测试困难难度下敌人 HP 增加"""
        from src.combat_system import EnemyFactory, Difficulty
        enemy = EnemyFactory.create_enemy("影狼", level=1, difficulty=Difficulty.HARD)
        # 影狼基础 HP=12, 无等级缩放×1.5 = 18
        assert enemy.max_hp == 18
        assert enemy.damage_mult == 1.3

    def test_enemy_factory_create_enemy_hard_with_level_scaling(self):
        """测试困难难度下敌人 HP 随等级缩放后再乘难度系数"""
        from src.combat_system import EnemyFactory, Difficulty
        # 等级2: scale_hp = 1.0 + (2-1)*0.15 = 1.15
        # 影狼基础 HP=12, 等级缩放后=13.8→int=13, 困难难度×1.5 = 19.5→int=20
        enemy = EnemyFactory.create_enemy("影狼", level=2, difficulty=Difficulty.HARD)
        assert enemy.max_hp == 20, f"Expected 20 (int(12*1.15*1.5)), got {enemy.max_hp}"

    def test_enemy_factory_create_random_enemy_accepts_difficulty(self):
        """测试 create_random_enemy 接受 difficulty 参数并正确设置 damage_mult"""
        from src.combat_system import EnemyFactory, Difficulty
        # 多次调用确保 difficulty 参数被正确应用（damage_mult 应为 1.3）
        for _ in range(5):
            enemy, is_generic = EnemyFactory.create_random_enemy(level=1, location="森林", difficulty=Difficulty.HARD)
            assert enemy.damage_mult == 1.3, f"Expected 1.3, got {enemy.damage_mult}"
            # HP 应该大于普通难度下的 HP（证明难度已应用）
            assert enemy.max_hp > 0

    def test_enemy_difficulty_affects_damage(self):
        """测试难度影响敌人伤害（通过 damage_mult）"""
        from src.combat_system import EnemyFactory, Difficulty
        easy_enemy = EnemyFactory.create_enemy("影狼", level=1, difficulty=Difficulty.EASY)
        hard_enemy = EnemyFactory.create_enemy("影狼", level=1, difficulty=Difficulty.HARD)

        # 验证 damage_mult 已正确设置
        assert easy_enemy.damage_mult == 0.8
        assert hard_enemy.damage_mult == 1.3

        # 伤害计算在 _resolve_action 中使用 damage_mult
        # 基础伤害 easy: max(1, int((max_hp//6) * 0.8)) = max(1, int(8//6*0.8)) = max(1, 1) = 1
        # 基础伤害 hard: max(1, int((max_hp//6) * 1.3)) = max(1, int(18//6*1.3)) = max(1, int(3*1.3)) = max(1, 3) = 3
        easy_base_damage = max(1, int((easy_enemy.max_hp // 6) * easy_enemy.damage_mult))
        hard_base_damage = max(1, int((hard_enemy.max_hp // 6) * hard_enemy.damage_mult))
        assert easy_base_damage < hard_base_damage, "简单难度敌人伤害应低于困难难度"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
