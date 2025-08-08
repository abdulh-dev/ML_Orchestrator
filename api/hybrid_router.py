#Actively in Use
"""
Hybrid API Router for Async Translation Workflow

Implements the new endpoints from the clean-room design:
- /workflows/translate - Async NL→DSL translation with token response
- /translation/{token} - Polling endpoint for translation status  
- /workflows/dsl - Direct DSL execution
- /workflows/suggest - Generate workflow suggestions
- Enhanced edge-case handling and validation
"""
#Actively in Use

import asyncio
import logging
import yaml
from typing import Dict, Any, Optional, List
from datetime import datetime

from fastapi import APIRouter, HTTPException, BackgroundTasks, status, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, validator

from ..orchestrator_tools.translation_queue import TranslationQueue, TranslationWorker, TranslationStatus
from ..orchestrator_tools.translator import LLMTranslator, NeedsHumanError
from ..orchestrator_tools.workflow_manager import WorkflowManager
from ..orchestrator_tools.decision_engine import DecisionEngine
from ..orchestrator_tools.security import SecurityUtils
from ..orchestrator_tools.guards import TokenRateLimiter
from ..orchestrator_tools.agent_registry import validate_workflow_tasks
from ..orchestrator_tools.telemetry import trace_async, get_correlation_id, set_correlation_id, CorrelationID

logger = logging.getLogger(__name__)

# Request/Response Models
class TranslationRequest(BaseModel):
    """Request model for natural language translation."""
    natural_language: str = Field(..., min_length=10, max_length=5000, description="Natural language workflow description")
    client_id: Optional[str] = Field(default="default", description="Client identifier for rate limiting")
    metadata: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Additional metadata")
    priority: Optional[int] = Field(default=5, ge=1, le=10, description="Translation priority (1=low, 10=high)")
    
    @validator('natural_language')
    def validate_nl_content(cls, v):
        """Validate natural language content."""
        if not v or v.isspace():
            raise ValueError("Natural language content cannot be empty")
        
        # Basic content validation
        if len(v.split()) < 3:
            raise ValueError("Natural language content too brief, provide more details")
        
        return v.strip()

class TranslationResponse(BaseModel):
    """Response model for translation requests."""
    token: str = Field(..., description="Translation token for polling")
    status: str = Field(..., description="Initial status (queued)")
    estimated_completion_seconds: Optional[int] = Field(description="Estimated completion time")
    message: str = Field(..., description="Human-readable status message")

class TranslationStatusResponse(BaseModel):
    """Response model for translation status."""
    token: str = Field(..., description="Translation token")
    status: str = Field(..., description="Current translation status")
    dsl: Optional[str] = Field(description="Generated DSL (when status=done)")
    error_message: Optional[str] = Field(description="Error message (when status=error)")
    error_details: Optional[Dict[str, Any]] = Field(description="Detailed error information")
    created_at: str = Field(..., description="Creation timestamp")
    updated_at: str = Field(..., description="Last update timestamp")
    retries: int = Field(default=0, description="Number of retry attempts")
    metadata: Optional[Dict[str, Any]] = Field(description="Request metadata")

class DSLWorkflowRequest(BaseModel):
    """Request model for direct DSL execution."""
    dsl_yaml: str = Field(..., min_length=20, description="Workflow DSL in YAML format")
    client_id: Optional[str] = Field(default="default", description="Client identifier")
    metadata: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Additional metadata")
    validate_only: bool = Field(default=False, description="Only validate DSL without execution")
    
    @validator('dsl_yaml')
    def validate_dsl_yaml(cls, v):
        """Validate DSL YAML format."""
        try:
            parsed = yaml.safe_load(v)
            if not isinstance(parsed, dict):
                raise ValueError("DSL must be a valid YAML object")
            if "tasks" not in parsed:
                raise ValueError("DSL must contain 'tasks' field")
            if not isinstance(parsed["tasks"], list):
                raise ValueError("'tasks' must be a list")
            if len(parsed["tasks"]) == 0:
                raise ValueError("DSL must contain at least one task")
        except yaml.YAMLError as e:
            raise ValueError(f"Invalid YAML format: {e}")
        
        return v

class SuggestionRequest(BaseModel):
    """Request model for workflow suggestions."""
    context: str = Field(..., min_length=5, max_length=1000, description="Context for suggestions")
    domain: Optional[str] = Field(default="data-science", description="Problem domain")
    complexity: Optional[str] = Field(default="medium", pattern="^(simple|medium|complex)$", description="Desired complexity")

class WorkflowResponse(BaseModel):
    """Response model for workflow operations."""
    workflow_id: str = Field(..., description="Unique workflow identifier")
    status: str = Field(..., description="Workflow status")
    message: str = Field(..., description="Human-readable message")
    validation_results: Optional[Dict[str, Any]] = Field(description="Validation results")

class ValidationResponse(BaseModel):
    """Response model for DSL validation."""
    valid: bool = Field(..., description="Whether DSL is valid")
    errors: Optional[List[str]] = Field(description="Validation errors")
    warnings: Optional[List[str]] = Field(description="Validation warnings")
    parsed_workflow: Optional[Dict[str, Any]] = Field(description="Parsed workflow structure")

def create_hybrid_router(
    translation_queue: TranslationQueue,
    llm_translator: LLMTranslator,
    workflow_manager: WorkflowManager,
    decision_engine: DecisionEngine,
    security_utils: SecurityUtils,
    rate_limiter: TokenRateLimiter
) -> APIRouter:
    """
    Create hybrid API router with all dependencies injected.
    
    Args:
        translation_queue: Translation queue instance
        llm_translator: LLM translator instance  
        workflow_manager: Workflow manager instance
        decision_engine: Decision engine instance
        security_utils: Security utilities
        rate_limiter: Rate limiter instance
        
    Returns:
        Configured FastAPI router
    """
    router = APIRouter(prefix="/api/v1", tags=["workflows"])
    
    # Dependency injection
    async def get_client_id_from_request(request) -> str:
        """Extract client ID from request."""
        return getattr(request, 'client_id', 'default')
    
    # Translation endpoints
    @router.post("/workflows/translate", response_model=TranslationResponse)
    @trace_async("translate_natural_language", operation_type="api_endpoint")
    async def translate_natural_language(
        request: TranslationRequest,
        background_tasks: BackgroundTasks
    ):
        """
        Submit natural language for async translation to DSL.
        
        Flow:
        1. Validate and sanitize input
        2. Check rate limits
        3. Enqueue translation with token
        4. Return 202 with token for polling
        """
        try:
            # Set correlation ID
            correlation_id = CorrelationID.generate()
            set_correlation_id(correlation_id)
            
            # Security validation
            if security_utils:
                if not security_utils.validate_input(request.natural_language):
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="Input contains potentially dangerous content"
                    )
            
            # Rate limiting
            if rate_limiter and not rate_limiter.check(request.client_id):
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="Rate limit exceeded. Please try again later."
                )
            
            # Enqueue translation
            token = await translation_queue.enqueue(
                text=request.natural_language,
                metadata={
                    **request.metadata,
                    "client_id": request.client_id,
                    "priority": request.priority,
                    "correlation_id": str(correlation_id)
                }
            )
            
            # Estimate completion time based on queue size and complexity
            estimated_seconds = _estimate_completion_time(
                text_length=len(request.natural_language),
                priority=request.priority,
                queue_stats=translation_queue.get_stats()
            )
            
            logger.info(f"Translation queued: token={token}, client={request.client_id}")
            
            return TranslationResponse(
                token=token,
                status=TranslationStatus.QUEUED.value,
                estimated_completion_seconds=estimated_seconds,
                message="Translation queued successfully. Use the token to poll for results."
            )
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Translation request failed: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to queue translation request"
            )
    
    @router.get("/translation/{token}", response_model=TranslationStatusResponse)
    @trace_async("get_translation_status", operation_type="api_endpoint")
    async def get_translation_status(token: str):
        """
        Poll translation status by token.
        
        Returns current status and results when complete.
        Handles all edge cases: timeout, needs_human, error, etc.
        """
        try:
            # Validate token format
            if not token or len(token) != 32:  # UUID4 hex length
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid token format"
                )
            
            # Get status from queue
            status_data = await translation_queue.get_status(token)
            if not status_data:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Translation token not found or expired"
                )
            
            # Parse metadata safely
            metadata = status_data.get("metadata", {})
            if isinstance(metadata, str):
                try:
                    import json
                    metadata = json.loads(metadata)
                except (json.JSONDecodeError, TypeError):
                    metadata = {}
            
            response = TranslationStatusResponse(
                token=token,
                status=status_data.get("status", "unknown"),
                dsl=status_data.get("dsl"),
                error_message=status_data.get("error_message"),
                error_details=status_data.get("error_details"),
                created_at=status_data.get("created_at", ""),
                updated_at=status_data.get("updated_at", ""),
                retries=int(status_data.get("retries", 0)),
                metadata=metadata
            )
            
            # Log successful retrieval
            logger.debug(f"Translation status retrieved: token={token}, status={response.status}")
            
            return response
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Failed to get translation status for token {token}: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to retrieve translation status"
            )
    
    @router.post("/workflows/dsl", response_model=WorkflowResponse)
    @trace_async("execute_dsl_workflow", operation_type="api_endpoint")
    async def execute_dsl_workflow(request: DSLWorkflowRequest):
        """
        Execute workflow from DSL YAML directly.
        
        Supports validation-only mode and full execution.
        Includes comprehensive DSL validation with repair loops.
        """
        try:
            # Set correlation ID
            correlation_id = CorrelationID.generate()
            set_correlation_id(correlation_id)
            
            # Parse and validate DSL with repair pipeline
            try:
                # Try direct parsing first
                workflow_def = yaml.safe_load(request.dsl_yaml)
                validation_result = await _validate_workflow_dsl(workflow_def, request.dsl_yaml)
                
                # If validation fails, try repair pipeline
                if not validation_result["valid"] and workflow_manager and workflow_manager.db:
                    try:
                        from ..orchestrator_tools.dsl_repair_pipeline import repair as repair_dsl
                        repaired_workflow = await repair_dsl(request.dsl_yaml, workflow_manager.db)
                        workflow_def = repaired_workflow
                        validation_result = await _validate_workflow_dsl(workflow_def, request.dsl_yaml)
                        validation_result["repaired"] = True
                        validation_result["repair_message"] = "DSL was automatically repaired"
                    except Exception as repair_error:
                        logger.warning(f"DSL repair failed: {repair_error}")
                        # Continue with original validation result
                        
            except yaml.YAMLError as e:
                # Try repair pipeline for malformed YAML
                if workflow_manager and workflow_manager.db:
                    try:
                        from ..orchestrator_tools.dsl_repair_pipeline import repair as repair_dsl
                        repaired_workflow = await repair_dsl(request.dsl_yaml, workflow_manager.db)
                        workflow_def = repaired_workflow
                        validation_result = await _validate_workflow_dsl(workflow_def, request.dsl_yaml)
                        validation_result["repaired"] = True
                        validation_result["repair_message"] = "Malformed YAML was automatically repaired"
                    except Exception as repair_error:
                        raise HTTPException(
                            status_code=status.HTTP_400_BAD_REQUEST,
                            detail=f"Invalid YAML format and repair failed: {e}"
                        )
                else:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"Invalid YAML format: {e}"
                    )
            
            if not validation_result["valid"]:
                if request.validate_only:
                    return JSONResponse(
                        status_code=status.HTTP_200_OK,
                        content={
                            "valid": False,
                            "errors": validation_result["errors"],
                            "warnings": validation_result.get("warnings", [])
                        }
                    )
                else:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail={
                            "message": "DSL validation failed",
                            "errors": validation_result["errors"],
                            "warnings": validation_result.get("warnings", [])
                        }
                    )
            
            # Validation-only mode
            if request.validate_only:
                return JSONResponse(
                    status_code=status.HTTP_200_OK,
                    content={
                        "valid": True,
                        "warnings": validation_result.get("warnings", []),
                        "parsed_workflow": validation_result.get("parsed_workflow")
                    }
                )
            
            # Security validation
            if security_utils:
                if not security_utils.validate_input(request.dsl_yaml):
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="DSL contains potentially dangerous content"
                    )
            
            # Rate limiting
            if rate_limiter and not rate_limiter.check(request.client_id):
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="Rate limit exceeded. Please try again later."
                )
            
            # Apply decision engine policies
            if decision_engine:
                processed_tasks = []
                for task in workflow_def.get("tasks", []):
                    decision = decision_engine.evaluate("dsl_direct", task)
                    if decision.allowed:
                        task.update(decision.overrides)
                        processed_tasks.append(task)
                    else:
                        logger.warning(f"Task {task.get('id', 'unknown')} blocked by policy: {decision.reason}")
                
                workflow_def["tasks"] = processed_tasks
            
            # Initialize workflow
            if workflow_manager:
                workflow_id = await workflow_manager.init_workflow(
                    workflow_def,
                    metadata={
                        **request.metadata,
                        "client_id": request.client_id,
                        "source": "dsl_direct",
                        "correlation_id": str(correlation_id),
                        "validated": True
                    }
                )
                
                # Start workflow execution
                success = await workflow_manager.start_workflow(workflow_id)
                
                if success:
                    return WorkflowResponse(
                        workflow_id=workflow_id,
                        status="running",
                        message="DSL workflow started successfully",
                        validation_results=validation_result
                    )
                else:
                    raise HTTPException(
                        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                        detail="Failed to start workflow execution"
                    )
            else:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Workflow manager not available"
                )
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"DSL workflow execution failed: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to execute DSL workflow"
            )
    
    @router.post("/workflows/suggest")
    @trace_async("generate_workflow_suggestions", operation_type="api_endpoint")
    async def generate_workflow_suggestions(request: SuggestionRequest):
        """
        Generate workflow suggestions based on context.
        
        Uses LLM to generate multiple workflow options.
        """
        try:
            # Security validation
            if security_utils:
                if not security_utils.validate_input(request.context):
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="Context contains potentially dangerous content"
                    )
            
            # Generate suggestions using LLM
            if llm_translator:
                suggestions = await llm_translator.generate_suggestions(
                    context=request.context,
                    domain=request.domain,
                    complexity=request.complexity
                )
                
                return {
                    "suggestions": suggestions,
                    "context": request.context,
                    "domain": request.domain,
                    "complexity": request.complexity,
                    "generated_at": datetime.utcnow().isoformat()
                }
            else:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="LLM translator not available"
                )
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Suggestion generation failed: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to generate workflow suggestions"
            )
    
    # Helper functions
    def _estimate_completion_time(text_length: int, priority: int, queue_stats: Dict[str, Any]) -> int:
        """Estimate translation completion time."""
        base_time = min(30 + (text_length // 100) * 5, 180)  # 30s base, +5s per 100 chars, max 3min
        
        # Adjust for priority (higher priority = faster)
        priority_factor = 0.5 + (priority / 20)  # 0.55 to 1.0
        
        # Adjust for queue size
        queue_size = queue_stats.get("queue_size", 0)
        if isinstance(queue_size, int):
            queue_factor = 1.0 + (queue_size * 0.1)  # +10% per item in queue
        else:
            queue_factor = 1.2  # Unknown queue size, assume some delay
        
        estimated = int(base_time * priority_factor * queue_factor)
        return max(10, min(estimated, 600))  # Between 10s and 10min
    
    async def _validate_workflow_dsl(workflow_def: Dict[str, Any], raw_yaml: str) -> Dict[str, Any]:
        """Comprehensive DSL validation with repair attempts."""
        errors = []
        warnings = []
        
        try:
            # Basic structure validation
            if not isinstance(workflow_def, dict):
                errors.append("Workflow must be a YAML object")
                return {"valid": False, "errors": errors}
            
            if "tasks" not in workflow_def:
                errors.append("Workflow must contain 'tasks' field")
                return {"valid": False, "errors": errors}
            
            tasks = workflow_def["tasks"]
            if not isinstance(tasks, list):
                errors.append("'tasks' must be a list")
                return {"valid": False, "errors": errors}
            
            if len(tasks) == 0:
                errors.append("Workflow must contain at least one task")
                return {"valid": False, "errors": errors}
            
            # Task validation
            task_ids = set()
            for i, task in enumerate(tasks):
                if not isinstance(task, dict):
                    errors.append(f"Task {i} must be an object")
                    continue
                
                # Required fields
                if "id" not in task:
                    errors.append(f"Task {i} missing required 'id' field")
                elif task["id"] in task_ids:
                    errors.append(f"Duplicate task ID: {task['id']}")
                else:
                    task_ids.add(task["id"])
                
                if "agent" not in task:
                    errors.append(f"Task {task.get('id', i)} missing required 'agent' field")
                
                if "action" not in task:
                    errors.append(f"Task {task.get('id', i)} missing required 'action' field")
                
                # Dependency validation
                if "depends_on" in task:
                    deps = task["depends_on"]
                    if not isinstance(deps, list):
                        warnings.append(f"Task {task.get('id', i)} 'depends_on' should be a list")
                    else:
                        for dep in deps:
                            if dep not in task_ids and dep not in [t.get("id") for t in tasks]:
                                errors.append(f"Task {task.get('id', i)} depends on unknown task: {dep}")
            
            # Circular dependency check (simplified)
            if not errors:
                try:
                    _check_circular_dependencies(tasks)
                except ValueError as e:
                    errors.append(str(e))
            
            return {
                "valid": len(errors) == 0,
                "errors": errors,
                "warnings": warnings,
                "parsed_workflow": workflow_def if len(errors) == 0 else None
            }
            
        except Exception as e:
            return {
                "valid": False,
                "errors": [f"Validation error: {e}"],
                "warnings": warnings
            }
    
    def _check_circular_dependencies(tasks: List[Dict[str, Any]]):
        """Check for circular dependencies in task graph."""
        # Build adjacency list
        graph = {}
        for task in tasks:
            task_id = task.get("id")
            deps = task.get("depends_on", [])
            graph[task_id] = deps
        
        # DFS cycle detection
        visited = set()
        rec_stack = set()
        
        def dfs(node):
            if node in rec_stack:
                raise ValueError(f"Circular dependency detected involving task: {node}")
            if node in visited:
                return
            
            visited.add(node)
            rec_stack.add(node)
            
            for neighbor in graph.get(node, []):
                dfs(neighbor)
            
            rec_stack.remove(node)
        
        for task_id in graph:
            if task_id not in visited:
                dfs(task_id)
    
    return router 