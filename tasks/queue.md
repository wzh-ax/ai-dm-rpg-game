# 任务队列

## P0 任务

| 任务ID | 描述 | 状态 | 完成时间 |
|--------|------|------|----------|
| t_20260411_p0_env_repeat | 环境描写机械重复修复 | ✅ 已完成 | 2026-04-11 19:31 |
| t_20260412_p0_npc_crash | NPC对话崩溃修复（'str' has no attribute 'value'） | 📋 待领取 | — |

---

## P1 任务

| 任务ID | 描述 | 状态 | 完成时间 |
|--------|------|------|----------|
| t_20260411_p1_quest_hint_update | 任务提示位置更新修复 | ✅ 已完成 | 2026-04-11 19:35 |
| t_20260411_p1_structured_logging | 结构化日志系统 | ✅ 已完成 | 2026-04-12 12:40 |
| t_20260412_fangan_tech_proposal | 第二轮技术方案（基于根因分析第二轮） | ✅ 已完成 | 2026-04-12 13:11 |
| t_20260412_p1_syscmd_inconsistent | 系统命令一致性修复 | 📋 待领取 | — |
| t_20260412_p1_template_abuse | 模板滥用与空响应修复 | 📋 待领取 | — |
| t_20260412_p1_bug_002_active_combat | Bug #002 - 场景切换未重置 active_combat | ✅ 已完成 | 2026-04-12 23:19 |

---

## 任务详情

### t_20260411_p0_env_repeat - 环境描写机械重复

**问题**: 当前场景生成虽然用了 LLM，但不同场景的描写流于形式，缺乏真正差异化。

**修复方案**:
1. 强化 `generate_differentiation()` 的 prompt，强制要求至少 3 种感官通道的具体描写
2. 新增场景变体机制（酒馆→昏暗角落/热闹大厅/宁静包间等）
3. 将 core_concept 完整传递到 detail 步骤

**验收标准**:
- 连续生成3次同一地点类型应有明显差异的描述
- 场景描述包含独特的感官细节

**状态**: ✅ 已完成

---

### t_20260411_p1_quest_hint_update - 任务提示位置更新修复

**问题**: `get_stage_hint()` 是纯基于 QuestStage 的静态方法，玩家已在提示指向的地点时，提示仍重复描述该地点而非告知下一步动作。

**修复方案**:
1. `quest_state.get_stage_hint()` 增加 `current_location` 参数
2. hints 字典值改为 tuple: `(在正确地点时的提示, 前往该地点时的提示)`
3. `game_master` 在场景切换时传入 `scene_type` 作为 `current_location`

**验收标准**:
- 玩家在月叶镇接受任务后，提示应指向「镇中心」
- 玩家从镇中心去森林后，提示应更新为指向「击败影狼」或「返回镇中心」，而非「去镇中心」
- `pytest tests/test_quest_state.py -v` 确认测试通过

**状态**: ✅ 已完成（详见 `../t_20260411_p1_quest_hint_update.md`）

---

### t_20260411_p1_structured_logging - 结构化日志系统

**问题**: 游戏核心模块缺乏结构化日志，难以进行问题根因分析和方案分析。

**实现方案**:
1. 创建 `src/logging_system.py` 作为核心模块
2. 使用 `queue.Queue` + `QueueHandler` 实现异步安全的日志写入
3. 日志格式: `{timestamp} [{level}] [{module}] {message}`
4. 每次 `new_game()` 创建新的日志文件: `logs/game_{timestamp}.log`
5. 集成到 4 个核心模块: `game_master.py`, `combat_system.py`, `scene_agent.py`, `npc_agent.py`
6. 关键日志点: 场景切换、战斗开始/结束、NPC交互、LLM API调用(DEBUG)、异常/错误(ERROR)
7. `@log_call` 装饰器简化关键函数日志
8. `GameLogFilter` 敏感信息脱敏(API keys, passwords, tokens, emails)

**验收标准**:
- `pytest` 全量测试通过(不含新增测试的干扰)
- 日志文件正确生成并写入
- 日志格式结构化、可解析

**状态**: ✅ 已完成

---

### t_20260412_fangan_tech_proposal - 第二轮技术方案（基于根因分析第二轮）

**基于根因分析**: docs/ROOT_CAUSE_ANALYSIS.md（第二轮，2026-04-12）

**问题概览**:
- P0 万能敷衍循环（_generate_main_narrative 降级 + generate_synopsis fallback 硬编码）
- P0 系统命令全部失效（中文 lower() 失效 + 无命令路由层）
- P0 战斗未激活（"未知敌人"兜底敌人类型缺失）
- P1 酒馆场景自相矛盾（Fallback tier=LIGHT，无NPC）
- P1 任务提示不更新（降级状态场景更新被跳过）

**技术方案要点**:
- P0-1: _generate_main_narrative 检测降级状态，调用 generate_atmosphere_v2 替代硬编码
- P0-2: generate_synopsis fallback 改用 generate_atmosphere_v2
- P0-3: DegradationTracker 触发强制场景重建（降级恢复闭环）
- P0-4: "未知敌人" → 场景通用怪物映射表
- P0-5: 游戏内系统命令内联检测（_cmd_status 等）
- P1-1: Fallback tier 按 scene_type 设最低要求（酒馆≥MEDIUM）
- P1-2: interactive_master 中文命令不用 lower()

**推荐实施顺序**: P0-1 → P0-2 → P0-5 → P0-4 → P0-3 → P1-1 → P1-2

**状态**: ✅ 已完成（详见 ../docs/TECH_PROPOSAL.md 第二轮方案章节）

---

## 待领取任务

| 任务ID | 描述 | 优先级 |
|--------|------|--------|
| t_20260412_p0_npc_crash | NPC对话崩溃修复（'str' has no attribute 'value'） | P0 |
| t_20260412_p1_syscmd_inconsistent | 系统命令一致性修复 | P1 |
| t_20260412_p1_template_abuse | 模板滥用与空响应修复 | P1 |

---

### t_20260412_p0_npc_crash - NPC对话崩溃修复

**问题来源**: 体验官报告 2026-04-12 下午场
**优先级**: P0（阻塞级）

**问题**: 玩家第一次尝试与 NPC 对话时游戏直接崩溃，报错：`'str' object has no attribute 'value'`
```
Error in subscriber 'game_master' for event player_input: 'str' object has no attribute 'value'
NPC not found: None
```

**根因**: `event_bus.py` 中 `_on_player_input` 将字符串当作枚举类型调用了 `.value`；`npc_agent.py` 的 `_on_npc_dialogue` 收到 `npc_id=None`

**修复要求**:
1. 追踪 `'str' object has no attribute 'value'` 错误的真正来源
2. 修复 NPC ID 事件传递链路
3. 确保 NPC 对话不崩溃

**验收标准**: 与 NPC 对话不再崩溃；`pytest tests/ -x -q` 338+ 通过

**状态**: 📋 待领取

---

### t_20260412_p1_syscmd_inconsistent - 系统命令一致性修复

**问题来源**: 体验官报告 2026-04-12 下午场
**优先级**: P1

**问题**: 同一输入（"查看状态"、"查看背包"）有时有效有时无效，商店/任务命令本次运行中崩溃

**修复要求**:
1. 调查系统命令失效根本原因
2. 确保所有系统命令稳定可用
3. 添加防御性检查，避免命令路由崩溃

**验收标准**: 系统命令 100% 可用，不再崩溃

**状态**: 📋 待领取

---

### t_20260412_p1_template_abuse - 模板滥用与空响应修复

**问题来源**: 体验官报告 2026-04-12 下午场
**优先级**: P1

**问题**:
- 模板滥用：20次，最高频"空气中弥漫着 XX 气息"出现在几乎所有探索回复
- 空响应率 47%（19个动作中9个空响应）
- 酒馆场景自相矛盾

**根因**: `_generate_main_narrative` 降级状态输出万能敷衍模板；`atmosphere == "mysterious"` 固化

**修复要求**（参考第二轮 TECH_PROPOSAL）:
1. `_generate_main_narrative` 调用 `generate_atmosphere_v2()` 动态生成氛围
2. `generate_synopsis` fallback 改用 `generate_atmosphere_v2`
3. Fallback tier 按 scene_type 设最低要求（酒馆≥MEDIUM）
4. 降级恢复机制

**验收标准**: 连续3次同一地点描述有差异；空响应率降至 10% 以下

**状态**: 📋 待领取

---

### t_20260412_p1_bug_002_active_combat - Bug #002: 场景切换未重置 active_combat

**问题**: 场景切换后 `active_combat=True` 未被重置为 `False`，导致非战斗动作被当作战斗处理。

**根因**: `_generate_scene()` 在场景切换时更新了 `game_state["location"]` 但没有重置 `game_state["active_combat"]`。

**修复**: 在 `_generate_scene()` 的两个代码路径（fallback 和非 fallback）中，`self.game_state["location"] = scene_type` 之后添加 `self.game_state["active_combat"] = False`。

**修改文件**: `src/game_master.py`
- Fallback 路径：`game_state["location"]` 赋值后添加 `active_combat = False`
- 非 Fallback 路径：同样添加重置逻辑

**验收标准**: `pytest tests/bugs/test_bug_002_active_combat_reset.py -v` 全部 PASS

**状态**: ✅ 已完成
