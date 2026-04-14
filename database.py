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
        
        conn.commit()
        conn.close()
    
    def _calculate_image_hash(self, image_bytes: bytes) -> str:
        """计算图片的哈希值（用于去重）"""
        return hashlib.sha256(image_bytes).hexdigest()
    
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
        notes: Optional[str] = None
    ) -> int:
        """
        保存实验记录到数据库
        
        Returns:
            实验记录的ID
        """
        image_hash = self._calculate_image_hash(image_bytes)
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # 检查是否已存在相同图片的记录
        cursor.execute("SELECT id FROM experiments WHERE image_hash = ?", (image_hash,))
        existing = cursor.fetchone()
        
        if existing:
            # 更新现有记录
            experiment_id = existing[0]
            update_fields = []
            update_values = []
            
            # 只更新非空且有效的字段（避免用空值覆盖已有数据）
            if image_path is not None and image_path != "":
                update_fields.append("image_path = ?")
                update_values.append(image_path)
            if image_reference_path is not None and image_reference_path != "":
                update_fields.append("image_reference_path = ?")
                update_values.append(image_reference_path)
            # JSON 字段：只更新非空字符串（空字符串表示未处理，不应覆盖）
            if raw_json is not None and raw_json != "":
                update_fields.append("raw_json = ?")
                update_values.append(raw_json)
            if reviewed_json is not None and reviewed_json != "":
                update_fields.append("reviewed_json = ?")
                update_values.append(reviewed_json)
            if formatted_markdown is not None and formatted_markdown != "":
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
            # human_feedback: 空字符串表示无反馈，不应覆盖已有反馈
            if human_feedback is not None and human_feedback != "":
                update_fields.append("human_feedback = ?")
                update_values.append(human_feedback)
            if review_passed_override is not None:
                update_fields.append("review_passed_override = ?")
                update_values.append(1 if review_passed_override else 0)
            if notes is not None and notes != "":
                update_fields.append("notes = ?")
                update_values.append(notes)
            
            # 更新关键参数文本（如果 JSON 数据有更新）
            if reviewed_json is not None and reviewed_json != "":
                try:
                    reviewed_data = json.loads(reviewed_json)
                    key_params_text = self._extract_key_params_text(reviewed_data)
                    if key_params_text:
                        update_fields.append("key_params_text = ?")
                        update_values.append(key_params_text)
                except:
                    pass
            elif raw_json is not None and raw_json != "":
                try:
                    raw_data = json.loads(raw_json)
                    key_params_text = self._extract_key_params_text(raw_data)
                    if key_params_text:
                        update_fields.append("key_params_text = ?")
                        update_values.append(key_params_text)
                except:
                    pass
            
            # 总是更新 updated_at 时间戳
            update_fields.append("updated_at = CURRENT_TIMESTAMP")
            update_values.append(experiment_id)
            
            if len(update_fields) > 1:  # 至少有 updated_at 和一个其他字段
                query = f"UPDATE experiments SET {', '.join(update_fields)} WHERE id = ?"
                cursor.execute(query, update_values)
        else:
            # 提取关键参数文本（用于增强搜索）
            key_params_text = ""
            if reviewed_json:
                try:
                    reviewed_data = json.loads(reviewed_json)
                    key_params_text = self._extract_key_params_text(reviewed_data)
                except:
                    pass
            if not key_params_text and raw_json:
                try:
                    raw_data = json.loads(raw_json)
                    key_params_text = self._extract_key_params_text(raw_data)
                except:
                    pass
            
            # 插入新记录
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
        
        conn.commit()
        conn.close()
        
        return experiment_id
    
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

