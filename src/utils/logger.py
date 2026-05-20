"""
Structured Logging System for DeepSeek Agent
Features:
- Console and file logging with rotation
- Colored output for better readability
- Structured JSON logging support
- Performance tracking
"""
import sys
import logging
import json
from pathlib import Path
from typing import Optional
from datetime import datetime
from logging.handlers import RotatingFileHandler
from rich.console import Console
from rich.logging import RichHandler


class JSONFormatter(logging.Formatter):
    """JSON formatter for structured logging"""
    
    def format(self, record: logging.LogRecord) -> str:
        log_data = {
            "timestamp": datetime.utcnow().isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }
        
        # Add extra fields if present
        if hasattr(record, "extra_data"):
            log_data["data"] = record.extra_data
        
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)
        
        return json.dumps(log_data, ensure_ascii=False)


class AgentLogger:
    """
    Custom Logger with enhanced features
    
    Usage:
        logger = get_logger(__name__)
        logger.info("Processing request", extra={"request_id": "123"})
    """
    
    _loggers: dict[str, logging.Logger] = {}
    _initialized: bool = False
    
    @classmethod
    def setup(
        cls,
        log_level: str = "INFO",
        log_file: Optional[str] = None,
        log_format: Optional[str] = None,
        max_file_size: int = 10485760,
        backup_count: int = 5,
        use_json: bool = False,
    ) -> None:
        """
        Setup the root logger configuration
        
        Args:
            log_level: Logging level (DEBUG, INFO, WARNING, ERROR)
            log_file: Path to log file (optional)
            log_format: Custom format string
            max_file_size: Max size of each log file in bytes
            backup_count: Number of backup files to keep
            use_json: Use JSON formatting for logs
        """
        if cls._initialized:
            return
        
        cls._initialized = True
        
        # Get or create root logger
        root_logger = logging.getLogger()
        root_logger.setLevel(getattr(logging, log_level.upper()))
        
        # Clear existing handlers to avoid duplicates
        root_logger.handlers.clear()
        
        # Default format
        if not log_format:
            log_format = (
                "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
            )
        
        # Console handler with Rich
        console_handler = RichHandler(
            console=Console(),
            show_time=True,
            show_path=True,
            markup=True,
            rich_tracebacks=True,
        )
        console_handler.setLevel(getattr(logging, log_level.upper()))
        root_logger.addHandler(console_handler)
        
        # File handler (if specified)
        if log_file:
            log_path = Path(log_file)
            log_path.parent.mkdir(parents=True, exist_ok=True)
            
            file_handler = RotatingFileHandler(
                filename=log_file,
                maxBytes=max_file_size,
                backupCount=backup_count,
                encoding="utf-8",
            )
            file_handler.setLevel(getattr(logging, log_level.upper()))
            
            if use_json:
                file_handler.setFormatter(JSONFormatter())
            else:
                file_handler.setFormatter(logging.Formatter(log_format))
            
            root_logger.addHandler(file_handler)
    
    @classmethod
    def get_logger(cls, name: str) -> logging.Logger:
        """
        Get a logger instance by name
        
        Args:
            name: Logger name (typically __name__)
            
        Returns:
            Configured logger instance
        """
        if name not in cls._loggers:
            cls._loggers[name] = logging.getLogger(name)
        return cls._loggers[name]


def setup_logger(
    log_level: str = "INFO",
    log_file: Optional[str] = None,
    use_json: bool = False,
) -> None:
    """
    Convenience function to setup the logging system
    
    Args:
        log_level: Logging level
        log_file: Optional path to log file
        use_json: Use JSON formatting
    """
    AgentLogger.setup(
        log_level=log_level,
        log_file=log_file,
        use_json=use_json,
    )


def get_logger(name: str) -> logging.Logger:
    """
    Get a configured logger instance
    
    Args:
        name: Logger name (use __name__)
        
    Returns:
        Logger instance ready to use
    """
    return AgentLogger.get_logger(name)


# Convenience functions for common patterns
def log_execution_time(logger: logging.Logger, func_name: str):
    """
    Decorator to log function execution time
    
    Usage:
        @log_execution_time(logger, "my_function")
        def my_function():
            pass
    """
    import time
    from functools import wraps
    
    def decorator(func):
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            start_time = time.time()
            try:
                result = await func(*args, **kwargs)
                elapsed = time.time() - start_time
                logger.debug(
                    f"[PERF] {func_name} completed in {elapsed:.3f}s"
                )
                return result
            except Exception as e:
                elapsed = time.time() - start_time
                logger.error(
                    f"[PERF] {func_name} failed after {elapsed:.3f}s: {e}"
                )
                raise
        
        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            start_time = time.time()
            try:
                result = func(*args, **kwargs)
                elapsed = time.time() - start_time
                logger.debug(
                    f"[PERF] {func_name} completed in {elapsed:.3f}s"
                )
                return result
            except Exception as e:
                elapsed = time.time() - start_time
                logger.error(
                    f"[PERF] {func_name} failed after {elapsed:.3f}s: {e}"
                )
                raise
        
        import asyncio
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper
    
    return decorator


class ContextFilter(logging.Filter):
    """Add contextual information to log records"""
    
    def __init__(self, context: dict):
        super().__init__()
        self.context = context
    
    def filter(self, record: logging.LogRecord) -> bool:
        for key, value in self.context.items():
            setattr(record, key, value)
        return True
