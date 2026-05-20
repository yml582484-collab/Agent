"""
Short-term Memory System
Manages recent conversation context with sliding window and token management
"""
from collections import deque
from typing import List, Optional, Dict, Any
from dataclasses import dataclass, field
from datetime import datetime

from ..llm.provider import Message
from ..utils.config import get_config
from ..utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class ConversationTurn:
    """Represents a single conversation turn"""
    user_message: Optional[Message] = None
    assistant_message: Optional[Message] = None
    timestamp: datetime = field(default_factory=datetime.now)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    @property
    def is_complete(self) -> bool:
        """Check if this turn has both user and assistant messages"""
        return self.user_message is not None and \
               self.assistant_message is not None


class ShortTermMemory:
    """
    Short-term Memory with Sliding Window
    
    Features:
    - Maintain recent N conversation turns
    - Token count tracking and management
    - Conversation context retrieval
    - Message compression when approaching limits
    
    Usage:
        memory = ShortTermMemory(window_size=10)
        
        memory.add_user_message("Hello!")
        memory.add_assistant_message("Hi! How can I help?")
        
        context = memory.get_context()  # Get all messages
        recent = memory.get_recent(5)  # Get last 5 turns
    """
    
    def __init__(
        self,
        window_size: Optional[int] = None,
        max_tokens: Optional[int] = None,
    ):
        """
        Initialize short-term memory
        
        Args:
            window_size: Maximum number of conversation turns to keep
            max_tokens: Maximum total tokens in memory
        """
        config = get_config().config.memory.short_term
        
        self.window_size = window_size or config.window_size
        self.max_tokens = max_tokens or config.max_tokens
        
        # Use deque for efficient sliding window
        self._conversations: deque[ConversationTurn] = deque(
            maxlen=self.window_size
        )
        
        # Track token counts (approximate)
        self._total_tokens: int = 0
        self._current_turn: Optional[ConversationTurn] = None
        
        logger.info(
            f"ShortTermMemory initialized "
            f"(window={self.window_size}, max_tokens={self.max_tokens})"
        )
    
    def add_user_message(
        self,
        content: str,
        metadata: Optional[Dict] = None,
    ) -> None:
        """
        Add a user message to current conversation turn
        
        Args:
            content: User message text
            metadata: Additional metadata for this message
        """
        message = Message(role="user", content=content)
        
        if self._current_turn is None or \
           self._current_turn.is_complete:
            # Start new turn
            self._current_turn = ConversationTurn(
                user_message=message,
                timestamp=datetime.now(),
                metadata=metadata or {},
            )
            self._conversations.append(self._current_turn)
        else:
            # Update existing turn's user message
            self._current_turn.user_message = message
        
        self._update_token_count(content)
        logger.debug(f"Added user message ({len(content)} chars)")
    
    def add_assistant_message(
        self,
        content: str,
        metadata: Optional[Dict] = None,
    ) -> None:
        """
        Add an assistant response to current conversation turn
        
        Args:
            content: Assistant response text
            metadata: Additional metadata for this message
        """
        if self._current_turn is None:
            logger.warning("Adding assistant message without user message")
            self._current_turn = ConversationTurn()
            self._conversations.append(self._current_turn)
        
        message = Message(role="assistant", content=content)
        self._current_turn.assistant_message = message
        self._current_turn.metadata.update(metadata or {})
        
        self._update_token_count(content)
        logger.debug(f"Added assistant message ({len(content)} chars)")
    
    def add_tool_result(
        self,
        tool_name: str,
        result: str,
        tool_call_id: str,
    ) -> None:
        """
        Add a tool execution result to the conversation
        
        Args:
            tool_name: Name of the tool that was called
            result: Tool execution result
            tool_call_id: ID of the tool call
        """
        content = f"[Tool: {tool_name}]\n{result}"
        message = Message(
            role="tool",
            content=content,
            name=tool_name,
            tool_call_id=tool_call_id,
        )
        
        # Add as part of current turn
        if self._current_turn:
            self._current_turn.metadata["last_tool_call"] = {
                "name": tool_name,
                "call_id": tool_call_id,
            }
        
        # Store in conversations as special message type
        # (simplified - could be enhanced)
        self._update_token_count(content)
        logger.debug(f"Added tool result from {tool_name}")
    
    def get_context(self) -> List[Message]:
        """
        Get all messages in conversation context
        
        Returns:
            List of Message objects in chronological order
        """
        messages = []
        
        for turn in self._conversations:
            if turn.user_message:
                messages.append(turn.user_message)
            
            # Add tool results if present
            if "tool_results" in turn.metadata:
                for tool_result in turn.metadata["tool_results"]:
                    messages.append(tool_result)
            
            if turn.assistant_message:
                messages.append(turn.assistant_message)
        
        return messages
    
    def get_recent(self, n_turns: int = 5) -> List[Message]:
        """
        Get messages from most recent N conversation turns
        
        Args:
            n_turns: Number of recent turns to retrieve
            
        Returns:
            List of recent messages
        """
        recent_turns = list(self._conversations)[-n_turns:]
        messages = []
        
        for turn in recent_turns:
            if turn.user_message:
                messages.append(turn.user_message)
            if turn.assistant_message:
                messages.append(turn.assistant_message)
        
        return messages
    
    def get_conversation_history(self) -> str:
        """
        Get formatted conversation history string for prompts
        
        Returns:
            Formatted conversation history
        """
        history_parts = []
        
        for i, turn in enumerate(self._conversations, 1):
            if turn.user_message:
                history_parts.append(
                    f"用户 [{i}]: {turn.user_message.content}"
                )
            if turn.assistant_message:
                history_parts.append(
                    f"助手 [{i}]: {turn.assistant_message.content}"
                )
        
        return "\n".join(history_parts) if history_parts else "（无历史记录）"
    
    def clear(self) -> None:
        """Clear all conversation history"""
        self._conversations.clear()
        self._total_tokens = 0
        self._current_turn = None
        logger.info("Short-term memory cleared")
    
    @property
    def size(self) -> int:
        """Number of conversation turns in memory"""
        return len(self._conversations)
    
    @property
    def token_count(self) -> int:
        """Estimated total tokens in memory"""
        return self._total_tokens
    
    @property
    def is_empty(self) -> bool:
        """Check if memory is empty"""
        return len(self._conversations) == 0
    
    def _update_token_count(self, text: str) -> None:
        """Update estimated token count (rough: 1 token ≈ 4 chars for Chinese)"""
        # Simple estimation: ~4 characters per token for mixed Chinese/English
        estimated_tokens = len(text) // 4 + 1
        self._total_tokens += estimated_tokens
        
        # Check if we need to compress
        if self._total_tokens > self.max_tokens * 0.8:
            logger.warning(
                f"Approaching token limit ({self._total_tokens}/{self.max_tokens})"
            )
            self._compress_if_needed()
    
    def _compress_if_needed(self) -> None:
        """Compress old conversations if needed"""
        if self._total_tokens <= self.max_tokens:
            return
        
        # Remove oldest turns until under limit
        while (
            self._conversations and 
            self._total_tokens > self.max_tokens * 0.7
        ):
            oldest = self._conversations.popleft()
            if oldest.user_message:
                self._total_tokens -= len(oldest.user_message.content) // 4 + 1
            if oldest.assistant_message:
                self._total_tokens -= len(oldest.assistant_message.content) // 4 + 1
            
            logger.debug("Removed oldest conversation turn to manage tokens")
    
    def to_dict(self) -> Dict[str, Any]:
        """Export memory state to dictionary"""
        return {
            "window_size": self.window_size,
            "max_tokens": self.max_tokens,
            "current_size": self.size,
            "token_count": self._total_tokens,
            "turns": [
                {
                    "user": turn.user_message.content if turn.user_message else None,
                    "assistant": turn.assistant_message.content if turn.assistant_message else None,
                    "timestamp": turn.timestamp.isoformat(),
                }
                for turn in self._conversations
            ],
        }
    
    def __repr__(self) -> str:
        return (
            f"ShortTermMemory(size={self.size}, "
            f"tokens≈{self._total_tokens}, "
            f"max_window={self.window_size})"
        )
