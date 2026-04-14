import sys
sys.path.insert(0, '.')
from src.game_master import GameMaster
import inspect

lines = inspect.getsource(GameMaster).split('\n')

output = []
for i in range(686, 740):
    if i < len(lines):
        output.append(f'{i+1}: {repr(lines[i][:80])}')

with open('sandbox/gap_analysis.txt', 'w', encoding='utf-8') as f:
    f.write('\n'.join(output))
print('Done')
