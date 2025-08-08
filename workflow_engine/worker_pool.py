"""
Worker Pool for Workflow Engine

Manages async workers per agent that execute tasks via HTTP calls.
Emits TASK_STARTED/SUCCESS/FAILED events to Kafka for workflow coordination.
"""

import asyncio
import aiohttp
import json
import logging
import time
from typing import Dict, Any, Optional, List
from dataclasses import dataclass
from datetime import datetime

logger = logging.getLogger(__name__)

@dataclass
class WorkerStats:
    """Statistics for a worker."""
    tasks_executed: int = 0
    tasks_succeeded: int = 0
    tasks_failed: int = 0
    total_runtime_s: float = 0.0
    last_task_time: Optional[float] = None
    is_active: bool = False

class WorkerPool:
    """
    Manages async workers for a specific agent.
    
    Workers continuously poll the scheduler for tasks assigned to their agent,
    execute them via HTTP, and emit events to Kafka.
    """
    
    def __init__(self, agent: str, scheduler, retry_tracker, config: Dict[str, Any]):
        """
        Initialize worker pool.
        
        Args:
            agent: Agent identifier (e.g., "eda_agent", "ml_agent")
            scheduler: PriorityQueueScheduler instance
            retry_tracker: RetryTracker instance
            config: Configuration dict
        """
        self.agent = agent
        self.scheduler = scheduler
        self.retry_tracker = retry_tracker
        self.config = config
        
        # Worker configuration
        self.max_workers = config.get("max_workers_per_agent", {}).get(agent, 1)
        self.agent_base_url = config.get("agent_urls", {}).get(agent, f"http://{agent}:8000")
        self.task_timeout = config.get("task_timeout_s", 600)  # 10 minutes
        self.poll_interval = config.get("poll_interval_s", 0.2)
        
        # Worker management
        self.workers: List[asyncio.Task] = []
        self.is_running = False
        self.worker_stats: List[WorkerStats] = [WorkerStats() for _ in range(self.max_workers)]
        
        # Event publishing (would be integrated with Kafka)
        self.event_callbacks: List[callable] = []
        
        # HTTP session
        self.session: Optional[aiohttp.ClientSession] = None
        
        logger.info(f"Worker pool initialized for agent '{agent}': "
                   f"{self.max_workers} workers, URL: {self.agent_base_url}")
    
    def add_event_callback(self, callback: callable):
        """Add callback for task events."""
        self.event_callbacks.append(callback)
    
    async def start(self):
        """Start all workers in the pool."""
        if self.is_running:
            logger.warning(f"Worker pool for {self.agent} already running")
            return
        
        self.is_running = True
        
        # Create HTTP session
        timeout = aiohttp.ClientTimeout(total=self.task_timeout)
        self.session = aiohttp.ClientSession(timeout=timeout)
        
        # Start workers
        for i in range(self.max_workers):
            worker_task = asyncio.create_task(self._worker_loop(i))
            self.workers.append(worker_task)
        
        logger.info(f"Started {len(self.workers)} workers for agent {self.agent}")
    
    async def stop(self):
        """Stop all workers in the pool."""
        if not self.is_running:
            return
        
        self.is_running = False
        
        # Cancel all workers
        for worker in self.workers:
            worker.cancel()
        
        # Wait for workers to finish
        if self.workers:
            await asyncio.gather(*self.workers, return_exceptions=True)
        
        # Close HTTP session
        if self.session:
            await self.session.close()
            self.session = None
        
        self.workers.clear()
        logger.info(f"Stopped worker pool for agent {self.agent}")
    
    async def _worker_loop(self, worker_id: int):
        """Main worker loop."""
        logger.info(f"Worker {worker_id} started for agent {self.agent}")
        stats = self.worker_stats[worker_id]
        
        while self.is_running:
            try:
                # Try to get a task for this agent
                task_meta = self.scheduler.dequeue(agent_filter=self.agent)
                
                if task_meta:
                    stats.is_active = True
                    await self._execute_task(task_meta, worker_id)
                    stats.is_active = False
                else:
                    # No tasks available, sleep briefly
                    await asyncio.sleep(self.poll_interval)
                    
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in worker {worker_id} for agent {self.agent}: {e}")
                stats.is_active = False
                await asyncio.sleep(self.poll_interval * 5)  # Backoff on error
        
        logger.info(f"Worker {worker_id} stopped for agent {self.agent}")
    
    async def _execute_task(self, task_meta: Dict[str, Any], worker_id: int):
        """
        Execute a single task.
        
        Args:
            task_meta: Task metadata
            worker_id: Worker identifier
        """
        task_id = task_meta.get("task_id", "unknown")
        run_id = task_meta.get("run_id", "unknown")
        stats = self.worker_stats[worker_id]
        start_time = time.time()
        
        try:
            # Check if workflow has been cancelled before starting execution
            if await self._is_workflow_cancelled(run_id):
                logger.info(f"Skipping task {task_id} - workflow {run_id} has been cancelled")
                await self._emit_event("TASK_CANCELLED", task_meta, 
                                     reason="workflow_cancelled")
                return
            
            logger.info(f"Worker {worker_id} executing task {task_id}")
            
            # Update task start time
            task_meta["started_at"] = start_time
            stats.last_task_time = start_time
            
            # Emit TASK_STARTED event
            await self._emit_event("TASK_STARTED", task_meta)
            
            # Execute task via HTTP
            result = await self._call_agent(task_meta)
            
            # Calculate runtime
            runtime = time.time() - start_time
            task_meta["completed_at"] = time.time()
            task_meta["runtime_s"] = runtime
            
            # Update statistics
            stats.tasks_executed += 1
            stats.tasks_succeeded += 1
            stats.total_runtime_s += runtime
            
            # Update ERT in Redis
            action = task_meta.get("action", "unknown")
            if self.scheduler.redis:
                self.scheduler.redis.update_ert(self.agent, action, runtime)
            
            # Emit TASK_SUCCESS event
            await self._emit_event("TASK_SUCCESS", task_meta, result=result)
            
            logger.info(f"Task {task_id} completed successfully in {runtime:.2f}s")
            
        except Exception as e:
            # Calculate runtime even on failure
            runtime = time.time() - start_time
            error_msg = str(e)
            
            # Update statistics
            stats.tasks_executed += 1
            stats.tasks_failed += 1
            stats.total_runtime_s += runtime
            
            # Update task metadata
            task_meta["failed_at"] = time.time()
            task_meta["runtime_s"] = runtime
            task_meta["error"] = error_msg
            
            # Emit TASK_FAILED event
            await self._emit_event("TASK_FAILED", task_meta, error=error_msg)
            
            # Schedule retry if appropriate
            self.retry_tracker.schedule(task_meta, error_msg)
            
            logger.error(f"Task {task_id} failed after {runtime:.2f}s: {error_msg}")
    
    async def _call_agent(self, task_meta: Dict[str, Any]) -> Dict[str, Any]:
        """
        Call agent HTTP API to execute task.
        
        Args:
            task_meta: Task metadata
            
        Returns:
            Task execution result
            
        Raises:
            Exception: If task execution fails
        """
        if not self.session:
            raise RuntimeError("HTTP session not initialized")
        
        # Prepare request
        url = f"{self.agent_base_url}/execute"
        payload = {
            "task_id": task_meta.get("task_id"),
            "action": task_meta.get("action"),
            "params": task_meta.get("params", {}),
            "run_id": task_meta.get("run_id"),
            "metadata": task_meta.get("metadata", {})
        }
        
        # Make HTTP request
        async with self.session.post(url, json=payload) as response:
            if response.status == 200:
                result = await response.json()
                return result
            else:
                error_text = await response.text()
                raise Exception(f"Agent returned {response.status}: {error_text}")
    
    async def _emit_event(self, event_type: str, task_meta: Dict[str, Any], **kwargs):
        """
        Emit task event to registered callbacks.
        
        Args:
            event_type: Event type (TASK_STARTED, TASK_SUCCESS, TASK_FAILED)
            task_meta: Task metadata
            **kwargs: Additional event data
        """
        event = {
            "type": event_type,
            "task_id": task_meta.get("task_id"),
            "run_id": task_meta.get("run_id"),
            "agent": self.agent,
            "timestamp": datetime.utcnow().isoformat(),
            "task_meta": task_meta,
            **kwargs
        }
        
        # Call all registered callbacks
        for callback in self.event_callbacks:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(event)
                else:
                    callback(event)
            except Exception as e:
                logger.error(f"Error in event callback: {e}")
    
    async def _is_workflow_cancelled(self, run_id: str) -> bool:
        """
        Check if a workflow has been cancelled by looking in Redis.
        
        Args:
            run_id: Workflow run ID to check
            
        Returns:
            True if workflow is cancelled, False otherwise
        """
        try:
            # Check Redis for cancelled runs
            if hasattr(self.scheduler, 'redis') and self.scheduler.redis:
                redis_client = self.scheduler.redis.redis_client
                if redis_client:
                    return await redis_client.sismember("cancelled_runs", run_id)
            
            # Fallback: Check with workflow manager directly
            try:
                import sys
                import os
                # Add the parent directory to the path for imports
                parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                if parent_dir not in sys.path:
                    sys.path.append(parent_dir)
                
                from orchestrator_tools.workflow_manager import get_workflow_status
                workflow_info = await get_workflow_status(run_id)
                if workflow_info:
                    status = workflow_info.get("status", "")
                    return status in ["CANCELLED", "CANCELLING"]
            except Exception:
                pass  # Fallback failed, assume not cancelled
            
            return False
            
        except Exception as e:
            logger.warning(f"Error checking cancellation status for run {run_id}: {e}")
            return False  # Assume not cancelled on error
    
    def get_stats(self) -> Dict[str, Any]:
        """Get worker pool statistics."""
        total_tasks = sum(worker.tasks_executed for worker in self.worker_stats)
        total_succeeded = sum(worker.tasks_succeeded for worker in self.worker_stats)
        total_failed = sum(worker.tasks_failed for worker in self.worker_stats)
        total_runtime = sum(worker.total_runtime_s for worker in self.worker_stats)
        active_workers = sum(1 for worker in self.worker_stats if worker.is_active)
        
        return {
            "agent": self.agent,
            "max_workers": self.max_workers,
            "active_workers": active_workers,
            "is_running": self.is_running,
            "tasks": {
                "total": total_tasks,
                "succeeded": total_succeeded,
                "failed": total_failed,
                "success_rate": total_succeeded / max(total_tasks, 1)
            },
            "performance": {
                "total_runtime_s": total_runtime,
                "avg_task_time_s": total_runtime / max(total_tasks, 1),
                "tasks_per_hour": (total_tasks / max(total_runtime / 3600, 1/3600)) if total_runtime > 0 else 0
            },
            "worker_details": [
                {
                    "worker_id": i,
                    "is_active": worker.is_active,
                    "tasks_executed": worker.tasks_executed,
                    "success_rate": worker.tasks_succeeded / max(worker.tasks_executed, 1),
                    "avg_runtime_s": worker.total_runtime_s / max(worker.tasks_executed, 1),
                    "last_task_time": worker.last_task_time
                }
                for i, worker in enumerate(self.worker_stats)
            ]
        }

class MultiAgentWorkerManager:
    """
    Manages worker pools for multiple agents.
    """
    
    def __init__(self, scheduler, retry_tracker, config: Dict[str, Any]):
        """
        Initialize multi-agent worker manager.
        
        Args:
            scheduler: PriorityQueueScheduler instance
            retry_tracker: RetryTracker instance
            config: Configuration dict
        """
        self.scheduler = scheduler
        self.retry_tracker = retry_tracker
        self.config = config
        
        # Agent configuration
        self.agent_pools: Dict[str, WorkerPool] = {}
        self.enabled_agents = config.get("enabled_agents", ["eda_agent", "ml_agent"])
        
        # Initialize worker pools for each agent
        for agent in self.enabled_agents:
            pool = WorkerPool(agent, scheduler, retry_tracker, config)
            self.agent_pools[agent] = pool
        
        logger.info(f"Multi-agent worker manager initialized for agents: {self.enabled_agents}")
    
    def add_event_callback(self, callback: callable):
        """Add event callback to all worker pools."""
        for pool in self.agent_pools.values():
            pool.add_event_callback(callback)
    
    async def start_all(self):
        """Start all worker pools."""
        tasks = [pool.start() for pool in self.agent_pools.values()]
        await asyncio.gather(*tasks, return_exceptions=True)
        logger.info("All worker pools started")
    
    async def stop_all(self):
        """Stop all worker pools."""
        tasks = [pool.stop() for pool in self.agent_pools.values()]
        await asyncio.gather(*tasks, return_exceptions=True)
        logger.info("All worker pools stopped")
    
    def get_pool(self, agent: str) -> Optional[WorkerPool]:
        """Get worker pool for specific agent."""
        return self.agent_pools.get(agent)
    
    def get_all_stats(self) -> Dict[str, Any]:
        """Get statistics for all worker pools."""
        return {
            agent: pool.get_stats()
            for agent, pool in self.agent_pools.items()
        } 