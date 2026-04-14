"""
专家级晶体生长 Agent 使用示例

这个示例展示了如何使用基于 LangGraph 的状态图智能体处理实验图片。
"""

import os
from agent import create_lab_agent_graph

def process_experiment_image(image_path: str, output_dir: str = "md_output"):
    """
    处理单张实验图片
    
    Args:
        image_path: 图片文件路径
        output_dir: 输出 Markdown 文件的目录
    """
    # 创建 Agent
    agent = create_lab_agent_graph()
    
    # 构建输出路径
    image_basename = os.path.basename(image_path)
    image_name = os.path.splitext(image_basename)[0]
    output_md_path = os.path.join(output_dir, f"{image_name}.md")
    
    # 构建图片相对路径（用于 Markdown 中的图片引用）
    image_rel_path = f"../{os.path.dirname(image_path)}/{image_basename}"
    
    # 初始化状态
    initial_state = {
        "image_path": image_path,
        "image_reference_path": image_rel_path,
        "output_path": output_md_path,
        "raw_json": "",
        "reviewed_json": "",
        "formatted_markdown": "",
        "needs_correction": False,
        "correction_hints": "",
        "iteration_count": 0,
        "max_iterations": 3,  # 最多允许 3 次自修正迭代
        "review_issues": [],
        "review_passed": False,
        "human_feedback": "",
        "needs_human_review": False,
        "messages": []
    }
    
    # 运行工作流
    config = {"configurable": {"thread_id": f"process-{image_name}"}}
    
    print(f"\n🚀 开始处理: {image_path}")
    print("=" * 60)
    
    final_state = agent.invoke(initial_state, config)
    
    # 输出结果
    print("\n" + "=" * 60)
    print("✅ 处理完成！")
    print("=" * 60)
    print(f"\n📄 Markdown 文件: {output_md_path}")
    
    # 显示审核结果
    review_issues = final_state.get("review_issues", [])
    if review_issues:
        print(f"\n⚠️ 发现 {len(review_issues)} 个问题:")
        for issue in review_issues[:5]:  # 只显示前5个
            severity = issue.get("severity", "info")
            desc = issue.get("description", "")
            print(f"  [{severity}] {desc}")
    
    # 显示迭代次数
    iteration_count = final_state.get("iteration_count", 0)
    if iteration_count > 1:
        print(f"\n🔄 自修正迭代次数: {iteration_count}")
    
    return final_state

if __name__ == "__main__":
    # 示例：处理单张图片
    test_image = "img_test/MoOBr2.jpg"
    
    if os.path.exists(test_image):
        process_experiment_image(test_image)
    else:
        print(f"❌ 未找到测试图片: {test_image}")
        print("\n💡 使用方法:")
        print("  from agent_example import process_experiment_image")
        print("  process_experiment_image('path/to/your/image.jpg')")

