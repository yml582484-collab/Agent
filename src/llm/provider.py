"""
DeepSeek LLM Provider Interface
Handles communication with DeepSeek API including streaming, retries, and token management
"""
import json
import asyncio
from typing import AsyncIterator, Optional, Any, Dict, List
from dataclasses import dataclass, field
from openai import AsyncOpenAI
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
)

from ..utils.config import get_config
from ..utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class Message:
    """Represents a chat message"""
    role: str  # "system", "user", "assistant", "tool"
    content: str
    name: Optional[str] = None
    tool_call_id: Optional[str] = None
    tool_calls: Optional[List[Dict]] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class LLMResponse:
    """Structured response from LLM"""
    content: str
    model: str
    finish_reason: str
    usage: Dict[str, int] = field(default_factory=dict)
    tool_calls: Optional[List[Dict]] = None
    raw_response: Optional[Any] = None


@dataclass
class TokenUsage:
    """Token usage statistics"""
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    
    def to_dict(self) -> Dict[str, int]:
        return {
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.total_tokens,
        }


class DeepSeekProvider:
    """
    DeepSeek LLM Provider
    
    Features:
    - Async streaming and non-streaming calls
    - Automatic retry with exponential backoff
    - Token usage tracking
    - Rate limiting awareness
    - Structured message handling
    
    Usage:
        provider = DeepSeekProvider()
        
        # Non-streaming
        response = await provider.chat(messages)
        print(response.content)
        
        # Streaming
        async for chunk in provider.chat_stream(messages):
            print(chunk.content, end="")
    """
    
    def __init__(self, config=None):
        """
        Initialize the DeepSeek provider
        
        Args:
            config: Optional configuration object (uses global config if not provided)
        """
        self.config = config or get_config().config.llm
        self.client = self._create_client()
        self._token_usage = TokenUsage()
        self._total_calls = 0
        self._total_errors = 0
        
        logger.info(
            f"Initialized DeepSeek provider with model {self.config.model}"
        )
    
    def _create_client(self) -> AsyncOpenAI:
        """Create OpenAI-compatible client for DeepSeek"""
        api_key = getattr(self.config, 'api_key', None) or \
                  __import__('os').getenv('DEEPSEEK_API_KEY')
        
        if not api_key:
            raise ValueError(
                "DeepSeek API key not configured. "
                "Set DEEPSEEK_API_KEY environment variable or in config.yaml"
            )
        
        return AsyncOpenAI(
            api_key=api_key,
            base_url=self.config.api_base,
        )
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type(Exception),
    )
    async def chat(
        self,
        messages: List[Message],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        tools: Optional[List[Dict]] = None,
        tool_choice: Optional[str] = None,
        **kwargs,
    ) -> LLMResponse:
        """
        Send a non-streaming chat completion request
        
        Args:
            messages: List of Message objects
            temperature: Sampling temperature (overrides config)
            max_tokens: Max tokens in response (overrides config)
            tools: Available tools for function calling
            tool_choice: Tool selection strategy ("auto", "none", "required")
            **kwargs: Additional OpenAI API parameters
            
        Returns:
            LLMResponse object with content and metadata
        """
        try:
            self._total_calls += 1
            
            # Convert messages to OpenAI format
            openai_messages = [
                self._message_to_dict(msg) for msg in messages
            ]
            
            logger.debug(
                f"Sending chat request ({len(openai_messages)} messages)"
            )
            
            response = await self.client.chat.completions.create(
                model=self.config.model,
                messages=openai_messages,
                temperature=temperature or self.config.temperature,
                max_tokens=max_tokens or self.config.max_tokens,
                stream=False,
                tools=tools,
                tool_choice=tool_choice,
                **kwargs,
            )
            
            # Parse response
            llm_response = self._parse_response(response)
            
            # Update token usage
            if response.usage:
                self._token_usage.prompt_tokens += response.usage.prompt_tokens
                self._token_usage.completion_tokens += response.usage.completion_tokens
                self._token_usage.total_tokens += response.usage.total_tokens
            
            logger.debug(
                f"Received response ({len(llm_response.content)} chars, "
                f"{response.usage.total_tokens if response.usage else 0} tokens)"
            )
            
            return llm_response
            
        except Exception as e:
            self._total_errors += 1
            logger.error(f"Chat request failed: {e}")
            raise
    
    async def chat_stream(
        self,
        messages: List[Message],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        tools: Optional[List[Dict]] = None,
        **kwargs,
    ) -> AsyncIterator[LLMResponse]:
        """
        Send a streaming chat completion request
        
        Yields:
            LLMResponse objects for each chunk
            
        Usage:
            async for chunk in provider.chat_stream(messages):
                print(chunk.content, end="", flush=True)
        """
        try:
            self._total_calls += 1
            
            openai_messages = [
                self._message_to_dict(msg) for msg in messages
            ]
            
            logger.debug("Sending streaming chat request")
            
            stream = await self.client.chat.completions.create(
                model=self.config.model,
                messages=openai_messages,
                temperature=temperature or self.config.temperature,
                max_tokens=max_tokens or self.config.max_tokens,
                stream=True,
                tools=tools,
                **kwargs,
            )
            
            async for chunk in stream:
                if chunk.choices and chunk.choices[0].delta.content:
                    yield LLMResponse(
                        content=chunk.choices[0].delta.content or "",
                        model=self.config.model,
                        finish_reason=chunk.choices[0].finish_reason or "",
                    )
                    
        except Exception as e:
            self._total_errors += 1
            logger.error(f"Streaming chat request failed: {e}")
            raise
    
    async def chat_with_retry(
        self,
        messages: List[Message],
        max_retries: int = 3,
        **kwargs,
    ) -> LLMResponse:
        """
        Chat with automatic retry on empty/invalid responses
        
        Args:
            messages: Chat messages
            max_retries: Maximum number of retry attempts
            **kwargs: Additional arguments passed to chat()
            
        Returns:
            Valid LLMResponse
        """
        last_error = None
        
        for attempt in range(max_retries):
            try:
                response = await self.chat(messages, **kwargs)
                
                # Validate response
                if response.content and len(response.content.strip()) > 0:
                    return response
                
                logger.warning(
                    f"Empty response on attempt {attempt + 1}, retrying..."
                )
                
            except Exception as e:
                last_error = e
                logger.warning(
                    f"Request failed on attempt {attempt + 1}: {e}"
                )
                
                if attempt < max_retries - 1:
                    await asyncio.sleep(1 * (attempt + 1))  # Exponential backoff
        
        raise RuntimeError(
            f"Failed after {max_retries} attempts. Last error: {last_error}"
        )
    
    def _message_to_dict(self, message: Message) -> Dict:
        """Convert Message object to OpenAI format"""
        msg_dict = {
            "role": message.role,
            "content": message.content,
        }
        
        if message.name:
            msg_dict["name"] = message.name
        
        if message.tool_call_id:
            msg_dict["tool_call_id"] = message.tool_call_id
        
        if message.tool_calls:
            msg_dict["tool_calls"] = message.tool_calls
        
        return msg_dict
    
    def _parse_response(self, response: Any) -> LLMResponse:
        """Parse OpenAI response into LLMResponse"""
        choice = response.choices[0]
        
        return LLMResponse(
            content=choice.message.content or "",
            model=response.model,
            finish_reason=choice.finish_reason,
            usage={
                "prompt_tokens": response.usage.prompt_tokens if response.usage else 0,
                "completion_tokens": response.usage.completion_tokens if response.usage else 0,
                "total_tokens": response.usage.total_tokens if response.usage else 0,
            },
            tool_calls=choice.message.tool_calls,
            raw_response=response,
        )
    
    @property
    def token_usage(self) -> TokenUsage:
        """Get current token usage statistics"""
        return self._token_usage
    
    @property
    def stats(self) -> Dict[str, Any]:
        """Get provider statistics"""
        return {
            "total_calls": self._total_calls,
            "total_errors": self._total_errors,
            "success_rate": (
                (self._total_calls - self._total_errors) / self._total_calls * 100
                if self._total_calls > 0
                else 0
            ),
            "token_usage": self._token_usage.to_dict(),
        }
    
    def reset_stats(self) -> None:
        """Reset usage statistics"""
        self._token_usage = TokenUsage()
        self._total_calls = 0
        self._total_errors = 0
    
    async def close(self) -> None:
        """Close the client connection"""
        await self.client.close()
        logger.debug("DeepSeek provider closed")


# Convenience functions
def create_message(
    role: str,
    content: str,
    **kwargs,
) -> Message:
    """Create a new Message object"""
    return Message(role=role, content=content, **kwargs)


def create_system_message(content: str) -> Message:
    """Create a system message"""
    return create_message("system", content)


def create_user_message(content: str) -> Message:
    """Create a user message"""
    return create_message("user", content)


def create_assistant_message(
    content: str,
    tool_calls: Optional[List[Dict]] = None,
) -> Message:
    """Create an assistant message"""
    return create_message("assistant", content, tool_calls=tool_calls)


def create_tool_message(
    content: str,
    tool_call_id: str,
    tool_name: str = None,
) -> Message:
    """Create a tool result message"""
    return create_message(
        "tool",
        content,
        name=tool_name,
        tool_call_id=tool_call_id,
    )
