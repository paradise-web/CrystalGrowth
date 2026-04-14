"""
外部文献 RAG 模块
用于检索晶体生长手册、论文等外部知识库，增强系统专业性
"""

import os
import json
import re
from typing import List, Dict, Optional, Any
from pathlib import Path

# 向量库（使用 Chroma，轻量级）
try:
    import chromadb
    from chromadb.config import Settings
    CHROMA_AVAILABLE = True
except ImportError:
    CHROMA_AVAILABLE = False
    print("⚠️ 警告: chromadb 未安装，外部文献 RAG 功能将不可用。安装: pip install chromadb")

# PDF 解析
try:
    import pdfplumber
    PDF_AVAILABLE = True
except ImportError:
    PDF_AVAILABLE = False
    print("⚠️ 警告: pdfplumber 未安装，PDF 解析功能将不可用。安装: pip install pdfplumber")

# Embedding API
from openai import OpenAI

# ================= 配置 =================

API_KEY = os.getenv("DASHSCOPE_API_KEY", "sk-eec9cb28d6804d18aaddcdb4bdd9a1b9")
BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"

# 向量库路径
VECTOR_DB_PATH = Path("./vector_db")
KNOWLEDGE_BASE_PATH = Path("./knowledge_base")

# ================= PDF 处理 =================

def parse_pdf(pdf_path: str, max_chunk_size: int = 900) -> List[str]:
    """
    解析 PDF 文件，返回文本块列表
    
    Args:
        pdf_path: PDF 文件路径
        max_chunk_size: 最大块大小（字符数），超过此大小的块会被进一步分割（默认900，适合embedding模型）
        
    Returns:
        文本块列表（按段落分割，长段落会进一步分割）
    """
    if not PDF_AVAILABLE:
        raise ImportError("pdfplumber 未安装，无法解析 PDF")
    
    chunks = []
    try:
        with pdfplumber.open(pdf_path) as pdf:
            for page_num, page in enumerate(pdf.pages):
                text = page.extract_text()
                if text:
                    # 按段落分割（双换行符）
                    paragraphs = [p.strip() for p in text.split('\n\n') if p.strip()]
                    
                    # 对每个段落检查长度，如果太长则进一步分割
                    for para in paragraphs:
                        if len(para) > max_chunk_size:
                            # 如果段落太长，使用 chunk_text 进一步分割
                            sub_chunks = chunk_text(para, chunk_size=max_chunk_size, overlap=200)
                            chunks.extend(sub_chunks)
                        else:
                            chunks.append(para)
    except Exception as e:
        print(f"⚠️ PDF 解析失败 ({pdf_path}): {e}")
    
    return chunks

def chunk_text(text: str, chunk_size: int = 500, overlap: int = 50) -> List[str]:
    """
    将长文本分割成固定大小的块（用于向量化）
    
    Args:
        text: 原始文本
        chunk_size: 块大小（字符数）
        overlap: 重叠大小（字符数）
        
    Returns:
        文本块列表
    """
    if len(text) <= chunk_size:
        return [text]
    
    chunks = []
    words = text.split()
    word_count = len(words)
    
    for i in range(0, word_count, chunk_size - overlap):
        chunk = ' '.join(words[i:i + chunk_size])
        chunks.append(chunk)
    
    return chunks

# ================= 向量化 =================

def embed_text(text: str, model: str = "text-embedding-v2") -> List[float]:
    """
    使用 DashScope API 生成文本向量
    
    Args:
        text: 输入文本
        model: Embedding 模型名称
        
    Returns:
        向量列表
    """
    if not API_KEY:
        raise ValueError("DASHSCOPE_API_KEY 未设置")
    
    # 检查并处理过长的文本
    estimated_tokens = _estimate_token_count(text)
    if estimated_tokens > 2000:
        text = _truncate_text_for_embedding(text, max_tokens=2000)
    
    client = OpenAI(api_key=API_KEY, base_url=BASE_URL)
    
    try:
        response = client.embeddings.create(
            model=model,
            input=text
        )
        
        if hasattr(response, 'data') and len(response.data) > 0:
            return response.data[0].embedding
        else:
            print(f"⚠️ Embedding 响应格式异常: 无数据")
            return None
            
    except Exception as e:
        error_msg = str(e)
        print(f"⚠️ Embedding 生成失败: {error_msg}")
        
        # 检查是否是模型名称错误
        if "model" in error_msg.lower() or "not found" in error_msg.lower():
            print(f"💡 提示: 模型名称可能不正确，当前使用: {model}")
            print(f"   请检查 DashScope 文档确认正确的模型名称")
            print(f"   常见模型名称: 'text-embedding-v1', 'text-embedding-v2'")
        
        # 检查是否是文本长度错误
        if "length" in error_msg.lower() or "range" in error_msg.lower() or "2048" in error_msg:
            print(f"💡 提示: 文本可能过长，请尝试使用 chunk_text 函数分割文本")
        
        return None

def _estimate_token_count(text: str) -> int:
    """
    估算文本的 token 数量
    对于中英文混合文本，采用保守估算：1 token ≈ 1.5 字符
    这确保了在限制范围内，因为实际 token 数可能更少
    
    Args:
        text: 输入文本
        
    Returns:
        估算的 token 数量
    """
    # 保守估算：对于中文，1 token ≈ 1-1.5 字符；对于英文，1 token ≈ 4 字符
    # 使用 1.5 作为平均估算值，确保不会超过限制
    return int(len(text) / 1.5)

def _smart_chunk_text(text: str, max_tokens: int = 1000, overlap: int = 100) -> List[str]:
    """
    智能切分文本，基于token数进行切分，确保所有子块都安全
    
    Args:
        text: 原始文本
        max_tokens: 最大token数（默认1000，留出安全余量）
        overlap: 重叠大小（字符数，用于保持上下文连续性）
        
    Returns:
        文本块列表（所有子块都确保不超过token限制）
    """
    if not text:
        return []
    
    estimated_tokens = _estimate_token_count(text)
    
    # 如果已经足够小，直接返回
    if estimated_tokens <= max_tokens:
        return [text]
    
    chunks = []
    
    # 首先尝试按句子分割（更自然）
    sentence_endings = ['。', '.', '！', '!', '？', '?', '\n\n']
    
    # 按句子分割
    sentences = []
    current_sentence = ""
    
    for char in text:
        current_sentence += char
        if char in sentence_endings:
            if current_sentence.strip():
                sentences.append(current_sentence.strip())
            current_sentence = ""
    
    # 添加最后一句（如果没有结束符）
    if current_sentence.strip():
        sentences.append(current_sentence.strip())
    
    # 如果按句子分割失败，回退到按换行分割
    if not sentences:
        sentences = [s.strip() for s in text.split('\n') if s.strip()]
    
    # 如果还是失败，回退到按段落分割
    if not sentences:
        sentences = [p.strip() for p in text.split('\n\n') if p.strip()]
    
    # 如果仍然失败，使用字符级分割
    if not sentences:
        return _char_level_chunk(text, max_tokens, overlap)
    
    # 将句子组合成chunks
    current_chunk = ""
    current_tokens = 0
    
    for sentence in sentences:
        sentence_tokens = _estimate_token_count(sentence)
        
        # 如果单个句子就超过限制，需要进一步分割
        if sentence_tokens > max_tokens:
            # 先保存当前chunk
            if current_chunk:
                chunks.append(current_chunk)
                current_chunk = ""
                current_tokens = 0
            
            # 对超长句子进行字符级分割
            sub_chunks = _char_level_chunk(sentence, max_tokens, overlap)
            chunks.extend(sub_chunks)
            continue
        
        # 检查添加这个句子后是否超过限制
        if current_tokens + sentence_tokens > max_tokens:
            # 保存当前chunk
            if current_chunk:
                chunks.append(current_chunk)
            # 开始新chunk（带重叠）
            if overlap > 0 and current_chunk:
                # 从当前chunk末尾取overlap长度的文本作为新chunk的开头
                overlap_text = current_chunk[-overlap:] if len(current_chunk) > overlap else current_chunk
                current_chunk = overlap_text + " " + sentence
            else:
                current_chunk = sentence
            current_tokens = _estimate_token_count(current_chunk)
        else:
            # 添加到当前chunk
            if current_chunk:
                current_chunk += " " + sentence
            else:
                current_chunk = sentence
            current_tokens = _estimate_token_count(current_chunk)
    
    # 添加最后一个chunk
    if current_chunk:
        chunks.append(current_chunk)
    
    return chunks if chunks else [text]

def _char_level_chunk(text: str, max_tokens: int, overlap: int) -> List[str]:
    """
    字符级分割（当句子级分割失败时使用）
    """
    chunks = []
    # 估算最大字符数：max_tokens * 1.5（保守估算）
    max_chars = int(max_tokens * 1.5)
    start = 0
    
    while start < len(text):
        # 计算当前chunk的结束位置
        end = min(start + max_chars, len(text))
        
        if end >= len(text):
            # 最后一块
            chunks.append(text[start:])
            break
        
        # 尝试在句子边界截断
        chunk_text = text[start:end]
        for punct in ['。', '.', '！', '!', '？', '?', '\n']:
            last_punct = chunk_text.rfind(punct)
            if last_punct > len(chunk_text) * 0.7:  # 如果找到合适的截断点
                end = start + last_punct + 1
                break
        
        chunks.append(text[start:end])
        start = max(end - overlap, start + 1)  # 重叠，但确保前进
    
    return chunks

def _truncate_text_for_embedding(text: str, max_tokens: int = 2000) -> str:
    """
    截断文本以适应 embedding 模型的 token 限制（最后手段，应尽量避免使用）
    
    Args:
        text: 输入文本
        max_tokens: 最大 token 数（默认 2000，为 2048 限制留出安全边界）
        
    Returns:
        截断后的文本
    """
    estimated_tokens = _estimate_token_count(text)
    
    if estimated_tokens <= max_tokens:
        return text
    
    # 如果文本太长，需要截断
    # 估算最大字符数：max_tokens * 1.5
    max_chars = int(max_tokens * 1.5)
    
    # 尝试在句子边界截断（更自然）
    if len(text) > max_chars:
        truncated = text[:max_chars]
        # 尝试找到最后一个句号、问号或感叹号
        for punct in ['。', '.', '！', '!', '？', '?', '\n']:
            last_punct = truncated.rfind(punct)
            if last_punct > max_chars * 0.8:  # 如果句号位置不太靠前
                return truncated[:last_punct + 1]
        # 如果找不到合适的截断点，直接截断
        return truncated
    
    return text

def embed_chunks_batch(chunks: List[str], batch_size: int = 10, model: str = "text-embedding-v2") -> List[List[float]]:
    """
    批量生成向量（逐个调用，提高可靠性）
    
    Args:
        chunks: 文本块列表
        batch_size: 批处理大小（用于进度显示，实际逐个调用以提高可靠性）
        model: Embedding 模型名称
        
    Returns:
        向量列表
    """
    if not API_KEY:
        raise ValueError("DASHSCOPE_API_KEY 未设置")
    
    client = OpenAI(api_key=API_KEY, base_url=BASE_URL)
    embeddings = []
    
    # DashScope Embedding API 可能不支持批量输入，改为逐个调用以提高可靠性
    total = len(chunks)
    success_count = 0
    fail_count = 0
    truncated_count = 0
    
    print(f"  📊 开始生成 {total} 个文本块的向量...")
    
    for i, chunk in enumerate(chunks):
        try:
            # 检查文本长度（应该在调用前已经处理过，这里只是最后的安全检查）
            estimated_tokens = _estimate_token_count(chunk)
            
            if estimated_tokens > 2000:  # 2000 tokens 作为安全边界
                truncated_count += 1
                # 如果仍然过长，进行硬截断（这种情况不应该发生，因为应该在调用前处理）
                chunk = _truncate_text_for_embedding(chunk, max_tokens=2000)
                if truncated_count <= 3:  # 只在前3次警告
                    print(f"  ⚠️ 警告: 文本块过长 (第 {i+1}/{total} 个): 估算 {estimated_tokens} tokens，已截断至约 2000 tokens")
                    print(f"     建议: 在调用 embed_chunks_batch 前使用 _smart_chunk_text 进行预处理")
            
            # 单个调用（更可靠）
            response = client.embeddings.create(
                model=model,
                input=chunk
            )
            
            if hasattr(response, 'data') and len(response.data) > 0:
                embedding = response.data[0].embedding
                embeddings.append(embedding)
                success_count += 1
            else:
                print(f"  ⚠️ 响应格式异常 (第 {i+1}/{total} 个): 无数据")
                embeddings.append(None)
                fail_count += 1
                
        except Exception as e:
            error_msg = str(e)
            
            # 检查是否是文本长度错误
            if "length" in error_msg.lower() or "range" in error_msg.lower() or "2048" in error_msg:
                print(f"  ❌ Embedding 生成失败 (第 {i+1}/{total} 个): 文本过长")
                print(f"     文本长度: {len(chunk)} 字符，估算 tokens: {estimated_tokens}")
                print(f"     错误: 文本块在预处理阶段未正确处理，请检查预处理逻辑")
            
            # 检查是否是模型名称错误
            elif "model" in error_msg.lower() or "not found" in error_msg.lower() or "invalid" in error_msg.lower():
                print(f"  ⚠️ Embedding 生成失败 (第 {i+1}/{total} 个): 模型名称错误")
                print(f"  💡 提示: 模型名称可能不正确，当前使用: {model}")
                print(f"     请检查 DashScope 文档确认正确的模型名称")
                print(f"     常见模型名称: 'text-embedding-v1', 'text-embedding-v2'")
            
            # 检查是否是 API Key 错误
            elif "api" in error_msg.lower() and ("key" in error_msg.lower() or "auth" in error_msg.lower()):
                print(f"  ⚠️ Embedding 生成失败 (第 {i+1}/{total} 个): API Key 错误")
                print(f"  💡 提示: API Key 可能无效或未设置")
            
            else:
                print(f"  ⚠️ Embedding 生成失败 (第 {i+1}/{total} 个): {error_msg[:150]}")
            
            embeddings.append(None)
            fail_count += 1
        
        # 进度显示（每 10 个显示一次）
        if (i + 1) % 10 == 0 or (i + 1) == total:
            print(f"  进度: {i+1}/{total} (成功: {success_count}, 失败: {fail_count}, 截断: {truncated_count})")
    
    print(f"  ✅ 完成: 成功 {success_count}/{total}, 失败 {fail_count}/{total}, 截断 {truncated_count}/{total}")
    
    if fail_count > 0:
        print(f"  ⚠️ 警告: {fail_count} 个文本块向量生成失败，这些块将被跳过")
    
    return embeddings

# ================= 向量库管理 =================

class ExternalKnowledgeBase:
    """外部知识库管理类"""
    
    def __init__(self, db_path: str = None, model: str = "text-embedding-v2", force_recreate: bool = False):
        """
        初始化知识库
        
        Args:
            db_path: 向量数据库路径（默认: ./vector_db）
            model: Embedding 模型名称（用于检查维度一致性）
            force_recreate: 是否强制重建集合（如果维度不匹配，会自动重建）
        """
        if not CHROMA_AVAILABLE:
            raise ImportError("chromadb 未安装，无法使用外部知识库")
        
        self.db_path = Path(db_path) if db_path else VECTOR_DB_PATH
        self.db_path.mkdir(parents=True, exist_ok=True)
        self.model = model
        
        # 初始化 Chroma 客户端
        self.client = chromadb.PersistentClient(
            path=str(self.db_path),
            settings=Settings(anonymized_telemetry=False)
        )
        
        # 检查集合是否存在
        collection_name = "crystal_growth_kb"
        try:
            existing_collection = self.client.get_collection(name=collection_name)
            
            # 如果集合已存在，检查维度是否匹配
            if not force_recreate:
                # 尝试获取集合的维度（通过检查现有数据或测试添加）
                try:
                    # 创建一个测试向量来检查维度
                    test_embedding = embed_text("test", model=model)
                    if test_embedding:
                        expected_dim = len(test_embedding)
                        
                        # 检查集合中是否已有数据，如果有，检查第一个向量的维度
                        count = existing_collection.count()
                        if count > 0:
                            # 获取一个现有向量来检查维度
                            sample = existing_collection.get(limit=1)
                            if sample and sample.get('embeddings') and len(sample['embeddings']) > 0:
                                existing_dim = len(sample['embeddings'][0])
                                if existing_dim != expected_dim:
                                    print(f"⚠️ 检测到维度不匹配: 集合期望 {existing_dim} 维，但模型输出 {expected_dim} 维")
                                    print(f"   将重建集合以匹配新模型...")
                                    force_recreate = True
                                else:
                                    self.collection = existing_collection
                                    print(f"✅ 使用现有集合，维度: {expected_dim}")
                                    return
                        else:
                            # 集合为空，尝试添加测试向量来检查维度是否匹配
                            try:
                                existing_collection.add(
                                    embeddings=[test_embedding],
                                    documents=["__dimension_test__"],
                                    ids=["__dimension_test_id__"]
                                )
                                # 如果成功，删除测试数据
                                existing_collection.delete(ids=["__dimension_test_id__"])
                                self.collection = existing_collection
                                print(f"✅ 使用现有集合，维度: {expected_dim}")
                                return
                            except Exception as e:
                                if "dimension" in str(e).lower():
                                    print(f"⚠️ 检测到维度不匹配，将重建集合...")
                                    print(f"   错误信息: {e}")
                                    force_recreate = True
                                else:
                                    raise
                except Exception as e:
                    print(f"⚠️ 检查维度时出错: {e}，将重建集合")
                    force_recreate = True
            
            # 如果需要重建，删除旧集合
            if force_recreate:
                try:
                    self.client.delete_collection(name=collection_name)
                    print(f"🗑️ 已删除旧集合（维度不匹配）")
                except Exception:
                    pass  # 集合可能不存在
        except Exception:
            # 集合不存在，继续创建
            pass
        
        # 创建新集合
        self.collection = self.client.get_or_create_collection(
            name=collection_name,
            metadata={"description": "晶体生长外部知识库", "model": model}
        )
        print(f"✅ 已创建/获取集合: {collection_name} (模型: {model})")
    
    def add_documents(self, chunks: List[str], embeddings: List[List[float]], metadata: List[Dict] = None):
        """
        添加文档到向量库
        
        Args:
            chunks: 文本块列表
            embeddings: 向量列表
            metadata: 元数据列表（可选）
        """
        if metadata is None:
            metadata = [{}] * len(chunks)
        
        # 生成 ID
        ids = [f"doc_{i}_{hash(chunk) % 10000}" for i, chunk in enumerate(chunks)]
        
        # 添加到集合
        self.collection.add(
            embeddings=embeddings,
            documents=chunks,
            metadatas=metadata,
            ids=ids
        )
        
        print(f"✅ 已添加 {len(chunks)} 个文档块到知识库")
    
    def search(self, query: str, top_k: int = 5, filter_metadata: Dict = None) -> List[Dict]:
        """
        检索相关知识
        
        Args:
            query: 查询文本
            top_k: 返回结果数量
            filter_metadata: 元数据过滤条件（可选）
            
        Returns:
            检索结果列表，每个结果包含：
            - text: 文档文本
            - metadata: 元数据
            - score: 相似度分数（距离，越小越相似）
        """
        # 生成查询向量
        query_embedding = embed_text(query)
        if not query_embedding:
            return []
        
        # 执行检索
        if filter_metadata:
            results = self.collection.query(
                query_embeddings=[query_embedding],
                n_results=top_k,
                where=filter_metadata
            )
        else:
            results = self.collection.query(
                query_embeddings=[query_embedding],
                n_results=top_k
            )
        
        # 格式化结果
        formatted_results = []
        if results['documents'] and len(results['documents'][0]) > 0:
            for i in range(len(results['documents'][0])):
                formatted_results.append({
                    "text": results['documents'][0][i],
                    "metadata": results['metadatas'][0][i] if results['metadatas'] else {},
                    "score": results['distances'][0][i] if results['distances'] else 0.0
                })
        
        return formatted_results
    
    def build_from_pdfs(self, pdf_directory: str):
        """
        从 PDF 目录构建知识库
        
        Args:
            pdf_directory: PDF 文件目录路径
        """
        if not PDF_AVAILABLE:
            raise ImportError("pdfplumber 未安装，无法处理 PDF")
        
        pdf_dir = Path(pdf_directory)
        if not pdf_dir.exists():
            raise FileNotFoundError(f"PDF 目录不存在: {pdf_directory}")
        
        all_chunks = []
        all_metadata = []
        
        # 遍历所有 PDF 文件
        for pdf_file in pdf_dir.glob("*.pdf"):
            print(f"📄 处理: {pdf_file.name}")
            
            # 解析 PDF
            chunks = parse_pdf(str(pdf_file))
            
            # 为每个块添加元数据
            for i, chunk in enumerate(chunks):
                all_chunks.append(chunk)
                all_metadata.append({
                    "source": pdf_file.name,
                    "type": "manual" if "manual" in pdf_file.name.lower() else "paper",
                    "chunk_index": i
                })
        
        if not all_chunks:
            print("⚠️ 未找到任何 PDF 文件或文本内容")
            return
        
        print(f"📚 共解析 {len(all_chunks)} 个文本块，正在生成向量...")
        
        # 批量生成向量
        embeddings = embed_chunks_batch(all_chunks, batch_size=1)
        
        # 过滤掉失败的向量
        valid_chunks = []
        valid_embeddings = []
        valid_metadata = []
        
        for chunk, embedding, metadata in zip(all_chunks, embeddings, all_metadata):
            if embedding is not None:
                valid_chunks.append(chunk)
                valid_embeddings.append(embedding)
                valid_metadata.append(metadata)
        
        # 添加到向量库
        if valid_chunks:
            self.add_documents(valid_chunks, valid_embeddings, valid_metadata)
            print(f"✅ 知识库构建完成，共 {len(valid_chunks)} 个文档块")
        else:
            print("❌ 所有向量生成失败，知识库构建失败")

# ================= 检索接口 =================

# 全局知识库实例（懒加载）
_kb_instance = None

def get_knowledge_base() -> ExternalKnowledgeBase:
    """获取知识库实例（单例模式）"""
    global _kb_instance
    if _kb_instance is None:
        _kb_instance = ExternalKnowledgeBase()
    return _kb_instance

def retrieve_knowledge(
    compound: str,
    method: str = None,
    top_k: int = 5
) -> List[Dict]:
    """
    检索外部知识（主要接口）
    
    Args:
        compound: 化合物名称（如 "FeSe", "MoS2"）
        method: 实验方法（如 "CVT", "Flux"）
        top_k: 返回结果数量
        
    Returns:
        检索结果列表
    """
    if not CHROMA_AVAILABLE:
        return []
    
    try:
        kb = get_knowledge_base()
        
        # 构建查询文本
        query_parts = [compound, "crystal growth"]
        if method:
            query_parts.append(method)
        query_text = " ".join(query_parts)
        
        # 执行检索
        results = kb.search(query_text, top_k=top_k)
        
        return results
    except Exception as e:
        print(f"⚠️ 知识检索失败: {e}")
        return []

def validate_compound_with_knowledge(
    compound: str,
    method: str = None
) -> List[Dict]:
    """
    基于外部知识校验化合物和配方
    
    Args:
        compound: 化合物名称
        method: 实验方法
        
    Returns:
        校验问题列表（格式与 review_issues 一致）
    """
    issues = []
    
    # 检索相关知识
    knowledge = retrieve_knowledge(compound, method, top_k=3)
    
    if not knowledge:
        return issues
    
    # 检查常见识别错误
    # 例如：I₂ 可能被识别为 12
    if "I2" in compound or "I₂" in compound:
        # 检查知识库中是否有关于 I₂ 作为输运剂的信息
        for item in knowledge:
            text = item["text"].lower()
            if "i2" in text or "i₂" in text or "iodine" in text:
                if "transport" in text or "输运" in text or "cvt" in text.lower():
                    # 如果识别为 "12" 而不是 "I2"，应该修正
                    if compound.replace("I2", "").replace("I₂", "") == "12":
                        issues.append({
                            "severity": "error",
                            "field": "ingredients[].compound",
                            "description": f"化合物识别错误：'{compound}' 可能是 'I₂'（碘）的误识别。根据文献，CVT 法常用 I₂ 作为输运剂。",
                            "suggestion": "请检查图片中的化学式，确认是否为 I₂（碘）而非数字 12。"
                        })
    
    return issues

def retrieve_material_properties(compound: str) -> Optional[Dict]:
    """
    检索材料的物理性质
    
    Args:
        compound: 化合物名称
        
    Returns:
        物理性质字典，包含：
        - melting_point: 熔点
        - space_group: 空间群
        - lattice_params: 晶格参数
        - etc.
    """
    # 检索相关知识
    knowledge = retrieve_knowledge(compound, top_k=5)
    
    if not knowledge:
        return None
    
    # 从检索结果中提取物理性质
    properties = {}
    
    for item in knowledge:
        text = item["text"]
        
        # 提取熔点
        melting_match = re.search(r'melting point[:\s]+([\d\.]+)\s*[°℃]?C', text, re.IGNORECASE)
        if melting_match:
            properties["melting_point"] = melting_match.group(1) + "°C"
        
        # 提取空间群
        space_group_match = re.search(r'space group[:\s]+([A-Z0-9/]+)', text, re.IGNORECASE)
        if space_group_match:
            properties["space_group"] = space_group_match.group(1)
        
        # 提取晶格参数
        lattice_match = re.search(r'lattice parameter[:\s]+([\d\.]+)\s*Å', text, re.IGNORECASE)
        if lattice_match:
            properties["lattice_parameter"] = lattice_match.group(1) + " Å"
    
    return properties if properties else None

# ================= 使用示例 =================

if __name__ == "__main__":
    # 示例 1: 构建知识库
    print("=" * 60)
    print("示例 1: 构建知识库")
    print("=" * 60)
    
    kb = ExternalKnowledgeBase()
    
    # 从 PDF 目录构建（如果存在）
    if KNOWLEDGE_BASE_PATH.exists():
        kb.build_from_pdfs(str(KNOWLEDGE_BASE_PATH))
    else:
        print(f"⚠️ 知识库目录不存在: {KNOWLEDGE_BASE_PATH}")
        print("   请创建该目录并放入 PDF 文件")
    
    # 示例 2: 检索知识
    print("\n" + "=" * 60)
    print("示例 2: 检索知识")
    print("=" * 60)
    
    results = retrieve_knowledge("FeSe", method="CVT", top_k=3)
    for i, result in enumerate(results, 1):
        print(f"\n结果 {i}:")
        print(f"  相似度: {1 - result['score']:.3f}")
        print(f"  来源: {result['metadata'].get('source', 'unknown')}")
        print(f"  文本: {result['text'][:100]}...")
    
    # 示例 3: 配方校验
    print("\n" + "=" * 60)
    print("示例 3: 配方校验")
    print("=" * 60)
    
    issues = validate_compound_with_knowledge("12", method="CVT")
    for issue in issues:
        print(f"\n{issue['severity'].upper()}: {issue['description']}")
        print(f"  建议: {issue['suggestion']}")
    
    # 示例 4: 检索材料性质
    print("\n" + "=" * 60)
    print("示例 4: 检索材料性质")
    print("=" * 60)
    
    properties = retrieve_material_properties("FeSe")
    if properties:
        print("物理性质:")
        for key, value in properties.items():
            print(f"  {key}: {value}")
    else:
        print("未找到相关物理性质")

