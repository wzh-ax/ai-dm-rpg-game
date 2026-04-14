#!/usr/bin/env python
import sys
import os

# Add the project root to the path
sys.path.insert(0, os.getcwd())
sys.path.insert(0, os.path.join(os.getcwd(), 'src'))
sys.path.insert(0, os.path.join(os.getcwd(), 'sandbox'))

# Try importing via the package
try:
    from src.scene_agent import (
        _FALLBACK_SCENES, _DEFAULT_FALLBACK_SCENES,
        get_fallback_scene, FailureType, FallbackTier, DegradationTracker
    )
    print('All imports successful!')
    print('Scene types in _FALLBACK_SCENES:', list(_FALLBACK_SCENES.keys()))
    print('get_fallback_scene works:', get_fallback_scene is not None)
except Exception as e:
    print(f'Import error: {e}')
    
    # Try alternate approach
    print('\nTrying alternate approach...')
    from sandbox.fallback_data import _FALLBACK_SCENES as fbs, _DEFAULT_FALLBACK_SCENES as dfbs
    print('fallback_data imports work:', fbs is not None)
