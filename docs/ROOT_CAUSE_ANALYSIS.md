# AI DM RPG 体验问题根因分析报告

**根因师**: genyin（根因师 🔍）
**分析日期**: 2026-04-12
**方法论**: 5 Why 追问法
**报告类型**: 第二轮根因分析（2026-04-11 报告续篇）

---

## 概览

| 关键发现 | 描述 |
|---------|------|
| **综合评分** | 2.1/10（体验官）/ 3/10（2026-04-12报告） |
| **核心问题** | 第4回合后游戏核心循环断裂，所有输入返回万能敷衍文本或空响应 |
| **阻塞程度** | P0 - 游戏基本不可玩 |
| **根因层次** | 系统层（Fallback降级策略）+ 输入理解层（命令路由缺失） |

---

## 问题一：万能敷衍循环（第4回合后全面失效）

### 问题描述

从第4回合开始，所有玩家操作（查看状态、背包、道具、商店、战斗等）全部返回 **"空气中弥漫着XX气息"** 的万能敷衍回复。

**典型表现：**
- 第4回合输入："查看状态" → 输出：`[回合 N] 你说道："查看状态"\n\n空气中弥漫着XX的气息。`
- 第4回合输入："使用治疗药水" → 输出：同上格式，唯一的区别是XX的内容不同
- 第4回合输入："攻击NPC" → 输出：同样是万能敷衍，没有触发战斗

**根本不是"体验一般"，而是核心游戏循环完全失效。**

---

### 相关代码/模块

| 文件 | 关键方法 | 作用 |
|------|---------|------|
| `src/game_master.py` | `_generate_main_narrative()` | 每回合生成主叙事，输出万能敷衍模板 |
| `src/game_master.py` | `_handle_exploration_input()` | 探索模式输入处理，组合各handler结果 |
| `src/game_master.py` | `_check_scene_update()` | 检测是否需要场景切换 |
| `src/scene_agent.py` | `generate_scene()` | 四步场景生成流程 |
| `src/scene_agent.py` | `generate_atmosphere_v2()` | 动态生成氛围（未生效） |
| `src/fallback_strategy.py` | `get_fallback_scene()` | LLM失败时的降级场景 |
| `src/minimax_interface.py` | `generate()` | LLM API调用 |

---

### 数据流追踪

```
玩家输入 → handle_player_message()
  → EventBus.publish(PLAYER_INPUT)
  → _on_player_input()
    → _handle_exploration_input()
      → _check_scene_update() → 返回 None（未检测到场景切换）
      → _check_npc_interaction() → 返回 None（无NPC关键词或scene无NPC）
      → _check_object_interaction() → 返回 None（scene无objects）
      → _check_combat_trigger() → 返回 None（无战斗关键词）
      → _generate_main_narrative() → **生成万能敷衍**
    → EventBus.publish(NARRATIVE_OUTPUT)
  → interactive_master 接收叙事
```

**关键路径分析：**

`_generate_main_narrative()` 的输出逻辑：
```python
# 第1-3回合（LLM正常工作）：atmosphere = LLM生成的有意义内容
# → 输出差异化的氛围描述

# 第4回合+（LLM降级）：atmosphere = synopsis_data.get("atmosphere", "mysterious")
# → "mysterious" → "空气中弥漫着mysterious的气息"
# → 每次回合相同，因为 current_scene.atmosphere 固定不变
```

---

### 5 Why 追问

**Why 1: 为什么第4回合后所有输入都返回万能敷衍？**

→ 因为 `_generate_main_narrative()` 每次输出相同的模板文本。

**Why 2: 为什么 `_generate_main_narrative()` 输出相同的万能文本？**

→ 因为 `atmosphere` 字段值固定为 "mysterious"（降级占位符），且 `_generate_main_narrative` 每次构造相同的模板：
```python
scene_details.append(f"空气中弥漫着{atmosphere}的气息")
base_narrative += "，".join(scene_details) + "。"
```

**Why 3: 为什么 atmosphere 固定为 "mysterious"？**

→ 当 `generate_synopsis()` LLM调用失败时，`synopsis_data` 使用硬编码占位符：
```python
synopsis_data = {
    "atmosphere": "mysterious",  # ← 固定占位符
    "synopsis": f"一个{scene_type}类型的地点:{requirements}",
    ...
}
```
这个 "mysterious" 被存入 `scene.atmosphere`，后续所有回合都复用它。

**Why 4: 为什么 `generate_synopsis()` LLM调用失败？**

→ 场景生成需要4次LLM调用（差异化定位→纲要→详细内容×N），任意一次失败都可能触发降级。更关键的是：即使单次失败，整个场景质量大幅下降。Rate limiting（429错误）或连续超时会导致连续降级。

**Why 5: 根本原因**

→ **Fallback降级策略不区分层次**：场景的 `atmosphere` 在 `generate_synopsis` 失败时硬编码为 "mysterious"，这是最低质量降级。更深层的问题是：**没有任何机制在检测到降级后主动尝试恢复高质量模式**。一旦降级，游戏永远处于降级状态。

---

### 根本原因

**Fallback降级不可逆 + 降级检测告警机制存在但未有效触发恢复**

`DegradationTracker` 记录降级次数（alert_threshold=3），但：
1. 只记录，不触发任何恢复动作
2. 降级后的场景被当作正常场景继续使用
3. `generate_atmosphere_v2()` 可以生成动态氛围（无需LLM），但 `_generate_main_narrative` 没有调用它

---

### 修复方向建议

| 优先级 | 修复点 | 具体方案 |
|--------|--------|---------|
| P0 | `_generate_main_narrative` | 调用 `generate_atmosphere_v2()` 动态生成氛围，而非读固定字段 |
| P0 | `generate_synopsis` fallback | fallback时调用 `generate_atmosphere_v2()` 而非硬编码 "mysterious" |
| P0 | 降级检测后强制重试 | DegradationTracker连续3次降级后，强制重置 `current_scene` 并重新生成 |
| P1 | `_check_scene_update` 关键词 | 扩展关键词（如"看状态"="查看状态"），避免误判 |
| P1 | 连续失败检测 | 2次连续LLM失败后，发送告警事件，通知外部（飞书/日志） |

---

## 问题二：战斗系统未激活

### 问题描述

玩家主动发出攻击指令（"攻击NPC"、"挥拳"）时，没有任何战斗事件触发，输出仍然是万能敷衍文本。

---

### 相关代码/模块

| 文件 | 关键方法 | 作用 |
|------|---------|------|
| `src/game_master.py` | `_check_combat_trigger()` | 检测战斗触发关键词 |
| `src/game_master.py` | `_enter_combat()` | 进入战斗 |
| `src/combat_system.py` | `CombatSystem` | 战斗逻辑核心 |

---

### 数据流追踪

```
玩家输入 "攻击NPC" 
  → _handle_exploration_input()
    → _check_scene_update() → None
    → _check_npc_interaction() → None（无NPC关键词）
    → _check_object_interaction() → None
    → _check_combat_trigger() 
      → 检查 attack_keywords ["攻击", "打", "砍", "揍", "打怪", "战斗"]
      → "攻击NPC" 包含 "攻击" ✓
      → 调用 _extract_enemy_name() → 从 enemy_names 列表匹配
      → enemy_names = ["哥布林", "龙", "狼", "骷髅", "史莱姆", "巨魔", ...]
      → "NPC" 不在列表中 → enemy_name = None
      → 返回 {"trigger": "aggressive", "enemy_data": {"name": "未知敌人"}, ...}
    → _enter_combat({"name": "未知敌人"}) 
      → 创建战斗 → 触发战斗事件
```

**理论上战斗应该触发**。但实际体验报告说战斗未触发，说明可能的问题：

1. `_check_combat_trigger` 成功检测到攻击意图
2. 但 `_enter_combat` 因为 `enemy_name = "未知敌人"` 创建了一个没有实际数据的敌人
3. 战斗可能立即结束或没有有效输出

**更可能的原因**：第4回合后游戏整体降级，连 `_check_combat_trigger` 的结果都被 `_generate_main_narrative` 的万能敷衍覆盖了。

---

### 5 Why 追问

**Why 1: 为什么攻击NPC没有战斗事件？**

→ 攻击检测关键词 "攻击" 被 `_check_scene_update` 或 `_check_npc_interaction` 拦截了？实际上不会，因为检查顺序是：scene_update → npc → object → combat_trigger。

**Why 2: 为什么战斗未输出有意义内容？**

→ 战斗生成了，但输出的是万能敷衍模板。`_enter_combat` 成功后，`_handle_exploration_input` 的 `narrative_parts` 包含了战斗叙事 + `_generate_main_narrative` 的万能敷衍，最终输出是组合结果。但如果是降级模式，`_generate_scene` 可能失败了，战斗无法初始化。

**Why 3: 为什么战斗初始化失败？**

→ 如果 `_check_combat_trigger` 返回 `{"name": "未知敌人"}` 但EnemyFactory无法创建"未知敌人"类型的敌人，`_enter_combat` 可能抛异常或返回空。

**Why 4: 根本原因**

→ **"未知敌人"不在敌人注册表中**：`EnemyFactory.create_enemy("未知敌人")` 找不到匹配，返回 None 或默认敌人，战斗无法正常开始。同时，`_extract_enemy_name` 的敌人名称列表不包含"NPC"、"老板"、"小女孩"等，泛化的"攻击+目标"组合会得到"未知敌人"。

---

### 修复方向建议

| 优先级 | 修复点 | 具体方案 |
|--------|--------|---------|
| P0 | `_extract_enemy_name` | 扩展敌人名称列表，或实现通用"未知敌人"兜底 |
| P0 | `_check_combat_trigger` | 当攻击关键词存在但无明确敌人时，生成一个通用敌人（如"森林中的怪物"） |
| P1 | `_enter_combat` 异常处理 | 当敌人创建失败时，提供fallback战斗体验（不崩溃） |
| P1 | 战斗叙事fallback | 战斗叙事生成失败时，使用模板叙事而非空 |

---

## 问题三：系统命令全部失效

### 问题描述

"查看状态"、"查看背包"、"使用治疗药水"、"去商店" 等系统命令全部返回空响应或万能敷衍文本，无法提供玩家应有的系统信息。

**体验官反馈**：新手会完全迷茫，不知道游戏是否还在运行。

---

### 相关代码/模块

| 文件 | 关键行 | 作用 |
|------|--------|------|
| `interactive_master.py` | 790-793 | 系统命令路由（理论上在主循环处理） |
| `game_master.py` | `_handle_exploration_input()` | 游戏命令处理 |

---

### 数据流追踪

**理论路径（interactive_master.py）：**
```
玩家输入 "查看状态"
  → cmd = player_input.lower() = "查看状态"
  → cmd == "status" ❌
  → cmd in ["查看状态", "状态"] ✓
  → print_status(master.game_state)
  → continue（跳过handle_player_message）
```

**实际路径（推测）：**
```
玩家输入 "查看状态"
  → cmd = player_input.lower() = "查看状态"
  → cmd == "status" ❌
  → cmd in ["查看状态", "状态"] ❌（Windows GBK编码问题，lower()行为异常？）
  → 未匹配任何系统命令
  → await master.handle_player_message("查看状态")
    → _check_scene_update()：无场景关键词，返回None
    → _check_npc_interaction()："查看"是examine关键词，尝试找NPC
    → _check_object_interaction()：当前场景无objects，返回None
    → _check_combat_trigger()：无战斗关键词
    → _generate_main_narrative()：输出万能敷衍
  → print(万能敷衍)
```

---

### 5 Why 追问

**Why 1: 为什么系统命令返回万能敷衍而非系统信息？**

→ 因为系统命令没有被 `interactive_master` 的 `cmd` 路由捕获，直接进入了游戏主循环。

**Why 2: 为什么 cmd 路由没有捕获系统命令？**

→ `cmd = player_input.lower()` 在Windows环境下处理中文可能有编码问题。`"查看状态".lower()` 的结果是否等于 "查看状态" 取决于Python运行环境的locale设置。

**Why 3: 为什么 lower() 可能失效？**

→ 在Windows GBK/CP936环境下，中文字符的 `.lower()` 可能产生意外结果（虽然理论上中文没有大小写之分，但PowerShell/cmd的编码转换可能影响字符串比较）。

**Why 4: 根本原因**

→ **中文命令匹配依赖精确的字符串比较，没有任何规范化或模糊匹配**。同时，游戏主循环 `_handle_exploration_input` 没有对"系统命令类"输入做专门处理，全部进入通用叙事生成流程。

---

### 修复方向建议

| 优先级 | 修复点 | 具体方案 |
|--------|--------|---------|
| P0 | 系统命令路由 | 命令匹配前先做 strip() + 去除空白，不要依赖 lower() 对中文的处理 |
| P0 | 游戏内系统命令 | 在 `_handle_exploration_input` 中添加系统命令检测（查看状态、背包、商店等）作为独立分支 |
| P1 | 命令模糊匹配 | 用 `in` 或 `startswith` 做部分匹配，不要精确字符串比较 |
| P1 | 帮助系统 | 当输入无法识别时，自动显示可用命令列表 |

---

## 问题四：酒馆场景自相矛盾

### 问题描述

进入酒馆场景后，出现以下自相矛盾的描述序列：
1. "这里是一个酒馆"（酒馆场景）
2. "这里似乎没有人"（NPC交互结果）
3. "没有值得探索的"（万能敷衍）

---

### 5 Why 追问

**Why 1: 为什么酒馆场景自相矛盾？**

→ 酒馆场景生成使用了fallback（LLM调用失败），fallback场景的NPC列表为空或不完整。

**Why 2: 为什么NPC列表为空？**

→ Fallback tier = LIGHT（复杂度评分 < 50）时，`get_fallback_scene` 返回 `npcs = []`。酒馆场景的LIGHT fallback没有NPC。

**Why 3: 为什么复杂度评分为LIGHT？**

→ 复杂度 = synopsis长度 + requirements长度。Fallack synopsis = `f"一个{scene_type}类型的地点:{requirements}"`，只有约20字符，评分 < 50。

**Why 4: 根本原因**

→ **Fallback tier选择只看复杂度，不考虑场景类型**。酒馆是一个需要NPC的社交场景，LIGHT tier（无NPC）对于酒馆来说质量太差。即使是fallback，酒馆也应该有基本的NPC配置（如酒馆老板）。

---

### 修复方向建议

| 优先级 | 修复点 | 具体方案 |
|--------|--------|---------|
| P0 | Fallback tier选择 | 根据场景类型决定最低tier：酒馆/城镇最低MEDIUM（有NPC），洞穴/森林可LIGHT |
| P1 | NPC强制注入 | Fallback场景如果有quest_active，强制注入1个与任务相关的NPC |

---

## 问题五：任务提示不更新

### 问题描述

所有操作后都重复显示"镇中心似乎有人聚集"，没有根据玩家位置和动作动态调整。

---

### 5 Why 追问

**Why 1: 为什么任务提示不更新？**

→ `quest_hint` 来自 `quest_state.get_stage_hint(current_location=current_location)`，但 `current_location` 的值固定为场景的 `type` 字段，没有根据玩家实际位置更新。

**Why 2: 根本原因**

→ **任务提示的动态调整逻辑依赖 `current_scene.type`，但没有根据玩家输入的意图做二次调整**。当玩家说"去酒馆"但场景还在生成中时，任务提示仍显示旧位置的提示。

---

## 跨问题的系统性根因

通过以上5 Why分析，所有问题指向三个系统层根因：

### 根因 A: LLM降级不可逆，无恢复机制

**表现**：
- 5个P0空响应全部发生在LLM降级后
- 一旦进入降级模式，游戏永久处于低质量状态
- `DegradationTracker` 有检测但无恢复动作

**机制**：
```
LLM调用失败 → Fallback tier选择 → 硬编码占位符存入scene →
current_scene固定 → 每回合读固定值 → 万能敷衍循环
```

**为什么第1-3回合正常**：
- 初始场景生成可能使用正常LLM
- 随着playtest运行，LLM调用增多，rate limit/tout累积
- 第4回合触发降级阈值，之后永久降级

---

### 根因 B: 输入理解层缺少命令路由

**表现**：
- 系统命令没有专门的处理路径
- 所有输入都进入通用叙事生成流程
- 边缘动作（发呆、撞墙）没有有意义的响应

**机制**：
```
玩家输入 → 关键字猜测 → 场景/NPC/物品/战斗 检测
→ 全返回None → _generate_main_narrative（万能敷衍）
```

---

### 根因 C: Fallback tier选择只看复杂度，不看场景语义

**表现**：
- 酒馆场景fallback到LIGHT（无NPC），质量严重不足
- NPC/战斗类场景需要MEDIUM+ tier，但fallback可能选择了LIGHT

---

## 根因层次图

```
┌─────────────────────────────────────────────────────────────┐
│ 体验层：2.1/10 综合评分，P0问题5个                           │
└────────────────────────────┬────────────────────────────────┘
                             │
┌────────────────────────────▼────────────────────────────────┐
│ 功能层：万能敷衍循环 + 战斗未激活 + 系统命令失效               │
│ - _generate_main_narrative: 固定模板输出                      │
│ - _check_combat_trigger: "未知敌人"兜底失败                   │
│ - interactive_master: 中文命令匹配失败                         │
└────────────────────────────┬────────────────────────────────┘
                             │
┌────────────────────────────▼────────────────────────────────┐
│ 数据层：current_scene 降级后永久固化                          │
│ - atmosphere = "mysterious" (hardcoded fallback)              │
│ - npcs = [] (LIGHT tier fallback)                             │
│ - 无动态更新机制                                              │
└────────────────────────────┬────────────────────────────────┘
                             │
┌────────────────────────────▼────────────────────────────────┐
│ LLM层：LLM调用失败触发降级，但无恢复路径                       │
│ - generate_synopsis 失败 → 硬编码占位符                        │
│ - generate_detail 失败 → 降级tier（但tier选择只看复杂度）        │
│ - DegradationTracker: 有检测无恢复                            │
└────────────────────────────┬────────────────────────────────┘
                             │
┌────────────────────────────▼────────────────────────────────┐
│ 架构层：缺失 降级恢复机制 + 命令路由层 + 边缘动作处理           │
└─────────────────────────────────────────────────────────────┘
```

---

## 建议优先级总览

| 优先级 | 根因 | 对应问题 | 修复难度 |
|--------|------|---------|---------|
| P0 | `_generate_main_narrative` 调用 `generate_atmosphere_v2` | 万能敷衍循环 | 低 |
| P0 | Fallback synopsis 使用 `generate_atmosphere_v2` 而非硬编码 | 万能敷衍循环 | 低 |
| P0 | Fallback tier按场景类型设置最低要求 | 酒馆自相矛盾 | 低 |
| P0 | 游戏内系统命令检测 | 系统命令失效 | 中 |
| P0 | "未知敌人"兜底敌人类型 | 战斗未激活 | 低 |
| P0 | DegradationTracker触发强制重试 | 降级不可逆 | 中 |
| P1 | 中文命令路由的编码规范化 | 系统命令失效 | 低 |
| P1 | 边缘动作（发呆、撞墙）的fallback叙事 | 空响应 | 低 |
| P1 | 连续LLM失败告警 | 降级不可逆 | 低 |

---

## 参考文件

- 体验报告：`experience_report_20260412.md`
- 体验数据：`agents/玩家/playtest_results.json`
- 队列任务：`workspace-ai-dm-rpg/tasks/queue.md`
- 第一轮分析：`docs/ROOT_CAUSE_ANALYSIS.md`（2026-04-11）

---

*根因师 genyin 🔍 | 2026-04-12*

---

## 最新根因分析（2026-04-12 第二轮）

> **背景**：无新增体验报告；对 TECH_PROPOSAL 修复方案进行根因回推，挖掘"方案本身"的盲区。

---

### 问题 P0-1：万能敷衍循环（追问版）

**5 Why 深问（方案层回推）**

| Why | 追问 | 回答 |
|-----|------|------|
| Why 1 | 为什么 atmosphere 固化？ | `_generate_main_narrative` 依赖 `current_scene.atmosphere`，降级时被硬编码为 `"mysterious"` |
| Why 2 | 为什么会硬编码？ | `generate_synopsis` LLM 失败后 fallback 直接写死 `"mysterious"`，无动态生成路径 |
| Why 3 | 为什么 fallback 不调用 `generate_atmosphere_v2`？ | 架构上 fallback 路径从未连接 `generate_atmosphere_v2`；后者只在正常流程中存在 |
| Why 4 | 为什么没有设计这个连接？ | 开发者误判 `generate_atmosphere_v2` 也依赖 LLM，不知道它是确定性函数 |
| Why 5 | 为什么不知道？ | `generate_atmosphere_v2` 无内部注释，方案A强调"调用该函数替代硬编码"——说明这个盲区在设计阶段就存在 |

**新发现**：TECH_PROPOSAL 方案A-1 的改动范围"只改一个方法"是正确的，但忽略了 `generate_atmosphere_v2` 本身是否被正确理解。真正的根因不是"没有调用它"，而是"fallback 路径从未被设计成可以调用它"——这是架构层缺失。|

---

### 问题 P0-2：系统命令全部失效（追问版·修正）

> ⚠️ **重要修正**：现有文档（第一轮分析）将系统命令失效归因于 `lower()` 对中文无效——**这是错误的**。Python 3 中 `str.lower()` 对中文字符返回相同字符串（`"查看状态".lower() == "查看状态"` 返回 `True`）。真正的问题是命令列表本身不完整。

**实际代码追踪**（`interactive_master.py`）：
```python
cmd_lower = player_input.lower()

if player_input in ["quit", "exit", "退出", "q"] or cmd_lower in ["quit", "exit", "q"]:
    # ... exit

if player_input in ["help", "帮助", "h", "?"] or cmd_lower in ["help", "h", "?"]:
    # ... help

if player_input in ["状态", "status"] or cmd_lower == "status":   # ← "查看状态" 不在这里
    print_status(master.game_state)
    continue

# "查看状态" 未匹配上述任何分支 → 落到游戏输入处理 → 触发万能敷衍
await master.handle_player_message(player_input)
```

**5 Why 深问（重新分析）**

| Why | 追问 | 回答 |
|-----|------|------|
| Why 1 | 为什么"查看状态"返回万能敷衍？ | `"查看状态"` 不在系统命令匹配列表中，未被识别为系统命令 |
| Why 2 | 为什么命令列表不完整？ | 命令列表只包含 `["状态", "status"]`，漏掉了"查看状态"这一常见表述 |
| Why 3 | 为什么漏掉？ | 开发者编写命令列表时只覆盖了最简形式，没有枚举所有等效表达 |
| Why 4 | 为什么没有枚举测试？ | 缺乏等价类测试用例——英文命令有完整列表，中文变体被视为"同义词"未单独处理 |
| Why 5 | 为什么同义词不处理？ | 历史上以英文命令为主，中文是后期追加；命令匹配逻辑采用精确匹配而非语义匹配 |

**验证**：`python -c "s='查看状态'; print(s.lower() == '查看状态')"` → `True`

**关键修正**：第一轮根因分析错误地将 `lower()` 归为罪魁祸首。真正的根因是两层叠加：
1. **命令列表不完整**：`"查看状态"`、`"查看背包"` 等变体未被枚举
2. **fallback 兜底失效**：未匹配命令进入游戏循环后，GameMaster 的 `_check_system_command` 同样使用 `text in (...)` 精确匹配，且匹配列表同样不完整（见 `game_master.py` 第 674-706 行）

**系统性共性问题补充**：中文命令支持不是"加了 `lower()` 就能用"，而是要建立**命令变体枚举 + 模糊匹配**机制。这是TECH_PROPOSAL P1-2方案（CI/CD中文测试）的根本盲区——它测了 `lower()`，但没有测试**变体覆盖度**。|

---

### 问题 P0-NEW：0438 定时自动体验·100%空响应（深度分析）

**问题描述**（来自 `tiyanguan_cron_report_20260412_0438.md`）：
- 游玩时长：57秒，19个动作，100%空响应（0字）
- 所有动作（教程跳过/NPC对话/战斗/系统命令/边界输入）全部返回0字符
- 上一轮体验报告（01:50，约294秒）尚有正常叙事输出
- 两次体验时间差约3小时，评分从 5.9/10 跌至 0.0/10

**关键异常**：上一次体验（01:50）游戏尚可运行，3小时后再次体验（04:38）游戏完全失效。**这是崩塌而非退化。**

**5 Why 深度追问**

| Why | 追问 | 回答 |
|-----|------|------|
| Why 1 | 为什么 100% 的动作都返回空响应？ | `NARRATIVE_OUTPUT` 事件的数据字段为空，或事件从未被发布 |
| Why 2 | 为什么事件数据为空？ | `_handle_exploration_input` 返回了空字符串，或 `_on_player_input` 异常未捕获 |
| Why 3 | 为什么会返回空字符串？ | 场景 agent 的 registry 未正确初始化 → `get_atmosphere_count` 抛 AttributeError → 所有后续叙事短路 |
| Why 4 | 为什么 registry 未初始化？ | `SceneAgent(scene_agent)` 在 `GameMaster.__init__` 中创建时，`self.registry` 可能为 `None` 且未做空检查 |
| Why 5 | 为什么没有空检查？ | 开发者假设 registry 必然被创建（`registry or SceneRegistry()`），但未考虑初始化顺序依赖导致的竞态条件 |

**备选 Why 2（事件未发布）**：

| Why | 追问 | 回答 |
|-----|------|------|
| Why 2a | 为什么事件未发布？ | `_on_player_input` 中的异常被 `try/except` 吞掉，静默跳过事件发布 |
| Why 3a | 为什么不抛出异常？ | 异常被 `except Exception as e: logger.error(...)` 吞没 → 游戏继续运行但不产生输出 |
| Why 4a | 为什么 logger.error 不足以发现问题？ | 错误日志写入了但测试脚本不读取日志，只看事件输出 → 开发者不知道发生了什么 |
| Why 5a | 为什么测试只看事件输出？ | 测试框架和日志系统独立开发，输出通道没有对齐；无端到端告警机制 |

**最可能的根因路径**（按可能性排序）：

**路径A（高概率）：场景初始化竞态**
```
GameMaster.__init__ → SceneAgent() 创建 → self.scene_agent 未设置
→ _handle_exploration_input 访问 self.scene_agent.registry
→ AttributeError: 'NoneType' has no attribute 'registry'
→ 异常被吞 → 返回空字符串 → NARRATIVE_OUTPUT 数据为空
```

**路径B（中等概率）：随机初始化失败**
```
new_game() → generate_scene() → scene_agent.registry 为 None
→ registry.get_atmosphere_count() → AttributeError
→ 降级到 atmosphere="mysterious" → 但如果 atmosphere 写入也失败
→ current_scene 为空 dict → _generate_main_narrative 输出空
```

**路径C（低概率）：事件订阅竞态**
```
玩家输入 → EventBus.publish(PLAYER_INPUT)
→ 但 _on_player_input 尚未注册（异步订阅未完成）
→ 事件丢失 → NARRATIVE_OUTPUT 从未发布 → 脚本等待超时
```

**与 P0-1 万能敷衍循环的关键区别**：

| 维度 | P0-1 万能敷衍循环 | P0-NEW 100%空响应 |
|------|------------------|------------------|
| 表现 | 有输出，但质量差 | 完全没有输出 |
| 根因 | atmosphere 固化 | 场景系统崩溃（事件/初始化） |
| 机制 | 降级后读固定字段 | 初始化失败导致所有操作异常 |
| 恢复难度 | 低（动态生成可修复） | 高（需要完整的初始化检查） |

**修复方向建议**：

| 优先级 | 修复项 | 关键改动 |
|--------|--------|---------|
| P0 | **添加 SceneAgent 和 SceneRegistry 的空检查** | `_handle_exploration_input` 和 `_generate_main_narrative` 中访问 registry 前做 `if self.scene_agent and hasattr(self.scene_agent, 'registry')` 检查 |
| P0 | **添加初始化完成标志** | `new_game()` 等待 `scene_agent` 和 `registry` 完全初始化后再接受玩家输入 |
| P0 | **异常重新抛出（不吞没）** | `_on_player_input` 中捕获的异常应重新抛出或写入带外通道（飞书/邮件告警） |
| P1 | **添加启动完整性检查** | `initialize()` 中验证所有核心组件（registry/event_bus/llm）非空 |
| P1 | **测试脚本增加日志监控** | tiyanguan_cron 脚本同时监控日志文件和事件输出，任一异常都报告 |

---

### 问题 P1-1：酒馆场景自相矛盾（追问版）

**5 Why 深问（方案层回推）**

| Why | 追问 | 回答 |
|-----|------|------|
| Why 1 | 为什么酒馆 fallback 到 LIGHT（无NPC）？ | `get_fallback_scene()` tier 选择只看输入复杂度，不看场景类型 |
| Why 2 | 为什么不看场景类型？ | fallback 逻辑设计时，场景类型没有被当作决策参数 |
| Why 3 | 为什么没有设计？ | 开发者假设 fallback 是"降级到最简单版本"，没有考虑"降级后场景是否仍然有意义" |
| Why 4 | 为什么没有考虑？ | 酒馆等社交场景的 NPC 依赖性在设计时没有被识别为"fallback后损失最严重的场景属性" |
| Why 5 | 为什么没有被识别？ | 场景类型和 fallback 策略之间没有对应的矩阵文档；两者独立设计后未做交叉验证 |

**新发现**：方案P0-3（Fallback tier按场景类型设置最低要求）触碰到了问题表面，但未解决根因——**即使设置了最低要求，场景类型本身在 fallback 时没有被传入决策函数**。真正需要修复的是：让 `get_fallback_scene()` 接受 `scene_type` 参数，并在函数内部建立 scene_type → tier 的映射矩阵。|

---

### 问题 P1-2：任务提示不更新（追问版）

**5 Why 深问（方案层回推）**

| Why | 追问 | 回答 |
|-----|------|------|
| Why 1 | 为什么任务提示固定不变？ | `current_scene.type` 固化，任务提示依赖它做动态调整 |
| Why 2 | 为什么 `current_scene.type` 固化？ | 场景切换逻辑依赖 LLM 调用成功，降级后场景更新逻辑被跳过 |
| Why 3 | 为什么降级后跳过？ | `_check_scene_update()` 在降级状态下返回 False/None，不触发场景更新 |
| Why 4 | 为什么这样设计？ | 开发者假设降级状态是临时的，"跳过更新"比"强制更新"风险更低 |
| Why 5 | 为什么假设正确但实际相反？ | 降级在游戏中是永久的（见根因A），跳过更新导致玩家在错误的场景提示下游戏——比"强制更新到降级场景"体验更差 |

**新发现**：这个问题的根因和 P0-1（万能敷衍）共享同一根源——**降级不可逆导致整个游戏状态冻结**。任务提示不更新只是冰山一角，所有依赖 `current_scene` 动态性的功能在降级后全部失效。|

---

### 系统性共性问题（新发现）

**共性一："修复方案层"暴露了"架构层缺失"**

TECH_PROPOSAL 的所有方案都在解决"症状"或"局部设计"，没有解决"架构层为什么容许这些症状发生"。具体：
- 方案A修复了 `generate_atmosphere_v2` 的调用，但没有修复"为什么 fallback 路径从未设计过调用它"
- 方案P0-4修复了中文匹配，但没有修复"为什么没有命令意图识别层"
- 方案P0-3修复了 tier 映射，但没有修复"为什么 scene_type 在 fallback 时没有被传入"

**共性二：降级状态的"临时假设"导致所有缓兵之计全部失效**

所有针对降级状态的"优化"（跳过更新、降低期望、简化输出）都建立在"降级是临时的，很快会恢复"的假设上。但实际上：
- DegradationTracker 只检不恢复
- 降级触发后每回合都读固化字段
- 降级触发后所有动态逻辑被短路

**正确的架构假设应该是：降级是永久的，所有依赖动态性的功能必须具备在降级状态下继续工作的降级路径。**

**共性三：缺乏"降级场景语义完整性"概念**

酒馆场景 fallback 到 LIGHT 后"没有 NPC"——这不是 tier 问题，是**降级后场景失去了它存在的意义**。应该有"场景语义完整性检查"：每种场景类型在 fallback 时必须保留哪些核心属性，否则整个场景应该被替换为通用降级场景而不是当前场景的劣化版本。

**共性四：测试框架与游戏日志系统完全割裂**（来自 0438 报告分析）

0438 定时体验显示 100% 空响应，但测试脚本只监听事件总线（EventBus），不读取日志文件。游戏内部的 `logger.error` 写入了错误，但测试脚本完全看不见。**这意味着：游戏在后台崩溃，测试在外面喊"一切正常"。**

表现：
- `tiyanguan_cron_0412.py` 只订阅 `NARRATIVE_OUTPUT` 事件
- `game_master.py` 的 `_on_player_input` 捕获异常后只写 logger，不重新抛出
- 测试脚本等待 `narrative_ready` 事件超时 → 静默超时 → 返回 0 字符
- 开发者只能看到"超时"，无法知道后台发生了什么

根因：
- 测试框架（`tiyanguan_cron_*`）和日志系统（`src/logging_system.py`）是两条独立的数据流
- 没有端到端的告警机制——游戏崩溃不触发飞书/邮件通知
- 错误被"静默吞没"（catch-only-log-no-throw）成了标准模式

**正确的工程实践应该是：异常必须走带外通道（告警），不能只在日志里躺着。**

**共性五：中文命令测试的覆盖盲区**（来自 P0-2 修正分析）

第一轮分析错误地将系统命令失效归因于 `lower()` 对中文无效。真正的盲区是：**测试只验证了 `lower()` 的正确性，没有测试命令变体覆盖度**。

- 英文命令：`["quit", "exit", "q"]` —— 覆盖了所有常见变体
- 中文命令：`["状态", "status"]` —— **没有** `"查看状态"`、`"当前状态"`、`"人物状态"`

这不是 `lower()` 的问题，是**命令同义词枚举不完整**的问题。

---

## 更新的下一步修复建议（2026-04-12 第二轮·扩充）

> 新增项目标注 🆕；修正项目标注 ⚠️

| 优先级 | 修复项 | 根因层次 | 关键改动 |
|--------|--------|---------|---------|
| P0 | **架构：设计 fallback 路径的通用调用规范** | 架构层 | 所有 fallback 点必须能够调用 `generate_atmosphere_v2` 和其他确定性函数；制定规范防止未来新 fallback 点重蹈覆辙 |
| P0 | **架构：建立 scene_type → tier 映射矩阵** | 架构层 | `get_fallback_scene()` 必须接受 `scene_type` 参数；按场景类型设置 tier 下限（酒馆/战斗：MEDIUM+，探索：LIGHT） |
| P0 | **架构：设计命令意图识别层（CommandRouter）** | 架构层 | 所有输入先经过 CommandRouter 分类：系统命令 / 游戏命令 / 叙事输入；各走独立处理路径 |
| P0 | **降级：修复 DegradationTracker——加入恢复动作** | LLM层 | 连续 N 回合成功后应尝试恢复；恢复时从固化字段重新初始化场景对象 |
| P0 | **降级：建立"场景语义完整性检查"** | 功能层 | fallback 后验证核心属性是否存在；酒馆无 NPC 时提示玩家场景不可用而非显示空场景 |
| P0 🆕 | **初始化：添加 SceneAgent/SceneRegistry 空检查** | 架构层 | `_handle_exploration_input` 中访问 registry 前做 `if self.scene_agent and hasattr(...)` 检查；防止 AttributeError 导致静默崩溃 |
| P0 🆕 | **初始化：添加 GameMaster 启动完整性检查** | 架构层 | `initialize()` 验证所有核心组件（registry/event_bus/llm）非空；加入 `assert` 或显式告警 |
| P0 🆕 | **异常：`_on_player_input` 异常重新抛出** | 功能层 | 捕获的异常不应只写日志就吞没；应通过飞书/邮件等带外通道告警，或重新抛出阻止静默失败 |
| P0 🆕 | **测试：tiyanguan_cron 同时监控日志和事件** | 工程层 | 脚本同时订阅事件 + 监控日志文件；任一通道出现 ERROR 都立即报告 |
| P1 ⚠️ | **中文：枚举命令同义词而非修 `lower()`** | 输入层 | 重新评估：实际问题是 `"查看状态"` 不在命令列表，而非 `lower()` 失效；应枚举所有中文变体（"查看状态"、"当前状态"、"人物状态" 等） |
| P1 | **中文：CI/CD 加入中文命令变体覆盖度测试** | 工程层 | 不仅测 `lower()` 正确性，还要测等价表达式的枚举覆盖度 |
| P1 | **数据：给所有确定性函数加内部注释** | 文档层 | 特别是 `generate_atmosphere_v2`，注明"无LLM依赖、确定性、可在fallback路径安全调用" |
| P2 | **任务提示：降级状态下强制场景更新** | 功能层 | `_check_scene_update()` 在降级时不应返回 False；应更新到降级版场景描述并告知玩家 |
| P2 | **告警：建立端到端游戏健康状态监控** | 工程层 | GameMaster 崩溃或连续异常时，通过飞书机器人/邮件通知；不再依赖测试脚本来发现生产环境问题 |

---

## 根因层次全景图（第二轮更新）

```
┌─────────────────────────────────────────────────────────────────────────┐
│ 体验层：0.0/10（0438定时体验）~ 5.9/10（非定时体验）                     │
│ - 0438: 100%空响应，游戏完全不可用                                      │
│ - 其他: 万能敷衍 + 酒馆自相矛盾 + 命令失效                              │
└────────────────────────────┬──────────────────────────────────────────┘
                              │
┌────────────────────────────▼──────────────────────────────────────────┐
│ 功能层：事件发布失败 + 叙事生成失效                                      │
│ - 0438: AttributeError（registry未初始化）→ 异常被吞 → 静默空响应     │
│ - 其他: atmosphere固化 → 万能敷衍模板                                   │
│ - 命令: "查看状态"不在列表 → fallback到游戏循环 → 万能敷衍             │
└────────────────────────────┬──────────────────────────────────────────┘
                              │
┌────────────────────────────▼──────────────────────────────────────────┐
│ 架构层：三层缺失                                                        │
│ 1. Fallback路径无确定性函数调用规范（generate_atmosphere_v2从未连接）  │
│ 2. 命令路由层缺失（系统命令/游戏命令/叙事输入 全部走同一路径）         │
│ 3. 初始化完整性检查缺失（scene_agent.registry 可能为 None）             │
└────────────────────────────┬──────────────────────────────────────────┘
                              │
┌────────────────────────────▼──────────────────────────────────────────┐
│ 工程层：测试框架与日志系统割裂                                          │
│ - 测试只监听事件总线，看不见日志里的 ERROR                              │
│ - 异常静默吞没（catch-only-log）是标准模式                              │
│ - 无端到端告警机制 → 游戏在后台崩溃，外部不知道                        │
└─────────────────────────────────────────────────────────────────────────┘
```

---

*根因师 genyin 🔍 | 2026-04-12 第二轮 | 基于 TECH_PROPOSAL.md 方案层回推 + 0438定时体验报告深度分析*
