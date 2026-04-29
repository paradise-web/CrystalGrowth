#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""测试修复效果"""

from database import get_db

def test_database_fixes():
    print("=" * 60)
    print("🧪 测试数据库修复效果")
    print("=" * 60)
    
    try:
        db = get_db()
        print("✅ 数据库连接成功")
        
        # 测试审计日志表
        logs = db.get_audit_logs()
        print(f"✅ 审计日志表正常，当前记录数: {len(logs)}")
        
        # 测试条件校验方法
        result = db.validate_approval_conditions('test-task-id')
        print(f"✅ 条件校验方法正常，返回: {result}")
        
        # 测试任务查询方法（问题1修复验证）
        tasks = db.get_processing_tasks(limit=5)
        print(f"✅ get_processing_tasks 返回 {len(tasks)} 条记录")
        
        tasks_needing_review = db.get_tasks_needing_review()
        print(f"✅ get_tasks_needing_review 返回 {len(tasks_needing_review)} 条记录")
        
        print("\n🎉 所有数据库修改验证通过！")
        return True
        
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    test_database_fixes()