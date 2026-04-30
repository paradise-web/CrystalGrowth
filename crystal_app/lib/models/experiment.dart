class Experiment {
  final int id;
  final String imageFilename;
  final String? imagePath;
  final String? rawJson;
  final String? reviewedJson;
  final String? formattedMarkdown;
  final bool reviewPassed;
  final List<ReviewIssue> reviewIssues;
  final String createdAt;

  Experiment({
    required this.id,
    required this.imageFilename,
    this.imagePath,
    this.rawJson,
    this.reviewedJson,
    this.formattedMarkdown,
    required this.reviewPassed,
    required this.reviewIssues,
    required this.createdAt,
  });

  factory Experiment.fromJson(Map<String, dynamic> json) {
    var issuesJson = json['review_issues'] as List? ?? [];
    var issues = issuesJson.map((issue) => ReviewIssue.fromJson(issue)).toList();

    return Experiment(
      id: json['id'] ?? 0,
      imageFilename: json['image_filename'] ?? '',
      imagePath: json['image_path'],
      rawJson: json['raw_json'],
      reviewedJson: json['reviewed_json'],
      formattedMarkdown: json['formatted_markdown'],
      reviewPassed: json['review_passed'] ?? false,
      reviewIssues: issues,
      createdAt: json['created_at'] ?? '',
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