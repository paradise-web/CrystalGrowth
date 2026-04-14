"""
重建外部文献知识库脚本
彻底清洗旧数据并重新构建向量数据库
"""

import os
import sys
import shutil
from pathlib import Path

# 导入外部文献 RAG 模块
try:
    from external_rag import ExternalKnowledgeBase, VECTOR_DB_PATH
except ImportError as e:
    print(f"❌ 导入失败: {e}")
    print("请确保 external_rag.py 文件存在且依赖已安装")
    sys.exit(1)

def check_api_key():
    """检查 API Key 是否设置"""
    api_key = os.getenv("DASHSCOPE_API_KEY")
    
    if not api_key:
        print("⚠️ 未检测到 DASHSCOPE_API_KEY 环境变量")
        print("   请设置环境变量或确保在 external_rag.py 中配置了 API Key")
        
        # 检查 external_rag.py 中是否有默认值
        try:
            from external_rag import API_KEY
            if API_KEY and API_KEY != "":
                print(f"✅ 检测到 external_rag.py 中的默认 API Key，将使用该值")
                return True
        except:
            pass
        
        response = input("\n是否继续？(y/n): ")
        if response.lower() != 'y':
            print("❌ 已取消操作")
            sys.exit(1)
    
    return True

def clean_old_database(db_path: Path):
    """
    清理旧的向量数据库
    
    Args:
        db_path: 向量数据库路径
    """
    if db_path.exists():
        print(f"🗑️  发现旧的向量数据库目录: {db_path}")
        print(f"   正在删除旧数据...")
        
        try:
            shutil.rmtree(db_path)
            print(f"✅ 旧数据库已完全删除")
        except Exception as e:
            print(f"❌ 删除旧数据库失败: {e}")
            print("   请手动删除该目录后重试")
            sys.exit(1)
    else:
        print(f"ℹ️  未发现旧的向量数据库目录: {db_path}")
        print(f"   将创建新的数据库")

def rebuild_database(pdf_directory: str = "pdfs"):
    """
    重建向量数据库
    
    Args:
        pdf_directory: PDF 文件目录路径
    """
    # 检查 PDF 目录
    pdf_dir = Path(pdf_directory)
    if not pdf_dir.exists():
        print(f"❌ PDF 目录不存在: {pdf_directory}")
        print(f"   请确保该目录存在并包含 PDF 文件")
        sys.exit(1)
    
    # 检查是否有 PDF 文件
    pdf_files = list(pdf_dir.glob("*.pdf"))
    if not pdf_files:
        print(f"⚠️  在 {pdf_directory} 目录中未找到任何 PDF 文件")
        response = input("是否继续？（将创建空数据库）(y/n): ")
        if response.lower() != 'y':
            print("❌ 已取消操作")
            sys.exit(1)
    else:
        print(f"📚 找到 {len(pdf_files)} 个 PDF 文件")
    
    # 获取向量数据库路径
    db_path = Path(VECTOR_DB_PATH) if isinstance(VECTOR_DB_PATH, (str, Path)) else VECTOR_DB_PATH
    
    # 清理旧数据库
    print("\n" + "=" * 60)
    print("步骤 1: 清理旧数据库")
    print("=" * 60)
    clean_old_database(db_path)
    
    # 重建数据库
    print("\n" + "=" * 60)
    print("步骤 2: 重建向量数据库")
    print("=" * 60)
    
    try:
        # 实例化知识库（会自动创建新的数据库目录）
        print("🔧 初始化新的向量数据库...")
        kb = ExternalKnowledgeBase()
        
        # 构建知识库
        print(f"📄 开始处理 PDF 文件...")
        kb.build_from_pdfs(str(pdf_dir))
        
        print("\n" + "=" * 60)
        print("✅ 数据库重建完成！")
        print("=" * 60)
        print(f"📁 向量数据库位置: {db_path.absolute()}")
        print(f"💡 现在可以在 Role B 和 Role C 中使用更新后的外部文献 RAG 功能")
        
        return True
        
    except Exception as e:
        print(f"\n❌ 数据库重建失败: {e}")
        import traceback
        print(f"   详细错误信息:\n{traceback.format_exc()}")
        sys.exit(1)

def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(
        description="彻底清洗并重建外部文献知识库",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python rebuild_db.py                    # 使用默认 PDF 目录 (./pdfs)
  python rebuild_db.py --pdf-dir pdfs     # 指定 PDF 目录
        """
    )
    parser.add_argument(
        "--pdf-dir",
        type=str,
        default="pdfs",
        help="PDF 文件目录路径（默认: pdfs）"
    )
    parser.add_argument(
        "--skip-check",
        action="store_true",
        help="跳过 API Key 检查（不推荐）"
    )
    
    args = parser.parse_args()
    
    # 环境检查
    if not args.skip_check:
        print("=" * 60)
        print("环境检查")
        print("=" * 60)
        if not check_api_key():
            sys.exit(1)
    
    # 确认操作
    print("\n" + "=" * 60)
    print("⚠️  警告：此操作将完全删除旧的向量数据库并重新构建")
    print("=" * 60)
    print(f"📁 PDF 目录: {args.pdf_dir}")
    print(f"📁 向量数据库目录: {VECTOR_DB_PATH}")
    
    response = input("\n确认继续？(yes/no): ")
    if response.lower() not in ['yes', 'y']:
        print("❌ 已取消操作")
        sys.exit(0)
    
    # 执行重建
    print("\n" + "=" * 60)
    print("开始重建数据库")
    print("=" * 60)
    
    success = rebuild_database(args.pdf_dir)
    
    if success:
        print("\n🎉 数据库重建成功！")
    else:
        print("\n❌ 数据库重建失败")
        sys.exit(1)

if __name__ == "__main__":
    main()

