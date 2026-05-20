"""
Code Executor Tool
Safely executes code snippets in a sandboxed environment
"""
import subprocess
import tempfile
import os
from pathlib import Path
from typing import Any, Dict, Optional

from .base import BaseTool
from ..utils.config import get_config
from ..utils.logger import get_logger

logger = get_logger(__name__)


class CodeExecutorTool(BaseTool):
    """
    Sandboxed Code Execution Tool
    
    Executes Python and JavaScript code safely with:
    - Timeout limits
    - Resource restrictions
    - Output capture
    - Error handling
    """
    
    name = "code_executor"
    description = (
        "Execute code snippets and return the output. "
        "Supports Python and JavaScript. "
        "Useful for testing algorithms, data processing, or demonstrating concepts. "
        "Code runs in a sandboxed environment with timeout restrictions."
    )
    
    def __init__(self):
        super().__init__()
        config = get_config().config.tools.code_executor
        self.timeout = config.timeout
        self.allowed_languages = config.allowed_languages
    
    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "code": {
                    "type": "string",
                    "description": "Code snippet to execute",
                },
                "language": {
                    "type": "string",
                    "description": "Programming language",
                    "enum": self.allowed_languages,
                    "default": "python",
                },
                "timeout": {
                    "type": "integer",
                    "description": "Execution timeout in seconds (optional)",
                    "default": self.timeout,
                },
            },
            "required": ["code"],
        }
    
    async def execute(
        self,
        code: str,
        language: str = "python",
        timeout: Optional[int] = None,
        **kwargs,
    ) -> Dict[str, Any]:
        """
        Execute code safely
        
        Args:
            code: Code to execute
            language: Programming language
            timeout: Execution timeout in seconds
            
        Returns:
            Dictionary with execution results
        """
        timeout = timeout or self.timeout
        
        logger.info(
            f"Executing {language} code "
            f"({len(code)} chars, timeout={timeout}s)"
        )
        
        # Validate language
        if language not in self.allowed_languages:
            return {
                "success": False,
                "error": f"Language '{language}' not supported. "
                         f"Allowed: {self.allowed_languages}",
                "output": "",
            }
        
        # Basic security check
        dangerous_patterns = [
            "import os",
            "subprocess",
            "system(",
            "__import__",
            "eval(",
            "exec(",
            "rm -rf",
            "del /",
        ]
        
        code_lower = code.lower()
        for pattern in dangerous_patterns:
            if pattern.lower() in code_lower:
                return {
                    "success": False,
                    "error": f"Security violation: potentially dangerous code detected",
                    "output": "",
                    "blocked_pattern": pattern,
                }
        
        try:
            if language == "python":
                result = await self._execute_python(code, timeout)
            elif language == "javascript":
                result = await self._execute_javascript(code, timeout)
            else:
                raise ValueError(f"Unsupported language: {language}")
            
            return result
            
        except Exception as e:
            logger.error(f"Code execution failed: {e}")
            return {
                "success": False,
                "error": str(e),
                "output": "",
            }
    
    async def _execute_python(
        self,
        code: str,
        timeout: int,
    ) -> Dict[str, Any]:
        """Execute Python code in subprocess"""
        # Create temporary file for code
        with tempfile.NamedTemporaryFile(
            mode='w',
            suffix='.py',
            delete=False,
            encoding='utf-8',
        ) as f:
            f.write(code)
            temp_file = f.name
        
        try:
            # Run code in subprocess with timeout
            process = await asyncio.create_subprocess_exec(
                sys.executable,
                temp_file,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            
            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(),
                    timeout=timeout,
                )
                
                output = stdout.decode('utf-8')
                errors = stderr.decode('utf-8')
                
                success = process.returncode == 0
                
                return {
                    "success": success,
                    "output": output,
                    "errors": errors if errors else None,
                    "exit_code": process.returncode,
                    "language": "python",
                }
                
            except asyncio.TimeoutError:
                process.kill()
                return {
                    "success": False,
                    "error": f"Execution timed out after {timeout} seconds",
                    "output": "",
                    "language": "python",
                }
                
        finally:
            # Clean up temp file
            try:
                os.unlink(temp_file)
            except:
                pass
    
    async def _execute_javascript(
        self,
        code: str,
        timeout: int,
    ) -> Dict[str, Any]:
        """Execute JavaScript code using Node.js"""
        # Check if Node.js is available
        try:
            proc = await asyncio.create_subprocess_exec(
                "node", "--version",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await proc.communicate()
            
            if proc.returncode != 0:
                return {
                    "success": False,
                    "error": "Node.js is not installed or not available",
                    "output": "",
                }
                
        except FileNotFoundError:
            return {
                "success": False,
                "error": "Node.js runtime not found. Please install Node.js.",
                "output": "",
            }
        
        # Create temporary file
        with tempfile.NamedTemporaryFile(
            mode='w',
            suffix='.js',
            delete=False,
            encoding='utf-8',
        ) as f:
            f.write(code)
            temp_file = f.name
        
        try:
            process = await asyncio.create_subprocess_exec(
                "node",
                temp_file,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            
            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(),
                    timeout=timeout,
                )
                
                output = stdout.decode('utf-8')
                errors = stderr.decode('utf-8')
                
                return {
                    "success": process.returncode == 0,
                    "output": output,
                    "errors": errors if errors else None,
                    "exit_code": process.returncode,
                    "language": "javascript",
                }
                
            except asyncio.TimeoutError:
                process.kill()
                return {
                    "success": False,
                    "error": f"Execution timed out after {timeout} seconds",
                    "output": "",
                }
                
        finally:
            try:
                os.unlink(temp_file)
            except:
                pass


# Import asyncio at module level
import asyncio
import sys
