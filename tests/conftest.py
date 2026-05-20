# Test Configuration and Fixtures
import pytest
import asyncio
from pathlib import Path
import sys

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


@pytest.fixture
def event_loop():
    """Create event loop for async tests"""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def sample_config(tmp_path):
    """Create a temporary config file for testing"""
    import yaml
    
    config_data = {
        "llm": {
            "provider": "deepseek",
            "model": "deepseek-chat",
            "api_base": "https://api.deepseek.com/v1",
            "temperature": 0.7,
            "max_tokens": 100,
            "stream": False,
        },
        "memory": {
            "short_term": {"window_size": 5, "max_tokens": 1000},
            "long_term": {
                "vector_db": "chromadb",
                "persist_directory": str(tmp_path / "test_chromadb"),
                "collection_name": "test_memories",
            },
        },
        "agent": {
            "name": "Test Agent",
            "max_iterations": 5,
            "thinking_verbose": False,
        },
    }
    
    config_file = tmp_path / "config.yaml"
    with open(config_file, 'w', encoding='utf-8') as f:
        yaml.dump(config_data, f)
    
    return str(config_file)
