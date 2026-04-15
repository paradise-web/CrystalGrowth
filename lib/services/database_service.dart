import 'dart:io';
import 'package:sqflite/sqflite.dart';
import 'package:path/path.dart';
import 'package:path_provider/path_provider.dart';

class DatabaseService {
  static Database? _database;

  static Future<Database> get database async {
    if (_database != null) return _database!;

    _database = await _initDatabase();
    return _database!;
  }

  static Future<Database> _initDatabase() async {
    Directory documentsDirectory = await getApplicationDocumentsDirectory();
    String path = join(documentsDirectory.path, 'experiments.db');

    return await openDatabase(
      path,
      version: 1,
      onCreate: (db, version) {
        return db.execute('''
          CREATE TABLE experiments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            image_path TEXT,
            result TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
          )
        ''');
      },
    );
  }

  static Future<int> saveExperiment(String imagePath, String result) async {
    final db = await database;
    return await db.insert(
      'experiments',
      {'image_path': imagePath, 'result': result},
      conflictAlgorithm: ConflictAlgorithm.replace,
    );
  }

  static Future<List<Map<String, dynamic>>> getExperiments() async {
    final db = await database;
    return await db.query('experiments', orderBy: 'created_at DESC');
  }

  static Future<Map<String, dynamic>?> getExperiment(int id) async {
    final db = await database;
    final List<Map<String, dynamic>> maps = await db.query(
      'experiments',
      where: 'id = ?',
      whereArgs: [id],
    );

    if (maps.isNotEmpty) {
      return maps.first;
    }
    return null;
  }

  static Future<int> deleteExperiment(int id) async {
    final db = await database;
    return await db.delete(
      'experiments',
      where: 'id = ?',
      whereArgs: [id],
    );
  }
}