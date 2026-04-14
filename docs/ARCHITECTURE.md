# AI DM RPG - 多 Agent 协作架构

## 概述

AI DM RPG 采用 **事件驱动的多 Agent 协作架构**，由一个主 Agent（珂宝）协调多个专业 Agent。

```
珂宝（主 Agent - 规划 + 协调）
│
├── 景绘（Scene Agent）     - 场景生成
├── 言者（Narrative Agent） - 叙事对话
├── 战策（Combat Agent）    - 战斗机制
├── 构师（Architecture Agent）- 架构工程
├── 智匠（AI Engineer）     - AI 工程
└── 审官（QA Agent）        - 质量验收
```

---

## Agent 职责边界

### 景绘（Scene Agent）

**职责：**
- 场景生成（四步法：差异化 → 纲要 → 细节 → 描述）
- 环境描述、地点细节、氛围
- 视觉元素、地点名称

**不负责：**
- NPC 对话（归言者）
- 战斗逻辑（归战策）
- 代码实现（归构师/智匠）

---

### 言者（Narrative Agent）

**职责：**
- NPC 对话生成
- 剧情走向设计
- 角色性格定义
- 世界观填充

**不负责：**
- 场景生成（归景绘）
- 战斗数值（归战策）
- 代码实现（归构师/智匠）

**可动态触发：**
- 需要场景时 → 触发景绘

---

### 战策（Combat Agent）

**职责：**
- 战斗机制设计（先攻、回合、动作）
- 技能效果设计
- 敌人属性（HP、AC、伤害）
- 数值平衡（伤害曲线、升级）

**不负责：**
- 叙事内容（归言者）
- 场景生成（归景绘）
- 代码实现（归构师/智匠）

**可动态触发：**
- 需要场景时 → 触发景绘
- 需要叙事时 → 触发言者

---

### 构师（Architecture Agent）

**职责：**
- EventBus 实现
- Hook 机制设计
- 模块接口定义
- 代码规范制定

**不负责：**
- 叙事内容（归言者）
- 战斗数值（归战策）
- AI 接入（归智匠）

---

### 智匠（AI Engineer）

**职责：**
- LLM 接入（MiniMax / 其他）
- Prompt 设计
- RAG / 记忆系统
- AI 生成策略

**不负责：**
- 叙事内容（归言者）
- 战斗数值（归战策）
- 架构实现（归构师）

---

### 审官（QA Agent）

**职责：**
- 单元测试设计与执行
- 集成测试验证
- 代码审查
- 平衡性验证（数值是否合理）
- 叙事质量抽查

**不负责：**
- 具体实现（归构师/智匠）
- 内容创作（归景绘/言者）

---

## 事件 Schema

### 核心事件

| 事件名 | 触发者 | 监听者 | 数据格式 |
|--------|--------|--------|---------|
| `scene.requested` | 言者/战策 | 景绘 | `{ scene_type, requirements, requester_id }` |
| `scene.generated` | 景绘 | 请求者 + 审官 | `{ scene_id, scene_type, description, atmosphere, tags }` |
| `narrative.requested` | 战策 | 言者 | `{ context, scene_id, requirements }` |
| `narrative.generated` | 言者 | 战策 + 审官 | `{ narrative_id, dialogue, characters, plot }` |
| `combat.design.requested` | 珂宝 | 战策 | `{ encounter_type, difficulty, context }` |
| `combat.ready` | 战策 | 审官 | `{ combat_id, mechanics, stats, balance_notes }` |
| `code.commit` | 构师/智匠 | 审官 | `{ files, commit_message, test_included }` |
| `test.passed` | 审官 | 珂宝 | `{ test_count, passed, failed, coverage }` |
| `test.failed` | 审官 | 珂宝 | `{ test_count, failures: [{ test, error }] }` |

### 事件通用字段

所有事件包含：
```json
{
  "event_id": "uuid",
  "timestamp": "ISO8601",
  "source_agent": "agent_name",
  "trace_id": "用于追踪完整流程"
}
```

---

## 协作模式

### 1. 计划触发（珂宝调度）

珂宝决定执行顺序，按计划链式触发：
```
珂宝 → 景绘 → 言者 → 战策 → 审官
```

### 2. 需求触发（动态调用）

Agent 在工作中按需触发其他 Agent：
```
言者工作中需要场景 → 触发景绘 → 返回结果 → 继续
战策工作中需要叙事 → 触发言者 → 返回结果 → 继续
```

### 3. 并行执行

珂宝决定可并行的任务：
```
景绘 ──┬──→ 言者（串行，景绘完成后言者开始）
       │
       └──→ 审官（并行，景绘完成即触发验收）
```

---

## 珂宝的协调职责

1. **任务分配** - 决定下一步做什么、指派给哪个 Agent
2. **进度追踪** - 维护项目状态，决定是否可以并行
3. **质量验收** - 接收审官的 test.passed / test.failed，决定是否继续
4. **干预权** - 任何时候可以介入，调整执行顺序或打回重做

---

## 当前状态

- [x] 架构文档（本文档）
- [x] 景绘 SOUL.md + AGENTS.md
- [x] 言者 SOUL.md + AGENTS.md
- [x] 战策 SOUL.md + AGENTS.md
- [x] 构师 SOUL.md + AGENTS.md
- [x] 智匠 SOUL.md + AGENTS.md
- [x] 审官 SOUL.md + AGENTS.md
- [ ] 飞书配置（待奶咖配置）
