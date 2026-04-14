# 地理/政治边界配置

> 定义哪些区域/势力存在，哪些不存在。LLM 生成内容时，Hook 层校验，涉及不存在区域的生成直接拒绝或重定向。

---

## 结构化边界（配置层）

```json
{
  "world": {
    "continents": ["mainland"],
    "exists_formally": true
  },
  "regions": {
    "northern_kingdom": {
      "exists": true,
      "danger_level": "high",
      "controlled_by": "kingdom_north",
      "description": "常年冰封的北境王国，民风彪悍"
    },
    "southern_islands": {
      "exists": false,
      "note": "目前无记录，LLM 不得主动生成此区域内容"
    }
  },
  "factions": [
    "kingdom_north",
    "kingdom_central",
    "mercenary_guild",
    "forest_tribes"
  ],
  "forbidden_zones": [
    "outer_plane",
    "celestial_realm"
  ]
}
```

---

## 层级说明

| 层级 | 存在状态 | 说明 |
|------|----------|------|
| 大陆 | 始终存在 | 只有一个大陆 |
| 区域（Region） | 配置决定 | 人工定义重要区域 |
| 地点（Location） | 动态生成 | 森林、建筑等，由 LLM 生成后可写入 canon |
| 事件（Event） | 动态生成 | 同样可写入 canon |

---

## 校验机制

当 LLM 生成的内容涉及 `regions` 或 `factions` 时：
1. **Hook 层拦截**：检查配置中 `exists` 字段
2. **不存在** → 返回拒绝或重定向提示
3. **存在** → 放行，允许继续生成

---

_最后更新：2026-03-30_
