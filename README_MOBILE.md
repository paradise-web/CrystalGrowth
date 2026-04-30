# 晶体生长实验记录助手 - 移动版

## 项目结构

```
exp_dec/
├── app.py                 # 原有的 Streamlit 应用（保持不变）
├── api_server.py          # 新增 FastAPI 后端服务
├── database.py            # 数据库模块（已更新）
├── requirements.txt       # 依赖文件（已更新）
└── crystal_app/           # Flutter 移动应用
    ├── pubspec.yaml
    └── lib/
        ├── main.dart
        ├── models/
        │   ├── experiment.dart
        │   ├── task.dart
        │   └── statistics.dart
        ├── services/
        │   └── api_service.dart
        └── pages/
            ├── home_page.dart
            ├── upload_page.dart
            ├── tasks_page.dart
            ├── experiments_page.dart
            └── statistics_page.dart
```

## 使用说明

### 1. 安装 Python 依赖

```bash
pip install -r requirements.txt
```

### 2. 启动 FastAPI 后端

```bash
python api_server.py
```

后端服务将在 `http://localhost:8000` 启动。

### 3. 运行 Flutter 应用

#### 前置条件

确保已安装 Flutter SDK：
```bash
flutter --version
```

#### 运行在 Android 设备

```bash
cd crystal_app
flutter pub get
flutter run
```

#### 运行在 iOS 设备（仅 macOS）

```bash
cd crystal_app
flutter pub get
flutter run
```

### 4. 配置网络地址

在实际设备上运行时，需要修改 `crystal_app/lib/services/api_service.dart` 中的 `baseUrl`：

```dart
// 从 localhost 改为你的电脑的实际 IP 地址
static const String baseUrl = 'http://192.168.1.100:8000';
```

## API 接口

### 上传图片

```
POST /api/upload
Content-Type: multipart/form-data
```

### 获取任务列表

```
GET /api/tasks
```

### 获取单个任务

```
GET /api/task/{task_id}
```

### 获取实验记录

```
GET /api/experiments
```

### 获取单个实验记录

```
GET /api/experiment/{experiment_id}
```

### 审核实验记录

```
POST /api/experiment/{experiment_id}/review
Content-Type: application/json
{
  "review_passed": true,
  "feedback": "审核通过"
}
```

### 删除实验记录

```
DELETE /api/experiment/{experiment_id}
```

### 删除任务

```
DELETE /api/task/{task_id}
```

### 获取统计信息

```
GET /api/statistics
```

## Flutter 应用功能

- 📸 **上传页面**: 拍照或从相册选择实验记录图片
- 📋 **任务页面**: 查看处理任务进度
- 📚 **记录页面**: 查看和审核实验记录
- 📊 **统计页面**: 查看数据统计
- 🏠 **首页**: 项目介绍和快速访问

## 注意事项

1. **原有 Streamlit 应用保持不变**，仍可继续使用 `streamlit run app.py`
2. **FastAPI 服务和 Streamlit 共享同一个数据库**，数据互通
3. Flutter 应用在真机上使用时，确保手机和电脑在同一局域网
4. 如需部署到公网，请配置正确的网络地址和安全措施
