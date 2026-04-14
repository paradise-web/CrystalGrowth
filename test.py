import os
import base64
import json
import time
import io
import re
from PIL import Image, ImageOps
from openai import OpenAI

# ================= 配置常量 =================
DEFAULT_API_KEY = "sk-eec9cb28d6804d18aaddcdb4bdd9a1b9" # 建议实际使用时通过环境变量获取
BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
MODEL_NAME = "qwen-vl-max" 
VALID_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.bmp', '.webp', '.heic'}

# ================= 1. 核心提示词 =================

def get_system_prompt():
    """
    【修正版 Prompt v4】
    更新点：
    1. CVT判定：新增支持 "700/600°C" 这种斜杠分隔的双温区写法识别。
    2. 保留：RT=室温、Flux/Solid State 互斥逻辑、Melt Growth 识别。
    """
    return """
    # Role
    你是一位晶体生长专家。请分析实验记录图片，将其拆解为结构化的数据列表。

    # 🧠 Complex Logic Handling (核心逻辑)

    ## 1. 缩写与术语纠错 (关键)
    - **RT**: 代表 **Room Temperature (室温)**。
      - 若出现在流程中 (如 "RT -> 800℃")，指起始温度。
      - 若出现在设备栏 (如 "RT炉")，通常指 "Resistive Tube Furnace" (电阻管式炉)，但需优先结合上下文判断是否指温度。
    - **h / d / min**: 分别代表 小时(hour), 天(day), 分钟(minute)。
    - **Vapor / Total P**: 指压强相关参数。

    ## 2. 实验方法判定 (Method Classification) - 互斥分类

    ### A. CVT (化学气相传输)
    - **判据**: 必须同时满足 [输运剂] + [双温区]。
      1. **输运剂**: I2, Br2, Cl2, TeCl4, NH4Cl 等。
      2. **双温区**: 必须存在 Source T (高温) 和 Sink T (低温)。
    - **双温区常见写法**:
      - **斜杠法**: "700/600°C", "1000/900", "T_source/T_sink"。这代表源区700度，生长区600度。
      - **位置标注**: 明确画出炉子的两个温区位置。``
    - **特征**: 气相生长，通常在密封石英管中。

    ### B. Flux (助熔剂法/熔盐生长)
    - **本质**: **液相生长 (Solution Growth)**。原料溶解在助熔剂中。
    - **判据**: 
       1. **大量助熔剂**: 配料中包含过量的金属/盐 (Sn, Bi, NaCl等)，比例通常非化学计量 (如 1:10, 1:20)。
       2. **液相分离**: 出现 "Centrifuge"(离心), "Decant"(倒出), "Spin" 等将晶体与液体分离的操作。
    - **流程**: 典型为 "升温熔化 -> 慢速降温(结晶) -> 分离"。

    ### C. Solid State (固相反应/烧结)
    - **本质**: **固相扩散 (Solid Phase Diffusion)**。无液相或仅有微量液相。
    - **判据**: 
       1. **化学计量比**: 配料严格按照产物化学式比例 (Stoichiometric)。
       2. **物理操作**: 出现 "Regrind"(研磨), "Pellet"(压片), "Sinter"(烧结), "Calcining"(煅烧)。
    - **区别 Flux**: 即使有降温过程，只要没有大量助熔剂且目的是合成粉末/陶瓷，就是 Solid State。

    ### D. Melt Growth (熔体法/Bridgman)
    - **判据**: 原料完全熔化，通过 **移动 (mm/h)** 通过温区进行结晶。

    ## 3. 工艺流程解析 (Process Parsing)
    - **RT 处理**: 
      - 如果流程写 "RT -> 900℃"，描述字段填 "Room Temperature -> 900℃"。
      - 不要把 RT 填入 `high_temp`，`high_temp` 只填最高保温温度。
    - **双温区 (CVT)**: 
      - 若识别到 "700/600°C"，则 `high_temp`="700°C", `low_temp`="600°C"。
    - **单温区/Flux/Solid State**: 
      - `high_temp`: 填最高处理温度。
      - `low_temp`: 留空 (除非有明确的低温区保温段，单纯降温不算)。
      - `description`: 必须完整记录升降温过程 (例如 "RT -> 1000℃ (10h) -> 500℃ (2℃/h)")。

    # Output JSON Schema
    {
      "experiments": [
        {
          "meta": {
            "title": "实验名称",
            "date": "YYYY-MM-DD",
            "furnace": "设备名 (若写RT炉则转为'Tube Furnace', 若无则'-')",
            "method": "CVT / Flux / Solid State / Melt Growth / Other"
          },
          "reaction_equation": "string OR null",
          "ingredients": [
            { "compound": "str", "mass_g": "str", "molar_ratio": "str", "role": "Raw Material / Flux / Transport Agent" }
          ],
          "process": {
            "high_temp": "str (最高温度/源区)",
            "low_temp": "str (低温区/生长区, 仅CVT填写)",
            "duration": "str (最高温保温时长)",
            "description": "str (完整流程: 包含 RT 起始、升降温速率、中间研磨等细节)"
          },
          "results": [
            { "type": "Microscope/Photo", "label": "str", "description": "str" }
          ],
          "notes": "str (包含对 RT, 颜色, 产物形态的额外描述)"
        }
      ]
    }
    """

# ================= 2. 通用处理函数 =================

def preprocess_and_encode_image(image_input):
    """通用预处理"""
    try:
        if isinstance(image_input, str):
            if not os.path.exists(image_input): return None
            img = Image.open(image_input)
        else:
            img = Image.open(image_input)

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

def call_ai_model(client, base64_img):
    """调用 AI"""
    try:
        completion = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {"role": "system", "content": get_system_prompt()},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "请分析实验记录。注意区分Flux降温法和CVT双温区法。准确提取数据。"},
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

# ================= 2.5 摩尔比计算辅助工具 (新增) =================

# 常用元素原子量表 
ATOMIC_WEIGHTS = {
    'H': 1.008, 'Li': 6.94, 'C': 12.01, 'N': 14.01, 'O': 16.00, 'F': 19.00,
    'Na': 22.99, 'Mg': 24.31, 'Al': 26.98, 'Si': 28.09, 'P': 30.97, 'S': 32.06,
    'Cl': 35.45, 'K': 39.10, 'Ca': 40.08, 'Ti': 47.87, 'V': 50.94, 'Cr': 52.00,
    'Mn': 54.94, 'Fe': 55.85, 'Co': 58.93, 'Ni': 58.69, 'Cu': 63.55, 'Zn': 65.38,
    'Ga': 69.72, 'Ge': 72.63, 'As': 74.92, 'Se': 78.96, 'Br': 79.90, 'Zr': 91.22,
    'Nb': 92.91, 'Mo': 95.95, 'Ru': 101.07, 'Rh': 102.91, 'Pd': 106.42, 'Ag': 107.87,
    'Cd': 112.41, 'In': 114.82, 'Sn': 118.71, 'Sb': 121.76, 'Te': 127.60, 'I': 126.90,
    'Ba': 137.33, 'Ta': 180.95, 'W': 183.84, 'Pt': 195.08, 'Au': 196.97, 'Hg': 200.59,
    'Pb': 207.2, 'Bi': 208.98
}

def get_molar_mass(formula):
    """简易计算摩尔质量 (支持如 MoS2, Sn, MoCl5)"""
    if not formula: return 0
    parsed = re.findall(r'([A-Z][a-z]?)(\d*)', formula)
    mass = 0
    for elem, count in parsed:
        count = int(count) if count else 1
        mass += ATOMIC_WEIGHTS.get(elem, 0) * count
    return mass

def parse_mass_to_g(mass_str):
    """将 '500mg', '1.2g', '1g' 等统一转换为克"""
    if not mass_str: return 0
    mass_str = mass_str.lower().strip()
    # 提取数字
    match = re.search(r"([\d\.]+)", mass_str)
    if not match: return 0
    val = float(match.group(1))
    
    if "mg" in mass_str:
        return val / 1000
    return val

def calculate_missing_ratios(ingredients):
    """
    原地修改 ingredients 列表，计算缺失的摩尔比
    """
    valid_data = []
    
    # 1. 计算所有组分的摩尔数
    for item in ingredients:
        comp = item.get('compound')
        mass_str = item.get('mass_g')
        role = item.get('role', '')
        
        # 如果已经有比例且不是"-"，则跳过计算（以手写为准）
        current_ratio = item.get('molar_ratio')
        if current_ratio and current_ratio not in ['-', 'None', 'null']:
            continue

        # 计算摩尔数
        m_mass = get_molar_mass(comp)
        mass_g = parse_mass_to_g(mass_str)
        
        if m_mass > 0 and mass_g > 0:
            moles = mass_g / m_mass
            # 将计算所需的元数据暂存
            valid_data.append({
                'item': item,
                'moles': moles,
                'is_transport': 'Transport' in role # 输运剂通常不作为归一化基准
            })
    
    if not valid_data:
        return

    # 2. 确定归一化基准 (找摩尔数最小的非输运剂，如果没有则找全局最小)
    non_transport_moles = [x['moles'] for x in valid_data if not x['is_transport']]
    if non_transport_moles:
        base_mole = min(non_transport_moles)
    else:
        base_mole = min([x['moles'] for x in valid_data])
        
    if base_mole == 0: return

    # 3. 回填计算结果
    for data in valid_data:
        ratio_val = data['moles'] / base_mole
        # 格式化：接近整数取整，否则保留1位小数
        if abs(ratio_val - round(ratio_val)) < 0.1:
            formatted_ratio = str(int(round(ratio_val)))
        else:
            formatted_ratio = f"{ratio_val:.1f}"
        
        # 标记是自动计算的 (可选：加个*)
        data['item']['molar_ratio'] = f"{formatted_ratio} (Auto)"


# ================= 3. 核心 Markdown 生成逻辑 (修改版) =================

def generate_markdown_content(json_str, image_reference_path):
    """
    将 
    JSON 转换为 Markdown
    修正点：
    1. CVT 方法不显示化学方程式。
    2. 自动计算缺失的摩尔比。
    """
    try:
        # === JSON 清洗与解析 ===
        cleaned_str = json_str.replace("```json", "").replace("```", "").strip()
        try:
            data = json.loads(cleaned_str)
        except json.JSONDecodeError as e:
            match = re.search(r'\{.*\}', cleaned_str, re.DOTALL)
            if match:
                data = json.loads(match.group())
            else:
                return f"JSON 解析致命错误: {e}\n原始返回: {json_str[:100]}..."

        if "experiments" not in data:
            data = {"experiments": [data]}
            
        experiments = data.get("experiments", [])
        md_output = []
        
        # 遍历所有实验
        for idx, exp in enumerate(experiments):
            meta = exp.get("meta") or {}
            ingredients = exp.get("ingredients") or []
            process = exp.get("process") or {}
            results = exp.get("results") or []
            
            # === 预处理：方法判定 ===
            method = meta.get('method', '-')
            is_cvt = "CVT" in method.upper()
            
            # === 预处理：计算摩尔比 ===
            # 这里调用上面定义的辅助函数
            calculate_missing_ratios(ingredients)
            
            # === 标题与元数据 ===
            title = meta.get('title') or "实验记录"
            if title == "RT": title = "实验记录"
            
            furnace = meta.get('furnace')
            if furnace and "PT" in furnace: 
                furnace = furnace.replace("PT", "RT").replace("RT炉", "管式炉")
            if not furnace: furnace = '-'
            
            md_output.append(f"# 🧪 {title}")
            md_output.append(f"> **📅 日期**: {meta.get('date', '-')} | **🔥 设备**: {furnace} | **⚗️ 方法**: {method}")
            
            # === 图片 ===
            if results and len(results) > 0:
                md_output.append(f"\n![原始记录含表征]({image_reference_path})\n")
            md_output.append("\n---\n")
            
            # === 反应体系 (修正点1：CVT 不显示) ===
            equation = exp.get("reaction_equation")
            if equation and not is_cvt:  # 只有非 CVT 且有方程式才显示
                md_output.append("## ⚗️ 反应体系")
                eq = equation.replace("->", "\\rightarrow")
                md_output.append(f"**方程式**: \n> ${eq}$\n")
            
            # === 配料表 (修正点2：已包含自动计算值) ===
            md_output.append("## ⚖️ 配料表")
            if ingredients:
                md_output.append("| 组分 | 质量 (Mass) | 摩尔比 (Ratio) | 备注 (Role) |")
                md_output.append("| :--- | :--- | :--- | :--- |")
                for i in ingredients:
                    md_output.append(f"| **{i.get('compound','-')}** | {i.get('mass_g','-')} | {i.get('molar_ratio','-')} | {i.get('role','-')} |")
            else:
                md_output.append("> *未识别到配料表*")
                
            # === 生长工艺 ===
            md_output.append("\n## 🌡️ 生长工艺")
            md_output.append(f"- **最高/源区温度**: `{process.get('high_temp', '-')}`")
            
            low_temp = process.get('low_temp')
            # 只有当低温区存在，且不等于高温区时才显示（避免单温区重复显示）
            if low_temp and low_temp.strip() and low_temp != process.get('high_temp'):
                md_output.append(f"- **低温区温度**: `{low_temp}`")
            
            md_output.append(f"- **保温时长**: `{process.get('duration', '-')}`")
            
            desc = process.get('description')
            desc = desc.replace("PT", "RT") if desc else '-'
            md_output.append(f"- **完整流程**: \n    > {desc}")
            
            # === 结果表征 ===
            if results:
                md_output.append("\n## 🔬 结果表征")
                md_output.append("| 类型 | 标注 | 描述 |")
                md_output.append("| :--- | :--- | :--- |")
                for r in results:
                    md_output.append(f"| {r.get('type','-')} | **{r.get('label','-')}** | {r.get('description','-')} |")
            
            # === 备注 ===
            notes = exp.get("notes")
            if notes:
                md_output.append(f"\n## 📌 备注\n{notes}")
            
            # 分割线
            if idx < len(experiments) - 1:
                md_output.append("\n\n---\n\n")
        
        return "\n".join(md_output)
        
    except Exception as e:
        import traceback
        return f"Markdown 生成出错: {str(e)}\n{traceback.format_exc()}"

# ================= 4. 脚本入口 =================

if __name__ == "__main__":
    INPUT_DIR = "img_1128" 
    OUTPUT_DIR = "md_1128" # 使用独立的输出目录测试
    
    if not os.path.exists(INPUT_DIR):
        print(f"❌ 请创建 '{INPUT_DIR}' 并放入图片")
        exit()
    if not os.path.exists(OUTPUT_DIR): os.makedirs(OUTPUT_DIR)
    
    client = OpenAI(api_key=DEFAULT_API_KEY, base_url=BASE_URL)
    files = [f for f in os.listdir(INPUT_DIR) if os.path.splitext(f)[1].lower() in VALID_EXTENSIONS]
    
    print(f"🚀 [批量模式] 开始处理 {len(files)} 张图片...")
    for f in files:
        print(f"处理: {f} ...")
        img_path = os.path.join(INPUT_DIR, f)
        
        b64 = preprocess_and_encode_image(img_path)
        if b64:
            res = call_ai_model(client, b64)
            if res:
                rel_path = f"../{INPUT_DIR}/{f}" 
                md = generate_markdown_content(res, rel_path)
                
                out_path = os.path.join(OUTPUT_DIR, os.path.splitext(f)[0] + ".md")
                with open(out_path, "w", encoding="utf-8") as f_out:
                    f_out.write(md)
                print("  ✅ 完成")
            else:
                print("  ❌ AI Failed")
        else:
            print("  ❌ Image Failed")
        time.sleep(1)