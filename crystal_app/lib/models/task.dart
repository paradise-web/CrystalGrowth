class Task {
  final String taskId;
  final String imageFilename;
  final String status;
  final String? errorMessage;
  final int progress;
  final String? currentStep;
  final String createdAt;

  Task({
    required this.taskId,
    required this.imageFilename,
    required this.status,
    this.errorMessage,
    required this.progress,
    this.currentStep,
    required this.createdAt,
  });

  factory Task.fromJson(Map<String, dynamic> json) {
    return Task(
      taskId: json['task_id'] ?? '',
      imageFilename: json['image_filename'] ?? '',
      status: json['status'] ?? '',
      errorMessage: json['error_message'],
      progress: json['progress'] ?? 0,
      currentStep: json['current_step'],
      createdAt: json['created_at'] ?? '',
    );
  }
}

class TaskResponse {
  final String taskId;
  final String status;
  final String message;

  TaskResponse({
    required this.taskId,
    required this.status,
    required this.message,
  });

  factory TaskResponse.fromJson(Map<String, dynamic> json) {
    return TaskResponse(
      taskId: json['task_id'] ?? '',
      status: json['status'] ?? '',
      message: json['message'] ?? '',
    );
  }
}