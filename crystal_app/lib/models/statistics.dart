class Statistics {
  final int totalCount;
  final int passedCount;
  final int failedCount;
  final double avgIterations;
  final int recentCount;
  final double passRate;

  Statistics({
    required this.totalCount,
    required this.passedCount,
    required this.failedCount,
    required this.avgIterations,
    required this.recentCount,
    required this.passRate,
  });

  factory Statistics.fromJson(Map<String, dynamic> json) {
    return Statistics(
      totalCount: json['total_count'] ?? 0,
      passedCount: json['passed_count'] ?? 0,
      failedCount: json['failed_count'] ?? 0,
      avgIterations: (json['avg_iterations'] ?? 0).toDouble(),
      recentCount: json['recent_count'] ?? 0,
      passRate: (json['pass_rate'] ?? 0).toDouble(),
    );
  }
}