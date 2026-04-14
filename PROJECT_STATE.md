# AI DM RPG - 项目状态

_由珂宝自主维护，每次心跳时更新_

## 目标

**质量指标（核心目标）：**
1. 情绪张力：玩家情绪跌宕起伏
2. 可重玩性：每局体验差异化
3. 受众广度：吸引不同类型玩家

**时间节点（新规划）：**
- 4/15：核心架构搭完 ✅ 已完成
- 4/22：子 Agent 集成 ✅ 已完成
- **4/18：MVP 验收**（提前12天）
- **4/25：体验打磨**（场景差异化、难度模式、多结局分支）

**新里程碑：体验打磨（4/18 - 4/25）**

| 目标 | 优先级 | 描述 |
|------|--------|------|
| 场景差异化增强 | P0 | 每局场景生成真正随机化，减少模板感 |
| 多结局分支 | P0 | 玩家选择影响剧情走向 |
| 难度模式 | P1 | 简单/普通/困难三档 |
| 受众广度 | P2 | accessibility、新手引导分层 |

---

## 当前里程碑

**Milestone: 核心架构搭建**
目标：Event Bus + Main DM 运行起来，空跑无报错
截止：2026-04-15

---

## 任务队列

### 下一步（Next）
- [x] **【P0-1】动态氛围替代硬编码**：`_generate_main_narrative` 改调 `generate_atmosphere_v2()` ✅ (10:56)
- [x] **【P0-2】Fallback atmosphere 动态化**：`generate_synopsis` fallback 改用 `generate_atmosphere_v2` ✅ (11:05)
- [x] **【P0-3】降级恢复机制**：`DegradationTracker` 连续3次降级触发强制场景重建 ✅ (11:05)
- [x] **【P0-5】系统命令内联分支**：游戏内系统命令在 `_handle_exploration_input` 中内联处理 ✅ (11:30)
- [x] **【P1-1】Fallback tier 场景语义**：按场景类型设最低 tier（酒馆≥MEDIUM） ✅ (11:35)
- [x] **【P1-2】中文命令编码修复**：`interactive_master` 命令路由移除 `.lower()` ✅ (11:25)
- [ ] **【P0-n】NPC对话崩溃修复**：事件传递链路修复 `'str' has no attribute 'value'`（体验官第二轮新发现）
- [ ] **【P1-n】系统命令一致性**：同一命令有时有效有时无效

### 已完成（Done）
- [x] 任务系统 UX 改善（探索模式任务 HUD + 战斗模式技能列表 + 场景叙事融入任务线索 + Tutorial 后首个场景改善）
- [x] 受众广度（accessibility + 新手引导分层）（伤害数字着色、状态Emoji、教程三模式）
- [x] 场景差异化增强
- [x] 多结局分支
- [x] 难度模式

### 进行中（In Progress）
- [x] **体验官体验报告**（完成，综合评分 2/10，发现新 P0 Bug）

### 已完成（Done）
- [x] 打通场景→探索流程（场景生成后如何进入探索模式，场景如何和 GameMaster 对接）
- [x] 存档系统设计与实现（JSON 文件持久化玩家状态）
- [x] 设计文档完成（14 个设计文档）
- [x] 架构确定（双层 Agent + Event Bus + Hook）
- [x] MVP 目标确认
- [x] 项目基础结构搭建（Python 项目 + pyproject.toml）
- [x] Event Bus 核心实现（asyncio 异步事件总线）
- [x] Main DM Agent 实现（接收输入→分发→叙事输出）
- [x] Hook 机制实现（输入/输出前后触发点）
- [x] 空跑测试通过（EventBus + MainDM + Hook 联动）
- [x] Scene Agent 实现（四步场景生成流程 + SceneRegistry）
- [x] SceneAgent 单元测试通过
- [x] MiniMax API 接入（Anthropic Messages API 格式，测试全通过）
- [x] NPC Agent 实现（四步 NPC 生成流程 + NPCRegistry + 对话缓存）
- [x] NPC Agent 单元测试通过（9/9 passed）
- [x] 核心记忆机制实现（分层记忆 + RAG 检索 + 持久化）
- [x] Memory Manager 单元测试通过（16/16 passed）
- [x] 战斗系统实现（先攻排序 + 回合流程 + 命中/伤害判定 + 状态效果）
- [x] Combat System 单元测试通过（19/19 passed）
- [x] 道具/物品系统实现（Item + ItemRegistry + InventoryManager + 默认物品模板）
- [x] Item System 单元测试通过（37/37 passed）
- [x] **子 Agent 集成完成**（GameMaster 协调器 + Hook + EventBus 接入）
- [x] **GameMaster 叙事生成接入 LLM**（MiniMax 生成沉浸式 DM 叙事 + NPC Agent 接入）
- [x] **探索→战斗模式切换完善**（HP条 + 敌人反击 + 差异化敌人属性 + 沉浸式战斗叙事）
- [x] **LLM 战斗叙事生成**（_generate_combat_narrative + 敌人反击 LLM 叙事）
- [x] **战斗后场景恢复**（探索→战斗→探索状态延续 + LLM 恢复叙事）
- [x] **战斗动作 LLM 叙事完整性**（防御/技能/道具/逃跑全动作 LLM 叙事 + CombatSystem 集成）
- [x] **NPC 对话深度联动**（NPCAgent 完整接入 + 场景 NPC 跟踪 + 多轮对话连贯性）
- [x] **战斗奖励系统**（XP/金币/掉落物品/升级 + LLM奖励叙事生成）
- [x] **完整的游戏流程演示**（run_master.py 演示脚本完善，完整冒险流程可运行）
- [x] **战斗机制完善**（WAIT延迟动作修复 + 战术性敌人AI + 难度缩放 + 玩家HP同步 + 技能系统丰富化 + 敌人逃跑系统）
- [x] **玩家输入适配**（interactive_master.py 实现真正的玩家交互，替换硬编码演示脚本）
- [x] **角色创建系统**（CharacterCreator 模块：种族/职业/名字选择、属性自动分配、背景故事生成）
- [x] **角色创建单元测试**（25/25 passed）
- [x] **新手冒险引导系统**（TutorialSystem 模块：世界观简介、操作说明、新手任务引导）
- [x] **新手引导单元测试**（21/21 passed）
- [x] **入口脚本重构**（interactive_master.py 支持全新游戏/继续游戏双入口，集成角色创建和教程）
- [x] **任务系统 MVP**（src/quest_state.py + game_master.py 集成 + interactive_master.py 自动激活 + 26个单元测试）
- [x] **敌人种类扩展**（森林巨魔分裂、暗影盗贼偷袭、沼泽毒蟾中毒特殊能力 + 攻击加成修复）
- [x] **装备系统集成**（equipment_system.py + 战斗加成应用 + 逃跑成功率加成 + 92测试通过）
- [x] **场景可交互物品系统**（scene_objects.py + scene_agent.py 集成 + game_master.py 物品交互 + 27测试通过）

### 阻塞（Blocked）
- None

---

## 体验问题修复（来源：genyin 根因分析 2026-04-12）

### 根因分析（2026-04-12 新一轮）
| 优先级 | 问题 | 根因 |
|--------|------|------|
| P0 | **万能敷衍循环** | LLM降级后 `atmosphere = "mysterious"` 固化，`_generate_main_narrative` 每次输出相同模板 |
| P0 | **NPC对话崩溃** | `_on_player_input` 中字符串当枚举调用 `.value`，NPC ID 未正确传递 | 🔍 新发现（体验官第二轮）|
| P0 | **系统命令不稳定** | 同一输入有时有效有时无效，命令路由缺乏防御性检查 | 🔍 新发现（体验官第二轮）|
| P0 | **战斗系统未激活** | 攻击"未知敌人"（NPC不在敌人注册表）导致战斗初始化失败 | ✅ 已修复（P0-4）|
| P0 | **系统命令全部失效** | Windows中文环境下 `lower()` 字符串匹配失效，命令误入游戏主循环 |
| P1 | 酒馆场景自相矛盾 | Fallback tier=LIGHT（无NPC），不适合酒馆这类社交场景 |
| P2 | 任务提示不更新 | `current_scene.type` 固定，未根据玩家实际位置动态调整 |

### 系统性根因（跨问题共性）
1. **LLM降级不可逆** — `DegradationTracker` 有检测无恢复，降级后永久低质量
2. **无命令路由层** — 所有输入走通用叙事生成，边缘动作无fallback叙事
3. **Fallback tier只看复杂度** — 不考虑场景语义，酒馆/战斗类场景降级质量不足

### 修复任务（下一步 Next）

- [ ] **【P0-1】动态氛围替代硬编码**：`_generate_main_narrative` 改调 `generate_atmosphere_v2()` 替代硬编码 atmosphere
- [ ] **【P0-2】Fallback atmosphere 动态化**：`generate_synopsis` fallback 改用 `generate_atmosphere_v2` 替代硬编码 "mysterious"
- [ ] **【P0-3】降级恢复机制**：`DegradationTracker` 连续3次降级触发强制场景重建
- [ ] **【P0-5】系统命令内联分支**：游戏内系统命令在 `_handle_exploration_input` 中内联处理，不走 LLM
- [ ] **【P1-1】Fallback tier 场景语义**：按场景类型设最低 tier（酒馆≥MEDIUM）
- [ ] **【P1-2】中文命令编码修复**：`interactive_master` 命令路由移除 `.lower()`

### 第一轮根因分析（2026-04-11，已完成）
| 优先级 | 问题 | 状态 |
|--------|------|------|
| P0 | NPC 场景状态继承丢失 | ✅ 已修复 |
| P0 | 叙事 AI 自爆 | ✅ 已修复 |
| P0 | 系统命令空响应 | ✅ 已修复（P0-5 为更深层修复）|
| P0 | 环境描写机械重复 | ✅ 已修复（Atmosphere 动态生成）|

### 建议优先级（第一轮）
- **P0**：统一 `scene.npcs` 与 `active_npcs` 数据源 ✅
- **P0**：requirements 参数隔离，不直接暴露给 LLM ✅
- **P0**：关键字匹配逻辑收窄，避免误触发场景切换 ✅
- **P1**：Fallback 场景质量提升 + 不持久化 ✅
- **P1**：Atmosphere 动态生成机制 ✅

---

## 项目笔记

### 技术决策
- 语言：Python 3.12+
- LLM 接口：MiniMax（Anthropic Messages API，`https://api.minimaxi.com/anthropic`）
- 事件总线：asyncio（已实现 + 空跑通过）
- 项目管理：pyproject.toml + hatchling

### MiniMax API 详情
- Base URL: `https://api.minimaxi.com/anthropic`
- API 格式: Anthropic Messages API
- 模型: `MiniMax-M2.7`（推理模型，返回 thinking + text blocks）
- 测试覆盖: 简单对话、差异化定位、场景纲要、详细内容生成

### 风险
- ~~Python 并发/异步经验不足，可能需要额外调研~~（已解决：asyncio 实践）
- ~~MiniMax API 接口细节未知，需要实测~~（已解决：测试全通过）

### 依赖
- Python 3.11+ ✓（当前 3.12.9）

---

## 最后更新时间
2026-04-12 20:27 GMT+8（体验官第二轮完成，发现新P0 Bug，已生成第三轮任务）
- 所有 P0/P1 任务已完成（10:25~13:05）
- 根因分析完成（13:05）→ docs/ROOT_CAUSE_ANALYSIS.md
- 体验官已触发（18:36）
- 等待体验报告 → fangan 任务生成
- 任务系统 MVP：26 测试通过 ✓
- 角色创建系统：25 测试通过 ✓
- 新手引导系统：21 测试通过 ✓
- 入口脚本重构完成 ✓
- 场景可交互物品系统 ✓
- 任务系统 UX 改善 ✓
- Tutorial 后开场场景生成 ✓
