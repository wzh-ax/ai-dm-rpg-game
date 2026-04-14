#!/usr/bin/env python
"""Fix multi-line strings in scene_agent.py"""

with open('src/scene_agent.py', 'r', encoding='utf-8') as f:
    content = f.read()

# We'll process line by line and fix strings that span multiple lines
lines = content.split('\n')
fixed_lines = []
i = 0
while i < len(lines):
    line = lines[i]
    
    # Check if this line ends with Chinese punctuation (indicating it might continue)
    stripped = line.rstrip()
    if stripped.endswith(('。', '，', '：', '；', '”', '』')):
        # Check if the next line looks like a continuation (starts with whitespace, not a quote)
        if i + 1 < len(lines):
            next_line = lines[i + 1]
            if next_line and next_line[0] == ' ' and not next_line.strip().startswith(('"', "'", ',', ']', ')', '}')):
                # This is a multi-line string - we need to merge them
                merged = line.rstrip()
                j = i + 1
                while j < len(lines):
                    cont_line = lines[j]
                    cont_stripped = cont_line.strip()
                    # Check if this continuation line should be merged
                    if cont_line[0] == ' ' and not cont_stripped.startswith(('"', "'", ',', ']', ')', '}')):
                        # Merge with \n
                        merged += '\\n' + cont_line.strip()
                        j += 1
                    else:
                        break
                fixed_lines.append(merged)
                i = j
                continue
    
    fixed_lines.append(line)
    i += 1

with open('src/scene_agent.py', 'w', encoding='utf-8') as f:
    f.write('\n'.join(fixed_lines))

print("Fixed!")
