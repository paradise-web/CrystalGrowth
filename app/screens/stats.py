from kivy.uix.screenmanager import Screen
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.scrollview import ScrollView
from kivy.uix.gridlayout import GridLayout

class StatsScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.layout = BoxLayout(orientation='vertical', padding=20, spacing=20)
        
        # 标题
        title = Label(text='📊 统计信息', font_size=24, bold=True, size_hint_y=0.1)
        self.layout.add_widget(title)
        
        # 基本统计信息
        stats_grid = GridLayout(cols=2, spacing=10, size_hint_y=0.3)
        
        # 统计卡片
        def create_stat_card(title, value):
            card = BoxLayout(orientation='vertical', padding=10, spacing=5)
            card.canvas.before.clear()
            from kivy.graphics import Color, Rectangle
            with card.canvas.before:
                Color(0.8, 0.9, 1, 1)
                Rectangle(pos=card.pos, size=card.size)
            card.add_widget(Label(text=title, font_size=14))
            card.add_widget(Label(text=value, font_size=20, bold=True))
            return card
        
        stats_grid.add_widget(create_stat_card('总记录数', '127'))
        stats_grid.add_widget(create_stat_card('通过率', '92%'))
        stats_grid.add_widget(create_stat_card('最近7天', '15'))
        stats_grid.add_widget(create_stat_card('平均处理时间', '3.2s'))
        
        self.layout.add_widget(stats_grid)
        
        # 审核状态分布
        status_layout = BoxLayout(orientation='vertical', spacing=10, size_hint_y=0.2)
        status_layout.add_widget(Label(text='审核状态分布', font_size=18, bold=True))
        
        status_grid = GridLayout(cols=2, spacing=10)
        status_grid.add_widget(create_stat_card('通过', '117'))
        status_grid.add_widget(create_stat_card('未通过', '10'))
        
        status_layout.add_widget(status_grid)
        self.layout.add_widget(status_layout)
        
        # 时间趋势
        trend_layout = BoxLayout(orientation='vertical', spacing=10, size_hint_y=0.3)
        trend_layout.add_widget(Label(text='最近30天记录趋势', font_size=18, bold=True))
        
        # 模拟趋势图
        trend_mock = BoxLayout(orientation='vertical', spacing=5)
        trend_mock.add_widget(Label(text='日记录数:', font_size=14))
        trend_mock.add_widget(Label(text='4月1日: 5', font_size=12))
        trend_mock.add_widget(Label(text='4月5日: 8', font_size=12))
        trend_mock.add_widget(Label(text='4月10日: 6', font_size=12))
        trend_mock.add_widget(Label(text='4月15日: 7', font_size=12))
        
        trend_layout.add_widget(trend_mock)
        self.layout.add_widget(trend_layout)
        
        # 返回按钮
        back_button = Button(text='返回首页', size_hint_y=0.08)
        back_button.bind(on_press=lambda x: self.manager.current = 'home')
        self.layout.add_widget(back_button)
        
        self.add_widget(self.layout)