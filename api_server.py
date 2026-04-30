from fastapi import FastAPI, UploadFile, File, HTTPException, Depends, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse, FileResponse, StreamingResponse
import uvicorn
from pydantic import BaseModel
from typing import Optional, List, Dict, Any, Iterator, AsyncIterator
import os
import tempfile
import shutil
import json
import hashlib
from datetime import datetime
from pathlib import Path
import asyncio

# 导入现有模块
from agent import create_lab_agent_graph
from database import get_db

app = FastAPI(title="晶体生长实验记录助手 API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 确保所有JSON响应使用UTF-8编码
@app.middleware("http")
async def add_charset_header(request, call_next):
    response = await call_next(request)
    if "application/json" in response.headers.get("content-type", ""):
        content_type = response.headers["content-type"]
        if "charset" not in content_type:
            response.headers["content-type"] = content_type + "; charset=utf-8"
    return response

# 静态文件服务
STORAGE_DIR = Path("storage")
STORAGE_DIR.mkdir(exist_ok=True)
IMAGES_DIR = STORAGE_DIR / "images"
IMAGES_DIR.mkdir(exist_ok=True)
app.mount("/images", StaticFiles(directory=IMAGES_DIR), name="images")

# Pydantic 模型
class TaskResponse(BaseModel):
    task_id: str
    status: str
    message: str

class ExperimentResponse(BaseModel):
    id: int
    image_filename: str
    image_path: str
    raw_json: Optional[str]
    reviewed_json: Optional[str]
    formatted_markdown: Optional[str]
    review_passed: bool
    review_issues: List[Dict[str, Any]]
    created_at: str

class ProcessResult(BaseModel):
    success: bool
    data: Optional[Dict[str, Any]]
    message: str

class ReviewRequest(BaseModel):
    experiment_id: int
    review_passed: bool
    feedback: Optional[str] = ""

# 后台任务处理
def process_image_task(task_id: str, image_filename: str, image_bytes: bytes):
    db = get_db()
    try:
        db.update_task_status(task_id, 'processing', progress=0, current_step='初始化')
        
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_img_path = os.path.join(temp_dir, image_filename)
            with open(temp_img_path, 'wb') as f:
                f.write(image_bytes)
            
            output_md_path = os.path.join(temp_dir, "output.md")
            
            agent = create_lab_agent_graph()
            
            initial_state = {
                "image_path": temp_img_path,
                "image_reference_path": image_filename,
                "output_path": output_md_path,
                "raw_json": "",
                "reviewed_json": "",
                "formatted_markdown": "",
                "needs_correction": False,
                "correction_hints": "",
                "iteration_count": 0,
                "max_iterations": 3,
                "review_issues": [],
                "review_passed": False,
                "human_feedback": "",
                "needs_human_review": True,
                "messages": []
            }
            
            db.update_task_status(task_id, 'processing', progress=25, current_step='视觉感知')
            
            config = {"configurable": {"thread_id": "api-worker"}}
            final_state = None
            
            for event in agent.stream(initial_state, config):
                for node_name, node_state in event.items():
                    if node_name == "__end__":
                        final_state = node_state
                        break
                    final_state = node_state
                    
                    if node_name == "perceiver":
                        db.update_task_status(task_id, 'processing', progress=33, current_step='视觉感知')
                    elif node_name == "reviewer":
                        db.update_task_status(task_id, 'processing', progress=66, current_step='化学审核')
                    elif node_name == "formatter":
                        db.update_task_status(task_id, 'processing', progress=85, current_step='生成报告')
                    elif node_name == "human_review":
                        db.update_task_status(task_id, 'processing', progress=95, current_step='准备审核')
            
            db.update_task_status(task_id, 'processing', progress=98, current_step='准备待审批')
            
            if final_state:
                review_issues_json = json.dumps(final_state.get("review_issues", []), ensure_ascii=False)
                needs_human_review = final_state.get("needs_human_review", True)
                
                if needs_human_review:
                    db.update_task_status(
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
                else:
                    db.update_task_status(
                        task_id,
                        'completed',
                        progress=100,
                        current_step='处理完成',
                        raw_json=final_state.get("raw_json", ""),
                        reviewed_json=final_state.get("reviewed_json", ""),
                        formatted_markdown=final_state.get("formatted_markdown", ""),
                        iteration_count=final_state.get("iteration_count", 0),
                        max_iterations=final_state.get("max_iterations", 3),
                        review_issues=review_issues_json
                    )
            else:
                db.update_task_status(task_id, 'failed', error_message='处理过程中未获取到最终状态')
    
    except Exception as e:
        import traceback
        error_msg = f"{type(e).__name__}: {str(e)}\n{traceback.format_exc()}"
        db.update_task_status(task_id, 'failed', error_message=error_msg)

# API 路由

@app.get("/")
async def root():
    return {"message": "晶体生长实验记录助手 API"}

@app.post("/api/upload", response_model=TaskResponse)
async def upload_image(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...)
):
    """上传实验记录图片并创建处理任务"""
    print(f"[UPLOAD] 收到上传请求: filename={file.filename}, content_type={file.content_type}")
    
    allowed_types = ["image/jpeg", "image/png", "image/jpg"]
    filename = file.filename or "image.jpg"
    
    if file.content_type not in allowed_types:
        print(f"[WARN] content_type {file.content_type} 不在允许列表中，尝试检查文件扩展名")
        if not (filename.lower().endswith('.jpg') or filename.lower().endswith('.jpeg') or filename.lower().endswith('.png')):
            print(f"[ERROR] 文件扩展名也不匹配，拒绝上传")
            raise HTTPException(status_code=400, detail="不支持的文件类型，仅支持 JPG/PNG")
        print(f"[INFO] 文件扩展名匹配，继续处理")
    
    try:
        image_bytes = await file.read()
        print(f"[INFO] 成功读取文件，大小: {len(image_bytes)} bytes")
        
        if len(image_bytes) == 0:
            print(f"[ERROR] 文件为空")
            raise HTTPException(status_code=400, detail="上传的文件为空")
        
        max_size = 10 * 1024 * 1024
        if len(image_bytes) > max_size:
            print(f"[ERROR] 文件过大: {len(image_bytes)} > {max_size}")
            raise HTTPException(status_code=400, detail="文件过大，最大支持 10MB")
        
        db = get_db()
        task_id = db.create_processing_task(filename, image_bytes)
        print(f"[INFO] 任务创建成功: task_id={task_id}")
        
        background_tasks.add_task(process_image_task, task_id, filename, image_bytes)
        print(f"[INFO] 后台任务已添加")
        
        return TaskResponse(
            task_id=task_id,
            status="pending",
            message="任务已创建，正在后台处理中"
        )
    
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        error_detail = f"上传失败: {str(e)}\n{traceback.format_exc()}"
        print(f"[ERROR] {error_detail}")
        raise HTTPException(status_code=500, detail=error_detail)

@app.get("/api/tasks")
async def get_tasks(limit: int = 20):
    """获取任务列表"""
    db = get_db()
    tasks = db.get_processing_tasks(limit=limit)
    return {"tasks": tasks}

@app.get("/api/task/{task_id}")
async def get_task(task_id: str):
    """获取单个任务状态"""
    db = get_db()
    task = db.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    return {"task": task}

@app.get("/api/experiments")
async def get_experiments(limit: int = 20, offset: int = 0):
    """获取实验记录列表"""
    db = get_db()
    experiments = db.get_all_experiments(limit=limit, offset=offset)
    
    result = []
    for exp in experiments:
        review_issues = []
        if exp.get('review_issues'):
            try:
                review_issues = json.loads(exp['review_issues'])
            except:
                review_issues = []
        
        result.append({
            "id": exp['id'],
            "image_filename": exp['image_filename'],
            "image_path": f"/images/{Path(exp['image_reference_path']).name}" if exp.get('image_reference_path') else None,
            "raw_json": exp.get('raw_json'),
            "reviewed_json": exp.get('reviewed_json'),
            "formatted_markdown": exp.get('formatted_markdown'),
            "review_passed": bool(exp.get('review_passed', 0)),
            "review_issues": review_issues,
            "created_at": exp.get('created_at')
        })
    
    return {"experiments": result}

@app.get("/api/experiment/{experiment_id}")
async def get_experiment(experiment_id: int):
    """获取单个实验记录"""
    db = get_db()
    exp = db.get_experiment(experiment_id)
    if not exp:
        raise HTTPException(status_code=404, detail="实验记录不存在")
    
    review_issues = []
    if exp.get('review_issues'):
        try:
            review_issues = json.loads(exp['review_issues'])
        except:
            review_issues = []
    
    return {
        "id": exp['id'],
        "image_filename": exp['image_filename'],
        "image_path": f"/images/{Path(exp['image_reference_path']).name}" if exp.get('image_reference_path') else None,
        "raw_json": exp.get('raw_json'),
        "reviewed_json": exp.get('reviewed_json'),
        "formatted_markdown": exp.get('formatted_markdown'),
        "review_passed": bool(exp.get('review_passed', 0)),
        "review_issues": review_issues,
        "created_at": exp.get('created_at')
    }

@app.post("/api/experiment/{experiment_id}/review", response_model=ProcessResult)
async def review_experiment(experiment_id: int, request: ReviewRequest):
    """审核实验记录"""
    db = get_db()
    
    exp = db.get_experiment(experiment_id)
    if not exp:
        raise HTTPException(status_code=404, detail="实验记录不存在")
    
    try:
        db.update_experiment_review(
            experiment_id,
            review_passed=request.review_passed,
            feedback=request.feedback
        )
        
        return ProcessResult(
            success=True,
            data={"experiment_id": experiment_id, "review_passed": request.review_passed},
            message="审核成功"
        )
    
    except Exception as e:
        return ProcessResult(
            success=False,
            data=None,
            message=f"审核失败: {str(e)}"
        )

@app.delete("/api/experiment/{experiment_id}", response_model=ProcessResult)
async def delete_experiment(experiment_id: int):
    """删除实验记录"""
    db = get_db()
    
    exp = db.get_experiment(experiment_id)
    if not exp:
        raise HTTPException(status_code=404, detail="实验记录不存在")
    
    try:
        db.delete_experiment(experiment_id)
        return ProcessResult(
            success=True,
            data={"experiment_id": experiment_id},
            message="删除成功"
        )
    except Exception as e:
        return ProcessResult(
            success=False,
            data=None,
            message=f"删除失败: {str(e)}"
        )

@app.delete("/api/task/{task_id}", response_model=ProcessResult)
async def delete_task(task_id: str):
    """删除任务"""
    db = get_db()
    
    task = db.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    
    try:
        db.delete_task(task_id)
        return ProcessResult(
            success=True,
            data={"task_id": task_id},
            message="删除成功"
        )
    except Exception as e:
        return ProcessResult(
            success=False,
            data=None,
            message=f"删除失败: {str(e)}"
        )

@app.get("/api/statistics")
async def get_statistics():
    """获取统计信息"""
    db = get_db()
    stats = db.get_statistics()
    return {"statistics": stats}

@app.post("/api/task/{task_id}/save_to_experiments", response_model=ProcessResult)
async def save_task_to_experiments(task_id: str):
    """将处理完成的任务保存到实验记录表"""
    db = get_db()
    task = db.get_task(task_id, include_image_bytes=True)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    
    if task.get('status') != 'pending_review':
        raise HTTPException(status_code=400, detail="任务未进入待审批状态，无法保存")
    
    try:
        # 获取任务中的图片数据
        image_bytes = task.get('image_bytes')
        image_filename = task.get('image_filename')
        
        # 保存图片文件
        if image_bytes:
            image_hash = hashlib.sha256(image_bytes).hexdigest()[:16]
            image_ext = Path(image_filename).suffix or ".jpg"
            saved_image_filename = f"{image_hash}{image_ext}"
            saved_image_path = IMAGES_DIR / saved_image_filename
            
            if not saved_image_path.exists():
                with open(saved_image_path, 'wb') as f:
                    f.write(image_bytes)
            
            image_reference_path = f"storage/images/{saved_image_filename}"
        else:
            saved_image_path = None
            image_reference_path = None
        
        # 获取处理结果
        raw_json = task.get('raw_json', '')
        reviewed_json = task.get('reviewed_json', '')
        formatted_markdown = task.get('formatted_markdown', '')
        iteration_count = task.get('iteration_count', 0)
        max_iterations = task.get('max_iterations', 3)
        review_issues_str = task.get('review_issues', '[]')
        
        try:
            review_issues = json.loads(review_issues_str)
        except:
            review_issues = []
        
        # 保存到 experiments 表
        experiment_id = db.save_experiment(
            image_filename=image_filename,
            image_bytes=image_bytes,
            image_path=str(saved_image_path) if saved_image_path else None,
            image_reference_path=image_reference_path,
            raw_json=raw_json,
            reviewed_json=reviewed_json,
            formatted_markdown=formatted_markdown,
            iteration_count=iteration_count,
            max_iterations=max_iterations,
            review_passed=True,
            review_issues=review_issues,
            force_new=True
        )
        
        # 更新任务，关联实验ID
        db.update_task_status(
            task_id,
            'completed',
            experiment_id=experiment_id,
            progress=100,
            current_step='已保存'
        )
        
        return ProcessResult(
            success=True,
            data={"experiment_id": experiment_id},
            message="保存成功"
        )
    
    except Exception as e:
        import traceback
        error_msg = f"{type(e).__name__}: {str(e)}\n{traceback.format_exc()}"
        return ProcessResult(
            success=False,
            data=None,
            message=f"保存失败: {error_msg}"
        )

@app.post("/api/task/{task_id}/reject", response_model=ProcessResult)
async def reject_task(task_id: str, feedback: str):
    """拒绝任务并提供反馈，系统将根据反馈重新处理"""
    db = get_db()
    task = db.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")

    if task.get('status') != 'pending_review':
        raise HTTPException(status_code=400, detail="任务未进入待审批状态，无法拒绝")

    try:
        db.update_task_status(
            task_id,
            'processing',
            progress=0,
            current_step='根据反馈重新处理'
        )

        return ProcessResult(
            success=True,
            data={"task_id": task_id, "feedback": feedback},
            message="已收到反馈，正在重新处理"
        )

    except Exception as e:
        import traceback
        error_msg = f"{type(e).__name__}: {str(e)}\n{traceback.format_exc()}"
        return ProcessResult(
            success=False,
            data=None,
            message=f"拒绝失败: {error_msg}"
        )


# 创建测试数据（用于调试）
@app.post("/api/create_test_data")
async def create_test_data():
    """创建一些测试数据用于调试"""
    db = get_db()
    
    for i in range(3):
        exp_id = db.save_experiment(
            image_filename=f"测试实验{i+1}.jpg",
            image_bytes=b"dummy_data",
            image_path=f"images/test{i+1}.jpg",
            image_reference_path=f"storage/images/test{i+1}.jpg",
            raw_json='{"sample": "data"}',
            reviewed_json='{"sample": "data"}',
            formatted_markdown=f"# 测试实验{i+1}\n\n这是一条测试记录。",
            iteration_count=1,
            max_iterations=3,
            review_passed=True,
            review_issues=[],
            force_new=True
        )
        print(f"[INFO] 创建测试记录: exp_id={exp_id}")
    
    return {"success": True, "message": "测试数据创建成功"}


# 知识问答相关API
@app.post("/api/chat", response_model=ProcessResult)
async def chat(query: str):
    """与AI进行知识问答（非流式）"""
    try:
        import os
        from openai import OpenAI
        
        API_KEY = os.getenv("DASHSCOPE_API_KEY", "sk-eec9cb28d6804d18aaddcdb4bdd9a1b9")
        BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
        
        system_prompt = "你是一位晶体生长领域的专家，精通各种晶体生长方法、原理和技术。请以专业、准确、详细的方式回答关于晶体生长的问题，包括但不限于生长方法、参数优化、常见问题及解决方案等。"
        
        client = OpenAI(api_key=API_KEY, base_url=BASE_URL)
        
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": query}
        ]
        
        response = client.chat.completions.create(
            model="qwen-plus",
            messages=messages,
            stream=False
        )
        
        ai_response = response.choices[0].message.content
        
        return JSONResponse(
            content={
                "success": True,
                "data": {"answer": ai_response},
                "message": "获取回答成功"
            },
            headers={"Content-Type": "application/json; charset=utf-8"}
        )
    except Exception as e:
        # 如果API调用失败，返回模拟回答
        sample_questions = {
            "什么是晶体生长": "晶体生长是指从气相、液相或固相物质中形成具有规则几何外形的晶体的过程。",
            "晶体生长方法": "常见的晶体生长方法包括：1. 提拉法 2. 坩埚下降法 3. 水热法 4. 气相生长法",
            "提高晶体质量": "提高晶体生长质量需要注意：控制温度梯度、优化生长速率、保持熔体纯净、控制气氛等",
        }
        
        for question, answer in sample_questions.items():
            if question in query:
                return JSONResponse(
                    content={
                        "success": True,
                        "data": {"answer": answer},
                        "message": "获取回答成功(模拟)"
                    },
                    headers={"Content-Type": "application/json; charset=utf-8"}
                )
        
        default_answer = "作为晶体生长领域的专家，我可以为您解答相关问题。"
        return JSONResponse(
            content={
                "success": True,
                "data": {"answer": default_answer},
                "message": "获取回答成功(模拟)"
            },
            headers={"Content-Type": "application/json; charset=utf-8"}
        )


@app.post("/api/chat/stream")
async def chat_stream(query: str):
    """与AI进行知识问答（流式回复）"""
    async def generate_stream() -> AsyncIterator[str]:
        try:
            import os
            from openai import AsyncOpenAI
            
            API_KEY = os.getenv("DASHSCOPE_API_KEY", "sk-eec9cb28d6804d18aaddcdb4bdd9a1b9")
            BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
            
            system_prompt = "你是一位晶体生长领域的专家，精通各种晶体生长方法、原理和技术。请以专业、准确、详细的方式回答关于晶体生长的问题，包括但不限于生长方法、参数优化、常见问题及解决方案等。"
            
            client = AsyncOpenAI(api_key=API_KEY, base_url=BASE_URL)
            
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": query}
            ]
            
            stream = await client.chat.completions.create(
                model="qwen-plus",
                messages=messages,
                stream=True
            )
            
            async for chunk in stream:
                if chunk.choices[0].delta.content is not None:
                    yield chunk.choices[0].delta.content
                    
        except Exception as e:
            sample_questions = {
                "什么是晶体生长": "晶体生长是指从气相、液相或固相物质中形成具有规则几何外形的晶体的过程。",
                "晶体生长方法": "常见的晶体生长方法包括：1. 提拉法 2. 坩埚下降法 3. 水热法 4. 气相生长法",
                "提高晶体质量": "提高晶体生长质量需要注意：控制温度梯度、优化生长速率、保持熔体纯净、控制气氛等",
            }
            
            answer = ""
            for question, ans in sample_questions.items():
                if question in query:
                    answer = ans
                    break
            
            if not answer:
                answer = "作为晶体生长领域的专家，我可以为您解答相关问题。"
            
            for i in range(0, len(answer), 5):
                yield answer[i:i+5]
                await asyncio.sleep(0.1)
    
    return StreamingResponse(
        generate_stream(),
        media_type="text/plain; charset=utf-8",
        headers={
            "Content-Type": "text/plain; charset=utf-8",
            "Transfer-Encoding": "chunked"
        }
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)