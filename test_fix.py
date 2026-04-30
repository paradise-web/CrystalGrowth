import requests
import json

print("=== 测试任务列表 API ===")
try:
    response = requests.get('http://localhost:8000/api/tasks')
    print(f"状态码: {response.status_code}")
    data = response.json()
    print(f"任务数量: {len(data.get('tasks', []))}")
    print(f"响应: {json.dumps(data, ensure_ascii=False, indent=2)}")
except Exception as e:
    print(f"错误: {e}")

print("\n=== 测试上传图片 ===")
try:
    # 找一个测试图片
    files = {'file': open('img_data/MoS2.png', 'rb')}
    response = requests.post('http://localhost:8000/api/upload', files=files)
    print(f"状态码: {response.status_code}")
    data = response.json()
    print(f"响应: {json.dumps(data, ensure_ascii=False, indent=2)}")
except Exception as e:
    print(f"错误: {e}")

print("\n=== 再次测试任务列表 API ===")
try:
    response = requests.get('http://localhost:8000/api/tasks')
    print(f"状态码: {response.status_code}")
    data = response.json()
    print(f"任务数量: {len(data.get('tasks', []))}")
    if data.get('tasks'):
        print(f"第一个任务: {json.dumps(data['tasks'][0], ensure_ascii=False, indent=2)}")
except Exception as e:
    print(f"错误: {e}")

print("\n测试完成!")