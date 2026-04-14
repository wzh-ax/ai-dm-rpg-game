#!/usr/bin/env python
import sys
try:
    with open('src/scene_agent.py', 'r', encoding='utf-8') as f:
        lines = f.readlines()
    print(f'Total lines: {len(lines)}')
except Exception as e:
    print(f'Error: {e}')
    sys.exit(1)
