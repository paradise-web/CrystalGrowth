"""
构建外部文献知识库脚本
从 pdfs 文件夹中读取所有 PDF 文件，构建向量数据库
"""

import os
import sys
from pathlib import Path

# 进度条（可选）
try:
    from tqdm import tqdm
    TQDM_AVAILABLE = True
except ImportError:
    TQDM_AVAILABLE = False
    # 如果没有 tqdm，使用简单的进度显示
    def tqdm(iterable, desc="", unit=""):
        print(f"{desc}...")
        return iterable

# 导入外部文献 RAG 模块
try:
    from external_rag import ExternalKnowledgeBase, parse_pdf, chunk_text, embed_chunks_batch, _smart_chunk_text, _estimate_token_count
except ImportError as e:
    print(f"❌ 导入失败: {e}")
    print("请确保 external_rag.py 文件存在且依赖已安装")
    sys.exit(1)

def build_knowledge_base(pdf_directory: str = "pdfs", batch_size: int = 10):
    """
    从 PDF 目录构建知识库
    
    Args:
        pdf_directory: PDF 文件目录路径
        batch_size: 批量处理大小（用于进度显示）
    """
    pdf_dir = Path(pdf_directory)
    
    if not pdf_dir.exists():
        print(f"❌ PDF 目录不存在: {pdf_directory}")
        print(f"   请创建该目录并放入 PDF 文件")
        return False
    
    # 获取所有 PDF 文件
    pdf_files = list(pdf_dir.glob("*.pdf"))
    
    if not pdf_files:
        print(f"⚠️ 在 {pdf_directory} 目录中未找到任何 PDF 文件")
        return False
    
    print(f"📚 找到 {len(pdf_files)} 个 PDF 文件")
    print("=" * 60)
    
    # 初始化知识库
    print("🔧 初始化向量数据库...")
    # 如果遇到维度不匹配错误，设置 force_recreate=True 来重建集合
    kb = ExternalKnowledgeBase(force_recreate=False)
    
    # 统计信息
    total_chunks = 0
    total_processed = 0
    failed_files = []
    
    # 处理每个 PDF 文件
    print("\n📄 开始处理 PDF 文件...")
    print("=" * 60)
    
    for pdf_file in tqdm(pdf_files, desc="处理 PDF", unit="文件"):
        try:
            print(f"\n📄 处理: {pdf_file.name}")
            
            # 解析 PDF
            chunks = parse_pdf(str(pdf_file))
            
            if not chunks:
                print(f"  ⚠️ 未提取到文本内容，跳过")
                failed_files.append((pdf_file.name, "未提取到文本"))
                continue
            
            # 递归检查和扁平化处理：确保所有chunk都安全
            print(f"  📝 初步提取到 {len(chunks)} 个文本块，进行安全检查...")
            safe_chunks = []
            
            for chunk in chunks:
                # 检查token数，如果超过1000（留出安全余量），进行智能切分
                estimated_tokens = _estimate_token_count(chunk)
                
                if estimated_tokens > 1000:
                    # 使用智能切分，确保所有子块都安全
                    sub_chunks = _smart_chunk_text(chunk, max_tokens=1000, overlap=100)
                    # 将所有子块扩展到safe_chunks（不丢弃任何子块！）
                    safe_chunks.extend(sub_chunks)
                    if len(sub_chunks) > 1:
                        print(f"     切分: 1个块 -> {len(sub_chunks)}个子块 (token: {estimated_tokens} -> 每个<1000)")
                else:
                    # 如果已经安全，直接添加
                    safe_chunks.append(chunk)
            
            if not safe_chunks:
                print(f"  ⚠️ 安全检查后为空，跳过")
                failed_files.append((pdf_file.name, "安全检查后为空"))
                continue
            
            print(f"  ✅ 安全检查完成: {len(chunks)} 个初步块 -> {len(safe_chunks)} 个安全块")
            
            # 重新构建元数据列表，确保与safe_chunks一一对应
            metadata_list = []
            for i, chunk in enumerate(safe_chunks):
                metadata_list.append({
                    "source": pdf_file.name,
                    "type": "paper",
                    "chunk_index": i,
                    "total_chunks": len(safe_chunks)
                })
            
            # 批量生成向量（传入安全的chunks）
            print(f"  🔄 正在生成向量（批量大小: {batch_size}）...")
            embeddings = embed_chunks_batch(safe_chunks, batch_size=batch_size)
            
            # 过滤掉失败的向量
            valid_chunks = []
            valid_embeddings = []
            valid_metadata = []
            
            for chunk, embedding, metadata in zip(safe_chunks, embeddings, metadata_list):
                if embedding is not None:
                    valid_chunks.append(chunk)
                    valid_embeddings.append(embedding)
                    valid_metadata.append(metadata)
            
            if not valid_chunks:
                print(f"  ❌ 所有向量生成失败，跳过此文件")
                failed_files.append((pdf_file.name, "向量生成失败"))
                continue
            
            # 添加到向量库
            kb.add_documents(valid_chunks, valid_embeddings, valid_metadata)
            
            total_chunks += len(valid_chunks)
            total_processed += 1
            
            print(f"  ✅ 成功添加 {len(valid_chunks)} 个文档块")
            
        except Exception as e:
            print(f"  ❌ 处理失败: {e}")
            failed_files.append((pdf_file.name, str(e)))
            import traceback
            print(f"     详细错误: {traceback.format_exc()[:200]}")
    
    # 输出统计信息
    print("\n" + "=" * 60)
    print("📊 构建完成统计")
    print("=" * 60)
    print(f"✅ 成功处理: {total_processed} / {len(pdf_files)} 个文件")
    print(f"📚 总文档块数: {total_chunks}")
    
    if failed_files:
        print(f"\n⚠️ 失败文件 ({len(failed_files)} 个):")
        for filename, reason in failed_files[:10]:  # 只显示前10个
            print(f"  - {filename}: {reason}")
        if len(failed_files) > 10:
            print(f"  ... 还有 {len(failed_files) - 10} 个失败文件")
    
    print("\n" + "=" * 60)
    print("✅ 知识库构建完成！")
    print("=" * 60)
    print(f"📁 向量数据库位置: ./vector_db/")
    print(f"💡 现在可以在 Role B 和 Role C 中使用外部文献 RAG 功能")
    
    return True

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="构建外部文献知识库")
    parser.add_argument(
        "--pdf-dir",
        type=str,
        default="pdfs",
        help="PDF 文件目录路径（默认: pdfs）"
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=10,
        help="批量处理大小（默认: 10）"
    )
    
    args = parser.parse_args()
    
    # 检查 API Key
    if not os.getenv("DASHSCOPE_API_KEY"):
        print("⚠️ 警告: 未设置 DASHSCOPE_API_KEY 环境变量")
        print("   请设置环境变量或确保在代码中配置了 API Key")
        response = input("是否继续？(y/n): ")
        if response.lower() != 'y':
            sys.exit(1)
    
    # 构建知识库
    success = build_knowledge_base(args.pdf_dir, args.batch_size)
    
    if success:
        print("\n🎉 知识库构建成功！")
    else:
        print("\n❌ 知识库构建失败")
        sys.exit(1)

