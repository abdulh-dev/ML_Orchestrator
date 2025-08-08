#!/usr/bin/env python3
"""
Enhanced Master Orchestrator API with Step-by-Step Results Capture

Coordinates workflows between different agents and captures detailed results from each step.
"""

from fastapi import FastAPI, HTTPException, UploadFile, File, Form, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
import uvicorn
import asyncio
import json
import uuid
import time
import os
import shutil
from pathlib import Path
import requests
from datetime import datetime
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize FastAPI app
app = FastAPI(
    title="Enhanced Master Orchestrator API",
    description="Orchestrates workflows with detailed step-by-step result capture",
    version="2.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── DATA MODELS ──────────────────────────────────────────────────────────────

class Task(BaseModel):
    agent: str
    action: str
    args: Dict[str, Any]

class WorkflowRequest(BaseModel):
    run_name: str
    tasks: List[Task]
    priority: Optional[int] = 1

class WorkflowResponse(BaseModel):
    run_id: str
    status: str
    message: str

class StepResult(BaseModel):
    step_number: int
    agent: str
    action: str
    status: str
    start_time: str
    end_time: Optional[str] = None
    results: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    duration_seconds: Optional[float] = None

class EnhancedRunStatus(BaseModel):
    run_id: str
    status: str
    progress: float
    current_task: Optional[str]
    start_time: str
    end_time: Optional[str]
    error_message: Optional[str]
    steps: List[StepResult] = []
    total_steps: int = 0

# ─── GLOBAL STATE ─────────────────────────────────────────────────────────────

# Enhanced storage with step results
workflows = {}
datasets = {}
artifacts = {}
run_status = {}
step_results = {}  # New: Store detailed step results

# Configuration
EDA_AGENT_URL = "http://localhost:8001"
GRAPHING_AGENT_URL = "http://localhost:8002"
UPLOAD_DIR = "uploads"
ARTIFACT_DIR = "artifacts"
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(ARTIFACT_DIR, exist_ok=True)

# ─── HELPER FUNCTIONS ─────────────────────────────────────────────────────────

def get_agent_url(agent_name: str) -> str:
    """Get the URL for a specific agent."""
    agent_urls = {
        "eda_agent": EDA_AGENT_URL,
        "graphing_agent": GRAPHING_AGENT_URL,
    }
    return agent_urls.get(agent_name, "")

def store_step_result(run_id: str, step_number: int, agent: str, action: str, 
                     status: str, results: Dict[str, Any] = None, error: str = None,
                     start_time: str = None, end_time: str = None):
    """Store detailed results for a workflow step."""
    if run_id not in step_results:
        step_results[run_id] = []
    
    duration = None
    if start_time and end_time:
        try:
            start_dt = datetime.fromisoformat(start_time.replace('Z', '+00:00'))
            end_dt = datetime.fromisoformat(end_time.replace('Z', '+00:00'))
            duration = (end_dt - start_dt).total_seconds()
        except:
            pass
    
    step_result = StepResult(
        step_number=step_number,
        agent=agent,
        action=action,
        status=status,
        start_time=start_time or datetime.now().isoformat(),
        end_time=end_time,
        results=results,
        error=error,
        duration_seconds=duration
    )
    
    step_results[run_id].append(step_result)
    logger.info(f"Stored step result for {run_id}: Step {step_number} - {agent}:{action} = {status}")

async def execute_task_with_results(task: Task, run_id: str, step_number: int) -> Dict[str, Any]:
    """Execute a single task and capture detailed results."""
    agent_url = get_agent_url(task.agent)
    if not agent_url:
        error_msg = f"Unknown agent: {task.agent}"
        store_step_result(run_id, step_number, task.agent, task.action, "failed", error=error_msg)
        raise HTTPException(status_code=400, detail=error_msg)
    
    start_time = datetime.now().isoformat()
    
    try:
        logger.info(f"Executing Step {step_number}: {task.action} on {task.agent}")
        
        # Store step start
        store_step_result(run_id, step_number, task.agent, task.action, "running", start_time=start_time)
        
        # Call the agent's endpoint
        response = requests.post(
            f"{agent_url}/{task.action}",
            json=task.args,
            timeout=120
        )
        response.raise_for_status()
        
        end_time = datetime.now().isoformat()
        result = response.json()
        
        # Extract meaningful summary from result
        summary = extract_result_summary(task.agent, task.action, result)
        
        # Store successful result
        store_step_result(
            run_id, step_number, task.agent, task.action, "completed",
            results={
                "summary": summary,
                "data": result,
                "response_size": len(str(result))
            },
            start_time=start_time,
            end_time=end_time
        )
        
        logger.info(f"Step {step_number} completed successfully: {task.action}")
        return result
        
    except requests.exceptions.RequestException as e:
        end_time = datetime.now().isoformat()
        error_msg = f"Agent task failed: {str(e)}"
        
        # Store failed result
        store_step_result(
            run_id, step_number, task.agent, task.action, "failed",
            error=error_msg,
            start_time=start_time,
            end_time=end_time
        )
        
        logger.error(f"Step {step_number} failed: {task.action} - {str(e)}")
        raise HTTPException(status_code=500, detail=error_msg)

def extract_result_summary(agent: str, action: str, result: Dict[str, Any]) -> str:
    """Extract a human-readable summary from agent results."""
    try:
        if agent == "eda_agent":
            if action == "profile_dataset":
                basic_info = result.get("basic_info", {})
                shape = basic_info.get("shape", {})
                return f"📊 Profiled dataset: {shape.get('rows', '?')} rows, {shape.get('columns', '?')} columns"
            
            elif action == "statistical_summary":
                summary = result.get("summary", {})
                return f"📈 Generated statistics for {len(summary)} numeric columns"
            
            elif action == "data_quality":
                quality_score = result.get("quality_score", 0)
                missing_values = result.get("missing_values", {})
                total_missing = sum(info.get("missing_count", 0) for info in missing_values.values()) if missing_values else 0
                return f"🔍 Quality score: {quality_score:.1f}/100, {total_missing} missing values detected"
            
            elif action == "correlation_analysis":
                correlations = result.get("correlations", {})
                top_corrs = result.get("top_correlations", {})
                strongest = list(top_corrs.keys())[0] if top_corrs else "None"
                return f"🔗 Found {len(correlations)} correlation pairs, strongest: {strongest}"
        
        elif agent == "graphing_agent":
            if action == "histogram":
                file_path = result.get("file_path", "")
                column = result.get("column", "")
                stats = result.get("statistics", {})
                mean_val = stats.get("mean", 0)
                return f"📊 Created histogram for '{column}' (mean: {mean_val:.2f}) → {Path(file_path).name if file_path else 'visualization'}"
            
            elif action == "scatter_plot":
                file_path = result.get("file_path", "")
                x_col = result.get("x_column", "")
                y_col = result.get("y_column", "")
                correlation = result.get("correlation", None)
                corr_text = f", correlation: {correlation:.3f}" if correlation else ""
                return f"📈 Created scatter plot: {x_col} vs {y_col}{corr_text} → {Path(file_path).name if file_path else 'visualization'}"
            
            elif action == "correlation_heatmap":
                file_path = result.get("file_path", "")
                variables = result.get("variables", [])
                return f"🔥 Created correlation heatmap for {len(variables)} variables → {Path(file_path).name if file_path else 'visualization'}"
            
            elif action == "box_plot":
                file_path = result.get("file_path", "")
                columns = result.get("columns", [])
                groupby = result.get("groupby_column", "")
                group_text = f" grouped by {groupby}" if groupby else ""
                return f"📦 Created box plot for {', '.join(columns)}{group_text} → {Path(file_path).name if file_path else 'visualization'}"
            
            elif action == "multi_plot":
                file_path = result.get("file_path", "")
                plot_count = result.get("number_of_plots", 0)
                return f"📊 Created dashboard with {plot_count} plots → {Path(file_path).name if file_path else 'visualization'}"
            
            elif action == "distribution_plot":
                file_path = result.get("file_path", "")
                columns = result.get("columns", [])
                return f"📈 Created distribution analysis for {', '.join(columns)} → {Path(file_path).name if file_path else 'visualization'}"
        
        # Generic fallback
        return f"✅ Completed {action} successfully"
        
    except Exception as e:
        return f"✅ Completed {action} (summary extraction failed: {str(e)})"

async def run_workflow_with_results(run_id: str, workflow_request: WorkflowRequest):
    """Execute a workflow with detailed step result capture."""
    try:
        logger.info(f"Starting enhanced workflow: {run_id}")
        
        # Initialize enhanced status
        run_status[run_id] = {
            "run_id": run_id,
            "status": "RUNNING",
            "progress": 0.0,
            "current_task": None,
            "start_time": datetime.now().isoformat(),
            "end_time": None,
            "error_message": None,
            "total_steps": len(workflow_request.tasks)
        }
        
        # Initialize step results storage
        step_results[run_id] = []
        
        total_tasks = len(workflow_request.tasks)
        
        for i, task in enumerate(workflow_request.tasks):
            step_number = i + 1
            
            try:
                # Update current task
                run_status[run_id]["current_task"] = f"{task.agent}:{task.action}"
                run_status[run_id]["progress"] = (i / total_tasks) * 100
                
                # Execute task with result capture
                result = await execute_task_with_results(task, run_id, step_number)
                
                # Store artifact information if applicable
                if run_id not in artifacts:
                    artifacts[run_id] = []
                
                # Check if result contains visualization files
                if "file_path" in result:
                    file_path = result["file_path"]
                    if os.path.exists(file_path):
                        # Copy file to a shared location accessible by backend
                        filename = Path(file_path).name
                        shared_path = Path("shared_artifacts") / filename
                        shared_path.parent.mkdir(exist_ok=True)
                        
                        import shutil
                        shutil.copy2(file_path, shared_path)
                        logger.info(f"Copied visualization to shared location: {shared_path}")
                        
                        artifact = {
                            "artifact_id": str(uuid.uuid4()),
                            "type": "visualization",
                            "filename": filename,
                            "original_path": str(file_path),
                            "shared_path": str(shared_path),
                            "size": os.path.getsize(file_path),
                            "created_at": datetime.now().isoformat(),
                            "download_url": f"/artifacts/{run_id}/{filename}",
                            "step_number": step_number
                        }
                        artifacts[run_id].append(artifact)
                
                # Check for multiple files (multi_plot)
                if "visualization_files" in result:
                    for viz_file in result["visualization_files"]:
                        if os.path.exists(viz_file):
                            filename = Path(viz_file).name
                            shared_path = Path("shared_artifacts") / filename
                            shared_path.parent.mkdir(exist_ok=True)
                            
                            import shutil
                            shutil.copy2(viz_file, shared_path)
                            logger.info(f"Copied multi-plot visualization to shared location: {shared_path}")
                            
                            artifact = {
                                "artifact_id": str(uuid.uuid4()),
                                "type": "visualization",
                                "filename": filename,
                                "original_path": str(viz_file),
                                "shared_path": str(shared_path),
                                "size": os.path.getsize(viz_file),
                                "created_at": datetime.now().isoformat(),
                                "download_url": f"/artifacts/{run_id}/{filename}",
                                "step_number": step_number
                            }
                            artifacts[run_id].append(artifact)
                
                logger.info(f"Step {step_number}/{total_tasks} completed: {task.action}")
                
            except Exception as e:
                logger.error(f"Step {step_number} failed: {task.action} - {str(e)}")
                run_status[run_id]["status"] = "FAILED"
                run_status[run_id]["error_message"] = str(e)
                run_status[run_id]["end_time"] = datetime.now().isoformat()
                return
        
        # Mark as completed
        run_status[run_id]["status"] = "COMPLETED"
        run_status[run_id]["progress"] = 100.0
        run_status[run_id]["end_time"] = datetime.now().isoformat()
        run_status[run_id]["current_task"] = None
        
        logger.info(f"Enhanced workflow completed: {run_id}")
        
    except Exception as e:
        logger.error(f"Enhanced workflow failed: {run_id} - {str(e)}")
        if run_id in run_status:
            run_status[run_id]["status"] = "FAILED"
            run_status[run_id]["error_message"] = str(e)
            run_status[run_id]["end_time"] = datetime.now().isoformat()

# ─── ENHANCED API ENDPOINTS ──────────────────────────────────────────────────

@app.get("/")
async def root():
    """Root endpoint with API information."""
    return {
        "message": "Enhanced Master Orchestrator API",
        "version": "2.0.0",
        "status": "operational",
        "agents": ["eda_agent", "graphing_agent"],
        "features": ["step_result_capture", "detailed_monitoring"],
        "docs": "/docs"
    }

@app.get("/health")
async def health_check():
    """Enhanced health check endpoint."""
    agent_status = {}
    
    # Check EDA Agent
    try:
        response = requests.get(f"{EDA_AGENT_URL}/health", timeout=5)
        agent_status["eda_agent"] = {
            "url": EDA_AGENT_URL,
            "status": "healthy" if response.status_code == 200 else "unhealthy",
            "response_time": response.elapsed.total_seconds()
        }
    except:
        agent_status["eda_agent"] = {
            "url": EDA_AGENT_URL,
            "status": "unreachable"
        }
    
    # Check Graphing Agent
    try:
        response = requests.get(f"{GRAPHING_AGENT_URL}/health", timeout=5)
        agent_status["graphing_agent"] = {
            "url": GRAPHING_AGENT_URL,
            "status": "healthy" if response.status_code == 200 else "unhealthy",
            "response_time": response.elapsed.total_seconds()
        }
    except:
        agent_status["graphing_agent"] = {
            "url": GRAPHING_AGENT_URL,
            "status": "unreachable"
        }
    
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "agents": agent_status,
        "active_workflows": len([r for r in run_status.values() if r["status"] == "RUNNING"])
    }

@app.post("/datasets/upload", response_model=Dict[str, str])
async def upload_dataset(
    file: UploadFile = File(...),
    name: str = Form(...)
):
    """Upload a dataset file."""
    try:
        # Use original filename (no unique identifier)
        file_path = os.path.join(UPLOAD_DIR, file.filename)
        
        # Save file
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        
        # Store dataset info (using filename as key instead of UUID)
        datasets[file.filename] = {
            "name": name,
            "filename": file.filename,
            "file_path": file_path,
            "size": os.path.getsize(file_path),
            "uploaded_at": datetime.now().isoformat()
        }
        
        logger.info(f"Dataset uploaded: {name} -> {file.filename}")
        
        return {
            "filename": file.filename,
            "name": name,
            "file_path": file_path,
            "message": "Dataset uploaded successfully"
        }
        
    except Exception as e:
        logger.error(f"Upload failed: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")

@app.get("/datasets")
async def list_datasets():
    """List all uploaded datasets."""
    return {
        "datasets": list(datasets.values()),
        "count": len(datasets)
    }

@app.post("/workflows/start", response_model=WorkflowResponse)
async def start_enhanced_workflow(
    workflow_request: WorkflowRequest,
    background_tasks: BackgroundTasks
):
    """Start a new workflow with enhanced result capture."""
    try:
        # Generate run ID
        run_id = str(uuid.uuid4())
        
        # Store workflow
        workflows[run_id] = {
            "run_id": run_id,
            "request": workflow_request.dict(),
            "created_at": datetime.now().isoformat()
        }
        
        # Start enhanced workflow in background
        background_tasks.add_task(run_workflow_with_results, run_id, workflow_request)
        
        logger.info(f"Enhanced workflow started: {run_id} - {workflow_request.run_name}")
        
        return WorkflowResponse(
            run_id=run_id,
            status="STARTED",
            message=f"Enhanced workflow '{workflow_request.run_name}' started successfully"
        )
        
    except Exception as e:
        logger.error(f"Failed to start enhanced workflow: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to start workflow: {str(e)}")

@app.get("/runs/{run_id}/status")
async def get_enhanced_run_status(run_id: str):
    """Get enhanced status of a workflow run with step details."""
    if run_id not in run_status:
        raise HTTPException(status_code=404, detail="Run not found")
    
    status_data = run_status[run_id].copy()
    
    # Add step results if available
    if run_id in step_results:
        status_data["steps"] = [step.dict() for step in step_results[run_id]]
    else:
        status_data["steps"] = []
    
    return status_data

@app.get("/runs/{run_id}/steps")
async def get_workflow_steps(run_id: str):
    """Get detailed step results for a workflow run."""
    if run_id not in step_results:
        raise HTTPException(status_code=404, detail="No step results found for this run")
    
    return {
        "run_id": run_id,
        "steps": [step.dict() for step in step_results[run_id]],
        "total_steps": len(step_results[run_id]),
        "completed_steps": len([s for s in step_results[run_id] if s.status == "completed"]),
        "failed_steps": len([s for s in step_results[run_id] if s.status == "failed"])
    }

@app.get("/runs/{run_id}/steps/{step_number}")
async def get_step_detail(run_id: str, step_number: int):
    """Get detailed results for a specific step."""
    if run_id not in step_results:
        raise HTTPException(status_code=404, detail="No step results found for this run")
    
    # Find the specific step
    step = None
    for s in step_results[run_id]:
        if s.step_number == step_number:
            step = s
            break
    
    if not step:
        raise HTTPException(status_code=404, detail=f"Step {step_number} not found")
    
    return step.dict()

@app.get("/runs")
async def list_enhanced_runs():
    """List all workflow runs with enhanced information."""
    enhanced_runs = []
    
    for run_data in run_status.values():
        run_info = run_data.copy()
        run_id = run_info["run_id"]
        
        # Add step summary
        if run_id in step_results:
            steps = step_results[run_id]
            run_info["step_summary"] = {
                "total": len(steps),
                "completed": len([s for s in steps if s.status == "completed"]),
                "failed": len([s for s in steps if s.status == "failed"]),
                "running": len([s for s in steps if s.status == "running"])
            }
        else:
            run_info["step_summary"] = {"total": 0, "completed": 0, "failed": 0, "running": 0}
        
        # Add artifact count
        if run_id in artifacts:
            run_info["artifact_count"] = len(artifacts[run_id])
        else:
            run_info["artifact_count"] = 0
            
        enhanced_runs.append(run_info)
    
    return {
        "runs": enhanced_runs,
        "count": len(enhanced_runs)
    }

@app.get("/runs/{run_id}/artifacts")
async def get_run_artifacts(run_id: str):
    """Get artifacts generated by a workflow run."""
    if run_id not in artifacts:
        return {"artifacts": [], "count": 0}
    
    return {
        "artifacts": artifacts[run_id],
        "count": len(artifacts[run_id])
    }

@app.get("/artifacts/{run_id}/{filename}")
async def download_artifact(run_id: str, filename: str):
    """Download a specific artifact file."""
    # Try multiple locations for the artifact
    possible_paths = [
        Path("shared_artifacts") / filename,  # Shared location (preferred)
        Path(filename),                       # Current directory
        Path("artifacts") / filename,         # Artifacts folder
    ]
    
    file_path = None
    for path in possible_paths:
        if path.exists():
            file_path = path
            break
    
    if not file_path:
        logger.error(f"Artifact file not found: {filename}")
        logger.info(f"Searched paths: {[str(p) for p in possible_paths]}")
        raise HTTPException(status_code=404, detail="Artifact file not found")
    
    logger.info(f"Serving artifact from: {file_path}")
    
    return FileResponse(
        path=file_path,
        filename=filename,
        media_type="application/octet-stream"
    )

@app.delete("/runs/{run_id}")
async def delete_enhanced_run(run_id: str):
    """Delete a workflow run and its artifacts and step results."""
    deleted_items = []
    
    if run_id in workflows:
        del workflows[run_id]
        deleted_items.append("workflow")
        
    if run_id in run_status:
        del run_status[run_id]
        deleted_items.append("status")
        
    if run_id in artifacts:
        del artifacts[run_id]
        deleted_items.append("artifacts")
        
    if run_id in step_results:
        del step_results[run_id]
        deleted_items.append("step_results")
    
    return {
        "message": f"Run {run_id} deleted successfully",
        "deleted_items": deleted_items
    }

@app.get("/analytics")
async def get_workflow_analytics():
    """Get analytics about workflow performance."""
    total_runs = len(run_status)
    completed_runs = len([r for r in run_status.values() if r["status"] == "COMPLETED"])
    failed_runs = len([r for r in run_status.values() if r["status"] == "FAILED"])
    running_runs = len([r for r in run_status.values() if r["status"] == "RUNNING"])
    
    # Calculate average step durations
    all_steps = []
    for run_id, steps in step_results.items():
        all_steps.extend(steps)
    
    step_analytics = {}
    for step in all_steps:
        key = f"{step.agent}:{step.action}"
        if key not in step_analytics:
            step_analytics[key] = {"count": 0, "total_duration": 0, "failures": 0}
        
        step_analytics[key]["count"] += 1
        if step.duration_seconds:
            step_analytics[key]["total_duration"] += step.duration_seconds
        if step.status == "failed":
            step_analytics[key]["failures"] += 1
    
    # Calculate averages
    for key, data in step_analytics.items():
        if data["count"] > 0:
            data["avg_duration"] = data["total_duration"] / data["count"]
            data["failure_rate"] = data["failures"] / data["count"]
        else:
            data["avg_duration"] = 0
            data["failure_rate"] = 0
    
    return {
        "run_summary": {
            "total": total_runs,
            "completed": completed_runs,
            "failed": failed_runs,
            "running": running_runs,
            "success_rate": completed_runs / total_runs if total_runs > 0 else 0
        },
        "step_analytics": step_analytics,
        "total_steps_executed": len(all_steps),
        "total_artifacts": sum(len(arts) for arts in artifacts.values())
    }

# ─── STARTUP AND SHUTDOWN ────────────────────────────────────────────────────

@app.on_event("startup")
async def startup_event():
    """Initialize the enhanced orchestrator on startup."""
    logger.info("Enhanced Master Orchestrator starting up...")
    
    # Test agent connectivity
    try:
        response = requests.get(f"{EDA_AGENT_URL}/health", timeout=5)
        if response.status_code == 200:
            logger.info("EDA Agent is accessible")
        else:
            logger.warning("EDA Agent health check failed")
    except Exception as e:
        logger.warning(f"EDA Agent not accessible: {e}")
    
    try:
        response = requests.get(f"{GRAPHING_AGENT_URL}/health", timeout=5)
        if response.status_code == 200:
            logger.info("Graphing Agent is accessible")
        else:
            logger.warning("Graphing Agent health check failed")
    except Exception as e:
        logger.warning(f"Graphing Agent not accessible: {e}")

@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown."""
    logger.info("Enhanced Master Orchestrator shutting down...")

# ─── MAIN ────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    uvicorn.run(
        "master_orchestrator_api:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )