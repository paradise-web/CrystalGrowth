import streamlit as st
import os
import sys
from PIL import Image

# 添加当前目录到Python路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from agent import create_lab_agent_graph
from database import get_db
import tempfile

# 测试文件上传和解析流程
def test_upload_process():
    # 选择测试图片
    test_images = os.listdir('img_test')
    if not test_images:
        print("No test images found in img_test directory")
        return
    
    # 选择第一个测试图片
    test_image = test_images[0]
    image_path = os.path.join('img_test', test_image)
    print(f"Testing with image: {test_image}")
    
    # 读取图片
    try:
        img = Image.open(image_path)
        print(f"Image loaded successfully: {image_path}")
    except Exception as e:
        print(f"Failed to load image: {e}")
        return
    
    # 创建临时目录
    with tempfile.TemporaryDirectory() as temp_dir:
        # 保存图片到临时目录
        temp_img_path = os.path.join(temp_dir, test_image)
        img.save(temp_img_path)
        
        # 初始化 Agent
        try:
            agent = create_lab_agent_graph()
            print("Agent created successfully")
        except Exception as e:
            print(f"Failed to create agent: {e}")
            return
        
        # 构建初始状态
        initial_state = {
            "image_path": temp_img_path,
            "image_reference_path": test_image,
            "output_path": os.path.join(temp_dir, "output.md"),
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
            "needs_human_review": False,
            "messages": []
        }
        
        # 运行 Agent
        try:
            config = {"configurable": {"thread_id": "test-user"}}
            print("Running agent...")
            
            # 流式运行
            final_state = None
            for event in agent.stream(initial_state, config):
                for node_name, node_state in event.items():
                    if node_name == "__end__":
                        final_state = node_state
                        print(f"✓ Agent processing completed")
                        break
                    
                    print(f"Processing node: {node_name}")
                    # 打印一些关键信息
                    if node_name == "perceiver":
                        if node_state.get("raw_json"):
                            print("✓ Perceiver completed - data extracted")
                        else:
                            print("⚠️ Perceiver completed but no data extracted")
                    elif node_name == "reviewer":
                        issues = node_state.get("review_issues", [])
                        print(f"✓ Reviewer completed - found {len(issues)} issues")
                    elif node_name == "formatter":
                        if node_state.get("formatted_markdown"):
                            print("✓ Formatter completed - Markdown generated")
                        else:
                            print("⚠️ Formatter completed but no Markdown generated")
                    
                    # 检查是否有错误
                    if "error" in node_state:
                        print(f"❌ Error in {node_name}: {node_state['error']}")
            
            # 检查最终状态
            if final_state:
                print("\nFinal state summary:")
                print(f"- Iteration count: {final_state.get('iteration_count', 0)}")
                print(f"- Review passed: {final_state.get('review_passed', False)}")
                print(f"- Issues found: {len(final_state.get('review_issues', []))}")
                print(f"- Markdown generated: {'Yes' if final_state.get('formatted_markdown') else 'No'}")
                print(f"- Raw JSON: {'Yes' if final_state.get('raw_json') else 'No'}")
                print(f"- Reviewed JSON: {'Yes' if final_state.get('reviewed_json') else 'No'}")
                
                # 保存到数据库
                try:
                    db = get_db()
                    with open(image_path, 'rb') as f:
                        image_bytes = f.read()
                    
                    experiment_id = db.save_experiment(
                        image_filename=test_image,
                        image_bytes=image_bytes,
                        image_path=image_path,
                        raw_json=final_state.get("raw_json", ""),
                        reviewed_json=final_state.get("reviewed_json", ""),
                        formatted_markdown=final_state.get("formatted_markdown", ""),
                        iteration_count=final_state.get("iteration_count", 0),
                        max_iterations=3,
                        review_passed=final_state.get("review_passed", False),
                        review_issues=final_state.get("review_issues", [])
                    )
                    print(f"Experiment saved to database with ID: {experiment_id}")
                except Exception as e:
                    print(f"Failed to save to database: {e}")
                    import traceback
                    traceback.print_exc()
            else:
                print("No final state received")
                
        except Exception as e:
            print(f"Error during agent processing: {e}")
            import traceback
            traceback.print_exc()

if __name__ == "__main__":
    test_upload_process()