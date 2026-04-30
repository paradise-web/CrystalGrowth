import requests

# 测试基本API
print("测试基本API...")
try:
    r = requests.get('http://localhost:8000/')
    print(f"成功! 状态码: {r.status_code}")
    print(f"响应: {r.text}")
except Exception as e:
    print(f"失败: {e}")

# 测试非流式聊天API
print("\n测试非流式聊天API...")
try:
    r = requests.post('http://localhost:8000/api/chat?query=什么是晶体生长')
    print(f"成功! 状态码: {r.status_code}")
    print(f"响应: {r.text}")
except Exception as e:
    print(f"失败: {e}")

# 测试流式聊天API
print("\n测试流式聊天API...")
try:
    r = requests.post('http://localhost:8000/api/chat/stream?query=什么是晶体生长', stream=True)
    print(f"成功! 状态码: {r.status_code}")
    content = ''
    for chunk in r.iter_content(chunk_size=1024):
        if chunk:
            content += chunk.decode('utf-8')
    print(f"响应: {content}")
except Exception as e:
    print(f"失败: {e}")

print("\n测试完成!")