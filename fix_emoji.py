import os

emoji_map = {
    "🔍": "[INFO]",
    "✅": "[OK]",
    "❌": "[ERROR]",
    "⚠️": "[WARN]",
    "🧪": "[CHEM]",
    "🔬": "[LAB]",
    "📊": "[STATS]",
}

files_to_fix = [
    "agent.py",
    "database.py",
    "app.py",
]

def fix_emoji_in_file(filepath):
    if not os.path.exists(filepath):
        print(f"文件不存在: {filepath}")
        return False
    
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    original_content = content
    for emoji, replacement in emoji_map.items():
        content = content.replace(emoji, replacement)
    
    if content != original_content:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f"已修复: {filepath}")
        return True
    else:
        print(f"无需修复: {filepath}")
        return False

if __name__ == "__main__":
    print("开始修复 emoji 字符...")
    for filename in files_to_fix:
        fix_emoji_in_file(filename)
    print("修复完成！")