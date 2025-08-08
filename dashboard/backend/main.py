from fastapi import FastAPI, WebSocket, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
from confluent_kafka import Consumer
import asyncio
import json
import threading
from typing import Dict, List, Optional
import logging
from bson import ObjectId
from datetime import datetime, timedelta
from enum import Enum
import time
import yaml
from pathlib import Path
import sys
import os

# Add the parent directory to the path to import config
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..', 'mcp-server'))

try:
    from orchestrator_tools.config import load_config, EDAConfig
except ImportError:
    # Fallback if config module is not available
    print("Warning: Could not import config module. Using default configuration.")
    config = None

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load configuration
try:
    config = load_config(os.path.join(os.path.dirname(__file__), '..', '..', 'mcp-server', 'config.yaml'))
    logger.info("Configuration loaded successfully")
except Exception as e:
    logger.error(f"Failed to load configuration: {e}")
    config = None

app = FastAPI(title="Deepline Observability Dashboard")

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],  # React dev server
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# MongoDB connection
db = AsyncIOMotorClient("mongodb://localhost:27017").deepline

# Store active WebSocket connections
active_connections: List[WebSocket] = []

class WorkflowStatus(Enum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"

class TaskStatus(Enum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"

# Orchestrator state management
class OrchestratorState:
    def __init__(self):
        self.running_workflows = 0
        self.workflow_queue = []
        self.task_retry_counts = {}
        self.lock = asyncio.Lock()
    
    async def can_start_workflow(self) -> bool:
        """Check if we can start a new workflow based on concurrency limits"""
        if not config:
            return True  # No config, allow all workflows
        
        async with self.lock:
            return self.running_workflows < config.orchestrator.max_concurrent_workflows
    
    async def start_workflow(self, workflow_id: str):
        """Mark a workflow as started"""
        async with self.lock:
            self.running_workflows += 1
            logger.info(f"Started workflow {workflow_id}. Running workflows: {self.running_workflows}")
    
    async def complete_workflow(self, workflow_id: str):
        """Mark a workflow as completed"""
        async with self.lock:
            self.running_workflows = max(0, self.running_workflows - 1)
            logger.info(f"Completed workflow {workflow_id}. Running workflows: {self.running_workflows}")
    
    async def get_retry_count(self, task_id: str) -> int:
        """Get the current retry count for a task"""
        return self.task_retry_counts.get(task_id, 0)
    
    async def increment_retry_count(self, task_id: str) -> int:
        """Increment retry count for a task and return new count"""
        async with self.lock:
            count = self.task_retry_counts.get(task_id, 0) + 1
            self.task_retry_counts[task_id] = count
            return count
    
    async def clear_retry_count(self, task_id: str):
        """Clear retry count for a task"""
        async with self.lock:
            if task_id in self.task_retry_counts:
                del self.task_retry_counts[task_id]

orchestrator_state = OrchestratorState()

async def calculate_backoff_delay(retry_count: int) -> int:
    """Calculate exponential backoff delay"""
    if not config:
        return 30  # Default 30 seconds
    
    base = config.orchestrator.retry.backoff_base_s
    max_delay = config.orchestrator.retry.backoff_max_s
    
    delay = base * (2 ** retry_count)
    return min(delay, max_delay)

async def should_retry_task(task_id: str, error: str) -> bool:
    """Determine if a task should be retried based on configuration"""
    if not config:
        return False
    
    retry_count = await orchestrator_state.get_retry_count(task_id)
    max_retries = config.orchestrator.retry.max_retries
    
    if retry_count >= max_retries:
        logger.info(f"Task {task_id} has reached maximum retry count ({max_retries})")
        return False
    
    # Add logic here to determine if specific errors should be retried
    # For now, retry all errors
    return True

def serialize_doc(doc):
    """Convert MongoDB document to JSON serializable format"""
    if doc is None:
        return None
    if isinstance(doc, list):
        return [serialize_doc(item) for item in doc]
    if isinstance(doc, dict):
        result = {}
        for key, value in doc.items():
            if isinstance(value, ObjectId):
                result[key] = str(value)
            elif isinstance(value, (dict, list)):
                result[key] = serialize_doc(value)
            else:
                result[key] = value
        return result
    return doc

@app.get("/")
async def root():
    """Health check endpoint"""
    return {"status": "running", "message": "Deepline Observability Dashboard"}

@app.post("/runs")
async def create_run(workflow_data: dict):
    """Create a new workflow run with concurrency checks"""
    try:
        # Check if we can start a new workflow
        if not await orchestrator_state.can_start_workflow():
            raise HTTPException(
                status_code=429, 
                detail="Maximum concurrent workflows reached. Please try again later."
            )
        
        # Create workflow document
        workflow_id = workflow_data.get("workflow_id", f"workflow_{int(time.time())}")
        run_doc = {
            "run_id": workflow_id,
            "status": WorkflowStatus.QUEUED.value,
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
            "workflow_data": workflow_data,
            "sla_task_complete_s": config.orchestrator.scheduling.sla_task_complete_s if config else 600,
            "sla_workflow_complete_s": config.orchestrator.scheduling.sla_workflow_complete_s if config else 3600
        }
        
        # Insert into database
        await db.runs.insert_one(run_doc)
        
        # Mark workflow as started
        await orchestrator_state.start_workflow(workflow_id)
        
        # Update status to running
        await db.runs.update_one(
            {"run_id": workflow_id},
            {"$set": {"status": WorkflowStatus.RUNNING.value, "updated_at": datetime.utcnow()}}
        )
        
        # Broadcast event
        await broadcast_event({
            "type": "workflow_started",
            "workflow_id": workflow_id,
            "timestamp": datetime.utcnow().isoformat()
        })
        
        return {"workflow_id": workflow_id, "status": "started"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating run: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.put("/runs/{run_id}/complete")
async def complete_run(run_id: str):
    """Mark a workflow run as completed"""
    try:
        # Update database
        await db.runs.update_one(
            {"run_id": run_id},
            {"$set": {"status": WorkflowStatus.COMPLETED.value, "updated_at": datetime.utcnow()}}
        )
        
        # Mark workflow as completed in orchestrator
        await orchestrator_state.complete_workflow(run_id)
        
        # Broadcast event
        await broadcast_event({
            "type": "workflow_completed",
            "workflow_id": run_id,
            "timestamp": datetime.utcnow().isoformat()
        })
        
        return {"workflow_id": run_id, "status": "completed"}
        
    except Exception as e:
        logger.error(f"Error completing run {run_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.put("/runs/{run_id}/fail")
async def fail_run(run_id: str, error_data: dict):
    """Mark a workflow run as failed"""
    try:
        # Update database
        await db.runs.update_one(
            {"run_id": run_id},
            {"$set": {
                "status": WorkflowStatus.FAILED.value, 
                "updated_at": datetime.utcnow(),
                "error": error_data.get("error", "Unknown error")
            }}
        )
        
        # Mark workflow as completed in orchestrator
        await orchestrator_state.complete_workflow(run_id)
        
        # Broadcast event
        await broadcast_event({
            "type": "workflow_failed",
            "workflow_id": run_id,
            "error": error_data.get("error", "Unknown error"),
            "timestamp": datetime.utcnow().isoformat()
        })
        
        return {"workflow_id": run_id, "status": "failed"}
        
    except Exception as e:
        logger.error(f"Error failing run {run_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.put("/tasks/{task_id}/retry")
async def retry_task(task_id: str):
    """Retry a failed task with exponential backoff"""
    try:
        # Get current task
        task = await db.tasks.find_one({"task_id": task_id})
        if not task:
            raise HTTPException(status_code=404, detail="Task not found")
        
        # Check if task should be retried
        if not await should_retry_task(task_id, task.get("error", "")):
            raise HTTPException(status_code=400, detail="Task cannot be retried")
        
        # Increment retry count
        retry_count = await orchestrator_state.increment_retry_count(task_id)
        
        # Calculate backoff delay
        backoff_delay = await calculate_backoff_delay(retry_count)
        
        # Schedule retry
        retry_at = datetime.utcnow() + timedelta(seconds=backoff_delay)
        
        # Update task
        await db.tasks.update_one(
            {"task_id": task_id},
            {"$set": {
                "status": TaskStatus.QUEUED.value,
                "retry_count": retry_count,
                "retry_at": retry_at,
                "updated_at": datetime.utcnow()
            }}
        )
        
        # Broadcast event
        await broadcast_event({
            "type": "task_retried",
            "task_id": task_id,
            "retry_count": retry_count,
            "retry_at": retry_at.isoformat(),
            "timestamp": datetime.utcnow().isoformat()
        })
        
        return {
            "task_id": task_id, 
            "status": "queued_for_retry",
            "retry_count": retry_count,
            "retry_at": retry_at.isoformat()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrying task {task_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/runs/{run_id}")
async def get_run(run_id: str):
    """Get a specific run with its tasks"""
    try:
        run = await db.runs.find_one({"run_id": run_id})
        tasks = await db.tasks.find({"run_id": run_id}).to_list(100)
        return {
            "run": serialize_doc(run), 
            "tasks": serialize_doc(tasks)
        }
    except Exception as e:
        logger.error(f"Error fetching run {run_id}: {e}")
        return {"error": str(e)}

@app.get("/runs")
async def get_runs(limit: int = 10):
    """Get recent runs"""
    try:
        runs = await db.runs.find().sort([("_id", -1)]).limit(limit).to_list(limit)
        return {"runs": serialize_doc(runs)}
    except Exception as e:
        logger.error(f"Error fetching runs: {e}")
        return {"error": str(e)}

@app.get("/tasks/{task_id}")
async def get_task(task_id: str):
    """Get a specific task"""
    try:
        task = await db.tasks.find_one({"task_id": task_id})
        return {"task": serialize_doc(task)}
    except Exception as e:
        logger.error(f"Error fetching task {task_id}: {e}")
        return {"error": str(e)}

@app.websocket("/ws/events")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint for live event streaming"""
    await websocket.accept()
    active_connections.append(websocket)
    logger.info(f"Client connected. Total connections: {len(active_connections)}")
    
    try:
        while True:
            # Keep connection alive
            await websocket.receive_text()
    except Exception as e:
        logger.info(f"WebSocket disconnected: {e}")
    finally:
        active_connections.remove(websocket)
        logger.info(f"Client disconnected. Total connections: {len(active_connections)}")

async def broadcast_event(event: dict):
    """Broadcast event to all connected WebSocket clients"""
    if active_connections:
        disconnected = []
        for connection in active_connections:
            try:
                await connection.send_text(json.dumps(event))
            except Exception as e:
                logger.error(f"Error sending to WebSocket: {e}")
                disconnected.append(connection)
        
        # Remove disconnected clients
        for connection in disconnected:
            active_connections.remove(connection)

def kafka_consumer():
    """Kafka consumer running in a separate thread"""
    try:
        consumer = Consumer({
            'bootstrap.servers': 'localhost:9092',
            'group.id': 'dashboard',
            'auto.offset.reset': 'latest'
        })
        consumer.subscribe(['task.events'])
        logger.info("Kafka consumer started")
        
        while True:
            msg = consumer.poll(1.0)
            if msg is None:
                continue
            if msg.error():
                logger.error(f"Kafka error: {msg.error()}")
                continue
            
            try:
                event = json.loads(msg.value().decode('utf-8'))
                # Schedule the broadcast in the main event loop
                asyncio.run_coroutine_threadsafe(broadcast_event(event), asyncio.get_event_loop())
            except json.JSONDecodeError as e:
                logger.error(f"Error parsing Kafka message: {e}")
            except Exception as e:
                logger.error(f"Error processing Kafka message: {e}")
                
    except Exception as e:
        logger.error(f"Kafka consumer error: {e}")

async def sla_monitor():
    """Background task to monitor SLA violations"""
    logger.info("SLA monitor started")
    
    while True:
        try:
            if not config:
                await asyncio.sleep(60)  # Check every minute if no config
                continue
            
            current_time = datetime.utcnow()
            
            # Check for stale tasks
            task_sla_seconds = config.orchestrator.scheduling.sla_task_complete_s
            task_sla_cutoff = current_time - timedelta(seconds=task_sla_seconds)
            
            stale_tasks = await db.tasks.find({
                "status": {"$in": [TaskStatus.QUEUED.value, TaskStatus.RUNNING.value]},
                "created_at": {"$lt": task_sla_cutoff}
            }).to_list(100)
            
            for task in stale_tasks:
                task_id = task["task_id"]
                age_seconds = (current_time - task["created_at"]).total_seconds()
                
                logger.warning(f"SLA violation: Task {task_id} has been {task['status']} for {age_seconds:.0f} seconds (SLA: {task_sla_seconds}s)")
                
                # Broadcast SLA violation event
                await broadcast_event({
                    "type": "sla_violation",
                    "resource_type": "task",
                    "resource_id": task_id,
                    "status": task["status"],
                    "age_seconds": age_seconds,
                    "sla_seconds": task_sla_seconds,
                    "timestamp": current_time.isoformat()
                })
                
                # Mark task as SLA violated
                await db.tasks.update_one(
                    {"task_id": task_id},
                    {"$set": {"sla_violated": True, "sla_violated_at": current_time}}
                )
            
            # Check for stale workflows
            workflow_sla_seconds = config.orchestrator.scheduling.sla_workflow_complete_s
            workflow_sla_cutoff = current_time - timedelta(seconds=workflow_sla_seconds)
            
            stale_workflows = await db.runs.find({
                "status": {"$in": [WorkflowStatus.QUEUED.value, WorkflowStatus.RUNNING.value]},
                "created_at": {"$lt": workflow_sla_cutoff}
            }).to_list(100)
            
            for workflow in stale_workflows:
                workflow_id = workflow["run_id"]
                age_seconds = (current_time - workflow["created_at"]).total_seconds()
                
                logger.warning(f"SLA violation: Workflow {workflow_id} has been {workflow['status']} for {age_seconds:.0f} seconds (SLA: {workflow_sla_seconds}s)")
                
                # Broadcast SLA violation event
                await broadcast_event({
                    "type": "sla_violation",
                    "resource_type": "workflow",
                    "resource_id": workflow_id,
                    "status": workflow["status"],
                    "age_seconds": age_seconds,
                    "sla_seconds": workflow_sla_seconds,
                    "timestamp": current_time.isoformat()
                })
                
                # Mark workflow as SLA violated
                await db.runs.update_one(
                    {"run_id": workflow_id},
                    {"$set": {"sla_violated": True, "sla_violated_at": current_time}}
                )
            
            # Sleep for 30 seconds before next check
            await asyncio.sleep(30)
            
        except Exception as e:
            logger.error(f"Error in SLA monitor: {e}")
            await asyncio.sleep(60)  # Wait longer on error

@app.on_event("startup")
async def startup_event():
    """Start background tasks"""
    logger.info("Starting Deepline Observability Dashboard")
    
    # Start Kafka consumer in a separate thread
    kafka_thread = threading.Thread(target=kafka_consumer, daemon=True)
    kafka_thread.start()
    logger.info("Kafka consumer thread started")
    
    # Start SLA monitor as an async task
    asyncio.create_task(sla_monitor())
    logger.info("SLA monitor task started")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=True) 