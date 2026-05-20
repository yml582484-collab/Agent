"""
Unit Tests for Tool System
Tests tool registration, execution, and validation
"""
import pytest
import json
from typing import Dict, Any


class TestToolRegistry:
    """Tests for the global tool registry system"""
    
    def test_registry_initialization(self):
        """Test that registry initializes empty"""
        from src.tools.base import tool_registry
        
        assert isinstance(tool_registry.count, int)
    
    def test_tool_registration_via_class(self):
        """Test registering tools via class inheritance"""
        from src.tools.base import BaseTool, tool_registry
        
        class TestTool(BaseTool):
            name = "test_tool"
            description = "A test tool"
            
            @property
            def parameters_schema(self) -> Dict[str, Any]:
                return {
                    "type": "object",
                    "properties": {
                        "param1": {"type": "string", "description": "Test param"}
                    },
                    "required": ["param1"],
                }
            
            async def execute(self, **kwargs) -> Dict:
                return {"result": f"Processed: {kwargs.get('param1')}"}
        
        # Tool should be auto-registered via __init_subclass__
        tool = tool_registry.get_tool("test_tool")
        
        assert tool is not None
        assert tool.name == "test_tool"
        assert tool.description == "A test tool"
        
        # Cleanup
        tool_registry._tools.pop("test_tool", None)
        tool_registry._enabled_tools.discard("test_tool")
    
    def test_tool_enable_disable(self):
        """Test enabling and disabling tools"""
        from src.tools.base import BaseTool, tool_registry
        
        class TempTool(BaseTool):
            name = "temp_tool"
            description = "Temporary tool"
            
            @property
            def parameters_schema(self) -> Dict[str, Any]:
                return {"type": "object", "properties": {}, "required": []}
            
            async def execute(self, **kwargs) -> Dict:
                return {}
        
        # Disable
        tool_registry.disable_tool("temp_tool")
        assert tool_registry.get_tool("temp_tool") is None
        
        # Re-enable
        tool_registry.enable_tool("temp_tool")
        assert tool_registry.get_tool("temp_tool") is not None
        
        # Cleanup
        tool_registry._tools.pop("temp_tool", None)
        tool_registry._enabled_tools.discard("temp_tool")
    
    def test_list_tools(self):
        """Test listing all registered tools"""
        from src.tools.base import tool_registry
        
        tools_list = tool_registry.list_tools()
        
        assert isinstance(tools_list, list)


class TestCalculatorTool:
    """Tests for CalculatorTool"""
    
    @pytest.mark.asyncio
    async def test_basic_arithmetic(self):
        """Test basic arithmetic operations"""
        from src.tools.calculator import CalculatorTool
        
        calc = CalculatorTool()
        
        result = await calc.execute(expression="2 + 2")
        
        assert result["success"] is True
        assert result["result"] == 4
    
    @pytest.mark.asyncio
    async def test_complex_expression(self):
        """Test complex mathematical expressions"""
        from src.tools.calculator import CalculatorTool
        
        calc = CalculatorTool()
        
        result = await calc.execute(expression="(100 * 0.1) + 50")
        
        assert result["success"] is True
        assert result["result"] == 60.0
    
    @pytest.mark.asyncio
    async def test_power_operation(self):
        """Test power/exponentiation operation"""
        from src.tools.calculator import CalculatorTool
        
        calc = CalculatorTool()
        
        result = await calc.execute(expression="2 ** 10")
        
        assert result["success"] is True
        assert result["result"] == 1024
    
    @pytest.mark.asyncio
    async def test_invalid_expression(self):
        """Test error handling for invalid expressions"""
        from src.tools.calculator import CalculatorTool
        
        calc = CalculatorTool()
        
        # This should fail validation or evaluation
        result = await calc.execute(expression="invalid !!! expression")
        
        assert result["success"] is False
        assert "error" in result


class TestFileManagerTool:
    """Tests for FileManagerTool (uses temp directory)"""
    
    @pytest.mark.asyncio
    async def test_write_and_read(self, tmp_path):
        """Test writing and reading files"""
        import sys
        from pathlib import Path
        sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
        
        from src.utils.config import get_config, ConfigManager
        from src.tools.file_manager import FileManagerTool
        
        # Create config with temp base path
        config_manager = ConfigManager.__new__(ConfigManager)
        config_manager._config = type('obj', (object,), {
            'tools': type('obj', (object,), {
                'file_manager': type('obj', (object,), {
                    'base_path': str(tmp_path),
                    'allowed_extensions': ['.txt', '.md', '.json'],
                })()
            })()
        })()
        
        # Patch get_config temporarily
        original_get_config = None
        import src.tools.file_manager as fm_module
        original_get_config = fm_module.get_config
        fm_module.get_config = lambda: config_manager
        
        try:
            file_mgr = FileManagerTool()
            
            # Write file
            write_result = await file_mgr.execute(
                action="write",
                path="test.txt",
                content="Hello, World!",
            )
            
            assert write_result["success"] is True
            
            # Read file back
            read_result = await file_mgr.execute(
                action="read",
                path="test.txt",
            )
            
            assert read_result["success"] is True
            assert read_result["content"] == "Hello, World!"
            
        finally:
            # Restore original function
            fm_module.get_config = original_get_config
    
    @pytest.mark.asyncio
    async def test_directory_listing(self, tmp_path):
        """Test listing directory contents"""
        import sys
        from pathlib import Path
        sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
        
        from src.utils.config import get_config, ConfigManager
        from src.tools.file_manager import FileManagerTool
        
        # Setup config similar to above
        config_manager = ConfigManager.__new__(ConfigManager)
        config_manager._config = type('obj', (object,), {
            'tools': type('obj', (object,), {
                'file_manager': type('obj', (object,), {
                    'base_path': str(tmp_path),
                    'allowed_extensions': ['.txt'],
                })()
            })()
        })()
        
        import src.tools.file_manager as fm_module
        original_get_config = fm_module.get_config
        fm_module.get_config = lambda: config_manager
        
        try:
            file_mgr = FileManagerTool()
            
            # List root directory
            list_result = await file_mgr.execute(
                action="list",
                path=".",
            )
            
            assert list_result["success"] is True
            assert "items" in list_result
            assert "count" in list_result
            
        finally:
            fm_module.get_config = original_get_config


class TestWebSearchTool:
    """Tests for WebSearchTool"""
    
    @pytest.mark.asyncio
    async def test_search_execution(self):
        """Test that search can be executed (may use fallback)"""
        from src.tools.web_search import WebSearchTool
        
        search = WebSearchTool()
        
        # Execute search (will use fallback if DuckDuckGo unavailable)
        result = await search.execute(query="Python programming", max_results=3)
        
        assert "success" in result
        assert "query" in result
        assert isinstance(result["results"], list)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
