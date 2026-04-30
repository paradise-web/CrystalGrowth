import 'package:flutter/material.dart';
import 'package:flutter_slidable/flutter_slidable.dart';
import 'package:flutter_markdown/flutter_markdown.dart';
import 'package:cached_network_image/cached_network_image.dart';
import '../services/api_service.dart';
import '../models/experiment.dart';

class ExperimentsPage extends StatefulWidget {
  const ExperimentsPage({super.key});

  @override
  State<ExperimentsPage> createState() => _ExperimentsPageState();
}

class _ExperimentsPageState extends State<ExperimentsPage> {
  List<Experiment> _experiments = [];
  bool _isLoading = true;
  Experiment? _selectedExperiment;
  bool _showDetail = false;

  @override
  void initState() {
    super.initState();
    _loadExperiments();
  }

  Future<void> _loadExperiments() async {
    setState(() {
      _isLoading = true;
    });
    List<Experiment>? experiments = await ApiService.getExperiments();
    setState(() {
      _experiments = experiments ?? [];
      _isLoading = false;
    });
  }

  Future<void> _deleteExperiment(int experimentId) async {
    bool success = await ApiService.deleteExperiment(experimentId);
    if (success) {
      setState(() {
        _experiments.removeWhere((exp) => exp.id == experimentId);
        if (_selectedExperiment?.id == experimentId) {
          _selectedExperiment = null;
          _showDetail = false;
        }
      });
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('删除成功')),
      );
    } else {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('删除失败')),
      );
    }
  }

  void _showExperimentDetail(Experiment experiment) {
    setState(() {
      _selectedExperiment = experiment;
      _showDetail = true;
    });
  }

  void _closeDetail() {
    setState(() {
      _showDetail = false;
      _selectedExperiment = null;
    });
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('实验记录'),
        actions: [
          IconButton(
            icon: const Icon(Icons.refresh),
            onPressed: _loadExperiments,
          ),
        ],
      ),
      body: _isLoading
          ? const Center(child: CircularProgressIndicator())
          : _showDetail && _selectedExperiment != null
              ? _buildDetailView(_selectedExperiment!)
              : _experiments.isEmpty
                  ? const Center(child: Text('暂无实验记录'))
                  : ListView.builder(
                      itemCount: _experiments.length,
                      itemBuilder: (context, index) {
                        Experiment experiment = _experiments[index];
                        return Slidable(
                          endActionPane: ActionPane(
                            motion: const ScrollMotion(),
                            children: [
                              SlidableAction(
                                onPressed: (context) => _deleteExperiment(experiment.id),
                                backgroundColor: Colors.red,
                                foregroundColor: Colors.white,
                                icon: Icons.delete,
                                label: '删除',
                              ),
                            ],
                          ),
                          child: Card(
                            margin: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
                            child: Padding(
                              padding: const EdgeInsets.all(16.0),
                              child: InkWell(
                                onTap: () => _showExperimentDetail(experiment),
                                child: Row(
                                  children: [
                                    experiment.imagePath != null
                                        ? CachedNetworkImage(
                                            imageUrl: 'http://localhost:8000${experiment.imagePath}',
                                            width: 80,
                                            height: 80,
                                            fit: BoxFit.cover,
                                            placeholder: (context, url) => const CircularProgressIndicator(),
                                            errorWidget: (context, url, error) => const Icon(Icons.image),
                                          )
                                        : const Icon(Icons.image, size: 80),
                                    const SizedBox(width: 16),
                                    Expanded(
                                      child: Column(
                                        crossAxisAlignment: CrossAxisAlignment.start,
                                        children: [
                                          Text(
                                            experiment.imageFilename,
                                            style: const TextStyle(fontWeight: FontWeight.bold),
                                          ),
                                          const SizedBox(height: 4),
                                          Text('创建时间: ${experiment.createdAt}'),
                                          const SizedBox(height: 4),
                                          Row(
                                            children: [
                                              experiment.reviewPassed
                                                  ? const Icon(Icons.check_circle, color: Colors.green, size: 16)
                                                  : const Icon(Icons.close, color: Colors.red, size: 16),
                                              const SizedBox(width: 4),
                                              Text(
                                                experiment.reviewPassed ? '已通过' : '待审核',
                                                style: TextStyle(
                                                  color: experiment.reviewPassed ? Colors.green : Colors.red,
                                                ),
                                              ),
                                            ],
                                          ),
                                        ],
                                      ),
                                    ),
                                    const Icon(Icons.arrow_forward_ios),
                                  ],
                                ),
                              ),
                            ),
                          ),
                        );
                      },
                    ),
    );
  }

  Widget _buildDetailView(Experiment experiment) {
    return SingleChildScrollView(
      child: Padding(
        padding: const EdgeInsets.all(16.0),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                IconButton(
                  icon: const Icon(Icons.arrow_back),
                  onPressed: _closeDetail,
                ),
                Expanded(
                  child: Text(
                    experiment.imageFilename,
                    style: const TextStyle(fontSize: 18, fontWeight: FontWeight.bold),
                  ),
                ),
              ],
            ),
            const SizedBox(height: 16),
            
            if (experiment.imagePath != null)
              CachedNetworkImage(
                imageUrl: 'http://localhost:8000${experiment.imagePath}',
                width: double.infinity,
                fit: BoxFit.contain,
                placeholder: (context, url) => const CircularProgressIndicator(),
                errorWidget: (context, url, error) => const Icon(Icons.image),
              ),
            const SizedBox(height: 20),

            const Text(
              '📋 审核结果',
              style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold),
            ),
            const SizedBox(height: 8),
            Row(
              children: [
                experiment.reviewPassed
                    ? const Icon(Icons.check_circle, color: Colors.green, size: 24)
                    : const Icon(Icons.close, color: Colors.red, size: 24),
                const SizedBox(width: 8),
                Text(
                  experiment.reviewPassed ? '审核通过' : '待审核',
                  style: TextStyle(
                    fontSize: 18,
                    fontWeight: FontWeight.bold,
                    color: experiment.reviewPassed ? Colors.green : Colors.red,
                  ),
                ),
              ],
            ),
            const SizedBox(height: 20),

            if (experiment.reviewIssues.isNotEmpty) ...[
              const Text(
                '🔍 审核问题',
                style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold),
              ),
              const SizedBox(height: 8),
              Column(
                children: experiment.reviewIssues.map((issue) {
                  Color severityColor;
                  String severityText;
                  switch (issue.severity) {
                    case 'error':
                      severityColor = Colors.red;
                      severityText = '错误';
                      break;
                    case 'warning':
                      severityColor = Colors.orange;
                      severityText = '警告';
                      break;
                    default:
                      severityColor = Colors.blue;
                      severityText = '信息';
                  }
                  return Card(
                    margin: const EdgeInsets.symmetric(vertical: 4),
                    child: Padding(
                      padding: const EdgeInsets.all(8.0),
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Row(
                            children: [
                              Container(
                                padding: const EdgeInsets.symmetric(horizontal: 4, vertical: 2),
                                color: severityColor,
                                child: Text(
                                  severityText,
                                  style: const TextStyle(color: Colors.white, fontSize: 10),
                                ),
                              ),
                              if (issue.field != null) ...[
                                const SizedBox(width: 8),
                                Text(issue.field!),
                              ],
                            ],
                          ),
                          if (issue.description != null) ...[
                            const SizedBox(height: 4),
                            Text(issue.description!),
                          ],
                          if (issue.suggestion != null) ...[
                            const SizedBox(height: 4),
                            Text(
                              '💡 ${issue.suggestion}',
                              style: const TextStyle(color: Colors.green),
                            ),
                          ],
                        ],
                      ),
                    ),
                  );
                }).toList(),
              ),
              const SizedBox(height: 20),
            ],

            if (experiment.formattedMarkdown != null) ...[
              const Text(
                '📝 实验报告',
                style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold),
              ),
              const SizedBox(height: 8),
              Card(
                child: Padding(
                  padding: const EdgeInsets.all(16.0),
                  child: MarkdownBody(
                    data: experiment.formattedMarkdown!,
                    styleSheet: MarkdownStyleSheet(
                      h1: const TextStyle(fontSize: 20, fontWeight: FontWeight.bold),
                      h2: const TextStyle(fontSize: 16, fontWeight: FontWeight.bold),
                      h3: const TextStyle(fontSize: 14, fontWeight: FontWeight.bold),
                      p: const TextStyle(fontSize: 14),
                    ),
                  ),
                ),
              ),
            ],
          ],
        ),
      ),
    );
  }
}