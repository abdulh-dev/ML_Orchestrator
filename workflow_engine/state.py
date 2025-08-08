"""
Redis State Management for Workflow Engine

Provides lightweight Redis operations for delay queues, runtime estimates,
and other stateful workflow engine operations.
"""

import redis
import json
import logging
from typing import List, Optional, Dict, Any

logger = logging.getLogger(__name__)

class RedisStore:
    """Redis helper for workflow engine state management."""
    
    def __init__(self, url: str = "redis://localhost:6379", namespace: str = "workflow_engine"):
        """
        Initialize Redis store.
        
        Args:
            url: Redis connection URL
            namespace: Key namespace prefix
        """
        try:
            self.r = redis.Redis.from_url(url, decode_responses=True)
            self.namespace = namespace
            # Test connection
            self.r.ping()
            logger.info(f"Redis store initialized with namespace '{namespace}'")
        except Exception as e:
            logger.error(f"Failed to connect to Redis: {e}")
            # Use mock for development without Redis
            self.r = None
    
    def _key(self, suffix: str) -> str:
        """Generate namespaced key."""
        return f"{self.namespace}:{suffix}"
    
    # === Delay Queue Operations ===
    
    def zadd_retry(self, task_id: str, timestamp: float) -> bool:
        """
        Add task to retry delay queue.
        
        Args:
            task_id: Task identifier
            timestamp: When task should be retried (unix timestamp)
            
        Returns:
            True if added successfully
        """
        if not self.r:
            logger.warning("Redis not available, retry scheduling disabled")
            return False
        
        try:
            self.r.zadd(self._key("retry_q"), {task_id: timestamp})
            logger.debug(f"Scheduled retry for task {task_id} at {timestamp}")
            return True
        except Exception as e:
            logger.error(f"Failed to schedule retry for {task_id}: {e}")
            return False
    
    def fetch_due_retries(self, now: float) -> List[str]:
        """
        Fetch tasks due for retry.
        
        Args:
            now: Current timestamp
            
        Returns:
            List of task IDs ready for retry
        """
        if not self.r:
            return []
        
        try:
            # Get all tasks with score <= now (due for retry)
            due_tasks = self.r.zrangebyscore(self._key("retry_q"), 0, now)
            if due_tasks:
                # Remove them from the delay queue
                self.r.zremrangebyscore(self._key("retry_q"), 0, now)
                logger.debug(f"Found {len(due_tasks)} tasks due for retry")
            return due_tasks
        except Exception as e:
            logger.error(f"Failed to fetch due retries: {e}")
            return []
    
    def remove_retry(self, task_id: str) -> bool:
        """
        Remove task from retry queue (e.g., on successful completion).
        
        Args:
            task_id: Task identifier
            
        Returns:
            True if removed successfully
        """
        if not self.r:
            return False
        
        try:
            removed = self.r.zrem(self._key("retry_q"), task_id)
            if removed:
                logger.debug(f"Removed task {task_id} from retry queue")
            return bool(removed)
        except Exception as e:
            logger.error(f"Failed to remove retry for {task_id}: {e}")
            return False
    
    # === Runtime Estimates ===
    
    def get_ert(self, agent: str, action: str, default: float = 60.0) -> float:
        """
        Get estimated runtime for agent/action combination.
        
        Args:
            agent: Agent identifier
            action: Action name
            default: Default estimate if none found
            
        Returns:
            Estimated runtime in seconds
        """
        if not self.r:
            return default
        
        try:
            key = f"{agent}:{action}"
            ert = self.r.hget(self._key("ert"), key)
            return float(ert) if ert else default
        except Exception as e:
            logger.debug(f"Failed to get ERT for {agent}:{action}, using default: {e}")
            return default
    
    def update_ert(self, agent: str, action: str, runtime_seconds: float) -> bool:
        """
        Update estimated runtime based on actual execution.
        
        Args:
            agent: Agent identifier
            action: Action name
            runtime_seconds: Actual runtime in seconds
            
        Returns:
            True if updated successfully
        """
        if not self.r:
            return False
        
        try:
            key = f"{agent}:{action}"
            # Use exponential moving average: new_ert = 0.7 * old_ert + 0.3 * actual
            old_ert = self.get_ert(agent, action, runtime_seconds)
            new_ert = 0.7 * old_ert + 0.3 * runtime_seconds
            
            self.r.hset(self._key("ert"), key, new_ert)
            logger.debug(f"Updated ERT for {agent}:{action}: {old_ert:.1f}s -> {new_ert:.1f}s")
            return True
        except Exception as e:
            logger.error(f"Failed to update ERT for {agent}:{action}: {e}")
            return False
    
    # === General State Operations ===
    
    def set_state(self, key: str, value: Any, ttl: Optional[int] = None) -> bool:
        """
        Set arbitrary state value.
        
        Args:
            key: State key
            value: Value to store (will be JSON serialized)
            ttl: Optional TTL in seconds
            
        Returns:
            True if set successfully
        """
        if not self.r:
            return False
        
        try:
            serialized = json.dumps(value) if not isinstance(value, str) else value
            if ttl:
                self.r.setex(self._key(key), ttl, serialized)
            else:
                self.r.set(self._key(key), serialized)
            return True
        except Exception as e:
            logger.error(f"Failed to set state {key}: {e}")
            return False
    
    def get_state(self, key: str, default: Any = None) -> Any:
        """
        Get state value.
        
        Args:
            key: State key
            default: Default value if not found
            
        Returns:
            Stored value or default
        """
        if not self.r:
            return default
        
        try:
            value = self.r.get(self._key(key))
            if value is None:
                return default
            
            # Try to deserialize as JSON, fallback to string
            try:
                return json.loads(value)
            except json.JSONDecodeError:
                return value
        except Exception as e:
            logger.error(f"Failed to get state {key}: {e}")
            return default
    
    def get_stats(self) -> Dict[str, Any]:
        """Get Redis store statistics."""
        if not self.r:
            return {"status": "unavailable", "retry_queue_size": 0}
        
        try:
            retry_count = self.r.zcard(self._key("retry_q"))
            ert_count = self.r.hlen(self._key("ert"))
            
            return {
                "status": "connected",
                "retry_queue_size": retry_count,
                "ert_entries": ert_count,
                "namespace": self.namespace
            }
        except Exception as e:
            logger.error(f"Failed to get Redis stats: {e}")
            return {"status": "error", "error": str(e)} 