import requests
import json

def test_stream_chat():
    """测试流式回复API"""
    print("=== 测试流式回复API ===")
    try:
        response = requests.post(
            'http://localhost:8000/api/chat/stream',
            params={'query': '什么是晶体生长'}
        )
        print(f"状态码: {response.status_code}")
        print(f"响应头: {response.headers}")
        print(f"响应内容: {response.text}")
        print("✅ 流式回复测试成功")
    except Exception as e:
        print(f"❌ 流式回复测试失败: {e}")

def test_chat():
    """测试非流式聊天API"""
    print("\n=== 测试非流式聊天API ===")
    try:
        response = requests.post(
            'http://localhost:8000/api/chat',
            params={'query': '晶体生长方法'}
        )
        print(f"状态码: {response.status_code}")
        print(f"响应头: {response.headers}")
        print(f"响应编码: {response.encoding}")
        result = response.json()
        print(f"响应内容: {json.dumps(result, ensure_ascii=False, indent=2)}")
        print("✅ 非流式聊天测试成功")
    except Exception as e:
        print(f"❌ 非流式聊天测试失败: {e}")

def test_upload():
    """测试图片上传API"""
    print("\n=== 测试图片上传API ===")
    try:
        # 使用测试图片
        test_image_path = 'd:/exp_dec/img_data/test1.jpg'
        with open(test_image_path, 'rb') as f:
            files = {'file': ('test1.jpg', f, 'image/jpeg')}
            response = requests.post(
                'http://localhost:8000/api/upload',
                files=files
            )
        print(f"状态码: {response.status_code}")
        print(f"响应头: {response.headers}")
        print(f"响应编码: {response.encoding}")
        result = response.json()
        print(f"响应内容: {json.dumps(result, ensure_ascii=False, indent=2)}")
        print("✅ 图片上传测试成功")
        return result.get('task_id')
    except Exception as e:
        print(f"❌ 图片上传测试失败: {e}")
        return None

def test_experiments():
    """测试获取实验记录API"""
    print("\n=== 测试获取实验记录API ===")
    try:
        response = requests.get('http://localhost:8000/api/experiments')
        print(f"状态码: {response.status_code}")
        print(f"响应头: {response.headers}")
        print(f"响应编码: {response.encoding}")
        result = response.json()
        print(f"记录数量: {len(result.get('experiments', []))}")
        if result.get('experiments'):
            first_exp = result['experiments'][0]
            print(f"第一条记录标题检查: {first_exp.get('image_filename', '')}")
            markdown = first_exp.get('formatted_markdown', '')
            if markdown:
                print(f"Markdown内容预览(前100字符): {markdown[:100]}...")
        print("✅ 获取实验记录测试成功")
    except Exception as e:
        print(f"❌ 获取实验记录测试失败: {e}")

if __name__ == '__main__':
    test_stream_chat()
    test_chat()
    test_upload()
    test_experiments()