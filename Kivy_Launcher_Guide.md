# 使用Kivy Launcher在Android上运行应用

## 什么是Kivy Launcher？
Kivy Launcher是一个Android应用，可以直接运行Kivy应用的源代码，无需构建APK。这是一个快速测试和运行Kivy应用的好方法。

## 步骤

### 1. 安装Kivy Launcher
- 在Google Play商店搜索并安装"Kivy Launcher"
- 或者从[Kivy官方网站](https://kivy.org/doc/stable/installation/installation-android.html#kivy-launcher)下载APK

### 2. 准备应用文件
1. 在你的Android设备上创建一个名为`Kivy`的文件夹
2. 在`Kivy`文件夹中创建一个子文件夹，例如`exp_dec`
3. 将以下文件复制到`exp_dec`文件夹中：
   - `app/main.py` - 应用入口
   - `app/screens/` - 所有页面文件
   - `core/` - 核心功能模块
   - `requirements.txt` - 依赖文件

### 3. 修改main.py文件
修改`app/main.py`文件，确保它可以在Kivy Launcher中正确运行：

```python
from kivy.app import App
from kivy.uix.screenmanager import ScreenManager
import os
import sys

# 添加当前目录到Python路径
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from screens.home import HomeScreen
from screens.upload import UploadScreen
from screens.history import HistoryScreen
from screens.stats import StatsScreen

class ExpDecApp(App):
    def build(self):
        sm = ScreenManager()
        sm.add_widget(HomeScreen(name='home'))
        sm.add_widget(UploadScreen(name='upload'))
        sm.add_widget(HistoryScreen(name='history'))
        sm.add_widget(StatsScreen(name='stats'))
        return sm

if __name__ == '__main__':
    ExpDecApp().run()
```

### 4. 运行应用
1. 打开Kivy Launcher应用
2. 你应该能看到`exp_dec`文件夹
3. 点击它来运行应用

## 注意事项
- Kivy Launcher可能无法处理所有依赖项，特别是复杂的AI库
- 这是一个临时解决方案，适合测试和开发
- 对于最终发布，建议使用Buildozer构建完整的APK

## 替代方案

### 使用Google Colab构建APK
1. 打开`build_android.ipynb`文件
2. 将`yourusername`替换为你的GitHub用户名
3. 运行所有单元格
4. 下载生成的APK文件

### 使用GitHub Actions
1. 将代码推送到GitHub的`feat/pack_android`分支
2. 在GitHub仓库的Actions页面触发构建
3. 下载生成的APK文件
