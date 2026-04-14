#!/usr/bin/env python
"""Fix multi-line strings in scene_agent.py"""

import re

with open('src/scene_agent.py', 'r', encoding='utf-8') as f:
    content = f.read()

lines = content.split('\n')
fixed_lines = []
i = 0

while i < len(lines):
    line = lines[i]
    
    # Check if this line ends with Chinese punctuation and is followed by non-structural content
    stripped = line.rstrip()
    
    # A line ending with Chinese full-stop punctuation and followed by a continuation
    if stripped.endswith(('。', '，', '：', '；')):
        # Check subsequent lines for continuation
        if i + 1 < len(lines):
            # Collect all continuation lines until we hit a structural line
            j = i + 1
            continuation_lines = []
            
            while j < len(lines):
                next_line = lines[j]
                next_stripped = next_line.strip()
                
                # Empty line or line starting with structural character
                if not next_stripped:
                    # Empty line - could be part of multi-line string
                    continuation_lines.append('')
                    j += 1
                elif next_line[0] in ' \t' and not next_stripped.startswith(('"', "'", ',', ']', ')', '}')):
                    # Continuation line (indented, not starting with quote/comma/bracket)
                    continuation_lines.append(next_stripped)
                    j += 1
                else:
                    # Structural line - stop
                    break
            
            # If we found continuation lines, merge them
            if continuation_lines:
                # Merge the current line with continuations
                merged_parts = [stripped]
                for cont in continuation_lines:
                    if cont:  # Non-empty continuation
                        merged_parts.append(cont)
                    else:  # Empty line (paragraph break)
                        merged_parts.append('')  # Will become \n\n
                
                merged = '\\n'.join(merged_parts)
                fixed_lines.append(merged)
                i = j
                continue
    
    fixed_lines.append(line)
    i += 1

with open('src/scene_agent.py', 'w', encoding='utf-8') as f:
    f.write('\n'.join(fixed_lines))

print(f'Processed {len(lines)} lines into {len(fixed_lines)} lines')
