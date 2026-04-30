import 'package:flutter/material.dart';
import '../services/api_service.dart';
import '../models/statistics.dart';
import 'upload_page.dart';

class HomePage extends StatefulWidget {
  const HomePage({super.key});

  @override
  State<HomePage> createState() => _HomePageState();
}

class _HomePageState extends State<HomePage> {
  Statistics? _statistics;
  bool _isLoading = true;
  bool _creatingTestData = false;

  @override
  void initState() {
    super.initState();
    _loadStatistics();
  }

  Future<void> _loadStatistics() async {
    setState(() {
      _isLoading = true;
    });
    try {
      _statistics = await ApiService.getStatistics();
    } catch (e) {
      print('加载统计信息失败: $e');
    }
    setState(() {
      _isLoading = false;
    });
  }

  Future<void> _createTestData() async {
    setState(() {
      _creatingTestData = true;
    });
    try {
      var response = await ApiService.createTestData();
      if (response != null && response['success'] == true) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('测试数据创建成功！')),
        );
        await _loadStatistics(); // 重新加载统计信息
      } else {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('创建测试数据失败')),
        );
      }
    } catch (e) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('创建测试数据失败: $e')),
      );
    }
    setState(() {
      _creatingTestData = false;
    });
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('🏠 首页'),
      ),
      body: SingleChildScrollView(
        child: Padding(
          padding: const EdgeInsets.all(16.0),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const SizedBox(height: 20),
              const Text(
                '🔍 欢迎使用',
                style: TextStyle(fontSize: 24, fontWeight: FontWeight.bold),
              ),
              const SizedBox(height: 10),
              const Text(
                '基于AI的实验记录数字化工具，将手写记录转化为结构化数据',
                style: TextStyle(fontSize: 16, color: Colors.grey),
              ),
              const SizedBox(height: 30),

              _isLoading
                  ? const Center(child: CircularProgressIndicator())
                  : _buildStatisticsCards(),

              const SizedBox(height: 20),

              // 创建测试数据按钮
              ElevatedButton.icon(
                onPressed: _creatingTestData ? null : _createTestData,
                icon: _creatingTestData
                    ? const SizedBox(
                        width: 20,
                        height: 20,
                        child: CircularProgressIndicator(
                          strokeWidth: 2,
                          color: Colors.white,
                        ),
                      )
                    : const Icon(Icons.add_circle_outline),
                label: Text(_creatingTestData ? '创建中...' : '创建测试数据'),
                style: ElevatedButton.styleFrom(
                  backgroundColor: const Color(0xFF667eea),
                  padding: const EdgeInsets.symmetric(
                    horizontal: 24,
                    vertical: 12,
                  ),
                ),
              ),

              const SizedBox(height: 30),

              _buildFeatures(),

              const SizedBox(height: 30),

              _buildWorkflow(),
            ],
          ),
        ),
      ),
      floatingActionButton: FloatingActionButton(
        onPressed: () {
          Navigator.push(
            context,
            MaterialPageRoute(builder: (context) => UploadPage()),
          );
        },
        child: const Icon(Icons.camera_alt),
      ),
    );
  }

  Widget _buildStatisticsCards() {
    return Row(
      children: [
        Expanded(
          child: Card(
            elevation: 4,
            child: Padding(
              padding: const EdgeInsets.all(16.0),
              child: Column(
                children: [
                  const Icon(Icons.file_copy, color: Colors.indigo, size: 32),
                  const SizedBox(height: 8),
                  Text(
                    '${_statistics?.totalCount ?? 0}',
                    style: const TextStyle(fontSize: 24, fontWeight: FontWeight.bold),
                  ),
                  const Text('总记录数'),
                ],
              ),
            ),
          ),
        ),
        const SizedBox(width: 10),
        Expanded(
          child: Card(
            elevation: 4,
            child: Padding(
              padding: const EdgeInsets.all(16.0),
              child: Column(
                children: [
                  const Icon(Icons.check_circle, color: Colors.green, size: 32),
                  const SizedBox(height: 8),
                  Text(
                    '${_statistics?.passedCount ?? 0}',
                    style: const TextStyle(fontSize: 24, fontWeight: FontWeight.bold),
                  ),
                  const Text('审核通过'),
                ],
              ),
            ),
          ),
        ),
        const SizedBox(width: 10),
        Expanded(
          child: Card(
            elevation: 4,
            child: Padding(
              padding: const EdgeInsets.all(16.0),
              child: Column(
                children: [
                  const Icon(Icons.trending_up, color: Colors.orange, size: 32),
                  const SizedBox(height: 8),
                  Text(
                    '${_statistics?.passRate ?? 0}%',
                    style: const TextStyle(fontSize: 24, fontWeight: FontWeight.bold),
                  ),
                  const Text('通过率'),
                ],
              ),
            ),
          ),
        ),
      ],
    );
  }

  Widget _buildFeatures() {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const Text(
          '✨ 核心功能',
          style: TextStyle(fontSize: 20, fontWeight: FontWeight.bold),
        ),
        const SizedBox(height: 16),
        Row(
          children: [
            Expanded(
              child: _featureCard(
                '🤖',
                '视觉感知',
                '使用AI模型分析实验记录图片，自动提取数据',
              ),
            ),
            const SizedBox(width: 10),
            Expanded(
              child: _featureCard(
                '🔬',
                '化学审核',
                '专业化学知识审核提取的数据，确保准确性',
              ),
            ),
          ],
        ),
        const SizedBox(height: 10),
        Row(
          children: [
            Expanded(
              child: _featureCard(
                '📝',
                '报告生成',
                '生成标准化的Markdown实验报告',
              ),
            ),
            const SizedBox(width: 10),
            Expanded(
              child: _featureCard(
                '📊',
                '数据分析',
                '统计分析实验数据，支持数据挖掘',
              ),
            ),
          ],
        ),
      ],
    );
  }

  Widget _featureCard(String icon, String title, String description) {
    return Card(
      elevation: 2,
      child: Padding(
        padding: const EdgeInsets.all(16.0),
        child: Column(
          children: [
            Text(icon, style: const TextStyle(fontSize: 32)),
            const SizedBox(height: 8),
            Text(
              title,
              style: const TextStyle(fontSize: 16, fontWeight: FontWeight.bold),
            ),
            const SizedBox(height: 8),
            Text(
              description,
              style: const TextStyle(fontSize: 12, color: Colors.grey),
              textAlign: TextAlign.center,
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildWorkflow() {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const Text(
          '🔄 工作流程',
          style: TextStyle(fontSize: 20, fontWeight: FontWeight.bold),
        ),
        const SizedBox(height: 16),
        Column(
          children: [
            _workflowStep(1, '上传图片', '拍摄或选择手写实验记录'),
            _workflowStep(2, 'AI分析', '视觉感知提取数据，化学审核验证'),
            _workflowStep(3, '人工审核', '查看结果，提供反馈'),
            _workflowStep(4, '生成报告', '保存标准化实验报告'),
          ],
        ),
      ],
    );
  }

  Widget _workflowStep(int step, String title, String description) {
    return Container(
      margin: const EdgeInsets.symmetric(vertical: 8),
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
                      color: Colors.grey[50],
                      borderRadius: const BorderRadius.all(Radius.circular(8)),
                      border: const Border(left: BorderSide(color: Color(0xFF667eea), width: 4)),
                    ),
      child: Row(
        children: [
          Container(
            width: 32,
            height: 32,
            decoration: BoxDecoration(
              color: const Color(0xFF667eea),
              borderRadius: BorderRadius.circular(16),
            ),
            child: Center(
              child: Text(
                '$step',
                style: const TextStyle(color: Colors.white, fontWeight: FontWeight.bold),
              ),
            ),
          ),
          const SizedBox(width: 16),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  title,
                  style: const TextStyle(fontWeight: FontWeight.bold),
                ),
                Text(
                  description,
                  style: const TextStyle(color: Colors.grey, fontSize: 12),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}