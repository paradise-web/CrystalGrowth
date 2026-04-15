import 'package:flutter/material.dart';
import 'package:flutter_markdown/flutter_markdown.dart';

class ResultScreen extends StatelessWidget {
  final Map<String, dynamic> result;

  const ResultScreen({super.key, required this.result});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('分析结果'),
        centerTitle: true,
      ),
      body: SingleChildScrollView(
        padding: const EdgeInsets.all(20.0),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            _buildSection('基础信息', _buildMetaInfo()),
            const SizedBox(height: 20),
            _buildSection('反应体系', _buildReactionInfo()),
            const SizedBox(height: 20),
            _buildSection('配料表', _buildIngredientsTable()),
            const SizedBox(height: 20),
            _buildSection('生长工艺', _buildProcessInfo()),
            const SizedBox(height: 20),
            if (result.containsKey('results') && result['results'].isNotEmpty)
              _buildSection('结果表征', _buildResultsInfo()),
            const SizedBox(height: 20),
            if (result.containsKey('notes') && result['notes'].isNotEmpty)
              _buildSection('备注', _buildNotesInfo()),
            const SizedBox(height: 40),
            Center(
              child: ElevatedButton(
                onPressed: () => Navigator.pop(context),
                child: const Text('返回'),
              ),
            ),
            const SizedBox(height: 40),
          ],
        ),
      ),
    );
  }

  Widget _buildSection(String title, Widget content) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          title,
          style: const TextStyle(
            fontSize: 18,
            fontWeight: FontWeight.bold,
            color: Colors.blue,
          ),
        ),
        const SizedBox(height: 10),
        content,
      ],
    );
  }

  Widget _buildMetaInfo() {
    final meta = result['meta'] ?? {};
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(15.0),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            if (meta.containsKey('title'))
              _buildInfoRow('实验名称', meta['title']),
            if (meta.containsKey('date'))
              _buildInfoRow('日期', meta['date']),
            if (meta.containsKey('furnace'))
              _buildInfoRow('设备', meta['furnace']),
            if (meta.containsKey('method'))
              _buildInfoRow('方法', meta['method']),
          ],
        ),
      ),
    );
  }

  Widget _buildReactionInfo() {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(15.0),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            if (result.containsKey('reaction_equation') && result['reaction_equation'].isNotEmpty)
              Text(
                '方程式: ${result['reaction_equation']}',
                style: const TextStyle(fontSize: 16),
              ),
          ],
        ),
      ),
    );
  }

  Widget _buildIngredientsTable() {
    final ingredients = result['ingredients'] ?? [];
    if (ingredients.isEmpty) {
      return const Card(
        child: Padding(
          padding: EdgeInsets.all(15.0),
          child: Text('未识别到配料表'),
        ),
      );
    }

    return Card(
      child: Padding(
        padding: const EdgeInsets.all(15.0),
        child: DataTable(
          columns: const [
            DataColumn(label: Text('组分')),
            DataColumn(label: Text('质量')),
            DataColumn(label: Text('摩尔比')),
            DataColumn(label: Text('备注')),
          ],
          rows: ingredients.map((ingredient) {
            return DataRow(cells: [
              DataCell(Text(ingredient['compound'] ?? '-')),
              DataCell(Text(ingredient['mass_g'] ?? '-')),
              DataCell(Text(ingredient['molar_ratio'] ?? '-')),
              DataCell(Text(ingredient['role'] ?? '-')),
            ]);
          }).toList(),
        ),
      ),
    );
  }

  Widget _buildProcessInfo() {
    final process = result['process'] ?? {};
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(15.0),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            if (process.containsKey('high_temp'))
              _buildInfoRow('高温区', process['high_temp']),
            if (process.containsKey('low_temp'))
              _buildInfoRow('低温区', process['low_temp']),
            if (process.containsKey('description'))
              Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const Text('完整流程:', style: TextStyle(fontWeight: FontWeight.bold)),
                  const SizedBox(height: 5),
                  Text(process['description']),
                ],
              ),
          ],
        ),
      ),
    );
  }

  Widget _buildResultsInfo() {
    final results = result['results'] ?? [];
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(15.0),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: results.map((resultItem) {
            return Padding(
              padding: const EdgeInsets.only(bottom: 10),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    '${resultItem['type']}: ${resultItem['label'] ?? ''}',
                    style: const TextStyle(fontWeight: FontWeight.bold),
                  ),
                  if (resultItem['description'])
                    Text(resultItem['description']),
                ],
              ),
            );
          }).toList(),
        ),
      ),
    );
  }

  Widget _buildNotesInfo() {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(15.0),
        child: Text(result['notes']),
      ),
    );
  }

  Widget _buildInfoRow(String label, dynamic value) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 5),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            '$label: ',
            style: const TextStyle(fontWeight: FontWeight.bold),
          ),
          Expanded(child: Text(value.toString())),
        ],
      ),
    );
  }
}