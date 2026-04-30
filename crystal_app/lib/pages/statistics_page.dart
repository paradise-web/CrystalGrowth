import 'package:flutter/material.dart';
import '../services/api_service.dart';
import '../models/statistics.dart';

class StatisticsPage extends StatefulWidget {
  const StatisticsPage({super.key});

  @override
  State<StatisticsPage> createState() => _StatisticsPageState();
}

class _StatisticsPageState extends State<StatisticsPage> {
  Statistics? _statistics;
  bool _isLoading = true;

  @override
  void initState() {
    super.initState();
    _loadStatistics();
  }

  Future<void> _loadStatistics() async {
    setState(() {
      _isLoading = true;
    });
    _statistics = await ApiService.getStatistics();
    setState(() {
      _isLoading = false;
    });
  }

  Widget _statCard(String title, String value, String unit, Color color) {
    return Card(
      elevation: 4,
      child: Padding(
        padding: const EdgeInsets.all(16.0),
        child: Column(
          children: [
            Text(title, style: const TextStyle(color: Colors.grey)),
            const SizedBox(height: 8),
            Row(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                Text(
                  value,
                  style: TextStyle(fontSize: 32, fontWeight: FontWeight.bold, color: color),
                ),
                if (unit.isNotEmpty) const SizedBox(width: 4),
                Text(unit, style: const TextStyle(color: Colors.grey)),
              ],
            ),
          ],
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('统计信息'),
        actions: [
          IconButton(
            icon: const Icon(Icons.refresh),
            onPressed: _loadStatistics,
          ),
        ],
      ),
      body: _isLoading
          ? const Center(child: CircularProgressIndicator())
          : SingleChildScrollView(
              padding: const EdgeInsets.all(16.0),
              child: Column(
                children: [
                  const SizedBox(height: 20),
                  Row(
                    children: [
                      Expanded(
                        child: _statCard(
                          '总记录数',
                          '${_statistics?.totalCount ?? 0}',
                          '',
                          Colors.indigo,
                        ),
                      ),
                      const SizedBox(width: 10),
                      Expanded(
                        child: _statCard(
                          '审核通过',
                          '${_statistics?.passedCount ?? 0}',
                          '',
                          Colors.green,
                        ),
                      ),
                    ],
                  ),
                  const SizedBox(height: 10),
                  Row(
                    children: [
                      Expanded(
                        child: _statCard(
                          '审核未通过',
                          '${_statistics?.failedCount ?? 0}',
                          '',
                          Colors.red,
                        ),
                      ),
                      const SizedBox(width: 10),
                      Expanded(
                        child: _statCard(
                          '通过率',
                          '${_statistics?.passRate ?? 0}',
                          '%',
                          Colors.orange,
                        ),
                      ),
                    ],
                  ),
                  const SizedBox(height: 10),
                  Row(
                    children: [
                      Expanded(
                        child: _statCard(
                          '最近7天',
                          '${_statistics?.recentCount ?? 0}',
                          '条',
                          Colors.blue,
                        ),
                      ),
                      const SizedBox(width: 10),
                      Expanded(
                        child: _statCard(
                          '平均迭代',
                          '${_statistics?.avgIterations ?? 0}',
                          '次',
                          Colors.purple,
                        ),
                      ),
                    ],
                  ),
                  const SizedBox(height: 30),
                  Card(
                    elevation: 4,
                    child: Padding(
                      padding: const EdgeInsets.all(16.0),
                      child: Column(
                        children: [
                          const Text(
                            '📊 数据概览',
                            style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold),
                          ),
                          const SizedBox(height: 20),
                          _buildProgressBar('审核进度', _statistics?.passRate ?? 0),
                          _buildProgressBar('最近活跃度', (_statistics?.recentCount ?? 0) * 10),
                        ],
                      ),
                    ),
                  ),
                  const SizedBox(height: 20),
                  Card(
                    elevation: 4,
                    child: Padding(
                      padding: const EdgeInsets.all(16.0),
                      child: Column(
                        children: [
                          const Text(
                            '💡 使用建议',
                            style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold),
                          ),
                          const SizedBox(height: 16),
                          _suggestionCard('📸', '提高图片质量', '拍摄时尽量清晰，光线充足'),
                          _suggestionCard('🔍', '审核反馈', '及时审核记录，提供反馈帮助AI改进'),
                          _suggestionCard('📁', '数据备份', '定期备份实验记录数据'),
                        ],
                      ),
                    ),
                  ),
                ],
              ),
            ),
    );
  }

  Widget _buildProgressBar(String label, double percentage) {
    return Column(
      children: [
        Row(
          mainAxisAlignment: MainAxisAlignment.spaceBetween,
          children: [
            Text(label),
            Text('${percentage.toStringAsFixed(1)}%'),
          ],
        ),
        const SizedBox(height: 8),
        LinearProgressIndicator(
          value: (percentage > 100 ? 100 : percentage) / 100,
          backgroundColor: Colors.grey[200],
          color: const Color(0xFF667eea),
        ),
        const SizedBox(height: 16),
      ],
    );
  }

  Widget _suggestionCard(String icon, String title, String description) {
    return Container(
      margin: const EdgeInsets.symmetric(vertical: 8),
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: Colors.grey[50],
        borderRadius: BorderRadius.circular(8),
      ),
      child: Row(
        children: [
          Text(icon, style: const TextStyle(fontSize: 24)),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(title, style: const TextStyle(fontWeight: FontWeight.bold)),
                Text(description, style: const TextStyle(color: Colors.grey, fontSize: 12)),
              ],
            ),
          ),
        ],
      ),
    );
  }
}