"""
Data Pipeline API 简化文件管理器

提供简单的文件列表和下载功能，无压缩等复杂功能
"""

import os
from pathlib import Path
from typing import Dict, Any, List
from datetime import datetime

import logging


class SimpleFileManager:
    """简化的文件管理器"""
    
    def __init__(self, base_output_dir: str = "./data_pipeline/training_data/"):
        """
        初始化文件管理器
        
        Args:
            base_output_dir: 基础输出目录
        """
        self.base_output_dir = Path(base_output_dir)
        # 使用简单的控制台日志，不使用文件日志
        self.logger = logging.getLogger("SimpleFileManager")
        self.logger.setLevel(logging.INFO)
        
        # 确保基础目录存在
        self.base_output_dir.mkdir(parents=True, exist_ok=True)
    
    def get_task_directory(self, task_id: str) -> Path:
        """获取任务目录路径"""
        return self.base_output_dir / task_id
    
    def create_task_directory(self, task_id: str) -> bool:
        """创建任务目录"""
        try:
            task_dir = self.get_task_directory(task_id)
            task_dir.mkdir(parents=True, exist_ok=True)
            self.logger.info(f"任务目录已创建: {task_dir}")
            return True
        except Exception as e:
            self.logger.error(f"创建任务目录失败: {e}")
            return False
    
    def get_task_files(self, task_id: str) -> List[Dict[str, Any]]:
        """获取任务目录下的所有文件信息"""
        try:
            task_dir = self.get_task_directory(task_id)
            if not task_dir.exists():
                return []
            
            files_info = []
            for file_path in task_dir.iterdir():
                if file_path.is_file():
                    file_info = self._get_file_info(file_path)
                    files_info.append(file_info)
            
            # 按修改时间排序（最新的在前）
            files_info.sort(key=lambda x: x['modified_at'], reverse=True)
            return files_info
            
        except Exception as e:
            self.logger.error(f"获取任务文件失败: {e}")
            return []
    
    def _get_file_info(self, file_path: Path) -> Dict[str, Any]:
        """获取单个文件的基本信息"""
        try:
            stat = file_path.stat()
            
            return {
                "file_name": file_path.name,
                "file_path": str(file_path),
                "file_type": self._determine_file_type(file_path),
                "file_size": stat.st_size,
                "file_size_formatted": self._format_file_size(stat.st_size),
                "created_at": datetime.fromtimestamp(stat.st_ctime),
                "modified_at": datetime.fromtimestamp(stat.st_mtime),
                "is_readable": os.access(file_path, os.R_OK)
            }
            
        except Exception as e:
            self.logger.error(f"获取文件信息失败: {e}")
            return {
                "file_name": file_path.name,
                "file_path": str(file_path),
                "file_type": "unknown",
                "file_size": 0,
                "file_size_formatted": "0 B",
                "created_at": datetime.now(),
                "modified_at": datetime.now(),
                "is_readable": False
            }
    
    def _determine_file_type(self, file_path: Path) -> str:
        """根据文件扩展名确定文件类型"""
        suffix = file_path.suffix.lower()
        
        type_mapping = {
            '.ddl': 'ddl',
            '.sql': 'sql',
            '.md': 'markdown',
            '.markdown': 'markdown',
            '.json': 'json',
            '.txt': 'text',
            '.log': 'log'
        }
        
        return type_mapping.get(suffix, 'other')
    
    def _format_file_size(self, size_bytes: int) -> str:
        """格式化文件大小显示"""
        if size_bytes == 0:
            return "0 B"
        
        size_names = ["B", "KB", "MB", "GB"]
        i = 0
        size = float(size_bytes)
        
        while size >= 1024.0 and i < len(size_names) - 1:
            size /= 1024.0
            i += 1
        
        return f"{size:.1f} {size_names[i]}"
    
    def get_file_path(self, task_id: str, file_name: str) -> Path:
        """获取文件的完整路径"""
        task_dir = self.get_task_directory(task_id)
        return task_dir / file_name
    
    def file_exists(self, task_id: str, file_name: str) -> bool:
        """检查文件是否存在"""
        file_path = self.get_file_path(task_id, file_name)
        return file_path.exists() and file_path.is_file()
    
    def is_file_safe(self, task_id: str, file_name: str) -> bool:
        """检查文件路径是否安全（防止路径遍历攻击）"""
        try:
            task_dir = self.get_task_directory(task_id)
            file_path = task_dir / file_name
            
            # 确保文件在任务目录内
            file_path.resolve().relative_to(task_dir.resolve())
            return True
        except ValueError:
            return False
    
    def get_directory_info(self, task_id: str) -> Dict[str, Any]:
        """获取任务目录信息"""
        try:
            task_dir = self.get_task_directory(task_id)
            
            if not task_dir.exists():
                return {
                    "exists": False,
                    "directory_path": str(task_dir),
                    "total_files": 0,
                    "total_size": 0,
                    "total_size_formatted": "0 B"
                }
            
            files = self.get_task_files(task_id)
            total_size = sum(file_info['file_size'] for file_info in files)
            
            return {
                "exists": True,
                "directory_path": str(task_dir),
                "total_files": len(files),
                "total_size": total_size,
                "total_size_formatted": self._format_file_size(total_size)
            }
            
        except Exception as e:
            self.logger.error(f"获取目录信息失败: {e}")
            return {
                "exists": False,
                "directory_path": str(self.get_task_directory(task_id)),
                "total_files": 0,
                "total_size": 0,
                "total_size_formatted": "0 B"
            }