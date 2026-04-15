from kivy.uix.screenmanager import Screen
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.scrollview import ScrollView
from kivy.uix.gridlayout import GridLayout
import os

class HistoryScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.layout = BoxLayout(orientation='vertical', padding=20, spacing=20)
        
        # 标题
        title = Label(text='📚 历史记录', font_size=24, bold=True, size_hint_y=0.1)
        self.layout.add_widget(title)
        
        # 搜索和筛选
        search_layout = BoxLayout(size_hint_y=0.1, spacing=10)
        search_btn = Button(text='🔍 搜索')
        filter_btn = Button(text='📋 筛选')
        search_layout.add_widget(search_btn)
        search_layout.add_widget(filter_btn)
        self.layout.add_widget(search_layout)
        
        # 历史记录列表
        scroll = ScrollView(size_hint_y=0.7)
        self.history_list = GridLayout(cols=1, spacing=10, size_hint_y=None)
        self.history_list.bind(minimum_height=self.history_list.setter('height'))
        
        # 模拟历史记录数据
        self.load_history()
        
        scroll.add_widget(self.history_list)
        self.layout.add_widget(scroll)
        
        # 返回按钮
        back_button = Button(text='返回首页', size_hint_y=0.08)
        back_button.bind(on_press=lambda x: self.manager.current = 'home')
        self.layout.add_widget(back_button)
        
        self.add_widget(self.layout)
    
    def load_history(self):
        # 清空列表
        self.history_list.clear_widgets()
        
        # 模拟历史记录
        mock_history = [
            {'id': 1, 'name': 'MoS2实验记录', 'date': '2026-04-14', 'status': '通过'},
            {'id': 2, 'name': 'NbSe2实验记录', 'date': '2026-04-13', 'status': '通过'},
            {'id': 3, 'name': 'VPS4实验记录', 'date': '2026-04-12', 'status': '未通过'},
            {'id': 4, 'name': 'MoCl3实验记录', 'date': '2026-04-11', 'status': '通过'},
            {'id': 5, 'name': 'CsCr6Sb6实验记录', 'date': '2026-04-10', 'status': '通过'},
        ]
        
        for record in mock_history:
            record_item = BoxLayout(orientation='vertical', padding=10, spacing=5,
                                  size_hint_y=None, height=120)
            record_item.canvas.before.clear()
            from kivy.graphics import Color, Rectangle
            with record_item.canvas.before:
                Color(0.9, 0.9, 0.9, 1)
                Rectangle(pos=record_item.pos, size=record_item.size)
            
            name_label = Label(text=record['name'], font_size=18, bold=True)
            info_label = Label(text=f'日期: {record['date']} | 状态: {record['status']}', font_size=14)
            
            btn_layout = BoxLayout(size_hint_y=0.3, spacing=5)
            view_btn = Button(text='查看详情', size_hint_x=0.5)
            delete_btn = Button(text='删除', size_hint_x=0.5)
            
            btn_layout.add_widget(view_btn)
            btn_layout.add_widget(delete_btn)
            
            record_item.add_widget(name_label)
            record_item.add_widget(info_label)
            record_item.add_widget(btn_layout)
            
            self.history_list.add_widget(record_item)