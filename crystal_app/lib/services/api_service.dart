import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';
import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;
import '../models/experiment.dart';
import '../models/task.dart';
import '../models/statistics.dart';

class MultiUploadResult {
  final bool success;
  final String message;
  final List<String> taskIds;
  final int failedCount;
  final List<String> failedFiles;

  MultiUploadResult({
    required this.success,
    required this.message,
    required this.taskIds,
    required this.failedCount,
    required this.failedFiles,
  });

  factory MultiUploadResult.fromJson(Map<String, dynamic> json) {
    return MultiUploadResult(
      success: json['success'] ?? false,
      message: json['message'] ?? '',
      taskIds: List<String>.from(json['task_ids'] ?? []),
      failedCount: json['failed_count'] ?? 0,
      failedFiles: List<String>.from(json['failed_files'] ?? []),
    );
  }
}

class ApiService {
  static const String baseUrl = 'http://localhost:8000';

  static Future<TaskResponse?> uploadImage(File imageFile) async {
    try {
      var request = http.MultipartRequest(
        'POST',
        Uri.parse('$baseUrl/api/upload'),
      );
      request.files.add(
        await http.MultipartFile.fromPath('file', imageFile.path),
      );

      var response = await request.send();
      if (response.statusCode == 200) {
        var responseBody = await response.stream.bytesToString();
        var jsonResponse = json.decode(responseBody);
        return TaskResponse.fromJson(jsonResponse);
      }
      return null;
    } catch (e) {
      print('上传图片失败: $e');
      return null;
    }
  }

  static Future<TaskResponse?> uploadWebImage(Uint8List imageBytes, String fileName) async {
    try {
      var request = http.MultipartRequest(
        'POST',
        Uri.parse('$baseUrl/api/upload'),
      );
      request.files.add(
        http.MultipartFile.fromBytes(
          'file',
          imageBytes,
          filename: fileName,
        ),
      );

      var response = await request.send();
      if (response.statusCode == 200) {
        var responseBody = await response.stream.bytesToString();
        var jsonResponse = json.decode(responseBody);
        return TaskResponse.fromJson(jsonResponse);
      }
      return null;
    } catch (e) {
      print('上传图片失败: $e');
      return null;
    }
  }

  static Future<List<Task>?> getTasks() async {
    try {
      var response = await http.get(Uri.parse('$baseUrl/api/tasks'));
      if (response.statusCode == 200) {
        // 使用utf8解码确保正确处理中文字符
        var responseBody = utf8.decode(response.bodyBytes);
        var jsonResponse = json.decode(responseBody);
        var tasksJson = jsonResponse['tasks'] as List;
        return tasksJson.map((task) => Task.fromJson(task)).toList();
      }
      return null;
    } catch (e) {
      print('获取任务列表失败: $e');
      return null;
    }
  }

  static Future<Task?> getTask(String taskId) async {
    try {
      var response = await http.get(Uri.parse('$baseUrl/api/task/$taskId'));
      if (response.statusCode == 200) {
        var responseBody = utf8.decode(response.bodyBytes);
        var jsonResponse = json.decode(responseBody);
        return Task.fromJson(jsonResponse['task']);
      }
      return null;
    } catch (e) {
      print('获取任务失败: $e');
      return null;
    }
  }

  static Future<List<Experiment>?> getExperiments() async {
    try {
      var response = await http.get(Uri.parse('$baseUrl/api/experiments'));
      if (response.statusCode == 200) {
        var responseBody = utf8.decode(response.bodyBytes);
        var jsonResponse = json.decode(responseBody);
        var experimentsJson = jsonResponse['experiments'] as List;
        return experimentsJson.map((exp) => Experiment.fromJson(exp)).toList();
      }
      return null;
    } catch (e) {
      print('获取实验记录失败: $e');
      return null;
    }
  }

  static Future<Experiment?> getExperiment(int experimentId) async {
    try {
      var response = await http.get(Uri.parse('$baseUrl/api/experiment/$experimentId'));
      if (response.statusCode == 200) {
        var responseBody = utf8.decode(response.bodyBytes);
        var jsonResponse = json.decode(responseBody);
        return Experiment.fromJson(jsonResponse);
      }
      return null;
    } catch (e) {
      print('获取实验记录失败: $e');
      return null;
    }
  }

  static Future<bool> reviewExperiment(int experimentId, bool reviewPassed, String feedback) async {
    try {
      var response = await http.post(
        Uri.parse('$baseUrl/api/experiment/$experimentId/review'),
        headers: {'Content-Type': 'application/json'},
        body: json.encode({
          'experiment_id': experimentId,
          'review_passed': reviewPassed,
          'feedback': feedback,
        }),
      );
      if (response.statusCode == 200) {
        var jsonResponse = json.decode(response.body);
        return jsonResponse['success'] ?? false;
      }
      return false;
    } catch (e) {
      print('审核失败: $e');
      return false;
    }
  }

  static Future<bool> deleteExperiment(int experimentId) async {
    try {
      var response = await http.delete(
        Uri.parse('$baseUrl/api/experiment/$experimentId'),
      );
      if (response.statusCode == 200) {
        var jsonResponse = json.decode(response.body);
        return jsonResponse['success'] ?? false;
      }
      return false;
    } catch (e) {
      print('删除失败: $e');
      return false;
    }
  }

  static Future<bool> deleteTask(String taskId) async {
    try {
      var response = await http.delete(
        Uri.parse('$baseUrl/api/task/$taskId'),
      );
      if (response.statusCode == 200) {
        var jsonResponse = json.decode(response.body);
        return jsonResponse['success'] ?? false;
      }
      return false;
    } catch (e) {
      print('删除任务失败: $e');
      return false;
    }
  }

  static Future<Statistics?> getStatistics() async {
    try {
      var response = await http.get(Uri.parse('$baseUrl/api/statistics'));
      if (response.statusCode == 200) {
        var jsonResponse = json.decode(response.body);
        return Statistics.fromJson(jsonResponse['statistics']);
      }
      return null;
    } catch (e) {
      print('获取统计信息失败: $e');
      return null;
    }
  }

  static Future<Map<String, dynamic>?> saveTaskToExperiments(String taskId) async {
    try {
      var response = await http.post(
        Uri.parse('$baseUrl/api/task/$taskId/save_to_experiments'),
      );
      if (response.statusCode == 200) {
        var responseBody = utf8.decode(response.bodyBytes);
        return json.decode(responseBody);
      }
      return null;
    } catch (e) {
      print('保存任务失败: $e');
      return null;
    }
  }

  static Future<Map<String, dynamic>?> rejectTask(String taskId, String feedback) async {
    try {
      var response = await http.post(
        Uri.parse('$baseUrl/api/task/$taskId/reject?feedback=${Uri.encodeQueryComponent(feedback)}'),
      );
      if (response.statusCode == 200) {
        var responseBody = utf8.decode(response.bodyBytes);
        return json.decode(responseBody);
      }
      return null;
    } catch (e) {
      print('拒绝任务失败: $e');
      return null;
    }
  }

  static Future<String?> sendChatMessage(String message) async {
    try {
      var response = await http.post(
        Uri.parse('$baseUrl/api/chat?query=${Uri.encodeQueryComponent(message)}'),
      );
      if (response.statusCode == 200) {
        var responseBody = utf8.decode(response.bodyBytes);
        var jsonResponse = json.decode(responseBody);
        if (jsonResponse['success'] == true && jsonResponse['data'] != null) {
          return jsonResponse['data']['answer'];
        }
      }
      return null;
    } catch (e) {
      print('发送消息失败: $e');
      return null;
    }
  }

  static Stream<String> sendChatMessageStream(String message) async* {
    try {
      var request = http.Request('POST', Uri.parse('$baseUrl/api/chat/stream?query=${Uri.encodeQueryComponent(message)}'));
      var response = await request.send();
      
      if (response.statusCode == 200) {
        String buffer = '';
        await for (var chunk in response.stream.transform(utf8.decoder)) {
          buffer += chunk;
          yield buffer;
        }
      } else {
        yield '请求失败，请稍后重试。';
      }
    } catch (e) {
      print('流式消息发送失败: $e');
      yield '连接失败，请稍后重试。';
    }
  }

  static Future<Map<String, dynamic>?> createTestData() async {
    try {
      var response = await http.post(
        Uri.parse('$baseUrl/api/create_test_data'),
      );
      if (response.statusCode == 200) {
        return json.decode(response.body);
      }
      return null;
    } catch (e) {
      print('创建测试数据失败: $e');
      return null;
    }
  }

  static Future<MultiUploadResult?> uploadMultipleImages(
    List<File> imageFiles,
  ) async {
    // Web平台不支持dart:io，使用Web上传方法
    if (kIsWeb) {
      return uploadMultipleWebImages(
        await Future.wait(imageFiles.map((f) => f.readAsBytes())),
        imageFiles.map((f) => f.path.split('/').last).toList(),
      );
    }
    
    try {
      var request = http.MultipartRequest(
        'POST',
        Uri.parse('$baseUrl/api/upload/multiple'),
      );

      for (var file in imageFiles) {
        request.files.add(
          await http.MultipartFile.fromPath('files', file.path),
        );
      }

      var streamedResponse = await request.send();
      var response = await http.Response.fromStream(streamedResponse);
      
      if (response.statusCode == 200) {
        var responseBody = utf8.decode(response.bodyBytes);
        var jsonResponse = json.decode(responseBody);
        return MultiUploadResult.fromJson(jsonResponse);
      }
      return null;
    } catch (e) {
      print('批量上传图片失败: $e');
      return null;
    }
  }

  static Future<MultiUploadResult?> uploadMultipleWebImages(
    List<Uint8List> imageBytesList,
    List<String> fileNames,
  ) async {
    try {
      var request = http.MultipartRequest(
        'POST',
        Uri.parse('$baseUrl/api/upload/multiple'),
      );

      for (int i = 0; i < imageBytesList.length; i++) {
        request.files.add(
          http.MultipartFile.fromBytes(
            'files',
            imageBytesList[i],
            filename: fileNames[i],
          ),
        );
      }

      var streamedResponse = await request.send();
      var response = await http.Response.fromStream(streamedResponse);
      
      if (response.statusCode == 200) {
        var responseBody = utf8.decode(response.bodyBytes);
        var jsonResponse = json.decode(responseBody);
        return MultiUploadResult.fromJson(jsonResponse);
      }
      return null;
    } catch (e) {
      print('批量上传图片失败: $e');
      return null;
    }
  }
}