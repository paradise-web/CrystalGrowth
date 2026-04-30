import requests
import sys

def test_streaming_api():
    url = 'http://localhost:8000/api/chat/stream'
    params = {'query': '什么是晶体生长'}
    
    print("测试流式API...")
    try:
        response = requests.post(url, params=params, stream=True)
        response.raise_for_status()
        
        print(f"状态码: {response.status_code}")
        print("流式响应内容:")
        
        full_response = ""
        for chunk in response.iter_content(chunk_size=1024):
            if chunk:
                decoded = chunk.decode('utf-8')
                full_response += decoded
                print(decoded, end='', flush=True)
        
        print(f"\n\n完整响应: {full_response}")
        return True
    except Exception as e:
        print(f"错误: {e}")
        return False

def test_upload_api():
    url = 'http://localhost:8000/api/upload'
    
    print("\n测试上传API...")
    try:
        files = {'file': open('img_data/MoS2.png', 'rb')}
        response = requests.post(url, files=files)
        
        print(f"状态码: {response.status_code}")
        print(f"响应: {response.text}")
        return response.status_code == 200
    except Exception as e:
        print(f"错误: {e}")
        return False

if __name__ == "__main__":
    print("=" * 50)
    print("API测试脚本")
    print("=" * 50)
    
    # 先测试上传功能
    upload_success = test_upload_api()
    
    # 再测试流式API
    stream_success = test_streaming_api()
    
    print("=" * 50)
    print(f"上传测试: {'成功' if upload_success else '失败'}")
    print(f"流式API测试: {'成功' if stream_success else '失败'}")
    print("=" * 50)