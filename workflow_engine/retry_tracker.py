"""
Retry Tracker for Workflow Engine

Handles task retry scheduling with exponential backoff using Redis delay queues.
Polls for due retries and re-enqueues them through the scheduler.
"""

import time
import asyncio
import logging
from typing import Dict, Any, Optional, List
from .state import RedisStore

logger = logging.getLogger(__name__)

class RetryTracker:
    """
    Manages task retry scheduling with exponential backoff.
    
    Uses Redis sorted sets as delay queues where the score is the retry timestamp.
    """
    
    def __init__(self, scheduler, config: Dict[str, Any]):
        """
        Initialize retry tracker.
        
        Args:
            scheduler: PriorityQueueScheduler instance
            config: Configuration dict with retry settings
        """
        self.scheduler = scheduler
        self.config = config
        
        # Retry configuration
        self.max_retries = config.get("max_retries", 3)
        self.backoff_base_s = config.get("backoff_base_s", 15)
        self.backoff_max_s = config.get("backoff_max_s", 300)
        
        # Redis for delay queue
        redis_url = config.get("redis_url", "redis://localhost:6379")
        self.redis = RedisStore(redis_url, "retry_tracker")
        
        # Background polling
        self.is_running = False
        self.poll_task = None
        self.poll_interval = config.get("poll_interval_s", 1.0)
        
        # Statistics
        self.stats = {
            "retries_scheduled": 0,
            "retries_executed": 0,
            "retries_abandoned": 0,
            "current_pending": 0
        }
        
        logger.info(f"RetryTracker initialized: max_retries={self.max_retries}, "
                   f"backoff_base={self.backoff_base_s}s, max={self.backoff_max_s}s")
    
    def schedule(self, task_meta: Dict[str, Any], error_context: Optional[str] = None) -> bool:
        """
        Schedule a task for retry with exponential backoff.
        
        Args:
            task_meta: Task metadata
            error_context: Optional error information
            
        Returns:
            True if scheduled, False if max retries exceeded
        """
        try:
            task_id = task_meta.get("task_id", "unknown")
            current_retries = task_meta.get("retries", 0)
            
            # Check if we've exceeded max retries
            if current_retries >= self.max_retries:
                logger.warning(f"Task {task_id} exceeded max retries ({self.max_retries}), abandoning")
                self.stats["retries_abandoned"] += 1
                return False
            
            # Calculate delay with exponential backoff
            delay = min(
                self.backoff_base_s * (2 ** current_retries),
                self.backoff_max_s
            )
            retry_timestamp = time.time() + delay
            
            # Update task metadata
            task_meta["retries"] = current_retries + 1
            task_meta["last_error"] = error_context
            task_meta["retry_timestamp"] = retry_timestamp
            
            # Schedule in Redis
            success = self.redis.zadd_retry(task_id, retry_timestamp)
            
            if success:
                self.stats["retries_scheduled"] += 1
                self.stats["current_pending"] = self._get_pending_count()
                
                logger.info(f"Scheduled retry {current_retries + 1}/{self.max_retries} "
                           f"for task {task_id} in {delay:.1f}s")
                return True
            else:
                logger.error(f"Failed to schedule retry for task {task_id}")
                return False
                
        except Exception as e:
            logger.error(f"Error scheduling retry for task: {e}")
            return False
    
    def cancel_retry(self, task_id: str) -> bool:
        """
        Cancel pending retry for a task.
        
        Args:
            task_id: Task identifier
            
        Returns:
            True if retry was cancelled
        """
        try:
            success = self.redis.remove_retry(task_id)
            if success:
                self.stats["current_pending"] = self._get_pending_count()
                logger.debug(f"Cancelled retry for task {task_id}")
            return success
        except Exception as e:
            logger.error(f"Error cancelling retry for {task_id}: {e}")
            return False
    
    async def start_polling(self):
        """Start background polling for due retries."""
        if self.is_running:
            logger.warning("Retry tracker polling already running")
            return
        
        self.is_running = True
        self.poll_task = asyncio.create_task(self._poll_loop())
        logger.info("Started retry tracker polling")
    
    async def stop_polling(self):
        """Stop background polling."""
        if not self.is_running:
            return
        
        self.is_running = False
        if self.poll_task:
            self.poll_task.cancel()
            try:
                await self.poll_task
            except asyncio.CancelledError:
                pass
        
        logger.info("Stopped retry tracker polling")
    
    async def _poll_loop(self):
        """Main polling loop for due retries."""
        logger.info("Retry tracker polling started")
        
        while self.is_running:
            try:
                await self._process_due_retries()
                await asyncio.sleep(self.poll_interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in retry tracker poll loop: {e}")
                # Backoff on error to avoid rapid failure loops
                await asyncio.sleep(min(self.poll_interval * 5, 30))
    
    async def _process_due_retries(self):
        """Process tasks that are due for retry."""
        try:
            current_time = time.time()
            due_task_ids = self.redis.fetch_due_retries(current_time)
            
            if not due_task_ids:
                return
            
            logger.debug(f"Processing {len(due_task_ids)} due retries")
            
            for task_id in due_task_ids:
                try:
                    # Fetch full task metadata (this would need integration with workflow_manager)
                    task_meta = await self._fetch_task_metadata(task_id)
                    
                    if task_meta:
                        # Re-enqueue in scheduler
                        success = self.scheduler.enqueue(task_meta)
                        if success:
                            self.stats["retries_executed"] += 1
                            logger.info(f"Re-enqueued retry for task {task_id}")
                        else:
                            logger.error(f"Failed to re-enqueue retry for task {task_id}")
                    else:
                        logger.warning(f"Could not fetch metadata for retry task {task_id}")
                
                except Exception as e:
                    logger.error(f"Error processing retry for task {task_id}: {e}")
            
            # Update pending count
            self.stats["current_pending"] = self._get_pending_count()
            
        except Exception as e:
            logger.error(f"Error processing due retries: {e}")
    
    async def _fetch_task_metadata(self, task_id: str) -> Optional[Dict[str, Any]]:
        """
        Fetch complete task metadata for retry.
        
        This is a placeholder - in real implementation, this would query
        the workflow manager or database for full task details.
        
        Args:
            task_id: Task identifier
            
        Returns:
            Task metadata or None if not found
        """
        # TODO: Integrate with workflow_manager to fetch task from MongoDB
        # For now, return None - this will need proper integration
        logger.debug(f"TODO: Fetch task metadata for {task_id}")
        return None
    
    def _get_pending_count(self) -> int:
        """Get count of pending retries."""
        try:
            # Count items in Redis retry queue
            if self.redis.r:
                return self.redis.r.zcard(self.redis._key("retry_q"))
            return 0
        except Exception as e:
            logger.debug(f"Error getting pending count: {e}")
            return 0
    
    def get_retry_info(self, task_id: str) -> Optional[Dict[str, Any]]:
        """
        Get retry information for a specific task.
        
        Args:
            task_id: Task identifier
            
        Returns:
            Retry info or None if not found
        """
        try:
            if not self.redis.r:
                return None
            
            # Get retry timestamp
            score = self.redis.r.zscore(self.redis._key("retry_q"), task_id)
            if score is None:
                return None
            
            retry_timestamp = float(score)
            current_time = time.time()
            time_remaining = max(0, retry_timestamp - current_time)
            
            return {
                "task_id": task_id,
                "retry_timestamp": retry_timestamp,
                "time_remaining_s": time_remaining,
                "is_due": time_remaining <= 0
            }
        except Exception as e:
            logger.error(f"Error getting retry info for {task_id}: {e}")
            return None
    
    def list_pending_retries(self, limit: int = 10) -> List[Dict[str, Any]]:
        """
        List pending retries.
        
        Args:
            limit: Maximum number to return
            
        Returns:
            List of retry information
        """
        try:
            if not self.redis.r:
                return []
            
            # Get pending retries with scores
            pending = self.redis.r.zrange(
                self.redis._key("retry_q"), 
                0, limit - 1, 
                withscores=True
            )
            
            current_time = time.time()
            results = []
            
            for task_id, timestamp in pending:
                time_remaining = max(0, timestamp - current_time)
                results.append({
                    "task_id": task_id,
                    "retry_timestamp": timestamp,
                    "time_remaining_s": time_remaining,
                    "is_due": time_remaining <= 0
                })
            
            return results
        except Exception as e:
            logger.error(f"Error listing pending retries: {e}")
            return []
    
    def get_stats(self) -> Dict[str, Any]:
        """Get retry tracker statistics."""
        self.stats["current_pending"] = self._get_pending_count()
        
        return {
            **self.stats,
            "config": {
                "max_retries": self.max_retries,
                "backoff_base_s": self.backoff_base_s,
                "backoff_max_s": self.backoff_max_s,
                "poll_interval_s": self.poll_interval
            },
            "is_running": self.is_running,
            "redis_status": self.redis.get_stats()["status"]
        }
    
    def clear_all_retries(self):
        """Clear all pending retries (for testing/debugging)."""
        try:
            if self.redis.r:
                cleared = self.redis.r.delete(self.redis._key("retry_q"))
                self.stats["current_pending"] = 0
                logger.info(f"Cleared {cleared} pending retries")
                return cleared
            return 0
        except Exception as e:
            logger.error(f"Error clearing retries: {e}")
            return 0 