"""
File Manager Tool
Read, write, list, and manage files within allowed directories
"""
import os
import shutil
import json
from pathlib import Path
from typing import Any, Dict, List, Optional
from datetime import datetime

from .base import BaseTool
from ..utils.config import get_config
from ..utils.logger import get_logger

logger = get_logger(__name__)


class FileManagerTool(BaseTool):
    """
    File System Operations Tool
    
    Provides safe file operations within a restricted base directory.
    Prevents path traversal attacks and restricts file types.
    """
    
    name = "file_manager"
    description = (
        "Read, write, create, list, and manage files. "
        "Can read file contents, write text/data to files, "
        "list directory contents, and perform basic file operations. "
        "All operations are restricted to a safe workspace directory."
    )
    
    def __init__(self):
        super().__init__()
        config = get_config().config.tools.file_manager
        self.base_path = Path(config.base_path)
        self.allowed_extensions = config.allowed_extensions
        
        # Ensure base path exists
        self.base_path.mkdir(parents=True, exist_ok=True)
    
    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "description": "File operation to perform",
                    "enum": [
                        "read",
                        "write",
                        "append",
                        "list",
                        "delete",
                        "exists",
                        "info",
                        "create_directory",
                        "search",
                    ],
                },
                "path": {
                    "type": "string",
                    "description": (
                        "Relative file/directory path from workspace root. "
                        "Examples: 'data.txt', 'notes/memo.md'"
                    ),
                },
                "content": {
                    "type": "string",
                    "description": "Content to write (for write/append actions)",
                },
                "pattern": {
                    "type": "string",
                    "description": "Search pattern (for search action)",
                },
            },
            "required": ["action", "path"],
        }
    
    async def execute(
        self,
        action: str,
        path: str,
        content: Optional[str] = None,
        pattern: Optional[str] = None,
        **kwargs,
    ) -> Dict[str, Any]:
        """
        Perform file operation
        
        Args:
            action: Operation type (read, write, append, list, etc.)
            path: File/directory path (relative to base)
            content: Content for write operations
            pattern: Pattern for search operations
            
        Returns:
            Dictionary with operation result
        """
        logger.info(f"File operation: {action} on {path}")
        
        # Resolve and validate path
        full_path = self._resolve_path(path)
        
        if full_path is None:
            return {
                "success": False,
                "error": f"Invalid or unsafe path: {path}",
                "action": action,
            }
        
        # Route to appropriate handler
        handlers = {
            "read": self._handle_read,
            "write": self._handle_write,
            "append": self._handle_append,
            "list": self._handle_list,
            "delete": self._handle_delete,
            "exists": self._handle_exists,
            "info": self._handle_info,
            "create_directory": self._handle_create_directory,
            "search": self._handle_search,
        }
        
        handler = handlers.get(action)
        if not handler:
            return {
                "success": False,
                "error": f"Unknown action: {action}. "
                         f"Available: {list(handlers.keys())}",
                "action": action,
            }
        
        try:
            result = await handler(full_path, content, pattern)
            result["action"] = action
            result["path"] = path
            return result
            
        except Exception as e:
            logger.error(f"File operation failed ({action}, {path}): {e}")
            return {
                "success": False,
                "error": str(e),
                "action": action,
                "path": path,
            }
    
    def _resolve_path(self, relative_path: str) -> Optional[Path]:
        """
        Resolve and validate path to prevent traversal attacks
        
        Args:
            relative_path: User-provided path
            
        Returns:
            Resolved absolute path, or None if unsafe
        """
        try:
            # Convert to Path object
            full_path = (self.base_path / relative_path).resolve()
            
            # Security check: must be within base_path
            if not str(full_path).startswith(str(self.base_path.resolve())):
                logger.warning(f"Path traversal attempt blocked: {relative_path}")
                return None
            
            return full_path
            
        except Exception as e:
            logger.error(f"Path resolution failed: {e}")
            return None
    
    def _check_extension(self, path: Path) -> bool:
        """Check if file extension is allowed"""
        if not self.allowed_extensions:
            return True
        
        return path.suffix.lower() in self.allowed_extensions
    
    async def _handle_read(
        self,
        path: Path,
        content: Optional[str],
        pattern: Optional[str],
    ) -> Dict:
        """Read file contents"""
        if not path.exists():
            return {"success": False, "error": "File not found"}
        
        if not path.is_file():
            return {"success": False, "error": "Path is not a file"}
        
        if not self._check_extension(path):
            return {
                "success": False,
                "error": f"File type {path.suffix} not allowed",
            }
        
        # Read based on file extension
        if path.suffix == '.json':
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return {"success": True, "content": data, "format": "json"}
        else:
            with open(path, 'r', encoding='utf-8') as f:
                content = f.read()
                return {
                    "success": True,
                    "content": content,
                    "size": len(content),
                    "lines": content.count('\n') + 1,
                }
    
    async def _handle_write(
        self,
        path: Path,
        content: Optional[str],
        pattern: Optional[str],
    ) -> Dict:
        """Write content to file (creates/overwrites)"""
        if content is None:
            return {"success": False, "error": "No content provided"}
        
        if not self._check_extension(path):
            return {
                "success": False,
                "error": f"File type {path.suffix} not allowed",
            }
        
        # Create parent directories if needed
        path.parent.mkdir(parents=True, exist_ok=True)
        
        # Write file
        with open(path, 'w', encoding='utf-8') as f:
            f.write(content)
        
        return {
            "success": True,
            "message": f"Written {len(content)} characters to {path.name}",
        }
    
    async def _handle_append(
        self,
        path: Path,
        content: Optional[str],
        pattern: Optional[str],
    ) -> Dict:
        """Append content to existing file"""
        if content is None:
            return {"success": False, "error": "No content provided"}
        
        if not self._check_extension(path):
            return {
                "success": False,
                "error": f"File type {path.suffix} not allowed",
            }
        
        mode = 'a' if path.exists() else 'w'
        
        with open(path, mode, encoding='utf-8') as f:
            f.write('\n' + content)
        
        return {
            "success": True,
            "message": f"Appended {len(content)} characters to {path.name}",
        }
    
    async def _handle_list(
        self,
        path: Path,
        content: Optional[str],
        pattern: Optional[str],
    ) -> Dict:
        """List directory contents"""
        if not path.exists():
            return {"success": False, "error": "Directory not found"}
        
        if not path.is_dir():
            return {"success": False, "error": "Path is not a directory"}
        
        items = []
        for item in path.iterdir():
            items.append({
                "name": item.name,
                "type": "directory" if item.is_dir() else "file",
                "size": item.stat().st_size if item.is_file() else None,
                "modified": datetime.fromtimestamp(
                    item.stat().st_mtime
                ).isoformat(),
            })
        
        # Sort: directories first, then by name
        items.sort(key=lambda x: (x['type'] != 'directory', x['name']))
        
        return {
            "success": True,
            "items": items,
            "count": len(items),
            "path": str(path.relative_to(self.base_path)),
        }
    
    async def _handle_delete(
        self,
        path: Path,
        content: Optional[str],
        pattern: Optional[str],
    ) -> Dict:
        """Delete file or empty directory"""
        if not path.exists():
            return {"success": False, "error": "Path not found"}
        
        try:
            if path.is_dir():
                shutil.rmtree(path)
                msg = f"Deleted directory: {path.name}"
            else:
                path.unlink()
                msg = f"Deleted file: {path.name}"
            
            return {"success": True, "message": msg}
            
        except Exception as e:
            return {"success": False, "error": f"Delete failed: {e}"}
    
    async def _handle_exists(
        self,
        path: Path,
        content: Optional[str],
        pattern: Optional[str],
    ) -> Dict:
        """Check if path exists"""
        return {
            "success": True,
            "exists": path.exists(),
            "is_file": path.is_file() if path.exists() else None,
            "is_directory": path.is_dir() if path.exists() else None,
        }
    
    async def _handle_info(
        self,
        path: Path,
        content: Optional[str],
        pattern: Optional[str],
    ) -> Dict:
        """Get detailed file/directory information"""
        if not path.exists():
            return {"success": False, "error": "Path not found"}
        
        stat = path.stat()
        
        info = {
            "success": True,
            "name": path.name,
            "type": "directory" if path.is_dir() else "file",
            "size": stat.st_size,
            "created": datetime.fromtimestamp(stat.st_ctime).isoformat(),
            "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
            "accessed": datetime.fromtimestamp(stat.st_atime).isoformat(),
        }
        
        if path.is_file():
            info["extension"] = path.suffix
        
        return info
    
    async def _handle_create_directory(
        self,
        path: Path,
        content: Optional[str],
        pattern: Optional[str],
    ) -> Dict:
        """Create new directory"""
        if path.exists():
            return {"success": False, "error": "Directory already exists"}
        
        path.mkdir(parents=True, exist_ok=True)
        
        return {
            "success": True,
            "message": f"Created directory: {path.name}",
        }
    
    async def _handle_search(
        self,
        path: Path,
        content: Optional[str],
        pattern: Optional[str],
    ) -> Dict:
        """Search for files matching pattern"""
        if not pattern:
            return {"success": False, "error": "No search pattern provided"}
        
        if not path.exists():
            return {"success": False, "error": "Directory not found"}
        
        matches = []
        search_pattern = pattern.lower()
        
        for item in path.rglob('*'):
            if item.is_file():
                if search_pattern in item.name.lower():
                    matches.append({
                        "name": item.name,
                        "path": str(item.relative_to(self.base_path)),
                        "size": item.stat().st_size,
                    })
        
        return {
            "success": True,
            "matches": matches,
            "count": len(matches),
            "pattern": pattern,
        }
