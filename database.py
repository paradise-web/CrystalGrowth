"""
数据库模块 - 实验记录持久化存储
使用 SQLite 数据库存储实验记录和处理历史
"""

import sqlite3
import json
import os
import hashlib
from datetime import datetime
from typing import Optional, List, Dict, Any
from pathlib import Path


class ExperimentDB:
    """实验记录数据库管理类"""
    
    def __init__(self, db_path: str = "experiments.db"):
        """
        初始化数据库连接
        
        Args:
            db_path: 数据库文件路径
        """
        self.db_path = db_path
        self._init_database()
    
    def _init_database(self):
        """初始化数据库表结构"""
        conn = sqlite3.connect(self.db_path)
        conn.text_factory = str
        cursor = conn.cursor()
        
        # 创建实验记录表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS experiments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                image_filename TEXT NOT NULL,
                image_hash TEXT NOT NULL UNIQUE,
                image_path TEXT,
                image_reference_path TEXT,
                
                -- 提取的数据
                raw_json TEXT,
                reviewed_json TEXT,
                formatted_markdown TEXT,
                
                -- 处理元数据
                iteration_count INTEGER DEFAULT 0,
                max_iterations INTEGER DEFAULT 3,
                review_passed INTEGER DEFAULT 0,  -- 0=False, 1=True
                review_issues TEXT,  -- JSON格式存储问题列表
                
                -- 人工审核信息
                human_feedback TEXT,
                review_passed_override INTEGER,  -- NULL=未设置, 0=False, 1=True
                
                -- 时间戳
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                
                -- 额外信息
                notes TEXT,
                
                -- 增强搜索：关键参数文本（用于动态参数检索）
                key_params_text TEXT
            )
        """)
        
        # 数据库迁移：检查并添加 key_params_text 列（如果不存在）
        try:
            # 检查列是否存在
            cursor.execute("PRAGMA table_info(experiments)")
            columns = [row[1] for row in cursor.fetchall()]
            if 'key_params_text' not in columns:
                cursor.execute("ALTER TABLE experiments ADD COLUMN key_params_text TEXT")
                conn.commit()
        except sqlite3.OperationalError as e:
            # 如果出错，尝试直接添加（可能表不存在，会在 CREATE TABLE 中创建）
            try:
                cursor.execute("ALTER TABLE experiments ADD COLUMN key_params_text TEXT")
                conn.commit()
            except:
                pass  # 列已存在或表不存在，忽略
        
        # 创建反馈历史表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS feedback_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                experiment_id INTEGER NOT NULL,
                feedback_text TEXT NOT NULL,
                feedback_type TEXT DEFAULT 'human',  -- 'human' or 'auto'
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (experiment_id) REFERENCES experiments(id) ON DELETE CASCADE
            )
        """)
        
        # 创建处理任务表（用于异步处理队列）
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS processing_tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id TEXT NOT NULL UNIQUE,
                image_filename TEXT NOT NULL,
                image_bytes BLOB NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                error_message TEXT,
                progress INTEGER DEFAULT 0,
                current_step TEXT,
                experiment_id INTEGER,
                raw_json TEXT,
                reviewed_json TEXT,
                formatted_markdown TEXT,
                iteration_count INTEGER DEFAULT 0,
                max_iterations INTEGER DEFAULT 3,
                review_issues TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (experiment_id) REFERENCES experiments(id) ON DELETE SET NULL
            )
        """)
        
        # 创建审计日志表（用于记录历史记录入库操作）
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS audit_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                operation_type TEXT NOT NULL,  -- 'CREATE', 'UPDATE', 'DELETE', 'APPROVE'
                table_name TEXT NOT NULL,     -- 'experiments', 'processing_tasks', etc.
                record_id INTEGER,            -- 被操作的记录ID
                operator TEXT DEFAULT 'system',  -- 操作人员
                trigger_condition TEXT,      -- 触发条件描述
                conditions_met TEXT,         -- 条件满足情况（JSON格式）
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                details TEXT                 -- 操作详情（JSON格式）
            )
        """)
        
        # 创建索引以提高查询性能
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_image_hash ON experiments(image_hash)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_created_at ON experiments(created_at)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_review_passed ON experiments(review_passed)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_feedback_experiment ON feedback_history(experiment_id)
        """)
        
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_task_status ON processing_tasks(status)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_task_created ON processing_tasks(created_at)
        """)
        
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_audit_operation ON audit_logs(operation_type)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_audit_created ON audit_logs(created_at)
        """)
        
        conn.commit()
        
        self._migrate_processing_tasks(conn)
        
        conn.close()
    
    def _migrate_processing_tasks(self, conn: sqlite3.Connection):
        """
        迁移 processing_tasks 表，添加新列（如果不存在）
        """
        cursor = conn.cursor()
        
        cursor.execute("PRAGMA table_info(processing_tasks)")
        columns = [row[1] for row in cursor.fetchall()]
        
        new_columns = {
            'raw_json': 'TEXT',
            'reviewed_json': 'TEXT',
            'formatted_markdown': 'TEXT',
            'iteration_count': 'INTEGER DEFAULT 0',
            'max_iterations': 'INTEGER DEFAULT 3',
            'review_issues': 'TEXT'
        }
        
        for col_name, col_type in new_columns.items():
            if col_name not in columns:
                try:
                    cursor.execute(f"ALTER TABLE processing_tasks ADD COLUMN {col_name} {col_type}")
                    print(f"  [OK] Added column {col_name} to processing_tasks")
                except sqlite3.OperationalError as e:
                    print(f"  [WARN] Failed to add column {col_name}: {e}")
        
        conn.commit()
    
    def _calculate_image_hash(self, image_bytes: bytes) -> str:
        """计算图片的哈希值（用于去重）"""
        return hashlib.sha256(image_bytes).hexdigest()
    
    def _check_existing_by_hash(self, image_hash: str) -> Optional[Dict[str, Any]]:
        """
        根据图片哈希值检查是否已存在记录
        
        Args:
            image_hash: 图片的 SHA256 哈希值
            
        Returns:
            存在的记录字典，如果不存在则返回 None
        """
        conn = sqlite3.connect(self.db_path)
        conn.text_factory = str
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM experiments WHERE image_hash = ?", (image_hash,))
        row = cursor.fetchone()
        conn.close()
        
        if row:
            return self._row_to_dict(row)
        return None
    
    def save_experiment(
        self,
        image_filename: str,
        image_bytes: bytes,
        image_path: Optional[str] = None,
        image_reference_path: Optional[str] = None,
        raw_json: Optional[str] = None,
        reviewed_json: Optional[str] = None,
        formatted_markdown: Optional[str] = None,
        iteration_count: int = 0,
        max_iterations: int = 3,
        review_passed: bool = False,
        review_issues: Optional[List[Dict]] = None,
        human_feedback: Optional[str] = None,
        review_passed_override: Optional[bool] = None,
        notes: Optional[str] = None,
        force_new: bool = False  # 新增参数：强制插入新记录
    ) -> int:
        """
        保存实验记录到数据库
        
        Returns:
            实验记录的ID
        """
        try:
            print(f"[INFO] [DB DEBUG] save_experiment 开始")
            print(f"  - image_filename: {image_filename}")
            print(f"  - image_bytes 长度: {len(image_bytes) if image_bytes else 0}")
            print(f"  - image_path: {image_path}")
            print(f"  - review_passed: {review_passed}")
            print(f"  - review_passed_override: {review_passed_override}")
            
            # 如果强制插入新记录，生成唯一的哈希值（加入时间戳）
            if force_new:
                # 加入时间戳确保唯一性
                timestamp_bytes = str(datetime.now()).encode('utf-8')
                combined_bytes = image_bytes + timestamp_bytes
                image_hash = hashlib.sha256(combined_bytes).hexdigest()
            else:
                image_hash = self._calculate_image_hash(image_bytes)
            print(f"  - image_hash: {image_hash}")
            
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            print(f"  [OK] 数据库连接成功")
            
            # 检查是否已存在相同图片的记录
            cursor.execute("SELECT id FROM experiments WHERE image_hash = ?", (image_hash,))
            existing = cursor.fetchone()
            print(f"  - 已存在记录: {'是' if existing else '否'}")
            if existing:
                print(f"    - 现有记录ID: {existing[0]}")
            print(f"  - force_new: {force_new}")
            
            if existing and not force_new:
                # 更新现有记录（只有在不是强制插入新记录时）
                experiment_id = existing[0]
                update_fields = []
                update_values = []
                
                # 更新字段：允许空字符串（空字符串表示需要重新处理）
                if image_path is not None:
                    update_fields.append("image_path = ?")
                    update_values.append(image_path)
                if image_reference_path is not None:
                    update_fields.append("image_reference_path = ?")
                    update_values.append(image_reference_path)
                # JSON 字段：空字符串也是有效值（表示需要重新提取）
                if raw_json is not None:
                    update_fields.append("raw_json = ?")
                    update_values.append(raw_json)
                if reviewed_json is not None:
                    update_fields.append("reviewed_json = ?")
                    update_values.append(reviewed_json)
                if formatted_markdown is not None:
                    update_fields.append("formatted_markdown = ?")
                    update_values.append(formatted_markdown)
                # 数值字段：总是更新（即使为0也是有效值）
                if iteration_count is not None:
                    update_fields.append("iteration_count = ?")
                    update_values.append(iteration_count)
                if max_iterations is not None:
                    update_fields.append("max_iterations = ?")
                    update_values.append(max_iterations)
                if review_passed is not None:
                    update_fields.append("review_passed = ?")
                    update_values.append(1 if review_passed else 0)
                # review_issues: 空列表也是有效值，需要更新
                if review_issues is not None:
                    update_fields.append("review_issues = ?")
                    update_values.append(json.dumps(review_issues, ensure_ascii=False))
                # human_feedback: 允许更新为空字符串（表示清除反馈）
                if human_feedback is not None:
                    update_fields.append("human_feedback = ?")
                    update_values.append(human_feedback)
                if review_passed_override is not None:
                    update_fields.append("review_passed_override = ?")
                    update_values.append(1 if review_passed_override else 0)
                if notes is not None:
                    update_fields.append("notes = ?")
                    update_values.append(notes)
                
                # 更新关键参数文本（根据最新的 JSON 数据）
                if reviewed_json is not None:
                    try:
                        reviewed_data = json.loads(reviewed_json)
                        key_params_text = self._extract_key_params_text(reviewed_data)
                        update_fields.append("key_params_text = ?")
                        update_values.append(key_params_text)
                    except Exception as e:
                        print(f"    [WARN] 解析 reviewed_json 失败: {e}")
                elif raw_json is not None:
                    try:
                        raw_data = json.loads(raw_json)
                        key_params_text = self._extract_key_params_text(raw_data)
                        update_fields.append("key_params_text = ?")
                        update_values.append(key_params_text)
                    except Exception as e:
                        print(f"    [WARN] 解析 raw_json 失败: {e}")
                
                # 总是更新 updated_at 时间戳
                update_fields.append("updated_at = CURRENT_TIMESTAMP")
                update_values.append(experiment_id)
                
                print(f"  - 更新字段数: {len(update_fields)}")
                print(f"  - 更新值数: {len(update_values)}")
                
                if len(update_fields) > 0:  # 至少有一个字段（至少有 updated_at）
                    query = f"UPDATE experiments SET {', '.join(update_fields)} WHERE id = ?"
                    print(f"    - SQL: {query[:100]}...")
                    cursor.execute(query, update_values)
                    print(f"    [OK] UPDATE 执行成功，影响行数: {cursor.rowcount}")
            else:
                # 提取关键参数文本（用于增强搜索）
                key_params_text = ""
                if reviewed_json:
                    try:
                        reviewed_data = json.loads(reviewed_json)
                        key_params_text = self._extract_key_params_text(reviewed_data)
                    except Exception as e:
                        print(f"    [WARN] 解析 reviewed_json 失败: {e}")
                if not key_params_text and raw_json:
                    try:
                        raw_data = json.loads(raw_json)
                        key_params_text = self._extract_key_params_text(raw_data)
                    except Exception as e:
                        print(f"    [WARN] 解析 raw_json 失败: {e}")
                
                # 插入新记录
                print(f"    📥 执行 INSERT...")
                cursor.execute("""
                    INSERT INTO experiments (
                        image_filename, image_hash, image_path, image_reference_path,
                        raw_json, reviewed_json, formatted_markdown,
                        iteration_count, max_iterations, review_passed, review_issues,
                        human_feedback, review_passed_override, notes, key_params_text
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    image_filename, image_hash, image_path, image_reference_path,
                    raw_json, reviewed_json, formatted_markdown,
                    iteration_count, max_iterations, 1 if review_passed else 0,
                    json.dumps(review_issues, ensure_ascii=False) if review_issues else None,
                    human_feedback,
                    1 if review_passed_override else 0 if review_passed_override is not None else None,
                    notes, key_params_text
                ))
                experiment_id = cursor.lastrowid
                print(f"    [OK] INSERT 执行成功，新记录ID: {experiment_id}")
            
            conn.commit()
            print(f"  [OK] 事务提交成功")
            conn.close()
            
            print(f"[OK] [DB DEBUG] save_experiment 完成，experiment_id={experiment_id}")
            return experiment_id
        except Exception as e:
            print(f"[ERROR] [DB DEBUG] save_experiment 失败: {type(e).__name__}: {str(e)}")
            import traceback
            print(f"   详细错误: {traceback.format_exc()}")
            raise
    
    def _extract_key_params_text(self, data: dict) -> str:
        """
        从实验数据中提取关键参数文本（用于增强搜索）
        
        Args:
            data: 实验数据字典
        
        Returns:
            关键参数文本字符串
        """
        params = []
        
        for exp in data.get("experiments", []):
            # 提取方法
            meta = exp.get("meta", {})
            if isinstance(meta, dict) and meta.get("method"):
                params.append(meta.get("method"))
            
            # 提取温度参数
            process = exp.get("process", {})
            if isinstance(process, dict):
                # 从 dynamic_params 提取
                if process.get("dynamic_params"):
                    for param in process.get("dynamic_params", []):
                        if isinstance(param, dict):
                            name = param.get("name", "")
                            value = param.get("value", "")
                            if name and value:
                                params.append(f"{name}: {value}")
                # 向后兼容：从固定参数提取
                if process.get("high_temp"):
                    params.append(f"高温: {process.get('high_temp')}")
                if process.get("low_temp"):
                    params.append(f"低温: {process.get('low_temp')}")
            
            # 提取配料
            ingredients = exp.get("ingredients", {})
            if isinstance(ingredients, dict):
                precursors = ingredients.get("precursors", [])
                for p in precursors:
                    if isinstance(p, dict):
                        name = p.get("name", "") or p.get("compound", "")
                        if name:
                            params.append(name)
            elif isinstance(ingredients, list):
                for ing in ingredients:
                    if isinstance(ing, dict):
                        name = ing.get("compound", "") or ing.get("name", "")
                        if name:
                            params.append(name)
        
        return " ".join(params)
    
    def get_experiment(self, experiment_id: int) -> Optional[Dict[str, Any]]:
        """根据ID获取实验记录"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM experiments WHERE id = ?", (experiment_id,))
        row = cursor.fetchone()
        conn.close()
        
        if row:
            return self._row_to_dict(row)
        return None
    
    def get_all_experiments(
        self,
        limit: Optional[int] = None,
        offset: int = 0,
        order_by: str = "created_at",
        order_desc: bool = True,
        filter_review_passed: Optional[bool] = None,
        search_query: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        获取所有实验记录
        
        Args:
            limit: 返回记录数限制
            offset: 偏移量
            order_by: 排序字段
            order_desc: 是否降序
            filter_review_passed: 按审核状态筛选
            search_query: 搜索关键词（搜索文件名和Markdown内容）
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        query = "SELECT * FROM experiments WHERE 1=1"
        params = []
        
        if filter_review_passed is not None:
            query += " AND review_passed = ?"
            params.append(1 if filter_review_passed else 0)
        
        if search_query:
            query += " AND (image_filename LIKE ? OR formatted_markdown LIKE ? OR raw_json LIKE ? OR key_params_text LIKE ?)"
            search_pattern = f"%{search_query}%"
            params.extend([search_pattern, search_pattern, search_pattern, search_pattern])
        
        # 排序
        order_direction = "DESC" if order_desc else "ASC"
        query += f" ORDER BY {order_by} {order_direction}"
        
        # 分页
        if limit:
            query += " LIMIT ? OFFSET ?"
            params.extend([limit, offset])
        
        cursor.execute(query, params)
        rows = cursor.fetchall()
        conn.close()
        
        return [self._row_to_dict(row) for row in rows]
    
    def get_experiment_count(
        self,
        filter_review_passed: Optional[bool] = None,
        search_query: Optional[str] = None
    ) -> int:
        """获取实验记录总数"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        query = "SELECT COUNT(*) FROM experiments WHERE 1=1"
        params = []
        
        if filter_review_passed is not None:
            query += " AND review_passed = ?"
            params.append(1 if filter_review_passed else 0)
        
        if search_query:
            query += " AND (image_filename LIKE ? OR formatted_markdown LIKE ? OR raw_json LIKE ? OR key_params_text LIKE ?)"
            search_pattern = f"%{search_query}%"
            params.extend([search_pattern, search_pattern, search_pattern, search_pattern])
        
        cursor.execute(query, params)
        count = cursor.fetchone()[0]
        conn.close()
        
        return count
    
    def add_feedback(self, experiment_id: int, feedback_text: str, feedback_type: str = "human"):
        """添加反馈历史"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT INTO feedback_history (experiment_id, feedback_text, feedback_type)
            VALUES (?, ?, ?)
        """, (experiment_id, feedback_text, feedback_type))
        
        conn.commit()
        conn.close()
    
    def log_audit(self, operation_type: str, table_name: str, record_id: int = None, 
                  operator: str = "system", trigger_condition: str = "", 
                  conditions_met: dict = None, details: dict = None):
        """
        记录审计日志
        
        Args:
            operation_type: 操作类型 ('CREATE', 'UPDATE', 'DELETE', 'APPROVE')
            table_name: 操作的表名
            record_id: 被操作的记录ID
            operator: 操作人员
            trigger_condition: 触发条件描述
            conditions_met: 条件满足情况（字典）
            details: 操作详情（字典）
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        conditions_met_json = json.dumps(conditions_met or {}, ensure_ascii=False)
        details_json = json.dumps(details or {}, ensure_ascii=False)
        
        cursor.execute("""
            INSERT INTO audit_logs (
                operation_type, table_name, record_id, operator, 
                trigger_condition, conditions_met, details
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (operation_type, table_name, record_id, operator, 
              trigger_condition, conditions_met_json, details_json))
        
        conn.commit()
        conn.close()
    
    def get_audit_logs(self, operation_type: str = None, limit: int = 100) -> List[Dict[str, Any]]:
        """
        获取审计日志
        
        Args:
            operation_type: 操作类型筛选（可选）
            limit: 返回记录数限制
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        query = "SELECT * FROM audit_logs WHERE 1=1"
        params = []
        
        if operation_type:
            query += " AND operation_type = ?"
            params.append(operation_type)
        
        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)
        
        cursor.execute(query, params)
        rows = cursor.fetchall()
        conn.close()
        
        result = []
        for row in rows:
            row_dict = dict(row)
            if row_dict.get('conditions_met'):
                try:
                    row_dict['conditions_met'] = json.loads(row_dict['conditions_met'])
                except:
                    pass
            if row_dict.get('details'):
                try:
                    row_dict['details'] = json.loads(row_dict['details'])
                except:
                    pass
            result.append(row_dict)
        
        return result
    
    def validate_approval_conditions(self, task_id: str) -> Dict[str, bool]:
        """
        校验历史记录入库的三重条件：
        a) Agent已完成对试验记录报告的处理
        b) 任务状态已更新为"待审核"
        c) 用户在待审批页面明确点击"通过审核"按钮
        
        Args:
            task_id: 任务ID
        
        Returns:
            条件满足情况字典
        """
        task = self.get_task(task_id)
        
        conditions = {
            'agent_processing_completed': False,
            'status_pending_review': False,
            'user_approved': False
        }
        
        if task:
            # 条件a: Agent已完成处理 - 检查是否有处理结果
            conditions['agent_processing_completed'] = (
                task.get('status') == 'pending_review' and 
                (task.get('raw_json') or task.get('reviewed_json') or task.get('formatted_markdown'))
            )
            
            # 条件b: 任务状态为待审核（使用专门的待审批状态）
            conditions['status_pending_review'] = (
                task.get('status') == 'pending_review'
            )
            
            # 条件c: 用户已点击"通过审核"按钮
            # 这个条件需要在应用层检查，这里默认返回False，由应用层设置
            conditions['user_approved'] = False
        
        return conditions
    
    def get_feedback_history(self, experiment_id: int) -> List[Dict[str, Any]]:
        """获取实验的反馈历史"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT * FROM feedback_history
            WHERE experiment_id = ?
            ORDER BY created_at ASC
        """, (experiment_id,))
        
        rows = cursor.fetchall()
        conn.close()
        
        return [dict(row) for row in rows]
    
    def update_experiment_review(self, experiment_id: int, review_passed: bool, feedback: Optional[str] = None) -> bool:
        """更新实验记录的审核状态"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        update_fields = ["review_passed = ?", "updated_at = CURRENT_TIMESTAMP"]
        params = [1 if review_passed else 0]
        
        if feedback is not None:
            update_fields.append("human_feedback = ?")
            params.append(feedback)
        
        params.append(experiment_id)
        
        cursor.execute(
            f"UPDATE experiments SET {', '.join(update_fields)} WHERE id = ?",
            params
        )
        
        updated = cursor.rowcount > 0
        
        conn.commit()
        conn.close()
        
        return updated
    
    def delete_experiment(self, experiment_id: int) -> bool:
        """删除实验记录（级联删除反馈历史）"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("DELETE FROM experiments WHERE id = ?", (experiment_id,))
        deleted = cursor.rowcount > 0
        
        conn.commit()
        conn.close()
        
        return deleted
    
    def get_statistics(self) -> Dict[str, Any]:
        """获取统计信息"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # 总记录数
        cursor.execute("SELECT COUNT(*) FROM experiments")
        total_count = cursor.fetchone()[0]
        
        # 审核通过数
        cursor.execute("SELECT COUNT(*) FROM experiments WHERE review_passed = 1")
        passed_count = cursor.fetchone()[0]
        
        # 审核未通过数
        cursor.execute("SELECT COUNT(*) FROM experiments WHERE review_passed = 0")
        failed_count = cursor.fetchone()[0]
        
        # 平均迭代次数
        cursor.execute("SELECT AVG(iteration_count) FROM experiments WHERE iteration_count > 0")
        avg_iterations = cursor.fetchone()[0] or 0
        
        # 最近7天的记录数
        cursor.execute("""
            SELECT COUNT(*) FROM experiments
            WHERE created_at >= datetime('now', '-7 days')
        """)
        recent_count = cursor.fetchone()[0]
        
        conn.close()
        
        return {
            "total_count": total_count,
            "passed_count": passed_count,
            "failed_count": failed_count,
            "avg_iterations": round(avg_iterations, 2),
            "recent_count": recent_count,
            "pass_rate": round(passed_count / total_count * 100, 2) if total_count > 0 else 0
        }
    
    def get_daily_statistics(self, start_date: str = None, end_date: str = None) -> List[Dict[str, Any]]:
        """获取指定时间范围内的每日记录数"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # 构建查询
        query = """
            SELECT 
                date(created_at) as date,
                COUNT(*) as count
            FROM experiments
            WHERE 1=1
        """
        params = []
        
        # 添加时间范围条件
        if start_date:
            query += " AND created_at >= ?"
            params.append(start_date)
        if end_date:
            query += " AND created_at <= ?"
            params.append(end_date + " 23:59:59")
        
        # 分组和排序
        query += " GROUP BY date(created_at) ORDER BY date(created_at) ASC"
        
        cursor.execute(query, params)
        
        rows = cursor.fetchall()
        conn.close()
        
        # 转换为字典列表
        result = []
        for row in rows:
            result.append({
                "date": row[0],
                "count": row[1]
            })
        
        return result
    
    def get_status_statistics(self) -> Dict[str, Any]:
        """获取审核状态分布"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # 审核通过数
        cursor.execute("SELECT COUNT(*) FROM experiments WHERE review_passed = 1")
        passed = cursor.fetchone()[0]
        
        # 审核未通过数
        cursor.execute("SELECT COUNT(*) FROM experiments WHERE review_passed = 0")
        failed = cursor.fetchone()[0]
        
        conn.close()
        
        return {
            "passed": passed,
            "failed": failed
        }
    
    def get_time_statistics(self) -> Optional[Dict[str, Any]]:
        """获取处理时间统计"""
        # 由于我们没有存储处理时间，返回None
        return None
    
    def create_processing_task(self, image_filename: str, image_bytes: bytes) -> str:
        """
        创建处理任务
        
        Args:
            image_filename: 图片文件名
            image_bytes: 图片二进制数据
            
        Returns:
            任务ID
        """
        import uuid
        task_id = str(uuid.uuid4())
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT INTO processing_tasks (task_id, image_filename, image_bytes)
            VALUES (?, ?, ?)
        """, (task_id, image_filename, image_bytes))
        
        conn.commit()
        conn.close()
        
        return task_id
    
    def update_task_status(self, task_id: str, status: str, **kwargs):
        """
        更新任务状态
        
        Args:
            task_id: 任务ID
            status: 任务状态 (pending, processing, completed, failed)
            kwargs: 其他可选字段: progress, current_step, error_message, experiment_id,
                     raw_json, reviewed_json, formatted_markdown, iteration_count, max_iterations, review_issues
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        update_fields = ["status = ?", "updated_at = CURRENT_TIMESTAMP"]
        params = [status]
        
        if 'progress' in kwargs:
            update_fields.append("progress = ?")
            params.append(kwargs['progress'])
        if 'current_step' in kwargs:
            update_fields.append("current_step = ?")
            params.append(kwargs['current_step'])
        if 'error_message' in kwargs:
            update_fields.append("error_message = ?")
            params.append(kwargs['error_message'])
        if 'experiment_id' in kwargs:
            update_fields.append("experiment_id = ?")
            params.append(kwargs['experiment_id'])
        if 'raw_json' in kwargs:
            update_fields.append("raw_json = ?")
            params.append(kwargs['raw_json'])
        if 'reviewed_json' in kwargs:
            update_fields.append("reviewed_json = ?")
            params.append(kwargs['reviewed_json'])
        if 'formatted_markdown' in kwargs:
            update_fields.append("formatted_markdown = ?")
            params.append(kwargs['formatted_markdown'])
        if 'iteration_count' in kwargs:
            update_fields.append("iteration_count = ?")
            params.append(kwargs['iteration_count'])
        if 'max_iterations' in kwargs:
            update_fields.append("max_iterations = ?")
            params.append(kwargs['max_iterations'])
        if 'review_issues' in kwargs:
            update_fields.append("review_issues = ?")
            params.append(kwargs['review_issues'])
        
        params.append(task_id)
        
        cursor.execute(
            f"UPDATE processing_tasks SET {', '.join(update_fields)} WHERE task_id = ?",
            params
        )
        
        conn.commit()
        conn.close()
    
    def get_task(self, task_id: str, include_image_bytes: bool = False) -> Optional[Dict[str, Any]]:
        """
        根据任务ID获取任务信息
        
        Args:
            task_id: 任务ID
            include_image_bytes: 是否包含图片二进制数据（用于审批入库）
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM processing_tasks WHERE task_id = ?", (task_id,))
        row = cursor.fetchone()
        conn.close()
        
        if row:
            task_dict = dict(row)
            if not include_image_bytes:
                task_dict.pop('image_bytes', None)
            return task_dict
        return None
    
    def get_pending_tasks(self, limit: int = 10) -> List[Dict[str, Any]]:
        """
        获取等待处理的任务
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute(
            "SELECT * FROM processing_tasks WHERE status = 'pending' ORDER BY created_at ASC LIMIT ?",
            (limit,)
        )
        
        rows = cursor.fetchall()
        conn.close()
        
        tasks = []
        for row in rows:
            task_dict = dict(row)
            task_dict.pop('image_bytes', None)
            tasks.append(task_dict)
        
        return tasks
    
    def get_tasks_needing_review(self) -> List[Dict[str, Any]]:
        """
        获取需要人工审核的任务（处理完成但未保存到数据库）
        条件：status = 'pending_review'（专门的待审批状态）
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT * FROM processing_tasks
            WHERE status = 'pending_review'
            ORDER BY created_at DESC
        """)
        
        rows = cursor.fetchall()
        conn.close()
        
        tasks = []
        for row in rows:
            task_dict = dict(row)
            task_dict.pop('image_bytes', None)
            tasks.append(task_dict)
        
        return tasks
    
    def delete_task(self, task_id: str) -> bool:
        """
        删除任务
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("DELETE FROM processing_tasks WHERE task_id = ?", (task_id,))
        deleted = cursor.rowcount > 0
        
        conn.commit()
        conn.close()
        
        return deleted
    
    def get_all_tasks(self, limit: int = 20) -> List[Dict[str, Any]]:
        """
        获取所有任务（用于显示任务列表）
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute(
            "SELECT * FROM processing_tasks ORDER BY created_at DESC LIMIT ?",
            (limit,)
        )
        
        rows = cursor.fetchall()
        conn.close()
        
        tasks = []
        for row in rows:
            task_dict = dict(row)
            task_dict.pop('image_bytes', None)
            tasks.append(task_dict)
        
        return tasks

    def get_processing_tasks(self, limit: int = 20) -> List[Dict[str, Any]]:
        """
        获取所有任务（待处理、处理中、待审批、已完成、失败）
        用于文件上传页面的任务列表显示
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute(
            "SELECT * FROM processing_tasks ORDER BY created_at DESC LIMIT ?",
            (limit,)
        )
        
        rows = cursor.fetchall()
        conn.close()
        
        tasks = []
        for row in rows:
            task_dict = dict(row)
            task_dict.pop('image_bytes', None)
            tasks.append(task_dict)
        
        return tasks
    
    def search_experiments_by_compound(
        self,
        compound_name: str,
        exclude_experiment_id: Optional[int] = None,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """
        根据化合物名称检索历史实验记录（用于 RAG 记忆回溯）
        
        Args:
            compound_name: 化合物名称（如 "FeSe", "MoS2"）
            exclude_experiment_id: 排除的实验ID（通常是当前正在处理的实验）
            limit: 返回记录数限制
            
        Returns:
            匹配的历史实验记录列表
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        # 构建查询：在多个字段中搜索化合物名称（包括关键参数文本）
        query = """
            SELECT * FROM experiments 
            WHERE (raw_json LIKE ? OR reviewed_json LIKE ? OR formatted_markdown LIKE ? OR key_params_text LIKE ?)
        """
        params = [f"%{compound_name}%", f"%{compound_name}%", f"%{compound_name}%", f"%{compound_name}%"]
        
        # 排除当前实验
        if exclude_experiment_id is not None:
            query += " AND id != ?"
            params.append(exclude_experiment_id)
        
        # 只返回审核通过的记录（更可靠）
        query += " AND review_passed = 1"
        
        # 按创建时间倒序排列
        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)
        
        cursor.execute(query, params)
        rows = cursor.fetchall()
        conn.close()
        
        return [self._row_to_dict(row) for row in rows]
    
    def search_similar_experiments(
        self,
        current_data: Dict[str, Any],
        exclude_experiment_id: Optional[int] = None,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """
        检索与当前实验相似的历史实验（基于化合物、方法、参数等）
        支持动态参数的语义匹配
        
        Args:
            current_data: 当前实验的 JSON 数据
            exclude_experiment_id: 排除的实验ID
            limit: 返回记录数限制
            
        Returns:
            相似的历史实验记录列表
        """
        # 提取当前实验的关键信息
        compounds = []
        method = None
        param_keywords = []  # 提取参数关键词用于增强搜索
        
        for exp in current_data.get("experiments", []):
            # 提取化合物名称（从配料表中）
            ingredients = exp.get("ingredients", [])
            for ing in ingredients:
                compound = ing.get("compound", "")
                role = ing.get("role", "")
                # 只提取原料和产物，排除输运剂
                if compound and compound not in ['-', 'null', ''] and 'Transport' not in role:
                    compounds.append(compound)
            
            # 提取实验方法
            meta = exp.get("meta", {})
            method = meta.get("method", "")
            
            # 提取参数关键词（支持动态参数）
            process = exp.get("process", {})
            if process.get("dynamic_params"):
                for param in process.get("dynamic_params", []):
                    param_name = param.get("name", "")
                    param_type = param.get("type", "")
                    # 提取温度、时间等关键参数的关键词
                    if param_type == "temperature":
                        param_keywords.append("temperature")
                        param_keywords.append("temp")
                    elif param_type == "time":
                        param_keywords.append("time")
                        param_keywords.append("duration")
                    if param_name:
                        param_keywords.append(param_name.lower())
            else:
                # 向后兼容：从固定参数中提取关键词
                if process.get("high_temp"):
                    param_keywords.append("temperature")
                    param_keywords.append("temp")
                if process.get("duration"):
                    param_keywords.append("time")
                    param_keywords.append("duration")
        
        # 如果没有找到化合物，返回空列表
        if not compounds:
            return []
        
        # 使用第一个主要化合物进行搜索（通常是产物）
        main_compound = compounds[0] if compounds else ""
        
        # 检索历史实验（基于化合物）
        similar_experiments = self.search_experiments_by_compound(
            main_compound,
            exclude_experiment_id=exclude_experiment_id,
            limit=limit * 2  # 先获取更多候选，然后进行语义筛选
        )
        
        # 如果有关键参数，进行语义匹配筛选
        if param_keywords and similar_experiments:
            scored_experiments = []
            for exp in similar_experiments:
                score = 0
                hist_json_str = exp.get("reviewed_json") or exp.get("raw_json", "{}")
                try:
                    hist_data = json.loads(hist_json_str)
                    if "experiments" not in hist_data:
                        hist_data = {"experiments": [hist_data]}
                    
                    for hist_exp_item in hist_data.get("experiments", []):
                        hist_process = hist_exp_item.get("process", {})
                        hist_text = json.dumps(hist_process, ensure_ascii=False).lower()
                        
                        # 计算匹配分数（参数关键词匹配）
                        for keyword in param_keywords:
                            if keyword.lower() in hist_text:
                                score += 1
                        
                        # 方法匹配加分
                        hist_meta = hist_exp_item.get("meta", {})
                        if method and hist_meta.get("method", "") == method:
                            score += 2
                        
                        break
                except:
                    pass
                
                if score > 0:
                    scored_experiments.append((score, exp))
            
            # 按分数排序，返回前 limit 个
            scored_experiments.sort(key=lambda x: x[0], reverse=True)
            similar_experiments = [exp for _, exp in scored_experiments[:limit]]
        
        return similar_experiments
    
    def _row_to_dict(self, row: sqlite3.Row) -> Dict[str, Any]:
        """将数据库行转换为字典"""
        result = dict(row)
        
        # 转换布尔值
        result['review_passed'] = bool(result['review_passed'])
        if result['review_passed_override'] is not None:
            result['review_passed_override'] = bool(result['review_passed_override'])
        
        # 解析JSON字段
        if result.get('review_issues'):
            try:
                result['review_issues'] = json.loads(result['review_issues'])
            except:
                result['review_issues'] = []
        else:
            result['review_issues'] = []
        
        return result


# 全局数据库实例（单例模式）
_db_instance: Optional[ExperimentDB] = None


def get_db() -> ExperimentDB:
    """获取数据库实例（单例）"""
    global _db_instance
    if _db_instance is None:
        _db_instance = ExperimentDB()
    return _db_instance

