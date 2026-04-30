import 'package:flutter/material.dart';
import 'package:flutter_slidable/flutter_slidable.dart';
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

  Future<void> _saveTaskToExperiments(String taskId) async {
    try {
      var response = await ApiService.saveTaskToExperiments(taskId);
      if (response != null && response['success']) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('保存成功')),
        );
        await _loadTasks();
      } else {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('保存失败')),
        );
      }
    } catch (e) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('保存失败: $e')),
      );
    }
  }

  Color _getStatusColor(String status) {
    switch (status) {
      case 'pending':
        return Colors.orange;
      case 'processing':
        return Colors.blue;
      case 'completed':
        return Colors.green;
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
      case 'completed':
        return '待审批';
      case 'failed':
        return '失败';
      default:
        return status;
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('任务列表'),
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
                          if (task.status == 'completed')
                            SlidableAction(
                              onPressed: (context) => _saveTaskToExperiments(task.taskId),
                              backgroundColor: Colors.green,
                              foregroundColor: Colors.white,
                              icon: Icons.save,
                              label: '保存',
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
                                    padding: const EdgeInsets.symmetric(
                                        horizontal: 8, vertical: 4),
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
                              if (task.status == 'completed') ...[
                                const SizedBox(height: 8),
                                ElevatedButton.icon(
                                  onPressed: () => _saveTaskToExperiments(task.taskId),
                                  icon: const Icon(Icons.save),
                                  label: const Text('保存到实验记录'),
                                  style: ElevatedButton.styleFrom(
                                    backgroundColor: const Color(0xFF667eea),
                                  ),
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