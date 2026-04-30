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
    print("[WARN] 警告: pymatgen 未安装，将使用备用原子量表。建议运行: pip install pymatgen")

# 外部文献 RAG
try:
    from external_rag import retrieve_knowledge, validate_compound_with_knowledge, retrieve_material_properties
    EXTERNAL_RAG_AVAILABLE = True
except ImportError:
    EXTERNAL_RAG_AVAILABLE = False
    print("[WARN] 警告: external_rag 模块未找到，外部文献 RAG 功能将不可用。")

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
            print(f"[WARN] pymatgen 解析失败 ({formula}): {e}，使用备用方法")
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
            print(f"[WARN] 未知元素: {elem}，在化学式 {formula} 中")
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
    
    **[WARN] 重要警告：风格参考文件（Style Reference）的数据说明**：
       - 风格参考文件中的所有数据（包括表格中的数值、横线 "-"、摩尔比等）**均为虚构的占位符**。
       - **严禁模仿风格参考文件中的数据内容**，仅参考其标题层级和排版风格。
       - 对于配料表（Ingredients Table），如果用户提供了【真实配料表数据（必须使用）】块，**必须完全忠实于该数据块**，直接将其嵌入表格中，完全忽略风格参考文件中的配料表数据。
    
    **[TOOL] 【静默原则/客观性约束】严禁添加质疑性备注或警告信息**：
       - **绝对中立**：你是一个客观的记录工具，不是评审专家。你的唯一任务是将 JSON 数据转换为格式化的 Markdown 报告，**严禁**对数据的合理性、科学性、矛盾点进行任何形式的点评、质疑或警告。
       - **禁止质疑**：即使数据看起来违反常理（例如"固相法"使用了"双温区"），你也必须照实记录，**严禁**添加任何"疑点说明"、"警告符号([WARN])"、"建议核实"、"可能为..."等主观性文字。
       - **信任上游**：默认所有输入的 JSON 数据都已经过人工专家（Role B）的严格审核。如果数据中有矛盾，那是专家的意图，不需要你来指出或解释。
       - **禁止加戏**：在"备注"或"说明"部分，只允许通过 RAG 补充客观的物理性质（如熔点、空间群），**严禁**生成任何主观的对实验设计的评价、质疑或建议。
       - **示例禁止项**：严禁在报告中出现以下类型的内容：
         * "[WARN] 可能为记录重复..."
         * "[WARN] 方法学疑点：尽管标记为 Solid State... 但更接近 CVT..."
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
    default_reference = """# [CHEM] MoO₂Br₂的单晶制备
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
* [CHEM]**气体的类型及流量：**
  * 常压下生长。
* [LAB]**空间放置**： 未明确标注空间放置方式
- 🌡️ **高温区温度**： `700 °C`
- 🌡️ **低温区温度**： `600 °C`

## [LAB] 实验结果与表征
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
    [WARN] **重要说明**：以下风格参考文件中的所有数据（包括表格中的数值、横线 "-"、摩尔比等）均为虚构的占位符，**严禁模仿其数据内容**。
    
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
    print("\n[INFO] [Role A: 视觉感知者] 正在分析图片...")
    
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
        user_prompt += f"\n\n[WARN] 修正提示: {correction_hints}\n请特别注意上述问题，重新仔细检查图片。"
    
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
        
        print("[OK] [Role A] 数据提取完成")
        return {
            **state,
            "raw_json": raw_json,
            "needs_correction": False,
            # 保留修正提示，以便后续节点（reviewer、formatter）也能看到用户反馈
            "correction_hints": state.get("correction_hints", ""),
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
    report_lines.append("[HIST] 历史实验记忆回溯 (RAG)")
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
    report_lines.append(f"\n[STATS] 历史实验统计（共 {len(historical_experiments)} 条记录）:")
    
    # 方法对比
    if methods:
        method_counts = {}
        for m in methods:
            method_counts[m] = method_counts.get(m, 0) + 1
        most_common_method = max(method_counts.items(), key=lambda x: x[1])[0]
        report_lines.append(f"  • 常用方法: {most_common_method} ({method_counts[most_common_method]} 次)")
        if current_params.get("method") and current_params["method"] != most_common_method:
            report_lines.append(f"  [WARN] 当前方法 ({current_params['method']}) 与历史常用方法不一致")
    
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
                            report_lines.append(f"  [ERROR] 异常检测: 当前参数 ({param_str}) 与历史范围差异较大！")
                            report_lines.append(f"     历史记录中该化合物通常在 {min_temp}°C - {max_temp}°C 生长")
    
    # 失败实验警告
    if failed_experiments:
        report_lines.append(f"\n[WARN] 发现 {len(failed_experiments)} 个失败的历史实验:")
        for failed in failed_experiments[:3]:  # 只显示前3个
            report_lines.append(f"  • 实验 #{failed['id']} ({failed['date']}): {failed['method']}, {failed['high_temp']}")
            # 检查是否与当前实验相似
            if (current_params.get("method") == failed['method'] and 
                current_params.get("high_temp") == failed['high_temp']):
                report_lines.append(f"    [WARN] 警告: 检测到与失败实验 #{failed['id']} 相似的配方！")
    
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
        print(f"[WARN] [RAG] 检索历史实验失败: {e}")
        return []

# ================= Role B: 领域审核员 (Reviewer) =================

def reviewer_node(state: AgentState) -> AgentState:
    """
    Role B: 领域审核员
    负责校验化学合理性，触发自修正机制
    """
    print("\n[LAB] [Role B: 领域审核员] 正在审核数据...")
    
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
    print("[INFO] [RAG] 正在检索历史实验记录...")
    historical_experiments = retrieve_historical_experiments(data)
    
    historical_context = ""
    if historical_experiments:
        print(f"[OK] [RAG] 找到 {len(historical_experiments)} 条历史实验记录")
        historical_context = compare_with_historical_experiments(data, historical_experiments)
        # print(historical_context)
    else:
        print("[INFO] [RAG] 未找到相关历史实验记录")
    
    # ========== 外部文献 RAG: 配方校验和知识增强 ==========
    external_issues = []
    external_knowledge_context = ""
    
    if EXTERNAL_RAG_AVAILABLE:
        print("[INFO] [External RAG] 正在检索外部文献知识库...")
        
        for exp in data.get("experiments", []):
            # 类型检查：确保 exp 是字典
            if not isinstance(exp, dict):
                print(f"  [WARN] [External RAG] 跳过非字典类型的实验数据: {type(exp)}")
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
                        print(f"  [WARN] [External RAG] 发现 {len(compound_issues)} 个配方校验问题")
                    
                    # 检索相关知识（用于 LLM 审核）
                    knowledge = retrieve_knowledge(main_compound, method, top_k=3)
                    if knowledge:
                        print(f"  [OK] [External RAG] 找到 {len(knowledge)} 条关于 {main_compound} 的知识")
                        
                        # 构建知识上下文
                        knowledge_texts = [item["text"][:200] + "..." for item in knowledge[:3]]
                        external_knowledge_context += f"\n\n## 外部文献知识库 - {main_compound}:\n"
                        for i, text in enumerate(knowledge_texts, 1):
                            external_knowledge_context += f"{i}. {text}\n"
                except Exception as e:
                    print(f"  [WARN] [External RAG] 检索失败 ({main_compound}): {e}")
    else:
        print("ℹ️ [External RAG] 外部文献 RAG 功能未启用")
    
    # 获取人工反馈（如果有）
    correction_hints = state.get("correction_hints", "")
    human_feedback = state.get("human_feedback", "")
    
    # 如果有反馈，加入到审核提示中
    feedback_context = ""
    if correction_hints or human_feedback:
        feedback_text = correction_hints or human_feedback
        feedback_context = f"\n\n[WARN] 人工反馈: {feedback_text}\n请根据上述反馈，特别关注相关问题，调整审核标准。"
    
    # 增强的 Prompt，明确要求返回 JSON
    enhanced_reviewer_prompt = get_reviewer_prompt() + "\n\n**重要**：你必须只返回 JSON 格式，不要添加任何其他说明文字。直接输出 JSON 对象，不要使用代码块标记。"
    
    review_prompt = ChatPromptTemplate.from_messages([
        ("system", enhanced_reviewer_prompt),
        ("human", "请审核以下实验数据，只返回 JSON 格式（不要添加任何其他文字）：\n\n{json_data}{historical_context}{external_knowledge_context}{feedback_context}")
    ])
    
    try:
        review_response = llm.invoke(review_prompt.format_messages(
            json_data=json.dumps(data, ensure_ascii=False, indent=2),
            historical_context=historical_context,
            external_knowledge_context=external_knowledge_context,
            feedback_context=feedback_context
        ))
        review_text = review_response.content.strip()
        
        # 调试输出（可选，生产环境可以注释掉）
        # print(f"[INFO] [调试] 审核 LLM 原始返回: {review_text[:200]}...")
        
        # 解析审核结果
        review_result = _parse_review_result(review_text)
        
        # 同时进行程序化检查（补充 LLM 审核）
        programmatic_issues = _programmatic_review(data)
        review_result["issues"].extend(programmatic_issues)
        
        # 基于历史实验的异常检测（RAG）
        if historical_experiments:
            rag_issues = _rag_anomaly_detection(data, historical_experiments)
            review_result["issues"].extend(rag_issues)
        
        # 外部文献 RAG 校验结果
        if external_issues:
            review_result["issues"].extend(external_issues)
        
        # 判断是否需要修正
        has_errors = any(issue.get("severity") == "error" for issue in review_result["issues"])
        needs_correction = has_errors and state.get("iteration_count", 0) < state.get("max_iterations", 3)
        
        print(f"[STATS] [Role B] 审核完成: {'通过' if review_result.get('passed') and not has_errors else '发现问题'}")
        if review_result["issues"]:
            print(f"\n📋 审核问题详情 ({len(review_result['issues'])} 个):")
            print("-" * 70)
            for idx, issue in enumerate(review_result["issues"], 1):
                severity = issue.get('severity', 'info')
                field = issue.get('field', '-')
                desc = issue.get('description', '-')
                suggestion = issue.get('suggestion', '')
                severity_icon = {"error": "[ERROR]", "warning": "[WARN]", "info": "ℹ️"}.get(severity, "ℹ️")
                print(f"  {idx}. {severity_icon} [{severity.upper()}] {desc}")
                if field != '-':
                    print(f"     字段: {field}")
                if suggestion:
                    print(f"     建议: {suggestion}")
            print("-" * 70)
        
        return {
            **state,
            "reviewed_json": json.dumps(data, ensure_ascii=False),
            "review_passed": review_result.get("passed", False) and not has_errors,
            "review_issues": review_result["issues"],
            "needs_correction": needs_correction,
            "correction_hints": review_result.get("correction_hints", "")
        }
    except Exception as e:
        error_type = type(e).__name__
        error_msg = str(e)
        print(f"[WARN] [Role B] 审核过程出错: {error_type}: {error_msg}")
        import traceback
        print(f"   详细错误信息: {traceback.format_exc()[:]}")  # 只显示前500字符
        
        # 如果审核失败，仍然继续流程（但标记为未通过）
        return {
            **state,
            "reviewed_json": json.dumps(data, ensure_ascii=False),
            "review_passed": False,
            "review_issues": [{
                "severity": "warning",
                "field": "system",
                "description": f"审核过程出错: {error_type}: {error_msg}",
                "suggestion": "请检查审核 LLM 的返回格式是否正确"
            }],
            "needs_correction": False
        }

def _parse_review_result(review_text: str) -> dict:
    """解析审核结果（从 LLM 返回的文本中提取 JSON）"""
    try:
        # 尝试直接解析 JSON
        cleaned = review_text.replace("```json", "").replace("```", "").strip()
        match = re.search(r'\{.*\}', cleaned, re.DOTALL)
        if match:
            json_str = match.group()
            result = json.loads(json_str)
            # 验证结果格式
            if isinstance(result, dict) and "passed" in result:
                return result
    except json.JSONDecodeError as e:
        print(f"[WARN] [Role B] JSON 解析错误: {e}")
        print(f"   原始文本片段: {review_text[:200]}...")
    except Exception as e:
        print(f"[WARN] [Role B] 解析审核结果时出错: {type(e).__name__}: {e}")
        print(f"   原始文本片段: {review_text[:200]}...")
    
    # 如果解析失败，返回默认结果
    print("[WARN] [Role B] 无法解析审核结果，使用默认值（通过审核）")
    return {
        "passed": True,
        "issues": [],
        "correction_hints": ""
    }

def _rag_anomaly_detection(current_data: dict, historical_experiments: List[dict]) -> list:
    """
    基于历史实验的异常检测（程序化检查）
    
    Args:
        current_data: 当前实验数据
        historical_experiments: 历史实验记录列表
        
    Returns:
        异常检测问题列表
    """
    issues = []
    
    if not historical_experiments:
        return issues
    
    # 提取当前实验参数
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
        }
        break
    
    # 统计历史实验参数
    high_temps = []
    methods = []
    failed_experiments = []
    
    for hist_exp in historical_experiments:
        hist_json_str = hist_exp.get("reviewed_json") or hist_exp.get("raw_json", "{}")
        try:
            hist_data = json.loads(hist_json_str)
            if "experiments" not in hist_data:
                hist_data = {"experiments": [hist_data]}
            
            for hist_exp_item in hist_data.get("experiments", []):
                # 类型检查：确保 hist_exp_item 是字典
                if not isinstance(hist_exp_item, dict):
                    continue
                
                hist_meta = hist_exp_item.get("meta", {})
                hist_process = hist_exp_item.get("process", {})
                
                # 确保 meta 和 process 是字典
                if not isinstance(hist_meta, dict):
                    hist_meta = {}
                if not isinstance(hist_process, dict):
                    hist_process = {}
                
                method = hist_meta.get("method", "")
                high_temp = hist_process.get("high_temp", "")
                
                if method:
                    methods.append(method)
                if high_temp and high_temp not in ['-', 'null', '']:
                    match = re.search(r'(\d+)', str(high_temp))
                    if match:
                        high_temps.append(int(match.group(1)))
                
                if not hist_exp.get("review_passed", False):
                    failed_experiments.append({
                        "id": hist_exp.get("id"),
                        "method": method,
                        "high_temp": high_temp
                    })
        except:
            continue
    
    # 温度异常检测
    if high_temps and current_params.get("high_temp"):
        current_temp_match = re.search(r'(\d+)', str(current_params["high_temp"]))
        if current_temp_match:
            current_temp_val = int(current_temp_match.group(1))
            min_hist_temp = min(high_temps)
            max_hist_temp = max(high_temps)
            avg_hist_temp = sum(high_temps) / len(high_temps)
            
            # 如果当前温度与历史平均温度差异超过 100°C，标记为异常
            if abs(current_temp_val - avg_hist_temp) > 100:
                issues.append({
                    "severity": "warning",
                    "field": "process.high_temp",
                    "description": f"温度异常：当前高温 ({current_params['high_temp']}) 与历史记录差异较大。历史记录中该化合物通常在 {min_hist_temp}°C - {max_hist_temp}°C 生长（平均: {avg_hist_temp:.0f}°C）",
                    "suggestion": f"请确认温度是否正确。如果确实是新尝试，请说明原因。"
                })
    
    # 方法不一致检测
    if methods and current_params.get("method"):
        method_counts = {}
        for m in methods:
            method_counts[m] = method_counts.get(m, 0) + 1
        most_common_method = max(method_counts.items(), key=lambda x: x[1])[0]
        
        if current_params["method"] != most_common_method:
            issues.append({
                "severity": "info",
                "field": "meta.method",
                "description": f"方法不一致：当前使用 {current_params['method']}，但历史记录中常用 {most_common_method}",
                "suggestion": "如果这是有意尝试新方法，可以忽略此提示。"
            })
    
    # 重复失败配方检测
    if failed_experiments and current_params.get("method") and current_params.get("high_temp"):
        for failed in failed_experiments:
            if (current_params["method"] == failed["method"] and 
                current_params["high_temp"] == failed["high_temp"]):
                issues.append({
                    "severity": "error",
                    "field": "process",
                    "description": f"[WARN] 检测到与失败实验 #{failed['id']} 相似的配方（方法: {failed['method']}, 温度: {failed['high_temp']}）",
                    "suggestion": f"历史记录显示实验 #{failed['id']} 使用相同参数但失败了。请检查配方是否有问题，或考虑调整参数。"
                })
                break  # 只报告第一个匹配的失败实验
    
    return issues

def _programmatic_review(data: dict) -> list:
    """程序化审核（补充 LLM 审核）"""
    issues = []
    
    for exp in data.get("experiments", []):
        # 类型检查：确保 exp 是字典
        if not isinstance(exp, dict):
            continue
        
        ingredients = exp.get("ingredients", [])
        
        # 确保 ingredients 是列表
        if not isinstance(ingredients, list):
            continue
        
        for idx, ing in enumerate(ingredients):
            # 类型检查：确保 ing 是字典
            if not isinstance(ing, dict):
                continue
            compound = ing.get("compound", "")
            mass_str = ing.get("mass_g", "")
            
            # 检查质量合理性
            if mass_str and mass_str not in ['-', 'null', '']:
                mass_val, _ = _parse_mass(mass_str)  # 忽略毫摩尔数标志，只使用质量值
                if mass_val > 100:  # 超过 100g 不合理
                    issues.append({
                        "severity": "error",
                        "field": f"ingredients[{idx}].mass_g",
                        "description": f"{compound} 的质量 {mass_str} 过大（>100g），可能是单位识别错误（mg 被误识别为 g）",
                        "suggestion": f"请重新检查 {compound} 的质量单位，确认是否为 mg 而非 g"
                    })
                elif 0 < mass_val < 0.001:  # 小于 0.001g 可能不合理
                    issues.append({
                        "severity": "warning",
                        "field": f"ingredients[{idx}].mass_g",
                        "description": f"{compound} 的质量 {mass_str} 过小（<0.001g），请确认单位是否正确",
                        "suggestion": "请确认质量单位"
                    })
            
            # 检查化学式是否可解析
            if compound and compound not in ['-', 'null', '']:
                mol_weight = get_molecular_weight(compound)
                if mol_weight == 0:
                    issues.append({
                        "severity": "warning",
                        "field": f"ingredients[{idx}].compound",
                        "description": f"化学式 {compound} 无法解析，可能是识别错误",
                        "suggestion": f"请检查化学式 {compound} 是否正确"
                    })
    
    return issues

def _parse_mass(mass_str: str) -> Tuple[float, bool]:
    """
    解析质量字符串，返回数值（单位：g）和是否为毫摩尔数
    
    Returns:
        tuple[float, bool]: (质量值（单位：g）, 是否为毫摩尔数)
        如果是毫摩尔数，返回的 float 是摩尔数（而非质量）
    """
    if not mass_str or mass_str in ['-', 'null', '']:
        return (0.0, False)
    
    mass_lower = str(mass_str).lower()
    
    # 优先检查是否为毫摩尔数（mmol）
    if 'mmol' in mass_lower:
        # 提取数字
        match = re.search(r'([\d\.]+)', str(mass_str))
        if match:
            mmol_value = float(match.group(1))
            # 返回摩尔数（mmol / 1000 = mol）
            return (mmol_value / 1000.0, True)
        return (0.0, False)
    
    # 提取数字（增强鲁棒性：支持 "10mg" 这样的格式）
    # 使用更精确的正则表达式，确保能正确提取数字
    match = re.search(r'([\d\.]+)', str(mass_str))
    if not match:
        return (0.0, False)
    
    value = float(match.group(1))
    
    # 检查单位（增强对 "mg" 的检测，防止 "10mg" 被误解析）
    if 'mg' in mass_lower or '毫克' in mass_lower:
        # 确保是 mg 单位，而不是其他包含 "mg" 的字符串
        # 检查 "mg" 是否紧跟在数字后面，或者有空格/标点分隔
        mg_pattern = r'[\d\.]+\s*mg|mg\s*[\d\.]+|毫克'
        if re.search(mg_pattern, mass_lower, re.IGNORECASE):
            value = value / 1000.0  # mg -> g
    elif 'kg' in mass_lower or '千克' in mass_lower:
        value = value * 1000.0  # kg -> g
    
    return (value, False)

# ================= Role C: 数据工程师 (Formatter) =================

def formatter_node(state: AgentState) -> AgentState:
    """
    Role C: 数据工程师
    负责计算摩尔比、生成 Markdown、保存文件
    """
    print("\n📝 [Role C: 数据工程师] 正在格式化数据...")
    
    reviewed_json_str = state.get("reviewed_json", state.get("raw_json", "{}"))
    image_reference_path = state.get("image_reference_path", "")
    
    # 解析 JSON
    try:
        cleaned = reviewed_json_str.replace("```json", "").replace("```", "").strip()
        data = json.loads(cleaned)
        if "experiments" not in data:
            data = {"experiments": [data]}
    except Exception as e:
        return {
            **state,
            "formatted_markdown": f"# [ERROR] 错误\n\nJSON 解析失败: {e}",
        }
    
    # 获取人工反馈（如果有）
    correction_hints = state.get("correction_hints", "")
    human_feedback = state.get("human_feedback", "")
    feedback_text = correction_hints or human_feedback
    
    # ========== 外部文献 RAG: 知识增强（补充材料物理性质）==========
    if EXTERNAL_RAG_AVAILABLE:
        print("[INFO] [Knowledge Enhancement] 正在补充材料信息...")
        
        for exp in data.get("experiments", []):
            main_compound = extract_main_compound({"experiments": [exp]})
            
            if main_compound:
                try:
                    # 检索材料物理性质
                    material_info = retrieve_material_properties(main_compound)
                    
                    if material_info:
                        # 添加到实验数据中
                        if "material_properties" not in exp:
                            exp["material_properties"] = {}
                        exp["material_properties"].update(material_info)
                        print(f"  [OK] 已补充 {main_compound} 的物理性质: {list(material_info.keys())}")
                    else:
                        print(f"  ℹ️ 未找到 {main_compound} 的物理性质信息")
                except Exception as e:
                    print(f"  [WARN] [Knowledge Enhancement] 检索失败 ({main_compound}): {e}")
    else:
        print("ℹ️ [Knowledge Enhancement] 外部文献 RAG 功能未启用")
    
    # 计算并补全摩尔比
    print("  🔢 开始计算摩尔比...")
    data = _calculate_molar_ratios(data)
    
    # 调试：检查摩尔比是否已计算
    print("  [INFO] 检查计算后的摩尔比:")
    for exp in data.get("experiments", []):
        ingredients = exp.get("ingredients", {})
        if isinstance(ingredients, dict):
            precursors = ingredients.get("precursors", [])
            if isinstance(precursors, list):
                for p in precursors:
                    if isinstance(p, dict):
                        name = p.get("name", "未知")
                        molar_ratio = p.get("molar_ratio", "未设置")
                        print(f"    - {name}: {molar_ratio}")
        elif isinstance(ingredients, list):
            for i in ingredients:
                if isinstance(i, dict):
                    compound = i.get("compound", "未知")
                    molar_ratio = i.get("molar_ratio", "未设置")
                    print(f"    - {compound}: {molar_ratio}")
    
    # 生成 Markdown（使用 LLM 驱动的风格迁移生成）
    try:
        # 读取风格参考文件（优先使用新示例）
        style_reference_paths = ["实验记录示例新.md", "实验记录示例.md"]
        style_reference_content = ""
        for path in style_reference_paths:
            if os.path.exists(path):
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        style_reference_content = f.read()
                    print(f"  [OK] 已加载风格参考文件: {path}")
                    break
                except Exception as e:
                    print(f"  [WARN] 读取风格参考文件失败 ({path}): {e}")
        
        # 使用 LLM 生成 Markdown
        markdown = generate_markdown_with_llm(
            data, 
            image_reference_path, 
            feedback_text,
            style_reference_content
        )
        print("  [OK] 使用 LLM 生成 Markdown 完成")
    except Exception as e:
        print(f"  [WARN] LLM 生成 Markdown 失败: {e}，回退到传统方法")
        # 回退到传统方法
        markdown = generate_markdown(data, image_reference_path, feedback_text)
    
    # 保存文件
    output_path = state.get("output_path", "")
    review_issues = state.get("review_issues", [])
    
    if output_path:
        try:
            output_dir = os.path.dirname(output_path)
            if output_dir and not os.path.exists(output_dir):
                os.makedirs(output_dir)
            with open(output_path, "w", encoding="utf-8") as f:
                f.write(markdown)
            print(f"[OK] [Role C] 文件已保存: {output_path}")
            
            # 同时保存审核问题到 JSON 文件（可选）
            if review_issues:
                issues_json_path = output_path.replace(".md", "_issues.json")
                with open(issues_json_path, "w", encoding="utf-8") as f:
                    json.dump({
                        "image_path": state.get("image_path", ""),
                        "iteration_count": state.get("iteration_count", 0),
                        "review_passed": state.get("review_passed", False),
                        "issues": review_issues
                    }, f, ensure_ascii=False, indent=2)
                print(f"📋 [Role C] 审核问题已保存: {issues_json_path}")
        except Exception as e:
            print(f"[WARN] [Role C] 文件保存失败: {e}")
    
    return {
        **state,
        "formatted_markdown": markdown
    }

def _calculate_molar_ratios(data: dict) -> dict:
    """计算并补全缺失的摩尔比（支持新旧两种 Schema 格式）"""
    for exp in data.get("experiments", []):
        # 类型检查：确保 exp 是字典
        if not isinstance(exp, dict):
            continue
        
        ingredients = exp.get("ingredients", [])
        valid = []
        
        # 新格式：ingredients 是对象，包含 precursors
        if isinstance(ingredients, dict):
            precursors = ingredients.get("precursors", [])
            # 确保 precursors 是列表
            if not isinstance(precursors, list):
                precursors = []
            
            for item in precursors:
                # 类型检查：确保 item 是字典
                if not isinstance(item, dict):
                    continue
                
                # 如果已经有比值，跳过（与旧格式保持一致）
                existing_ratio = item.get('molar_ratio')
                if existing_ratio is not None and str(existing_ratio).strip() not in ['-', 'null', 'None', '']:
                    continue
                
                name = item.get("name", "")
                mass = item.get("mass", "")
                
                if not name or str(name) in ['-', 'null', 'None', '']:
                    continue
                
                if not mass or str(mass) in ['-', 'null', 'None', '']:
                    continue
                
                mass_val, is_mmol = _parse_mass(str(mass))
                
                if is_mmol:
                    # 如果已经是毫摩尔数，直接使用
                    moles = mass_val
                else:
                    # 否则通过分子量计算
                    mol_mass = get_molecular_weight(str(name))
                    if mol_mass > 0 and mass_val > 0:
                        moles = mass_val / mol_mass
                    else:
                        continue
                
                if moles > 0:
                    valid.append({
                        'item': item,
                        'moles': moles,
                        'role': str(item.get('role', ''))
                    })
        
        # 旧格式：ingredients 是数组
        elif isinstance(ingredients, list):
            for item in ingredients:
                # 类型检查：确保 item 是字典
                if not isinstance(item, dict):
                    continue
                
                # 如果已经有比值，跳过
                existing_ratio = item.get('molar_ratio')
                if existing_ratio is not None and str(existing_ratio).strip() not in ['-', 'null', 'None', '']:
                    continue
                
                compound = item.get('compound', '')
                mass_str = item.get('mass_g', '')
                
                if not compound or str(compound) in ['-', 'null', 'None', '']:
                    continue
                
                if not mass_str or str(mass_str) in ['-', 'null', 'None', '']:
                    continue
                
                mass_val, is_mmol = _parse_mass(str(mass_str))
                
                if is_mmol:
                    # 如果已经是毫摩尔数，直接使用
                    moles = mass_val
                else:
                    # 否则通过分子量计算
                    mol_mass = get_molecular_weight(str(compound))
                    if mol_mass > 0 and mass_val > 0:
                        moles = mass_val / mol_mass
                    else:
                        continue
                
                if moles > 0:
                    valid.append({
                        'item': item,
                        'moles': moles,
                        'role': str(item.get('role', ''))
                    })
        
        if valid:
            # 1. 筛选出潜在的主原料（排除输运剂/助熔剂）
            main_candidates = [x for x in valid if 'Transport' not in str(x['role']) and 'Flux' not in str(x['role'])]
            
            # 如果没有明确的主原料，就用所有有效组分
            if not main_candidates:
                main_candidates = valid
            
            moles_values = [x['moles'] for x in main_candidates]
            
            # 2. 计算中位数（智能基准选择）
            if len(moles_values) > 1:
                median_moles = statistics.median(moles_values)
                # 3. 排除微量成分（小于中位数的 20%）作为基准的资格
                base_candidates = [m for m in moles_values if m >= 0.2 * median_moles]
            else:
                base_candidates = moles_values
            
            # 4. 确定基准值 (Base)
            if base_candidates:
                base = min(base_candidates)
            else:
                # 兜底：如果过滤后没有候选者，回退到使用绝对最小值
                base = min(moles_values) if moles_values else min([x['moles'] for x in valid])
            
            if base > 0:  # 确保基准值有效
                for v in valid:
                    ratio = v['moles'] / base
                    
                    # 5. 优化数值格式化
                    if ratio < 0.01:
                        # 极小值使用科学计数法或更多小数
                        ratio_str = f"{ratio:.4g}"
                    elif ratio < 1.0:
                        # 微量成分保留3位小数，去除末尾的0
                        ratio_str = f"{ratio:.3f}".rstrip('0').rstrip('.')
                    elif abs(ratio - round(ratio)) < 0.1:
                        # 接近整数，显示为整数
                        ratio_str = f"{int(round(ratio))}"
                    else:
                        # 普通小数，保留2位小数
                        ratio_str = f"{ratio:.2f}"
                    
                    # 根据格式设置比值
                    if isinstance(ingredients, dict):
                        # 关键修复：将计算出的摩尔比写回 item 字典，以便后续生成 Markdown 时调用
                        v['item']['molar_ratio'] = ratio_str
                        print(f"  [OK] 已计算摩尔比: {v['item'].get('name', '未知')} = {ratio_str}")
                    else:
                        # 旧格式：直接设置 molar_ratio
                        v['item']['molar_ratio'] = ratio_str
                        print(f"  [OK] 已计算摩尔比: {v['item'].get('compound', '未知')} = {ratio_str}")
    
    return data

def generate_markdown_with_llm(
    data: dict, 
    image_reference_path: str = "", 
    feedback: str = "",
    style_reference: str = ""
) -> str:
    """
    使用 LLM 生成 Markdown（风格迁移生成）- 增强版：使用预组装表格行强制修正摩尔比问题
    """
    llm = ChatOpenAI(
        model="qwen-plus",
        openai_api_key=API_KEY,
        openai_api_base=BASE_URL,
        temperature=0.3
    )
    
    # 构建提示词
    formatter_prompt = get_formatter_prompt(style_reference)
    
    # 构建反馈部分
    feedback_section = ""
    if feedback:
        feedback_section = f"**人工反馈**: {feedback}\n请根据反馈调整格式。\n\n"
    
    # 序列化 JSON
    try:
        json_data_str = json.dumps(data, ensure_ascii=False, indent=2)
    except (TypeError, ValueError) as json_err:
        print(f"  [WARN] JSON 序列化错误: {json_err}")
        raise
    
    # =================================================================
    # 🔥 核心修改：在 Python 中预组装配料表行 (Cheat Sheet)
    # =================================================================
    cheat_sheet_rows = []
    default_forms = {
        "MoO3": "粉末", "MoO2": "粉末", "S": "粉末", "Mo": "粉末", 
        "C6Br6": "液体", "C2Br6": "液体", "I2": "固体", "Si": "片状"
    }
    
    # 遍历实验数据，构建强制的 Markdown 行
    for exp in data.get("experiments", []):
        ingredients = exp.get("ingredients", {})
        
        # 统一获取 precursors 列表
        current_precursors = []
        if isinstance(ingredients, dict):
            current_precursors = ingredients.get("precursors", [])
        elif isinstance(ingredients, list):
            current_precursors = ingredients
            
        for p in current_precursors:
            if not isinstance(p, dict): continue
            
            # 提取各项数据
            name = p.get("name") or p.get("compound") or "-"
            if name in ['-', '']: continue
            
            mass = p.get("mass") or p.get("mass_g") or "-"
            
            # 获取 Python 端已计算好的摩尔比 (转为字符串)
            # 注意：这里直接取值，不依赖 LLM 计算
            # 修复：正确处理 None 值
            molar_ratio_raw = p.get("molar_ratio")
            if molar_ratio_raw is None or str(molar_ratio_raw).strip() in ['', 'null', 'None', '-']:
                ratio = "-"
            else:
                ratio = str(molar_ratio_raw).strip()
            
            # 调试输出：检查 Cheat Sheet 构建时的摩尔比值
            print(f"  [INFO] [Cheat Sheet] {name}: 原始值={repr(molar_ratio_raw)}, 处理后={ratio}")
            
            # 简单推断形态 (辅助 LLM)
            form = p.get("form")
            if not form or form in ['-', 'null', 'None', '']:
                form = default_forms.get(name, "-")
                if form == "-": 
                    # 尝试去下标匹配 (如 MoO3 -> MoO)
                    import re
                    norm_name = re.sub(r'[₀-₉0-9]', '', name)
                    form = default_forms.get(norm_name, "粉末")
            
            role = p.get("role", "-")
            
            # 🔨 强制组装 Markdown 行
            # 格式: | **Name** | Form | Mass | Ratio | Role |
            row_str = f"| **{name}** | {form} | {mass} | {ratio} | {role} |"
            cheat_sheet_rows.append(row_str)
            
    cheat_sheet_text = "\n".join(cheat_sheet_rows)
    
    # 调试输出：打印 Cheat Sheet 内容
    if cheat_sheet_rows:
        print(f"  📋 [Cheat Sheet] 已构建 {len(cheat_sheet_rows)} 行配料表数据:")
        for row in cheat_sheet_rows:
            print(f"    {row}")
    else:
        print(f"  [WARN] [Cheat Sheet] 警告：未找到任何配料数据！")
    # =================================================================

    # 构建 image_path_text
    image_path_text = image_reference_path if image_reference_path else "无"
    
    # 构建最终的 user_content
    user_content_parts = [
        "请将以下 JSON 数据转换为 Markdown 格式的实验报告。",
        "",
        "**图片引用路径**: " + image_path_text,
        "",
        "**JSON 数据**:",
        "```json",
        json_data_str,
        "```",
        "",
    ]
    
    # 🔥 在展示任何参考内容之前，先插入真实配料表数据
    if cheat_sheet_rows:
        user_content_parts.extend([
            "**【真实配料表数据（必须使用）】**",
            "[WARN] **最高优先级指令**：以下是预生成的、包含正确摩尔比的配料表数据。",
            "**你必须直接使用以下内容构建 Markdown 表格，严禁修改任何数值（特别是摩尔比列）**：",
            "```text",
            cheat_sheet_text,
            "```",
            "",
            "**[WARN] 重要提醒**：",
            "- 下方的'风格参考'中配料表可能包含占位符（如 '-'）或虚构数据，请**完全忽略**风格参考文件中的配料表数据！",
            "- 你必须使用上面这个【真实配料表数据】块中的内容来生成 Markdown 表格。",
            "- 不要自己重新计算或从 JSON 中提取，直接复制上面的表格行。",
            "",
        ])
    
    user_content_parts.extend([
        feedback_section,
        "**重要提示**：",
        "1. **输出格式**：请直接输出 Markdown 内容，不要输出 JSON 格式",
        "2. **不要添加代码块标记**：不要使用 ```markdown 或 ``` 包裹输出内容",
        "3. **配料表数据来源**：如果上方提供了【真实配料表数据】块，必须使用该块中的数据，完全忽略风格参考文件中的配料表数据。",
        "4. **输出示例**：你的输出应该以 `# [CHEM]` 开头。",
        "",
        "请现在开始输出 Markdown 内容："
    ])
    
    user_content = "\n".join(user_content_parts)
    
    try:
        from langchain_core.messages import HumanMessage, SystemMessage
        formatted_messages = [
            SystemMessage(content=formatter_prompt),
            HumanMessage(content=user_content)
        ]
        
        response = llm.invoke(formatted_messages)
        
        if not hasattr(response, 'content') or not response.content:
            raise ValueError("LLM 返回内容为空")
        
        markdown = response.content.strip()
        
        # 清理可能的代码块标记
        markdown = markdown.replace("```markdown", "").replace("```", "").strip()
        
        return markdown
    except Exception as e:
        print(f"  [WARN] LLM 调用失败: {e}")
        raise

def generate_markdown(data: dict, image_reference_path: str = "", feedback: str = "") -> str:
    """
    生成 Markdown 文档（传统方法，作为备用，支持新旧两种 Schema 格式）
    
    Args:
        data: 实验数据字典
        image_reference_path: 图片引用路径
        feedback: 人工反馈（用于调整格式）
    """
    experiments = data.get("experiments", [])
    md_output = []
    
    # 如果有反馈涉及格式问题，记录以便后续处理
    format_feedback = ""
    if feedback:
        # 检查反馈是否涉及格式问题
        format_keywords = ["格式", "markdown", "标题", "层级", "表格", "缺少", "添加", "删除"]
        if any(keyword in feedback.lower() for keyword in format_keywords):
            format_feedback = feedback
            print(f"📝 [格式化] 检测到格式相关反馈: {feedback[:50]}...")
    
    for idx, exp in enumerate(experiments):
        meta = exp.get("meta") or {}
        process = exp.get("process") or {}
        results = exp.get("results") or []
        
        method = meta.get('method', '-')
        is_cvt = "CVT" in method.upper()
        
        title = meta.get('title') or "实验记录"
        if title == "RT":
            title = "实验记录"
        
        furnace = meta.get('furnace', '-')
        if furnace and "PT" in furnace:
            furnace = furnace.replace("PT", "RT").replace("RT炉", "管式炉")
        
        md_output.append(f"# [CHEM] {title}")
        md_output.append(f"> **📅 日期**: {meta.get('date', '-')} | **🔥 设备**: {furnace} | **⚗️ 方法**: {method}")
        
        if results and len(results) > 0:
            md_output.append(f"\n![原始记录含表征]({image_reference_path})\n")
        md_output.append("\n---\n")
        
        # 注意：已删除材料化学式部分（根据用户要求）
        
        # 反应体系
        equation = exp.get("reaction_equation")
        if equation:
            md_output.append("## ⚗️ 反应体系")
            md_output.append("")
            eq = equation.replace("->", "\\rightarrow")
            md_output.append("**方程式**: ")
            md_output.append("")
            md_output.append(f"> ${eq}$")
            md_output.append("")
        
        # 配料表（强制使用表格格式）
        ingredients = exp.get("ingredients")
        md_output.append("## ⚖️ 配料表")
        md_output.append("")
        
        # 收集所有配料项
        all_ingredients = []
        
        # 默认形态映射（作为兜底，当 LLM 未补全时使用）
        default_forms = {
            "MoO3": "粉末", "MoO₂": "粉末", "MoO2": "粉末",
            "S": "粉末", "Se": "粉末", "Te": "粉末",
            "Mo": "粉末", "W": "粉末", "Nb": "粉末", "Ta": "粉末",
            "TeCl4": "粉末", "NH4Cl": "粉末",
            "C6Br6": "液体", "C₂Br₆": "液体", "C2Br6": "液体",
            "C2H5OH": "液体", "C₂H₅OH": "液体", "EtOH": "液体",
            "I2": "固体", "Br2": "液体", "Cl2": "气体",
            "Si": "片状", "SiO2": "衬底", "Si/SiO2": "衬底"
        }
        
        # 新格式：ingredients 是对象，包含 precursors
        if isinstance(ingredients, dict):
            precursors = ingredients.get("precursors", [])
            for p in precursors:
                if isinstance(p, dict):
                    compound = p.get("name", "-")
                    form = p.get("form", "")
                    # 如果 form 为空或 null，尝试从默认映射获取
                    if not form or form in ['-', 'null', 'None', '']:
                        # 尝试匹配化学式（支持带下标和不带下标）
                        form = default_forms.get(compound, "-")
                        # 如果直接匹配失败，尝试规范化匹配（移除下标）
                        if form == "-":
                            normalized = compound.replace("₂", "2").replace("₃", "3").replace("₄", "4").replace("₅", "5").replace("₆", "6")
                            form = default_forms.get(normalized, "-")
                    
                    # 读取摩尔比，确保正确显示计算出的值
                    molar_ratio = p.get("molar_ratio")
                    # 如果摩尔比为 None、空字符串或无效值，使用 "-"
                    if molar_ratio is None or str(molar_ratio).strip() in ['', 'null', 'None', '-']:
                        molar_ratio = "-"
                    else:
                        molar_ratio = str(molar_ratio).strip()
                    
                    all_ingredients.append({
                        "compound": compound,
                        "form": form,
                        "mass": p.get("mass", "-"),
                        "molar_ratio": molar_ratio,
                        "role": p.get("role", "-")
                    })
                    
                    # 调试输出
                    if molar_ratio != "-":
                        print(f"  📋 [Markdown生成] {compound}: 摩尔比 = {molar_ratio}")
        
        # 旧格式：ingredients 是数组
        elif isinstance(ingredients, list):
            for i in ingredients:
                if isinstance(i, dict):
                    compound = i.get("compound", "-")
                    form = i.get("form", "")
                    # 如果 form 为空或 null，尝试从默认映射获取
                    if not form or form in ['-', 'null', 'None', '']:
                        form = default_forms.get(compound, "-")
                        # 如果直接匹配失败，尝试规范化匹配
                        if form == "-":
                            normalized = compound.replace("₂", "2").replace("₃", "3").replace("₄", "4").replace("₅", "5").replace("₆", "6")
                            form = default_forms.get(normalized, "-")
                    
                    # 读取摩尔比，确保正确显示计算出的值
                    molar_ratio = i.get("molar_ratio")
                    # 如果摩尔比为 None、空字符串或无效值，使用 "-"
                    if molar_ratio is None or str(molar_ratio).strip() in ['', 'null', 'None', '-']:
                        molar_ratio = "-"
                    else:
                        molar_ratio = str(molar_ratio).strip()
                    
                    all_ingredients.append({
                        "compound": compound,
                        "form": form,
                        "mass": i.get("mass_g", i.get("mass", "-")),
                        "molar_ratio": molar_ratio,
                        "role": i.get("role", "-")
                    })
                    
                    # 调试输出
                    if molar_ratio != "-":
                        print(f"  📋 [Markdown生成] {compound}: 摩尔比 = {molar_ratio}")
        
        # 生成表格
        if all_ingredients:
            md_output.append("| 组分 | 形貌 | 质量 | 摩尔比 | 备注 |")
            md_output.append("| :-------- | ---- | :--- | :----- | :----- |")
            for ing in all_ingredients:
                compound = ing.get("compound", "-")
                form = ing.get("form", "-")
                mass = ing.get("mass", "-")
                molar_ratio = ing.get("molar_ratio", "-")
                role = ing.get("role", "-")
                md_output.append(f"| **{compound}** | {form} | {mass} | {molar_ratio} | {role} |")
        else:
            md_output.append("> *未识别到配料表*")
        
        # 添加材料性质部分（如果存在，来自外部文献 RAG）
        material_props = exp.get("material_properties")
        if material_props:
            md_output.append("\n## [LAB] 材料物理性质")
            md_output.append("> *以下信息来自外部文献知识库*")
            
            if material_props.get("melting_point"):
                md_output.append(f"- **熔点**: {material_props['melting_point']}")
            if material_props.get("space_group"):
                md_output.append(f"- **空间群**: {material_props['space_group']}")
            if material_props.get("lattice_parameter"):
                md_output.append(f"- **晶格参数**: {material_props['lattice_parameter']}")
            # 添加其他可能的性质
            for key, value in material_props.items():
                if key not in ["melting_point", "space_group", "lattice_parameter"]:
                    md_output.append(f"- **{key.replace('_', ' ').title()}**: {value}")
        
        md_output.append("## 🌡️ 实验方法及参数设置")
        
        # 实验方法
        md_output.append(f"* ⚗️ **实验方法**：{method}")
        
        # 新格式：heating_program（升温程序）- 智能自然语言格式化
        heating_program = process.get('heating_program', [])
        if heating_program and len(heating_program) > 0:
            md_output.append("* 🌡️ **反应温度与加热程序**：")
            
            for step in heating_program:
                if not isinstance(step, dict):
                    continue
                    
                step_name = str(step.get('step', '')).lower()
                temp = step.get('temp', '')
                target = step.get('target', '')
                rate = step.get('rate', '')
                duration = step.get('duration', '')
                note = step.get('note', '')
                
                # --- 智能格式化逻辑 ---
                line_content = ""
                
                # 1. 封管/预处理
                if any(k in step_name for k in ['purge', 'seal', '封管']):
                    line_content = "封管操作"
                    if note and '封管' not in note: 
                        line_content += f"（{note}）"
                
                # 2. 升温步骤 (Ramp)
                elif any(k in step_name for k in ['ramp', '升温']):
                    if duration and target:
                        line_content = f"{duration}升温至{target}"
                    elif rate and target:
                        line_content = f"以 {rate} 升温至 {target}"
                    elif target:
                        line_content = f"升温至 {target}"
                
                # 3. 生长/保温步骤 (Growth/Keep)
                elif any(k in step_name for k in ['growth', 'keep', 'dwell', '保温']):
                    display_temp = temp
                    if display_temp and duration:
                        line_content = f"在{display_temp}保持 {duration}"
                    elif display_temp:
                         line_content = f"在{display_temp}生长"
                
                # 4. 冷却 (Cooling)
                elif any(k in step_name for k in ['cool', '冷']):
                    if 'natural' in step_name or '自然' in step_name:
                        line_content = "自然冷却至室温"
                    elif target:
                        line_content = f"冷却至 {target}"
                    else:
                        line_content = "冷却过程"
                
                # 5. 其他情况 (Fallback)
                else:
                    parts = [p for p in [step.get('step'), temp, duration] if p]
                    line_content = " ".join(parts)

                # --- 最终组装 ---
                if line_content:
                    # 如果 note 包含重要信息（如双温区/低温区），追加到括号里
                    if note and note not in line_content:
                        line_content += f"（{note}）"
                    
                    md_output.append(f"  * {line_content}")
        
        # 新格式：method_specific（方法特定参数）
        method_specific = process.get('method_specific', {})
        if isinstance(method_specific, dict):
            gas_flow = method_specific.get('gas_flow')
            pressure = method_specific.get('pressure')
            geometry = method_specific.get('geometry')
            
            if gas_flow or pressure:
                md_output.append("* [CHEM] **气体的类型及流量**：")
                if gas_flow:
                    md_output.append(f"  * 使用 {gas_flow}。")
                if pressure:
                    md_output.append(f"  * {pressure}下生长。")
            
            if geometry:
                md_output.append(f"* [LAB] **空间放置**：{geometry}")
        
        # 完整流程描述（如果没有 heating_program，则显示 description）
        if not heating_program:
            desc = process.get('description', '-')
            desc = desc.replace("PT", "RT") if desc else '-'
            if desc and desc != '-':
                md_output.append(f"- **完整流程**: \n    > {desc}")
        
        if results:
            md_output.append("## [LAB] 实验结果与表征")
            # 优先使用列表格式（更易读）
            for r in results:
                if not isinstance(r, dict):
                    continue
                result_type = r.get('type', '-')
                label = r.get('label', '-')
                description = r.get('description', '-')
                md_output.append(f"* **[{result_type}] {label}**: {description}")
        
        notes = exp.get("notes")
        if notes:
            md_output.append(f"\n## 📌 备注\n{notes}")
        
        if idx < len(experiments) - 1:
            md_output.append("\n\n---\n\n")
    
    return "\n".join(md_output)

# ================= 路由函数 =================

def should_correct(state: AgentState) -> Literal["correct", "format"]:
    """判断是否需要重新提取"""
    if state.get("needs_correction", False):
        return "correct"
    return "format"

def should_ask_human(state: AgentState) -> Literal["human_review", "end"]:
    """判断是否需要人工审核"""
    # 修改逻辑：无论审核是否通过，自修正循环结束后都应该交由人工审核
    # 只有在人工已经提供反馈且明确通过的情况下，才直接结束
    human_feedback = state.get("human_feedback", "")
    review_passed_override = state.get("review_passed_override", None)
    
    # 如果人工已经明确通过审核，直接结束
    if human_feedback and review_passed_override is True:
        return "end"
    
    # 其他情况都进入人工审核
    return "human_review"

# ================= Human-in-the-loop 节点 =================

def human_review_node(state: AgentState) -> AgentState:
    """
    人工审核节点
    在实际应用中，这里可以集成 Streamlit、Gradio 等界面
    如果 human_feedback 已存在，说明用户已提供反馈，继续流程
    否则，标记需要人工审核，等待外部界面获取反馈
    """
    print("\n👤 [人工审核] 需要人工介入")
    print("=" * 60)
    iteration_count = state.get("iteration_count", 0)
    review_passed = state.get("review_passed", False)
    review_issues = state.get("review_issues", [])
    
    if review_issues:
        print(f"自修正循环已完成（迭代 {iteration_count} 次），发现以下问题：")
        print("\n发现的问题：")
        for issue in review_issues[:5]:
            print(f"  [{issue.get('severity', 'info')}] {issue.get('description', '')}")
    else:
        print(f"自修正循环已完成（迭代 {iteration_count} 次），审核状态：{'通过' if review_passed else '未通过'}")
        print("等待人工最终审核确认。")
    print("\n" + "=" * 60)
    
    # 检查是否已有用户反馈
    human_feedback = state.get("human_feedback", "")
    review_passed_override = state.get("review_passed_override", None)
    
    if human_feedback:
        # 用户已提供反馈，根据反馈决定是否通过
        print(f"[OK] 收到人工反馈: {human_feedback}")
        if review_passed_override is not None:
            print(f"[STATS] 审核结果: {'通过' if review_passed_override else '未通过'}")
            return {
                **state,
                "needs_human_review": False,
                "review_passed": review_passed_override
            }
        else:
            # 如果没有明确指定，默认通过
            print("[STATS] 审核结果: 通过（默认）")
            return {
                **state,
                "needs_human_review": False,
                "review_passed": True
            }
    else:
        # 等待人工反馈
        print("⏳ 等待人工审核反馈...")
        return {
            **state,
            "needs_human_review": True
        }

# ================= 构建 LangGraph 工作流 =================

def create_lab_agent_graph():
    """创建 LangGraph 状态图"""
    
    # 创建状态图
    workflow = StateGraph(AgentState)
    
    # 添加节点
    workflow.add_node("perceiver", perceiver_node)  # Role A
    workflow.add_node("reviewer", reviewer_node)    # Role B
    workflow.add_node("formatter", formatter_node) # Role C
    workflow.add_node("human_review", human_review_node)  # 人工审核
    
    # 设置入口
    workflow.set_entry_point("perceiver")
    
    # 添加边
    workflow.add_edge("perceiver", "reviewer")
    
    # 条件边：审核后判断是否需要修正
    workflow.add_conditional_edges(
        "reviewer",
        should_correct,
        {
            "correct": "perceiver",  # 需要修正，回到感知者
            "format": "formatter"    # 不需要修正，进入格式化
        }
    )
    
    # 条件边：格式化后判断是否需要人工审核
    workflow.add_conditional_edges(
        "formatter",
        should_ask_human,
        {
            "human_review": "human_review",
            "end": END
        }
    )
    
    # 人工审核后结束
    workflow.add_edge("human_review", END)
    
    # 编译图
    memory = MemorySaver()
    app = workflow.compile(checkpointer=memory)
    
    return app

# ================= 主程序 =================

if __name__ == "__main__":
    # 创建 Agent
    agent = create_lab_agent_graph()
    
    # 测试用例
    image_file = "img_test/CsCr6Sb6.png"
    
    if os.path.exists(image_file):
        print(f"\n🚀 开始处理图片: {image_file}\n")
        
        # 构建初始状态
        image_rel_path = f"../img_test/{os.path.basename(image_file)}"
        output_md_path = f"md_test/{os.path.splitext(os.path.basename(image_file))[0]}.md"
        
        initial_state = {
            "image_path": image_file,
            "image_reference_path": image_rel_path,
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
            "needs_human_review": False,
            "messages": []
        }
        
        # 运行工作流
        config = {"configurable": {"thread_id": "test-1"}}
        final_state = agent.invoke(initial_state, config)
        
        print("\n" + "=" * 60)
        print("[OK] 处理完成！")
        print("=" * 60)
        print(f"\n📄 Markdown 文件: {output_md_path}")
        
        # 显示审核问题详情（完整列表）
        review_issues = final_state.get("review_issues", [])
        if review_issues:
            print(f"\n{'='*70}")
            print(f"[WARN]  审核问题汇总 (共 {len(review_issues)} 个)")
            print(f"{'='*70}")
            
            # 按严重程度分组
            errors = [i for i in review_issues if i.get("severity") == "error"]
            warnings = [i for i in review_issues if i.get("severity") == "warning"]
            infos = [i for i in review_issues if i.get("severity") == "info"]
            
            if errors:
                print(f"\n[ERROR] 严重错误 ({len(errors)} 个):")
                print("-" * 70)
                for idx, issue in enumerate(errors, 1):
                    field = issue.get("field", "-")
                    desc = issue.get("description", "-")
                    suggestion = issue.get("suggestion", "")
                    print(f"  {idx}. {desc}")
                    if field != "-":
                        print(f"     字段: {field}")
                    if suggestion:
                        print(f"     建议: {suggestion}")
            
            if warnings:
                print(f"\n[WARN]  警告 ({len(warnings)} 个):")
                print("-" * 70)
                for idx, issue in enumerate(warnings, 1):
                    field = issue.get("field", "-")
                    desc = issue.get("description", "-")
                    suggestion = issue.get("suggestion", "")
                    print(f"  {idx}. {desc}")
                    if field != "-":
                        print(f"     字段: {field}")
                    if suggestion:
                        print(f"     建议: {suggestion}")
            
            if infos:
                print(f"\nℹ️  信息提示 ({len(infos)} 个):")
                print("-" * 70)
                for idx, issue in enumerate(infos, 1):
                    field = issue.get("field", "-")
                    desc = issue.get("description", "-")
                    print(f"  {idx}. {desc}")
                    if field != "-":
                        print(f"     字段: {field}")
            
            print(f"\n{'='*70}")
            print(f"💡 提示: 详细问题已保存到 JSON 文件: {output_md_path.replace('.md', '_issues.json')}")
        else:
            print("\n[OK] 未发现审核问题")
        
        # 显示迭代次数
        iteration_count = final_state.get("iteration_count", 0)
        if iteration_count > 1:
            print(f"\n🔄 自修正迭代次数: {iteration_count}")
    else:
        print(f"[ERROR] 未找到测试图片: {image_file}")
