#!/usr/bin/env python
"""Fix multi-line strings in scene_agent.py by replacing actual newlines with \n"""

with open('src/scene_agent.py', 'r', encoding='utf-8') as f:
    content = f.read()

lines = content.split('\n')
fixed_lines = []
i = 0

while i < len(lines):
    line = lines[i]
    
    # Check if this line might be part of a multi-line string
    # A string that needs fixing ends with Chinese punctuation and is followed by content
    stripped = line.rstrip()
    
    if stripped.endswith(('。', '，', '：', '；', '"')):
        # Check if next line continues the string
        if i + 1 < len(lines):
            next_line = lines[i + 1]
            
            # If next line is empty (just whitespace), it's likely a blank line in the string
            if next_line.strip() == '':
                # This is a blank line inside a multi-line string - merge it
                current_string = stripped
                j = i + 2  # Skip the blank line
                
                while j < len(lines):
                    cont_line = lines[j]
                    cont_stripped = cont_line.strip()
                    
                    # Check if this is still a continuation
                    if not cont_stripped:
                        # Still a blank line - include it and continue
                        current_string += '\\n\\n'
                        j += 1
                    elif cont_line[0] == ' ' and not cont_stripped.startswith(('"', "'", ',', ']', ')', '}')):
                        # Merge with escaped newline
                        current_string += '\\n' + cont_stripped
                        j += 1
                    else:
                        break
                
                fixed_lines.append(current_string)
                i = j
                continue
            elif next_line and next_line[0] == ' ' and not next_line.strip().startswith(('"', "'", ',', ']', ')', '}')):
                # This is a multi-line string that needs fixing
                current_string = stripped
                j = i + 1
                
                while j < len(lines):
                    cont_line = lines[j]
                    cont_stripped = cont_line.strip()
                    
                    # Check if this is still a continuation
                    if cont_line[0] == ' ' and cont_stripped and not cont_stripped.startswith(('"', "'", ',', ']', ')', '}')):
                        # Merge with escaped newline
                        current_string += '\\n' + cont_stripped
                        j += 1
                    else:
                        break
                
                fixed_lines.append(current_string)
                i = j
                continue
    
    fixed_lines.append(line)
    i += 1

with open('src/scene_agent.py', 'w', encoding='utf-8') as f:
    f.write('\n'.join(fixed_lines))

print(f"Processed {len(lines)} lines into {len(fixed_lines)} lines")
