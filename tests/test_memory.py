"""
Unit Tests for Memory System
Tests short-term, long-term, and working memory components
"""
import pytest
from pathlib import Path
import tempfile


class TestShortTermMemory:
    """Tests for ShortTermMemory component"""
    
    def test_initialization(self):
        """Test memory initialization with default parameters"""
        from src.memory.short_term import ShortTermMemory
        
        memory = ShortTermMemory(window_size=10, max_tokens=5000)
        
        assert memory.window_size == 10
        assert memory.max_tokens == 5000
        assert memory.is_empty is True
        assert memory.size == 0
    
    def test_add_messages(self):
        """Test adding user and assistant messages"""
        from src.memory.short_term import ShortTermMemory
        
        memory = ShortTermMemory(window_size=10)
        
        # Add messages
        memory.add_user_message("Hello!")
        memory.add_assistant_message("Hi there!")
        
        assert memory.size == 1
        assert memory.is_empty is False
    
    def test_get_context(self):
        """Test retrieving conversation context"""
        from src.memory.short_term import ShortTermMemory
        
        memory = ShortTermMemory(window_size=10)
        
        memory.add_user_message("What's the weather?")
        memory.add_assistant_message("It's sunny today!")
        
        context = memory.get_context()
        
        assert len(context) == 2
        assert context[0].content == "What's the weather?"
        assert context[1].content == "It's sunny today!"
    
    def test_sliding_window(self):
        """Test that old conversations are removed when window is full"""
        from src.memory.short_term import ShortTermMemory
        
        memory = ShortTermMemory(window_size=3)  # Only keep 3 turns
        
        # Add more than window size
        for i in range(5):
            memory.add_user_message(f"Message {i}")
            memory.add_assistant_message(f"Response {i}")
        
        # Should only have last 3 turns
        assert memory.size <= 3
    
    def test_clear_memory(self):
        """Test clearing all conversation history"""
        from src.memory.short_term import ShortTermMemory
        
        memory = ShortTermMemory(window_size=10)
        
        memory.add_user_message("Test")
        memory.add_assistant_message("Response")
        
        memory.clear()
        
        assert memory.is_empty is True
        assert memory.size == 0
    
    def test_get_recent_turns(self):
        """Test getting recent N conversation turns"""
        from src.memory.short_term import ShortTermMemory
        
        memory = ShortTermMemory(window_size=10)
        
        for i in range(5):
            memory.add_user_message(f"Q{i}")
            memory.add_assistant_message(f"A{i}")
        
        recent = memory.get_recent(n_turns=2)
        
        # Should get last 2 turns (4 messages: 2 user + 2 assistant)
        assert len(recent) == 4
        assert recent[-1].content == "A4"  # Last response


class TestWorkingMemory:
    """Tests for WorkingMemory component"""
    
    def test_task_management(self):
        """Test starting, updating, and completing tasks"""
        from src.memory.working_memory import WorkingMemory
        
        working = WorkingMemory()
        
        # Start task
        task = working.start_task("task_123", "Analyze data", total_steps=3)
        
        assert working.has_active_task is True
        assert task.description == "Analyze data"
        assert task.status == "in_progress"
    
    def test_variable_storage(self):
        """Test storing and retrieving variables in task scope"""
        from src.memory.working_memory import WorkingMemory
        
        working = WorkingMemory()
        working.start_task("task_1", "Test")
        
        working.set_variable("result", 42)
        working.set_variable("name", "test")
        
        assert working.get_variable("result") == 42
        assert working.get_variable("name") == "test"
        assert working.get_variable("nonexistent") is None
    
    def test_progress_tracking(self):
        """Test tracking task progress"""
        from src.memory.working_memory import WorkingMemory
        
        working = WorkingMemory()
        working.start_task("task_1", "Process", total_steps=5)
        
        working.update_progress(step=2, total=5)
        
        current = working.current_task
        assert current.current_step == 2
        assert current.total_steps == 5
    
    def test_error_recording(self):
        """Test recording errors during task execution"""
        from src.memory.working_memory import WorkingMemory
        
        working = WorkingMemory()
        working.start_task("task_1", "Test")
        
        working.add_error("Connection timeout")
        working.add_error("Invalid response format")
        
        task = working.current_task
        assert len(task.errors) == 2
        assert "timeout" in task.errors[0]
    
    def test_complete_task(self):
        """Test completing a task and moving to next"""
        from src.memory.working_memory import WorkingMemory
        
        working = WorkingMemory()
        
        # First task
        working.start_task("task_1", "First")
        completed = working.complete_task(success=True)
        
        assert completed.status == "completed"
        assert working.has_active_task is False
        
        # Start new task
        working.start_task("task_2", "Second")
        assert working.has_active_task is True
        
        # Check history
        assert len(working.task_history) == 1


class TestLongTermMemory:
    """Tests for LongTermMemory (requires ChromaDB)"""
    
    @pytest.mark.asyncio
    async def test_initialization(self, tmp_path):
        """Test initializing long-term memory with ChromaDB"""
        try:
            from src.memory.long_term import LongTermMemory
            
            persist_dir = str(tmp_path / "chromadb_test")
            memory = LongTermMemory(
                persist_directory=persist_dir,
                collection_name="test_collection",
            )
            
            await memory.initialize()
            
            assert memory.is_initialized is True
            assert memory.count == 0
            
            await memory.close()
            
        except ImportError:
            pytest.skip("ChromaDB not installed")
    
    @pytest.mark.asyncio
    async def test_add_and_search_memory(self, tmp_path):
        """Test adding and searching memories"""
        try:
            from src.memory.long_term import LongTermMemory
            
            persist_dir = str(tmp_path / "chromadb_test")
            memory = LongTermMemory(
                persist_directory=persist_dir,
                collection_name="test_collection",
            )
            
            await memory.initialize()
            
            # Add memories
            mem1 = await memory.add_memory(
                content="User likes Python programming",
                memory_type="preference",
                importance="high",
            )
            
            mem2 = await memory.add_memory(
                content="User works at Tech Corp",
                memory_type="fact",
                importance="medium",
            )
            
            assert memory.count == 2
            assert mem1.id is not None
            
            # Search memories
            results = await memory.search("programming languages")
            
            # Should find relevant memories (depending on similarity threshold)
            assert isinstance(results, list)
            
            await memory.close()
            
        except ImportError:
            pytest.skip("ChromaDB not installed")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
