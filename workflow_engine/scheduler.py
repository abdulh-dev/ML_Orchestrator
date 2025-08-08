"""
Priority Queue Scheduler for Workflow Engine

Implements αβγ priority scoring: α·ERT + β·priority + γ·urgency
Uses in-memory heap for fast dequeue operations.
"""

import heapq
import time
import threading
import logging
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field
from .state import RedisStore

logger = logging.getLogger(__name__)

@dataclass
class ScoredTask:
    """Task with computed priority score."""
    score: float
    enqueue_time: float
    task_meta: Dict[str, Any]
    
    def __lt__(self, other):
        """Heap comparison - lower score = higher priority."""
        if self.score != other.score:
            return self.score < other.score
        # Tiebreaker: earlier enqueue time wins
        return self.enqueue_time < other.enqueue_time

class PriorityQueueScheduler:
    """
    Priority queue scheduler with configurable scoring.
    
    Score formula: α/ERT + β·user_priority + γ·urgency
    - α: Runtime weight (favor shorter tasks)
    - β: User priority weight 
    - γ: Deadline urgency weight
    """
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize scheduler.
        
        Args:
            config: Configuration dict with weights and Redis settings
        """
        self.config = config
        
        # Priority weights
        self.α = config.get("alpha", 1.0)  # Runtime weight
        self.β = config.get("beta", 2.0)   # User priority weight  
        self.γ = config.get("gamma", 3.0)  # Urgency weight
        
        # Thread-safe heap
        self.heap: List[ScoredTask] = []
        self.lock = threading.RLock()
        
        # Redis for runtime estimates
        redis_url = config.get("redis_url", "redis://localhost:6379")
        self.redis = RedisStore(redis_url, "scheduler")
        
        # Statistics
        self.stats = {
            "tasks_enqueued": 0,
            "tasks_dequeued": 0,
            "current_queue_size": 0,
            "avg_score": 0.0
        }
        
        logger.info(f"Scheduler initialized with weights α={self.α}, β={self.β}, γ={self.γ}")
    
    def score(self, task_meta: Dict[str, Any]) -> float:
        """
        Calculate priority score for task.
        
        Args:
            task_meta: Task metadata dict
            
        Returns:
            Priority score (lower = higher priority)
        """
        try:
            # Component 1: Runtime estimate (α/ERT)
            agent = task_meta.get("agent", "unknown")
            action = task_meta.get("action", "unknown")
            ert = self.redis.get_ert(agent, action, default=60.0)
            runtime_score = self.α / max(ert, 1.0)  # Avoid division by zero
            
            # Component 2: User priority (β·priority)
            user_priority = task_meta.get("user_priority", 0.5)  # 0.0-1.0 scale
            priority_score = self.β * user_priority
            
            # Component 3: Deadline urgency (γ·urgency)
            deadline_ts = task_meta.get("deadline_ts")
            if deadline_ts:
                time_remaining = max(deadline_ts - time.time(), 1.0)
                urgency = 1.0 / time_remaining  # Higher urgency = shorter time
            else:
                urgency = 0.0  # No deadline = no urgency
            urgency_score = self.γ * urgency
            
            # Total score (lower = higher priority)
            total_score = -(runtime_score + priority_score + urgency_score)
            
            logger.debug(f"Task {task_meta.get('task_id', 'unknown')} scored: "
                        f"runtime={runtime_score:.3f}, priority={priority_score:.3f}, "
                        f"urgency={urgency_score:.3f}, total={total_score:.3f}")
            
            return total_score
            
        except Exception as e:
            logger.error(f"Error calculating score for task: {e}")
            # Fallback score
            return 0.0
    
    def enqueue(self, task_meta: Dict[str, Any]) -> bool:
        """
        Enqueue task with priority score.
        
        Args:
            task_meta: Task metadata
            
        Returns:
            True if enqueued successfully
        """
        try:
            score = self.score(task_meta)
            scored_task = ScoredTask(
                score=score,
                enqueue_time=time.time(),
                task_meta=task_meta
            )
            
            with self.lock:
                heapq.heappush(self.heap, scored_task)
                self.stats["tasks_enqueued"] += 1
                self.stats["current_queue_size"] = len(self.heap)
                
                # Update average score
                total_score = sum(task.score for task in self.heap)
                self.stats["avg_score"] = total_score / len(self.heap) if self.heap else 0.0
            
            logger.debug(f"Enqueued task {task_meta.get('task_id', 'unknown')} with score {score:.3f}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to enqueue task: {e}")
            return False
    
    def dequeue(self, agent_filter: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """
        Dequeue highest priority task.
        
        Args:
            agent_filter: Optional agent name to filter by
            
        Returns:
            Task metadata or None if queue empty
        """
        with self.lock:
            if not self.heap:
                return None
            
            # If no agent filter, return highest priority task
            if not agent_filter:
                scored_task = heapq.heappop(self.heap)
                self._update_dequeue_stats()
                logger.debug(f"Dequeued task {scored_task.task_meta.get('task_id', 'unknown')}")
                return scored_task.task_meta
            
            # Find highest priority task for specific agent
            matching_tasks = []
            remaining_tasks = []
            
            # Separate tasks by agent
            while self.heap:
                scored_task = heapq.heappop(self.heap)
                if scored_task.task_meta.get("agent") == agent_filter:
                    matching_tasks.append(scored_task)
                else:
                    remaining_tasks.append(scored_task)
            
            # Rebuild heap with non-matching tasks
            self.heap = remaining_tasks
            heapq.heapify(self.heap)
            
            if matching_tasks:
                # Return highest priority matching task
                best_task = min(matching_tasks, key=lambda t: t.score)
                # Put remaining matching tasks back
                for task in matching_tasks:
                    if task != best_task:
                        heapq.heappush(self.heap, task)
                
                self._update_dequeue_stats()
                logger.debug(f"Dequeued task {best_task.task_meta.get('task_id', 'unknown')} for agent {agent_filter}")
                return best_task.task_meta
            else:
                logger.debug(f"No tasks found for agent {agent_filter}")
                return None
    
    def _update_dequeue_stats(self):
        """Update statistics after dequeue."""
        self.stats["tasks_dequeued"] += 1
        self.stats["current_queue_size"] = len(self.heap)
        
        # Update average score
        if self.heap:
            total_score = sum(task.score for task in self.heap)
            self.stats["avg_score"] = total_score / len(self.heap)
        else:
            self.stats["avg_score"] = 0.0
    
    def peek(self, agent_filter: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """
        Peek at next task without removing it.
        
        Args:
            agent_filter: Optional agent name to filter by
            
        Returns:
            Task metadata or None if queue empty
        """
        with self.lock:
            if not self.heap:
                return None
            
            if not agent_filter:
                return self.heap[0].task_meta
            
            # Find highest priority task for agent
            matching_tasks = [task for task in self.heap if task.task_meta.get("agent") == agent_filter]
            if matching_tasks:
                best_task = min(matching_tasks, key=lambda t: t.score)
                return best_task.task_meta
            
            return None
    
    def get_queue_size(self, agent_filter: Optional[str] = None) -> int:
        """
        Get current queue size.
        
        Args:
            agent_filter: Optional agent name to filter by
            
        Returns:
            Queue size
        """
        with self.lock:
            if not agent_filter:
                return len(self.heap)
            
            return sum(1 for task in self.heap if task.task_meta.get("agent") == agent_filter)
    
    def remove_task(self, task_id: str) -> bool:
        """
        Remove specific task from queue.
        
        Args:
            task_id: Task identifier
            
        Returns:
            True if task was found and removed
        """
        with self.lock:
            original_size = len(self.heap)
            
            # Filter out the target task
            self.heap = [task for task in self.heap if task.task_meta.get("task_id") != task_id]
            heapq.heapify(self.heap)
            
            removed = len(self.heap) < original_size
            if removed:
                self.stats["current_queue_size"] = len(self.heap)
                logger.debug(f"Removed task {task_id} from queue")
            
            return removed
    
    def get_stats(self) -> Dict[str, Any]:
        """Get scheduler statistics."""
        with self.lock:
            stats = self.stats.copy()
            stats.update({
                "weights": {"alpha": self.α, "beta": self.β, "gamma": self.γ},
                "redis_stats": self.redis.get_stats()
            })
            return stats
    
    def clear(self):
        """Clear all tasks from queue."""
        with self.lock:
            self.heap.clear()
            self.stats["current_queue_size"] = 0
            self.stats["avg_score"] = 0.0
            logger.info("Scheduler queue cleared")
    
    def list_tasks(self, limit: int = 10) -> List[Dict[str, Any]]:
        """
        List current tasks in queue (for debugging).
        
        Args:
            limit: Maximum number of tasks to return
            
        Returns:
            List of task metadata
        """
        with self.lock:
            sorted_tasks = sorted(self.heap, key=lambda t: t.score)
            return [
                {
                    "task_id": task.task_meta.get("task_id", "unknown"),
                    "agent": task.task_meta.get("agent", "unknown"),
                    "action": task.task_meta.get("action", "unknown"),
                    "score": task.score,
                    "enqueue_time": task.enqueue_time
                }
                for task in sorted_tasks[:limit]
            ] 