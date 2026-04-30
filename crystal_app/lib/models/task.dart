import 'dart:convert';

class Task {
  final String taskId;
  final String imageFilename;
  final String status;
  final String? errorMessage;
  final int progress;
  final String? currentStep;
  final String createdAt;
  final String? rawJson;
  final String? reviewedJson;
  final String? formattedMarkdown;
  final List<ReviewIssue> reviewIssues;

  Task({
    required this.taskId,
    required this.imageFilename,
    required this.status,
    this.errorMessage,
    required this.progress,
    this.currentStep,
    required this.createdAt,
    this.rawJson,
    this.reviewedJson,
    this.formattedMarkdown,
    this.reviewIssues = const [],
  });

  factory Task.fromJson(Map<String, dynamic> json) {
    var issuesJson = json['review_issues'];
    List<ReviewIssue> issues = [];
    if (issuesJson != null) {
      if (issuesJson is List) {
        issues = issuesJson.map((issue) => ReviewIssue.fromJson(issue)).toList();
      } else if (issuesJson is String && issuesJson.isNotEmpty) {
        try {
          var parsed = jsonDecode(issuesJson) as List;
          issues = parsed.map((issue) => ReviewIssue.fromJson(issue)).toList();
        } catch (e) {
          issues = [];
        }
      }
    }

    return Task(
      taskId: json['task_id'] ?? '',
      imageFilename: json['image_filename'] ?? '',
      status: json['status'] ?? '',
      errorMessage: json['error_message'],
      progress: json['progress'] ?? 0,
      currentStep: json['current_step'],
      createdAt: json['created_at'] ?? '',
      rawJson: json['raw_json'],
      reviewedJson: json['reviewed_json'],
      formattedMarkdown: json['formatted_markdown'],
      reviewIssues: issues,
    );
  }
}

class ReviewIssue {
  final String? field;
  final String? description;
  final String? suggestion;
  final String? severity;

  ReviewIssue({
    this.field,
    this.description,
    this.suggestion,
    this.severity,
  });

  factory ReviewIssue.fromJson(Map<String, dynamic> json) {
    return ReviewIssue(
      field: json['field'],
      description: json['description'],
      suggestion: json['suggestion'],
      severity: json['severity'],
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