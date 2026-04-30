import 'package:flutter/material.dart';
import 'package:flutter_slidable/flutter_slidable.dart';
import 'package:flutter_markdown/flutter_markdown.dart';
import '../services/api_service.dart';
import '../models/task.dart';

class TasksPage extends StatefulWidget {
  const TasksPage({super.key});

  @override
  State<TasksPage> createState() => _TasksPageState();
}

class _TasksPageState extends State<TasksPage> {
  List<Task> _tasks = [];
  bool _isLoading = true;
  final Map<String, bool> _expandedTasks = {};

  @override
  void initState() {
    super.initState();
    _loadTasks();
  }

  Future<void> _loadTasks() async {
    setState(() {
      _isLoading = true;
    });
    List<Task>? tasks = await ApiService.getTasks();
    setState(() {
      _tasks = tasks ?? [];
      _isLoading = false;
    });
  }

  Future<void> _deleteTask(String taskId) async {
    bool success = await ApiService.deleteTask(taskId);
    if (success) {
      setState(() {
        _tasks.removeWhere((task) => task.taskId == taskId);
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

  Future<void> _approveTask(String taskId) async {
    try {
      var response = await ApiService.saveTaskToExperiments(taskId);
      if (response != null && response['success']) {
        if (mounted) {
          ScaffoldMessenger.of(context).showSnackBar(
            const SnackBar(content: Text('通过审核，已保存到实验记录')),
          );
        }
        await _loadTasks();
      } else {
        if (mounted) {
          ScaffoldMessenger.of(context).showSnackBar(
            const SnackBar(content: Text('保存失败')),
          );
        }
      }
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('保存失败: $e')),
        );
      }
    }
  }

  Future<void> _rejectTask(String taskId) async {
    final TextEditingController feedbackController = TextEditingController();
    final result = await showDialog<String>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('不通过审核'),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Text('请填写不通过的原因，以便大模型参照此原因对内容进行重新修改处理：'),
            const SizedBox(height: 16),
            TextField(
              controller: feedbackController,
              maxLines: 4,
              decoration: const InputDecoration(
                hintText: '请输入不通过的原因...',
                border: OutlineInputBorder(),
              ),
            ),
          ],
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context),
            child: const Text('取消'),
          ),
          ElevatedButton(
            onPressed: () => Navigator.pop(context, feedbackController.text),
            style: ElevatedButton.styleFrom(
              backgroundColor: Colors.red,
            ),
            child: const Text('提交', style: TextStyle(color: Colors.white)),
          ),
        ],
      ),
    );

    if (result != null && result.isNotEmpty) {
      try {
        var response = await ApiService.rejectTask(taskId, result);
        if (response != null && response['success']) {
          if (mounted) {
            ScaffoldMessenger.of(context).showSnackBar(
              const SnackBar(content: Text('已提交反馈，任务正在重新处理中')),
            );
          }
          await _loadTasks();
        } else {
          if (mounted) {
            ScaffoldMessenger.of(context).showSnackBar(
              const SnackBar(content: Text('提交失败')),
            );
          }
        }
      } catch (e) {
        if (mounted) {
          ScaffoldMessenger.of(context).showSnackBar(
            SnackBar(content: Text('提交失败: $e')),
          );
        }
      }
    }
  }

  Color _getStatusColor(String status) {
    switch (status) {
      case 'pending':
        return Colors.orange;
      case 'processing':
        return Colors.blue;
      case 'pending_review':
        return Colors.green;
      case 'completed':
        return Colors.teal;
      case 'failed':
        return Colors.red;
      default:
        return Colors.grey;
    }
  }

  String _getStatusText(String status) {
    switch (status) {
      case 'pending':
        return '待处理';
      case 'processing':
        return '处理中';
      case 'pending_review':
        return '待审批';
      case 'completed':
        return '已入库';
      case 'failed':
        return '失败';
      default:
        return status;
    }
  }

  void _toggleExpand(String taskId) {
    setState(() {
      _expandedTasks[taskId] = !(_expandedTasks[taskId] ?? false);
    });
  }

  Widget _buildReviewIssues(Task task) {
    if (task.reviewIssues.isEmpty) {
      return const SizedBox.shrink();
    }
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const Padding(
          padding: EdgeInsets.all(8.0),
          child: Text(
            '🔍 审核问题',
            style: TextStyle(fontWeight: FontWeight.bold),
          ),
        ),
        ...task.reviewIssues.map((issue) {
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
          return Padding(
            padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 4),
            child: Card(
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
            ),
          );
        }),
      ],
    );
  }

  Widget _buildModelOutput(Task task) {
    if (task.formattedMarkdown != null && task.formattedMarkdown!.isNotEmpty) {
      return Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Padding(
            padding: EdgeInsets.all(8.0),
            child: Text(
              '📋 模型生成的实验报告',
              style: TextStyle(fontWeight: FontWeight.bold),
            ),
          ),
          Padding(
            padding: const EdgeInsets.all(8.0),
            child: MarkdownBody(
              data: task.formattedMarkdown!,
              styleSheet: MarkdownStyleSheet(
                h1: const TextStyle(fontSize: 18, fontWeight: FontWeight.bold),
                h2: const TextStyle(fontSize: 16, fontWeight: FontWeight.bold),
                h3: const TextStyle(fontSize: 14, fontWeight: FontWeight.bold),
                p: const TextStyle(fontSize: 14),
              ),
            ),
          ),
        ],
      );
    } else if (task.reviewedJson != null && task.reviewedJson!.isNotEmpty) {
      return Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Padding(
            padding: EdgeInsets.all(8.0),
            child: Text(
              '📋 模型输出的JSON数据',
              style: TextStyle(fontWeight: FontWeight.bold),
            ),
          ),
          Padding(
            padding: const EdgeInsets.all(8.0),
            child: Container(
              padding: const EdgeInsets.all(8),
              decoration: BoxDecoration(
                color: Colors.grey[100],
                borderRadius: BorderRadius.circular(4),
              ),
              child: SelectableText(
                task.reviewedJson!,
                style: const TextStyle(fontFamily: 'monospace', fontSize: 12),
              ),
            ),
          ),
        ],
      );
    }
    return const SizedBox.shrink();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('🔄 待审批'),
        actions: [
          IconButton(
            icon: const Icon(Icons.refresh),
            onPressed: _loadTasks,
          ),
        ],
      ),
      body: _isLoading
          ? const Center(child: CircularProgressIndicator())
          : _tasks.isEmpty
              ? const Center(child: Text('暂无任务'))
              : ListView.builder(
                  itemCount: _tasks.length,
                  itemBuilder: (context, index) {
                    Task task = _tasks[index];
                    return Slidable(
                      endActionPane: ActionPane(
                        motion: const ScrollMotion(),
                        children: [
                          if (task.status == 'pending_review')
                            SlidableAction(
                              onPressed: (context) => _approveTask(task.taskId),
                              backgroundColor: Colors.green,
                              foregroundColor: Colors.white,
                              icon: Icons.check,
                              label: '通过',
                            ),
                          SlidableAction(
                            onPressed: (context) => _deleteTask(task.taskId),
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
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Row(
                                children: [
                                  Expanded(
                                    child: Text(
                                      task.imageFilename,
                                      style: const TextStyle(fontWeight: FontWeight.bold),
                                    ),
                                  ),
                                  Container(
                                    padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                                    decoration: BoxDecoration(
                                      color: _getStatusColor(task.status),
                                      borderRadius: BorderRadius.circular(4),
                                    ),
                                    child: Text(
                                      _getStatusText(task.status),
                                      style: const TextStyle(color: Colors.white, fontSize: 12),
                                    ),
                                  ),
                                ],
                              ),
                              const SizedBox(height: 8),
                              Text('创建时间: ${task.createdAt}'),
                              if (task.status == 'processing') ...[
                                const SizedBox(height: 8),
                                LinearProgressIndicator(
                                  value: task.progress / 100,
                                  backgroundColor: Colors.grey[200],
                                  color: const Color(0xFF667eea),
                                ),
                                const SizedBox(height: 4),
                                Text('进度: ${task.progress}% - ${task.currentStep ?? ''}'),
                              ],
                              if (task.status == 'failed' && task.errorMessage != null) ...[
                                const SizedBox(height: 8),
                                Text(
                                  '错误: ${task.errorMessage}',
                                  style: const TextStyle(color: Colors.red),
                                ),
                              ],
                              if (task.status == 'pending_review') ...[
                                const SizedBox(height: 8),
                                Container(
                                  decoration: BoxDecoration(
                                    border: Border.all(color: const Color(0xFF667eea)),
                                    borderRadius: BorderRadius.circular(4),
                                  ),
                                  child: Column(
                                    children: [
                                      InkWell(
                                        onTap: () => _toggleExpand(task.taskId),
                                        child: Padding(
                                          padding: const EdgeInsets.all(8.0),
                                          child: Row(
                                            children: [
                                              Icon(
                                                _expandedTasks[task.taskId] ?? false
                                                    ? Icons.expand_less
                                                    : Icons.expand_more,
                                                color: const Color(0xFF667eea),
                                              ),
                                              const SizedBox(width: 4),
                                              Text(
                                                _expandedTasks[task.taskId] ?? false
                                                    ? '收起模型输出'
                                                    : '查看模型输出',
                                                style: const TextStyle(
                                                  color: Color(0xFF667eea),
                                                  fontWeight: FontWeight.bold,
                                                ),
                                              ),
                                            ],
                                          ),
                                        ),
                                      ),
                                      if (_expandedTasks[task.taskId] ?? false) ...[
                                        _buildReviewIssues(task),
                                        _buildModelOutput(task),
                                      ],
                                    ],
                                  ),
                                ),
                                const SizedBox(height: 8),
                                Row(
                                  children: [
                                    Expanded(
                                      child: ElevatedButton.icon(
                                        onPressed: () => _approveTask(task.taskId),
                                        icon: const Icon(Icons.check_circle),
                                        label: const Text('通过审核'),
                                        style: ElevatedButton.styleFrom(
                                          backgroundColor: Colors.green,
                                          foregroundColor: Colors.white,
                                        ),
                                      ),
                                    ),
                                    const SizedBox(width: 8),
                                    Expanded(
                                      child: ElevatedButton.icon(
                                        onPressed: () => _rejectTask(task.taskId),
                                        icon: const Icon(Icons.cancel),
                                        label: const Text('不通过审核'),
                                        style: ElevatedButton.styleFrom(
                                          backgroundColor: Colors.red,
                                          foregroundColor: Colors.white,
                                        ),
                                      ),
                                    ),
                                  ],
                                ),
                              ],
                            ],
                          ),
                        ),
                      ),
                    );
                  },
                ),
    );
  }
}