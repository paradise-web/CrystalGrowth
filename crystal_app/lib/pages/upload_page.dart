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
  // 单图模式
  File? _imageFile;
  Uint8List? _webImageData;
  String? _webImageName;
  
  // 多图模式
  List<File> _imageFiles = [];
  List<_WebImageData> _webImagesData = [];
  bool _isMultiMode = false;
  
  bool _isUploading = false;
  TaskResponse? _uploadResult;
  MultiUploadResult? _multiUploadResult;

  final ImagePicker _picker = ImagePicker();

  Future<void> _pickImage(ImageSource source) async {
    try {
      if (_isMultiMode) {
        // 多图模式
        final pickedFiles = await _picker.pickMultiImage();
        if (pickedFiles.isNotEmpty) {
          setState(() {
            _imageFiles.addAll(pickedFiles.map((f) => File(f.path)));
            _uploadResult = null;
            _multiUploadResult = null;
          });
        }
      } else {
        // 单图模式
        final pickedFile = await _picker.pickImage(source: source);
        if (pickedFile != null) {
          if (kIsWeb) {
            final bytes = await pickedFile.readAsBytes();
            setState(() {
              _webImageData = bytes;
              _webImageName = pickedFile.name;
              _imageFile = null;
              _uploadResult = null;
              _multiUploadResult = null;
            });
          } else {
            setState(() {
              _imageFile = File(pickedFile.path);
              _webImageData = null;
              _uploadResult = null;
              _multiUploadResult = null;
            });
          }
        }
      }
    } catch (e) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('选择图片失败: $e')),
      );
    }
  }

  Future<void> _uploadImage() async {
    if (_isMultiMode) {
      await _uploadMultipleImages();
    } else {
      await _uploadSingleImage();
    }
  }

  Future<void> _uploadSingleImage() async {
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

  Future<void> _uploadMultipleImages() async {
    if (_imageFiles.isEmpty && _webImagesData.isEmpty) return;

    setState(() {
      _isUploading = true;
    });

    MultiUploadResult? result;
    if (kIsWeb && _webImagesData.isNotEmpty) {
      result = await ApiService.uploadMultipleWebImages(
        _webImagesData.map((e) => e.bytes).toList(),
        _webImagesData.map((e) => e.name).toList(),
      );
    } else if (_imageFiles.isNotEmpty) {
      result = await ApiService.uploadMultipleImages(_imageFiles);
    }

    setState(() {
      _isUploading = false;
      _multiUploadResult = result;
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

  void _removeImage(int index) {
    setState(() {
      if (_isMultiMode) {
        if (kIsWeb) {
          _webImagesData.removeAt(index);
        } else {
          _imageFiles.removeAt(index);
        }
      } else {
        _imageFile = null;
        _webImageData = null;
      }
      _uploadResult = null;
      _multiUploadResult = null;
    });
  }

  void _clearAllImages() {
    setState(() {
      _imageFile = null;
      _webImageData = null;
      _imageFiles.clear();
      _webImagesData.clear();
      _uploadResult = null;
      _multiUploadResult = null;
    });
  }

  void _toggleMultiMode() {
    setState(() {
      _isMultiMode = !_isMultiMode;
      // 切换模式时清空已选择的图片
      _imageFile = null;
      _webImageData = null;
      _imageFiles.clear();
      _webImagesData.clear();
      _uploadResult = null;
      _multiUploadResult = null;
    });
  }

  Widget _buildImagePreview() {
    if (_isMultiMode) {
      return _buildMultiImagePreview();
    }
    
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

  Widget _buildMultiImagePreview() {
    final List<dynamic> images = kIsWeb ? _webImagesData : _imageFiles;
    
    if (images.isEmpty) {
      return const Center(child: Text('未选择图片'));
    }
    
    return GridView.builder(
      padding: const EdgeInsets.all(8),
      gridDelegate: const SliverGridDelegateWithFixedCrossAxisCount(
        crossAxisCount: 3,
        crossAxisSpacing: 8,
        mainAxisSpacing: 8,
      ),
      itemCount: images.length,
      itemBuilder: (context, index) {
        return Stack(
          fit: StackFit.expand,
          children: [
            if (kIsWeb)
              Image.memory(
                _webImagesData[index].bytes,
                fit: BoxFit.cover,
              )
            else
              Image.file(
                _imageFiles[index],
                fit: BoxFit.cover,
              ),
            Positioned(
              top: 4,
              right: 4,
              child: GestureDetector(
                onTap: () => _removeImage(index),
                child: Container(
                  padding: const EdgeInsets.all(4),
                  decoration: BoxDecoration(
                    color: Colors.red,
                    borderRadius: BorderRadius.circular(12),
                  ),
                  child: const Icon(
                    Icons.close,
                    size: 16,
                    color: Colors.white,
                  ),
                ),
              ),
            ),
          ],
        );
      },
    );
  }

  bool get hasImage => _imageFile != null || (_webImageData != null && _webImageData!.isNotEmpty);
  bool get hasMultiImages => _imageFiles.isNotEmpty || (_webImagesData.isNotEmpty && _webImagesData.isNotEmpty);

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('📤 文件上传'),
        actions: [
          IconButton(
            icon: Icon(_isMultiMode ? Icons.photo : Icons.photo_library),
            onPressed: _toggleMultiMode,
            tooltip: _isMultiMode ? '切换到单图模式' : '切换到多图模式',
          ),
        ],
      ),
      body: SingleChildScrollView(
        padding: const EdgeInsets.all(16.0),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.center,
          children: [
            // 模式提示
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
              decoration: BoxDecoration(
                color: _isMultiMode ? Colors.orange : Colors.blue,
                borderRadius: BorderRadius.circular(16),
              ),
              child: Text(
                _isMultiMode ? '多图模式 (最多20张)' : '单图模式',
                style: const TextStyle(color: Colors.white, fontSize: 12),
              ),
            ),
            const SizedBox(height: 20),
            
            if (hasImage || hasMultiImages)
              Column(
                children: [
                  Container(
                    width: double.infinity,
                    height: _isMultiMode ? 400 : 300,
                    decoration: BoxDecoration(
                      border: Border.all(color: Colors.grey),
                      borderRadius: BorderRadius.circular(8),
                    ),
                    child: _buildImagePreview(),
                  ),
                  const SizedBox(height: 16),
                  if (_isMultiMode && hasMultiImages)
                    Padding(
                      padding: const EdgeInsets.only(bottom: 16),
                      child: Text(
                        '已选择 ${_imageFiles.length + _webImagesData.length} 张图片',
                        style: const TextStyle(color: Colors.grey),
                      ),
                    ),
                  Row(
                    children: [
                      Expanded(
                        child: ElevatedButton(
                          onPressed: _clearAllImages,
                          style: ElevatedButton.styleFrom(
                            backgroundColor: Colors.grey,
                          ),
                          child: const Text('清空'),
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
                              : Text(_isMultiMode ? '批量上传' : '上传并处理'),
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
                    child: Center(
                      child: Column(
                        mainAxisAlignment: MainAxisAlignment.center,
                        children: [
                          Icon(
                            _isMultiMode ? Icons.photo_library : Icons.image,
                            size: 64,
                            color: Colors.grey,
                          ),
                          const SizedBox(height: 8),
                          Text(
                            _isMultiMode ? '点击下方按钮选择多张图片' : '点击下方按钮选择图片',
                            style: const TextStyle(color: Colors.grey),
                          ),
                        ],
                      ),
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
                          label: Text(_isMultiMode ? '多选' : '相册'),
                        ),
                      ),
                    ],
                  ),
                ],
              ),

            if (_uploadResult != null && !_isMultiMode)
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

            if (_multiUploadResult != null && _isMultiMode)
              Card(
                elevation: 4,
                child: Padding(
                  padding: const EdgeInsets.all(16.0),
                  child: Column(
                    children: [
                      const Text(
                        '批量上传结果',
                        style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold),
                      ),
                      const SizedBox(height: 10),
                      Text('成功: ${_multiUploadResult?.taskIds.length} 个'),
                      if (_multiUploadResult!.failedCount > 0)
                        Text(
                          '失败: ${_multiUploadResult?.failedCount} 个',
                          style: const TextStyle(color: Colors.red),
                        ),
                      if (_multiUploadResult!.failedFiles.isNotEmpty)
                        Padding(
                          padding: const EdgeInsets.only(top: 8),
                          child: Text(
                            '失败文件: ${_multiUploadResult?.failedFiles.join(", ")}',
                            style: const TextStyle(color: Colors.red, fontSize: 12),
                          ),
                        ),
                      const SizedBox(height: 8),
                      Text(_multiUploadResult?.message ?? ''),
                    ],
                  ),
                ),
              ),

            const SizedBox(height: 20),
            Card(
              child: Padding(
                padding: const EdgeInsets.all(16.0),
                child: Column(
                  children: [
                    const Text(
                      '📌 提示',
                      style: TextStyle(fontWeight: FontWeight.bold),
                    ),
                    const SizedBox(height: 8),
                    Text(_isMultiMode 
                        ? '• 支持 JPG、PNG 格式\n• 最多一次上传 20 张图片\n• 上传后将在后台自动处理\n• 可在「任务」页面查看进度'
                        : '• 支持 JPG、PNG 格式\n• 建议拍摄清晰的手写记录\n• 上传后将在后台自动处理\n• 可在「任务」页面查看进度'),
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

class _WebImageData {
  final Uint8List bytes;
  final String name;

  _WebImageData({required this.bytes, required this.name});
}