"""
Working Memory System
Manages temporary state during task execution
"""
from typing import Any, Dict, Optional, List
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class TaskState:
    """Current state of an active task"""
    task_id: str
    description: str
    status: str = "in_progress"  # "in_progress", "completed", "failed", "paused"
    current_step: int = 0
    total_steps: int = 0
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    variables: Dict[str, Any] = field(default_factory=dict)
    intermediate_results: List[Dict] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)


class WorkingMemory:
    """
    Working Memory for Active Task State
    
    Features:
    - Store temporary variables during task execution
    - Track task progress and status
    - Manage intermediate computation results
    - Error tracking and recovery state
    
    Usage:
        working = WorkingMemory()
        
        working.start_task("task_123", "Analyze data")
        working.set_variable("data_path", "./data.csv")
        working.add_result({"analysis": "complete"})
        
        state = working.current_task
    """
    
    def __init__(self):
        """Initialize empty working memory"""
        self._current_task: Optional[TaskState] = None
        self._task_history: List[TaskState] = []
        self._global_variables: Dict[str, Any] = {}
    
    def start_task(
        self,
        task_id: str,
        description: str,
        total_steps: int = 0,
    ) -> TaskState:
        """
        Start a new task and set it as current
        
        Args:
            task_id: Unique task identifier
            description: Task description
            total_steps: Estimated number of steps
            
        Returns:
            Created TaskState object
        """
        # Save previous task if exists
        if self._current_task:
            self._task_history.append(self._current_task)
        
        self._current_task = TaskState(
            task_id=task_id,
            description=description,
            total_steps=total_steps,
        )
        
        return self._current_task
    
    def complete_task(self, success: bool = True) -> Optional[TaskState]:
        """
        Mark current task as completed
        
        Args:
            success: Whether task completed successfully
            
        Returns:
            Completed task state
        """
        if self._current_task:
            self._current_task.status = "completed" if success else "failed"
            self._current_task.updated_at = datetime.now()
            
            completed = self._current_task
            self._task_history.append(completed)
            self._current_task = None
            
            return completed
        return None
    
    def update_progress(self, step: int, total: Optional[int] = None) -> None:
        """
        Update task progress
        
        Args:
            step: Current step number
            total: Updated total steps (optional)
        """
        if self._current_task:
            self._current_task.current_step = step
            if total:
                self._current_task.total_steps = total
            self._current_task.updated_at = datetime.now()
    
    def set_variable(self, name: str, value: Any) -> None:
        """
        Set a variable in current task scope
        
        Args:
            name: Variable name
            value: Variable value
        """
        if self._current_task:
            self._current_task.variables[name] = value
    
    def get_variable(self, name: str, default: Any = None) -> Any:
        """
        Get a variable from current task scope
        
        Args:
            name: Variable name
            default: Default value if not found
            
        Returns:
            Variable value or default
        """
        if self._current_task and name in self._current_task.variables:
            return self._current_task.variables[name]
        return self._global_variables.get(name, default)
    
    def set_global_variable(self, name: str, value: Any) -> None:
        """
        Set a global variable (persists across tasks)
        
        Args:
            name: Variable name
            value: Variable value
        """
        self._global_variables[name] = value
    
    def add_result(self, result: Dict[str, Any]) -> None:
        """
        Add an intermediate result to current task
        
        Args:
            result: Result dictionary to store
        """
        if self._current_task:
            self._current_task.intermediate_results.append({
                "timestamp": datetime.now().isoformat(),
                "data": result,
            })
    
    def add_error(self, error: str) -> None:
        """
        Record an error that occurred during task execution
        
        Args:
            error: Error message or details
        """
        if self._current_task:
            self._current_task.errors.append(error)
    
    @property
    def current_task(self) -> Optional[TaskState]:
        """Get the current active task state"""
        return self._current_task
    
    @property
    def has_active_task(self) -> bool:
        """Check if there's an active task"""
        return self._current_task is not None
    
    @property
    def task_history(self) -> List[TaskState]:
        """Get list of completed tasks"""
        return self._task_history.copy()
    
    def clear(self) -> None:
        """Clear all working memory"""
        self._current_task = None
        self._task_history.clear()
        self._global_variables.clear()
    
    def to_dict(self) -> Dict[str, Any]:
        """Export working memory state to dictionary"""
        return {
            "current_task": self._current_task.__dict__ if self._current_task else None,
            "global_variables": self._global_variables,
            "completed_tasks": len(self._task_history),
        }
    
    def __repr__(self) -> str:
        if self._current_task:
            return (
                f"WorkingMemory(task={self._current_task.task_id}, "
                f"status={self._current_task.status}, "
                f"step={self._current_task.current_step}/"
                f"{self._current_task.total_steps})"
            )
        return "WorkingMemory(no active task)"
