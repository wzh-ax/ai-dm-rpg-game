# t_20260412_p1_template_abuse - 模板滥用与空响应修复

**问题来源**: 体验官报告 2026-04-12 下午场
**优先级**: P1
**创建时间**: 2026-04-12 20:27
**方案师状态**: 方案已存在于 TECH_PROPOSAL.md（第二轮方案）

## 问题描述
- **模板滥用**：20 次模板使用，最高频"空气中弥漫着 XX 气息"出现在几乎所有探索回复
- **空响应率 47%**：19 个动作中 9 个空响应（NPC 对话 3次、场景切换 1次、战斗触发 3次、边界输入 3次）
- **酒馆场景自相矛盾**："这里是一个酒馆"→"这里似乎没有人"→"没有值得探索的"

## 根因（来自第二轮根因分析）
- `_generate_main_narrative` 在降级状态下输出万能敷衍模板
- `atmosphere == "mysterious"` 固化，每次回合相同
- Fallback tier=LIGHT（无NPC），不适合酒馆社交场景

## 修复要求（参考 TECH_PROPOSAL 第二轮方案）
1. P0-1：`_generate_main_narrative` 调用 `generate_atmosphere_v2()` 动态生成氛围
2. P0-2：`generate_synopsis` fallback 改用 `generate_atmosphere_v2` 替代硬编码 "mysterious"
3. P0-3：降级恢复机制（DegradationTracker 连续3次降级触发强制场景重建）
4. P1-1：Fallback tier 按 scene_type 设最低要求（酒馆≥MEDIUM）

## 验收标准
- 连续生成3次同一地点类型应有明显差异的描述
- 空响应率降至 10% 以下
- 酒馆场景不再自相矛盾

## 当前状态
- [x] 方案分析完成
- [ ] 等待实施（实施者：待分配）
