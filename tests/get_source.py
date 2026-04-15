import sys
sys.path.insert(0, 'D:/ai-dm-rpg-game')
from src.game_master import GameMaster
import inspect

source = inspect.getsource(GameMaster.handle_player_message)
print(source)
