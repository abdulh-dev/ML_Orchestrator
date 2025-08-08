#Actively in Use
"""
Workflow Manager for the Master Orchestrator.

Handles workflow initialization, task management, and execution coordination.
"""

import asyncio
import logging
import json
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Callable
from enum import Enum

try:
    from motor.motor_asyncio import AsyncIOMotorClient
    from confluent_kafka import Producer
    KAFKA_AVAILABLE = True
    MONGO_AVAILABLE = True
except ImportError:
    KAFKA_AVAILABLE = False
    MONGO_AVAILABLE = False

# Import workflow engine for task execution
try:
    from workflow_engine import get_engine, enqueue_task as engine_enqueue_task
    WORKFLOW_ENGINE_AVAILABLE = True
except ImportError:
    WORKFLOW_ENGINE_AVAILABLE = False

logger = logging.getLogger(__name__)

class WorkflowStatus(Enum):
    """Workflow execution status."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    NEEDS_HUMAN = "needs_human"

class TaskStatus(Enum):
    """Task execution status."""
    PENDING = "pending"
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    RETRY = "retry"

class WorkflowManager:
    """Manages workflow execution and task coordination."""
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize workflow manager.
        
        Args:
            config: Configuration dictionary
        """
        self.config = config
        
        # Database connection
        self.mongo_client = None
        self.db = None
        self.use_mongo = False
        if MONGO_AVAILABLE:
            self._init_mongo()
        
        # In-memory fallback storage when MongoDB is unavailable
        self.in_memory_workflows = {}
        self.in_memory_tasks = {}
        
        # Kafka producer
        self.kafka_producer = None
        self.use_kafka = False
        if KAFKA_AVAILABLE:
            self._init_kafka()
        
        # Event callbacks
        self.event_callbacks: List[Callable] = []
        
        # Statistics
        self.stats = {
            "workflows_created": 0,
            "workflows_completed": 0,
            "workflows_failed": 0,
            "tasks_enqueued": 0,
            "tasks_completed": 0,
            "tasks_failed": 0
        }
    
    def _init_mongo(self):
        """Initialize MongoDB connection."""
        try:
            mongo_url = self.config.get("mongo_url", "mongodb://localhost:27017")
            db_name = self.config.get("db_name", "deepline")
            
            # Set a short timeout for testing connection
            self.mongo_client = AsyncIOMotorClient(
                mongo_url, 
                serverSelectionTimeoutMS=2000,  # 2 second timeout
                connectTimeoutMS=2000
            )
            self.db = self.mongo_client[db_name]
            self.use_mongo = True
            logger.info("MongoDB connection initialized")
        except Exception as e:
            logger.warning(f"MongoDB not available, using in-memory storage: {e}")
            self.mongo_client = None
            self.db = None
            self.use_mongo = False
    
    def _init_kafka(self):
        """Initialize Kafka producer."""
        try:
            kafka_config = {
                'bootstrap.servers': self.config.get("kafka_bootstrap_servers", "localhost:9092"),
                'client.id': 'workflow_manager'
            }
            
            self.kafka_producer = Producer(kafka_config)
            self.use_kafka = True
            logger.info("Kafka producer initialized")
        except Exception as e:
            logger.warning(f"Kafka not available, using direct execution: {e}")
            self.kafka_producer = None
            self.use_kafka = False
    
    def add_event_callback(self, callback: Callable):
        """Add event callback for workflow/task events."""
        self.event_callbacks.append(callback)
    
    async def _emit_event(self, event: Dict[str, Any]):
        """Emit event to all registered callbacks."""
        for callback in self.event_callbacks:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(event)
                else:
                    callback(event)
            except Exception as e:
                logger.error(f"Error in event callback: {e}")
    
    async def init_workflow(self, workflow_def: Dict[str, Any], metadata: Optional[Dict[str, Any]] = None, _retry: bool = False) -> str:
        """
        Initialize a new workflow.
        
        Args:
            workflow_def: Workflow definition with tasks
            metadata: Additional metadata for the workflow
            
        Returns:
            Workflow run ID
        """
        try:
            # Generate unique run ID
            run_id = f"run_{int(datetime.now().timestamp() * 1000)}"
            
            # Prepare workflow document
            workflow_doc = {
                "run_id": run_id,
                "workflow_definition": workflow_def,
                "status": WorkflowStatus.PENDING.value,
                "created_at": datetime.utcnow(),
                "updated_at": datetime.utcnow(),
                "metadata": metadata or {},
                "config_snapshot": self.config.copy(),
                "stats": {
                    "total_tasks": len(workflow_def.get("tasks", [])),
                    "completed_tasks": 0,
                    "failed_tasks": 0
                }
            }
            
            # Insert workflow into database or in-memory storage
            if self.use_mongo and self.db is not None:
                await self.db.runs.insert_one(workflow_doc)
                logger.info(f"Workflow {run_id} inserted into database")
            else:
                self.in_memory_workflows[run_id] = workflow_doc
                logger.info(f"Workflow {run_id} stored in memory")
            
            # Create task documents
            tasks = workflow_def.get("tasks", [])
            await self._create_task_documents(run_id, tasks)
            
            # Update statistics
            self.stats["workflows_created"] += 1
            
            # Emit workflow created event
            await self._emit_event({
                "type": "workflow_created",
                "run_id": run_id,
                "task_count": len(tasks),
                "timestamp": datetime.utcnow().isoformat()
            })
            
            logger.info(f"Workflow {run_id} initialized with {len(tasks)} tasks")
            return run_id
            
        except Exception as e:
            # Check if it's a MongoDB connection error and we haven't already retried
            if not _retry and any(keyword in str(e) for keyword in ["MongoDB", "Connection", "10061", "timed out", "NetworkTimeout", "localhost:27017"]):
                logger.warning(f"MongoDB connection failed, switching to in-memory storage: {e}")
                # Disable MongoDB and try again with in-memory storage
                self.use_mongo = False
                self.db = None
                self.mongo_client = None
                # Retry the workflow initialization with in-memory storage
                return await self.init_workflow(workflow_def, metadata, _retry=True)
            else:
                logger.error(f"Error initializing workflow: {e}")
                raise
    
    async def _create_task_documents(self, run_id: str, tasks: List[Dict[str, Any]]):
        """
        Create task documents in database or in-memory storage.
        
        Args:
            run_id: Workflow run ID
            tasks: List of task definitions
        """
        
        try:
            # Calculate in-degrees for dependency tracking
            task_deps = {}
            for task in tasks:
                task_id = task["id"]
                depends_on = task.get("depends_on", [])
                task_deps[task_id] = len(depends_on)
            
            # Create task documents
            task_docs = []
            for task in tasks:
                task_doc = {
                    "run_id": run_id,
                    "task_id": task["id"],
                    "definition": task,
                    "status": TaskStatus.PENDING.value,
                    "created_at": datetime.utcnow(),
                    "updated_at": datetime.utcnow(),
                    "retries": 0,
                    "in_degree": task_deps.get(task["id"], 0),
                    "original_in_degree": task_deps.get(task["id"], 0),
                    "agent": task.get("agent"),
                    "action": task.get("action"),
                    "params": task.get("params", {}),
                    "depends_on": task.get("depends_on", [])
                }
                task_docs.append(task_doc)
            
            # Bulk insert tasks into database or in-memory storage
            if task_docs:
                if self.use_mongo and self.db is not None:
                    await self.db.tasks.insert_many(task_docs)
                    logger.info(f"Created {len(task_docs)} task documents for workflow {run_id}")
                else:
                    for task_doc in task_docs:
                        task_key = f"{run_id}:{task_doc['task_id']}"
                        self.in_memory_tasks[task_key] = task_doc
                    logger.info(f"Created {len(task_docs)} task documents in memory for workflow {run_id}")
                
        except Exception as e:
            logger.error(f"Error creating task documents: {e}")
            raise
    
    async def start_workflow(self, run_id: str) -> bool:
        """
        Start workflow execution.
        
        Args:
            run_id: Workflow run ID
            
        Returns:
            True if started successfully
        """
        try:
            # Update workflow status
            if self.db is not None:
                await self.db.runs.update_one(
                    {"run_id": run_id},
                    {
                        "$set": {
                            "status": WorkflowStatus.RUNNING.value,
                            "started_at": datetime.utcnow(),
                            "updated_at": datetime.utcnow()
                        }
                    }
                )
            
            # Enqueue initial tasks (those with no dependencies)
            await self.enqueue_initial_tasks(run_id)
            
            # Emit workflow started event
            await self._emit_event({
                "type": "workflow_started",
                "run_id": run_id,
                "timestamp": datetime.utcnow().isoformat()
            })
            
            logger.info(f"Workflow {run_id} started")
            return True
            
        except Exception as e:
            logger.error(f"Error starting workflow {run_id}: {e}")
            return False
    
    async def enqueue_initial_tasks(self, run_id: str):
        """
        Enqueue tasks that have no dependencies.
        
        Args:
            run_id: Workflow run ID
        """
        try:
            if not self.db:
                logger.warning("Database not available, cannot enqueue tasks")
                return
            
            # Find tasks with in_degree = 0 (no dependencies)
            root_tasks = await self.db.tasks.find({
                "run_id": run_id,
                "in_degree": 0,
                "status": TaskStatus.PENDING.value
            }).to_list(None)
            
            for task in root_tasks:
                await self._enqueue_task(task)
            
            logger.info(f"Enqueued {len(root_tasks)} initial tasks for workflow {run_id}")
            
        except Exception as e:
            logger.error(f"Error enqueuing initial tasks: {e}")
            raise
    
    async def _enqueue_task(self, task: Dict[str, Any]):
        """
        Enqueue a single task for execution.
        
        Args:
            task: Task document
        """
        try:
            task_id = task["task_id"]
            run_id = task["run_id"]
            
            # Update task status to queued
            if self.db is not None:
                await self.db.tasks.update_one(
                    {"_id": task["_id"]},
                    {
                        "$set": {
                            "status": TaskStatus.QUEUED.value,
                            "queued_at": datetime.utcnow(),
                            "updated_at": datetime.utcnow()
                        }
                    }
                )
            
            # Prepare task metadata for workflow engine
            task_meta = {
                "run_id": run_id,
                "task_id": task_id,
                "agent": task["definition"].get("agent"),
                "action": task["definition"].get("action"),
                "params": task["definition"].get("params", {}),
                "depends_on": task["definition"].get("depends_on", []),
                "user_priority": task["definition"].get("priority", 0.5),
                "deadline_ts": task["definition"].get("deadline_ts"),
                "retries": task.get("retries", 0),
                "attempt": task.get("retries", 0) + 1,
                "metadata": task.get("metadata", {}),
                "timestamp": datetime.utcnow().isoformat()
            }
            
            # Enqueue in workflow engine scheduler (preferred) or fallback to Kafka
            enqueue_success = False
            if WORKFLOW_ENGINE_AVAILABLE:
                try:
                    enqueue_success = engine_enqueue_task(task_meta)
                    if enqueue_success:
                        logger.debug(f"Task {task_id} enqueued in workflow engine scheduler")
                except Exception as e:
                    logger.warning(f"Failed to enqueue in workflow engine, falling back to Kafka: {e}")
            
            # Fallback to Kafka if workflow engine not available or failed
            if not enqueue_success and self.kafka_producer:
                topic = self.config.get("task_requests_topic", "task.requests")
                kafka_payload = {
                    "run_id": run_id,
                    "task_id": task_id,
                    "definition": task["definition"],
                    "attempt": task.get("retries", 0) + 1,
                    "timestamp": datetime.utcnow().isoformat()
                }
                self.kafka_producer.produce(
                    topic,
                    value=json.dumps(kafka_payload),
                    key=task_id
                )
                self.kafka_producer.flush()
                logger.debug(f"Task {task_id} sent to Kafka topic {topic} (fallback)")
                enqueue_success = True
            
            # Update statistics
            self.stats["tasks_enqueued"] += 1
            
            # Emit task queued event
            await self._emit_event({
                "type": "task_queued",
                "run_id": run_id,
                "task_id": task_id,
                "agent": task.get("agent"),
                "action": task.get("action"),
                "timestamp": datetime.utcnow().isoformat()
            })
            
        except Exception as e:
            logger.error(f"Error enqueuing task {task.get('task_id', 'unknown')}: {e}")
            raise
    
    async def handle_task_completion(self, run_id: str, task_id: str, success: bool, result: Optional[Dict[str, Any]] = None):
        """
        Handle task completion and potentially enqueue dependent tasks.
        
        Args:
            run_id: Workflow run ID
            task_id: Completed task ID
            success: Whether task completed successfully
            result: Task execution result
        """
        try:
            if not self.db:
                logger.warning("Database not available, cannot handle task completion")
                return
            
            # Update task status
            new_status = TaskStatus.COMPLETED.value if success else TaskStatus.FAILED.value
            update_data = {
                "status": new_status,
                "completed_at": datetime.utcnow(),
                "updated_at": datetime.utcnow()
            }
            
            if result:
                update_data["result"] = result
            
            await self.db.tasks.update_one(
                {"run_id": run_id, "task_id": task_id},
                {"$set": update_data}
            )
            
            # Update workflow statistics
            if success:
                await self.db.runs.update_one(
                    {"run_id": run_id},
                    {
                        "$inc": {"stats.completed_tasks": 1},
                        "$set": {"updated_at": datetime.utcnow()}
                    }
                )
                self.stats["tasks_completed"] += 1
            else:
                await self.db.runs.update_one(
                    {"run_id": run_id},
                    {
                        "$inc": {"stats.failed_tasks": 1},
                        "$set": {"updated_at": datetime.utcnow()}
                    }
                )
                self.stats["tasks_failed"] += 1
            
            # If task succeeded, process dependent tasks
            if success:
                await self._process_dependent_tasks(run_id, task_id)
            
            # Check if workflow is complete
            await self._check_workflow_completion(run_id)
            
            # Emit task completion event
            await self._emit_event({
                "type": "task_completed" if success else "task_failed",
                "run_id": run_id,
                "task_id": task_id,
                "success": success,
                "result": result,
                "timestamp": datetime.utcnow().isoformat()
            })
            
            logger.info(f"Task {task_id} {'completed' if success else 'failed'}")
            
        except Exception as e:
            logger.error(f"Error handling task completion: {e}")
            raise
    
    async def _process_dependent_tasks(self, run_id: str, completed_task_id: str):
        """
        Process tasks that depend on the completed task.
        
        Args:
            run_id: Workflow run ID
            completed_task_id: ID of the completed task
        """
        try:
            # Find tasks that depend on the completed task
            dependent_tasks = await self.db.tasks.find({
                "run_id": run_id,
                "depends_on": completed_task_id,
                "status": TaskStatus.PENDING.value
            }).to_list(None)
            
            for task in dependent_tasks:
                # Decrement in_degree
                new_in_degree = task["in_degree"] - 1
                
                await self.db.tasks.update_one(
                    {"_id": task["_id"]},
                    {
                        "$set": {
                            "in_degree": new_in_degree,
                            "updated_at": datetime.utcnow()
                        }
                    }
                )
                
                # If in_degree reaches 0, enqueue the task
                if new_in_degree == 0:
                    # Refresh task document with updated in_degree
                    updated_task = await self.db.tasks.find_one({"_id": task["_id"]})
                    await self._enqueue_task(updated_task)
            
        except Exception as e:
            logger.error(f"Error processing dependent tasks: {e}")
            raise
    
    async def _check_workflow_completion(self, run_id: str):
        """
        Check if workflow is complete and update status.
        
        Args:
            run_id: Workflow run ID
        """
        try:
            # Get workflow and task counts
            workflow = await self.db.runs.find_one({"run_id": run_id})
            if not workflow:
                return
            
            total_tasks = workflow["stats"]["total_tasks"]
            completed_tasks = workflow["stats"]["completed_tasks"]
            failed_tasks = workflow["stats"]["failed_tasks"]
            
            # Check if all tasks are done
            if completed_tasks + failed_tasks >= total_tasks:
                if failed_tasks > 0:
                    # Workflow failed
                    await self.db.runs.update_one(
                        {"run_id": run_id},
                        {
                            "$set": {
                                "status": WorkflowStatus.FAILED.value,
                                "completed_at": datetime.utcnow(),
                                "updated_at": datetime.utcnow()
                            }
                        }
                    )
                    self.stats["workflows_failed"] += 1
                    
                    await self._emit_event({
                        "type": "workflow_failed",
                        "run_id": run_id,
                        "completed_tasks": completed_tasks,
                        "failed_tasks": failed_tasks,
                        "timestamp": datetime.utcnow().isoformat()
                    })
                    
                    logger.warning(f"Workflow {run_id} failed with {failed_tasks} failed tasks")
                else:
                    # Workflow completed successfully
                    await self.db.runs.update_one(
                        {"run_id": run_id},
                        {
                            "$set": {
                                "status": WorkflowStatus.COMPLETED.value,
                                "completed_at": datetime.utcnow(),
                                "updated_at": datetime.utcnow()
                            }
                        }
                    )
                    self.stats["workflows_completed"] += 1
                    
                    await self._emit_event({
                        "type": "workflow_completed",
                        "run_id": run_id,
                        "completed_tasks": completed_tasks,
                        "timestamp": datetime.utcnow().isoformat()
                    })
                    
                    logger.info(f"Workflow {run_id} completed successfully")
            
        except Exception as e:
            logger.error(f"Error checking workflow completion: {e}")
            raise
    
    async def cancel_workflow(self, run_id: str, reason: str = "User cancelled") -> bool:
        """
        Cancel a running workflow.
        
        Args:
            run_id: Workflow run ID
            reason: Cancellation reason
            
        Returns:
            True if cancelled successfully
        """
        try:
            if not self.db:
                return False
            
            # Update workflow status
            await self.db.runs.update_one(
                {"run_id": run_id},
                {
                    "$set": {
                        "status": WorkflowStatus.CANCELLED.value,
                        "cancelled_at": datetime.utcnow(),
                        "updated_at": datetime.utcnow(),
                        "cancellation_reason": reason
                    }
                }
            )
            
            # Cancel pending/queued tasks
            await self.db.tasks.update_many(
                {
                    "run_id": run_id,
                    "status": {"$in": [TaskStatus.PENDING.value, TaskStatus.QUEUED.value]}
                },
                {
                    "$set": {
                        "status": TaskStatus.CANCELLED.value,
                        "cancelled_at": datetime.utcnow(),
                        "updated_at": datetime.utcnow()
                    }
                }
            )
            
            # Emit cancellation event
            await self._emit_event({
                "type": "workflow_cancelled",
                "run_id": run_id,
                "reason": reason,
                "timestamp": datetime.utcnow().isoformat()
            })
            
            logger.info(f"Workflow {run_id} cancelled: {reason}")
            return True
            
        except Exception as e:
            logger.error(f"Error cancelling workflow {run_id}: {e}")
            return False
    
    async def get_workflow_status(self, run_id: str) -> Optional[Dict[str, Any]]:
        """
        Get workflow status and statistics.
        
        Args:
            run_id: Workflow run ID
            
        Returns:
            Workflow status dict or None if not found
        """
        try:
            if not self.db:
                return None
            
            workflow = await self.db.runs.find_one({"run_id": run_id})
            if not workflow:
                return None
            
            # Get task statistics
            task_stats = await self.db.tasks.aggregate([
                {"$match": {"run_id": run_id}},
                {"$group": {
                    "_id": "$status",
                    "count": {"$sum": 1}
                }}
            ]).to_list(None)
            
            status_counts = {stat["_id"]: stat["count"] for stat in task_stats}
            
            return {
                "run_id": run_id,
                "status": workflow["status"],
                "created_at": workflow["created_at"],
                "updated_at": workflow["updated_at"],
                "stats": workflow.get("stats", {}),
                "task_status_counts": status_counts,
                "metadata": workflow.get("metadata", {})
            }
            
        except Exception as e:
            logger.error(f"Error getting workflow status: {e}")
            return None
    
    async def _recompute_and_enqueue_tasks(self, run_id: str):
        """
        Recompute task dependencies and enqueue ready tasks.
        Used during rollback operations to resume workflow execution.
        
        Args:
            run_id: Workflow run ID
        """
        try:
            if self.use_mongo and self.db:
                # Get all tasks for this workflow
                tasks = await self.db.tasks.find({"run_id": run_id}).to_list(None)
                
                # Build dependency graph
                task_map = {task["task_id"]: task for task in tasks}
                
                # Find tasks that are ready to run (PENDING with no pending dependencies)
                ready_tasks = []
                for task in tasks:
                    if task["status"] == "PENDING":
                        dependencies = task.get("depends_on", [])
                        all_deps_complete = True
                        
                        for dep_id in dependencies:
                            dep_task = task_map.get(dep_id)
                            if not dep_task or dep_task["status"] != "SUCCESS":
                                all_deps_complete = False
                                break
                        
                        if all_deps_complete:
                            ready_tasks.append(task)
                
                # Enqueue ready tasks
                for task in ready_tasks:
                    await self._enqueue_task(run_id, task)
                    logger.info(f"Re-enqueued task {task['task_id']} after rollback")
                
                logger.info(f"Recomputed dependencies and enqueued {len(ready_tasks)} tasks for run {run_id}")
                
            else:
                # In-memory fallback
                logger.warning("Recompute with in-memory storage has limited functionality")
                
        except Exception as e:
            logger.error(f"Error recomputing tasks for run {run_id}: {e}")
            raise

    async def cancel_workflow(self, run_id: str, reason: str = "user-requested", 
                             force: bool = False, cancelled_by: str = "system") -> bool:
        """
        Cancel a running workflow gracefully.
        
        Args:
            run_id: Workflow run ID to cancel
            reason: Reason for cancellation
            force: Force cancellation even if tasks are running
            cancelled_by: Who or what initiated the cancellation
            
        Returns:
            True if cancellation was successful, False otherwise
        """
        try:
            if self.use_mongo and self.db:
                # Get workflow info
                workflow = await self.db.runs.find_one({"run_id": run_id})
                if not workflow:
                    logger.warning(f"Cannot cancel workflow {run_id}: not found")
                    return False
                
                current_status = workflow.get("status")
                if current_status in ["COMPLETED", "FAILED", "CANCELLED"]:
                    logger.warning(f"Cannot cancel workflow {run_id}: already in {current_status} state")
                    return False
                
                # Update workflow status
                cancellation_time = datetime.utcnow()
                await self.db.runs.update_one(
                    {"run_id": run_id},
                    {
                        "$set": {
                            "status": "CANCELLING",
                            "cancellation_reason": reason,
                            "cancelled_by": cancelled_by,
                            "cancelled_at": cancellation_time,
                            "updated_at": cancellation_time
                        }
                    }
                )
                
                # Cancel pending and queued tasks
                result = await self.db.tasks.update_many(
                    {"run_id": run_id, "status": {"$in": ["PENDING", "QUEUED"]}},
                    {
                        "$set": {
                            "status": "CANCELLED",
                            "cancellation_reason": reason,
                            "updated_at": cancellation_time
                        }
                    }
                )
                
                cancelled_task_count = result.modified_count
                
                # For running tasks, mark for cancellation and let workers handle them
                running_result = await self.db.tasks.update_many(
                    {"run_id": run_id, "status": "RUNNING"},
                    {
                        "$set": {
                            "cancellation_requested": True,
                            "cancellation_reason": reason,
                            "updated_at": cancellation_time
                        }
                    }
                )
                
                # Record cancelled runs in Redis for worker checking
                try:
                    import redis
                    redis_client = redis.Redis.from_url(
                        self.config.get("redis_url", "redis://localhost:6379"),
                        decode_responses=True
                    )
                    redis_client.sadd("cancelled_runs", run_id)
                    redis_client.expire("cancelled_runs", 86400)  # 24 hours
                except (ImportError, Exception) as e:
                    logger.warning(f"Could not mark run {run_id} as cancelled in Redis: {e}")
                
                logger.info(f"Cancelled workflow {run_id}: {cancelled_task_count} tasks cancelled, "
                           f"{running_result.modified_count} running tasks marked for cancellation")
                
                # Send cancellation event
                await self._send_event("WORKFLOW_CANCELLATION_INITIATED", {
                    "run_id": run_id,
                    "reason": reason,
                    "cancelled_by": cancelled_by,
                    "cancelled_tasks": cancelled_task_count,
                    "running_tasks_marked": running_result.modified_count
                })
                
                return True
                
            else:
                # In-memory fallback
                if run_id in self.in_memory_workflows:
                    workflow = self.in_memory_workflows[run_id]
                    workflow["status"] = "CANCELLED"
                    workflow["cancellation_reason"] = reason
                    workflow["cancelled_by"] = cancelled_by
                    workflow["cancelled_at"] = datetime.utcnow()
                    
                    # Cancel tasks
                    for task_id, task in self.in_memory_tasks.items():
                        if task.get("run_id") == run_id and task["status"] in ["PENDING", "QUEUED", "RUNNING"]:
                            task["status"] = "CANCELLED"
                            task["cancellation_reason"] = reason
                    
                    logger.info(f"Cancelled in-memory workflow {run_id}")
                    return True
                else:
                    logger.warning(f"Cannot cancel workflow {run_id}: not found in in-memory storage")
                    return False
                    
        except Exception as e:
            logger.error(f"Error cancelling workflow {run_id}: {e}", exc_info=True)
            return False

    async def get_workflow_status(self, run_id: str) -> Optional[Dict[str, Any]]:
        """
        Get detailed workflow status including cancellation information.
        
        Args:
            run_id: Workflow run ID
            
        Returns:
            Workflow status dictionary or None if not found
        """
        try:
            if self.use_mongo and self.db:
                workflow = await self.db.runs.find_one({"run_id": run_id})
                if not workflow:
                    return None
                
                # Get task counts
                task_counts = {}
                async for doc in self.db.tasks.aggregate([
                    {"$match": {"run_id": run_id}},
                    {"$group": {"_id": "$status", "count": {"$sum": 1}}}
                ]):
                    task_counts[doc["_id"]] = doc["count"]
                
                return {
                    "run_id": run_id,
                    "workflow_name": workflow.get("workflow_name"),
                    "status": workflow.get("status"),
                    "created_at": workflow.get("created_at"),
                    "updated_at": workflow.get("updated_at"),
                    "cancelled_at": workflow.get("cancelled_at"),
                    "cancellation_reason": workflow.get("cancellation_reason"),
                    "cancelled_by": workflow.get("cancelled_by"),
                    "client_id": workflow.get("client_id"),
                    "task_counts": task_counts,
                    "cancelled_task_count": task_counts.get("CANCELLED", 0)
                }
            else:
                # In-memory fallback
                workflow = self.in_memory_workflows.get(run_id)
                if not workflow:
                    return None
                
                return {
                    "run_id": run_id,
                    "workflow_name": workflow.get("workflow_name"),
                    "status": workflow.get("status"),
                    "created_at": workflow.get("created_at"),
                    "updated_at": workflow.get("updated_at"),
                    "cancelled_at": workflow.get("cancelled_at"),
                    "cancellation_reason": workflow.get("cancellation_reason"),
                    "cancelled_by": workflow.get("cancelled_by"),
                    "client_id": workflow.get("client_id")
                }
                
        except Exception as e:
            logger.error(f"Error getting workflow status for {run_id}: {e}")
            return None

    async def list_cancelled_workflows(self, limit: int = 50, offset: int = 0, 
                                     client_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        List cancelled workflows with pagination.
        
        Args:
            limit: Maximum number of results
            offset: Number of results to skip
            client_id: Optional filter by client ID
            
        Returns:
            List of cancelled workflow information
        """
        try:
            if self.use_mongo and self.db:
                query = {"status": {"$in": ["CANCELLED", "CANCELLING"]}}
                if client_id:
                    query["client_id"] = client_id
                
                workflows = []
                async for workflow in self.db.runs.find(query).sort("cancelled_at", -1).skip(offset).limit(limit):
                    # Get task count
                    task_count = await self.db.tasks.count_documents({"run_id": workflow["run_id"]})
                    
                    workflows.append({
                        "run_id": workflow["run_id"],
                        "workflow_name": workflow.get("workflow_name"),
                        "status": workflow["status"],
                        "cancelled_at": workflow.get("cancelled_at"),
                        "cancellation_reason": workflow.get("cancellation_reason", ""),
                        "cancelled_by": workflow.get("cancelled_by"),
                        "task_count": task_count,
                        "client_id": workflow.get("client_id")
                    })
                
                return workflows
            else:
                # In-memory fallback
                cancelled = [
                    w for w in self.in_memory_workflows.values()
                    if w.get("status") in ["CANCELLED", "CANCELLING"] and
                    (not client_id or w.get("client_id") == client_id)
                ]
                
                # Sort by cancelled_at descending
                cancelled.sort(key=lambda x: x.get("cancelled_at", datetime.min), reverse=True)
                
                return cancelled[offset:offset + limit]
                
        except Exception as e:
            logger.error(f"Error listing cancelled workflows: {e}")
            return []

    async def force_complete_cancellation(self, run_id: str) -> bool:
        """
        Force complete cancellation of a workflow, marking it as CANCELLED.
        
        Args:
            run_id: Workflow run ID
            
        Returns:
            True if successful, False otherwise
        """
        try:
            if self.use_mongo and self.db:
                # Update workflow to CANCELLED
                result = await self.db.runs.update_one(
                    {"run_id": run_id, "status": "CANCELLING"},
                    {
                        "$set": {
                            "status": "CANCELLED",
                            "updated_at": datetime.utcnow()
                        }
                    }
                )
                
                if result.modified_count == 0:
                    return False
                
                # Mark any remaining running tasks as cancelled
                await self.db.tasks.update_many(
                    {"run_id": run_id, "status": "RUNNING"},
                    {
                        "$set": {
                            "status": "CANCELLED",
                            "updated_at": datetime.utcnow()
                        }
                    }
                )
                
                logger.info(f"Force completed cancellation for workflow {run_id}")
                return True
            else:
                # In-memory fallback
                workflow = self.in_memory_workflows.get(run_id)
                if workflow and workflow.get("status") == "CANCELLING":
                    workflow["status"] = "CANCELLED"
                    workflow["updated_at"] = datetime.utcnow()
                    return True
                return False
                
        except Exception as e:
            logger.error(f"Error force completing cancellation for {run_id}: {e}")
            return False

    def get_statistics(self) -> Dict[str, Any]:
        """Get workflow manager statistics."""
        return {
            **self.stats,
            "mongo_available": self.db is not None,
            "kafka_available": self.kafka_producer is not None,
            "active_callbacks": len(self.event_callbacks)
        }


# Module-level convenience functions for external use
async def cancel_workflow_internal(run_id: str, reason: str = "system", 
                                 force: bool = False, cancelled_by: str = "system") -> bool:
    """
    Module-level function for cancelling workflows.
    
    This is used by the deadlock monitor and cancellation API.
    """
    try:
        # Import here to avoid circular imports
        from config import get_config
        config = get_config()
        
        # Create a temporary workflow manager instance
        manager = WorkflowManager(config.master_orchestrator.infrastructure.dict())
        return await manager.cancel_workflow(run_id, reason, force, cancelled_by)
    except Exception as e:
        logger.error(f"Error in cancel_workflow_internal: {e}")
        return False


async def get_workflow_status(run_id: str) -> Optional[Dict[str, Any]]:
    """Module-level function for getting workflow status."""
    try:
        from config import get_config
        config = get_config()
        
        manager = WorkflowManager(config.master_orchestrator.infrastructure.dict())
        return await manager.get_workflow_status(run_id)
    except Exception as e:
        logger.error(f"Error in get_workflow_status: {e}")
        return None


async def list_cancelled_workflows(limit: int = 50, offset: int = 0, 
                                 client_id: Optional[str] = None) -> List[Dict[str, Any]]:
    """Module-level function for listing cancelled workflows."""
    try:
        from config import get_config
        config = get_config()
        
        manager = WorkflowManager(config.master_orchestrator.infrastructure.dict())
        return await manager.list_cancelled_workflows(limit, offset, client_id)
    except Exception as e:
        logger.error(f"Error in list_cancelled_workflows: {e}")
        return []


async def force_complete_cancellation(run_id: str) -> bool:
    """Module-level function for force completing cancellation."""
    try:
        from config import get_config
        config = get_config()
        
        manager = WorkflowManager(config.master_orchestrator.infrastructure.dict())
        return await manager.force_complete_cancellation(run_id)
    except Exception as e:
        logger.error(f"Error in force_complete_cancellation: {e}")
        return False 