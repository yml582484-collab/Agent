"""
Calculator Tool
Evaluates mathematical expressions safely
"""
import ast
import operator
from typing import Any, Dict, List

from .base import BaseTool
from ..utils.logger import get_logger

logger = get_logger(__name__)


# Safe operators mapping
SAFE_OPERATORS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}

# Allowed functions
SAFE_FUNCTIONS = {
    'abs': abs,
    'round': round,
    'min': min,
    'max': max,
    'sum': sum,
    'len': len,
    'pow': pow,
}


class CalculatorTool(BaseTool):
    """
    Safe Mathematical Calculator
    
    Evaluates math expressions in a sandboxed environment.
    Only allows basic arithmetic operations for safety.
    """
    
    name = "calculator"
    description = (
        "Evaluate mathematical expressions safely. "
        "Supports basic arithmetic (+, -, *, /, **, %), "
        "and common functions (abs, round, min, max, sum). "
        "Use this for any calculation tasks."
    )
    
    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "expression": {
                    "type": "string",
                    "description": (
                        "Mathematical expression to evaluate. "
                        "Examples: '2 + 2', '(100 * 0.1) + 50', "
                        "'2 ** 10', 'abs(-42)'"
                    ),
                },
            },
            "required": ["expression"],
        }
    
    async def execute(self, expression: str, **kwargs) -> Dict[str, Any]:
        """
        Safely evaluate a mathematical expression
        
        Args:
            expression: Mathematical expression string
            
        Returns:
            Dictionary with result or error
        """
        logger.info(f"Evaluating expression: {expression}")
        
        try:
            result = self._safe_eval(expression)
            
            return {
                "success": True,
                "expression": expression,
                "result": result,
                "result_type": type(result).__name__,
            }
            
        except Exception as e:
            logger.warning(f"Calculation error: {e}")
            
            return {
                "success": False,
                "expression": expression,
                "error": str(e),
                "suggestion": (
                    "Please check your expression. "
                    "Supported operations: +, -, *, /, **, %, "
                    "and functions: abs, round, min, max, sum"
                ),
            }
    
    def _safe_eval(self, expr: str):
        """
        Safely evaluate an expression using AST parsing
        
        This prevents code injection by only allowing
        safe operations on the AST level.
        """
        # Parse the expression into an AST
        tree = ast.parse(expr, mode='eval')
        
        # Define visitor that checks/evaluates only safe nodes
        def _eval(node):
            if isinstance(node, ast.Expression):
                return _eval(node.body)
            
            elif isinstance(node, ast.Constant):  # Python 3.8+
                return node.value
            
            elif isinstance(node, ast.Num):  # Legacy Python
                return node.n
            
            elif isinstance(node, ast.BinOp):
                left = _eval(node.left)
                right = _eval(node.right)
                op_type = type(node.op)
                
                if op_type not in SAFE_OPERATORS:
                    raise TypeError(f"Operator {op_type.__name__} not allowed")
                
                return SAFE_OPERATORS[op_type](left, right)
            
            elif isinstance(node, ast.UnaryOp):
                operand = _eval(node.operand)
                op_type = type(node.op)
                
                if op_type not in SAFE_OPERATORS:
                    raise TypeError(f"Unary operator {op_type.__name__} not allowed")
                
                return SAFE_OPERATORS[op_type](operand)
            
            elif isinstance(node, ast.Call):
                func_name = node.func.id if isinstance(node.func, ast.Name) else None
                
                if func_name not in SAFE_FUNCTIONS:
                    raise TypeError(f"Function '{func_name}' not allowed")
                
                args = [_eval(arg) for arg in node.args]
                return SAFE_FUNCTIONS[func_name](*args)
            
            else:
                raise TypeError(f"Expression type {type(node).__name__} not allowed")
        
        return _eval(tree)


# Simple two-number calculator (registered at module load time)
async def quick_calculate(a: float, b: float, operation: str) -> Dict:
    """Simple two-number calculator"""
    ops = {
        "add": lambda x, y: x + y,
        "subtract": lambda x, y: x - y,
        "multiply": lambda x, y: x * y,
        "divide": lambda x, y: x / y if y != 0 else float('inf'),
    }
    
    if operation not in ops:
        raise ValueError(f"Invalid operation: {operation}")
    
    result = ops[operation](a, b)
    return {"a": a, "b": b, "operation": operation, "result": result}


# Register the quick calculator tool after both function and registry are available
def _register_quick_calculator():
    """Delay registration to avoid circular import"""
    from .base import tool_decorator
    
    # Apply decorator manually
    QuickCalculateTool = tool_decorator(
        name="quick_calculate",
        description="Quick calculator for simple arithmetic expressions",
        parameters_schema={
            "type": "object",
            "properties": {
                "a": {"type": "number", "description": "First number"},
                "b": {"type": "number", "description": "Second number"},
                "operation": {
                    "type": "string",
                    "description": "Operation: add, subtract, multiply, divide",
                    "enum": ["add", "subtract", "multiply", "divide"],
                },
            },
            "required": ["a", "b", "operation"],
        },
    )(quick_calculate)

# Attempt registration (will succeed after full import)
try:
    _register_quick_calculator()
except (NameError, ImportError):
    pass  # Will be registered when tools are fully loaded
