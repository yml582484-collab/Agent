"""
Base Tool Class and Registry System
Provides the foundation for creating and managing tools
"""
from typing import Any, Dict, List, Optional, Type, Callable, Union
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from functools import wraps
import inspect

from ..utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class ParameterSchema:
    """Schema for a tool parameter"""
    name: str
    type: str  # "string", "integer", "number", "boolean", "array", "object"
    description: str
    required: bool = True
    default: Any = None
    enum: Optional[List[Any]] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to OpenAI function calling format"""
        param: Dict[str, Any] = {
            "type": self.type,
            "description": self.description,
        }
        
        if self.enum:
            param["enum"] = self.enum
        if not self.required:
            param["default"] = self.default
            
        return param


@dataclass
class ToolSchema:
    """Complete schema for a tool (OpenAI function calling format)"""
    name: str
    description: str
    parameters: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API"""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


class BaseTool(ABC):
    """
    Abstract Base Class for All Tools
    
    All custom tools must inherit from this class and implement:
    - `name`: Tool identifier
    - `description`: What the tool does
    - `parameters_schema`: Input parameter definitions
    - `execute()`: Main logic
    
    Usage:
        class MyTool(BaseTool):
            name = "my_tool"
            description = "Does something useful"
            
            @property
            def parameters_schema(self) -> Dict:
                return {
                    "type": "object",
                    "properties": {
                        "param1": {"type": "string", "description": "First parameter"}
                    },
                    "required": ["param1"]
                }
            
            async def execute(self, **kwargs) -> Dict:
                # Implementation here
                return {"result": "success"}
    """
    
    name: str = ""
    description: str = ""
    
    def __init_subclass__(cls, **kwargs):
        """Auto-register tools when they're defined"""
        super().__init_subclass__(**kwargs)
        if cls.name and cls.description:
            tool_registry.register(cls)
    
    @property
    @abstractmethod
    def parameters_schema(self) -> Dict[str, Any]:
        """
        Define the input parameters schema
        
        Returns:
            Dictionary in JSON Schema format for OpenAI function calling
        """
        pass
    
    @abstractmethod
    async def execute(self, **kwargs) -> Any:
        """
        Execute the tool with given parameters
        
        Args:
            **kwargs: Tool parameters as keyword arguments
            
        Returns:
            Tool execution result (will be converted to string for LLM context)
        """
        pass
    
    async def __call__(self, **kwargs) -> Any:
        """Allow calling tool instance directly"""
        return await self.execute(**kwargs)
    
    def get_schema(self) -> ToolSchema:
        """
        Get the complete tool schema for function calling
        
        Returns:
            ToolSchema object ready for LLM consumption
        """
        return ToolSchema(
            name=self.name,
            description=self.description,
            parameters=self.parameters_schema,
        )
    
    def validate_parameters(self, params: Dict[str, Any]) -> bool:
        """
        Validate input parameters against schema
        
        Args:
            params: Parameters to validate
            
        Returns:
            True if valid, raises ValueError if invalid
        """
        schema = self.parameters_schema
        
        # Check required parameters
        required = schema.get("required", [])
        for req_param in required:
            if req_param not in params:
                raise ValueError(f"Missing required parameter: {req_param}")
        
        # Check parameter types (basic validation)
        properties = schema.get("properties", {})
        for key, value in params.items():
            if key in properties:
                expected_type = properties[key].get("type")
                if expected_type and not self._check_type(value, expected_type):
                    raise TypeError(
                        f"Parameter '{key}' should be {expected_type}, "
                        f"got {type(value).__name__}"
                    )
        
        return True
    
    @staticmethod
    def _check_type(value: Any, expected_type: str) -> bool:
        """Check if value matches expected type"""
        type_mapping = {
            "string": str,
            "integer": int,
            "number": (int, float),
            "boolean": bool,
            "array": list,
            "object": dict,
        }
        
        expected = type_mapping.get(expected_type)
        if expected is None:
            return True  # Unknown type, allow
        
        return isinstance(value, expected)
    
    def format_result(self, result: Any) -> str:
        """
        Format tool result for LLM consumption
        
        Args:
            result: Raw result from execute()
            
        Returns:
            Formatted string representation
        """
        if isinstance(result, dict):
            import json
            return json.dumps(result, ensure_ascii=False, indent=2)
        elif isinstance(result, list):
            import json
            return json.dumps(result, ensure_ascii=False, indent=2)
        else:
            return str(result)


class ToolRegistry:
    """
    Global Tool Registration and Management System
    
    Features:
    - Auto-registration via decorators or inheritance
    - Tool discovery and listing
    - Tool retrieval by name
    - Dynamic enable/disable of tools
    
    Usage:
        # Register via decorator
        @tool_registry.register
        class MyTool(BaseTool):
            ...
        
        # Or manually
        tool_registry.register(MyTool)
        
        # Get all tools
        all_tools = tool_registry.get_all_tools()
        
        # Get specific tool
        tool = tool_registry.get_tool("my_tool")
    """
    
    def __init__(self):
        self._tools: Dict[str, Type[BaseTool]] = {}
        self._instances: Dict[str, BaseTool] = {}
        self._enabled_tools: set = set()
    
    def register(
        self,
        tool_class: Union[Type[BaseTool], BaseTool],
    ) -> Type[BaseTool]:
        """
        Register a tool class (can be used as decorator)
        
        Args:
            tool_class: The tool class to register
            
        Returns:
            The same tool class (for decorator chaining)
        """
        # Handle both class and instance
        if inspect.isclass(tool_class):
            tool_name = getattr(tool_class, 'name', None)
            if not tool_name:
                raise ValueError(
                    f"Tool class {tool_class.__name__} must have a 'name' attribute"
                )
            
            self._tools[tool_name] = tool_class
            self._enabled_tools.add(tool_name)
            
            logger.debug(f"Registered tool: {tool_name}")
        else:
            # It's an instance
            tool_instance = tool_class
            tool_name = tool_instance.name
            self._tools[tool_name] = type(tool_instance)
            self._instances[tool_name] = tool_instance
            self._enabled_tools.add(tool_name)
            
            logger.debug(f"Registered tool instance: {tool_name}")
        
        return tool_class
    
    def get_tool(self, name: str) -> Optional[BaseTool]:
        """
        Get a tool instance by name
        
        Args:
            name: Tool name/identifier
            
        Returns:
            Tool instance or None if not found
        """
        if name not in self._enabled_tools:
            logger.warning(f"Tool '{name}' is not enabled")
            return None
        
        # Return cached instance or create new one
        if name in self._instances:
            return self._instances[name]
        
        if name in self._tools:
            instance = self._tools[name]()
            self._instances[name] = instance
            return instance
        
        logger.error(f"Tool '{name}' not found in registry")
        return None
    
    def get_all_tools(self) -> List[BaseTool]:
        """
        Get instances of all enabled tools
        
        Returns:
            List of tool instances
        """
        tools = []
        for name in self._enabled_tools:
            tool = self.get_tool(name)
            if tool:
                tools.append(tool)
        return tools
    
    def get_all_schemas(self) -> List[Dict[str, Any]]:
        """
        Get schemas for all enabled tools (for LLM function calling)
        
        Returns:
            List of tool schema dictionaries
        """
        schemas = []
        for tool in self.get_all_tools():
            schemas.append(tool.get_schema().to_dict())
        return schemas
    
    def get_tools_description(self) -> str:
        """
        Generate human-readable description of all tools
        
        Returns:
            Formatted string describing available tools
        """
        descriptions = []
        for tool in self.get_all_tools():
            descriptions.append(
                f"- **{tool.name}**: {tool.description}"
            )
        return "\n".join(descriptions) if descriptions else "No tools available"
    
    def enable_tool(self, name: str) -> bool:
        """
        Enable a disabled tool
        
        Args:
            name: Tool name
            
        Returns:
            True if successfully enabled
        """
        if name in self._tools:
            self._enabled_tools.add(name)
            logger.info(f"Enabled tool: {name}")
            return True
        return False
    
    def disable_tool(self, name: str) -> bool:
        """
        Disable a tool (won't be returned by get_all_tools)
        
        Args:
            name: Tool name
            
        Returns:
            True if successfully disabled
        """
        if name in self._enabled_tools:
            self._enabled_tools.remove(name)
            logger.info(f"Disabled tool: {name}")
            return True
        return False
    
    def list_tools(self) -> List[Dict[str, str]]:
        """
        List all registered tools with their status
        
        Returns:
            List of dicts with tool info
        """
        return [
            {
                "name": name,
                "description": cls.description if hasattr(cls, 'description') else "",
                "enabled": name in self._enabled_tools,
            }
            for name, cls in self._tools.items()
        ]
    
    def clear(self) -> None:
        """Clear all registered tools"""
        self._tools.clear()
        self._instances.clear()
        self._enabled_tools.clear()
        logger.info("Tool registry cleared")
    
    @property
    def count(self) -> int:
        """Number of enabled tools"""
        return len(self._enabled_tools)
    
    def __repr__(self) -> str:
        return (
            f"ToolRegistry(registered={len(self._tools)}, "
            f"enabled={len(self._enabled_tools)})"
        )


# Global singleton registry (must be defined before tool_decorator)
tool_registry = ToolRegistry()


def tool_decorator(
    name: str,
    description: str,
    parameters_schema: Optional[Dict] = None,
):
    """
    Decorator for quickly creating simple tools from functions
    
    Usage:
        @tool_decorator(
            name="calculator",
            description="Perform mathematical calculations",
            parameters_schema={
                "type": "object",
                "properties": {
                    "expression": {
                        "type": "string",
                        "description": "Mathematical expression to evaluate"
                    }
                },
                "required": ["expression"]
            }
        )
        async def calculate(expression: str) -> Dict:
            result = eval(expression)
            return {"expression": expression, "result": result}
    """
    def decorator(func: Callable) -> Type[BaseTool]:
        # Create dynamic tool class
        schema = parameters_schema or {
            "type": "object",
            "properties": {},
            "required": [],
        }
        
        class FunctionTool(BaseTool):
            name = name
            description = description
            
            @property
            def parameters_schema(self) -> Dict:
                return schema
            
            async def execute(self, **kwargs) -> Any:
                return await func(**kwargs) if inspect.iscoroutinefunction(func) else func(**kwargs)
        
        # Set original function name for debugging
        FunctionTool.__qualname__ = f"Tool({func.__name__})"
        
        # Register the tool
        tool_registry.register(FunctionTool)
        
        return FunctionTool
    
    return decorator
