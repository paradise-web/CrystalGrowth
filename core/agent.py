import os
import json
import base64
import io
import re
import statistics
from typing import TypedDict, Annotated, Literal, Optional, List, Dict, Any, Tuple
from PIL import Image, ImageOps

# LangChain & LangGraph 核心组件
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from langchain_core.prompts import ChatPromptTemplate
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver

# 动态化学知识库
try:
    from pymatgen.core import Composition
    PYMATGEN_AVAILABLE = True
except ImportError:
    PYMATGEN_AVAILABLE = False
    print("⚠️ 警告: pymatgen 未安装，将使用备用原子量表。建议运行: pip install pymatgen")

# 外部文献 RAG
try:
    from external_rag import retrieve_knowledge, validate_compound_with_knowledge, retrieve_material_properties
    EXTERNAL_RAG_AVAILABLE = True
except ImportError:
    EXTERNAL_RAG_AVAILABLE = False
    print("⚠️ 警告: external_rag 模块未找到，外部文献 RAG 功能将不可用。")

# ================= 配置 =================
API_KEY = os.getenv("DASHSCOPE_API_KEY", "sk-eec9cb28d6804d18aaddcdb4bdd9a1b9")
BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"

# 备用原子量表（当 pymatgen 不可用时使用）
FALLBACK_ATOMIC_WEIGHTS = {
    'H': 1.008, 'Li': 6.94, 'C': 12.01, 'N': 14.01, 'O': 16.00, 'F': 19.00,
    'Na': 22.99, 'Mg': 24.31, 'Al': 26.98, 'Si': 28.09, 'P': 30.97, 'S': 32.06,
    'Cl': 35.45, 'K': 39.10, 'Ca': 40.08, 'Ti': 47.87, 'V': 50.94, 'Cr': 52.00,
    'Mn': 54.94, 'Fe': 55.85, 'Co': 58.93, 'Ni': 58.69, 'Cu': 63.55, 'Zn': 65.38,
    'Ga': 69.72, 'Ge': 72.63, 'As': 74.92, 'Se': 78.96, 'Br': 79.90, 'Zr': 91.22,
    'Nb': 92.91, 'Mo': 95.95, 'Ru': 101.07, 'Rh': 102.91, 'Pd': 106.42, 'Ag': 107.87,
    'Cd': 112.41, 'In': 114.82, 'Sn': 118.71, 'Sb': 121.76, 'Te': 127.60, 'I': 126.90,
    'Ba': 137.33, 'Ta': 180.95, 'W': 183.84, 'Pt': 195.08, 'Au': 196.97, 'Hg': 200.59,
    'Pb': 207.2, 'Bi': 208.98, 'La': 138.91, 'Ce': 140.12, 'Pr': 140.91, 'Nd': 144.24,
    'Sm': 150.36, 'Eu': 151.96, 'Gd': 157.25, 'Tb': 158.93, 'Dy': 162.50, 'Ho': 164.93,
    'Er': 167.26, 'Tm': 168.93, 'Yb': 173.05, 'Lu': 174.97, 'Y': 88.91, 'Sc': 44.96,
    'Rb': 85.47, 'Cs': 132.91, 'Sr': 87.62
}

# ================= 动态化学知识库 =================

def _convert_unicode_subscripts(formula: str) -> str:
    """
    将 Unicode 下标字符转换为 ASCII 数字。
    例如：MoO₃ -> MoO3, C₆Br₆ -> C6Br6
    """
    # Unicode 下标到数字的映射
    subscript_map = {
        '₀': '0', '₁': '1', '₂': '2', '₃': '3', '₄': '4',
        '₅': '5', '₆': '6', '₇': '7', '₈': '8', '₉': '9',
        # 上标（虽然不常见，但也处理）
        '⁰': '0', '¹': '1', '²': '2', '³': '3', '⁴': '4',
        '⁵': '5', '⁶': '6', '⁷': '7', '⁸': '8', '⁹': '9',
    }
    
    result = formula
    for unicode_char, ascii_char in subscript_map.items():
        result = result.replace(unicode_char, ascii_char)
    
    return result

def get_molecular_weight(formula: str) -> float:
    """
    使用 pymatgen 动态计算化学式分子量。
    支持复杂化学式，如 La2-xBaxCuO4, FeSe, MoS2 等。
    自动处理 Unicode 下标（如 MoO₃ -> MoO3）。
    """
    if not formula or formula in ['-', 'null', '']:
        return 0.0
    
    # 首先转换 Unicode 下标为 ASCII 数字
    formula = _convert_unicode_subscripts(formula)
    
    # 清理化学式（移除空格、特殊字符等，但保留数字和字母）
    formula = re.sub(r'[^\w\.\-]', '', formula.strip())
    
    if PYMATGEN_AVAILABLE:
        try:
            # pymatgen 可以处理复杂化学式，包括掺杂（如 La2-xBaxCuO4）
            # 对于掺杂，我们取平均值或简化处理
            comp = Composition(formula)
            return comp.weight
        except Exception as e:
            # 如果 pymatgen 解析失败，回退到备用方法
            print(f"⚠️ pymatgen 解析失败 ({formula}): {e}，使用备用方法")
            return _fallback_molecular_weight(formula)
    else:
        return _fallback_molecular_weight(formula)

def _fallback_molecular_weight(formula: str) -> float:
    """备用方法：使用正则表达式解析简单化学式"""
    # 移除掺杂标记（如 La2-xBaxCuO4 -> La2BaCuO4，简化处理）
    formula = re.sub(r'-\w+', '', formula)
    
    # 匹配元素和数量：如 FeSe -> [('Fe', ''), ('Se', '')]
    parsed = re.findall(r'([A-Z][a-z]?)(\d*\.?\d*)', formula)
    mass = 0.0
    for elem, count_str in parsed:
        count = float(count_str) if count_str else 1.0
        atomic_weight = FALLBACK_ATOMIC_WEIGHTS.get(elem, 0.0)
        if atomic_weight == 0.0:
            print(f"⚠️ 未知元素: {elem}，在化学式 {formula} 中")
        mass += atomic_weight * count
    return mass

# ================= 状态定义 (State Schema) =================

class AgentState(TypedDict):
    """Agent 工作流的状态容器"""
    # 输入
    image_path: str
    image_reference_path: str  # 用于 Markdown 中的图片引用
    output_path: str  # 输出 Markdown 文件路径
    
    # 工作流数据
    raw_json: str  # Role A 提取的原始 JSON
    reviewed_json: str  # Role B 审核后的 JSON
    formatted_markdown: str  # Role C 生成的 Markdown
    
    # 控制流
    needs_correction: bool  # 是否需要重新提取
    correction_hints: str  # 修正提示（用于指导重新提取）
    iteration_count: int  # 迭代次数（防止无限循环）
    max_iterations: int  # 最大迭代次数
    
    # 审核结果
    review_issues: list  # 审核发现的问题列表
    review_passed: bool  # 审核是否通过
    
    # 人机回环
    human_feedback: str  # 人工反馈
    needs_human_review: bool  # 是否需要人工审核
    
    # 消息历史
    messages: Annotated[list, "messages"]  # 对话历史

# ================= 系统提示词 =================

def get_perceiver_prompt():
    """Role A: 视觉感知者的系统提示词"""
    return """
    # Role
    你是一位晶体生长专家。请分析实验记录图片，将其拆解为结构化的数据列表。

    # Complex Logic Handling (核心逻辑)

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
      - **位置标注**: 明确画出炉子的两个温区位置。
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

    # Output JSON Schema (增强版，支持更丰富的结构化数据)
    {
      "experiments": [
        {
          "meta": {
            "title": "实验名称",
            "date": "YYYY-MM-DD",
            "furnace": "设备名 (若写RT炉则转为'Tube Furnace', 若无则'-')",
            "method": "CVT / Flux / Solid State / Melt Growth / CVD / Other"
          },
          "material_info": {
            "formula": "主要产物化学式 (如 MoS2)",
            "phase": "相结构信息 (如 '2H-MoS2 (六方)' 或 null)"
          },
          "reaction_equation": "string OR null",
          "ingredients": {
            "precursors": [
              { 
                "name": "化学式 (如 MoO3)", 
                "purity": "纯度信息 (如 '≥99.99%' 或 null)", 
                "mass": "质量字符串 (如 '0.5g' 或 '500mg')", 
                "role": "Raw Material / Flux / Transport Agent",
                "form": "形态描述 (若图片中有明确标注如'粉末'、'片状'则提取；若未标注则留空/null)"
              }
            ],
            "substrate": "衬底信息 (如 'Si/SiO2, 285nm' 或 null)",
            "ratios": "配比描述 (如 'MoO3 : S = 1 : 1.5' 或 null)"
          },
          "process": {
            "description": "str (完整流程: 包含 RT 起始、升降温速率、中间研磨等细节)",
            "method_specific": {
              "gas_flow": "气体类型及流量 (CVD/CVT 方法时填写，如 'Ar 50 sccm' 或 null)",
              "pressure": "压强信息 (如 '常压', '1 atm' 或 null)",
              "geometry": "空间放置描述 (如 'Face-down, MoO3 in center, S at upstream' 或 null)"
            },
            "heating_program": [
              {
                "step": "步骤名称 (如 'Purge', 'Ramp 1', 'Growth', 'Cooling')",
                "temp": "温度 (如果是双温区，尽量提取为 '700/600°C' 格式，如 'RT', '300°C', '700°C' 或 null)",
                "target": "目标温度 (升温段使用，如 '300°C' 或 null)",
                "rate": "升温/降温速率 (如 '15°C/min', '2°C/h' 或 null)",
                "duration": "持续时间 (如 '10 min', '2h' 或 null)",
                "note": "额外说明 (如 'Ar 100 sccm', '开始对硫区加热' 或 null)"
              }
            ],
            "dynamic_params": [
              { 
                "name": "参数名称 (如 '高温区温度', '低温区温度', '反应时长', '降温速率' 等)", 
                "value": "参数值 (如 '800°C', '10h' 等)", 
                "unit": "单位 (如 '°C', 'h', 'min' 等，可选)",
                "type": "temperature / time / pressure / rate / other" 
              }
            ]
          },
          "results": [
            { "type": "Microscope/Photo", "label": "str", "description": "str" }
          ],
          "notes": "str (包含对 RT, 颜色, 产物形态的额外描述)"
        }
      ]
    }
    
    # 重要说明：
    # 1. **向后兼容性**：如果图片信息不够详细，可以只填写基本字段（如 ingredients 可以简化为数组格式，process 可以只填写 description 和 dynamic_params）
    # 2. **结构化提取**：
    #    - material_info: 如果图片中明确提到产物化学式和相结构，请填写；否则可以省略
    #    - ingredients.precursors: 前驱体列表，如果图片中区分了"前驱体"和"衬底"，请分开填写
    #    - ingredients.substrate: 衬底信息单独提取（CVD 方法常见）
    #    - process.heating_program: 如果图片中有详细的升温程序（如 "RT -> 300°C (15°C/min) -> 700°C (25°C/min) -> 保持10min"），请拆解为多个步骤
    #    - process.method_specific: 方法特定的参数（如 CVD 的气体流量、CVT 的空间放置等）
    # 3. **智能判断**：
    #    - 如果是 CVD 方法，重点提取 gas_flow, pressure, geometry, heating_program
    #    - 如果是 CVT 方法，重点提取双温区、输运剂、空间放置
    #    - 如果是 Flux 方法，重点提取助熔剂、离心等操作
    # 4. **动态参数**：process.dynamic_params 仍然保留，用于向后兼容和补充信息
    """

def get_formatter_prompt(reference_style_content: str = "") -> str:
    """
    Role C: 数据工程师的系统提示词（LLM 驱动的风格迁移生成）
    
    Args:
        reference_style_content: 风格参考的 Markdown 内容
    """
    base_prompt = """
    # Role
    你是一名专业的实验数据整理员。你的任务是将结构化的 JSON 数据转换为 Markdown 实验报告。

    # Requirements
    **0. 【最高优先级】数据绝对优先原则**：
       - **表格中的数值必须严格对应 JSON 数据，严禁因风格原因修改数据**。
       - **配料表摩尔比（Molar Ratio）字段的强制规则**：
         * JSON 中的 `molar_ratio` 字段已经自动计算完成（格式如 "1"、"2"、"1.5" 等纯数字）。
         * **绝对禁止**：严禁将 JSON 中的 `molar_ratio` 值（如 "1"）替换为 "-" 或其他任何值。
         * **必须逐字复制**：如果 JSON 中 `molar_ratio` 为 "1"，表格中就必须写 "1"，一个字都不能改。
         * **校验要求**：生成表格后，必须检查每个组分的摩尔比列是否与 JSON 中的 `molar_ratio` 字段完全一致。
         * **违反后果**：如果发现表格中的摩尔比与 JSON 不一致，必须立即修正。

    **⚠️ 重要警告：风格参考文件（Style Reference）的数据说明**：
       - 风格参考文件中的所有数据（包括表格中的数值、横线 "-"、摩尔比等）**均为虚构的占位符**。
       - **严禁模仿风格参考文件中的数据内容**，仅参考其标题层级和排版风格。
       - 对于配料表（Ingredients Table），如果用户提供了【真实配料表数据（必须使用）】块，**必须完全忠实于该数据块**，直接将其嵌入表格中，完全忽略风格参考文件中的配料表数据。

    **🔇 【静默原则/客观性约束】严禁添加质疑性备注或警告信息**：
       - **绝对中立**：你是一个客观的记录工具，不是评审专家。你的唯一任务是将 JSON 数据转换为格式化的 Markdown 报告，**严禁**对数据的合理性、科学性、矛盾点进行任何形式的点评、质疑或警告。
       - **禁止质疑**：即使数据看起来违反常理（例如"固相法"使用了"双温区"），你也必须照实记录，**严禁**添加任何"疑点说明"、"警告符号(⚠️)"、"建议核实"、"可能为..."等主观性文字。
       - **信任上游**：默认所有输入的 JSON 数据都已经过人工专家（Role B）的严格审核。如果数据中有矛盾，那是专家的意图，不需要你来指出或解释。
       - **禁止加戏**：在"备注"或"说明"部分，只允许通过 RAG 补充客观的物理性质（如熔点、空间群），**严禁**生成任何主观的对实验设计的评价、质疑或建议。
       - **示例禁止项**：严禁在报告中出现以下类型的内容：
         * "⚠️ 可能为记录重复..."
         * "⚠️ 方法学疑点：尽管标记为 Solid State... 但更接近 CVT..."
         * "建议核实实验方法..."
         * "该数据可能存在矛盾..."
         * 任何带有警告、质疑、建议性质的主观性文字
       - **违反后果**：如果你在生成的 Markdown 中添加了任何质疑性、警告性或建议性的文字，该报告将被视为不合格。

    1. **结构拟合**：尽量保持与参考样式一致的标题层级（如 "## 原料及配比", "## 实验方法及参数设置"），但**数据内容必须来自用户提供的真实数据**。
    2. **智能适应**：
       - 如果是 CVD 实验，重点描述气体流量、压强、升温程序和空间放置。
       - 如果是 CVT 实验，重点描述双温区、输运剂和空间配置。
       - 如果是 Flux 实验，重点描述助熔剂、配比和分离过程。
       - 如果是 Solid State 实验，重点描述化学计量比、研磨和烧结过程。
       - 如果包含多个实验（对比实验），请在 "实验结果" 或 "参数设置" 部分使用表格进行对比，而不是生成多个重复的块。
    3. **化学式渲染**：确保所有化学式使用 LaTeX 格式（如 $MoS_2$，使用下划线表示下标）。
    4. **数据完整性**：
       - 如果 JSON 中有 ingredients.precursors 和 ingredients.substrate，分开展示"前驱体"和"衬底"。
       - 如果 JSON 中有 process.heating_program，详细描述升温程序（如 "初始：室温 → purge（Ar 100 sccm）10 min"）。
       - 如果 JSON 中有 process.method_specific，展示方法特定参数（如气体流量、压强、空间放置）。
    5. **数据补全与推断**：
       - 检查配料表中的 `form` (形貌) 字段。如果 JSON 中该字段为空或缺失，请基于你的化学知识推断该物质在实验条件下的常见形态（例如：MoO3、S 推断为"粉末"；C2H5OH、C6Br6 推断为"液体"或"输运剂"；Si 片推断为"片状"）。
       - **注意**：如果 JSON 中已有明确识别的形貌，请以 JSON 为准，不要覆盖。
    6. **自然语言**：使用自然、流畅的中文描述，避免过于机械化的列表。
    7. **缺失数据处理**：如果数据中没有某项内容（如没有衬底信息），则自然省略该部分；如果有额外信息，请智能地展示。
    """
    
    # 默认使用新示例作为参考
    default_reference = """# 🧪 MoO₂Br₂的单晶制备
> **📅 日期**: None | **🔥 设备**: Tube Furnace | **⚗️ 方法**: CVT

## ⚗️ 反应体系

**方程式**: 

> $Mo + 2 MoO₃ + C₆Br₆ → 3 MoO₂Br₂$

## ⚖️ 配料表

| 组分      | 形貌 | 质量 | 摩尔比 | 备注   |
| :-------- | ---- | :--- | :----- | :----- |
| **Mo**    | 粉末 | 0.19 | 1      | 原料   |
| **MoO₃**  | 粉末 | 0.29 | 2      | 原料   |
| **C₆Br₆** | 液体 | 0.55 | 1      | 输运剂 |

## 🌡️ 实验方法及参数设置
* ⚗️**实验方法：**CVT
* 🌡️**反应温度与加热程序：**
  * 封管操作
  * 10h升温至700/600°C
  * 在700/600°C保持 72h（双温区生长，低温区600°C）
  * 自然冷却至室温
* 🧪**气体的类型及流量：**
  * 常压下生长。
* 🔬**空间放置**： 未明确标注空间放置方式
- 🌡️ **高温区温度**： `700 °C`
- 🌡️ **低温区温度**： `600 °C`

## 🔬 实验结果与表征
* **[Microscope] 多相混合**: 产物中存在多种相，未完全形成单一相
* **[Microscope] 簇状一维**: 观察到簇状的一维晶体结构
* **[XRD] XRD图谱**: XRD显示主要峰对应MoO₂Br₂，但存在Mo₄O₁₁杂质峰

## 📌 备注
C₂Br₆作为输运剂使用，状态为液体；双温区设置合理，高温区700°C，低温区600°C；反应方程已配平。"""
    
    # 使用传入的参考内容，如果没有则使用默认的新示例
    style_reference = reference_style_content if reference_style_content else default_reference
    
    # 使用字符串拼接而非 f-string，避免 style_reference 中的大括号导致格式化错误
    style_section = """
    # Style Reference (风格参考)
    ⚠️ **重要说明**：以下风格参考文件中的所有数据（包括表格中的数值、横线 "-"、摩尔比等）均为虚构的占位符，**严禁模仿其数据内容**。
    
    请**仅参考**以下 Markdown 的标题层级和排版风格，但**数据内容必须来自用户提供的真实数据**。
    
    特别是配料表部分：如果用户在消息中提供了【真实配料表数据（必须使用）】块，**必须完全忽略**风格参考文件中的配料表数据，直接使用用户提供的真实数据块。

    --- 参考样式开始（仅参考格式，数据为占位符）---
    """ + style_reference + """
    --- 参考样式结束 ---
    """
    return base_prompt + style_section

def get_reviewer_prompt():
    """Role B: 领域审核员的系统提示词"""
    return """
    # Role
    你是一位晶体生长领域的资深审核专家。你的任务是检查实验数据的化学合理性。

    # 审核标准

    ## 1. 质量合理性检查
    - 晶体生长实验通常使用 **mg 级到 g 级** 的原料（0.01g - 10g）。
    - 如果某个原料质量超过 100g，很可能是单位识别错误（mg 被误识别为 g）。
    - 如果质量小于 0.001g，可能是 g 被误识别为 mg。

    ## 2. 摩尔比合理性检查
    - 摩尔比应该在合理范围内（通常 0.1 到 100 之间）。
    - 如果计算出的摩尔比出现极端值（如 1 : 0.001 或 1 : 10000），可能存在：
      - 单位识别错误
      - 化学式识别错误
      - 质量数值识别错误

    ## 3. 化学式合理性检查
    - 检查化学式是否符合常见化合物命名规则。
    - 检查是否存在明显的元素符号错误（如 'cu' 应为 'Cu'）。

    ## 4. 参数合理性检查（支持动态参数）
    - 由于实验参数可能是动态的（如 "Max Temp", "Sintering T", "Source T" 等），你需要：
      - 识别参数类型（温度、时间、压力、速率等）
      - 根据参数类型和实验方法，判断参数值是否在合理范围内
      - 例如：CVT 方法的温度参数通常 500-1200°C，时间参数通常几小时到几天
      - 如果参数值明显异常（如温度超过 2000°C 或时间为负数），需要标记

    ## 5. 方法一致性检查
    - CVT 方法必须同时有输运剂和双温区（或两个温度参数）。
    - Flux 方法必须有大量助熔剂。
    - Solid State 方法通常是化学计量比。

    ## 6. 历史实验对比检查（RAG 记忆回溯）
    - 如果提供了历史实验对比信息，请特别关注以下异常：
      - **温度异常**：如果历史记录中该化合物通常在某个温度范围生长（如 400°C），而当前实验识别为差异很大的温度（如 900°C），应标记为严重警告。
      - **方法不一致**：如果历史记录中该化合物常用某种方法（如 CVT），而当前实验使用不同方法，需要验证合理性。
      - **重复失败配方**：如果历史记录显示某个相似配方曾经失败，应强烈警告当前实验可能重复失败。
    - 基于历史实验的统计信息，判断当前参数是否在合理范围内。
    - 如果发现明显异常，应在 issues 中添加 severity="error" 或 "warning" 的问题。

    # 输出格式
    请以 JSON 格式输出审核结果：
    {{
      "passed": true/false,
      "issues": [
        {{
          "severity": "error/warning/info",
          "field": "字段名（如 ingredients[0].mass_g）",
          "description": "问题描述",
          "suggestion": "修正建议"
        }}
      ],
      "correction_hints": "用于指导重新提取的提示词（如果有严重问题）"
    }}
    """

# ================= 图片处理 =================

def _preprocess_image(image_path: str) -> str:
    """预处理图片并转换为 base64"""
    try:
        with Image.open(image_path) as img:
            img = ImageOps.exif_transpose(img)
            if img.mode != 'RGB':
                img = img.convert('RGB')
            if max(img.size) > 2048:
                img.thumbnail((2048, 2048), Image.Resampling.LANCZOS)
            buffered = io.BytesIO()
            img.save(buffered, format="JPEG", quality=85)
            return base64.b64encode(buffered.getvalue()).decode('utf-8')
    except Exception as e:
        raise Exception(f"图片处理失败: {e}")

# ================= Role A: 视觉感知者 (Perceiver) =================

def perceiver_node(state: AgentState) -> AgentState:
    """
    Role A: 视觉感知者
    负责从图片中提取原始实验数据
    """
    print("\n🔍 [Role A: 视觉感知者] 正在分析图片...")
    
    image_path = state["image_path"]
    correction_hints = state.get("correction_hints", "")
    
    # 预处理图片
    try:
        b64_img = _preprocess_image(image_path)
    except Exception as e:
        return {
            **state,
            "raw_json": json.dumps({"error": str(e)}),
            "needs_correction": True,
            "review_issues": [{"severity": "error", "description": f"图片处理失败: {e}"}]
        }
    
    # 调用视觉模型
    from openai import OpenAI
    vl_client = OpenAI(api_key=API_KEY, base_url=BASE_URL)
    
    # 构建用户提示（如果有修正提示，加入）
    user_prompt = "请分析这张图。"
    if correction_hints:
        user_prompt += f"\n\n⚠️ 修正提示: {correction_hints}\n请特别注意上述问题，重新仔细检查图片。"
    
    try:
        completion = vl_client.chat.completions.create(
            model="qwen-vl-max",
            messages=[
                {"role": "system", "content": get_perceiver_prompt()},
                {"role": "user", "content": [
                    {"type": "text", "text": user_prompt},
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64_img}"}}
                ]}
            ],
            response_format={"type": "json_object"},
            stream=False
        )
        raw_json = completion.choices[0].message.content
        
        print("✅ [Role A] 数据提取完成")
        return {
            **state,
            "raw_json": raw_json,
            "needs_correction": False,
            "correction_hints": "",  # 清除修正提示
            "iteration_count": state.get("iteration_count", 0) + 1
        }
    except Exception as e:
        return {
            **state,
            "raw_json": json.dumps({"error": str(e)}),
            "needs_correction": True,
            "review_issues": [{"severity": "error", "description": f"视觉模型调用失败: {e}"}]
        }

# ================= RAG: 历史实验记忆回溯 =================

def extract_main_compound(data: dict) -> Optional[str]:
    """
    从实验数据中提取主要化合物名称（通常是产物）
    支持新旧两种 Schema 格式
    
    Args:
        data: 实验数据字典
        
    Returns:
        主要化合物名称，如果未找到则返回 None
    """
    compounds = []
    
    for exp in data.get("experiments", []):
        # 类型检查：确保 exp 是字典
        if not isinstance(exp, dict):
            continue
        
        # 优先从 material_info 中提取（新 Schema）
        material_info = exp.get("material_info", {})
        if material_info and isinstance(material_info, dict) and material_info.get("formula"):
            return material_info.get("formula")
        
        # 从配料表中提取化合物（排除输运剂）
        ingredients = exp.get("ingredients", [])
        
        # 新格式：ingredients 是对象，包含 precursors
        if isinstance(ingredients, dict):
            precursors = ingredients.get("precursors", [])
            for p in precursors:
                name = p.get("name", "")
                role = p.get("role", "")
                # 排除输运剂和助熔剂，优先选择原料
                if name and name not in ['-', 'null', '']:
                    if 'Transport' not in role:
                        compounds.append(name)
        
        # 旧格式：ingredients 是数组
        elif isinstance(ingredients, list):
            for ing in ingredients:
                compound = ing.get("compound", "")
                role = ing.get("role", "")
                # 排除输运剂和助熔剂，优先选择原料
                if compound and compound not in ['-', 'null', '']:
                    if 'Transport' not in role:
                        compounds.append(compound)
        
        # 也可以从反应方程式中提取
        reaction = exp.get("reaction_equation", "")
        if reaction:
            # 简单提取：反应方程式通常包含产物
            # 这里可以进一步优化，使用化学式解析
            pass
    
    # 返回第一个非输运剂的化合物（通常是主要产物）
    return compounds[0] if compounds else None

def compare_with_historical_experiments(
    current_data: dict,
    historical_experiments: List[dict]
) -> str:
    """
    对比当前实验与历史实验的参数差异，生成对比报告
    
    Args:
        current_data: 当前实验数据
        historical_experiments: 历史实验记录列表
        
    Returns:
        对比报告文本
    """
    if not historical_experiments:
        return ""
    
    report_lines = []
    report_lines.append("\n" + "="*70)
    report_lines.append("📚 历史实验记忆回溯 (RAG)")
    report_lines.append("="*70)
    
    # 提取当前实验的关键参数
    current_params = {}
    for exp in current_data.get("experiments", []):
        # 类型检查：确保 exp 是字典
        if not isinstance(exp, dict):
            continue
        
        meta = exp.get("meta", {})
        process = exp.get("process", {})
        
        # 确保 meta 和 process 是字典
        if not isinstance(meta, dict):
            meta = {}
        if not isinstance(process, dict):
            process = {}
        
        current_params = {
            "method": meta.get("method", ""),
            "high_temp": process.get("high_temp", ""),
            "low_temp": process.get("low_temp", ""),
            "ingredients": exp.get("ingredients", [])
        }
        break  # 只处理第一个实验
    
    # 统计历史实验的参数分布
    methods = []
    high_temps = []
    low_temps = []
    failed_experiments = []
    
    for hist_exp in historical_experiments:
        # 解析历史实验的 JSON
        hist_json_str = hist_exp.get("reviewed_json") or hist_exp.get("raw_json", "{}")
        try:
            hist_data = json.loads(hist_json_str)
            if "experiments" not in hist_data:
                hist_data = {"experiments": [hist_data]}
            
            for hist_exp_item in hist_data.get("experiments", []):
                hist_meta = hist_exp_item.get("meta", {})
                hist_process = hist_exp_item.get("process", {})
                
                method = hist_meta.get("method", "")
                
                # 提取参数（支持动态参数和固定参数）
                temp_params = []
                if hist_process.get("dynamic_params"):
                    for param in hist_process.get("dynamic_params", []):
                        if param.get("type") == "temperature":
                            temp_params.append(param.get("value", ""))
                else:
                    # 向后兼容固定参数
                    if hist_process.get("high_temp"):
                        temp_params.append(hist_process.get("high_temp"))
                    if hist_process.get("low_temp"):
                        temp_params.append(hist_process.get("low_temp"))
                
                if method:
                    methods.append(method)
                for temp in temp_params:
                    if temp and temp not in ['-', 'null', '']:
                        high_temps.append(temp)  # 统一存储到 high_temps
                
                # 检查是否为失败实验
                if not hist_exp.get("review_passed", False):
                    # 提取温度参数用于失败实验记录
                    hist_high_temp = temp_params[0] if temp_params else ""
                    hist_low_temp = temp_params[1] if len(temp_params) > 1 else ""
                    failed_experiments.append({
                        "id": hist_exp.get("id"),
                        "method": method,
                        "high_temp": hist_high_temp,
                        "low_temp": hist_low_temp,
                        "date": hist_meta.get("date", "")
                    })
        except:
            continue
    
    # 生成对比分析
    report_lines.append(f"\n📊 历史实验统计（共 {len(historical_experiments)} 条记录）:")
    
    # 方法对比
    if methods:
        method_counts = {}
        for m in methods:
            method_counts[m] = method_counts.get(m, 0) + 1
        most_common_method = max(method_counts.items(), key=lambda x: x[1])[0]
        report_lines.append(f"  • 常用方法: {most_common_method} ({method_counts[most_common_method]} 次)")
        if current_params.get("method") and current_params["method"] != most_common_method:
            report_lines.append(f"  ⚠️ 当前方法 ({current_params['method']}) 与历史常用方法不一致")
    
    # 温度对比
    if high_temps:
        # 提取温度数值进行统计
        temp_values = []
        for temp_str in high_temps:
            match = re.search(r'(\d+)', str(temp_str))
            if match:
                temp_values.append(int(match.group(1)))
        
        if temp_values:
            avg_temp = sum(temp_values) / len(temp_values)
            min_temp = min(temp_values)
            max_temp = max(temp_values)
            report_lines.append(f"  • 历史高温范围: {min_temp}°C - {max_temp}°C (平均: {avg_temp:.0f}°C)")
            
            # 检查当前温度是否异常（支持动态参数）
            current_params_list = current_params.get("params", [])
            for param_str in current_params_list:
                if "temp" in param_str.lower() or "温度" in param_str or "°C" in param_str or "℃" in param_str:
                    # 提取温度值
                    temp_match = re.search(r'(\d+)', param_str)
                    if temp_match:
                        current_temp_val = int(temp_match.group(1))
                        if current_temp_val < min_temp - 50 or current_temp_val > max_temp + 50:
                            report_lines.append(f"  ❌ 异常检测: 当前参数 ({param_str}) 与历史范围差异较大！")
                            report_lines.append(f"     历史记录中该化合物通常在 {min_temp}°C - {max_temp}°C 生长")
    
    # 失败实验警告
    if failed_experiments:
        report_lines.append(f"\n⚠️ 发现 {len(failed_experiments)} 个失败的历史实验:")
        for failed in failed_experiments[:3]:  # 只显示前3个
            report_lines.append(f"  • 实验 #{failed['id']} ({failed['date']}): {failed['method']}, {failed['high_temp']}")
            # 检查是否与当前实验相似
            if (current_params.get("method") == failed['method'] and 
                current_params.get("high_temp") == failed['high_temp']):
                report_lines.append(f"    ⚠️ 警告: 检测到与失败实验 #{failed['id']} 相似的配方！")
    
    report_lines.append("="*70 + "\n")
    
    return "\n".join(report_lines)

def retrieve_historical_experiments(data: dict) -> List[dict]:
    """
    从数据库检索历史实验记录
    
    Args:
        data: 当前实验数据
        
    Returns:
        历史实验记录列表
    """
    try:
        from database import get_db
        
        db = get_db()
        main_compound = extract_main_compound(data)
        
        if not main_compound:
            return []
        
        # 检索历史实验
        historical_experiments = db.search_experiments_by_compound(
            compound_name=main_compound,
            limit=10
        )
        
        return historical_experiments
    except Exception as e:
        print(f"⚠️ [RAG] 检索历史实验失败: {e}")
        return []

# ================= Role B: 领域审核员 (Reviewer) =================

def reviewer_node(state: AgentState) -> AgentState:
    """
    Role B: 领域审核员
    负责校验化学合理性，触发自修正机制
    """
    print("\n🔬 [Role B: 领域审核员] 正在审核数据...")
    
    raw_json_str = state.get("raw_json", "{}")
    
    # 解析 JSON
    try:
        cleaned = raw_json_str.replace("```json", "").replace("```", "").strip()
        data = json.loads(cleaned)
        if "experiments" not in data:
            data = {"experiments": [data]}
    except Exception as e:
        return {
            **state,
            "review_passed": False,
            "review_issues": [{"severity": "error", "description": f"JSON 解析失败: {e}"}],
            "needs_correction": True,
            "correction_hints": "请确保输出有效的 JSON 格式。"
        }
    
    # 使用 LLM 进行智能审核
    llm = ChatOpenAI(
        model="qwen-plus",
        openai_api_key=API_KEY,
        openai_api_base=BASE_URL,
        temperature=0.0
    )
    
    # ========== RAG: 历史实验记忆回溯 ==========
    print("🔍 [RAG] 正在检索历史实验记录...")
    historical_experiments = retrieve_historical_experiments(data)
    
    historical_context = ""
    if historical_experiments:
        print(f"✅ [RAG] 找到 {len(historical_experiments)} 条历史实验记录")
        historical_context = compare_with_historical_experiments(data, historical_experiments)
        print(historical_context)
    else:
        print("ℹ️ [RAG] 未找到相关历史实验记录")
    
    # ========== 外部文献 RAG: 配方校验和知识增强 ==========
    external_issues = []
    external_knowledge_context = ""
    
    if EXTERNAL_RAG_AVAILABLE:
        print("🔍 [External RAG] 正在检索外部文献知识库...")
        
        for exp in data.get("experiments", []):
            # 类型检查：确保 exp 是字典
            if not isinstance(exp, dict):
                print(f"  ⚠️ [External RAG] 跳过非字典类型的实验数据: {type(exp)}")
                continue
            
            # 提取主要化合物
            main_compound = extract_main_compound({"experiments": [exp]})
            method = exp.get("meta", {}).get("method", "")
            
            if main_compound:
                try:
                    # 配方校验：基于外部知识检查识别错误
                    compound_issues = validate_compound_with_knowledge(main_compound, method)
                    external_issues.extend(compound_issues)
                    
                    if compound_issues:
                        print(f"  ⚠️ [External RAG] 发现 {len(compound_issues)} 个配方校验问题")
                    
                    # 检索相关知识（用于 LLM 审核）
                    knowledge = retrieve_knowledge(main_compound, method, top_k=3)
                    if knowledge:
                        print(f"  ✅ [External RAG] 找到 {len(knowledge)} 条关于 {main_compound} 的知识")
                        
                        # 构建知识上下文
                        knowledge_texts = [item["text"][:200] + "..." for item in knowledge[:3]]
                        external_knowledge_context += f"\n\n## 外部文献知识库 - {main_compound}:\n"
                        for i, text in enumerate(knowledge_texts, 1):
                            external_knowledge_context += f"{i}. {text}\n"
                except Exception as e:
                    print(f"  ⚠️ [External RAG] 检索失败 ({main_compound}): {e}")
    else:
        print("ℹ️ [External RAG] 外部文献 RAG 功能未启用")
    
    # 获取人工反馈（如果有）
    correction_hints = state.get("correction_hints", "")
    human_feedback = state.get("human_feedback", "")
    
    # 如果有反馈，加入到审核提示中