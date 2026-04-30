import 'dart:io';
import 'dart:typed_data';
import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:image_picker/image_picker.dart';
import '../services/api_service.dart';
import '../models/task.dart';

class UploadPage extends StatefulWidget {
  const UploadPage({super.key});

  @override
  State<UploadPage> createState() => _UploadPageState();
}

class _UploadPageState extends State<UploadPage> {
  File? _imageFile;
  Uint8List? _webImageData;
  String? _webImageName;
  bool _isUploading = false;
  TaskResponse? _uploadResult;

  final ImagePicker _picker = ImagePicker();

  Future<void> _pickImage(ImageSource source) async {
    try {
      final pickedFile = await _picker.pickImage(source: source);
      if (pickedFile != null) {
        if (kIsWeb) {
          final bytes = await pickedFile.readAsBytes();
          setState(() {
            _webImageData = bytes;
            _webImageName = pickedFile.name;
            _imageFile = null;
            _uploadResult = null;
          });
        } else {
          setState(() {
            _imageFile = File(pickedFile.path);
            _webImageData = null;
            _uploadResult = null;
          });
        }
      }
    } catch (e) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('选择图片失败: $e')),
      );
    }
  }

  Future<void> _uploadImage() async {
    if (_imageFile == null && _webImageData == null) return;

    setState(() {
      _isUploading = true;
    });

    TaskResponse? result;
    if (kIsWeb && _webImageData != null) {
      result = await ApiService.uploadWebImage(_webImageData!, _webImageName ?? 'image.jpg');
    } else if (_imageFile != null) {
      result = await ApiService.uploadImage(_imageFile!);
    }

    setState(() {
      _isUploading = false;
      _uploadResult = result;
    });

    if (result != null) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(result.message)),
      );
    } else {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('上传失败，请重试')),
      );
    }
  }

  Widget _buildImagePreview() {
    if (kIsWeb && _webImageData != null) {
      return Image.memory(
        _webImageData!,
        fit: BoxFit.contain,
      );
    } else if (_imageFile != null) {
      return Image.file(
        _imageFile!,
        fit: BoxFit.contain,
      );
    }
    return const SizedBox();
  }

  bool get hasImage => _imageFile != null || (_webImageData != null && _webImageData!.isNotEmpty);

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('📤 文件上传'),
      ),
      body: SingleChildScrollView(
        padding: const EdgeInsets.all(16.0),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.center,
          children: [
            const SizedBox(height: 20),
            
            if (hasImage)
              Column(
                children: [
                  Container(
                    width: double.infinity,
                    height: 300,
                    decoration: BoxDecoration(
                      border: Border.all(color: Colors.grey),
                      borderRadius: BorderRadius.circular(8),
                    ),
                    child: _buildImagePreview(),
                  ),
                  const SizedBox(height: 16),
                  Row(
                    children: [
                      Expanded(
                        child: ElevatedButton(
                          onPressed: () => setState(() {
                            _imageFile = null;
                            _webImageData = null;
                            _uploadResult = null;
                          }),
                          style: ElevatedButton.styleFrom(
                            backgroundColor: Colors.grey,
                          ),
                          child: const Text('重新选择'),
                        ),
                      ),
                      const SizedBox(width: 10),
                      Expanded(
                        child: ElevatedButton(
                          onPressed: _isUploading ? null : _uploadImage,
                          style: ElevatedButton.styleFrom(
                            backgroundColor: const Color(0xFF667eea),
                          ),
                          child: _isUploading
                              ? const CircularProgressIndicator(color: Colors.white)
                              : const Text('上传并处理'),
                        ),
                      ),
                    ],
                  ),
                  const SizedBox(height: 20),
                ],
              )
            else
              Column(
                children: [
                  Container(
                    width: double.infinity,
                    height: 300,
                    decoration: BoxDecoration(
                      border: Border.all(color: Colors.grey),
                      borderRadius: BorderRadius.circular(8),
                    ),
                    child: const Center(
                      child: Text('点击下方按钮选择图片'),
                    ),
                  ),
                  const SizedBox(height: 20),
                  Row(
                    children: [
                      Expanded(
                        child: ElevatedButton.icon(
                          onPressed: () => _pickImage(ImageSource.camera),
                          icon: const Icon(Icons.camera),
                          label: const Text('拍照'),
                        ),
                      ),
                      const SizedBox(width: 10),
                      Expanded(
                        child: ElevatedButton.icon(
                          onPressed: () => _pickImage(ImageSource.gallery),
                          icon: const Icon(Icons.photo_library),
                          label: const Text('相册'),
                        ),
                      ),
                    ],
                  ),
                ],
              ),

            if (_uploadResult != null)
              Card(
                elevation: 4,
                child: Padding(
                  padding: const EdgeInsets.all(16.0),
                  child: Column(
                    children: [
                      const Text(
                        '上传结果',
                        style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold),
                      ),
                      const SizedBox(height: 10),
                      Text('任务ID: ${_uploadResult?.taskId}'),
                      Text('状态: ${_uploadResult?.status}'),
                      Text('消息: ${_uploadResult?.message}'),
                    ],
                  ),
                ),
              ),

            const SizedBox(height: 20),
            const Card(
              child: Padding(
                padding: EdgeInsets.all(16.0),
                child: Column(
                  children: [
                    Text(
                      '📌 提示',
                      style: TextStyle(fontWeight: FontWeight.bold),
                    ),
                    SizedBox(height: 8),
                    Text('• 支持 JPG、PNG 格式'),
                    Text('• 建议拍摄清晰的手写记录'),
                    Text('• 上传后将在后台自动处理'),
                    Text('• 可在「任务」页面查看进度'),
                  ],
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}