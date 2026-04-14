import inspect
import sys
sys.path.insert(0, '.')
from src.game_master import GameMaster

source = inspect.getsource(GameMaster.handle_player_message)
print(source)
