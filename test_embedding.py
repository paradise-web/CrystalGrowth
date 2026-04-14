"""
测试 DashScope Embedding API 连接
用于诊断批量 Embedding 失败的原因
"""

import os
import sys
from external_rag import embed_text, embed_chunks_batch, API_KEY, BASE_URL

def test_single_embedding():
    """测试单个文本的 Embedding"""
    print("=" * 60)
    print("测试 1: 单个文本 Embedding")
    print("=" * 60)
    
    test_text = "This is a test text for embedding."
    
    try:
        embedding = embed_text(test_text)
        if embedding:
            print(f"✅ 成功: 向量维度 = {len(embedding)}")
            return True
        else:
            print("❌ 失败: 返回 None")
            return False
    except Exception as e:
        print(f"❌ 异常: {e}")
        import traceback
        print(traceback.format_exc())
        return False

def test_batch_embedding():
    """测试批量 Embedding"""
    print("\n" + "=" * 60)
    print("测试 2: 批量文本 Embedding (3 个文本)")
    print("=" * 60)
    
    test_texts = [
        "Crystal growth using CVT method.",
        "FeSe compound synthesis.",
        "MoS2 single crystal preparation."
    ]
    
    try:
        embeddings = embed_chunks_batch(test_texts, batch_size=3)
        
        success_count = sum(1 for e in embeddings if e is not None)
        print(f"\n结果: {success_count}/{len(test_texts)} 成功")
        
        if success_count == len(test_texts):
            print("✅ 批量 Embedding 测试通过")
            return True
        else:
            print("⚠️ 部分失败，请检查错误信息")
            return False
            
    except Exception as e:
        print(f"❌ 异常: {e}")
        import traceback
        print(traceback.format_exc())
        return False

def check_api_config():
    """检查 API 配置"""
    print("=" * 60)
    print("环境检查")
    print("=" * 60)
    
    print(f"API Key: {'已设置' if API_KEY else '未设置'}")
    if API_KEY:
        print(f"  Key 前缀: {API_KEY[:10]}...")
    print(f"Base URL: {BASE_URL}")
    
    # 检查环境变量
    env_key = os.getenv("DASHSCOPE_API_KEY")
    if env_key:
        print(f"环境变量 DASHSCOPE_API_KEY: 已设置")
    else:
        print(f"环境变量 DASHSCOPE_API_KEY: 未设置（使用代码中的默认值）")
    
    return True

def main():
    """主函数"""
    print("\n" + "=" * 60)
    print("DashScope Embedding API 诊断工具")
    print("=" * 60)
    
    # 环境检查
    check_api_config()
    
    # 测试单个 Embedding
    test1_result = test_single_embedding()
    
    # 如果单个测试失败，不继续批量测试
    if not test1_result:
        print("\n❌ 单个 Embedding 测试失败，请先解决此问题")
        print("\n可能的原因:")
        print("1. API Key 无效或未设置")
        print("2. 模型名称不正确")
        print("3. 网络连接问题")
        print("4. API 服务异常")
        sys.exit(1)
    
    # 测试批量 Embedding
    test2_result = test_batch_embedding()
    
    # 总结
    print("\n" + "=" * 60)
    print("测试总结")
    print("=" * 60)
    if test1_result and test2_result:
        print("✅ 所有测试通过！")
        print("💡 如果批量处理仍然失败，可能是:")
        print("   - 文本块数量过多导致超时")
        print("   - API 速率限制")
        print("   - 某些文本块内容异常")
    else:
        print("❌ 部分测试失败，请根据上述错误信息排查问题")

if __name__ == "__main__":
    main()

