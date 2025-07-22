"""
Data Pipeline API 简化文件管理器

提供简单的文件列表、下载和上传功能，无压缩等复杂功能
"""

import os
from pathlib import Path
from typing import Dict, Any, List, BinaryIO, Union
from datetime import datetime
import tempfile
import shutil

import logging


class SimpleFileManager:
    """简化的文件管理器"""
    
    def __init__(self, base_output_dir: str = None):
        if base_output_dir is None:
            # 获取项目根目录的绝对路径
            from pathlib import Path
            project_root = Path(__file__).parent.parent.parent
            base_output_dir = str(project_root / "data_pipeline" / "training_data")
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
    
    def upload_table_list_file(self, task_id: str, file_obj: Union[BinaryIO, bytes], filename: str = None) -> Dict[str, Any]:
        """
        上传表清单文件到指定任务目录
        
        Args:
            task_id: 任务ID
            file_obj: 文件对象（Flask的FileStorage）或文件内容（字节流）
            filename: 原始文件名（可选，仅用于日志记录）
        
        Returns:
            Dict: 上传结果，包含filename、file_size、file_size_formatted、upload_time等
        
        Raises:
            ValueError: 文件验证失败（文件太大、空文件、格式错误等）
            FileNotFoundError: 任务目录不存在且无法创建
            IOError: 文件操作失败
        """
        try:
            # 获取配置
            from data_pipeline.config import SCHEMA_TOOLS_CONFIG
            upload_config = SCHEMA_TOOLS_CONFIG.get("file_upload", {})
            max_file_size_mb = upload_config.get("max_file_size_mb", 2)
            max_size = max_file_size_mb * 1024 * 1024  # 转换为字节
            target_filename = upload_config.get("target_filename", "table_list.txt")
            allowed_extensions = upload_config.get("allowed_extensions", ["txt"])
            
            # 处理文件对象或字节流
            if isinstance(file_obj, bytes):
                file_content = file_obj
                original_filename = filename or "uploaded_file.txt"
            else:
                # Flask FileStorage对象
                if hasattr(file_obj, 'filename') and file_obj.filename:
                    original_filename = file_obj.filename
                else:
                    original_filename = filename or "uploaded_file.txt"
                
                # 验证文件扩展名 - 修复：统一格式进行比较
                file_ext = Path(original_filename).suffix.lower().lstrip('.')
                if file_ext not in allowed_extensions:
                    raise ValueError(f"不支持的文件类型，仅支持: {', '.join(['.' + ext for ext in allowed_extensions])}")
                
                # 读取文件内容并验证大小
                file_content = b''
                chunk_size = 8192
                total_size = 0
                
                while True:
                    chunk = file_obj.read(chunk_size)
                    if not chunk:
                        break
                    
                    total_size += len(chunk)
                    if total_size > max_size:
                        raise ValueError(f"文件大小超过限制: {max_file_size_mb}MB")
                    
                    file_content += chunk
            
            # 验证文件内容为空
            if len(file_content) == 0:
                raise ValueError("文件为空，请选择有效的表清单文件")
            
            # 验证文件内容（简单检查是否为文本文件）
            self._validate_table_list_content_simple(file_content)
            
            # 确保任务目录存在
            task_dir = self.get_task_directory(task_id)
            if not task_dir.exists():
                task_dir.mkdir(parents=True, exist_ok=True)
                self.logger.info(f"创建任务目录: {task_dir}")
            
            # 确定目标文件路径
            target_file_path = task_dir / target_filename
            
            # 保存文件
            with open(target_file_path, 'wb') as f:
                f.write(file_content)
            
            # 验证文件是否成功写入
            if not target_file_path.exists():
                raise IOError("文件保存失败")
            
            # 获取文件信息
            file_stat = target_file_path.stat()
            upload_time = datetime.fromtimestamp(file_stat.st_mtime)
            
            self.logger.info(f"成功上传表清单文件到任务 {task_id}: {target_file_path}")
            
            return {
                "filename": target_filename,
                "original_filename": original_filename,
                "file_size": file_stat.st_size,
                "file_size_formatted": self._format_file_size(file_stat.st_size),
                "upload_time": upload_time,
                "target_path": str(target_file_path)
            }
            
        except Exception as e:
            self.logger.error(f"上传表清单文件失败: {e}")
            raise
    
    def _validate_table_list_content_simple(self, file_content: bytes) -> None:
        """
        简单验证表清单文件内容
        
        Args:
            file_content: 文件内容（字节流）
            
        Raises:
            ValueError: 文件内容验证失败
        """
        try:
            # 尝试解码文件内容
            try:
                content = file_content.decode('utf-8')
            except UnicodeDecodeError:
                try:
                    content = file_content.decode('gbk')
                except UnicodeDecodeError:
                    raise ValueError("文件编码错误，请确保文件为UTF-8或GBK格式")
            
            # 检查文件是否为空
            if not content.strip():
                raise ValueError("表清单文件为空")
            
            # 解析表名，支持换行符和逗号分隔
            all_tables = []
            lines = content.split('\n')
            
            for line in lines:
                line = line.strip()
                # 跳过空行和注释行
                if not line or line.startswith('#') or line.startswith('--'):
                    continue
                
                # 如果行内包含逗号，按逗号分割；否则整行作为一个表名
                if ',' in line:
                    tables_in_line = [t.strip() for t in line.split(',') if t.strip()]
                else:
                    tables_in_line = [line]
                
                all_tables.extend(tables_in_line)
            
            if not all_tables:
                raise ValueError("表清单文件不包含有效的表名")
            
            # 验证表名格式（避免SQL注入等安全问题）
            import re
            table_name_pattern = re.compile(r'^[a-zA-Z_][a-zA-Z0-9_]*(\.[a-zA-Z_][a-zA-Z0-9_]*)?$')
            invalid_tables = []
            
            # 只检查前10个表名以避免过度验证
            for table_name in all_tables[:10]:
                if not table_name_pattern.match(table_name):
                    invalid_tables.append(table_name)
            
            if invalid_tables:
                raise ValueError(f"表清单文件包含无效的表名格式: {', '.join(invalid_tables[:3])}")
                
        except ValueError:
            raise
        except Exception as e:
            raise ValueError(f"文件内容验证失败: {str(e)}")
    
    def _validate_table_list_content(self, file_content: bytes, config: Dict[str, Any]) -> Dict[str, Any]:
        """
        验证表清单文件内容
        
        Args:
            file_content: 文件内容（字节流）
            config: 文件上传配置
        
        Returns:
            Dict: 验证结果
        """
        try:
            # 解码文件内容
            encoding = config.get("encoding", "utf-8")
            try:
                content = file_content.decode(encoding)
            except UnicodeDecodeError:
                # 尝试其他编码
                for fallback_encoding in ["gbk", "latin1"]:
                    try:
                        content = file_content.decode(fallback_encoding)
                        self.logger.warning(f"文件编码检测为 {fallback_encoding}，建议使用 UTF-8")
                        break
                    except UnicodeDecodeError:
                        continue
                else:
                    return {
                        "valid": False,
                        "error": f"无法解码文件内容，请确保文件编码为 {encoding}"
                    }
            
            # 分析文件内容，支持换行符和逗号分隔
            lines = content.splitlines()
            total_lines = len(lines)
            
            # 过滤空行和注释行，解析表名
            valid_lines = []
            comment_lines = 0
            empty_lines = 0
            
            for line_num, line in enumerate(lines, 1):
                stripped = line.strip()
                if not stripped:
                    empty_lines += 1
                elif stripped.startswith('#'):
                    comment_lines += 1
                else:
                    # 如果行内包含逗号，按逗号分割；否则整行作为一个表名
                    if ',' in stripped:
                        tables_in_line = [t.strip() for t in stripped.split(',') if t.strip()]
                    else:
                        tables_in_line = [stripped]
                    
                    # 验证每个表名格式
                    for table_name in tables_in_line:
                        if self._is_valid_table_name(table_name):
                            valid_lines.append(table_name)
                        else:
                            return {
                                "valid": False,
                                "error": f"第 {line_num} 行包含无效的表名: {table_name}",
                                "details": {
                                    "line_number": line_num,
                                    "invalid_content": table_name
                            }
                        }
            
            # 检查有效行数
            min_lines = config.get("min_lines", 1)
            max_lines = config.get("max_lines", 1000)
            
            if len(valid_lines) < min_lines:
                return {
                    "valid": False,
                    "error": f"文件至少需要包含 {min_lines} 个有效表名，当前只有 {len(valid_lines)} 个",
                    "details": {
                        "valid_tables": len(valid_lines),
                        "min_required": min_lines
                    }
                }
            
            if len(valid_lines) > max_lines:
                return {
                    "valid": False,
                    "error": f"文件包含的表名数量超过限制，最多允许 {max_lines} 个，当前有 {len(valid_lines)} 个",
                    "details": {
                        "valid_tables": len(valid_lines),
                        "max_allowed": max_lines
                    }
                }
            
            return {
                "valid": True,
                "details": {
                    "total_lines": total_lines,
                    "empty_lines": empty_lines,
                    "comment_lines": comment_lines,
                    "valid_tables": len(valid_lines),
                    "table_names": valid_lines[:10]  # 只返回前10个作为预览
                }
            }
            
        except Exception as e:
            return {
                "valid": False,
                "error": f"文件内容验证失败: {str(e)}"
            }
    
    def _is_valid_table_name(self, table_name: str) -> bool:
        """
        验证表名格式是否有效
        
        Args:
            table_name: 表名
        
        Returns:
            bool: 是否有效
        """
        import re
        
        # 基本的表名格式检查
        # 支持: table_name, schema.table_name
        pattern = r'^[a-zA-Z_][a-zA-Z0-9_]*(\.[a-zA-Z_][a-zA-Z0-9_]*)?$'
        return bool(re.match(pattern, table_name))
    
    def get_table_list_file_info(self, task_id: str) -> Dict[str, Any]:
        """
        获取任务的表清单文件信息
        
        Args:
            task_id: 任务ID
        
        Returns:
            Dict: 文件信息或None
        """
        try:
            from data_pipeline.config import SCHEMA_TOOLS_CONFIG
            upload_config = SCHEMA_TOOLS_CONFIG.get("file_upload", {})
            target_filename = upload_config.get("target_filename", "table_list.txt")
            
            file_path = self.get_file_path(task_id, target_filename)
            
            if not file_path.exists():
                return {
                    "exists": False,
                    "file_name": target_filename,
                    "expected_path": str(file_path)
                }
            
            file_stat = file_path.stat()
            
            # 尝试读取文件内容进行分析，支持换行符和逗号分隔
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                    lines = content.splitlines()
                    valid_tables = []
                    
                    for line in lines:
                        line = line.strip()
                        # 跳过空行和注释行
                        if not line or line.startswith('#') or line.startswith('--'):
                            continue
                        
                        # 如果行内包含逗号，按逗号分割；否则整行作为一个表名
                        if ',' in line:
                            tables_in_line = [t.strip() for t in line.split(',') if t.strip()]
                        else:
                            tables_in_line = [line]
                        
                        valid_tables.extend(tables_in_line)
            except Exception:
                valid_tables = []
            
            return {
                "exists": True,
                "file_name": target_filename,
                "file_path": str(file_path),
                "file_size": file_stat.st_size,
                "file_size_formatted": self._format_file_size(file_stat.st_size),
                "uploaded_at": datetime.fromtimestamp(file_stat.st_mtime).isoformat(),
                "created_at": datetime.fromtimestamp(file_stat.st_ctime).isoformat(),
                "table_count": len(valid_tables),
                "table_names": valid_tables,  # 新增：返回解析出的表名列表
                "is_readable": os.access(file_path, os.R_OK)
            }
            
        except Exception as e:
            self.logger.error(f"获取表清单文件信息失败: {e}")
            return {
                "exists": False,
                "error": str(e)
            }
    
    def create_table_list_from_names(self, task_id: str, table_names: List[str]) -> Dict[str, Any]:
        """
        从表名列表创建table_list.txt文件
        
        Args:
            task_id: 任务ID
            table_names: 表名列表
        
        Returns:
            Dict: 创建结果，包含filename、table_count、file_size等信息
        
        Raises:
            ValueError: 表名验证失败（表名格式错误、空列表等）
            IOError: 文件操作失败
        """
        try:
            # 获取配置
            from data_pipeline.config import SCHEMA_TOOLS_CONFIG
            upload_config = SCHEMA_TOOLS_CONFIG.get("file_upload", {})
            target_filename = upload_config.get("target_filename", "table_list.txt")
            max_lines = upload_config.get("max_lines", 1000)
            min_lines = upload_config.get("min_lines", 1)
            
            # 验证输入
            if not table_names:
                raise ValueError("表名列表不能为空")
            
            if not isinstance(table_names, list):
                raise ValueError("表名必须是列表格式")
            
            # 处理和验证表名
            processed_tables = self._process_table_names(table_names)
            
            # 验证表名数量
            if len(processed_tables) < min_lines:
                raise ValueError(f"表名数量不能少于 {min_lines} 个")
            
            if len(processed_tables) > max_lines:
                raise ValueError(f"表名数量不能超过 {max_lines} 个")
            
            # 确保任务目录存在
            task_dir = self.get_task_directory(task_id)
            if not task_dir.exists():
                task_dir.mkdir(parents=True, exist_ok=True)
                self.logger.info(f"创建任务目录: {task_dir}")
            
            # 确定目标文件路径
            target_file_path = task_dir / target_filename
            
            # 生成文件内容
            file_content = self._generate_table_list_content(processed_tables)
            
            # 写入文件（覆盖模式）
            with open(target_file_path, 'w', encoding='utf-8') as f:
                f.write(file_content)
            
            # 验证文件是否成功写入
            if not target_file_path.exists():
                raise IOError("文件创建失败")
            
            # 获取文件信息
            file_stat = target_file_path.stat()
            created_time = datetime.fromtimestamp(file_stat.st_mtime)
            
            self.logger.info(f"成功创建表清单文件到任务 {task_id}: {target_file_path} ({len(processed_tables)} 个表)")
            
            return {
                "filename": target_filename,
                "table_count": len(processed_tables),
                "unique_table_count": len(set(processed_tables)),
                "file_size": file_stat.st_size,
                "file_size_formatted": self._format_file_size(file_stat.st_size),
                "created_time": created_time,
                "target_path": str(target_file_path)
            }
            
        except Exception as e:
            self.logger.error(f"创建表清单文件失败: {e}")
            raise
    
    def _process_table_names(self, table_names: List[str]) -> List[str]:
        """
        处理表名列表：验证格式、去重、排序
        
        Args:
            table_names: 原始表名列表
            
        Returns:
            List[str]: 处理后的表名列表
            
        Raises:
            ValueError: 表名格式验证失败
        """
        processed_tables = []
        invalid_tables = []
        
        for table_name in table_names:
            # 去除空白
            table_name = table_name.strip()
            
            # 跳过空字符串
            if not table_name:
                continue
            
            # 跳过注释行
            if table_name.startswith('#') or table_name.startswith('--'):
                continue
            
            # 验证表名格式
            if self._is_valid_table_name(table_name):
                processed_tables.append(table_name)
            else:
                invalid_tables.append(table_name)
        
        # 如果有无效表名，抛出异常
        if invalid_tables:
            raise ValueError(f"包含无效的表名格式: {', '.join(invalid_tables[:5])}")
        
        # 去重并保持顺序
        seen = set()
        unique_tables = []
        for table in processed_tables:
            if table not in seen:
                seen.add(table)
                unique_tables.append(table)
        
        return unique_tables
    
    def _generate_table_list_content(self, table_names: List[str]) -> str:
        """
        生成table_list.txt文件内容
        
        Args:
            table_names: 表名列表
            
        Returns:
            str: 文件内容
        """
        lines = []
        
        # 添加文件头注释
        lines.append("# 表清单文件")
        lines.append(f"# 生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append(f"# 表数量: {len(table_names)}")
        lines.append("")
        
        # 添加表名
        for table_name in table_names:
            lines.append(table_name)
        
        # 确保文件以换行符结束
        if lines and not lines[-1] == "":
            lines.append("")
        
        return "\n".join(lines)
    
    # ==================== 文件上传功能 ====================
    
    # 支持的文件类型
    ALLOWED_EXTENSIONS = {'.ddl', '.md', '.txt', '.json', '.sql', '.csv'}
    MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB
    
    def upload_file_to_task(self, task_id: str, file_stream, filename: str, overwrite_mode: str = "backup") -> Dict[str, Any]:
        """
        上传文件到指定任务目录
        
        Args:
            task_id: 任务ID
            file_stream: 文件流对象
            filename: 文件名
            overwrite_mode: 重名处理模式 ("backup", "replace", "skip")
        
        Returns:
            Dict: 上传结果
        """
        try:
            # 1. 验证任务存在
            task_dir = self.get_task_directory(task_id)
            if not task_dir.exists():
                # 创建任务目录
                task_dir.mkdir(parents=True, exist_ok=True)
                self.logger.info(f"创建任务目录: {task_dir}")
            
            # 2. 验证文件
            validation_result = self.validate_file_upload(filename, file_stream)
            if not validation_result["valid"]:
                raise ValueError(validation_result["error"])
            
            # 3. 检查目标文件路径
            target_file_path = task_dir / filename
            
            # 4. 处理重名文件
            backup_info = None
            if target_file_path.exists():
                if overwrite_mode == "skip":
                    return {
                        "success": True,
                        "skipped": True,
                        "message": f"文件已存在，跳过上传: {filename}",
                        "task_id": task_id,
                        "uploaded_file": {
                            "filename": filename,
                            "existed": True,
                            "action": "skipped"
                        }
                    }
                elif overwrite_mode == "backup":
                    backup_info = self.create_backup_file(target_file_path)
                # replace 模式不需要特殊处理，直接覆盖
            
            # 5. 保存新文件
            file_content = file_stream.read()
            with open(target_file_path, 'wb') as f:
                f.write(file_content)
            
            # 6. 获取文件信息
            file_stat = target_file_path.stat()
            upload_time = datetime.fromtimestamp(file_stat.st_mtime)
            
            self.logger.info(f"文件上传成功: {task_id}/{filename}")
            
            # 7. 构建响应
            result = {
                "success": True,
                "task_id": task_id,
                "uploaded_file": {
                    "filename": filename,
                    "size": file_stat.st_size,
                    "size_formatted": self._format_file_size(file_stat.st_size),
                    "uploaded_at": upload_time.isoformat(),
                    "overwrite_mode": overwrite_mode
                }
            }
            
            if backup_info:
                result["backup_info"] = backup_info
            
            return result
            
        except Exception as e:
            self.logger.error(f"文件上传失败: {e}")
            raise
    
    def validate_file_upload(self, filename: str, file_stream) -> Dict[str, Any]:
        """
        验证上传文件的合法性
        
        Args:
            filename: 文件名
            file_stream: 文件流
        
        Returns:
            Dict: 验证结果 {"valid": bool, "error": str}
        """
        try:
            # 1. 检查文件名安全性
            if not self._is_safe_filename(filename):
                return {
                    "valid": False,
                    "error": f"文件名包含不安全字符: {filename}"
                }
            
            # 2. 检查文件扩展名
            file_ext = Path(filename).suffix.lower()
            if file_ext not in self.ALLOWED_EXTENSIONS:
                return {
                    "valid": False,
                    "error": f"不支持的文件类型: {file_ext}，允许的类型: {', '.join(self.ALLOWED_EXTENSIONS)}"
                }
            
            # 3. 检查文件大小
            if hasattr(file_stream, 'seek') and hasattr(file_stream, 'tell'):
                # 获取文件大小
                current_pos = file_stream.tell()
                file_stream.seek(0, 2)  # 移动到文件末尾
                file_size = file_stream.tell()
                file_stream.seek(current_pos)  # 恢复原位置
                
                if file_size > self.MAX_FILE_SIZE:
                    return {
                        "valid": False,
                        "error": f"文件大小超出限制: {self._format_file_size(file_size)}，最大允许: {self._format_file_size(self.MAX_FILE_SIZE)}"
                    }
                
                if file_size == 0:
                    return {
                        "valid": False,
                        "error": "文件为空"
                    }
            
            return {"valid": True}
            
        except Exception as e:
            return {
                "valid": False,
                "error": f"文件验证失败: {str(e)}"
            }
    
    def _is_safe_filename(self, filename: str) -> bool:
        """检查文件名是否安全"""
        import re
        
        # 禁止的字符和模式
        dangerous_patterns = [
            r'\.\.',  # 路径遍历
            r'[<>:"|?*]',  # Windows 禁止字符
            r'[\x00-\x1f]',  # 控制字符
        ]
        
        # 禁止的文件名
        dangerous_names = [
            'CON', 'PRN', 'AUX', 'NUL',
            'COM1', 'COM2', 'COM3', 'COM4', 'COM5', 'COM6', 'COM7', 'COM8', 'COM9',
            'LPT1', 'LPT2', 'LPT3', 'LPT4', 'LPT5', 'LPT6', 'LPT7', 'LPT8', 'LPT9'
        ]
        
        # 检查危险模式
        for pattern in dangerous_patterns:
            if re.search(pattern, filename):
                return False
        
        # 检查危险文件名
        name_without_ext = Path(filename).stem.upper()
        if name_without_ext in dangerous_names:
            return False
        
        # 检查长度
        if len(filename) > 255:
            return False
        
        return True
    
    def find_next_backup_version(self, file_path: Path) -> int:
        """
        查找下一个可用的备份版本号
        
        Args:
            file_path: 原文件路径
        
        Returns:
            int: 下一个可用的版本号
        """
        version = 1
        while True:
            backup_path = Path(str(file_path) + f"_bak{version}")
            if not backup_path.exists():
                return version
            version += 1
            # 防止无限循环
            if version > 1000:
                raise ValueError("备份版本号超出限制")
    
    def create_backup_file(self, original_path: Path) -> Dict[str, Any]:
        """
        创建备份文件
        
        Args:
            original_path: 原文件路径
        
        Returns:
            Dict: 备份信息
        """
        try:
            # 找到下一个可用的版本号
            version = self.find_next_backup_version(original_path)
            backup_path = Path(str(original_path) + f"_bak{version}")
            
            # 创建备份
            shutil.copy2(original_path, backup_path)
            
            backup_time = datetime.now()
            
            self.logger.info(f"创建备份文件: {backup_path}")
            
            return {
                "had_existing_file": True,
                "backup_filename": backup_path.name,
                "backup_version": version,
                "backup_created_at": backup_time.isoformat()
            }
            
        except Exception as e:
            self.logger.error(f"创建备份文件失败: {e}")
            raise