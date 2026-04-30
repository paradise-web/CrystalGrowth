@echo off
echo 测试API...
D:\Anaconda3\python.exe -c "import requests; r = requests.get('http://localhost:8000/'); print('Index:', r.text)" >> test_result.txt
D:\Anaconda3\python.exe -c "import requests; r = requests.post('http://localhost:8000/api/chat?query=什么是晶体生长'); print('Chat:', r.text)" >> test_result.txt
D:\Anaconda3\python.exe -c "import requests; r = requests.post('http://localhost:8000/api/chat/stream?query=什么是晶体生长', stream=True); print('Stream:', r.text)" >> test_result.txt
echo 测试完成，结果已保存到 test_result.txt