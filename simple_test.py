import requests
import time

print("等待服务器启动...")
time.sleep(2)

try:
    print("测试流式API...")
    response = requests.post('http://localhost:8000/api/chat/stream', params={'query': 'test'})
    print(f"状态码: {response.status_code}")
    print(f"内容: {response.text}")
except Exception as e:
    print(f"错误: {e}")