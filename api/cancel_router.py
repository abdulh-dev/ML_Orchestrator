#Actively in Use

"""
Cancellation API Router

Provides REST endpoints for graceful workflow cancellation and status checking.
Supports both user-initiated and system-initiated cancellations with proper
error handling and status tracking.

Endpoints:
- PUT /runs/{run_id}/cancel - Cancel a running workflow
- GET /runs/{run_id}/cancel - Check cancellation status
- GET /runs/cancelled - List all cancelled workflows
"""

import logging
from datetime import datetime
from typing import Optional, List, Dict, Any

from fastapi import APIRouter, HTTPException, status, Query
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

# Request/Response Models
class CancelRequest(BaseModel):
    """Request model for workflow cancellation."""
    reason: str = Field(default="user-requested", max_length=500, description="Reason for cancellation")
    force: bool = Field(default=False, description="Force cancellation even if tasks are running")

class CancelResponse(BaseModel):
    """Response model for cancellation requests."""
    run_id: str = Field(..., description="Workflow run ID")
    status: str = Field(..., description="Current workflow status")
    message: str = Field(..., description="Human-readable response message")
    cancelled_at: Optional[datetime] = Field(description="Timestamp when cancellation was initiated")
    cancelled_tasks: int = Field(default=0, description="Number of tasks cancelled")
    reason: Optional[str] = Field(description="Cancellation reason")

class CancelStatusResponse(BaseModel):
    """Response model for cancellation status."""
    run_id: str = Field(..., description="Workflow run ID")
    is_cancelled: bool = Field(..., description="Whether workflow is cancelled")
    status: str = Field(..., description="Current workflow status")
    cancellation_reason: Optional[str] = Field(description="Reason for cancellation")
    cancelled_at: Optional[datetime] = Field(description="Cancellation timestamp")
    cancelled_by: Optional[str] = Field(description="Who or what initiated cancellation")

class CancelledWorkflowInfo(BaseModel):
    """Information about a cancelled workflow."""
    run_id: str
    workflow_name: Optional[str]
    status: str
    cancelled_at: datetime
    cancellation_reason: str
    cancelled_by: Optional[str]
    task_count: int
    client_id: Optional[str]

def create_cancel_router() -> APIRouter:
    """Create and configure the cancellation API router."""
    router = APIRouter(prefix="/runs", tags=["cancellation"])

    @router.put("/{run_id}/cancel", 
                response_model=CancelResponse,
                status_code=status.HTTP_202_ACCEPTED)
    async def cancel_workflow(
        run_id: str,
        request: CancelRequest = CancelRequest()
    ):
        """
        Cancel a running workflow.
        
        Gracefully cancels a workflow by:
        1. Updating workflow status to CANCELLING
        2. Marking pending/queued tasks as CANCELLED
        3. Signaling running tasks to abort
        4. Recording cancellation metadata
        
        Args:
            run_id: Workflow run ID to cancel
            request: Cancellation request with reason and options
            
        Returns:
            Cancellation response with status and metadata
            
        Raises:
            404: Workflow not found or already finished
            409: Workflow cannot be cancelled in current state
            500: Internal error during cancellation
        """
        try:
            # Import here to avoid circular imports
            from ..orchestrator_tools.workflow_manager import cancel_workflow_internal, get_workflow_status
            
            # Check if workflow exists and can be cancelled
            workflow_info = await get_workflow_status(run_id)
            if not workflow_info:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Workflow {run_id} not found"
                )
            
            current_status = workflow_info.get("status")
            if current_status in ["COMPLETED", "FAILED", "CANCELLED"]:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"Cannot cancel workflow in {current_status} state"
                )
            
            # Perform cancellation
            success = await cancel_workflow_internal(
                run_id=run_id,
                reason=request.reason,
                force=request.force,
                cancelled_by="user"
            )
            
            if not success:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Failed to cancel workflow"
                )
            
            # Get updated status
            updated_info = await get_workflow_status(run_id)
            cancelled_tasks = updated_info.get("cancelled_task_count", 0)
            
            logger.info(f"Workflow {run_id} cancellation initiated by user: {request.reason}")
            
            return CancelResponse(
                run_id=run_id,
                status="CANCELLING",
                message="Workflow cancellation initiated successfully",
                cancelled_at=datetime.utcnow(),
                cancelled_tasks=cancelled_tasks,
                reason=request.reason
            )
            
        except HTTPException:
            raise
        except ImportError:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Workflow cancellation service unavailable"
            )
        except Exception as exc:
            logger.error(f"Failed to cancel workflow {run_id}: {exc}", exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Internal error during workflow cancellation"
            )

    @router.get("/{run_id}/cancel",
                response_model=CancelStatusResponse)
    async def get_cancellation_status(run_id: str):
        """
        Get cancellation status for a workflow.
        
        Args:
            run_id: Workflow run ID to check
            
        Returns:
            Cancellation status information
            
        Raises:
            404: Workflow not found
        """
        try:
            from ..orchestrator_tools.workflow_manager import get_workflow_status
            
            workflow_info = await get_workflow_status(run_id)
            if not workflow_info:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Workflow {run_id} not found"
                )
            
            current_status = workflow_info.get("status")
            is_cancelled = current_status in ["CANCELLED", "CANCELLING"]
            
            return CancelStatusResponse(
                run_id=run_id,
                is_cancelled=is_cancelled,
                status=current_status,
                cancellation_reason=workflow_info.get("cancellation_reason"),
                cancelled_at=workflow_info.get("cancelled_at"),
                cancelled_by=workflow_info.get("cancelled_by")
            )
            
        except HTTPException:
            raise
        except Exception as exc:
            logger.error(f"Failed to get cancellation status for {run_id}: {exc}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to retrieve cancellation status"
            )

    @router.get("/cancelled",
                response_model=List[CancelledWorkflowInfo])
    async def list_cancelled_workflows(
        limit: int = Query(50, ge=1, le=1000, description="Maximum number of results"),
        offset: int = Query(0, ge=0, description="Number of results to skip"),
        client_id: Optional[str] = Query(None, description="Filter by client ID")
    ):
        """
        List cancelled workflows with pagination.
        
        Args:
            limit: Maximum number of results to return
            offset: Number of results to skip for pagination
            client_id: Optional filter by client ID
            
        Returns:
            List of cancelled workflow information
        """
        try:
            from ..orchestrator_tools.workflow_manager import list_cancelled_workflows
            
            workflows = await list_cancelled_workflows(
                limit=limit,
                offset=offset,
                client_id=client_id
            )
            
            return [
                CancelledWorkflowInfo(
                    run_id=w["run_id"],
                    workflow_name=w.get("workflow_name"),
                    status=w["status"],
                    cancelled_at=w["cancelled_at"],
                    cancellation_reason=w["cancellation_reason"],
                    cancelled_by=w.get("cancelled_by"),
                    task_count=w.get("task_count", 0),
                    client_id=w.get("client_id")
                ) for w in workflows
            ]
            
        except Exception as exc:
            logger.error(f"Failed to list cancelled workflows: {exc}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to retrieve cancelled workflows"
            )

    @router.delete("/{run_id}/cancel",
                   status_code=status.HTTP_204_NO_CONTENT)
    async def force_complete_cancellation(run_id: str):
        """
        Force complete cancellation of a workflow.
        
        This endpoint should be used with caution as it immediately
        marks a workflow as CANCELLED regardless of running tasks.
        
        Args:
            run_id: Workflow run ID to force cancel
            
        Raises:
            404: Workflow not found
            409: Workflow not in cancelling state
        """
        try:
            from ..orchestrator_tools.workflow_manager import force_complete_cancellation
            
            success = await force_complete_cancellation(run_id)
            if not success:
                # Check if workflow exists
                from ..orchestrator_tools.workflow_manager import get_workflow_status
                workflow_info = await get_workflow_status(run_id)
                
                if not workflow_info:
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail=f"Workflow {run_id} not found"
                    )
                
                current_status = workflow_info.get("status")
                if current_status != "CANCELLING":
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail=f"Workflow must be in CANCELLING state, currently {current_status}"
                    )
                
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Failed to force complete cancellation"
                )
            
            logger.warning(f"Force completed cancellation for workflow {run_id}")
            
        except HTTPException:
            raise
        except Exception as exc:
            logger.error(f"Failed to force complete cancellation for {run_id}: {exc}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Internal error during force cancellation"
            )

    return router 