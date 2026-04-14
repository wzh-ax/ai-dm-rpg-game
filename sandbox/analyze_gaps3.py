import sys
sys.path.insert(0, '.')
from src.game_master import GameMaster
import inspect

lines = inspect.getsource(GameMaster).split('\n')

# Find _check_system_command
for i, line in enumerate(lines):
    if 'def _check_system_command' in line:
        print(f'Found _check_system_command at line {i+1}')
        # Print next 30 lines
        for j in range(i, min(i+35, len(lines))):
            print(f'{j+1}: {repr(lines[j][:80])}')
        break

print()

# Find _check_npc_interaction
for i, line in enumerate(lines):
    if 'def _check_npc_interaction' in line:
        print(f'Found _check_npc_interaction at line {i+1}')
        for j in range(i, min(i+25, len(lines))):
            print(f'{j+1}: {repr(lines[j][:80])}')
        break
