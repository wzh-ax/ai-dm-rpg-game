# -*- coding: utf-8 -*-
import sys
sys.path.insert(0, 'D:/ai-dm-rpg-game')
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

import asyncio
from src.minimax_interface import MiniMaxInterface

async def test():
    print("Testing MiniMax API...")
    i = MiniMaxInterface()
    try:
        r = await i.generate("用一句话描述月叶镇的酒馆氛围")
        print(f"Result: {r[:200] if r else 'NONE'}")
    except Exception as e:
        print(f"Error: {e}")

asyncio.run(test())
