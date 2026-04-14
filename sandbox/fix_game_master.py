import os
import codecs

os.chdir('C:/Users/15901/.openclaw/workspace/ai-dm-rpg')

with codecs.open('src/game_master.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Find the problematic area - the f-string that starts with prompt = f"""
# and never properly closes
# The issue: "请以DM视角描述这个场景中正在发生的事情:"" followed by blank lines
# needs to be: "请以DM视角描述这个场景中正在发生的事情:""" followed by closing """

# Find the pattern: 发生的事情:"" then \r\n\r\n        \r\n\r\n        try:
# This should become: 发生的事情:"""\r\n        """ then \r\n        try:

# The exact bytes we need to find and replace
old_pattern = '事情:""\r\n\r\n        \r\n\r\n        try:'
new_pattern = '事情:"""\r\n        """\r\n        try:'

if old_pattern in content:
    print(f"Found pattern at byte {content.find(old_pattern)}")
    content = content.replace(old_pattern, new_pattern)
    with codecs.open('src/game_master.py', 'w', encoding='utf-8') as f:
        f.write(content)
    print("Fixed!")
else:
    print("Pattern not found, trying alternative...")
    # Try with just \n
    old_pattern2 = '事情:""\n\n        \n\n        try:'
    new_pattern2 = '事情:"""\n        """\n        try:'
    if old_pattern2 in content:
        print(f"Found pattern (unix) at byte {content.find(old_pattern2)}")
        content = content.replace(old_pattern2, new_pattern2)
        with codecs.open('src/game_master.py', 'w', encoding='utf-8') as f:
            f.write(content)
        print("Fixed (unix)!")
    else:
        print("Pattern not found!")
        # Debug: print around where we expect the issue
        idx = content.find('的事情:')
        if idx >= 0:
            print(f"Context around '的事情:': {repr(content[idx:idx+100])}")
