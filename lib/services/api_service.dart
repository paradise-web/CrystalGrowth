import 'dart:io';
import 'dart:convert';
import 'package:http/http.dart' as http;

class ApiService {
  static const String _baseUrl = 'http://localhost:8000'; // 本地API服务地址

  static Future<Map<String, dynamic>> analyzeImage(File image) async {
    var request = http.MultipartRequest(
      'POST',
      Uri.parse('$_baseUrl/analyze'),
    );

    request.files.add(
      await http.MultipartFile.fromPath(
        'image',
        image.path,
      ),
    );

    var streamedResponse = await request.send();
    var response = await http.Response.fromStream(streamedResponse);

    if (response.statusCode == 200) {
      return json.decode(response.body);
    } else {
      throw Exception('分析失败: ${response.statusCode}');
    }
  }

  static Future<Map<String, dynamic>> getExperiments() async {
    var response = await http.get(Uri.parse('$_baseUrl/experiments'));

    if (response.statusCode == 200) {
      return json.decode(response.body);
    } else {
      throw Exception('获取实验记录失败: ${response.statusCode}');
    }
  }

  static Future<Map<String, dynamic>> getExperimentDetail(int id) async {
    var response = await http.get(Uri.parse('$_baseUrl/experiments/$id'));

    if (response.statusCode == 200) {
      return json.decode(response.body);
    } else {
      throw Exception('获取实验详情失败: ${response.statusCode}');
    }
  }
}