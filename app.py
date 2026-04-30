import streamlit as st
import os
import tempfile
import base64
import json
import shutil
import hashlib
import re
from PIL import Image
from pathlib import Path
import pandas as pd
import plotly.express as px
from datetime import datetime
import threading
import time

from agent import create_lab_agent_graph, generate_markdown
from database import get_db


# ================= 页面配置 =================
st.set_page_config(
    page_title="晶体生长实验记录助手",
    page_icon="⚗️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ================= 后台任务处理器 =================
class TaskWorker:
    def __init__(self):
        self.running = True
        self.db = get_db()
    
    def run(self):
        while self.running:
            try:
                tasks = self.db.get_pending_tasks(limit=3)
                for task in tasks:
                    self.process_task(task)
            except Exception as e:
                print(f"Task worker error: {e}")
            time.sleep(3)
    
    def stop(self):
        self.running = False
    
    def process_task(self, task):
        try:
            task_id = task['task_id']
            image_filename = task['image_filename']
            image_bytes = task['image_bytes']
            
            self.db.update_task_status(task_id, 'processing', progress=0, current_step='初始化')
            
            with tempfile.TemporaryDirectory() as temp_dir:
                temp_img_path = os.path.join(temp_dir, image_filename)
                with open(temp_img_path, 'wb') as f:
                    f.write(image_bytes)
            
                output_md_path = os.path.join(temp_dir, "output.md")
            
                agent = create_lab_agent_graph()
            
                # 检查任务是否有之前的人工反馈（即审批失败后重新处理的任务）
                task_has_human_feedback = task.get('human_feedback', '')
                initial_state = {
                    "image_path": temp_img_path,
                    "image_reference_path": image_filename,
                    "output_path": output_md_path,
                    "raw_json": task.get('raw_json', ''),  # 如果有之前的处理结果，保留
                    "reviewed_json": task.get('reviewed_json', ''),
                    "formatted_markdown": task.get('formatted_markdown', ''),
                    "needs_correction": bool(task_has_human_feedback != ''),
                    "correction_hints": task_has_human_feedback,  # 将人工反馈作为修正提示
                    "iteration_count": task.get('iteration_count', 0),
                    "max_iterations": st.session_state.get('max_iter', 3),
                    "review_issues": [],
                    "review_passed": False,
                    "human_feedback": task_has_human_feedback,
                    "needs_human_review": False,
                    "messages": []
                }
            
                self.db.update_task_status(task_id, 'processing', progress=25, current_step='视觉感知')
            
                config = {"configurable": {"thread_id": "task-worker"}}
                final_state = None
            
                for event in agent.stream(initial_state, config):
                    for node_name, node_state in event.items():
                        if node_name == "__end__":
                            final_state = node_state
                            break
                        final_state = node_state
            
                        if node_name == "perceiver":
                            self.db.update_task_status(task_id, 'processing', progress=33, current_step='视觉感知')
                        elif node_name == "reviewer":
                            self.db.update_task_status(task_id, 'processing', progress=66, current_step='化学审核')
                        elif node_name == "formatter":
                            self.db.update_task_status(task_id, 'processing', progress=85, current_step='生成报告')
                        elif node_name == "human_review":
                            self.db.update_task_status(task_id, 'processing', progress=95, current_step='准备审核')
            
                self.db.update_task_status(task_id, 'processing', progress=98, current_step='准备待审批')
            
                if final_state:
                    import json
                    review_issues_json = json.dumps(final_state.get("review_issues", []), ensure_ascii=False)
                    
                    # 检查是否需要人工审核
                    needs_human_review = final_state.get("needs_human_review", True)  # 默认需要人工审核
                    
                    if needs_human_review:
                        # 需要人工审核，进入待审批队列
                        self.db.update_task_status(
                            task_id, 
                            'pending_review', 
                            progress=100, 
                            current_step='待审批',
                            raw_json=final_state.get("raw_json", ""),
                            reviewed_json=final_state.get("reviewed_json", ""),
                            formatted_markdown=final_state.get("formatted_markdown", ""),
                            iteration_count=final_state.get("iteration_count", 0),
                            max_iterations=final_state.get("max_iterations", 3),
                            review_issues=review_issues_json
                        )
                        print(f"[OK] [TaskWorker] 任务 {task_id} 已进入待审批队列")
                    else:
                        # 无需人工审核（已通过人工审核覆盖），直接完成并入库
                        # 获取包含图片字节的完整任务数据
                        task_with_image = self.db.get_task(task_id, include_image_bytes=True)
                        # 直接入库到 experiments 表
                        experiment_id = self.db.save_experiment(
                            image_filename=task_with_image['image_filename'],
                            image_bytes=task_with_image.get('image_bytes'),
                            image_path=None,
                            image_reference_path=task_with_image['image_filename'],
                            raw_json=final_state.get('raw_json', ''),
                            reviewed_json=final_state.get('reviewed_json', ''),
                            formatted_markdown=final_state.get('formatted_markdown', ''),
                            iteration_count=final_state.get('iteration_count', 0),
                            max_iterations=final_state.get('max_iterations', 3),
                            review_passed=True,
                            review_issues=final_state.get('review_issues', []),
                            human_feedback='自动审批通过',
                            review_passed_override=True
                        )
                        # 更新任务状态为 completed 并标记已入库
                        self.db.update_task_status(
                            task_id, 
                            'completed', 
                            progress=100, 
                            current_step='已入库',
                            experiment_id=experiment_id,
                            raw_json=final_state.get("raw_json", ""),
                            reviewed_json=final_state.get("reviewed_json", ""),
                            formatted_markdown=final_state.get("formatted_markdown", ""),
                            iteration_count=final_state.get("iteration_count", 0),
                            max_iterations=final_state.get("max_iterations", 3),
                            review_issues=review_issues_json
                        )
                        print(f"[OK] [TaskWorker] 任务 {task_id} 处理完成并已入库，experiment_id={experiment_id}")
                else:
                    self.db.update_task_status(
                        task_id, 
                        'failed', 
                        error_message='处理过程中未获取到最终状态'
                    )
        
        except Exception as e:
            import traceback
            error_msg = f"{type(e).__name__}: {str(e)}\n{traceback.format_exc()}"
            self.db.update_task_status(task_id, 'failed', error_message=error_msg)

# 启动后台任务处理器
worker = TaskWorker()
worker_thread = threading.Thread(target=worker.run, daemon=True)
worker_thread.start()

# ================= 全局变量 =================
# 用于存储当前查看详情的实验ID
current_detail_exp_id = None

# ================= 自定义CSS =================
def add_custom_css():
    st.markdown("""
    <style>
        /* 整体样式 */
        body {
            background-color: #f0f2f6;
        }
        
        /* 标题样式 */
        .main-title {
            font-size: 2.5rem;
            font-weight: bold;
            color: #2c3e50;
            text-align: center;
            margin-bottom: 2rem;
            text-shadow: 2px 2px 4px rgba(0,0,0,0.1);
        }
        
        /* 卡片样式 */
        .card {
            background: white;
            border-radius: 12px;
            box-shadow: 0 4px 6px rgba(0,0,0,0.1);
            padding: 20px;
            margin-bottom: 20px;
            transition: transform 0.3s ease, box-shadow 0.3s ease;
        }
        
        .card:hover {
            transform: translateY(-5px);
            box-shadow: 0 10px 20px rgba(0,0,0,0.1);
        }
        
        /* 悬浮框样式 */
        .float-box {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            border-radius: 16px;
            padding: 25px;
            box-shadow: 0 10px 25px rgba(0,0,0,0.2);
            margin: 20px 0;
        }
        
        /* 按钮样式 */
        .stButton > button {
            border-radius: 8px;
            padding: 10px 20px;
            font-weight: bold;
            transition: all 0.3s ease;
        }
        
        .stButton > button:hover {
            transform: scale(1.05);
        }
        
        /* 标签页样式 */
        .stTabs [data-baseweb="tab-list"] {
            gap: 10px;
        }
        
        .stTabs [data-baseweb="tab"] {
            height: 48px;
            padding: 0 24px;
            border-radius: 8px 8px 0 0;
            font-weight: 600;
        }
        
        .stTabs [data-baseweb="tab"][aria-selected="true"] {
            background-color: #667eea;
            color: white;
        }
        
        /* 进度条样式 */
        .stProgress > div > div {
            background-color: #667eea;
        }
        
        /* 卡片标题样式 */
        .card-title {
            font-size: 1.5rem;
            font-weight: bold;
            color: #2c3e50;
            margin-bottom: 1rem;
        }
        
        /* 流程图样式 */
        .flow-step {
            background: #f8f9fa;
            border-radius: 8px;
            padding: 15px;
            margin: 10px 0;
            border-left: 4px solid #667eea;
        }
        
        /* 统计图表容器 */
        .chart-container {
            background: white;
            border-radius: 12px;
            box-shadow: 0 4px 6px rgba(0,0,0,0.1);
            padding: 20px;
            margin-bottom: 20px;
        }
    </style>
    """, unsafe_allow_html=True)

# 添加自定义CSS
add_custom_css()

# ================= 初始化 =================
# 创建必要的目录
STORAGE_DIR = Path("storage")
STORAGE_DIR.mkdir(exist_ok=True)
IMAGES_DIR = STORAGE_DIR / "images"
IMAGES_DIR.mkdir(exist_ok=True)

# ================= 辅助函数 =================
def save_experiment_to_db(final_state: dict, file_name_to_use: str, image_bytes: bytes, image_path: str = None):
    """保存实验记录到数据库"""

    try:
        print(f"[INFO] [DEBUG] save_experiment_to_db 开始")
        print(f"  - file_name_to_use: {file_name_to_use}")
        print(f"  - image_bytes 长度: {len(image_bytes) if image_bytes else 0}")
        print(f"  - image_path: {image_path}")
        print(f"  - final_state keys: {list(final_state.keys())}")
        
        # 检查关键字段
        has_raw_json = "raw_json" in final_state and final_state["raw_json"]
        has_reviewed_json = "reviewed_json" in final_state and final_state["reviewed_json"]
        has_markdown = "formatted_markdown" in final_state and final_state["formatted_markdown"]
        print(f"  - 有 raw_json: {has_raw_json}")
        print(f"  - 有 reviewed_json: {has_reviewed_json}")
        print(f"  - 有 formatted_markdown: {has_markdown}")
        
        db = get_db()
        print(f"  [OK] 数据库连接成功")
        
        # 保存图片到持久化目录
        if image_bytes:
            image_hash = hashlib.sha256(image_bytes).hexdigest()[:16]
            image_ext = Path(file_name_to_use).suffix or ".jpg"
            saved_image_filename = f"{image_hash}{image_ext}"
            saved_image_path = IMAGES_DIR / saved_image_filename
            print(f"  - 保存图片到: {saved_image_path}")
        
            # 如果图片不存在，保存它
            if not saved_image_path.exists():
                with open(saved_image_path, "wb") as f:
                    f.write(image_bytes)
                print(f"  [OK] 图片保存成功")
            else:
                print(f"  ℹ️ 图片已存在，跳过保存")
        
            image_reference_path = f"storage/images/{saved_image_filename}"
        else:
            saved_image_path = None
            image_reference_path = None
            print(f"  [WARN] 没有图片数据")
        
        # 检查是否已存在相同图片的记录
        image_hash_for_check = hashlib.sha256(image_bytes).hexdigest() if image_bytes else ""
        existing_record = db._check_existing_by_hash(image_hash_for_check) if image_hash_for_check else None
        
        # 如果存在相同图片的记录，生成新的文件名（添加时间戳）
        final_file_name = file_name_to_use
        if existing_record:
            print(f"  [WARN] 发现重复记录 (ID: {existing_record['id']})，将重命名文件")
            # 生成带时间戳的新文件名
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            file_stem = Path(file_name_to_use).stem
            file_ext = Path(file_name_to_use).suffix or ".jpg"
            final_file_name = f"{file_stem}_{timestamp}{file_ext}"
            print(f"  - 新文件名: {final_file_name}")
        
        # 保存到数据库
        print(f"  📥 调用 db.save_experiment...")
        experiment_id = db.save_experiment(
            image_filename=final_file_name,  # 使用可能重命名后的文件名
            image_bytes=image_bytes,
            image_path=str(saved_image_path) if saved_image_path else image_path,
            image_reference_path=image_reference_path,
            raw_json=final_state.get("raw_json", ""),
            reviewed_json=final_state.get("reviewed_json", ""),
            formatted_markdown=final_state.get("formatted_markdown", ""),
            iteration_count=final_state.get("iteration_count", 0),
            max_iterations=final_state.get("max_iterations", 3),
            review_passed=final_state.get("review_passed_override") if final_state.get("review_passed_override") is not None else final_state.get("review_passed", False),
            review_issues=final_state.get("review_issues", []),
            human_feedback=final_state.get("human_feedback", ""),
            review_passed_override=final_state.get("review_passed_override"),
            force_new=True  # 强制插入新记录
        )
        print(f"  [OK] db.save_experiment 返回: {experiment_id}")
        
        # 保存反馈历史
        feedback_history = st.session_state.get('feedback_history', [])
        print(f"  - 反馈历史记录数: {len(feedback_history)}")
        for feedback in feedback_history:
            db.add_feedback(experiment_id, feedback, "human")
        
        print(f"[OK] [DEBUG] save_experiment_to_db 完成，experiment_id={experiment_id}")
        return experiment_id
    except Exception as e:
        print(f"[ERROR] [DEBUG] save_experiment_to_db 失败: {type(e).__name__}: {str(e)}")
        import traceback
        print(f"   详细错误: {traceback.format_exc()}")
        st.error(f"保存到数据库失败: {str(e)}")
        st.code(traceback.format_exc())
        return None

# ================= 主标签页 =================
tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs(["🏠 首页", "📤 文件上传", "🔄 待审批", "📚 历史记录", "[STATS] 统计信息" , "💬 知识问答" ])

# 全局变量
api_key_input = ""
max_iter = 1

# 初始化数据库连接
db = get_db()

# 首页
with tab1:
    st.markdown("<h3 class='main-title'>[INFO] 晶体生长实验记录助手</h3>", unsafe_allow_html=True)
    
    # 悬浮框：API Key 和最大修正次数设置
    with st.container():
        st.markdown("<div class='float-box'>", unsafe_allow_html=True)
        st.subheader("⚙️ 系统设置")
        
        # API Key 单独占一行
        api_key_input = st.text_input(
            "DashScope API Key", 
            type="password", 
            help="输入你的阿里云 DashScope API Key。如果留空，将尝试使用环境变量。",
            value=os.getenv("DASHSCOPE_API_KEY", "")
        )
        
        if api_key_input:
            os.environ["DASHSCOPE_API_KEY"] = api_key_input
        
        # 最大修正次数单独占一行
        if 'max_iter' not in st.session_state:
            st.session_state['max_iter'] = 3
        max_iter = st.slider("最大自修正次数", 1, 5, st.session_state['max_iter'], key="max_iter_slider")
        st.session_state['max_iter'] = max_iter
        
        st.markdown("</div>", unsafe_allow_html=True)
    
    # 项目介绍
    st.markdown("<div class='card'>", unsafe_allow_html=True)
    st.markdown("<h2 class='card-title'>📋 项目简介</h2>", unsafe_allow_html=True)
    st.markdown("""
    这是一个基于 Multi-Agent 的实验记录数字化工具，专为晶体生长实验设计。通过先进的AI技术，将手写实验记录转化为结构化的数字数据，提高实验数据管理的效率和准确性。
    """)
    st.markdown("</div>", unsafe_allow_html=True)
    
    # 核心功能
    st.markdown("<div class='card'>", unsafe_allow_html=True)
    st.markdown("<h2 class='card-title'>✨ 核心功能</h2>", unsafe_allow_html=True)
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.markdown("<div class='flow-step'>", unsafe_allow_html=True)
        st.subheader("🤖 视觉感知")
        st.write("使用 Qwen-VL 模型分析实验记录图片，自动提取实验数据。")
        st.markdown("</div>", unsafe_allow_html=True)
    
    with col2:
        st.markdown("<div class='flow-step'>", unsafe_allow_html=True)
        st.subheader("[LAB] 化学审核")
        st.write("Qwen-Plus 模型审核提取的数据，确保化学合理性和准确性。")
        st.markdown("</div>", unsafe_allow_html=True)
    
    with col3:
        st.markdown("<div class='flow-step'>", unsafe_allow_html=True)
        st.subheader("📝 数据格式化")
        st.write("Pymatgen 库将数据转换为标准化的 Markdown 报告。")
        st.markdown("</div>", unsafe_allow_html=True)
    st.markdown("</div>", unsafe_allow_html=True)
    
    # 工作流程
    st.markdown("<div class='card'>", unsafe_allow_html=True)
    st.markdown("<h2 class='card-title'>🔄 工作流程</h2>", unsafe_allow_html=True)
    
    st.markdown("<div class='flow-step'>", unsafe_allow_html=True)
    st.subheader("1. 上传实验记录")
    st.write("上传手写实验记录图片，支持 JPG、PNG 格式。")
    st.markdown("</div>", unsafe_allow_html=True)
    
    st.markdown("<div class='flow-step'>", unsafe_allow_html=True)
    st.subheader("2. AI 数据分析")
    st.write("视觉感知模型提取数据，化学审核模型验证合理性。")
    st.markdown("</div>", unsafe_allow_html=True)
    
    st.markdown("<div class='flow-step'>", unsafe_allow_html=True)
    st.subheader("3. 人工审核")
    st.write("用户审核提取结果，可提供反馈进行修正。")
    st.markdown("</div>", unsafe_allow_html=True)
    
    st.markdown("<div class='flow-step'>", unsafe_allow_html=True)
    st.subheader("4. 生成报告")
    st.write("系统生成标准化的 Markdown 实验报告。")
    st.markdown("</div>", unsafe_allow_html=True)
    st.markdown("</div>", unsafe_allow_html=True)
    
    # 技术特点
    st.markdown("<div class='card'>", unsafe_allow_html=True)
    st.markdown("<h2 class='card-title'>🚀 技术特点</h2>", unsafe_allow_html=True)
    
    st.markdown("- **多智能体协作**: 三个专业智能体协同工作，确保数据准确性")
    st.markdown("- **自修正机制**: 发现问题自动修正，提高数据提取质量")
    st.markdown("- **化学专业审核**: 确保实验数据的化学合理性")
    st.markdown("- **标准化报告**: 生成结构清晰的 Markdown 报告")
    st.markdown("- **历史记录管理**: 完整的实验记录存储和查询功能")
    st.markdown("</div>", unsafe_allow_html=True)

# 文件上传页
with tab2:
    st.markdown("<h1 class='main-title'>📤 文件上传</h1>", unsafe_allow_html=True)
    st.markdown("上传实验记录本的手写图片，AI 将自动提取数据、校验化学合理性并生成 Markdown 报告。")
    st.markdown("**支持同时上传多张图片，后台自动并行处理**")
    
    uploaded_files = st.file_uploader(
        "📤 上传图片 (支持多选 JPG, PNG)", 
        type=["jpg", "jpeg", "png"],
        accept_multiple_files=True
    )

    # 上传按钮 - 点击后创建任务
    if uploaded_files and st.button("🚀 开始上传并处理", type="primary"):
        # 创建任务列表
        task_ids = []
        for uploaded_file in uploaded_files:
            file_bytes = uploaded_file.getvalue()
            task_id = db.create_processing_task(uploaded_file.name, file_bytes)
            task_ids.append(task_id)
        st.success(f"已创建 {len(task_ids)} 个任务，后台正在处理...")
        # 刷新页面显示任务状态
        st.rerun()

    # 显示任务列表
    st.markdown("---")
    st.subheader("📋 任务列表")
    
    tasks = db.get_processing_tasks(limit=20)
    
    if tasks:
        selected_tasks = []
        
        col_select_all = st.columns([1])
        with col_select_all[0]:
            select_all = st.checkbox("全选", key="select_all")
        
        for task in tasks:
            with st.container():
                col_select, col_task_info, col_task_status = st.columns([0.3, 2, 1.5])
                with col_select:
                    if select_all:
                        selected = st.checkbox("", value=True, key=f"select_{task['task_id']}")
                    else:
                        selected = st.checkbox("", key=f"select_{task['task_id']}")
                    if selected:
                        selected_tasks.append(task['task_id'])
                
                with col_task_info:
                    st.markdown(f"**📄 {task['image_filename']}**")
                    st.markdown(f"创建时间: {task['created_at']}")
                with col_task_status:
                    status = task['status']
                    if status == 'pending':
                        st.status("⏳ 待处理", state="running")
                    elif status == 'processing':
                        st.progress(task['progress'], text=f"处理中: {task['current_step']}")
                    elif status == 'pending_review':
                        st.status("[OK] 处理完成，待审批", state="complete")
                        st.info("请切换到「🔄 待审批」标签页进行审核")
                    elif status == 'completed':
                        st.status("[OK] 已入库", state="success")
                        st.info("记录已保存到实验数据库")
                    elif status == 'failed':
                        st.status("[ERROR] 处理失败", state="error")
                        st.error(task.get('error_message', '未知错误'))
                        if st.button("🔄 重新处理", key=f"retry_{task['task_id']}"):
                            db.update_task_status(task['task_id'], 'pending', progress=0)
                            st.rerun()
                
                st.markdown("---")
        
        if selected_tasks:
            col_delete_selected = st.columns([1])
            with col_delete_selected[0]:
                confirm_key = f"confirm_delete_{'-'.join(selected_tasks)}"
                if confirm_key not in st.session_state:
                    st.session_state[confirm_key] = False
                
                if st.session_state[confirm_key]:
                    st.warning(f"确定要删除选中的 {len(selected_tasks)} 个任务吗？此操作不可撤销。")
                    col_confirm, col_cancel = st.columns([1, 1])
                    with col_confirm:
                        if st.button("[OK] 确认删除", key=f"confirm_btn_{confirm_key}", use_container_width=True):
                            for task_id in selected_tasks:
                                db.delete_task(task_id)
                            st.success(f"已成功删除 {len(selected_tasks)} 个任务")
                            st.session_state[confirm_key] = False
                            st.rerun()
                    with col_cancel:
                        if st.button("[ERROR] 取消", key=f"cancel_btn_{confirm_key}", use_container_width=True):
                            st.session_state[confirm_key] = False
                            st.rerun()
                else:
                    if st.button(f"🗑️ 删除选中的 {len(selected_tasks)} 个任务", type="primary", use_container_width=True):
                        st.session_state[confirm_key] = True
                        st.rerun()
    else:
        st.info("暂无任务，请上传图片开始处理")

    # 原有单文件处理逻辑（保持兼容）
    uploaded_file = uploaded_files[0] if uploaded_files else None
    
    if uploaded_file is not None:
        st.session_state['uploaded_file_name'] = uploaded_file.name
        st.session_state['uploaded_file_bytes'] = uploaded_file.getvalue()

    col1, col2 = st.columns([1, 1])

    has_processing_state = (
        st.session_state.get('human_review_completed', False) or 
        st.session_state.get('restart_processing', False) or
        st.session_state.get('needs_human_review', False)
    )

    if uploaded_file is not None or has_processing_state:
        # 显示图片：优先使用上传的文件，如果没有则使用 session state 中保存的
        if uploaded_file is not None:
            image = Image.open(uploaded_file)
            image_to_show = image
            file_name_to_use = uploaded_file.name
        elif st.session_state.get('uploaded_file_bytes'):
            import io
            image = Image.open(io.BytesIO(st.session_state.get('uploaded_file_bytes')))
            image_to_show = image
            file_name_to_use = st.session_state.get('uploaded_file_name', 'uploaded_image.jpg')
        else:
            image_to_show = None
            file_name_to_use = st.session_state.get('uploaded_file_name', 'image.jpg')
        
        if image_to_show:
            with col1:
                st.markdown("<div class='card'>", unsafe_allow_html=True)
                st.subheader("🖼️ 原始记录")
                st.image(image_to_show, use_container_width=True)
                st.markdown("</div>", unsafe_allow_html=True)

        # ================= 重新处理逻辑（如果审核不通过） =================
        if st.session_state.get('restart_processing', False):
            restart_state = st.session_state.get('restart_state', {})
            agent = st.session_state.get('restart_agent')
            config = st.session_state.get('restart_config')
            
            # 如果 agent 不存在，重新创建（因为 agent 对象可能无法正确序列化到 session_state）
            if not agent:
                try:
                    agent = create_lab_agent_graph()
                    config = {"configurable": {"thread_id": "streamlit-user"}}
                except Exception as e:
                    st.error(f"无法创建 Agent: {str(e)}")
                    st.stop()
            
            if agent and restart_state:
                # 清除重新处理标记
                st.session_state['restart_processing'] = False
                st.session_state['restart_state'] = None
                st.session_state['restart_agent'] = None
                st.session_state['restart_config'] = None
                
                # 检查并重新创建临时文件（如果 image_path 指向的文件不存在）
                image_path = restart_state.get("image_path", "")
                if not image_path or not os.path.exists(image_path):
                    # 如果临时文件不存在，从 session_state 中恢复文件
                    if st.session_state.get('uploaded_file_bytes'):
                        # 创建临时目录（不使用 with，因为我们需要在整个处理过程中保持它）
                        temp_dir = tempfile.mkdtemp()
                        file_name_to_use = st.session_state.get('uploaded_file_name', 'image.jpg')
                        new_image_path = os.path.join(temp_dir, file_name_to_use)
                        with open(new_image_path, "wb") as f:
                            f.write(st.session_state.get('uploaded_file_bytes'))
                        # 更新 restart_state 中的 image_path
                        restart_state["image_path"] = new_image_path
                        restart_state["image_reference_path"] = file_name_to_use
                        # 保存临时目录路径，以便后续清理
                        st.session_state['temp_dir_for_restart'] = temp_dir
                    else:
                        st.error("无法重新处理：图片文件已丢失")
                        st.stop()
                
                # 显示重新处理提示
                with col2:
                    st.info("🔄 根据您的反馈，正在重新处理...")
                
                # 重新从 perceiver 开始处理
                try:
                    # 使用流式 API 重新处理
                    progress_container = col2.container()
                    with progress_container:
                        st.markdown("<div class='card'>", unsafe_allow_html=True)
                        st.markdown("### 🔄 重新处理进度")
                        
                        progress_bar = st.progress(0)
                        status_placeholder = st.empty()
                        log_placeholder = st.empty()
                        
                        execution_logs = []
                        final_state = None
                        
                        # 增加递归限制，避免无限循环
                        config_with_limit = {**config, "recursion_limit": 50}
                        
                        for event in agent.stream(restart_state, config_with_limit):
                            for node_name, node_state in event.items():
                                if node_name == "__end__":
                                    final_state = node_state
                                    break
                                
                                state = node_state
                                final_state = state
                                
                                # 更新进度
                                node_order = ["perceiver", "reviewer", "formatter", "human_review"]
                                if node_name in node_order:
                                    progress = (node_order.index(node_name) + 1) / len(node_order)
                                    progress_bar.progress(progress)
                                    status_placeholder.markdown(f"**当前步骤**: {node_name}")
                                
                                # 添加日志
                                if node_name == "perceiver":
                                    execution_logs.append({
                                        "icon": "🔄",
                                        "message": "根据人工反馈重新分析图片...",
                                        "type": "info"
                                    })
                                elif node_name == "reviewer":
                                    execution_logs.append({
                                        "icon": "[LAB]",
                                        "message": "正在重新审核数据...",
                                        "type": "info"
                                    })
                                elif node_name == "formatter":
                                    execution_logs.append({
                                        "icon": "📝",
                                        "message": "正在生成报告...",
                                        "type": "info"
                                    })
                                elif node_name == "human_review":
                                    # 如果到达人工审核节点，保存状态以便后续处理
                                    needs_human_review = state.get("needs_human_review", False)
                                    if needs_human_review:
                                        execution_logs.append({
                                            "icon": "👤",
                                            "message": "重新处理完成，等待人工审核确认",
                                            "type": "info"
                                        })
                                        # 保存状态到 session state，用于后续处理
                                        st.session_state['needs_human_review'] = True
                                        st.session_state['human_review_state'] = state
                                        st.session_state['agent'] = agent
                                        st.session_state['config'] = config_with_limit
                                
                                # 更新日志显示
                                log_html = "<div style='max-height: 300px; overflow-y: auto; padding: 10px; background-color: #f8f9fa; border-radius: 5px;'>"
                                for log in execution_logs[-10:]:
                                    icon = log["icon"]
                                    msg = log["message"]
                                    log_type = log["type"]
                                    
                                    color = "#17a2b8"
                                    bg_color = "#d1ecf1"
                                    
                                    log_html += f"<div style='margin: 5px 0; padding: 8px 12px; background-color: {bg_color}; color: {color}; border-radius: 4px;'><strong>{icon}</strong> {msg}</div>"
                                
                                log_html += "</div>"
                                log_placeholder.markdown(log_html, unsafe_allow_html=True)
                        
                        progress_bar.progress(1.0)
                        status_placeholder.markdown("**[OK] 重新处理完成！**")
                        st.markdown("</div>", unsafe_allow_html=True)
                        
                        # 保存最终状态：无论审核是否通过，都应该交由人工审核
                        if final_state:
                            # 修改逻辑：无论审核是否通过，都应该进入人工审核
                            # 确保清除之前的反馈，让 human_review_node 能够再次触发
                            final_state['human_feedback'] = ""
                            final_state['review_passed_override'] = None
                            st.session_state['needs_human_review'] = True
                            st.session_state['human_review_state'] = final_state
                            st.session_state['agent'] = agent
                            st.session_state['config'] = config_with_limit
                            # 设置标志，表示这是新的审核会话，需要清除输入框
                            st.session_state['clear_feedback_on_next_review'] = True
                            # 清理临时目录（如果存在）
                            if st.session_state.get('temp_dir_for_restart'):
                                try:
                                    shutil.rmtree(st.session_state.get('temp_dir_for_restart'))
                                except:
                                    pass
                                st.session_state['temp_dir_for_restart'] = None
                            # 处理完成，重置处理中标志
                            st.session_state['is_processing'] = False
                            st.rerun()
                            
                except Exception as e:
                    st.error(f"重新处理时出错: {str(e)}")
                    import traceback
                    st.code(traceback.format_exc())
                    # 处理出错，重置处理中标志
                    st.session_state['is_processing'] = False
        
        # ================= 人工审核界面（优先检查，在按钮点击外部） =================
        # 检查是否需要人工审核（必须在按钮点击代码块外部，确保页面重新运行时也能显示）
        needs_human_review = st.session_state.get('needs_human_review', False)
        if needs_human_review:
            # 获取当前的 review_state
            current_review_state = st.session_state.get('human_review_state', {})
            
            # 使用审核会话计数器来生成唯一的 key，确保每次新审核会话都使用新的 key
            # 初始化审核会话计数器
            if 'review_session_counter' not in st.session_state:
                st.session_state['review_session_counter'] = 0
            
            # 检查是否需要清除输入框（重新处理完成后设置的标志）
            if st.session_state.get('clear_feedback_on_next_review', False):
                # 增加审核会话计数器，这样会使用新的 key
                st.session_state['review_session_counter'] = st.session_state.get('review_session_counter', 0) + 1
                # 清除标志
                st.session_state['clear_feedback_on_next_review'] = False
            
            # 获取当前的会话计数器
            session_counter = st.session_state.get('review_session_counter', 0)
            
            # 清空进度显示区域
            with col2:
                st.empty()  # 清空之前的进度显示
            
            with col2:
                st.markdown("<div class='card'>", unsafe_allow_html=True)
                st.markdown("---")
                st.info("👤 **人工审核**")
                st.markdown("自修正循环已完成，请查看提取的数据和审核结果，决定是否通过或需要进一步修改。")
                
                review_state = current_review_state
                review_issues = review_state.get("review_issues", [])
                iteration_count = review_state.get("iteration_count", 0)
                
                # 显示统计信息
                st.markdown("### [STATS] 审核概览")
                col_stat1, col_stat2 = st.columns(2)
                with col_stat1:
                    st.metric("迭代次数", f"{iteration_count} / {max_iter}")
                with col_stat2:
                    st.metric("发现问题", f"{len(review_issues)} 个")
                
                # 显示问题详情
                st.markdown("### [INFO] 发现的问题")
                
                if review_issues:
                    # 按严重程度分组
                    errors = [i for i in review_issues if i.get("severity") == "error"]
                    warnings = [i for i in review_issues if i.get("severity") == "warning"]
                    infos = [i for i in review_issues if i.get("severity") == "info"]
                    
                    if errors:
                        st.markdown("#### [ERROR] 严重错误")
                        for idx, issue in enumerate(errors, 1):
                            with st.expander(f"错误 #{idx}: {issue.get('description', '')[:60]}...", expanded=idx==1):
                                st.error(f"**描述**: {issue.get('description', '-')}")
                                if issue.get('field'):
                                    st.code(f"字段: {issue.get('field')}")
                                if issue.get('suggestion'):
                                    st.info(f"💡 **建议**: {issue.get('suggestion')}")
                    
                    if warnings:
                        st.markdown("#### [WARN] 警告")
                        for idx, issue in enumerate(warnings, 1):
                            with st.expander(f"警告 #{idx}: {issue.get('description', '')[:60]}...", expanded=False):
                                st.warning(f"**描述**: {issue.get('description', '-')}")
                                if issue.get('field'):
                                    st.code(f"字段: {issue.get('field')}")
                                if issue.get('suggestion'):
                                    st.info(f"💡 **建议**: {issue.get('suggestion')}")
                    
                    if infos:
                        st.markdown("#### ℹ️ 信息提示")
                        for idx, issue in enumerate(infos, 1):
                            st.info(f"**{idx}.** {issue.get('description', '-')}")
                
                # 人工审核表单
                st.markdown("### 👤 人工审核决策")
                
                # 审核选项（使用动态 key，基于会话计数器）
                review_decision = st.radio(
                    "请选择审核结果：",
                    ["[OK] 通过审核，继续生成报告", "[ERROR] 不通过，需要重新处理"],
                    key=f"review_decision_{session_counter}",
                    index=0
                )
                
                # 初始化反馈历史（如果不存在）
                if 'feedback_history' not in st.session_state:
                    st.session_state['feedback_history'] = []
                
                # 显示历史反馈
                if st.session_state['feedback_history']:
                    st.markdown("#### 📝 历史反馈记录")
                    with st.expander("查看之前的反馈内容", expanded=False):
                        for idx, prev_feedback in enumerate(st.session_state['feedback_history'], 1):
                            st.markdown(f"**反馈 #{idx}:")
                            st.info(prev_feedback)
                            st.markdown("---")
                
                # 反馈输入（使用动态 key，基于会话计数器，确保每次新会话都是空的）
                feedback_text = st.text_area(
                    "审核反馈（可选）：",
                    placeholder="请输入您的审核意见或说明...\n注意：新的反馈会自动累积到之前的反馈中。",
                    key=f"human_feedback_text_{session_counter}",
                    height=100,
                    value=""  # 明确设置为空字符串
                )
                
                # 提交按钮
                if st.button("[OK] 提交审核", type="primary", use_container_width=True):
                    # 更新状态
                    review_state = st.session_state.get('human_review_state', {})
                    review_passed = review_decision.startswith("[OK]")
                    
                    # 调试信息
                    print(f"[INFO] [审核提交] 开始")
                    print(f"  - review_passed: {review_passed}")
                    print(f"  - review_state keys: {list(review_state.keys())}")
                    print(f"  - review_state.get('raw_json') 长度: {len(review_state.get('raw_json', ''))}")
                    print(f"  - review_state.get('reviewed_json') 长度: {len(review_state.get('reviewed_json', ''))}")
                    print(f"  - review_state.get('formatted_markdown') 长度: {len(review_state.get('formatted_markdown', ''))}")
                    
                    # 构建反馈信息
                    feedback = feedback_text if feedback_text else (
                        "人工审核通过" if review_passed else "人工审核未通过"
                    )
                    print(f"  - feedback: {feedback[:50]}...")
                    
                    # 如果审核不通过且有新反馈，将反馈追加到历史中
                    if not review_passed and feedback_text:
                        st.session_state['feedback_history'].append(feedback_text)
                        # 注意：由于使用了动态 key，不需要手动清除，下次会自动使用新的 key
                    
                    if review_passed:
                        # 审核通过，标记完成（实际保存到历史记录需要在待审批页面完成）
                        updated_state = {
                            **review_state,
                            "human_feedback": feedback,
                            "review_passed_override": review_passed,
                            "needs_human_review": False
                        }
                        print(f"  - updated_state['review_passed_override']: {updated_state.get('review_passed_override')}")
                        
                        # 清除反馈历史（审核通过后不再需要）
                        if 'feedback_history' in st.session_state:
                            st.session_state['feedback_history'] = []
                        
                        # 保存更新后的状态，用于后续显示
                        st.session_state['human_review_completed'] = True
                        st.session_state['final_state_after_review'] = updated_state
                        st.session_state['needs_human_review'] = False
                        
                        # 重新运行以显示结果
                        st.rerun()
                    else:
                        # 审核不通过，根据反馈重新处理
                        # 将反馈信息作为修正提示，重新从 perceiver 开始
                        agent = st.session_state.get('agent')
                        config = st.session_state.get('config')
                        
                        # 如果 agent 不存在，重新创建（因为 agent 对象可能无法正确序列化到 session_state）
                        if not agent:
                            try:
                                agent = create_lab_agent_graph()
                                config = {"configurable": {"thread_id": "streamlit-user"}}
                            except Exception as e:
                                st.error(f"无法创建 Agent: {str(e)}")
                                st.stop()
                        
                        if agent:
                            # 更新状态，准备重新处理
                            # 注意：设置 iteration_count = max_iterations，确保即使发现错误也不会触发自动修正循环
                            # 只设置 correction_hints，让 perceiver 使用反馈信息
                            original_max_iter = review_state.get("max_iterations", max_iter)
                            
                            # 确保有 image_path（从 review_state 中获取）
                            image_path = review_state.get("image_path", "")
                            if not image_path:
                                st.error("无法重新处理：缺少图片路径信息")
                                st.stop()
                            
                            # 累积所有历史反馈（包括新反馈）
                            feedback_history = st.session_state.get('feedback_history', [])
                            if feedback_history:
                                # 将所有历史反馈合并，用换行符分隔，并添加序号
                                accumulated_feedback = "\n\n".join([
                                    f"反馈 #{idx}: {fb}" for idx, fb in enumerate(feedback_history, 1)
                                ])
                            else:
                                # 如果没有历史反馈，使用当前反馈
                                accumulated_feedback = feedback
                            
                            restart_state = {
                                **review_state,
                                "correction_hints": accumulated_feedback,  # 将累积的反馈作为修正提示
                                "human_feedback": "",  # 清除之前的反馈，让 human_review_node 能够再次触发人工审核
                                "review_passed_override": None,  # 清除之前的审核结果覆盖
                                "needs_correction": False,  # 不触发自动修正循环
                                "needs_human_review": False,  # 初始设置为 False，由 Agent 判断是否需要
                                "iteration_count": original_max_iter,  # 设置为 max_iterations，确保不会触发自动循环
                                "max_iterations": original_max_iter,  # 保持原始值
                                "review_passed": False,  # 初始设置为 False，由 reviewer 重新审核
                                "review_issues": [],  # 清空之前的问题
                                "raw_json": "",  # 清空原始 JSON，强制重新提取
                                "reviewed_json": "",  # 清空审核后的 JSON
                                "formatted_markdown": ""  # 清空格式化后的 Markdown
                            }
                            
                            # 清除审核相关状态（确保不会直接显示结果）
                            st.session_state['needs_human_review'] = False
                            st.session_state['human_review_state'] = None
                            st.session_state['human_review_completed'] = False  # 清除完成标记
                            st.session_state['final_state_after_review'] = None  # 清除最终状态
                            
                            # 保存重新处理的状态
                            st.session_state['restart_processing'] = True
                            st.session_state['restart_state'] = restart_state
                            st.session_state['restart_agent'] = agent
                            st.session_state['restart_config'] = config
                            
                            # 重新运行以开始重新处理
                            st.rerun()
                        else:
                            st.error("无法重新处理：Agent 创建失败")
                
                # 显示当前提取的数据预览（Markdown 格式）
                st.markdown("### 📋 当前提取的数据预览")
                
                # 优先使用 formatted_markdown（Role C 使用 LLM 和 Cheat Sheet 生成的高质量结果）
                formatted_markdown = review_state.get("formatted_markdown", "")
                if formatted_markdown:
                    # 处理图片路径：将本地图片路径替换为提示文字
                    # 匹配 Markdown 图片语法：![alt text](path)
                    display_md = re.sub(r'!\[.*?\]\([^\)]+\)', '*(原始图片见左侧)*', formatted_markdown)
                    
                    # 显示 Markdown 预览（使用 expander 以便折叠）
                    with st.expander("📄 查看 Markdown 预览", expanded=True):
                        st.markdown(display_md, unsafe_allow_html=True)
                    
                    # 同时提供 JSON 源码查看选项（折叠）
                    raw_json = review_state.get("raw_json", "")
                    if raw_json:
                        try:
                            preview_data = json.loads(raw_json.replace("```json", "").replace("```", "").strip())
                            with st.expander("[INFO] 查看原始 JSON 数据", expanded=False):
                                st.json(preview_data)
                        except Exception as e:
                            pass
                else:
                    # 兜底逻辑：如果 formatted_markdown 不存在，使用原有的 generate_markdown 逻辑
                    raw_json = review_state.get("raw_json", "")
                    if raw_json:
                        try:
                            # 解析 JSON
                            preview_data = json.loads(raw_json.replace("```json", "").replace("```", "").strip())
                            
                            # 处理 experiments 数组格式
                            if "experiments" not in preview_data:
                                preview_data = {"experiments": [preview_data]}
                            
                            # 获取图片引用路径（用于 Markdown 生成）
                            image_reference_path = review_state.get("image_reference_path", "")
                            
                            # 使用统一的 Markdown 生成函数（与最终输出格式一致）
                            markdown_preview = generate_markdown(preview_data, image_reference_path)
                            
                            # 显示 Markdown 预览（使用 expander 以便折叠）
                            with st.expander("📄 查看 Markdown 预览", expanded=True):
                                st.markdown(markdown_preview, unsafe_allow_html=True)
                            
                            # 同时提供 JSON 源码查看选项（折叠）
                            with st.expander("[INFO] 查看原始 JSON 数据", expanded=False):
                                st.json(preview_data)
                        except Exception as e:
                            st.error(f"数据解析失败: {str(e)}")
                            st.code(raw_json[:500] + "..." if len(raw_json) > 500 else raw_json)
                st.markdown("</div>", unsafe_allow_html=True)
                st.stop()  # 暂停执行，等待用户操作

# 待审批页
with tab3:
    st.markdown("<h1 class='main-title'>🔄 待审批</h1>", unsafe_allow_html=True)
    st.markdown("显示处理完成但待人工审核的实验记录")
    
    try:
        db = get_db()
        
        tasks = db.get_tasks_needing_review()
        
        if tasks:
            for idx, task in enumerate(tasks):
                with st.container():
                    st.markdown(f"### 📄 {task['image_filename']}")
                    st.markdown(f"创建时间: {task['created_at']}")
                    
                    # 显示处理结果预览
                    if task.get('formatted_markdown'):
                        display_md = re.sub(r'!\[.*?\]\([^\)]+\)', '*(原始图片见左侧)*', task['formatted_markdown'])
                        with st.expander("📋 查看提取结果", expanded=True):
                            st.markdown(display_md, unsafe_allow_html=True)
                    elif task.get('raw_json'):
                        try:
                            raw_data = json.loads(task['raw_json'].replace("```json", "").replace("```", "").strip())
                            with st.expander("📋 查看提取结果", expanded=True):
                                st.json(raw_data)
                        except:
                            st.code(task['raw_json'][:500] + "...")
                    
                    # 解析 review_issues
                    review_issues = []
                    if task.get('review_issues'):
                        try:
                            review_issues = json.loads(task['review_issues'])
                        except:
                            pass
                    
                    # 审核决策 - 使用索引避免 key 冲突
                    col_decision, col_feedback = st.columns([1, 2])
                    with col_decision:
                        review_decision = st.radio(
                            "审核结果",
                            ["[OK] 通过", "[ERROR] 不通过"],
                            key=f"review_decision_{idx}",
                            horizontal=True
                        )
                    with col_feedback:
                        feedback_text = st.text_area(
                            "审核备注（必填，不通过时作为修正依据）",
                            placeholder="请输入审核意见或说明...",
                            key=f"feedback_text_{idx}"
                        )
                    
                    col_submit, col_delete = st.columns([3, 1])
                    with col_submit:
                        if st.button(f"[OK] 提交审核", key=f"submit_{task['task_id']}", type="primary", use_container_width=True):
                            if not feedback_text:
                                st.error("请输入审核备注")
                            else:
                                passed = review_decision == "[OK] 通过"
                                if passed:
                                    # ============= 三重条件校验 =============
                                    conditions = db.validate_approval_conditions(task['task_id'])
                                    conditions['user_approved'] = True  # 用户已点击通过按钮
                                    
                                    # 检查所有条件是否满足
                                    all_conditions_met = all(conditions.values())
                                    
                                    # 记录审计日志
                                    db.log_audit(
                                        operation_type='APPROVE',
                                        table_name='experiments',
                                        record_id=None,
                                        operator='user',
                                        trigger_condition='用户点击通过审核按钮',
                                        conditions_met=conditions,
                                        details={
                                            'task_id': task['task_id'],
                                            'image_filename': task['image_filename'],
                                            'feedback': feedback_text,
                                            'all_conditions_met': all_conditions_met
                                        }
                                    )
                                    
                                    if all_conditions_met:
                                        # 获取包含图片字节的完整任务数据
                                        task_with_image = db.get_task(task['task_id'], include_image_bytes=True)
                                        
                                        # 所有条件满足，执行入库操作
                                        experiment_id = db.save_experiment(
                                            image_filename=task_with_image['image_filename'],
                                            image_bytes=task_with_image.get('image_bytes'),
                                            image_path=None,
                                            image_reference_path=task_with_image['image_filename'],
                                            raw_json=task_with_image.get('raw_json', ''),
                                            reviewed_json=task_with_image.get('reviewed_json', ''),
                                            formatted_markdown=task_with_image.get('formatted_markdown', ''),
                                            iteration_count=task_with_image.get('iteration_count', 0),
                                            max_iterations=task_with_image.get('max_iterations', 3),
                                            review_passed=True,
                                            review_issues=review_issues,
                                            human_feedback=f"人工审核通过 | 备注: {feedback_text}",
                                            review_passed_override=True
                                        )
                                        
                                        # 记录入库操作日志
                                        db.log_audit(
                                            operation_type='CREATE',
                                            table_name='experiments',
                                            record_id=experiment_id,
                                            operator='user',
                                            trigger_condition='人工审核通过',
                                            conditions_met=conditions,
                                            details={
                                                'task_id': task['task_id'],
                                                'experiment_id': experiment_id,
                                                'image_filename': task['image_filename']
                                            }
                                        )
                                        
                                        db.delete_task(task['task_id'])
                                        st.success(f"审核通过！记录已保存 (ID: {experiment_id})")
                                        st.rerun()
                                    else:
                                        # 条件不满足，拒绝入库
                                        st.error("[ERROR] 入库条件校验失败")
                                        st.warning("条件检查结果：")
                                        st.write(f"- Agent处理完成: {'[OK]' if conditions['agent_processing_completed'] else '[ERROR]'}")
                                        st.write(f"- 任务状态待审核: {'[OK]' if conditions['status_pending_review'] else '[ERROR]'}")
                                        st.write(f"- 用户已通过审核: {'[OK]' if conditions['user_approved'] else '[ERROR]'}")
                                        st.error("请确保所有条件满足后再提交审核")
                                else:
                                    # 审核不通过，记录审计日志
                                    db.log_audit(
                                        operation_type='UPDATE',
                                        table_name='processing_tasks',
                                        record_id=task['task_id'],
                                        operator='user',
                                        trigger_condition='用户点击不通过审核',
                                        conditions_met={'user_rejected': True},
                                        details={
                                            'task_id': task['task_id'],
                                            'image_filename': task['image_filename'],
                                            'feedback': feedback_text
                                        }
                                    )
                                    
                                    # 更新任务状态为待重新处理，保留原处理结果供参考
                                    db.update_task_status(
                                        task['task_id'], 
                                        'pending', 
                                        progress=0,
                                        current_step='待重新处理',
                                        human_feedback=feedback_text
                                        # 保留原有的 formatted_markdown 和 review_issues 供参考
                                    )
                                    st.info("已记录不通过原因，任务已重新提交处理")
                                st.rerun()
                    with col_delete:
                        if st.button("🗑️ 删除", key=f"delete_{task['task_id']}", use_container_width=True):
                            db.delete_task(task['task_id'])
                            st.success("任务已删除")
                            st.rerun()
                    
                    st.markdown("---")
        else:
            st.info("🎉 暂无待审批的记录")
    
    except Exception as e:
        st.error(f"加载待审批记录失败: {str(e)}")

# 历史记录页
with tab4:
    st.markdown("<h1 class='main-title'>📚 历史记录</h1>", unsafe_allow_html=True)
    
    try:
        db = get_db()
        
        # 搜索和筛选
        col_search1, col_search2, col_search3 = st.columns([2, 1, 1])
        with col_search1:
            # 使用session_state保存搜索框内容
            if 'history_search' not in st.session_state:
                st.session_state['history_search'] = ""
            search_query = st.text_input("[INFO] 搜索", placeholder="搜索文件名、化学式、日期...", value=st.session_state['history_search'], key="history_search", on_change=lambda: st.session_state.pop('history_page', None))
        with col_search2:
            # 使用session_state保存筛选状态
            if 'history_filter' not in st.session_state:
                st.session_state['history_filter'] = "全部"
            filter_status = st.selectbox("审核状态", ["全部", "通过", "未通过"], index=["全部", "通过", "未通过"].index(st.session_state['history_filter']), key="history_filter", on_change=lambda: st.session_state.pop('history_page', None))
        with col_search3:
            # 使用session_state保存排序状态
            if 'history_sort' not in st.session_state:
                st.session_state['history_sort'] = "最新"
            sort_order = st.selectbox("排序", ["最新", "最旧"], index=["最新", "最旧"].index(st.session_state['history_sort']), key="history_sort", on_change=lambda: st.session_state.pop('history_page', None))
        
        # 保存搜索框内容到session_state（在所有小部件实例化后）
        if search_query != st.session_state.get('history_search', ""):
            st.session_state['history_search'] = search_query
            st.session_state.pop('history_page', None)
        if filter_status != st.session_state.get('history_filter', "全部"):
            st.session_state['history_filter'] = filter_status
            st.session_state.pop('history_page', None)
        if sort_order != st.session_state.get('history_sort', "最新"):
            st.session_state['history_sort'] = sort_order
            st.session_state.pop('history_page', None)
        
        # 获取筛选条件
        filter_review_passed = None
        if filter_status == "通过":
            filter_review_passed = True
        elif filter_status == "未通过":
            filter_review_passed = False
        
        order_desc = (sort_order == "最新")
        
        # 分页
        page_size = 10
        page_num = st.session_state.get('history_page', 1)
        
        # 获取记录
        print(f"[INFO] [历史记录查询] filter_review_passed: {filter_review_passed}, search_query: {search_query}, order_desc: {order_desc}")
        
        total_count = db.get_experiment_count(
            filter_review_passed=filter_review_passed,
            search_query=search_query if search_query else None
        )
        print(f"  - 总记录数: {total_count}")
        
        experiments = db.get_all_experiments(
            limit=page_size,
            offset=(page_num - 1) * page_size,
            filter_review_passed=filter_review_passed,
            search_query=search_query if search_query else None,
            order_desc=order_desc
        )
        print(f"  - 当前页记录数: {len(experiments)}")
        if experiments:
            print(f"  - 第一条记录ID: {experiments[0].get('id')}, 文件名: {experiments[0].get('image_filename')}, review_passed: {experiments[0].get('review_passed')}")
        
        # 显示统计
        st.info(f"[STATS] 共找到 {total_count} 条记录，当前显示第 {(page_num-1)*page_size+1}-{min(page_num*page_size, total_count)} 条")
        
        # 分页控制
        if total_count > page_size:
            total_pages = (total_count + page_size - 1) // page_size
            
            # 创建一个容器，使分页控件在一行显示
            pagination_container = st.container()
            with pagination_container:
                col_prev, col_page, col_next = st.columns([1, 2, 1])
                with col_prev:
                    if st.button("◀ 上一页", disabled=(page_num <= 1), key="prev_page"):
                        st.session_state['history_page'] = page_num - 1
                        st.rerun()
                with col_page:
                    st.markdown(f"<div style='text-align: center; padding: 8px 0;'>第 {page_num} / {total_pages} 页</div>", unsafe_allow_html=True)
                with col_next:
                    if st.button("下一页 ▶", disabled=(page_num >= total_pages), key="next_page"):
                        st.session_state['history_page'] = page_num + 1
                        st.rerun()
        
        # 显示记录列表
        if experiments:
            for exp in experiments:
                with st.expander(
                    f"📄 {exp['image_filename']} | "
                    f"{'[OK]' if exp['review_passed'] else '[WARN]'} | "
                    f"{exp['created_at'][:19] if exp['created_at'] else '未知时间'}",
                    expanded=False
                ):
                    col_detail1, col_detail2 = st.columns([2, 1])
                    
                    with col_detail1:
                        st.markdown(f"**文件名**: {exp['image_filename']}")
                        st.markdown(f"**创建时间**: {exp['created_at']}")
                        st.markdown(f"**更新时间**: {exp['updated_at']}")
                        st.markdown(f"**迭代次数**: {exp['iteration_count']} / {exp['max_iterations']}")
                        st.markdown(f"**审核状态**: {'[OK] 通过' if exp['review_passed'] else '[WARN] 未通过'}")
                        
                        if exp.get('review_issues'):
                            issue_count = len(exp['review_issues'])
                            st.markdown(f"**发现问题**: {issue_count} 个")
                    
                    with col_detail2:
                        # 显示图片（如果存在）
                        if exp.get('image_path') and os.path.exists(exp['image_path']):
                            try:
                                img = Image.open(exp['image_path'])
                                st.image(img, use_container_width=True)
                            except:
                                st.info("图片无法显示")
                        
                        # 操作按钮
                        # 打开详情弹窗
                        if st.button("📖 查看详情", key=f"detail_{exp['id']}"):
                            st.session_state['show_detail_modal'] = True
                            st.session_state['current_detail_exp_id'] = exp['id']
                        
                        if st.button("🗑️ 删除", key=f"delete_{exp['id']}"):
                            if db.delete_experiment(exp['id']):
                                st.success("已删除")
                                st.rerun()
                            else:
                                st.error("删除失败")
        
        # 详情弹窗 - 使用st.expander创建弹窗
        if st.session_state.get('show_detail_modal') and st.session_state.get('current_detail_exp_id'):
            exp_id = st.session_state.get('current_detail_exp_id')
            exp = db.get_experiment(exp_id)
            
            if exp:
                # 创建弹窗
                with st.expander(f"📖 实验记录详情: {exp['image_filename']}", expanded=True):
                    # 显示完整信息
                    col_view1, col_view2 = st.columns([1, 1])
                    
                    with col_view1:
                        st.markdown("<div class='card'>", unsafe_allow_html=True)
                        st.markdown("#### 📋 基本信息")
                        st.json({
                            "ID": exp['id'],
                            "文件名": exp['image_filename'],
                            "创建时间": exp['created_at'],
                            "更新时间": exp['updated_at'],
                            "迭代次数": f"{exp['iteration_count']} / {exp['max_iterations']}",
                            "审核状态": "通过" if exp['review_passed'] else "未通过"
                        })
                        
                        # 显示图片
                        if exp.get('image_path') and os.path.exists(exp['image_path']):
                            st.markdown("#### 🖼️ 原始图片")
                            try:
                                img = Image.open(exp['image_path'])
                                st.image(img, use_container_width=True)
                            except:
                                st.error("图片无法显示")
                        st.markdown("</div>", unsafe_allow_html=True)
                    
                    with col_view2:
                        st.markdown("<div class='card'>", unsafe_allow_html=True)
                        st.markdown("#### 📝 Markdown 报告")
                        if exp.get('formatted_markdown'):
                            st.markdown(exp['formatted_markdown'], unsafe_allow_html=True)
                            
                            # 下载按钮
                            st.download_button(
                                label="⬇️ 下载 Markdown",
                                data=exp['formatted_markdown'],
                                file_name=f"{exp['image_filename']}_report.md",
                                mime="text/markdown"
                            )
                        else:
                            st.info("无 Markdown 内容")
                        st.markdown("</div>", unsafe_allow_html=True)
                    
                    # 审核问题
                    if exp.get('review_issues'):
                        st.markdown("<div class='card'>", unsafe_allow_html=True)
                        st.markdown("#### [INFO] 审核问题")
                        for issue in exp['review_issues']:
                            severity = issue.get('severity', 'info')
                            if severity == 'error':
                                st.error(f"**{issue.get('description', '-')}")
                            elif severity == 'warning':
                                st.warning(f"**{issue.get('description', '-')}")
                            else:
                                st.info(f"**{issue.get('description', '-')}")
                        st.markdown("</div>", unsafe_allow_html=True)
                    
                    # 反馈历史
                    feedback_history = db.get_feedback_history(exp_id)
                    if feedback_history:
                        st.markdown("<div class='card'>", unsafe_allow_html=True)
                        st.markdown("#### 💬 反馈历史")
                        for fb in feedback_history:
                            st.text_area(
                                f"反馈 ({fb['created_at']})",
                                value=fb['feedback_text'],
                                disabled=True,
                                key=f"feedback_{fb['id']}"
                            )
                        st.markdown("</div>", unsafe_allow_html=True)
                    
                    # 原始数据（直接显示，不再嵌套 expander）
                    st.markdown("#### [INFO] 原始 JSON 数据")
                    if exp.get('raw_json'):
                        try:
                            raw_data = json.loads(exp['raw_json'].replace("```json", "").replace("```", "").strip())
                            st.json(raw_data)
                        except:
                            st.code(exp['raw_json'])
                    
                    # 关闭按钮
                    col_close = st.columns([1, 2, 1])[1]
                    with col_close:
                        if st.button("[ERROR] 关闭详情", key=f"close_detail_{exp['id']}"):
                            # 清除相关状态
                            st.session_state['show_detail_modal'] = False
                            st.session_state['current_detail_exp_id'] = None
                            # 强制页面刷新
                            st.rerun()
    except Exception as e:
        st.error(f"加载历史记录失败: {str(e)}")
        import traceback
        st.code(traceback.format_exc())

# 统计信息页
with tab5:
    st.markdown("<h1 class='main-title'>[STATS] 统计信息</h1>", unsafe_allow_html=True)
    
    try:
        db = get_db()
        
        # 基本统计信息
        st.markdown("<div class='card'>", unsafe_allow_html=True)
        st.markdown("<h2 class='card-title'>📋 基本统计</h2>", unsafe_allow_html=True)
        
        stats = db.get_statistics()
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("总记录数", stats['total_count'])
        with col2:
            st.metric("通过率", f"{stats['pass_rate']}%")
        with col3:
            st.metric("最近7天", stats['recent_count'])
        st.markdown("</div>", unsafe_allow_html=True)
        
        # 时间范围记录数
        st.markdown("<div class='card'>", unsafe_allow_html=True)
        st.markdown("<h2 class='card-title'>📅 记录趋势</h2>", unsafe_allow_html=True)
        
        # 添加时间范围选择器
        col1, col2 = st.columns(2)
        with col1:
            start_date = st.date_input("起始日期")
        with col2:
            end_date = st.date_input("结束日期")
        
        # 确保结束日期不早于起始日期
        if end_date < start_date:
            st.error("结束日期不能早于起始日期")
        else:
            # 获取指定时间范围内的每日记录数
            daily_stats = db.get_daily_statistics(str(start_date), str(end_date))
            
            # 准备数据
            dates = []
            counts = []
            for item in daily_stats:
                dates.append(item['date'])
                counts.append(item['count'])
            
            # 创建数据框
            df = pd.DataFrame({
                '日期': dates,
                '记录数': counts
            })
            
            # 显示表格
            st.markdown("### 记录数表格")
            st.dataframe(df, use_container_width=True)
            
            # 显示柱状图
            st.markdown("### 记录数趋势")
            fig = px.bar(df, x='日期', y='记录数', color='记录数',
                        color_continuous_scale='Viridis',
                        title=f'{start_date} 至 {end_date} 的实验记录数')
            fig.update_layout(
                xaxis_title='日期',
                yaxis_title='记录数',
                plot_bgcolor='white',
                paper_bgcolor='white'
            )
            st.plotly_chart(fig, use_container_width=True)
        st.markdown("</div>", unsafe_allow_html=True)
        
        # 审核状态分布
        st.markdown("<div class='card'>", unsafe_allow_html=True)
        st.markdown("<h2 class='card-title'>[STATS] 审核状态分布</h2>", unsafe_allow_html=True)
        
        status_stats = db.get_status_statistics()
        
        # 准备数据
        status_df = pd.DataFrame([
            {'状态': '通过', '数量': status_stats.get('passed', 0)},
            {'状态': '未通过', '数量': status_stats.get('failed', 0)}
        ])
        
        # 显示饼图
        fig = px.pie(status_df, values='数量', names='状态',
                    title='审核状态分布',
                    color_discrete_sequence=['#4CAF50', '#F44336'])
        fig.update_layout(
            plot_bgcolor='white',
            paper_bgcolor='white'
        )
        st.plotly_chart(fig, use_container_width=True)
        st.markdown("</div>", unsafe_allow_html=True)
        
        # 平均处理时间
        st.markdown("<div class='card'>", unsafe_allow_html=True)
        st.markdown("<h2 class='card-title'>⏱️ 处理时间统计</h2>", unsafe_allow_html=True)
        
        time_stats = db.get_time_statistics()
        if time_stats:
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("平均处理时间", f"{time_stats.get('average_time', 0):.2f} 秒")
            with col2:
                st.metric("最长处理时间", f"{time_stats.get('max_time', 0):.2f} 秒")
            with col3:
                st.metric("最短处理时间", f"{time_stats.get('min_time', 0):.2f} 秒")
        else:
            st.info("暂无处理时间数据")
        st.markdown("</div>", unsafe_allow_html=True)
        
    except Exception as e:
        st.error(f"加载统计信息失败: {str(e)}")
        import traceback
        st.code(traceback.format_exc())

# 知识问答页
with tab6:
    st.markdown("<h1 class='main-title'>💬 知识问答</h1>", unsafe_allow_html=True)
    st.markdown("欢迎使用晶体生长实验助手的知识问答功能！在这里，你可以向AI询问关于晶体生长实验的相关问题。")
    
    # 初始化聊天历史
    if "chat_history" not in st.session_state:
        st.session_state.chat_history = []
    
    # 创建一个容器来显示聊天历史，使其可滚动
    chat_container = st.container()
    
    # 显示聊天历史
    with chat_container:
        for message in st.session_state.chat_history:
            with st.chat_message(message["role"]):
                st.markdown(message["content"])
    
    # 创建一个固定在底部的容器
    input_container = st.container()
    
    with input_container:
        # 用户输入 - 固定在底部
        user_input = st.chat_input("请输入你的问题...")
        
        if user_input:
            # 添加用户消息到聊天历史
            st.session_state.chat_history.append({"role": "user", "content": user_input})
            
            # 重新显示聊天历史
            with chat_container:
                with st.chat_message("user"):
                    st.markdown(user_input)
                
                # 生成AI响应
                with st.chat_message("assistant"):
                    # 创建一个占位符用于流式输出
                    response_placeholder = st.empty()
                    
                    # 显示AI思考过程
                    response_placeholder.markdown("<span style='color: #888;'>AI 正在思考...</span>", unsafe_allow_html=True)
                    
                    # 实际调用AI模型
                    import os
                    from openai import OpenAI
                    
                    # 使用与agent.py相同的API配置
                    API_KEY = os.getenv("DASHSCOPE_API_KEY", "sk-eec9cb28d6804d18aaddcdb4bdd9a1b9")
                    BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
                    
                    # 构建系统提示
                    system_prompt = "你是一位晶体生长领域的专家，精通各种晶体生长方法、原理和技术。请以专业、准确、详细的方式回答关于晶体生长的问题，包括但不限于生长方法、参数优化、常见问题及解决方案等。"
                    
                    try:
                        # 初始化OpenAI客户端
                        client = OpenAI(api_key=API_KEY, base_url=BASE_URL)
                        
                        # 构建消息历史
                        messages = [
                            {"role": "system", "content": system_prompt}
                        ]
                        
                        # 添加历史聊天记录
                        for msg in st.session_state.chat_history:
                            messages.append({"role": msg["role"], "content": msg["content"]})
                        
                        # 调用AI模型
                        full_response = ""
                        
                        # 使用流式输出
                        for chunk in client.chat.completions.create(
                            model="qwen-plus",
                            messages=messages,
                            stream=True
                        ):
                            if chunk.choices[0].delta.content:
                                full_response += chunk.choices[0].delta.content
                                response_placeholder.markdown(full_response)
                        
                        # 添加AI响应到聊天历史
                        st.session_state.chat_history.append({"role": "assistant", "content": full_response})
                    except Exception as e:
                        # 如果API调用失败，使用默认响应
                        error_response = f"抱歉，AI回答时出现错误：{str(e)}\n\n请检查API Key是否正确设置，或者稍后再试。"
                        response_placeholder.markdown(error_response)
                        st.session_state.chat_history.append({"role": "assistant", "content": error_response})
    
    # 操作按钮区域
    button_col1, button_col2 = st.columns(2)
    with button_col1:
        if st.button("🗑️ 清除聊天历史", key="clear_chat"):
            st.session_state.chat_history = []
            # 强制页面刷新
            st.rerun()
    with button_col2:
        # 导出对话为PDF
        if st.button("📄 导出对话", key="export_chat"):
            if st.session_state.chat_history:
                # 生成PDF内容
                pdf_content = "# 晶体生长实验助手 - 知识问答记录\n\n"
                pdf_content += f"导出时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
                
                for i, message in enumerate(st.session_state.chat_history, 1):
                    role = "用户" if message["role"] == "user" else "AI"
                    pdf_content += f"## {i}. {role}\n"
                    pdf_content += f"{message['content']}\n\n"
                
                # 提供下载
                st.download_button(
                    label="⬇️ 下载PDF",
                    data=pdf_content,
                    file_name=f"chat_history_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt",
                    mime="text/plain"
                )
            else:
                st.info("没有聊天记录可导出")






    
    # ================= 结果展示（审核完成后，在按钮点击代码块外部） =================
    # 检查是否有审核完成后的状态，如果有则显示结果（不依赖按钮点击）
    if st.session_state.get('human_review_completed', False) and not st.session_state.get('needs_human_review', False):
        final_state = st.session_state.get('final_state_after_review')
        if final_state:
            # 清空之前的状态标记
            st.session_state['human_review_completed'] = False
            st.session_state['final_state_after_review'] = None
            
            # 显示结果
            with col2:
                st.markdown("---")
                st.success("[OK] 处理完成！")
                
                # 显示统计信息
                iteration_count = final_state.get("iteration_count", 0)
                review_issues = final_state.get("review_issues", [])
                # 优先检查人工审核覆盖结果，如果人工审核通过，则显示为通过
                review_passed_override = final_state.get("review_passed_override")
                if review_passed_override is not None:
                    review_passed = review_passed_override
                else:
                    review_passed = final_state.get("review_passed", False)
                
                # 创建统计卡片
                stat_col1, stat_col2, stat_col3 = st.columns(3)
                with stat_col1:
                    st.metric("🔄 迭代次数", f"{iteration_count} / {max_iter}")
                with stat_col2:
                    status_icon = "[OK]" if review_passed else "[WARN]"
                    st.metric("[STATS] 审核状态", status_icon + ("通过" if review_passed else "未通过"))
                with stat_col3:
                    issue_count = len(review_issues)
                    st.metric("[INFO] 发现问题", f"{issue_count} 个")
                
                # 选项卡：Markdown 视图 / 源码视图 / 审核日志
                tab1, tab2, tab3 = st.tabs(["📄 渲染视图", "📝 Markdown 源码", "[INFO] 审核日志"])
                
                markdown_content = final_state.get("formatted_markdown", "")
                
                with tab1:
                    if markdown_content:
                        # 处理 markdown 中的图片路径
                        display_md = markdown_content.replace(f"![原始记录含表征]({file_name_to_use})", "*(原始图片见左侧)*")
                        st.markdown(display_md, unsafe_allow_html=True)
                    else:
                        st.warning("[WARN] 未生成 Markdown 内容")
                
                with tab2:
                    if markdown_content:
                        st.code(markdown_content, language="markdown")
                        st.download_button(
                            label="⬇️ 下载 .md 文件",
                            data=markdown_content,
                            file_name=f"{os.path.splitext(file_name_to_use)[0]}_report.md",
                            mime="text/markdown"
                        )
                    else:
                        st.warning("[WARN] 未生成 Markdown 内容")
                
                with tab3:
                    st.markdown("### 📋 详细审核报告")
                    
                    if review_issues:
                        # 按严重程度分组显示
                        errors = [i for i in review_issues if i.get("severity") == "error"]
                        warnings = [i for i in review_issues if i.get("severity") == "warning"]
                        infos = [i for i in review_issues if i.get("severity") == "info"]
                        
                        if errors:
                            st.markdown("#### [ERROR] 严重错误")
                            for idx, issue in enumerate(errors, 1):
                                with st.expander(f"错误 #{idx}: {issue.get('description', '')[:50]}...", expanded=False):
                                    st.error(f"**描述**: {issue.get('description', '-')}")
                                    if issue.get('field'):
                                        st.code(f"字段: {issue.get('field')}")
                                    if issue.get('suggestion'):
                                        st.info(f"💡 **建议**: {issue.get('suggestion')}")
                        
                        if warnings:
                            st.markdown("#### [WARN] 警告")
                            for idx, issue in enumerate(warnings, 1):
                                with st.expander(f"警告 #{idx}: {issue.get('description', '')[:50]}...", expanded=False):
                                    st.warning(f"**描述**: {issue.get('description', '-')}")
                                    if issue.get('field'):
                                        st.code(f"字段: {issue.get('field')}")
                                    if issue.get('suggestion'):
                                        st.info(f"💡 **建议**: {issue.get('suggestion')}")
                        
                        if infos:
                            st.markdown("#### ℹ️ 信息提示")
                            for idx, issue in enumerate(infos, 1):
                                st.info(f"**{idx}.** {issue.get('description', '-')}")
                                if issue.get('field'):
                                    st.caption(f"字段: `{issue.get('field')}`")
                    else:
                        st.success("🎉 数据完美通过审核，未发现问题。")

