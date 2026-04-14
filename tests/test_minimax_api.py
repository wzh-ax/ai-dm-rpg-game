"""测试 MiniMax API 集成"""
import asyncio
import sys
import os

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.minimax_interface import MiniMaxInterface

# 设置 UTF-8 输出
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

# MiniMax API Key (from OpenClaw config)
MINIMAX_API_KEY = "sk-cp-BdEBZiMM2Bcjo0vEPQ0YErUWcR3mXadL_arR4YiYUWizLIYqG0_3J0DinqfTRT-oVIJye7XcZGSSOjgGIaAcXnmeyEQoAijRGfcUNVJARW7dx1fA1c0qKT4"


async def test_minimax_api():
    """测试 MiniMax API 调用"""
    print(f"API Key: {MINIMAX_API_KEY[:20]}...")
    
    llm = MiniMaxInterface(api_key=MINIMAX_API_KEY)
    
    try:
        # Test 1: 简单对话
        print("\n[Test 1] Simple chat...")
        result = await llm.generate(
            prompt="Say hello in exactly 3 words",
            system="You are a helpful assistant.",
            max_tokens=100,
        )
        print(f"Result: {result[:200]}")
        
        # Test 2: 场景差异化
        print("\n[Test 2] Scene differentiation...")
        diff = await llm.generate_differentiation(
            scene_type="forest",
            existing_tags=["dark", "haunted", "ancient"],
            new_requirements="A forest with magical properties"
        )
        print(f"Differentiation: {diff[:200]}")
        
        # Test 3: 场景纲要
        print("\n[Test 3] Scene synopsis...")
        synopsis = await llm.generate_synopsis(
            core_concept="A forest where trees whisper secrets of the past",
            scene_type="forest"
        )
        print(f"Synopsis atmosphere: {synopsis.get('atmosphere')}")
        print(f"Synopsis danger_level: {synopsis.get('danger_level')}")
        print(f"Synopsis tags: {synopsis.get('tags')}")
        
        # Test 4: 详细内容
        print("\n[Test 4] Scene detail...")
        detail = await llm.generate_detail(
            synopsis="玩家走进一片被月光笼罩的森林，树木高大茂密。",
            scene_type="forest",
            atmosphere="神秘而宁静"
        )
        print(f"NPCs: {[n.get('name') for n in detail.get('npcs', [])]}")
        print(f"Events: {[e.get('type') for e in detail.get('events', [])]}")
        
        print("\n[PASS] All tests passed!")
        return True
        
    except Exception as e:
        print(f"\n[FAIL] Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        await llm.close()


if __name__ == "__main__":
    result = asyncio.run(test_minimax_api())
    sys.exit(0 if result else 1)
