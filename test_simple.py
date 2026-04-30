import requests

print("测试简单API...")
try:
    response = requests.get('http://localhost:8000/')
    print(f"GET / : {response.status_code} - {response.text}")
except Exception as e:
    print(f"GET / 错误: {e}")

print("\n测试非流式聊天API...")
try:
    response = requests.post('http://localhost:8000/api/chat?query=什么是晶体生长')
    print(f"POST /api/chat : {response.status_code}")
    print(f"响应内容: {response.text[:500]}")
except Exception as e:
    print(f"POST /api/chat 错误: {e}")