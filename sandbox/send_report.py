#!/usr/bin/env python
import sys
sys.path.insert(0, '.')
from src.feishu_client import send_message

content = """【任务完成】Fallback 降级策略 P1

✅ 任务状态：已完成
⏱ 完成时间：2026-04-11 23:50 GMT+8

📋 验收结果：
- ✅ 失败类型分类清晰（5种类型）
- ✅ 3档Fallback场景质量保障（沉浸式中文）
- ✅ Fallback不持久化到SceneRegistry
- ✅ 降级模式玩家可见提示（⚠️警告）
- ✅ 单元测试覆盖（27个测试全通过）

📁 新增文件：
- src/fallback_strategy.py（共享策略模块）
- tests/test_fallback_strategy.py（27个单元测试）

📝 主要实现：
1. FailureType/FallbackTier 枚举
2. classify_exception() 异常分类
3. DegradationTracker 连续降级跟踪
4. 8场景×3档 Fallback内容（酒馆/森林/村庄/城镇/城堡/洞穴/平原/河流）

🔗 代码位置：
src/scene_agent.py（重构导入）
src/game_master.py（添加降级跟踪）
"""

try:
    send_message('oc_e1ceff2fe81e3c715c2f01af0e194b72', content)
    print('Report sent to Feishu!')
except Exception as e:
    print(f'Error sending report: {e}')
