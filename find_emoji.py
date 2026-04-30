import re

# 读取文件
with open('agent.py', 'r', encoding='utf-8') as f:
    content = f.read()

# 查找所有 emoji 字符
emoji_pattern = re.compile(r'[\U00010000-\U0001ffff]')
emojis_found = set()

for i, line in enumerate(content.split('\n')):
    matches = emoji_pattern.findall(line)
    if matches:
        print(f"第 {i+1} 行: {matches} - {line[:100]}")
        emojis_found.update(matches)

print(f"\n找到的 emoji: {emojis_found}")