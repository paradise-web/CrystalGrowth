# Multi-Agent 工作逻辑总结

## 🏗️ 系统架构

本系统采用 **LangGraph** 构建的多智能体工作流，包含 4 个核心节点：

1. **Perceiver Node (Role A: 视觉感知者)** - 数据提取
2. **Reviewer Node (Role B: 领域审核员)** - 数据审核
3. **Formatter Node (Role C: 数据工程师)** - 格式化输出
4. **Human Review Node (人工审核)** - 人机交互

---

## 📊 工作流程图

```
┌─────────────────────────────────────────────────────────────┐
│                    开始处理                                  │
└─────────────────────────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────────────┐
│  🔍 Perceiver Node (Role A: 视觉感知者)                    │
│  - 使用 Qwen-VL-Max 分析图片                                │
│  - 提取实验数据（JSON 格式）                                 │
│  - 支持 correction_hints（修正提示）                        │
└─────────────────────────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────────────┐
│  🔬 Reviewer Node (Role B: 领域审核员)                      │
│  - 使用 Qwen-Plus 审核数据合理性                            │
│  - 程序化检查（化学式平衡、单位等）                          │
│  - 支持人工反馈调整审核标准                                 │
│  - 生成 review_issues（问题列表）                           │
└─────────────────────────────────────────────────────────────┘
                        ↓
            ┌───────────┴───────────┐
            │                       │
    needs_correction?         不需要修正
            │                       │
           是                       ↓
            │           ┌───────────────────────────┐
            │           │  📝 Formatter Node        │
            │           │  (Role C: 数据工程师)     │
            │           │  - 计算摩尔比             │
            │           │  - 生成 Markdown          │
            │           │  - 支持人工反馈调整格式   │
            │           └───────────────────────────┘
            │                       ↓
            │           ┌───────────────────────────┐
            │           │  should_ask_human?        │
            │           └───────────────────────────┘
            │                   │           │
            │           需要人工审核    不需要
            │                   │           │
            │                   ↓           ↓
            │           ┌──────────────┐   END
            │           │ 👤 Human     │
            │           │ Review Node  │
            │           └──────────────┘
            │                   │
            │           用户反馈
            │           ├─ 通过 → END
            │           └─ 不通过 → 重新处理
            │                       │
            └───────────────────────┘
                    (循环直到通过)
```

---

## 🔄 详细工作流程

### 阶段 1: 数据提取 (Perceiver Node)

**功能**：
- 使用 **Qwen-VL-Max** 视觉语言模型分析实验记录图片
- 提取结构化数据（JSON 格式）
- 包含：实验元数据、配料表、工艺流程、结果表征等

**输入**：
- `image_path`: 图片路径
- `correction_hints`: 修正提示（来自人工反馈或自动修正）

**处理**：
```python
1. 预处理图片（旋转、压缩、格式转换）
2. 构建提示词（包含 correction_hints）
3. 调用 Qwen-VL-Max API
4. 解析返回的 JSON 数据
```

**输出**：
- `raw_json`: 提取的原始 JSON 数据
- `iteration_count`: 迭代次数 +1
- `needs_correction`: 是否需要修正（如果提取失败）

**关键特性**：
- ✅ 支持多轮修正（通过 `correction_hints`）
- ✅ 自动处理图片格式问题
- ✅ 错误处理和重试机制

---

### 阶段 2: 数据审核 (Reviewer Node)

**功能**：
- 使用 **Qwen-Plus** 语言模型审核数据合理性
- 程序化检查（化学式平衡、单位转换等）
- 生成问题列表和建议

**输入**：
- `raw_json`: Perceiver 提取的原始数据
- `correction_hints`: 修正提示
- `human_feedback`: 人工反馈（用于调整审核标准）

**处理**：
```python
1. 解析 JSON 数据
2. 使用 LLM 进行智能审核（考虑人工反馈）
3. 程序化检查（补充 LLM 审核）
4. 合并问题列表
5. 判断是否需要修正
```

**输出**：
- `reviewed_json`: 审核后的 JSON 数据
- `review_passed`: 审核是否通过
- `review_issues`: 问题列表（error/warning/info）
- `needs_correction`: 是否需要重新提取
- `correction_hints`: 修正提示（用于下一轮提取）

**审核内容**：
- ✅ 化学式平衡性
- ✅ 单位合理性（质量、温度、时间）
- ✅ 数据完整性
- ✅ 逻辑一致性

**关键特性**：
- ✅ 支持人工反馈调整审核标准
- ✅ 多层级问题分类（error/warning/info）
- ✅ 自动生成修正建议

---

### 阶段 3: 路由决策 (should_correct)

**功能**：判断是否需要重新提取数据

**逻辑**：
```python
if needs_correction and iteration_count < max_iterations:
    return "correct"  # 回到 Perceiver，重新提取
else:
    return "format"   # 进入 Formatter，生成报告
```

**关键点**：
- 如果发现错误且未达到最大迭代次数 → 自动修正循环
- 如果达到最大迭代次数 → 进入格式化阶段

---

### 阶段 4: 格式化输出 (Formatter Node)

**功能**：
- 计算并补全缺失的摩尔比
- 生成 Markdown 格式的实验报告
- 保存文件

**输入**：
- `reviewed_json`: 审核后的 JSON 数据
- `image_reference_path`: 图片引用路径
- `correction_hints` / `human_feedback`: 反馈信息（用于调整格式）

**处理**：
```python
1. 解析 JSON 数据
2. 计算摩尔比（如果缺失）
3. 生成 Markdown（考虑反馈）
4. 保存文件
```

**输出**：
- `formatted_markdown`: 格式化的 Markdown 报告

**关键特性**：
- ✅ 自动计算摩尔比
- ✅ 支持 LaTeX 公式渲染
- ✅ 支持反馈调整格式

---

### 阶段 5: 人工审核判断 (should_ask_human)

**功能**：判断是否需要人工审核

**逻辑**：
```python
if not review_passed and iteration_count >= max_iterations:
    return "human_review"  # 需要人工审核
else:
    return "end"          # 直接结束
```

**关键点**：
- 如果审核未通过且达到最大迭代次数 → 触发人工审核
- 否则 → 直接结束流程

---

### 阶段 6: 人工审核 (Human Review Node)

**功能**：
- 等待用户提供反馈
- 根据反馈决定是否通过
- 支持循环审核

**输入**：
- `human_feedback`: 用户反馈（如果有）
- `review_passed_override`: 用户明确的通过/不通过决定
- `review_issues`: 审核问题列表

**处理**：
```python
if human_feedback:
    # 用户已提供反馈
    if review_passed_override is not None:
        # 有明确的通过/不通过决定
        return {
            "needs_human_review": False,
            "review_passed": review_passed_override
        }
    else:
        # 默认通过
        return {
            "needs_human_review": False,
            "review_passed": True
        }
else:
    # 等待人工反馈
    return {
        "needs_human_review": True
    }
```

**输出**：
- `needs_human_review`: 是否需要人工审核
- `review_passed`: 审核是否通过

---

## 🔁 循环审核机制

### 自动修正循环

```
Perceiver → Reviewer → (发现错误) → Perceiver → Reviewer → ...
         ↑                                    ↓
         └────────── (达到最大迭代次数) ──────┘
```

**触发条件**：
- `needs_correction = True`
- `iteration_count < max_iterations`

**特点**：
- 自动进行，无需人工干预
- 最多执行 `max_iterations` 次（默认 3 次）

---

### 人工审核循环

```
人工审核 → 不通过 → 重新处理 → 人工审核 → 不通过 → 重新处理 → ...
         ↑                                                      ↓
         └────────────── (用户选择通过) ───────────────────────┘
```

**触发条件**：
- 达到最大迭代次数后仍有问题
- 用户选择"不通过，需要重新处理"

**特点**：
- 需要人工干预
- 可以无限循环（直到用户选择通过）
- 每次重新处理都会使用用户的反馈作为修正提示

---

## 📋 状态管理

### AgentState 关键字段

```python
{
    # 输入
    "image_path": str,              # 图片路径
    "image_reference_path": str,     # 图片引用路径（用于 Markdown）
    "output_path": str,              # 输出文件路径
    
    # 处理结果
    "raw_json": str,                 # 原始提取的 JSON
    "reviewed_json": str,            # 审核后的 JSON
    "formatted_markdown": str,       # 格式化的 Markdown
    
    # 修正机制
    "correction_hints": str,         # 修正提示
    "needs_correction": bool,        # 是否需要修正
    "iteration_count": int,          # 迭代次数
    "max_iterations": int,           # 最大迭代次数
    
    # 审核结果
    "review_issues": list,          # 问题列表
    "review_passed": bool,           # 审核是否通过
    
    # 人工审核
    "human_feedback": str,           # 人工反馈
    "review_passed_override": bool,  # 用户明确的通过/不通过决定
    "needs_human_review": bool,      # 是否需要人工审核
    
    # 消息历史
    "messages": list                 # 对话历史
}
```

---

## 🎯 反馈机制

### 反馈传递路径

```
用户反馈
    ↓
correction_hints / human_feedback
    ↓
┌─────────────────────────────────────┐
│  1. Perceiver Node                  │
│     └─> 用于重新提取数据            │
│                                      │
│  2. Reviewer Node                   │
│     └─> 用于调整审核标准            │
│                                      │
│  3. Formatter Node                  │
│     └─> 用于调整输出格式            │
└─────────────────────────────────────┘
```

### 反馈类型

1. **数据提取问题** → 传递给 `Perceiver Node`
   - 例如："化学式不平衡"、"温度单位错误"

2. **审核逻辑问题** → 传递给 `Reviewer Node`
   - 例如："温度审核太严格"、"审核标准需要调整"

3. **输出格式问题** → 传递给 `Formatter Node`
   - 例如："Markdown 格式不对"、"缺少某个部分"

---

## 🔧 关键设计点

### 1. 迭代次数控制

- **自动修正循环**：`iteration_count < max_iterations` 时触发
- **人工审核触发**：`iteration_count >= max_iterations` 时触发
- **重新处理时**：`iteration_count = max_iterations`，防止自动修正循环

### 2. 状态清理

- 重新处理时清除之前的反馈和结果
- 强制重新提取，而不是基于旧结果修正
- 确保每轮处理都是独立的

### 3. 反馈累积

- 多轮反馈可以累积
- 每轮反馈都会传递给相应的节点
- 反馈历史保存在状态中

### 4. 循环终止条件

- **自动修正循环**：达到最大迭代次数或审核通过
- **人工审核循环**：用户选择通过或强制通过

---

## 📊 完整流程示例

### 场景：处理一张实验记录图片

```
1. 用户上传图片
   ↓
2. Perceiver Node
   - 提取数据：{"meta": {...}, "ingredients": [...], ...}
   ↓
3. Reviewer Node
   - 审核数据：发现 2 个错误
   - needs_correction = True
   - iteration_count = 1
   ↓
4. should_correct → "correct"
   ↓
5. Perceiver Node (第 2 次)
   - 使用 correction_hints 重新提取
   - iteration_count = 2
   ↓
6. Reviewer Node (第 2 次)
   - 审核数据：发现 1 个错误
   - needs_correction = True
   - iteration_count = 2
   ↓
7. should_correct → "correct"
   ↓
8. Perceiver Node (第 3 次)
   - 使用 correction_hints 重新提取
   - iteration_count = 3
   ↓
9. Reviewer Node (第 3 次)
   - 审核数据：仍有 1 个警告
   - needs_correction = False (iteration_count >= max_iterations)
   - iteration_count = 3
   ↓
10. should_correct → "format"
    ↓
11. Formatter Node
    - 生成 Markdown 报告
    ↓
12. should_ask_human
    - review_passed = False
    - iteration_count = 3 >= max_iterations
    - return "human_review"
    ↓
13. Human Review Node
    - needs_human_review = True
    - 等待用户反馈
    ↓
14. 用户提供反馈："温度单位错误，应该是摄氏度"
    ↓
15. 用户选择"不通过，需要重新处理"
    ↓
16. 重新处理（第 1 轮人工反馈）
    - correction_hints = "温度单位错误，应该是摄氏度"
    - human_feedback = ""
    - iteration_count = max_iterations
    ↓
17. Perceiver Node
    - 使用 feedback 重新提取
    ↓
18. Reviewer Node
    - 使用 feedback 调整审核标准
    ↓
19. Formatter Node
    - 生成报告
    ↓
20. should_ask_human
    - 如果仍有问题 → 再次触发人工审核
    - 如果审核通过 → 结束
    ↓
21. 用户再次审核
    - 如果通过 → 显示最终结果 ✅
    - 如果不通过 → 继续循环...
```

---

## 🎨 技术特点

### 1. 多模型协作

- **Qwen-VL-Max**: 视觉理解，数据提取
- **Qwen-Plus**: 领域知识，数据审核
- **Pymatgen**: 化学计算，摩尔比计算

### 2. 状态管理

- 使用 LangGraph 的状态图管理
- 状态持久化（MemorySaver）
- 支持流式处理（stream API）

### 3. 人机交互

- Streamlit 界面集成
- 实时进度显示
- 循环审核支持

### 4. 错误处理

- 多层级错误处理
- 自动重试机制
- 人工介入机制

---

## 📝 总结

这是一个**多智能体协作系统**，通过以下机制确保输出质量：

1. **自动修正循环**：在达到最大迭代次数前，自动修正错误
2. **人工审核循环**：达到最大迭代次数后，通过人工反馈持续改进
3. **反馈机制**：所有节点都能接收和使用反馈，实现精准修正
4. **状态管理**：完善的状态管理确保流程可控

整个系统设计遵循"**自动化优先，人工兜底**"的原则，在保证效率的同时确保质量。

