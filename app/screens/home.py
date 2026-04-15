from kivy.uix.screenmanager import Screen
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.scrollview import ScrollView
from kivy.uix.gridlayout import GridLayout

class HomeScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.layout = BoxLayout(orientation='vertical', padding=20, spacing=20)
        
        # 标题
        title = Label(text='晶体生长实验记录助手', font_size=30, bold=True, size_hint_y=0.1)
        self.layout.add_widget(title)
        
        # 导航按钮
        nav_layout = GridLayout(cols=2, spacing=10, size_hint_y=0.2)
        upload_btn = Button(text='📤 文件上传', font_size=18)
        upload_btn.bind(on_press=lambda x: self.manager.current = 'upload')
        history_btn = Button(text='📚 历史记录', font_size=18)
        history_btn.bind(on_press=lambda x: self.manager.current = 'history')
        stats_btn = Button(text='📊 统计信息', font_size=18)
        stats_btn.bind(on_press=lambda x: self.manager.current = 'stats')
        
        nav_layout.add_widget(upload_btn)
        nav_layout.add_widget(history_btn)
        nav_layout.add_widget(stats_btn)
        
        self.layout.add_widget(nav_layout)
        
        # 项目介绍
        scroll = ScrollView(size_hint_y=0.7)
        content = BoxLayout(orientation='vertical', spacing=10, size_hint_y=None)
        content.bind(minimum_height=content.setter('height'))
        
        intro_title = Label(text='📋 项目简介', font_size=20, bold=True)
        intro_text = Label(text='这是一个基于 Multi-Agent 的实验记录数字化工具，专为晶体生长实验设计。通过先进的AI技术，将手写实验记录转化为结构化的数字数据，提高实验数据管理的效率和准确性。',
                          font_size=16, text_size=(self.width - 40, None), halign='left')
        
        features_title = Label(text='✨ 核心功能', font_size=20, bold=True)
        features = BoxLayout(orientation='vertical', spacing=5)
        features.add_widget(Label(text='🤖 视觉感知：使用 Qwen-VL 模型分析实验记录图片，自动提取实验数据', font_size=14))
        features.add_widget(Label(text='🔬 化学审核：Qwen-Plus 模型审核提取的数据，确保化学合理性和准确性', font_size=14))
        features.add_widget(Label(text='📝 数据格式化：将数据转换为标准化的 Markdown 报告', font_size=14))
        
        content.add_widget(intro_title)
        content.add_widget(intro_text)
        content.add_widget(features_title)
        content.add_widget(features)
        
        scroll.add_widget(content)
        self.layout.add_widget(scroll)
        
        self.add_widget(self.layout)