# 修复重复的 save_experiment_to_db 函数定义

with open('app.py', 'r', encoding='utf-8') as f:
    content = f.read()

# 查找第一个函数定义的结束位置
first_def_start = content.find('def save_experiment_to_db')
if first_def_start == -1:
    print("未找到函数定义")
    exit(1)

# 找到第一个函数定义的结束
# 我们需要找到匹配的 closing brace
open_braces = 0
first_def_end = first_def_start
in_function = False

for i in range(first_def_start, len(content)):
    char = content[i]
    if char == '{':
        open_braces += 1
        in_function = True
    elif char == '}':
        open_braces -= 1
        if in_function and open_braces == 0:
            first_def_end = i + 1
            break

# 查找第二个函数定义
second_def_start = content.find('def save_experiment_to_db', first_def_end)
if second_def_start == -1:
    print("未找到重复的函数定义")
    exit(1)

# 找到第二个函数定义的结束
open_braces = 0
second_def_end = second_def_start
in_function = False

for i in range(second_def_start, len(content)):
    char = content[i]
    if char == '{':
        open_braces += 1
        in_function = True
    elif char == '}':
        open_braces -= 1
        if in_function and open_braces == 0:
            second_def_end = i + 1
            break

# 删除第二个函数定义
new_content = content[:second_def_start] + content[second_def_end:]

# 保存修改后的内容
with open('app.py', 'w', encoding='utf-8') as f:
    f.write(new_content)

print("已删除重复的函数定义")