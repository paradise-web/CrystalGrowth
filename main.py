import os
import base64
import json
import time
import io
from PIL import Image, ImageOps
from openai import OpenAI

# ================= 配置区域 =================
API_KEY = "sk-eec9cb28d6804d18aaddcdb4bdd9a1b9"
BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
MODEL_NAME = "qwen-vl-max" 

INPUT_DIR = "img_data"
OUTPUT_DIR = "md_data"
VALID_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.bmp', '.webp', '.heic'}
# ===========================================

def preprocess_and_encode_image(image_path):
    """预处理图片：修正方向、调整尺寸、转Base64"""
    try:
        with Image.open(image_path) as img:
            img = ImageOps.exif_transpose(img)
            if img.mode != 'RGB': img = img.convert('RGB')
            max_size = 2048
            if max(img.size) > max_size:
                img.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)
            buffered = io.BytesIO()
            img.save(buffered, format="JPEG", quality=85)
            return base64.b64encode(buffered.getvalue()).decode('utf-8')
    except Exception as e:
        print(f"  ⚠️ 图片处理失败: {e}")
        return None

def get_system_prompt():
    """
    【修正版 Prompt】针对 700/600温区、RT误识别、配比缺失进行专项优化
    """
    return """
    # Role
    你是一位晶体生长领域的资深专家。请将实验图片转化为高精度的结构化数据。

    # 🔧 Critical Correction Rules (必须遵守的修正规则)
    1. **RT vs PT**: 手写记录中的 **"RT"** 绝对代表 **"Room Temperature" (室温)**。
       - ❌ 严禁识别为 "PT"。
       - ❌ "PT" 不是炉子类型，如果看到类似字样，请修正为 "RT" 或忽略。
       - ✅ 降温步骤通常是 "Cooling to RT"。
    2. **温度解析**: 如果温度写为 **"700/600"** 或 **"700/600℃"**：
       - 前者 (700) 是 **高温区/源区 (Source Temp)**。
       - 后者 (600) 是 **低温区/生长区 (Sink Temp)**。
    3. **方法推断**: 
       - 如果存在高低温区 (Gradient) 且有卤素/输运剂，实验方法 (Method) 必定是 **"CVT (化学气相传输法)"**。
    4. **配比提取**: 
       - 配料表必须提取两列数据：**"质量(Mass)"** 和 **"摩尔配比(Molar Ratio)"**。
       - 摩尔配比通常是简单的整数比 (如 1:2:1) 或写在 'n' 行。

    # Task Breakdown
    
    ## 1. 基础信息
    - **Meta**: 实验名称、日期、设备(如管式炉, 勿填PT)、**实验方法(Method)**。
    - **Reaction**: 提取化学方程式。
    - **Ingredients**: 提取配料表。
      - 必须区分: `mass_g` (如 0.1g) 和 `molar_ratio` (如 1, 2, 3+5wt%)。

    ## 2. 工艺流程 (Process)
    - **High Temp**: 提取高温区数值 (如 700)。
    - **Low Temp**: 提取低温区数值 (如 600)。
    - **Description**: 将流程转化为文字描述 (如 "RT -> 升温 -> 保温 -> 降至RT")。

    ## 3. 结果表征 (Characterization)
    - 仅当图片中包含 **显微镜照片、晶体实物图或XRD谱** 时才提取。
    - 如果全是手写文字，此字段保持为空数组 `[]`。

    # Output JSON Schema
    {
      "meta": { 
        "title": "str", 
        "date": "str", 
        "furnace": "str",
        "method": "str (如 CVT, Flux, Solid State)"
      },
      "reaction_equation": "str",
      "ingredients": [
        { 
          "compound": "str", 
          "mass_g": "str (如 0.29g)", 
          "molar_ratio": "str (如 1 或 1+5wt%)", 
          "role": "str (原料/输运剂)" 
        }
      ],
      "process": { 
        "high_temp": "str (仅数字+单位)", 
        "low_temp": "str (仅数字+单位)", 
        "description": "str (注意RT修正)" 
      },
      "results": [
        { "type": "Microscope/Photo/XRD", "label": "str", "description": "str" }
      ],
      "notes": "str"
    }
    """

def process_single_image(client, image_path):
    try:
        base64_img = preprocess_and_encode_image(image_path)
        if not base64_img: return None
        
        completion = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {"role": "system", "content": get_system_prompt()},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "请分析这张实验记录。特别注意：配料表需要同时提取质量和摩尔比；'700/600'代表双温区；'RT'是室温不是PT。"},
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_img}"}},
                    ],
                }
            ],
            response_format={"type": "json_object"},
            stream=False
        )
        return completion.choices[0].message.content
    except Exception as e:
        print(f"  ❌ API Error: {e}")
        return None

def save_to_markdown(json_str, output_file, rel_img_path):
    try:
        data = json.loads(json_str.replace("```json", "").replace("```", "").strip())
        
        meta = data.get("meta", {})
        ingredients = data.get("ingredients", [])
        process = data.get("process", {})
        results = data.get("results", [])
        
        # 判断是否为含有表征图片的记录 (Type B)
        has_characterization = results and len(results) > 0
        
        md = []
        # === 1. 头部信息 ===
        title = meta.get('title') or "实验记录"
        # 如果标题被识别成 "RT"，强制修正
        if title == "RT": title = "实验记录"
            
        md.append(f"# 🧪 {title}")
        
        # 构建 Meta 行
        method = meta.get('method', 'Unknown')
        # 再次兜底修正 PT
        furnace = meta.get('furnace','-')
        if "PT" in furnace: furnace = furnace.replace("PT", "RT").replace("RT炉", "管式炉") # 简单规则修正
        
        md.append(f"> **📅 日期**: {meta.get('date','-')} | **🔥 设备**: {furnace} | **⚗️ 方法**: {method}")
        md.append("\n---\n")
        
        # === 2. 反应体系 ===
        md.append("## 1. ⚗️ 反应体系 (Reaction)")
        if data.get("reaction_equation"):
            eq = data.get('reaction_equation').replace("->", "\\rightarrow")
            md.append(f"**方程式**: \n> ${eq}$\n")
        
        md.append("### ⚖️ 配料表")
        if ingredients:
            # 修改表头，增加摩尔比列
            md.append("| 组分 (Component) | 质量 (Mass) | 摩尔比 (Ratio) | 备注 (Role) |")
            md.append("| :--- | :--- | :--- | :--- |")
            for i in ingredients:
                md.append(f"| **{i.get('compound','-')}** | {i.get('mass_g','-')} | {i.get('molar_ratio','-')} | {i.get('role','-')} |")
        else:
            md.append("> *未识别到配料表*")
            
        # === 3. 生长工艺 ===
        md.append("\n## 2. 🌡️ 生长工艺 (Process)")
        # 显式展示双温区
        md.append(f"- **高温区 (Source)**: `{process.get('high_temp','-')}`")
        md.append(f"- **低温区 (Sink)**: `{process.get('low_temp','-')}`")
        
        # 修正描述中的 PT -> RT
        desc = process.get('description','-').replace("PT", "RT")
        md.append(f"- **完整流程**: \n    > {desc}")
        
        # === 4. 结果表征 (仅当有结果时才显示图片和表格) ===
        if has_characterization:
            md.append("\n## 3. 🔬 结果表征 (Characterization)")
            
            # 【核心修改】只有在这里才插入原图
            md.append(f"\n![实验记录原图]({rel_img_path})\n")
            
            md.append("| 类型 | 标注 (Label) | 视觉描述 (Description) |")
            md.append("| :--- | :--- | :--- |")
            for r in results:
                md.append(f"| {r.get('type','-')} | **{r.get('label','-')}** | {r.get('description','-')} |")
        
        # === 5. 备注 ===
        notes = data.get("notes")
        if notes:
            md.append(f"\n## 4. 📌 备注\n{notes}")

        with open(output_file, "w", encoding="utf-8") as f:
            f.write("\n".join(md))
        return True
    except Exception as e:
        print(f"  ❌ Markdown Save Error: {e}")
        return False

def main():
    if not os.path.exists(INPUT_DIR):
        print(f"❌ 请创建 '{INPUT_DIR}' 并放入图片")
        return
    if not os.path.exists(OUTPUT_DIR): os.makedirs(OUTPUT_DIR)
    
    files = [f for f in os.listdir(INPUT_DIR) if os.path.splitext(f)[1].lower() in VALID_EXTENSIONS]
    client = OpenAI(api_key=API_KEY, base_url=BASE_URL)
    
    print(f"🚀 开始处理 {len(files)} 张图片...")
    for i, f in enumerate(files):
        print(f"[{i+1}/{len(files)}] Processing: {f} ...")
        res = process_single_image(client, os.path.join(INPUT_DIR, f))
        
        rel_path = f"../{INPUT_DIR}/{f}" 
        out_path = os.path.join(OUTPUT_DIR, os.path.splitext(f)[0] + ".md")
        
        if res and save_to_markdown(res, out_path, rel_path):
            print("  ✅ Done")
        else:
            print("  ❌ Failed")
        time.sleep(1)

if __name__ == "__main__":
    main()