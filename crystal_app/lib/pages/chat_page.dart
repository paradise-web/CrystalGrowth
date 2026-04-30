import 'package:flutter/material.dart';
import 'package:flutter_markdown/flutter_markdown.dart';
import '../services/api_service.dart';

class ChatPage extends StatefulWidget {
  const ChatPage({super.key});

  @override
  State<ChatPage> createState() => _ChatPageState();
}

class _ChatPageState extends State<ChatPage> {
  final List<Map<String, String>> _chatHistory = [];
  final TextEditingController _textController = TextEditingController();
  final ScrollController _scrollController = ScrollController();
  bool _isTyping = false;

  final List<Map<String, String>> _sampleQuestions = [
    {"question": "什么是晶体生长？", "answer": "晶体生长是指从气相、液相或固相物质中形成具有规则几何外形的晶体的过程。"},
    {"question": "常见的晶体生长方法有哪些？", "answer": "常见的晶体生长方法包括：提拉法、坩埚下降法、水热法、气相生长法等。"},
    {"question": "如何提高晶体生长质量？", "answer": "提高晶体生长质量需要注意：控制温度梯度、优化生长速率、保持熔体纯净等。"},
  ];

  void _scrollToBottom() {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      _scrollController.animateTo(
        _scrollController.position.maxScrollExtent,
        duration: const Duration(milliseconds: 300),
        curve: Curves.easeOut,
      );
    });
  }

  Future<void> _sendMessage() async {
    String userInput = _textController.text.trim();
    if (userInput.isEmpty) return;

    setState(() {
      _chatHistory.add({"role": "user", "content": userInput});
      _textController.clear();
      _isTyping = true;
    });

    _scrollToBottom();

    // 调用流式API
    try {
      String aiResponse = "";
      await for (var chunk in ApiService.sendChatMessageStream(userInput)) {
        aiResponse = chunk;
        setState(() {
          if (_chatHistory.isNotEmpty && _chatHistory.last["role"] == "assistant") {
            _chatHistory.removeLast();
          }
          _chatHistory.add({"role": "assistant", "content": aiResponse});
        });
        _scrollToBottom();
      }
    } catch (e) {
      print('流式API调用失败: $e');
      // 降级到非流式API
      String aiResponse = "抱歉，获取回答失败，请稍后重试。";
      try {
        var result = await ApiService.sendChatMessage(userInput);
        aiResponse = result ?? "抱歉，获取回答失败，请稍后重试。";
      } catch (e) {
        print('非流式API调用也失败: $e');
      }
      setState(() {
        if (_chatHistory.isNotEmpty && _chatHistory.last["role"] == "assistant") {
          _chatHistory.removeLast();
        }
        _chatHistory.add({"role": "assistant", "content": aiResponse});
      });
      _scrollToBottom();
    }

    setState(() {
      _isTyping = false;
    });
  }

  void _clearChat() {
    setState(() {
      _chatHistory.clear();
    });
  }

  Widget _buildChatBubble(Map<String, String> message) {
    bool isUser = message["role"] == "user";
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 8, horizontal: 16),
      child: Column(
        crossAxisAlignment: isUser ? CrossAxisAlignment.end : CrossAxisAlignment.start,
        children: [
          Container(
            padding: const EdgeInsets.all(12),
            decoration: BoxDecoration(
              color: isUser ? const Color(0xFF667eea) : Colors.grey[200],
              borderRadius: BorderRadius.circular(12),
            ),
            constraints: BoxConstraints(maxWidth: MediaQuery.of(context).size.width * 0.8),
            child: MarkdownBody(
              data: message["content"]!,
              styleSheet: MarkdownStyleSheet(
                p: TextStyle(
                  color: isUser ? Colors.white : Colors.black,
                  fontSize: 14,
                ),
                h1: TextStyle(
                  color: isUser ? Colors.white : Colors.black,
                  fontSize: 18,
                  fontWeight: FontWeight.bold,
                ),
                h2: TextStyle(
                  color: isUser ? Colors.white : Colors.black,
                  fontSize: 16,
                  fontWeight: FontWeight.bold,
                ),
                h3: TextStyle(
                  color: isUser ? Colors.white : Colors.black,
                  fontSize: 14,
                  fontWeight: FontWeight.bold,
                ),
                listBullet: TextStyle(
                  color: isUser ? Colors.white : Colors.black,
                ),
              ),
            ),
          ),
          const SizedBox(height: 4),
          Text(
            isUser ? "你" : "AI",
            style: TextStyle(
              fontSize: 12,
              color: Colors.grey,
            ),
          ),
        ],
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('💬 知识问答'),
        actions: [
          IconButton(
            icon: const Icon(Icons.delete),
            onPressed: _clearChat,
            tooltip: '清除聊天历史',
          ),
        ],
      ),
      body: Column(
        children: [
          Expanded(
            child: ListView.builder(
              controller: _scrollController,
              itemCount: _chatHistory.length + (_isTyping ? 1 : 0),
              itemBuilder: (context, index) {
                if (_isTyping && index == _chatHistory.length) {
                  return const Padding(
                    padding: EdgeInsets.symmetric(vertical: 8, horizontal: 16),
                    child: Row(
                      children: [
                        SizedBox(
                          width: 20,
                          height: 20,
                          child: CircularProgressIndicator(strokeWidth: 2),
                        ),
                        SizedBox(width: 8),
                        Text('AI 正在思考...'),
                      ],
                    ),
                  );
                }
                return _buildChatBubble(_chatHistory[index]);
              },
            ),
          ),
          if (_chatHistory.isEmpty)
            Expanded(
              child: SingleChildScrollView(
                padding: const EdgeInsets.all(16),
                child: Column(
                  children: [
                    const Text(
                      '欢迎使用晶体生长实验助手的知识问答功能！',
                      style: TextStyle(fontSize: 16, fontWeight: FontWeight.bold),
                    ),
                    const SizedBox(height: 16),
                    const Text(
                      '在这里，你可以向AI询问关于晶体生长实验的相关问题。',
                      style: TextStyle(color: Colors.grey),
                    ),
                    const SizedBox(height: 24),
                    const Text(
                      '热门问题：',
                      style: TextStyle(fontWeight: FontWeight.bold),
                    ),
                    const SizedBox(height: 12),
                    ..._sampleQuestions.take(3).map((sample) => Padding(
                          padding: const EdgeInsets.symmetric(vertical: 8),
                          child: ElevatedButton(
                            onPressed: () {
                              _textController.text = sample["question"]!;
                            },
                            style: ElevatedButton.styleFrom(
                              backgroundColor: Colors.grey[100],
                              foregroundColor: Colors.black,
                              elevation: 0,
                            ),
                            child: Text(sample["question"]!),
                          ),
                        )),
                  ],
                ),
              ),
            ),
          Padding(
            padding: const EdgeInsets.all(16),
            child: Row(
              children: [
                Expanded(
                  child: TextField(
                    controller: _textController,
                    decoration: const InputDecoration(
                      hintText: '请输入你的问题...',
                      border: OutlineInputBorder(),
                      contentPadding: EdgeInsets.symmetric(horizontal: 16, vertical: 12),
                    ),
                    onSubmitted: (_) => _sendMessage(),
                  ),
                ),
                const SizedBox(width: 12),
                ElevatedButton(
                  onPressed: _isTyping ? null : _sendMessage,
                  style: ElevatedButton.styleFrom(
                    backgroundColor: const Color(0xFF667eea),
                    padding: const EdgeInsets.all(16),
                    shape: const CircleBorder(),
                  ),
                  child: _isTyping
                      ? const CircularProgressIndicator(color: Colors.white)
                      : const Icon(Icons.send),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}