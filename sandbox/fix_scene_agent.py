#!/usr/bin/env python
"""Fix scene_agent.py by replacing broken fallback definitions with imports"""

# Read the original file
with open('src/scene_agent.py', 'r', encoding='utf-8') as f:
    content = f.read()

lines = content.split('\n')

# Lines 1-139 (before _FALLBACK_SCENES)
prefix_lines = lines[:139]

# Lines 302 onwards (after _DEFAULT_FALLBACK_SCENES ends at line 301)
suffix_lines = lines[302:]

# Build the replacement - import statement
import_statement = [
    "# Fallback scenes data - imported from fallback_data module",
    "from sandbox.fallback_data import _FALLBACK_SCENES, _DEFAULT_FALLBACK_SCENES",
    "",
]

# Combine
new_lines = prefix_lines + import_statement + suffix_lines

# Write the fixed file
with open('src/scene_agent.py', 'w', encoding='utf-8') as f:
    f.write('\n'.join(new_lines))

print(f"Fixed scene_agent.py: {len(lines)} -> {len(new_lines)} lines")
print(f"Removed lines 140-301 ({len(lines) - 302 + 1} lines)")
