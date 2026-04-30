from fastapi import FastAPI, UploadFile, File, HTTPException, Depends, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse, FileResponse
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
import os
import tempfile
import shutil
import json
import hashlib
from datetime import datetime
from pathlib import Path

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
                        'completed',
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
    allowed_types = ["image/jpeg", "image/png", "image/jpg"]
    if file.content_type not in allowed_types:
        raise HTTPException(status_code=400, detail="不支持的文件类型，仅支持 JPG/PNG")
    
    try:
        image_bytes = await file.read()
        
        if len(image_bytes) == 0:
            raise HTTPException(status_code=400, detail="上传的文件为空")
        
        db = get_db()
        task_id = db.create_processing_task(file.filename, image_bytes)
        
        background_tasks.add_task(process_image_task, task_id, file.filename, image_bytes)
        
        return TaskResponse(
            task_id=task_id,
            status="pending",
            message="任务已创建，正在后台处理中"
        )
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"上传失败: {str(e)}")

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
    experiments = db.get_experiments(limit=limit, offset=offset)
    
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
    task = db.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    
    if task.get('status') != 'completed':
        raise HTTPException(status_code=400, detail="任务未完成，无法保存")
    
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
            review_passed=False,
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

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=True)