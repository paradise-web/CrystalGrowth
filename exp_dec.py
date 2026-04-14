import os
import base64
import json
from openai import OpenAI

# ================= 配置区域 =================
# 建议配置环境变量，或者直接填入 API Key
# API_KEY = os.getenv("DASHSCOPE_API_KEY", "你的_API_KEY_填在这里") 
API_KEY = "sk-eec9cb28d6804d18aaddcdb4bdd9a1b9"
BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"

# 推荐使用 qwen-vl-max，在复杂的中文手写体和表格对齐上表现最好
MODEL_NAME = "qwen-vl-max" 
# ===========================================

def encode_image_to_base64(image_path):
    """将本地图片文件转换为 Base64 字符串"""
    if not os.path.exists(image_path):
        raise FileNotFoundError(f"找不到文件: {image_path}")
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode('utf-8')

def get_system_prompt():
    """
    【高精度版本】针对固相反应、CVT晶体生长实验记录的详细提示词。
    """
    return """
    # Role
    你是一位拥有20年经验的晶体生长工艺专家兼数据录入员。你的特长是识别潦草的实验室手写记录，并将其转化为结构化的电子实验报告。

    # Task Breakdown
    你需要分析上传的实验记录图片，提取以下三部分关键信息：

    1. **基础元数据 (Header Info)**：
       - 实验名称：通常在纸张最上方（例如：'VPS4-反铁磁体' 或 'CuWP2S6-强磁场炉'）。
       - 日期 (Date)：提取年-月-日。
       - 设备 (Furnace)：提取使用的设备名称（例如 '1号管式炉'）。

    2. **配料表 (Ingredients Matrix)** - 这是最核心的部分：
       - **结构识别**：这是一个矩阵。列标题通常是化学元素或化合物（如 V, P, S, Cu, WS2, I2）。
       - **行识别**：
         - 标记为 'n' 的行：代表摩尔比/化学计量比 (Stoichiometry)。注意可能包含 'wt%' (重量百分比) 的掺杂标注（如 '3+5wt%'）。
         - 标记为 'm' 的行：代表称量质量 (Mass)。
       - **对齐规则**：务必垂直对齐！例如，'V' 下方的 'n' 值属于 V，'m' 值也属于 V。
       - **特殊处理**：输运剂（如 I2）通常写在最后，可能标注有“输运”字样。

    3. **工艺流程 (Process)**：
       - **视觉理解**：寻找手绘的管式炉示意图（通常是一个长条圆角矩形）或箭头流程图。
       - **提取参数**：
         - 高温区/源区温度 (Source Temp)：通常数值较高（如 600℃）。
         - 低温区/生长区温度 (Sink Temp)：通常数值较低（如 500℃）。
         - 保温时长 (Duration)：寻找带有 'd'(天) 或 'h'(小时) 的标记（如 '7d'）。
         - 降温方式：'RT' 代表 Room Temperature（随炉冷却至室温）。
         - 完整描述：将箭头流程转化为文字（例如：'10h升温 -> 保温 -> 降温'）。

    # Data Correction Rules (逻辑修正)
    1. **单位补全**：如果质量行 ('m') 只有数字 (如 0.6115)，默认单位为 'g'。
    2. **化学式清洗**：请注意化学式的大小写规范，例如将识别到的 'cu' 修正为 'Cu'，'ws2' 修正为 'WS2'。
    3. **同上处理**：如果遇到 "-''-" 或 "do" 符号，请复制左侧或上侧的数值。

    # Output Format
    请仅输出纯净的 JSON 格式，不要输出 Markdown 代码块标记（```json），直接输出 JSON 字符串：
    {
      "meta": {
        "experiment_name": "实验名称",
        "date": "YYYY-MM-DD",
        "furnace": "设备名称"
      },
      "ingredients": [
        {
          "compound": "化学式 (如 V)",
          "ratio": "摩尔比 (如 1+20wt%)",
          "mass": "质量 (如 0.6115g)",
          "role": "raw_material" // 如果是输运剂填 transport_agent
        }
      ],
      "process": {
        "high_temp": "600℃",
        "low_temp": "500℃",
        "duration": "7d",
        "steps_description": "10h -> 500/600 -> RT",
        "notes": "手写备注内容"
      }
    }
    """

def process_image(client, image_path):
    """调用大模型进行识别"""
    try:
        base64_image = encode_image_to_base64(image_path)
        print(f"🚀 正在调用 {MODEL_NAME} 深度分析图片: {image_path} ...")
        
        completion = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {
                    "role": "system",
                    "content": get_system_prompt() # 使用详细版 Prompt
                },
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": "请将这张晶体生长实验记录数字化，生成详细报告。"
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{base64_image}"
                            },
                        },
                    ],
                }
            ],
            response_format={"type": "json_object"},
            stream=False
            # 注意：qwen-vl-max 不支持 thinking_budget，已移除相关参数
        )
        
        return completion.choices[0].message.content

    except Exception as e:
        print(f"❌ API 调用出错: {e}")
        return None

def save_to_markdown(json_str, output_file):
    """将 JSON 转换为 Markdown 实验报告"""
    try:
        # 清洗可能存在的 markdown 符号
        clean_json = json_str.replace("```json", "").replace("```", "").strip()
        data = json.loads(clean_json)
        
        meta = data.get("meta", {})
        process = data.get("process", {})
        ingredients = data.get("ingredients", [])
        
        md_lines = []
        
        # === 报告头部 ===
        exp_name = meta.get('experiment_name', '未命名实验')
        md_lines.append(f"# 🧪 实验记录报告: {exp_name}")
        md_lines.append(f"> **📅 日期**: {meta.get('date', 'N/A')} | **🔥 设备**: {meta.get('furnace', 'N/A')}")
        md_lines.append("\n---\n")
        
        # === 配料表 ===
        md_lines.append("## 1. ⚖️ 配料表 (Batching)")
        if ingredients:
            # Markdown 表格头部
            md_lines.append("| 化学式 (Compound) | 摩尔比 (n) | 质量 (m) | 类型/备注 |")
            md_lines.append("| :--- | :--- | :--- | :--- |")
            
            for ing in ingredients:
                compound = ing.get("compound", "-")
                ratio = ing.get("ratio", "-")
                mass = str(ing.get("mass", "-"))
                # 确保质量有单位
                if mass and mass.replace('.','',1).isdigit():
                    mass += "g"
                role = ing.get("role", "raw_material")
                if role == "transport_agent": role = "🌪️ 输运剂"
                elif role == "raw_material": role = "原料"
                
                md_lines.append(f"| **{compound}** | {ratio} | {mass} | {role} |")
        else:
            md_lines.append("> ⚠️ 未识别到配料数据")
        
        md_lines.append("\n")
        
        # === 工艺流程 ===
        md_lines.append("## 2. 🌡️ 工艺流程 (Process Parameters)")
        
        # 使用列表展示关键参数
        md_lines.append(f"- **高温区 (Source Temp)**: `{process.get('high_temp', 'N/A')}`")
        md_lines.append(f"- **低温区 (Sink Temp)**: `{process.get('low_temp', 'N/A')}`")
        md_lines.append(f"- **生长时长 (Duration)**: `{process.get('duration', 'N/A')}`")
        
        # 流程描述
        desc = process.get('steps_description', process.get('notes', '无详细描述'))
        md_lines.append(f"- **📝 完整流程**: \n    > {desc}")
        
        # === 其他备注 ===
        extra_notes = data.get("notes") or process.get("notes")
        # 避免与流程描述重复
        if extra_notes and extra_notes != desc:
             md_lines.append("\n## 3. 📌 其他手写备注")
             md_lines.append(f"{extra_notes}")

        # 写入文件
        with open(output_file, "w", encoding="utf-8") as f:
            f.write("\n".join(md_lines))
            
        print(f"✅ 成功！Markdown 报告已生成: {output_file}")
        
        # 打印预览
        print("\n" + "="*15 + " 报告预览 " + "="*15)
        print("\n".join(md_lines[:12]))
        print("...")

    except json.JSONDecodeError:
        print("❌ JSON 解析失败，模型可能返回了非标准格式。")
        print("原始内容:", json_str)
    except Exception as e:
        print(f"❌ 生成报告时出错: {e}")

# ================= 主程序 =================
if __name__ == "__main__":
    # 初始化客户端
    client = OpenAI(
        api_key=API_KEY,
        base_url=BASE_URL
    )

    # 替换你的图片路径
    target_image = "3R-MoS2.png"  # 请修改为你的实际文件名

    if os.path.exists(target_image):
        # 1. 识别
        result_json = process_image(client, target_image)
        
        # 2. 导出 Markdown
        if result_json:
            # 自动生成输出文件名 (同名.md)
            output_md = os.path.splitext(target_image)[0] + "_report.md"
            save_to_markdown(result_json, output_md)
    else:
        print(f"⚠️ 文件不存在: {target_image}")