"""
Agent Core Engine
Main orchestrator that integrates all components: LLM, Memory, Tools, and Planner
"""
import asyncio
import uuid
from typing import Any, Dict, List, Optional, AsyncIterator, Callable
from dataclasses import dataclass, field
from datetime import datetime

from .planner import ReActPlanner, PlanExecutionResult, PlannerState
from ..llm.provider import DeepSeekProvider, Message, LLMResponse
from ..llm.prompts import PromptTemplates
from ..memory.short_term import ShortTermMemory
from ..memory.long_term import LongTermMemory
from ..memory.working_memory import WorkingMemory
from ..tools.base import tool_registry, BaseTool
from ..utils.config import get_config, ConfigManager
from ..utils.logger import get_logger, log_execution_time

logger = get_logger(__name__)


@dataclass
class AgentResponse:
    """Standardized response from the agent"""
    session_id: str
    response: str
    success: bool
    timestamp: datetime = field(default_factory=datetime.now)
    metadata: Dict[str, Any] = field(default_factory=dict)
    reasoning_trace: Optional[List[Dict]] = None
    token_usage: Dict[str, int] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API responses"""
        return {
            "session_id": self.session_id,
            "response": self.response,
            "success": self.success,
            "timestamp": self.timestamp.isoformat(),
            "metadata": self.metadata,
            "reasoning_trace": self.reasoning_trace,
            "token_usage": self.token_usage,
        }


@dataclass
class SessionInfo:
    """Information about an active conversation session"""
    session_id: str
    created_at: datetime = field(default_factory=datetime.now)
    message_count: int = 0
    last_activity: datetime = field(default_factory=datetime.now)


class Agent:
    """
    DeepSeek Conversational Agent - Core Engine
    
    This is the main class that integrates all subsystems:
    - **LLM Provider**: DeepSeek API integration with streaming support
    - **Memory System**: Short-term (conversation), Long-term (vector DB), Working (task state)
    - **Tool System**: Extensible tool registry with built-in tools
    - **ReAct Planner**: Reasoning loop for complex task execution
    
    Features:
    ✅ Multi-turn conversations with context management
    ✅ Semantic memory retrieval and storage
    ✅ Tool calling and function execution
    ✅ ReAct reasoning for complex queries
    ✅ Streaming responses
    ✅ Session management
    ✅ Comprehensive error handling
    
    Usage:
        # Initialize agent
        agent = Agent()
        await agent.initialize()
        
        # Simple chat
        response = await agent.chat("Hello!")
        print(response.response)
        
        # Complex task with reasoning
        response = await agent.process("What's the weather in Beijing?")
        print(response.response)
        print(response.reasoning_trace)  # See the thinking process
        
        # Streaming
        async for chunk in agent.chat_stream("Tell me a story"):
            print(chunk, end="", flush=True)
        
        # Cleanup
        await agent.close()
    """
    
    def __init__(
        self,
        config_path: Optional[str] = None,
        auto_initialize: bool = True,
    ):
        """
        Initialize the Agent
        
        Args:
            config_path: Path to configuration file (optional)
            auto_initialize: Whether to automatically initialize on creation
        """
        # Configuration
        self.config_manager = get_config(config_path)
        self.config = self.config_manager.config
        
        # Component placeholders (initialized in initialize())
        self._llm: Optional[DeepSeekProvider] = None
        self._short_memory: Optional[ShortTermMemory] = None
        self._long_memory: Optional[LongTermMemory] = None
        self._working_memory: Optional[WorkingMemory] = None
        self._planner: Optional[ReActPlanner] = None
        
        # Session management
        self._sessions: Dict[str, SessionInfo] = {}
        self._current_session_id: Optional[str] = None
        
        # State tracking
        self._initialized: bool = False
        self._total_requests: int = 0
        self._start_time: datetime = datetime.now()
        
        logger.info("Agent instance created")
        
        if auto_initialize:
            # Don't auto-initialize here, let user call it explicitly
            pass
    
    async def initialize(self) -> None:
        """
        Initialize all agent components
        
        Call this before using the agent.
        """
        if self._initialized:
            logger.warning("Agent already initialized")
            return
        
        logger.info("=" * 60)
        logger.info("Initializing DeepSeek Agent...")
        logger.info("=" * 60)
        
        try:
            # 1. Initialize LLM Provider
            logger.info("[1/5] Initializing LLM provider...")
            self._llm = DeepSeekProvider(self.config.llm)
            
            # 2. Initialize Memory Systems
            logger.info("[2/5] Initializing memory systems...")
            self._short_memory = ShortTermMemory(
                window_size=self.config.memory.short_term.window_size,
                max_tokens=self.config.memory.short_term.max_tokens,
            )

            # 暂时禁用长期记忆以避免ChromaDB模型下载阻塞
            self._long_memory = None  # LongTermMemory(...)  # 暂时注释掉
            logger.info("Long-term memory disabled (to avoid ChromaDB download blocking)")

            self._working_memory = WorkingMemory()
            
            # 3. Register Built-in Tools
            logger.info("[3/5] Registering tools...")
            self._register_builtin_tools()
            
            # 4. Initialize ReAct Planner
            logger.info("[4/5] Initializing ReAct planner...")
            self._planner = ReActPlanner(
                llm_provider=self._llm,
                short_term_memory=self._short_memory,
                long_term_memory=self._long_memory,
                max_iterations=self.config.agent.max_iterations,
                verbose=self.config.agent.thinking_verbose,
            )
            
            # 5. Create default session
            logger.info("[5/5] Setting up session management...")
            self._current_session_id = self._create_session()
            
            self._initialized = True
            
            logger.info("=" * 60)
            logger.info("✅ Agent initialized successfully!")
            logger.info(f"   Model: {self.config.llm.model}")
            logger.info(f"   Tools registered: {tool_registry.count}")
            logger.info(f"   Long-term memories: {self._long_memory.count if self._long_memory else 0}")
            logger.info(f"   Max ReAct iterations: {self.config.agent.max_iterations}")
            logger.info("=" * 60)
            
        except Exception as e:
            logger.error(f"Agent initialization failed: {e}", exc_info=True)
            raise RuntimeError(f"Failed to initialize agent: {e}")
    
    def _register_builtin_tools(self) -> None:
        """Register all built-in tools"""
        # Import tool classes to trigger auto-registration
        from ..tools.web_search import WebSearchTool
        from ..tools.calculator import CalculatorTool
        from ..tools.code_executor import CodeExecutorTool
        from ..tools.file_manager import FileManagerTool
        
        # Enable/disable based on config
        enabled_tools = set(self.config.tools.enabled)
        
        all_tools = {
            "web_search": WebSearchTool,
            "calculator": CalculatorTool,
            "code_executor": CodeExecutorTool,
            "file_manager": FileManagerTool,
        }
        
        for tool_name, tool_class in all_tools.items():
            if tool_name in enabled_tools:
                # Tool is already registered via __init_subclass__
                # Just ensure it's enabled
                tool_registry.enable_tool(tool_name)
                logger.debug(f"Enabled tool: {tool_name}")
            else:
                tool_registry.disable_tool(tool_name)
                logger.debug(f"Disabled tool: {tool_name}")
    
    @log_execution_time(logger, "agent_chat")
    async def chat(
        self,
        message: str,
        session_id: Optional[str] = None,
        **kwargs,
    ) -> AgentResponse:
        """
        Send a message and get a response (simple chat mode)
        
        For simple conversations without ReAct planning.
        Uses direct LLM call with memory context.
        
        Args:
            message: User's message
            session_id: Session ID (uses current if not provided)
            
        Returns:
            AgentResponse with the assistant's reply
        """
        await self._ensure_initialized()
        
        self._total_requests += 1
        session_id = session_id or self._current_session_id or self._create_session()
        
        logger.info(f"\n{'─'*60}")
        logger.info(f"💬 Chat Request [Session: {session_id[:8]}]")
        logger.info(f"User: {message[:100]}...")
        logger.info(f"{'─'*60}\n")
        
        try:
            # Store user message in short-term memory
            self._short_memory.add_user_message(message)
            
            # Build messages with context
            system_prompt = PromptTemplates.get_system_prompt(
                agent_name=self.config.agent.name,
                tools=[{"name": t.name, "description": t.description} 
                       for t in tool_registry.get_all_tools()],
            )
            
            messages = [
                Message(role="system", content=system_prompt),
                *self._short_memory.get_context(),
            ]
            
            # Get LLM response
            response = await self._llm.chat_with_retry(messages)
            
            # Store assistant response
            self._short_memory.add_assistant_message(response.content)
            
            # Update session
            self._update_session(session_id)
            
            # Extract memories periodically (every 5th message)
            if self._total_requests % 5 == 0:
                asyncio.create_task(self._extract_and_store_memories())
            
            agent_response = AgentResponse(
                session_id=session_id,
                response=response.content,
                success=True,
                token_usage=response.usage,
                metadata={
                    "mode": "chat",
                    "model": self.config.llm.model,
                    "message_length": len(message),
                },
            )
            
            logger.info(f"\n✅ Response generated ({len(response.content)} chars)")
            
            return agent_response
            
        except Exception as e:
            logger.error(f"Chat failed: {e}", exc_info=True)
            
            return AgentResponse(
                session_id=session_id,
                response=f"I'm sorry, I encountered an error: {str(e)}",
                success=False,
                metadata={"error": str(e)},
            )
    
    @log_execution_time(logger, "agent_process")
    async def process(
        self,
        input_text: str,
        session_id: Optional[str] = None,
        use_react: bool = True,
        stream_callback: Optional[Callable] = None,
        **kwargs,
    ) -> AgentResponse:
        """
        Process a complex request with full ReAct planning
        
        Use this for tasks that may require tool usage or multi-step reasoning.
        
        Args:
            input_text: User's request
            session_id: Session ID
            use_react: Whether to use ReAct planning (default: True)
            stream_callback: Callback for intermediate results
            
        Returns:
            AgentResponse with final answer and reasoning trace
        """
        await self._ensure_initialized()
        
        self._total_requests += 1
        session_id = session_id or self._current_session_id or self._create_session()
        
        logger.info(f"\n{'='*60}")
        logger.info(f"🎯 Process Request [Session: {session_id[:8]}]")
        logger.info(f"Input: {input_text[:100]}...")
        logger.info(f"Mode: {'ReAct' if use_react else 'Direct'}")
        logger.info(f"{'='*60}\n")
        
        try:
            # Store user message
            self._short_memory.add_user_message(input_text)
            
            if use_react:
                # Use ReAct planner for complex tasks
                result = await self._planner.plan_and_execute(
                    user_input=input_text,
                    conversation_history=self._short_memory.get_context(),
                    stream_callback=stream_callback,
                )
                
                # Store assistant response
                self._short_memory.add_assistant_message(result.final_answer)
                
                response = AgentResponse(
                    session_id=session_id,
                    response=result.final_answer,
                    success=result.success,
                    reasoning_trace=[
                        {
                            "step": i+1,
                            "thought": t.content[:200],
                            "action": result.actions[i].tool_name if i < len(result.actions) else None,
                            "observation_success": result.observations[i].success if i < len(result.observations) else None,
                        }
                        for i, t in enumerate(result.thoughts)
                    ],
                    token_usage=result.token_usage,
                    metadata={
                        "mode": "react",
                        "steps_completed": result.steps_completed,
                        "state": result.state.value,
                        "duration_seconds": result.duration_seconds,
                    },
                )
                
            else:
                # Direct mode (simple chat)
                response = await self.chat(input_text, session_id)
            
            # Update session
            self._update_session(session_id)
            
            # Extract memories
            if self._total_requests % 5 == 0:
                asyncio.create_task(self._extract_and_store_memories())
            
            return response
            
        except Exception as e:
            logger.error(f"Process failed: {e}", exc_info=True)
            
            return AgentResponse(
                session_id=session_id,
                response=f"Processing failed: {str(e)}",
                success=False,
                metadata={"error": str(e)},
            )
    
    async def chat_stream(
        self,
        message: str,
        session_id: Optional[str] = None,
    ) -> AsyncIterator[str]:
        """
        Stream a chat response token by token
        
        Yields:
            String chunks of the response
            
        Usage:
            async for chunk in agent.chat_stream("Hello!"):
                print(chunk, end="", flush=True)
        """
        await self._ensure_initialized()
        
        session_id = session_id or self._current_session_id
        self._short_memory.add_user_message(message)
        
        system_prompt = PromptTemplates.get_system_prompt(
            agent_name=self.config.agent.name,
        )
        
        messages = [
            Message(role="system", content=system_prompt),
            *self._short_memory.get_context(),
        ]
        
        async for chunk in self._llm.chat_stream(messages):
            yield chunk.content
        
        # Note: We'll need to handle storing the complete response
        # This would require buffering the stream
    
    async def _extract_and_store_memories(self) -> None:
        """Extract important information from recent conversations"""
        if not self._long_memory or not self._short_memory:
            return
        
        try:
            conversation = self._short_memory.get_conversation_history()
            
            if conversation and len(conversation) > 50:
                await self._long_memory.extract_and_store(
                    conversation_text=conversation,
                    llm_provider=self._llm,
                )
                
        except Exception as e:
            logger.warning(f"Memory extraction failed: {e}")
    
    def _create_session(self) -> str:
        """Create a new conversation session"""
        session_id = str(uuid.uuid4())
        self._sessions[session_id] = SessionInfo(session_id=session_id)
        logger.debug(f"Created session: {session_id[:8]}")
        return session_id
    
    def _update_session(self, session_id: str) -> None:
        """Update session activity timestamp"""
        if session_id in self._sessions:
            session = self._sessions[session_id]
            session.message_count += 1
            session.last_activity = datetime.now()
    
    async def _ensure_initialized(self) -> None:
        """Ensure agent is initialized before use"""
        if not self._initialized:
            logger.info("Auto-initializing agent...")
            await self.initialize()
    
    def get_status(self) -> Dict[str, Any]:
        """
        Get comprehensive agent status information
        
        Returns:
            Dictionary with status details
        """
        uptime = (datetime.now() - self._start_time).total_seconds()
        
        return {
            "initialized": self._initialized,
            "uptime_seconds": round(uptime, 2),
            "config": {
                "model": self.config.llm.model,
                "provider": self.config.llm.provider,
                "agent_name": self.config.agent.name,
            },
            "statistics": {
                "total_requests": self._total_requests,
                "active_sessions": len(self._sessions),
                "tools_available": tool_registry.count,
            },
            "memory": {
                "short_term_conversations": self._short_memory.size if self._short_memory else 0,
                "long_term_memories": self._long_memory.count if self._long_memory else 0,
                "has_active_task": self._working_memory.has_active_task if self._working_memory else False,
            },
            "llm_stats": self._llm.stats if self._llm else {},
        }
    
    def list_sessions(self) -> List[Dict[str, Any]]:
        """List all active sessions"""
        return [
            {
                "session_id": s.session_id[:8] + "...",
                "created_at": s.created_at.isoformat(),
                "message_count": s.message_count,
                "last_activity": s.last_activity.isoformat(),
            }
            for s in self._sessions.values()
        ]
    
    def clear_session(self, session_id: Optional[str] = None) -> bool:
        """Clear a specific session or current session"""
        target_id = session_id or self._current_session_id
        
        if target_id and target_id in self._sessions:
            del self._sessions[target_id]
            
            if target_id == self._current_session_id:
                self._current_session_id = self._create_session()
                if self._short_memory:
                    self._short_memory.clear()
            
            logger.info(f"Cleared session: {target_id[:8]}")
            return True
        
        return False
    
    async def reset(self) -> None:
        """Reset agent to initial state (clear everything)"""
        logger.warning("Resetting agent...")
        
        if self._short_memory:
            self._short_memory.clear()
        
        if self._working_memory:
            self._working_memory.clear()
        
        self._sessions.clear()
        self._current_session_id = self._create_session()
        self._total_requests = 0
        
        if self._llm:
            self._llm.reset_stats()
        
        logger.info("Agent reset complete")
    
    async def close(self) -> None:
        """
        Cleanly close the agent and release resources
        
        Always call this when done using the agent.
        """
        logger.info("Closing agent...")
        
        try:
            if self._llm:
                await self._llm.close()
            
            if self._long_memory:
                await self._long_memory.close()
            
            self._initialized = False
            
            logger.info("Agent closed successfully")
            
        except Exception as e:
            logger.error(f"Error closing agent: {e}")
    
    async def __aenter__(self):
        """Async context manager entry"""
        await self.initialize()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        await self.close()
    
    def __repr__(self) -> str:
        status = "✅ Initialized" if self._initialized else "⏳ Not initialized"
        return (
            f"Agent({status}, "
            f"model={self.config.llm.model}, "
            f"requests={self._total_requests})"
        )


# Convenience function for quick usage
async def create_agent(
    config_path: Optional[str] = None,
) -> Agent:
    """
    Quick factory function to create and initialize an agent
    
    Usage:
        agent = await create_agent()
        response = await agent.chat("Hello!")
        await agent.close()
    """
    agent = Agent(config_path=config_path)
    await agent.initialize()
    return agent
