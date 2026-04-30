import re

# 读取文件
with open('agent.py', 'r', encoding='utf-8') as f:
    content = f.read()

# 定义所有需要替换的 emoji
emoji_map = {
    '\U0001f4da': '[INFO]',  # 📚
    '\U0001f507': '[TOOL]',  # 🔧
    '\U0001f4e5': '[IN]',    # 📥
    '\u26a0': '[WARN]',       # ⚠️
    '\u2705': '[OK]',         # ✅
    '\u274c': '[ERROR]',      # ❌
    '\U0001f9ea': '[CHEM]',   # 🧪
    '\U0001f52c': '[LAB]',    # 🔬
    '\U0001f4ca': '[STATS]',  # 📊
}

# 替换所有 emoji
original_length = len(content)
for emoji, replacement in emoji_map.items():
    content = content.replace(emoji, replacement)

# 如果有变化，保存文件
if len(content) != original_length:
    with open('agent.py', 'w', encoding='utf-8') as f:
        f.write(content)
    print(f"已修复 agent.py 中的 emoji")
else:
    print("agent.py 中没有需要修复的 emoji")