# AGENTS.md - AI DM RPG 项目规范

_本文件定义项目级规范，所有 sub-agent 必须遵守。_

---

## 🚨 硬阻塞规则（立即上报奶咖）

遇到以下情况，**不重试、不等待、不标注"pre-existing"**，立即通过飞书通知奶咖：

| 阻塞类型 | 举例 |
|---------|------|
| API key / credentials 缺失 | MINIMAX_API_KEY 未配置 |
| 外部 API 连续 2+ 次失败 | MiniMax API 返回 400/500/timeout |
| 文件损坏或被删除 | 核心模块被删除或语法错误 |
| 任何 agent 无法凭空生成的资源 | 第三方服务认证信息 |

**注意**：标注"pre-existing"是错误做法——这是阻塞，不是"已知问题"。

---

## 📋 Cron 配置规范

新建或修改 Cron 时，**必须**使用以下 delivery 格式：

```json
"delivery": {
  "mode": "announce",
  "channel": "feishu",
  "to": "chat:oc_d9356436abe015afff28ef02f09eb420"
}
```

**禁止使用 `channel: "last"`** — 这在 direct chat 中无法解析，会导致 400 投递失败。

---

## 📁 项目路径约定

- **实际代码目录**：`C:/Users/15901/.openclaw/workspace/ai-dm-rpg/`
- **任务队列目录**：`C:/Users/15901/.openclaw/workspace-ai-dm-rpg/tasks/`
- **注意**：两个目录不同！代码在 `workspace/ai-dm-rpg/`，任务在 `workspace-ai-dm-rpg/tasks/`

---

## 🔄 任务循环机制

当任务队列为空时：
1. 读取 `PROJECT_STATE.md` 的「下一步（Next）」列表
2. 取出第一个未完成项作为新任务
3. 创建任务文件并执行
4. 完成后标记该项为已完成
5. 继续处理下一个

**不允许**：队列为空时停止循环。

---

## 重试规则

- Rate limit（429）→ 本轮跳过，下轮重试，不累计失败次数
- 其他失败 → 累计失败计数
- 连续失败 3 次 → 标记为「阻塞」，上报奶咖
- 成功后重置失败计数

---

## 质量指标

| 指标 | 目标 |
|------|------|
| 情绪张力 | 玩家情绪跌宕起伏 |
| 可重玩性 | 每局体验差异化 |
| 受众广度 | 吸引不同类型玩家 |

**时间节点**：
- 4/15：核心架构搭完 ✅
- 4/22：子 Agent 集成 ✅
- 4/30：MVP 跑通，完整流程可玩
