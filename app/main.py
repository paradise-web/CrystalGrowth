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