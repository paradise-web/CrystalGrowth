from fastapi import FastAPI, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
import base64
import json
import io
from PIL import Image, ImageOps
from openai import OpenAI
import os

app = FastAPI()

# 配置CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 配置API密钥
API_KEY = os.getenv("DASHSCOPE_API_KEY", "sk-eec9cb28d6804d18aaddcdb4bdd9a1b9")
BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
MODEL_NAME = "qwen-vl-max"

def preprocess_and_encode_image(image_data):
    """预处理图片：修正方向、调整尺寸、转Base64"""
    try:
        img = Image.open(io.BytesIO(image_data))
        img = ImageOps.exif_transpose(img)
        if img.mode != 'RGB':
            img = img.convert('RGB')
        max_size = 2048
        if max(img.size) > max_size:
            img.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)
        buffered = io.BytesIO()
        img.save(buffered, format="JPEG", quality=85)
        return base64.b64encode(buffered.getvalue()).decode('utf-8')
    except Exception as e:
        print(f"图片处理失败: {e}")
        return None

def get_system_prompt():
    """系统提示词"""
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

@app.post("/analyze")
async def analyze_image(image: UploadFile = File(...)):
    """分析实验记录图片"""
    try:
        # 读取图片数据
        image_data = await image.read()
        
        # 预处理图片
        base64_img = preprocess_and_encode_image(image_data)
        if not base64_img:
            return {"error": "图片处理失败"}
        
        # 调用视觉模型
        client = OpenAI(api_key=API_KEY, base_url=BASE_URL)
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
        
        # 解析结果
        result = json.loads(completion.choices[0].message.content)
        return result
    except Exception as e:
        print(f"分析失败: {e}")
        return {"error": str(e)}

@app.get("/experiments")
async def get_experiments():
    """获取实验记录列表"""
    return {"experiments": []}

@app.get("/experiments/{id}")
async def get_experiment(id: int):
    """获取实验记录详情"""
    return {"error": "Not implemented"}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
