"""
ReAct (Reason-Act-Observe) Task Planner
Implements the ReAct reasoning loop for complex task execution
"""
import json
import re
import asyncio
from typing import Any, Dict, List, Optional, AsyncIterator, Tuple
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

from ..llm.provider import DeepSeekProvider, Message, LLMResponse
from ..llm.prompts import PromptTemplates
from ..tools.base import BaseTool, tool_registry
from ..memory.short_term import ShortTermMemory
from ..memory.long_term import LongTermMemory
from ..utils.config import get_config
from ..utils.logger import get_logger

logger = get_logger(__name__)


class PlannerState(Enum):
    """States in the ReAct planning cycle"""
    INITIALIZING = "initializing"
    REASONING = "reasoning"
    ACTING = "acting"
    OBSERVING = "observing"
    COMPLETED = "completed"
    FAILED = "failed"
    MAX_ITERATIONS_REACHED = "max_iterations_reached"


@dataclass
class Thought:
    """A single reasoning step in the ReAct loop"""
    step: int
    content: str
    timestamp: datetime = field(default_factory=datetime.now)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "step": self.step,
            "content": self.content,
            "timestamp": self.timestamp.isoformat(),
        }


@dataclass
class Action:
    """An action taken by the agent"""
    step: int
    tool_name: str
    parameters: Dict[str, Any]
    timestamp: datetime = field(default_factory=datetime.now)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "step": self.step,
            "tool_name": self.tool_name,
            "parameters": self.parameters,
            "timestamp": self.timestamp.isoformat(),
        }


@dataclass
class Observation:
    """Result from executing an action"""
    step: int
    result: Any
    success: bool
    error: Optional[str] = None
    timestamp: datetime = field(default_factory=datetime.now)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "step": self.step,
            "result": str(self.result)[:500] if self.result else None,
            "success": self.success,
            "error": self.error,
            "timestamp": self.timestamp.isoformat(),
        }


@dataclass
class PlanExecutionResult:
    """Complete result of plan execution"""
    final_answer: str
    success: bool
    steps_completed: int
    thoughts: List[Thought] = field(default_factory=list)
    actions: List[Action] = field(default_factory=list)
    observations: List[Observation] = field(default_factory=list)
    state: PlannerState = PlannerState.COMPLETED
    token_usage: Dict[str, int] = field(default_factory=dict)
    duration_seconds: float = 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "final_answer": self.final_answer,
            "success": self.success,
            "steps_completed": self.steps_completed,
            "state": self.state.value,
            "thoughts": [t.to_dict() for t in self.thoughts],
            "actions": [a.to_dict() for a in self.actions],
            "observations": [o.to_dict() for o in self.observations],
            "token_usage": self.token_usage,
            "duration_seconds": round(self.duration_seconds, 2),
        }


class ReActPlanner:
    """
    ReAct (Reason-Act-Observe) Task Planner
    
    Implements the cognitive loop for solving complex tasks:
    1. **Thought**: Analyze the situation and decide what to do next
    2. **Action**: Execute a tool or perform an operation
    3. **Observe**: Analyze the result of the action
    4. **Repeat** until the task is complete
    
    Features:
    - Automatic tool selection based on LLM reasoning
    - Iterative refinement with observation feedback
    - Maximum iteration limit for safety
    - Detailed execution trace for debugging
    - Streaming intermediate results
    
    Usage:
        planner = ReActPlanner(llm_provider, tools, memory)
        
        result = await planner.plan_and_execute("What's the weather in Beijing?")
        
        # Access the reasoning process
        for thought in result.thoughts:
            print(f"Step {thought.step}: {thought.content}")
    """
    
    def __init__(
        self,
        llm_provider: DeepSeekProvider,
        short_term_memory: ShortTermMemory,
        long_term_memory: Optional[LongTermMemory] = None,
        max_iterations: Optional[int] = None,
        verbose: bool = True,
    ):
        """
        Initialize the ReAct planner
        
        Args:
            llm_provider: LLM provider for reasoning
            short_term_memory: Short-term memory for context
            long_term_memory: Long-term memory for knowledge retrieval
            max_iterations: Maximum number of ReAct loops (safety limit)
            verbose: Whether to log detailed reasoning steps
        """
        config = get_config().config.agent
        
        self.llm = llm_provider
        self.short_term_memory = short_term_memory
        self.long_term_memory = long_term_memory
        self.max_iterations = max_iterations or config.max_iterations
        self.verbose = verbose
        
        self._state = PlannerState.INITIALIZING
        self._current_step = 0
        
        logger.info(
            f"ReActPlanner initialized "
            f"(max_iterations={self.max_iterations}, verbose={self.verbose})"
        )
    
    async def plan_and_execute(
        self,
        user_input: str,
        conversation_history: Optional[List[Message]] = None,
        stream_callback: Optional[callable] = None,
    ) -> PlanExecutionResult:
        """
        Execute the complete ReAct planning cycle

        Args:
            user_input: User's question or request
            conversation_history: Previous messages (optional)
            stream_callback: Callback for streaming intermediate results

        Returns:
            PlanExecutionResult with final answer and full trace
        """
        start_time = datetime.now()
        max_execution_time = 120  # 最大执行时间 120 秒

        result = PlanExecutionResult(
            final_answer="",
            success=False,
            steps_completed=0,
        )

        # 错误追踪
        consecutive_failures = 0
        max_consecutive_failures = 3  # 连续失败3次后强制停止

        try:
            self._state = PlannerState.REASONING

            # Get relevant context
            context = await self._gather_context(user_input)

            # Build initial prompt
            prompt = PromptTemplates.get_react_prompt(
                user_input=user_input,
                tools_description=tool_registry.get_tools_description(),
                conversation_history=self._format_history(conversation_history),
                relevant_memories=context,
            )

            # Initialize messages for this session
            messages = [
                Message(role="system", content=prompt),
                Message(role="user", content=user_input),
            ]

            # Main ReAct loop with timeout and error recovery
            while self._current_step < self.max_iterations:
                # 检查超时
                elapsed = (datetime.now() - start_time).total_seconds()
                if elapsed > max_execution_time:
                    logger.warning(f"ReAct execution timed out after {elapsed:.1f}s")
                    result.state = PlannerState.MAX_ITERATIONS_REACHED
                    result.final_answer = (
                        f"⏰ 任务执行时间过长（{elapsed:.1f}秒），已自动终止。\n\n"
                        f"以下是当前进度：\n"
                        + self._summarize_progress(result)
                    )
                    break

                self._current_step += 1

                if self.verbose:
                    logger.info(f"\n{'='*60}")
                    logger.info(f"ReAct Step {self._current_step}/{self.max_iterations}")
                    logger.info(f"{'='*60}\n")

                # Step 1: Reasoning (Thought)
                try:
                    thought = await self._reason(messages, user_input)
                except Exception as e:
                    logger.error(f"Reasoning failed at step {self._current_step}: {e}")
                    consecutive_failures += 1
                    if consecutive_failures >= max_consecutive_failures:
                        result.final_answer = f"❌ 推理过程连续失败{consecutive_failures}次，无法完成任务。错误：{str(e)}"
                        result.state = PlannerState.FAILED
                        break
                    continue

                result.thoughts.append(thought)

                if stream_callback:
                    await stream_callback({
                        "type": "thought",
                        "step": self._current_step,
                        "content": thought.content,
                    })

                # Check if we have a final answer
                if self._is_final_answer(thought.content):
                    result.final_answer = self._extract_final_answer(thought.content)
                    result.success = True
                    result.state = PlannerState.COMPLETED
                    break

                # Step 2: Decide on Action
                action = await self._decide_action(thought.content, messages)

                if action is None:
                    # No action needed - might be direct answer or unclear instruction
                    consecutive_failures += 1
                    if consecutive_failures >= max_consecutive_failures:
                        # 强制提取答案或生成错误信息
                        result.final_answer = (
                            f"⚠️ 无法确定下一步操作（连续{consecutive_failures}次）。\n\n"
                            f"最后的思考：\n{thought.content[:500]}\n\n"
                            f"建议：请尝试更具体的指令，或者简化任务要求。"
                        )
                        result.state = PlannerState.COMPLETED  # 标记为完成（虽然不完美）
                        break

                    # 尝试将当前思考作为最终答案
                    if self._current_step > 2 and len(thought.content) > 50:
                        logger.info(f"No action at step {self._current_step}, treating as potential answer")
                        # 不break，继续给LLM一次机会明确输出Final Answer
                        continue

                    logger.warning(f"No action parsed at step {self._current_step}, retry...")
                    continue

                # 重置失败计数器（成功解析到action）
                consecutive_failures = 0

                result.actions.append(action)

                if stream_callback:
                    await stream_callback({
                        "type": "action",
                        "step": self._current_step,
                        "tool_name": action.tool_name,
                        "parameters": action.parameters,
                    })

                # Step 3: Execute Action
                observation = await self._execute_action(action)
                result.observations.append(observation)

                if stream_callback:
                    await stream_callback({
                        "type": "observation",
                        "step": self._current_step,
                        "result": observation.result,
                        "success": observation.success,
                    })

                # Check for tool execution failure
                if not observation.success:
                    consecutive_failures += 1
                    logger.warning(f"Tool execution failed at step {self._current_step}: {observation.error}")

                    if consecutive_failures >= max_consecutive_failures:
                        result.final_answer = (
                            f"❌ 工具调用连续失败{consecutive_failures}次。\n\n"
                            f"最后错误：{observation.error}\n\n"
                            f"已完成步骤：\n"
                            + self._summarize_progress(result)
                        )
                        result.state = PlannerState.FAILED
                        break
                else:
                    # 成功执行，重置计数器
                    consecutive_failures = 0

                # Add observation back to context
                obs_message = Message(
                    role="assistant",
                    content=f"Observation: {observation.result}",
                )
                messages.append(obs_message)

                # Continue looping...

            else:
                # Reached max iterations without completion
                result.state = PlannerState.MAX_ITERATIONS_REACHED
                result.final_answer = (
                    f"✅ 已完成 {self.max_iterations} 步推理，任务处理中...\n\n"
                    + self._summarize_progress(result)
                    + "\n\n💡 如需继续，请提供更明确的指令。"
                )

            result.steps_completed = self._current_step

        except Exception as e:
            logger.error(f"ReAct planning failed: {e}", exc_info=True)
            result.state = PlannerState.FAILED
            result.final_answer = f"❌ 执行过程中发生错误：{str(e)}"

        finally:
            # Calculate duration
            result.duration_seconds = (
                datetime.now() - start_time
            ).total_seconds()

            # Record token usage
            result.token_usage = self.llm.token_usage.to_dict()

            # Reset state
            self._current_step = 0
            self._state = PlannerState.INITIALIZING

            total_time = result.duration_seconds
            logger.info(
                f"\n{'='*60}"
                f"\n📊 ReAct 执行完成:"
                f"\n   状态: {result.state.value}"
                f"\n   步骤: {result.steps_completed}/{self.max_iterations}"
                f"\n   耗时: {total_time:.2f}s"
                f"\n   Token使用: {result.token_usage.get('total_tokens', 0)}"
                f"\n{'='*60}\n"
            )

        return result
    
    async def _gather_context(self, query: str) -> str:
        """
        Gather relevant context from memory systems
        
        Args:
            query: User's query to search for relevant memories
            
        Returns:
            Formatted context string
        """
        context_parts = []
        
        # Search long-term memory if available
        if self.long_term_memory:
            try:
                memories = await self.long_term_memory.search(query, n_results=3)
                
                if memories:
                    context_parts.append("**相关记忆:**")
                    for mem in memories[:3]:  # Top 3 memories
                        context_parts.append(f"- {mem.content}")
                        
            except Exception as e:
                logger.warning(f"Long-term memory search failed: {e}")
        
        return "\n".join(context_parts) if context_parts else ""
    
    async def _reason(
        self,
        messages: List[Message],
        user_input: str,
    ) -> Thought:
        """
        Generate a reasoning step using LLM
        
        Args:
            messages: Conversation history so far
            user_input: Original user input
            
        Returns:
            Thought object with reasoning content
        """
        self._state = PlannerState.REASONING
        
        try:
            response = await self.llm.chat_with_retry(messages)
            
            thought = Thought(
                step=self._current_step,
                content=response.content,
            )
            
            if self.verbose:
                logger.info(f"\n🤔 **Thought [{self._current_step}]:**")
                logger.info(response.content)
            
            return thought
            
        except Exception as e:
            logger.error(f"Reasoning failed at step {self._current_step}: {e}")
            raise
    
    async def _decide_action(
        self,
        thought_content: str,
        messages: List[Message],
    ) -> Optional[Action]:
        """
        Parse thought and decide on next action
        
        Args:
            thought_content: Content of the current thought
            messages: Conversation history
            
        Returns:
            Action object or None if no action needed
        """
        self._state = PlannerState.ACTING
        
        try:
            # Try to extract structured action from thought
            action_data = self._parse_action_from_thought(thought_content)
            
            if action_data:
                action = Action(
                    step=self._current_step,
                    tool_name=action_data["tool"],
                    parameters=action_data["params"],
                )
                
                if self.verbose:
                    logger.info(f"\n🔧 **Action [{self._current_step}]:**")
                    logger.info(f"Tool: {action.tool_name}")
                    logger.info(f"Parameters: {action.parameters}")
                
                return action
            
            return None
            
        except Exception as e:
            logger.warning(f"Action parsing failed: {e}")
            return None
    
    async def _execute_action(self, action: Action) -> Observation:
        """
        Execute the decided action (call a tool)
        
        Args:
            action: Action to execute
            
        Returns:
            Observation with execution result
        """
        self._state = PlannerState.OBSERVING
        
        try:
            # Get tool instance
            tool = tool_registry.get_tool(action.tool_name)
            
            if not tool:
                return Observation(
                    step=self._current_step,
                    result=f"Tool '{action.tool_name}' not found or not enabled",
                    success=False,
                    error="Tool not found",
                )
            
            # Validate parameters
            if not tool.validate_parameters(action.parameters):
                return Observation(
                    step=self._current_step,
                    result="Invalid parameters provided to tool",
                    success=False,
                    error="Parameter validation failed",
                )
            
            # Execute tool
            result = await tool.execute(**action.parameters)
            
            # Format result for LLM consumption
            formatted_result = tool.format_result(result)
            
            observation = Observation(
                step=self._current_step,
                result=formatted_result,
                success=True,
            )
            
            if self.verbose:
                logger.info(f"\n👁️ **Observation [{self._current_step}]:**")
                logger.info(formatted_result[:500])
            
            return observation
            
        except Exception as e:
            logger.error(f"Action execution failed: {e}")
            
            return Observation(
                step=self._current_step,
                result=f"Error executing {action.tool_name}: {str(e)}",
                success=False,
                error=str(e),
            )
    
    def _parse_action_from_thought(self, thought: str) -> Optional[Dict]:
        """
        Parse action information from LLM thought output

        Enhanced parser with multiple pattern strategies and better error tolerance.
        """
        # ===== 策略1: 函数调用格式 (最常见) =====
        # 匹配: calculator(expression="..."), code_executor(code="...", language="python")
        func_patterns = [
            r'(calculator|code_executor|file_manager|web_search)\s*[\(（]\s*(.+?)\s*[\)）]',
            r'(calculator|code_executor|file_manager|web_search)\s*[\(（]([^)]+)[\)）]',  # 贪婪匹配
        ]

        for pattern in func_patterns:
            match = re.search(pattern, thought, re.IGNORECASE | re.DOTALL)
            if match:
                tool_name = match.group(1).lower().strip()
                params_raw = match.group(2).strip()

                logger.debug(f"Func pattern matched: {tool_name}({params_raw[:100]}...)")

                params = self._extract_function_params(tool_name, params_raw)
                if params:
                    return {"tool": tool_name, "params": params}

        # ===== 策略2: 结构化格式 (JSON/键值对) =====
        structured_patterns = [
            # **Action:** tool\nParameters: {json}
            (r'\*\*Action:\*\*\s*(\w+)', r'Parameters?:\s*(\{[^}]+\})'),

            # 行动：tool\n参数：{json} (中文)
            (r'[\u884c\u52a8][\uff1a:]\s*(\w+)', r'[\u53c2\u6570][\uff1a:]\s*(\{[^}]+\})'),

            # - **工具名称**: `tool`\n- **参数**: {json}
            (r'\*\*\u5de5\u5177\u540d\u79f0\*\*[：:]*\s*[`"]?(\w+)[`"]?', r'\*\*\u53c2\u6570\*\*[：:]*\s*(`[^`]+`|\{[^}]+\})'),
        ]

        for tool_pattern, param_pattern in structured_patterns:
            tool_match = re.search(tool_pattern, thought, re.IGNORECASE)
            if tool_match:
                tool_name = tool_match.group(1).lower().strip()
                param_match = re.search(param_pattern, thought, re.IGNORECASE | re.DOTALL)

                if param_match:
                    params_str = param_match.group(1).strip().strip('`')
                    params = self._try_parse_json(params_str)
                    if params:
                        return {"tool": tool_name, "params": params}

        # ===== 策略3: 宽松搜索 (Fallback) =====
        return self._fallback_action_parse(thought)

    def _extract_function_params(self, tool_name: str, params_raw: str) -> Dict:
        """
        从函数式参数字符串中提取参数
        例如: expression="(234 * 567) + 890" 或 code="print('hi')", language="python"
        """
        import json

        # 尝试直接解析为JSON
        params = self._try_parse_json(params_raw)
        if params:
            return params

        # 尝试解析 key=value 格式
        kv_params = {}

        # 使用正则提取所有 key="value" 或 key='value' 对
        kv_pattern = r'(\w+)\s*=\s*["\']([^"\']*)["\']'
        kv_matches = re.findall(kv_pattern, params_raw)

        if kv_matches:
            for key, value in kv_matches:
                kv_params[key] = value
            return kv_params

        # 如果只有单个值（没有key=），根据工具类型推断
        if params_raw and not kv_params:
            clean_param = params_raw.strip('"\' ')

            if tool_name == "calculator":
                return {"expression": clean_param}
            elif tool_name == "code_executor":
                # 可能是代码片段
                return {"code": clean_param, "language": "python"}
            elif tool_name == "web_search":
                return {"query": clean_param}
            elif tool_name == "file_manager":
                return {
                    "action": "write",
                    "path": "output.txt",
                    "content": clean_param
                }

        return kv_params if kv_params else None

    def _try_parse_json(self, text: str) -> Optional[Dict]:
        """尝试解析JSON字符串"""
        try:
            import json
            data = json.loads(text)
            if isinstance(data, dict):
                return data
        except (json.JSONDecodeError, TypeError):
            pass

        # 尝试修复常见的JSON格式问题
        try:
            import json
            # 移除可能的markdown标记
            cleaned = text.strip().strip('`').strip()
            data = json.loads(cleaned)
            if isinstance(data, dict):
                return data
        except:
            pass

        return None

    def _fallback_action_parse(self, thought: str) -> Optional[Dict]:
        """Fallback: 更宽松的解析策略"""
        available_tools = [t.name for t in tool_registry.get_all_tools()]
        found_tools = []

        for tool_name in available_tools:
            # 检查各种形式的工具名提及
            patterns = [
                rf'\b{re.escape(tool_name)}\b',
                rf'{re.escape(tool_name.replace("_", " "))}',
                rf'{re.escape(tool_name.replace("_", "-"))}',
            ]

            for pattern in patterns:
                if re.search(pattern, thought, re.IGNORECASE):
                    found_tools.append(tool_name)
                    break

        if not found_tools:
            return None

        # 使用第一个找到的工具
        tool_name = found_tools[0]

        # 尝试从thought中提取相关内容作为参数
        params = self._infer_parameters_from_context(tool_name, thought)

        if params:
            logger.info(f"Fallback parsed action: {tool_name}")
            return {"tool": tool_name, "params": params}

        return None

    def _infer_parameters_from_context(self, tool_name: str, context: str) -> Optional[Dict]:
        """根据上下文推断工具参数"""
        if tool_name == "calculator":
            # 查找数学表达式
            math_match = re.search(r'计算[：:]?\s*(.+?)(?:[。\n]|$)', context)
            if math_match:
                return {"expression": math_match.group(1).strip()}

        elif tool_name == "code_executor":
            # 查找代码块
            code_match = re.search(r'```(?:python)?\s*\n?(.*?)```', context, re.DOTALL)
            if code_match:
                return {"code": code_match.group(1).strip(), "language": "python"}

        elif tool_name == "file_manager":
            # 查找文件操作意图
            if any(word in context for word in ['保存', '写入', 'save', 'write', '存储']):
                return {
                    "action": "write",
                    "path": "output.txt",
                    "content": "[待生成的内容]"
                }

        elif tool_name == "web_search":
            # 查找搜索关键词
            search_match = re.search(r'(?:搜索|查找|search)[：:]?\s*(.+?)(?:[。\n]|$)', context)
            if search_match:
                return {"query": search_match.group(1).strip()}

        return None
    
    def _is_final_answer(self, content: str) -> bool:
        """Check if the thought contains a final answer"""
        final_indicators = [
            "**Final Answer**:",
            "**最终答案**:",
            "Final Answer:",
            "最终答案：",
            "I can now conclude",
            "Based on my analysis",
            "In conclusion",
            "综上所述",
            "因此",
        ]
        
        content_lower = content.lower()
        return any(indicator.lower() in content_lower 
                  for indicator in final_indicators)
    
    def _extract_final_answer(self, content: str) -> str:
        """Extract the final answer from thought content"""
        patterns = [
            r'\*\*Final Answer:\*\*\s*(.+?)(?:\n\n|\Z)',
            r'\*\*最终答案:\*\*\s*(.+?)(?:\n\n|\Z)',
            r'Final Answer:\s*(.+?)(?:\n\n|\Z)',
            r'最终答案[：:]\s*(.+?)(?:\n\n|\Z)',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, content, re.DOTALL | re.IGNORECASE)
            if match:
                return match.group(1).strip()
        
        # Return last paragraph as fallback
        paragraphs = content.split('\n\n')
        return paragraphs[-1].strip() if paragraphs else content
    
    def _format_history(
        self,
        history: Optional[List[Message]],
    ) -> str:
        """Format conversation history for prompts"""
        if not history:
            return ""
        
        formatted = []
        for msg in history[-6:]:  # Last 6 messages
            role_label = {
                "user": "用户",
                "assistant": "助手",
                "system": "系统",
            }.get(msg.role, msg.role)
            formatted.append(f"{role_label}: {msg.content}")
        
        return "\n".join(formatted)
    
    def _summarize_progress(self, result: PlanExecutionResult) -> str:
        """Generate summary of progress when max iterations reached"""
        parts = []
        
        parts.append(f"Completed {result.steps_completed} steps:")
        
        for i, (thought, action, obs) in enumerate(
            zip(result.thoughts, result.actions, result.observations), 1
        ):
            parts.append(f"\nStep {i}:")
            parts.append(f"  Thought: {thought.content[:200]}...")
            if action:
                parts.append(f"  Action: Called {action.tool_name}")
            if obs:
                status = "✓" if obs.success else "✗"
                parts.append(f"  Result: {status} {str(obs.result)[:200]}...")
        
        return "\n".join(parts)
    
    @property
    def state(self) -> PlannerState:
        """Current planner state"""
        return self._state
    
    @property
    def current_step(self) -> int:
        """Current step number in the ReAct loop"""
        return self._current_step
    
    def __repr__(self) -> str:
        return (
            f"ReActPlanner(state={self.state.value}, "
            f"step={self.current_step}, "
            f"max_iter={self.max_iterations})"
        )
