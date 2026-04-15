from kivy.uix.screenmanager import Screen
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.image import Image
from kivy.uix.label import Label
from kivy.uix.progressbar import ProgressBar
from kivy.clock import Clock
from kivy.core.window import Window
import os

class UploadScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.layout = BoxLayout(orientation='vertical', padding=20, spacing=20)
        
        # 标题
        title = Label(text='📤 文件上传', font_size=24, bold=True, size_hint_y=0.1)
        self.layout.add_widget(title)
        
        # 图片选择按钮
        self.select_button = Button(text='选择图片', size_hint_y=0.1)
        self.select_button.bind(on_press=self.select_image)
        self.layout.add_widget(self.select_button)
        
        # 图片显示
        self.image_display = Image(size_hint_y=0.4)
        self.layout.add_widget(self.image_display)
        
        # 分析按钮
        self.analyze_button = Button(text='开始分析', size_hint_y=0.1, disabled=True)
        self.analyze_button.bind(on_press=self.start_analysis)
        self.layout.add_widget(self.analyze_button)
        
        # 进度条
        self.progress_bar = ProgressBar(size_hint_y=0.05, value=0)
        self.layout.add_widget(self.progress_bar)
        
        # 结果显示
        self.result_label = Label(text='', size_hint_y=0.3, text_size=(Window.width - 40, None), halign='left')
        self.layout.add_widget(self.result_label)
        
        # 返回按钮
        back_button = Button(text='返回首页', size_hint_y=0.08)
        back_button.bind(on_press=lambda x: self.manager.current = 'home')
        self.layout.add_widget(back_button)
        
        self.add_widget(self.layout)
        self.image_path = None
        
    def select_image(self, instance):
        # 实现图片选择逻辑
        # 这里使用模拟路径，实际应用中需要使用文件选择器
        # 暂时使用测试图片
        test_image_path = 'img_test/MoS2-1.jpg'
        if os.path.exists(test_image_path):
            self.image_path = test_image_path
            self.image_display.source = test_image_path
            self.analyze_button.disabled = False
            self.result_label.text = f'已选择图片: {os.path.basename(test_image_path)}'
        else:
            self.result_label.text = '测试图片不存在，请手动选择图片'
    
    def start_analysis(self, instance):
        if not self.image_path:
            self.result_label.text = '请先选择图片'
            return
        
        self.result_label.text = '正在分析图片...'
        self.analyze_button.disabled = True
        
        # 模拟分析过程
        self.progress_bar.value = 0
        Clock.schedule_interval(self.update_progress, 0.1)
    
    def update_progress(self, dt):
        self.progress_bar.value += 5
        if self.progress_bar.value >= 100:
            self.progress_bar.value = 100
            self.result_label.text = '分析完成！\n\n这是一个模拟分析结果。\n在实际应用中，这里会显示AI分析的实验数据。'
            self.analyze_button.disabled = False
            return False
        return True