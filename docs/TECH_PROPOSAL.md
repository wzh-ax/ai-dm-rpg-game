# AI DM RPG 技术修复方案

**方案师**: 方案师 🛠️
**基于根因分析**: `docs/ROOT_CAUSE_ANALYSIS.md`（根因师 genyin 🔍，2026-04-12）
**日期**: 2026-04-12

---

## 技术方案

### 根因确认

根因分析报告准确，主要结构性根因有两层：

1. **降级不可逆**：一旦 LLM 调用失败触发 fallback，`current_scene.atmosphere` 被硬编码为 `"mysterious"` 并永续使用，导致 `_generate_main_narrative` 每次输出相同的万能敷衍模板。
2. **输入路由缺失**：系统命令（"查看状态"等）和游戏内命令（"攻击NPC"等）没有专门分支，全部进入通用叙事生成流程——无匹配时必然输出万能敷衍。

另有两个次要根因：
- **Fallback tier 忽略场景语义**：酒馆等需要 NPC 的社交场景 fallback 到 LIGHT（无 NPC），导致自相矛盾。
- **"未知敌人"兜底失效**：`EnemyFactory.create_enemy("未知敌人")` 找不到匹配，战斗无法初始化。

### 修复方案

---

#### 方案A（推荐）：分层修复，按优先级推进

##### P0-1：修复 `_generate_main_narrative` — 调用 `generate_atmosphere_v2` 替代硬编码字段

**改动点**: `src/game_master.py` → `_generate_main_narrative()`

**具体实现步骤**:
1. 在 `_generate_main_narrative()` 中，检测 `current_scene` 是否处于降级状态（`atmosphere == "mysterious"` 且无有效 description）。
2. 如果检测到降级，调用 `generate_atmosphere_v2(scene_type=current_scene.get("type", "未知"), consecutive_rounds=turn)` 生成动态氛围。
3. 用 `generate_atmosphere_v2` 的返回值（`atmosphere_str`）替代硬拼的 `"空气中弥漫着{atmosphere}的气息"` 模板。
4. 如果 `generate_atmosphere_v2` 也失败（连续调用自身），使用基于 scene_type 的硬编码模板兜底（每 scene_type 预置 3-5 条差异化开场白，随机选一条）。

```python
# 改动后的核心逻辑（示意）
atmosphere = self.current_scene.get("atmosphere", "")
if atmosphere == "mysterious" or not atmosphere:
    # 降级状态，强制使用 generate_atmosphere_v2 动态生成
    atm_result = generate_atmosphere_v2(
        scene_type=self.current_scene.get("type", "未知"),
        consecutive_rounds=turn
    )
    base_narrative += atm_result.get("atmosphere_str", "周围一切平静。")
else:
    # 正常状态
    scene_details = []
    if atmosphere:
        scene_details.append(f"空气中弥漫着{atmosphere}的气息")
    if scene_details:
        base_narrative += "，".join(scene_details) + "。"
```

**优点**:
- 不改变现有数据流，只改 `_generate_main_narrative` 一个方法
- `generate_atmosphere_v2` 已是成熟实现，无需 LLM 调用
- 差异化策略（按 consecutive_rounds 变化）避免重复输出

**风险/注意点**:
- 需要传入 `turn` 参数（已传入），用于 consecutive_rounds
- `generate_atmosphere_v2` 依赖随机种子，需确保 random 模块行为可复现（测试时固定 seed）

---

##### P0-2：修复 `generate_synopsis` fallback — 使用 `generate_atmosphere_v2` 而非硬编码

**改动点**: `src/scene_agent.py` → `generate_synopsis()` 中的 fallback 块

**具体实现步骤**:
1. 定位 `generate_synopsis()` 中 LLM 调用失败后的 fallback 逻辑。
2. 将硬编码的 `atmosphere="mysterious"` 替换为调用 `generate_atmosphere_v2(scene_type=scene_type, consecutive_rounds=1)`。
3. 将返回的 `atmosphere_str` 截取作为 synopsis 的 atmosphere 字段。

```python
# 改动后（示意）
except Exception as e:
    logger.warning(f"generate_synopsis LLM failed: {e}, using fallback atmosphere")
    atm_fallback = generate_atmosphere_v2(scene_type=scene_type, consecutive_rounds=1)
    synopsis_data = {
        "atmosphere": atm_fallback.get("atmosphere", "平静"),
        "atmosphere_str": atm_fallback.get("atmosphere_str", ""),
        "synopsis": f"一个{scene_type}类型的地点",
        # ... 其余硬编码字段保持不变
    }
```

**优点**:
- 阻止 `"mysterious"` 写入 scene，彻底消除万能敷衍源头
- 改动集中在一处，影响范围可控

**风险/注意点**:
- `generate_synopsis` 失败时，其他字段（`npcs`、`objects`）仍是硬编码，需要配合 P0-3（P1 优先级）

---

##### P0-3：降级检测触发强制重试 — `DegradationTracker` 增加恢复动作

**改动点**: `src/fallback_strategy.py` → `DegradationTracker` 类 + `src/game_master.py` → `_handle_exploration_input()`

**具体实现步骤**:
1. 在 `DegradationTracker` 中，当 `degradation_count >= alert_threshold(3)` 时，触发恢复事件：
   ```python
   if self.degradation_count >= self.alert_threshold:
       self.event_bus.publish(EventType.DEGRADATION_RECOVERY_TRIGGERED, {
           "count": self.degradation_count,
           "scene_type": scene_type,
       })
   ```
2. 在 `game_master.py` 的 `_handle_exploration_input()` 中，订阅 `DEGRADATION_RECOVERY_TRIGGERED` 事件。
3. 收到事件后，调用 `generate_scene()` 强制重新生成当前场景（传入 `force_regenerate=True`），将新场景替换 `current_scene`。

```python
# _handle_exploration_input 改动
self.event_bus.subscribe(EventType.DEGRADATION_RECOVERY_TRIGGERED, self._on_degradation_recovery)

async def _on_degradation_recovery(self, event: Event):
    logger.warning("Degradation threshold reached, forcing scene regeneration")
    new_scene = await self.scene_agent.generate_scene(
        scene_type=self.current_scene.get("type", "森林"),
        force_regenerate=True
    )
    self.current_scene = new_scene
```

**优点**:
- 恢复机制闭环：检测→告警→恢复，不再是"只记录不动作"
- 不改变降级逻辑，只在检测到连续降级时主动恢复

**风险/注意点**:
- 需要 `event_bus` 支持事件订阅，验证当前已有订阅机制
- 重新生成场景有 LLM 调用成本，避免在短时内重复触发（增加冷却期检查，如 3 回合内不重复强制重试）

---

##### P0-4：修复战斗触发兜底 — "未知敌人"改为场景通用怪物

**改动点**: `src/game_master.py` → `_check_combat_trigger()` 和 `_extract_enemy_name()`

**具体实现步骤**:
1. 当 `_extract_enemy_name()` 返回 `None` 时，根据当前 `current_scene.type` 映射一个场景内嵌的通用敌人：
   ```python
   SCENE_GENERIC_ENEMIES = {
       "森林": "森林狼",
       "洞穴": "洞穴蝙蝠",
       "酒馆": None,  # 酒馆无敌人
       "城镇": "流浪恶犬",
       "平原": "草原巨蟒",
       "城堡": "守卫骷髅",
       "河流": "河流鱼人",
   }
   ```
2. 当 `_extract_enemy_name` 返回 `None` 且攻击关键词存在时，从 `SCENE_GENERIC_ENEMIES` 取对应敌人，而非 `"未知敌人"`。
3. 验证 `EnemyFactory.create_enemy(scene_generic_enemy)` 对所有映射敌人都能成功创建。

```python
def _check_combat_trigger(self, player_text: str) -> dict | None:
    # ... existing logic ...
    for kw in attack_keywords:
        if kw in text:
            enemy_name = self._extract_enemy_name(text)
            if enemy_name is None:
                # 降级兜底：基于场景类型生成通用敌人
                scene_type = self.current_scene.get("type", "") if self.current_scene else ""
                enemy_name = SCENE_GENERIC_ENEMIES.get(scene_type, "森林狼")
            return {
                "trigger": "aggressive",
                "enemy_data": {"name": enemy_name, "role": "怪物"},
                "enemy_id": f"enemy_{enemy_name}",
            }
    return None
```

**优点**:
- 改动极小，只改一个方法
- 玩家在任何场景说"攻击"都能触发有效战斗，不依赖敌人名称匹配

**风险/注意点**:
- 需验证 `EnemyFactory` 对所有 `SCENE_GENERIC_ENEMIES` 值都能成功创建（加单元测试覆盖）
- 酒馆场景 `None` 时，应返回 `None`（不触发战斗，提示"这里不适合战斗"）

---

##### P0-5：游戏内系统命令检测 — 在 `_handle_exploration_input` 中添加独立分支

**改动点**: `src/game_master.py` → `_handle_exploration_input()`

**具体实现步骤**:
1. 在 `_handle_exploration_input()` 开头，添加系统命令检测分支（不依赖 `interactive_master` 的路由）：
   ```python
   async def _handle_exploration_input(self, player_text: str, turn: int) -> str:
       # 系统命令内联处理（游戏内触发，不走 interactive_master 路由）
       system_commands = {
           "查看状态": self._cmd_status,
           "状态": self._cmd_status,
           "背包": self._cmd_bag,
           "查看背包": self._cmd_bag,
           "商店": self._cmd_shop,
           "任务": self._cmd_quest,
       }
       for cmd, handler in system_commands.items():
           if player_text.strip() == cmd or cmd in player_text.strip():
               return await handler(turn)
   ```
2. 实现各 `_cmd_*` 方法（`_cmd_status` → 返回玩家状态摘要，`_cmd_bag` → 返回背包物品列表，`_cmd_shop` → 返回商店信息，`_cmd_quest` → 返回任务进度）。
3. 这些命令处理函数直接返回格式化文本字符串（不需要 LLM 调用）。

**优点**:
- 系统命令完全在游戏循环内处理，不受 `interactive_master` 编码问题影响
- 改动集中，测试容易

**风险/注意点**:
- 命令检测用 `in` 做模糊匹配，"查看状态详情" 也会触发"查看状态"
- 模糊匹配可能误触发，需明确黑名单（如"我查看状态的影子"不应触发命令）

---

##### P1-1：Fallback tier 按场景类型设置最低要求

**改动点**: `src/fallback_strategy.py` → `get_fallback_scene()`

**具体实现步骤**:
1. 在 `get_fallback_scene()` 中，场景类型到最低 tier 的映射：
   ```python
   SCENE_MIN_TIER = {
       "酒馆": FallbackTier.MEDIUM,  # 酒馆必须有 NPC
       "城镇": FallbackTier.MEDIUM,
       "村庄": FallbackTier.MEDIUM,
       "森林": FallbackTier.LIGHT,
       "洞穴": FallbackTier.LIGHT,
       "平原": FallbackTier.LIGHT,
       "河流": FallbackTier.LIGHT,
   }
   ```
2. 计算复杂度后，选择 `max(复杂度对应 tier, SCENE_MIN_TIER.get(scene_type, FallbackTier.LIGHT))` 作为最终 tier。
3. MEDIUM+ tier 的 fallback 场景预置基本 NPC（如酒馆预置"酒馆老板"）。

**优点**:
- 消除酒馆等社交场景的"自相矛盾"（有场景名但无 NPC）

**风险/注意点**:
- MEDIUM tier 的 fallback NPC 数据需要预先配置（工作量）

---

##### P1-2：修复 `interactive_master` 中文命令路由编码问题

**改动点**: `interactive_master.py` → 命令路由块

**具体实现步骤**:
1. 移除 `.lower()` 对中文命令的处理：
   ```python
   # 移除 cmd = player_input.lower()
   # 改为直接比较（中文无需大小写转换）
   stripped = player_input.strip()
   
   if stripped in ("quit", "exit", "退出", "q"):
       # ...
   if stripped in ("help", "帮助", "h", "?"):
       # ...
   # 中文命令不再依赖 lower()
   if stripped in ("查看状态", "状态", "status"):
       print_status(master.game_state)
       continue
   ```
2. 对于英文命令保留 `.lower()`（如 `cmd in ("quit", "exit", "q")`）。

**优点**:
- 彻底解决中文命令匹配依赖 `.lower()` 的潜在编码陷阱

**风险/注意点**:
- 改动在 `interactive_master.py` 的主循环，需完整回归测试所有系统命令

---

### 涉及模块

| 文件 | 改动类型 | 优先级 |
|------|---------|--------|
| `src/game_master.py` | 修改：`_generate_main_narrative`, `_check_combat_trigger`, `_extract_enemy_name`, `_handle_exploration_input`, 新增 `_cmd_*` 方法 | P0-1, P0-4, P0-5 |
| `src/scene_agent.py` | 修改：`generate_synopsis()` fallback 块 | P0-2 |
| `src/fallback_strategy.py` | 修改：`DegradationTracker` 增加恢复事件触发，`get_fallback_scene()` 增加场景类型最低 tier | P0-3, P1-1 |
| `interactive_master.py` | 修改：命令路由移除 `.lower()` | P1-2 |

---

### 测试建议

#### 单元测试（优先）

1. **test_generate_main_narrative_degradation**：
   - 构造 `current_scene.atmosphere = "mysterious"` 的降级场景
   - 调用 `_generate_main_narrative`，验证输出**不**包含 `"空气中弥漫着 mysterious 的气息"`
   - 验证输出来自 `generate_atmosphere_v2`（mock 验证调用）

2. **test_extract_enemy_name_unknown**：
   - 输入 `"攻击"`（无具体敌人名）
   - 调用 `_check_combat_trigger`，验证返回的 `enemy_name` 是场景对应通用敌人，而非 `None` 或 `"未知敌人"`

3. **test_handle_exploration_input_system_command**：
   - 输入 `"查看状态"`，验证返回包含玩家 HP、金币等状态信息，而非万能敷衍
   - 输入 `"背包"`、`"商店"` 同理

#### 集成测试

1. **降级恢复流程**：
   - 模拟连续 3 次 LLM 失败（mock `generate_synopsis` 抛出异常）
   - 验证 `DegradationTracker` 触发恢复事件
   - 验证第 4 次调用时场景被重新生成（`force_regenerate=True`）

2. **战斗流程端到端**：
   - 森林场景输入 `"攻击"` → 验证触发 `森林狼` 战斗
   - 验证 `EnemyFactory.create_enemy("森林狼")` 成功

3. **系统命令端到端**：
   - 从 `interactive_master` 主循环输入 `"查看状态"` → 验证 `print_status` 被调用（mock 验证）
   - 编码测试：传入 `"查看状态\r\n"`（带换行）仍能正确匹配

#### 回归测试（原有功能不破坏）

- 非降级场景（`atmosphere != "mysterious"`）的正常叙事输出保持不变
- 有明确敌人名的攻击（如"攻击哥布林"）保持原有匹配逻辑
- 非系统命令的普通游戏输入不受 P0-5 影响

---

## 第二轮方案（2026-04-12）

> 本方案基于 2026-04-12 第二轮根因分析，针对已确认的结构性根因制定具体实现。

---

## 第三轮更新（2026-04-12 下午场体验报告）

### 新增 P0：NPC 对话崩溃

**问题**：`'str' object has no attribute 'value'` — 玩家第一次与 NPC 对话时游戏直接崩溃，完全阻断社交/任务系统。

**根因追踪**：
1. `event_bus.py` 的 `_dispatch_event` 调用 `sub.callback(event)` 时，`_on_player_input` 收到 Event
2. 处理链中某处将字符串当作枚举类型调用了 `.value`
3. `npc_agent.py` 的 `_on_npc_dialogue` 收到 `npc_id=None`，说明事件发布时 NPC ID 未正确传递
4. 最终错误：`'str' object has no attribute 'value'`

**修复方案**（P0-NEW）：
- 在 `game_master.py` 或 `npc_agent.py` 中追踪 `.value` 调用点
- 修复 NPC ID 事件传递链路，确保 `_on_npc_dialogue` 收到有效 `npc_id`
- 添加防御性检查：在调用 `.value` 前先验证对象类型

**文件**：待追踪（需要读取 `src/event_bus.py`、`src/game_master.py`、`src/npc_agent.py`）

**验收标准**：与 NPC 对话不再崩溃，`pytest tests/ -x -q` 338+ 通过

---

### 新增 P1：NPC 崩溃连带导致空响应

**问题**：NPC 对话崩溃后，后续所有输入（战斗、场景切换、边界输入）均返回空响应（47% 空响应率）。

**根因**：NPC 异常未被正确捕获，导致整个 `_on_player_input` 处理链中断，后续事件无法正常发布。

**修复方案**：与 P0-NEW 联动，修复 NPC 异常后自然解决；同时在 `_on_player_input` 添加异常隔离，确保单个模块崩溃不影响全局。

---

### 根因与问题映射

| 系统根因 | 对应问题 | 优先级 |
|---------|---------|-------|
| A: LLM降级不可逆，无恢复机制 | 万能敷衍循环 | P0 |
| B: 输入理解层缺少命令路由 | 系统命令失效 | P0 |
| C: Fallback tier只看复杂度不看场景语义 | 酒馆场景自相矛盾 | P1 |
| D（新增）: NPC ID 事件传递链路断裂 + 字符串误用为枚举 | NPC对话崩溃 + 后续空响应 | P0 |

---

### P0 问题：NPC 对话崩溃（新增·最高优先）

#### P0-NEW：追踪并修复 `'str' object has no attribute 'value'`

**文件**: `src/event_bus.py`, `src/npc_agent.py`, `src/game_master.py`

**排查步骤**:
1. 在 `event_bus.py` 的 `_dispatch_event` 中，所有 `.callback(event)` 调用处添加类型检查
2. 在 `game_master.py` 的 `_on_player_input` 中搜索所有 `.value` 调用，确认哪个将字符串当作枚举使用
3. 检查 NPC 事件发布路径：`npc_id` 是否在事件载荷中正确传递

**修复逻辑**:
```python
# 示例：在调用 .value 前加类型检查
if isinstance(some_var, Enum):
    value = some_var.value
else:
    value = some_var  # 直接使用
```

**NPC ID 传递链路修复**:
```python
# 确保 _on_npc_dialogue 收到有效 npc_id
# 在事件发布处验证 npc_id 不为 None
if npc_id is None:
    logger.error(f"NPC ID is None, cannot trigger dialogue: {player_text}")
    return
```

**异常隔离**：在 `_on_player_input` 中对每个 handler（npc/object/combat）添加独立 try/except，确保单个模块崩溃不导致整条链路中断。

**测试**: 与 NPC 对话不崩溃，`pytest tests/ -x -q` 338+ 通过

**工作量**: 中

---

### P0 问题：万能敷衍循环

#### P0-1：`_generate_main_narrative` 调用 `generate_atmosphere_v2`

**文件**: `src/game_master.py`

**改动**: `_generate_main_narrative()` 方法

**逻辑**:
1. 检测 `current_scene.atmosphere == "mysterious"` → 降级状态
2. 降级时调用 `generate_atmosphere_v2(scene_type, consecutive_rounds=turn)` 动态生成
3. 用返回的 `atmosphere_str` 替代硬编码模板
4. 若 `generate_atmosphere_v2` 也失败 → 基于 scene_type 的预置模板兜底

**测试**: 构造 `atmosphere="mysterious"` 场景，验证输出不含 `"空气中弥漫着 mysterious 的气息"`

**工作量**: 小

---

#### P0-2：`generate_synopsis` fallback 改用 `generate_atmosphere_v2`

**文件**: `src/scene_agent.py`

**改动**: `generate_synopsis()` 的 except 块

**逻辑**: 将硬编码 `atmosphere="mysterious"` 替换为 `generate_atmosphere_v2(scene_type, 1)`

**测试**: mock LLM 抛出异常，验证 fallback 的 atmosphere 来自 `generate_atmosphere_v2`

**工作量**: 小

---

#### P0-3：降级检测触发强制重试

**文件**: `src/fallback_strategy.py` + `src/game_master.py`

**改动**:
- `DegradationTracker`: `degradation_count >= alert_threshold(3)` 时发布 `DEGRADATION_RECOVERY_TRIGGERED` 事件
- `game_master.py`: 订阅该事件，收到后调用 `generate_scene(force_regenerate=True)` 重建场景

**逻辑**: 检测→告警→恢复 闭环，冷却期 3 回合防重复触发

**测试**: mock 连续 3 次 LLM 失败，验证场景被强制重建

**工作量**: 中

---

### P0 问题：战斗系统未激活

#### P0-4：修复"未知敌人"兜底敌人

**文件**: `src/game_master.py`

**改动**: `_check_combat_trigger()` + 新增 `SCENE_GENERIC_ENEMIES` 映射表

**逻辑**:
```python
SCENE_GENERIC_ENEMIES = {
    "森林": "森林狼",
    "洞穴": "洞穴蝙蝠",
    "酒馆": None,  # 酒馆不触发战斗
    "城镇": "流浪恶犬",
    "平原": "草原巨蟒",
    "城堡": "守卫骷髅",
    "河流": "河流鱼人",
}
# _extract_enemy_name 返回 None 时，从映射表取场景对应敌人
```

**测试**: 森林场景输入"攻击"（无具体敌人名），验证触发"森林狼"战斗

**工作量**: 小

---

### P0 问题：系统命令全部失效

#### P0-5：游戏内系统命令内联检测

**文件**: `src/game_master.py`

**改动**: `_handle_exploration_input()` 新增命令分支 + 实现 `_cmd_*` 方法

**逻辑**:
```python
SYSTEM_COMMANDS = {
    "查看状态": self._cmd_status,
    "状态": self._cmd_status,
    "背包": self._cmd_bag,
    "查看背包": self._cmd_bag,
    "商店": self._cmd_shop,
    "任务": self._cmd_quest,
}
# 在 _handle_exploration_input 开头检测，匹配则调用对应方法
```

`_cmd_status` → 返回玩家 HP/金币/状态；`_cmd_bag` → 背包物品列表；`_cmd_shop` → 商店信息；`_cmd_quest` → 任务进度

**测试**: 输入"查看状态"，验证返回状态信息而非万能敷衍

**工作量**: 中

---

### P1 问题：酒馆场景自相矛盾

#### P1-1：Fallback tier 按场景类型设最低要求

**文件**: `src/fallback_strategy.py`

**改动**: `get_fallback_scene()` 增加场景类型最低 tier 映射

**逻辑**:
```python
SCENE_MIN_TIER = {
    "酒馆": FallbackTier.MEDIUM,  # 必须有 NPC
    "城镇": FallbackTier.MEDIUM,
    "村庄": FallbackTier.MEDIUM,
    "森林": FallbackTier.LIGHT,
    "洞穴": FallbackTier.LIGHT,
    "平原": FallbackTier.LIGHT,
    "河流": FallbackTier.LIGHT,
}
# tier = max(复杂度对应 tier, SCENE_MIN_TIER.get(scene_type, LIGHT))
```

MEDIUM+ tier fallback 预置 NPC（如酒馆→酒馆老板）

**工作量**: 中

---

#### P1-2：修复 `interactive_master` 中文命令路由

**文件**: `interactive_master.py`

**改动**: 主循环命令路由

**逻辑**:
```python
stripped = player_input.strip()  # 不再用 .lower() 处理中文
# 英文命令保留 .lower()
if stripped in ("quit", "exit", "q"):
    # ...
if stripped in ("查看状态", "状态", "status"):
    print_status(master.game_state)
```

**测试**: 传入 `"查看状态\r\n"`（带换行），验证正确匹配

**工作量**: 小

---

### 优先级排序与工作量

| 优先级 | 问题 | 改动文件 | 工作量 |
|-------|------|---------|-------|
| **P0-NEW** | NPC对话崩溃：`'str' object has no attribute 'value'` | `event_bus.py`, `npc_agent.py`, `game_master.py` | 中 |
| P0-1 | 万能敷衍循环：`_generate_main_narrative` 降级修复 | `game_master.py` | 小 |
| P0-2 | 万能敷衍循环：`generate_synopsis` fallback 改用 `generate_atmosphere_v2` | `scene_agent.py` | 小 |
| P0-3 | 降级不可逆：DegradationTracker 触发强制重试 | `fallback_strategy.py`, `game_master.py` | 中 |
| P0-4 | 战斗未激活："未知敌人"改为场景通用怪物 | `game_master.py` | 小 |
| P0-5 | 系统命令失效：游戏内命令内联检测 | `game_master.py` | 中 |
| P1-1 | 酒馆矛盾：Fallback tier 按场景类型设最低要求 | `fallback_strategy.py` | 中 |
| P1-2 | 系统命令失效：`interactive_master` 中文命令路由修复 | `interactive_master.py` | 小 |

**推荐实施顺序**: P0-NEW → P0-1 → P0-2 → P0-5 → P0-4 → P0-3 → P1-1 → P1-2
