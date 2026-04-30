import requests

log_file = open('test_output.log', 'w', encoding='utf-8')

def log(message):
    print(message)
    log_file.write(message + '\n')

log("测试简单API...")
try:
    response = requests.get('http://localhost:8000/')
    log(f"GET / : {response.status_code} - {response.text}")
except Exception as e:
    log(f"GET / 错误: {e}")

log("\n测试非流式聊天API...")
try:
    response = requests.post('http://localhost:8000/api/chat?query=什么是晶体生长')
    log(f"POST /api/chat : {response.status_code}")
    log(f"响应内容: {response.text}")
except Exception as e:
    log(f"POST /api/chat 错误: {e}")

log("\n测试流式聊天API...")
try:
    response = requests.post('http://localhost:8000/api/chat/stream?query=什么是晶体生长', stream=True)
    log(f"POST /api/chat/stream : {response.status_code}")
    content = ''
    for chunk in response.iter_content(chunk_size=1024):
        if chunk:
            content += chunk.decode('utf-8')
    log(f"流式响应内容: {content}")
except Exception as e:
    log(f"POST /api/chat/stream 错误: {e}")

log_file.close()
log("测试完成，结果已保存到 test_output.log")