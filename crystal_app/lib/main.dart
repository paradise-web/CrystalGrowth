import 'package:flutter/material.dart';
import 'pages/home_page.dart';
import 'pages/upload_page.dart';
import 'pages/tasks_page.dart';
import 'pages/experiments_page.dart';
import 'pages/statistics_page.dart';
import 'pages/chat_page.dart';

void main() {
  runApp(const CrystalApp());
}

class CrystalApp extends StatelessWidget {
  const CrystalApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: '晶体生长实验记录助手',
      theme: ThemeData(
        primaryColor: const Color(0xFF667eea),
        primarySwatch: Colors.indigo,
        appBarTheme: const AppBarTheme(
          backgroundColor: Color(0xFF667eea),
          foregroundColor: Colors.white,
        ),
        floatingActionButtonTheme: const FloatingActionButtonThemeData(
          backgroundColor: Color(0xFF667eea),
        ),
      ),
      home: const MainPage(),
      debugShowCheckedModeBanner: false,
    );
  }
}

class MainPage extends StatefulWidget {
  const MainPage({super.key});

  @override
  State<MainPage> createState() => _MainPageState();
}

class _MainPageState extends State<MainPage> {
  int _selectedIndex = 0;

  static const List<Widget> _pages = [
    HomePage(),
    UploadPage(),
    TasksPage(),
    ExperimentsPage(),
    StatisticsPage(),
    ChatPage(),
  ];

  static const List<BottomNavigationBarItem> _navItems = [
    BottomNavigationBarItem(
      icon: Icon(Icons.home),
      label: '首页',
    ),
    BottomNavigationBarItem(
      icon: Icon(Icons.upload_file),
      label: '上传',
    ),
    BottomNavigationBarItem(
      icon: Icon(Icons.list_alt),
      label: '任务',
    ),
    BottomNavigationBarItem(
      icon: Icon(Icons.book),
      label: '记录',
    ),
    BottomNavigationBarItem(
      icon: Icon(Icons.bar_chart),
      label: '统计',
    ),
    BottomNavigationBarItem(
      icon: Icon(Icons.chat),
      label: '问答',
    ),
  ];

  void _onItemTapped(int index) {
    setState(() {
      _selectedIndex = index;
    });
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: _pages[_selectedIndex],
      bottomNavigationBar: BottomNavigationBar(
        items: _navItems,
        currentIndex: _selectedIndex,
        selectedItemColor: const Color(0xFF667eea),
        unselectedItemColor: Colors.grey,
        onTap: _onItemTapped,
        type: BottomNavigationBarType.fixed,
      ),
    );
  }
}