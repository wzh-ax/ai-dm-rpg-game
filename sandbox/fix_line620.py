import os
import codecs

os.chdir('C:/Users/15901/.openclaw/workspace/ai-dm-rpg')

# Read as text
with codecs.open('src/game_master.py', 'r', encoding='utf-8') as f:
    content = f.read()

# The line in question - find it by content
target_line = '玩家动作:{player_input}"'
replacement_line = '玩家动作:{player_input}'

if target_line in content:
    content = content.replace(target_line, replacement_line)
    print("Fixed!")
    with codecs.open('src/game_master.py', 'w', encoding='utf-8') as f:
        f.write(content)
    print("Written!")
else:
    print("Target line not found!")
    # Debug: find around 发生的事情
    idx = content.find('玩家动作')
    if idx >= 0:
        print(f"Context: {repr(content[idx:idx+50])}")
