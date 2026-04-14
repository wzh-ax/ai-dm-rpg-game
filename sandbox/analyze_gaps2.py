import sys
sys.path.insert(0, '.')
from src.game_master import GameMaster
import inspect

lines = inspect.getsource(GameMaster).split('\n')

# Lines 770-780
output = ['Lines 770-780:']
for i in range(769, 781):
    if i < len(lines):
        output.append(f'{i+1}: {repr(lines[i][:80])}')

# Lines 783-860 (first 50 lines)
output.append('\nLines 783-833:')
for i in range(782, 833):
    if i < len(lines):
        output.append(f'{i+1}: {repr(lines[i][:80])}')

with open('sandbox/gap_analysis2.txt', 'w', encoding='utf-8') as f:
    f.write('\n'.join(output))
print('Done')
