"""
Configuration Management System
Supports YAML config files and environment variables with type validation
"""
import os
from pathlib import Path
from typing import Any, Optional, TypeVar, Type
import yaml
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings


T = TypeVar("T", bound=BaseModel)


class LLMConfig(BaseModel):
    """LLM Configuration"""
    provider: str = "deepseek"
    model: str = "deepseek-chat"
    api_base: str = "https://api.deepseek.com/v1"
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    max_tokens: int = Field(default=4096, ge=1, le=32000)
    stream: bool = True
    
    class RetryConfig(BaseModel):
        max_retries: int = 3
        retry_delay: float = 1.0
    
    retry: RetryConfig = Field(default_factory=RetryConfig)


class ShortTermMemoryConfig(BaseModel):
    """Short-term Memory Configuration"""
    window_size: int = Field(default=10, ge=1, le=100)
    max_tokens: int = Field(default=8000, ge=1000, le=128000)


class LongTermMemoryConfig(BaseModel):
    """Long-term Memory Configuration"""
    vector_db: str = "chromadb"
    persist_directory: str = "./data/chromadb"
    collection_name: str = "agent_memories"
    embedding_model: str = "all-MiniLM-L6-v2"
    similarity_threshold: float = Field(default=0.7, ge=0.0, le=1.0)
    max_results: int = Field(default=5, ge=1, le=20)


class MemoryConfig(BaseModel):
    """Memory System Configuration"""
    short_term: ShortTermMemoryConfig = Field(default_factory=ShortTermMemoryConfig)
    long_term: LongTermMemoryConfig = Field(default_factory=LongTermMemoryConfig)


class WebSearchToolConfig(BaseModel):
    """Web Search Tool Configuration"""
    engine: str = "duckduckgo"
    max_results: int = 5


class CodeExecutorToolConfig(BaseModel):
    """Code Executor Tool Configuration"""
    timeout: int = 30
    allowed_languages: list[str] = ["python", "javascript"]


class FileManagerToolConfig(BaseModel):
    """File Manager Tool Configuration"""
    base_path: str = "./workspace"
    allowed_extensions: list[str] = [".txt", ".md", ".py", ".json", ".csv"]


class ToolsConfig(BaseModel):
    """Tools Configuration"""
    enabled: list[str] = [
        "web_search",
        "calculator",
        "code_executor",
        "file_manager",
    ]
    web_search: WebSearchToolConfig = Field(default_factory=WebSearchToolConfig)
    code_executor: CodeExecutorToolConfig = Field(default_factory=CodeExecutorToolConfig)
    file_manager: FileManagerToolConfig = Field(default_factory=FileManagerToolConfig)


class AgentConfig(BaseModel):
    """Agent Core Configuration"""
    name: str = "DeepSeek Assistant"
    max_iterations: int = Field(default=15, ge=1, le=50)
    thinking_verbose: bool = True
    safe_mode: bool = True


class ServerConfig(BaseModel):
    """API Server Configuration"""
    host: str = "0.0.0.0"
    port: int = 8000
    debug: bool = False
    cors_origins: list[str] = ["*"]


class LoggingConfig(BaseModel):
    """Logging Configuration"""
    level: str = "INFO"
    format: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    file: str = "./logs/agent.log"
    max_file_size: int = 10485760  # 10MB
    backup_count: int = 5


class AppConfig(BaseModel):
    """Main Application Configuration"""
    llm: LLMConfig = Field(default_factory=LLMConfig)
    memory: MemoryConfig = Field(default_factory=MemoryConfig)
    tools: ToolsConfig = Field(default_factory=ToolsConfig)
    agent: AgentConfig = Field(default_factory=AgentConfig)
    server: ServerConfig = Field(default_factory=ServerConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)


class ConfigManager:
    """
    Centralized Configuration Manager
    
    Features:
    - Load from YAML config file
    - Override with environment variables
    - Type validation via Pydantic
    - Support nested configurations
    """
    
    def __init__(self, config_path: Optional[str] = None):
        self._config_path = Path(config_path) if config_path else self._find_config_file()
        self._config: Optional[AppConfig] = None
        self._load_config()
    
    def _find_config_file(self) -> Path:
        """Find config.yaml in standard locations"""
        candidates = [
            Path("configs/config.yaml"),
            Path("config.yaml"),
            Path(__file__).parent.parent.parent / "configs" / "config.yaml",
        ]
        
        for candidate in candidates:
            if candidate.exists():
                return candidate
        
        raise FileNotFoundError(
            f"Configuration file not found. Searched: {[str(c) for c in candidates]}"
        )
    
    def _load_config(self) -> None:
        """Load and validate configuration"""
        config_data = {}
        
        # Load from YAML file
        if self._config_path.exists():
            with open(self._config_path, "r", encoding="utf-8") as f:
                config_data = yaml.safe_load(f) or {}
        
        # Override with environment variables
        env_overrides = self._load_env_overrides()
        config_data = self._deep_merge(config_data, env_overrides)
        
        # Validate and create config object
        self._config = AppConfig(**config_data)
    
    def _load_env_overrides(self) -> dict[str, Any]:
        """Load environment variable overrides"""
        overrides = {}
        
        env_mappings = {
            "DEEPSEEK_API_KEY": ("llm", "api_key"),
            "DEEPSEEK_API_BASE": ("llm", "api_base"),
            "AGENT_NAME": ("agent", "name"),
            "LOG_LEVEL": ("logging", "level"),
        }
        
        for env_var, (section, key) in env_mappings.items():
            value = os.getenv(env_var)
            if value:
                if section not in overrides:
                    overrides[section] = {}
                overrides[section][key] = value
        
        return overrides
    
    @staticmethod
    def _deep_merge(base: dict, override: dict) -> dict:
        """Deep merge two dictionaries"""
        result = base.copy()
        for key, value in override.items():
            if (
                key in result
                and isinstance(result[key], dict)
                and isinstance(value, dict)
            ):
                result[key] = ConfigManager._deep_merge(result[key], value)
            else:
                result[key] = value
        return result
    
    @property
    def config(self) -> AppConfig:
        """Get the validated configuration"""
        if self._config is None:
            raise RuntimeError("Configuration not loaded")
        return self._config
    
    def get_section(self, section_name: str) -> BaseModel:
        """Get a specific configuration section"""
        return getattr(self.config, section_name)
    
    def reload(self) -> None:
        """Reload configuration from file"""
        self._load_config()
    
    def __repr__(self) -> str:
        return f"ConfigManager(config_path={self._config_path})"


# Global singleton instance
_config_manager: Optional[ConfigManager] = None


def get_config(config_path: Optional[str] = None) -> ConfigManager:
    """
    Get or create the global ConfigManager instance
    
    Args:
        config_path: Optional path to config file
        
    Returns:
        ConfigManager singleton instance
    """
    global _config_manager
    if _config_manager is None:
        _config_manager = ConfigManager(config_path)
    return _config_manager
