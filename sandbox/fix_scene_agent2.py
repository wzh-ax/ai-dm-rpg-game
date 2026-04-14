#!/usr/bin/env python
"""Fix scene_agent.py by replacing duplicate fallback definitions with proper import"""

with open('src/scene_agent.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Find the first occurrence of the fallback section marker
first_marker = content.find('# ============================================================================\n# Fallback 降级策略')
if first_marker == -1:
    print('Could not find first fallback marker')
    exit(1)

# Find the end of the first fallback section - look for the random opening templates marker
random_opening_marker = content.find('# ============================================================================\n# 随机开场模板', first_marker)
if random_opening_marker == -1:
    print('Could not find random opening marker')
    exit(1)

# Get the content before the fallback section
prefix = content[:first_marker]

# Get the content after the fallback section (skip the duplicate fallback definitions)
# Find the second fallback marker and start from after the random opening templates
second_marker_start = content.find('# ============================================================================\n# Fallback 降级策略', first_marker + 1)
if second_marker_start != -1:
    # There's a second occurrence - skip to after it
    # Find where the random opening templates section is after the second marker
    second_random_opening = content.find('# ============================================================================\n# 随机开场模板', second_marker_start)
    if second_random_opening != -1:
        suffix = content[second_random_opening:]
    else:
        suffix = content[second_marker_start:]
else:
    suffix = content[random_opening_marker:]

# Create the replacement import
import_statement = """# ============================================================================
# Fallback 降级策略 - 从 fallback_strategy 模块导入
# ============================================================================

from .fallback_strategy import (
    FailureType,
    FallbackTier,
    classify_exception,
    should_fallback,
    should_retry,
    DegradationTracker,
    get_fallback_scene,
    _FALLBACK_SCENES,
    _DEFAULT_FALLBACK_SCENES,
)

"""

# Combine
new_content = prefix + import_statement + suffix

with open('src/scene_agent.py', 'w', encoding='utf-8') as f:
    f.write(new_content)

print(f'Fixed scene_agent.py')
print(f'Prefix: {len(prefix)} chars')
print(f'Suffix: {len(suffix)} chars')
print(f'New content: {len(new_content)} chars')
