#!/usr/bin/env python
"""Find lines with actual newlines inside string literals"""
with open('src/scene_agent.py', 'r', encoding='utf-8') as f:
    content = f.read()

lines = content.split('\n')
for i, line in enumerate(lines, 1):
    # A line ending with Chinese punctuation and followed by a non-quote line is suspicious
    stripped = line.rstrip()
    if stripped.endswith(('。', '，', '：', '；')):
        if i < len(lines):
            next_line = lines[i]
            # If next line starts with whitespace but not a quote or comma, it's a continuation
            if next_line and next_line[0] == ' ' and not next_line.strip().startswith(('"', "'", ',', ']', ')', '}')):
                print(f"Line {i}: ends with punctuation, next line is continuation")
                print(f"  Current: {stripped[:60]}...")
                print(f"  Next: {next_line[:60]}...")
                print()
