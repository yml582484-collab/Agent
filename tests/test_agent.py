"""
Integration Tests for Agent Core
Tests the complete agent workflow including initialization, chat, and ReAct planning
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


class TestAgentInitialization:
    """Tests for agent initialization process"""
    
    @pytest.mark.asyncio
    async def test_agent_creation(self):
        """Test that agent instance can be created"""
        from src.agent.core import Agent
        
        agent = Agent(auto_initialize=False)
        
        assert agent is not None
        assert agent._initialized is False
    
    @pytest.mark.asyncio
    async def test_agent_status_before_init(self):
        """Test status before initialization"""
        from src.agent.core import Agent
        
        agent = Agent(auto_initialize=False)
        status = agent.get_status()
        
        assert status["initialized"] is False
        assert status["total_requests"] == 0


class TestAgentChat:
    """Tests for simple chat functionality"""
    
    @pytest.mark.asyncio
    async def test_chat_response_structure(self):
        """Test that chat returns proper response structure"""
        # Mock LLM provider
        with patch('src.agent.core.DeepSeekProvider') as MockProvider:
            mock_provider_instance = AsyncMock()
            MockProvider.return_value = mock_provider_instance
            
            # Configure mock responses
            mock_response = MagicMock()
            mock_response.content = "Hello! How can I help you today?"
            mock_response.usage = {"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30}
            mock_provider_instance.chat_with_retry.return_value = mock_response
            mock_provider_instance.token_usage.to_dict.return_value = {"total_tokens": 30}
            mock_provider_instance.stats = {"total_calls": 1, "total_errors": 0}
            
            with patch('src.agent.core.LongTermMemory') as MockMemory:
                mock_memory = AsyncMock()
                mock_memory.initialize.return_value = None
                mock_memory.count = 0
                MockMemory.return_value = mock_memory
                
                # Create and initialize agent
                agent = Agent(auto_initialize=False)
                
                try:
                    await agent.initialize()
                    
                    # Send chat message
                    response = await agent.chat("Hello!")
                    
                    # Verify response structure
                    assert hasattr(response, 'session_id')
                    assert hasattr(response, 'response')
                    assert hasattr(response, 'success')
                    assert hasattr(response, 'token_usage')
                    assert response.success is True
                    assert isinstance(response.response, str)
                    
                finally:
                    if agent._initialized:
                        await agent.close()


class TestAgentSessionManagement:
    """Tests for session management"""
    
    @pytest.mark.asyncio
    async def test_session_creation(self):
        """Test that sessions are created automatically"""
        from src.agent.core import Agent
        
        agent = Agent(auto_initialize=False)
        
        session_id = agent._create_session()
        
        assert session_id is not None
        assert session_id in agent._sessions
        assert len(agent._sessions) == 1
    
    @pytest.mark.asyncio
    async def test_session_listing(self):
        """Test listing active sessions"""
        from src.agent.core import Agent
        
        agent = Agent(auto_initialize=False)
        
        # Create multiple sessions
        s1 = agent._create_session()
        s2 = agent._create_session()
        s3 = agent._create_session()
        
        sessions = agent.list_sessions()
        
        assert len(sessions) == 3
    
    @pytest.mark.asyncio
    async def test_session_clearing(self):
        """Test clearing/deleting sessions"""
        from src.agent.core import Agent
        
        agent = Agent(auto_initialize=False)
        
        session_id = agent._create_session()
        assert session_id in agent._sessions
        
        # Clear session
        success = agent.clear_session(session_id)
        
        assert success is True
        assert session_id not in agent._sessions


class TestAgentReset:
    """Tests for agent reset functionality"""
    
    @pytest.mark.asyncio
    async def test_reset_clears_state(self):
        """Test that reset clears all state"""
        from src.agent.core import Agent
        
        agent = Agent(auto_initialize=False)
        
        # Simulate some activity
        agent._total_requests = 10
        agent._create_session()
        agent._create_session()
        
        # Reset
        import asyncio
        await agent.reset()
        
        assert agent._total_requests == 0
        assert len(agent._sessions) == 1  # One new default session


class TestAgentStatus:
    """Tests for status reporting"""
    
    def test_status_includes_all_sections(self):
        """Test that status includes expected sections"""
        from src.agent.core import Agent
        
        agent = Agent(auto_initialize=False)
        status = agent.get_status()
        
        # Verify all sections present
        assert "initialized" in status
        assert "uptime_seconds" in status
        assert "config" in status
        assert "statistics" in status
        assert "memory" in status
        assert "llm_stats" in status


class TestAgentContextManager:
    """Tests for async context manager usage"""
    
    @pytest.mark.asyncio
    async def test_async_with_statement(self):
        """Test using agent as async context manager"""
        with patch('src.agent.core.DeepSeekProvider') as MockProvider:
            mock_provider = AsyncMock()
            MockProvider.return_value = mock_provider
            mock_provider.chat_with_retry.return_value = MagicMock(
                content="Test response",
                usage={"total_tokens": 30},
            )
            mock_provider.token_usage.to_dict.return_value = {}
            mock_provider.stats = {}
            
            with patch('src.agent.core.LongTermMemory') as MockMemory:
                mock_memory = AsyncMock()
                mock_memory.initialize.return_value = None
                mock_memory.count = 0
                MockMemory.return_value = mock_memory
                
                async with Agent(auto_initialize=False) as agent:
                    assert agent._initialized is True
                    
                    # Agent should be usable here
                    status = agent.get_status()
                    assert status["initialized"] is True
                
                # After exiting context, should be closed
                assert agent._initialized is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
