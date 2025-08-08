#Actively in Use
"""
Decision Engine for the Master Orchestrator.

Centralizes policy decisions such as whether to run tasks, which models to use,
resource allocation (GPU vs CPU), and other business logic decisions.
"""

import logging
from typing import Dict, List, Optional, Any
from enum import Enum
from datetime import datetime
import re

logger = logging.getLogger(__name__)

class ResourceType(Enum):
    """Available resource types."""
    CPU = "cpu"
    GPU = "gpu"
    MEMORY_OPTIMIZED = "memory_optimized"
    COMPUTE_OPTIMIZED = "compute_optimized"

class DecisionResult:
    """Result of a decision evaluation."""
    
    def __init__(self, allowed: bool, reason: str = "", overrides: Optional[Dict[str, Any]] = None):
        self.allowed = allowed
        self.reason = reason
        self.overrides = overrides or {}
        self.timestamp = datetime.utcnow()

class DecisionEngine:
    """Engine for making policy decisions about workflow execution."""
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize decision engine.
        
        Args:
            config: Configuration dictionary for decision rules
        """
        self.config = config
        
        # Resource allocation rules
        self.gpu_agents = set(config.get("gpu_agents", ["ml_agent", "deep_learning_agent"]))
        self.cpu_agents = set(config.get("cpu_agents", ["eda_agent", "data_agent"]))
        
        # Model selection rules
        self.model_rules = config.get("model_rules", {})
        
        # Business rules
        self.max_task_count = config.get("max_task_count", 100)
        self.blocked_actions = set(config.get("blocked_actions", []))
        self.priority_agents = set(config.get("priority_agents", []))
        
        # Time-based rules
        self.maintenance_windows = config.get("maintenance_windows", [])
        
        # Resource limits
        self.resource_limits = config.get("resource_limits", {
            "max_concurrent_gpu_tasks": 2,
            "max_concurrent_cpu_tasks": 10,
            "max_memory_per_task_gb": 16
        })
        
        logger.info("Decision engine initialized with configuration")

    def evaluate(self, run_id: str, task_meta: Dict[str, Any]) -> DecisionResult:
        """
        Evaluate whether a task should be executed and with what parameters.
        
        Args:
            run_id: Workflow run ID
            task_meta: Task metadata including agent, action, params
            
        Returns:
            DecisionResult with allowed flag, reason, and any overrides
        """
        try:
            # Check basic business rules first
            basic_check = self._check_basic_rules(task_meta)
            if not basic_check.allowed:
                return basic_check
            
            # Check resource availability
            resource_check = self._check_resource_allocation(task_meta)
            if not resource_check.allowed:
                return resource_check
            
            # Check time-based rules
            time_check = self._check_time_based_rules(task_meta)
            if not time_check.allowed:
                return time_check
            
            # Determine resource allocation and model selection
            overrides = {}
            
            # Resource allocation decision
            resource_type = self._determine_resource_type(task_meta)
            overrides["resource_type"] = resource_type.value
            
            # Model selection decision
            model_selection = self._determine_model(task_meta)
            if model_selection:
                overrides.update(model_selection)
            
            # Priority adjustment
            priority = self._determine_priority(task_meta)
            overrides["priority"] = priority
            
            # Memory allocation
            memory_gb = self._determine_memory_allocation(task_meta, resource_type)
            overrides["memory_gb"] = memory_gb
            
            logger.debug(f"Task approved for run {run_id} with overrides: {overrides}")
            
            return DecisionResult(
                allowed=True,
                reason="Task approved by decision engine",
                overrides=overrides
            )
            
        except Exception as e:
            logger.error(f"Error in decision evaluation: {e}")
            return DecisionResult(
                allowed=False,
                reason=f"Decision engine error: {str(e)}"
            )

    def _check_basic_rules(self, task_meta: Dict[str, Any]) -> DecisionResult:
        """Check basic business rules."""
        action = task_meta.get("action", "")
        agent = task_meta.get("agent", "")
        
        # Check blocked actions
        if action in self.blocked_actions:
            return DecisionResult(
                allowed=False,
                reason=f"Action '{action}' is blocked by policy"
            )
        
        # Check task count limits (would need workflow context)
        # This is a placeholder - in practice you'd query the current workflow
        
        # Check agent validity
        known_agents = self.gpu_agents | self.cpu_agents
        if agent and agent not in known_agents:
            logger.warning(f"Unknown agent '{agent}', allowing with CPU resources")
        
        return DecisionResult(allowed=True, reason="Basic rules passed")

    def _check_resource_allocation(self, task_meta: Dict[str, Any]) -> DecisionResult:
        """Check if resources are available for the task."""
        agent = task_meta.get("agent", "")
        
        # Determine required resource type
        if agent in self.gpu_agents:
            # Check GPU availability (placeholder - would integrate with actual resource manager)
            # For now, we'll assume resources are available
            pass
        elif agent in self.cpu_agents:
            # Check CPU availability
            pass
        
        # In a real implementation, this would check:
        # - Current resource usage
        # - Queue lengths
        # - Available capacity
        
        return DecisionResult(allowed=True, reason="Resources available")

    def _check_time_based_rules(self, task_meta: Dict[str, Any]) -> DecisionResult:
        """Check time-based rules like maintenance windows."""
        current_time = datetime.utcnow()
        
        # Check maintenance windows
        for window in self.maintenance_windows:
            start_hour = window.get("start_hour", 0)
            end_hour = window.get("end_hour", 0)
            
            if start_hour <= current_time.hour < end_hour:
                return DecisionResult(
                    allowed=False,
                    reason=f"Task blocked during maintenance window ({start_hour}-{end_hour})"
                )
        
        return DecisionResult(allowed=True, reason="Time-based rules passed")

    def _determine_resource_type(self, task_meta: Dict[str, Any]) -> ResourceType:
        """Determine the appropriate resource type for the task."""
        agent = task_meta.get("agent", "")
        action = task_meta.get("action", "")
        
        # GPU-intensive agents
        if agent in self.gpu_agents:
            return ResourceType.GPU
        
        # Memory-intensive actions
        memory_intensive_actions = ["load_large_dataset", "feature_engineering", "data_transformation"]
        if action in memory_intensive_actions:
            return ResourceType.MEMORY_OPTIMIZED
        
        # Compute-intensive actions
        compute_intensive_actions = ["train_model", "hyperparameter_tuning", "cross_validation"]
        if action in compute_intensive_actions:
            return ResourceType.COMPUTE_OPTIMIZED
        
        # Default to CPU
        return ResourceType.CPU

    def _determine_model(self, task_meta: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Determine model selection based on task requirements."""
        action = task_meta.get("action", "")
        agent = task_meta.get("agent", "")
        params = task_meta.get("params", {})
        
        model_overrides = {}
        
        # LLM model selection for natural language tasks
        if action in ["generate_report", "explain_analysis", "summarize_data"]:
            # Use faster model for simple tasks
            model_overrides["llm_model"] = "claude-3-haiku-20240307"
        elif action in ["complex_analysis", "research_synthesis"]:
            # Use more capable model for complex tasks
            model_overrides["llm_model"] = "claude-3-sonnet-20240229"
        
        # ML model selection
        if agent == "ml_agent":
            dataset_size = params.get("dataset_size", 0)
            if dataset_size > 100000:
                model_overrides["use_distributed"] = True
            
            # Algorithm selection based on problem type
            problem_type = params.get("problem_type")
            if problem_type == "classification" and dataset_size < 10000:
                model_overrides["algorithm"] = "random_forest"
            elif problem_type == "regression" and dataset_size > 50000:
                model_overrides["algorithm"] = "gradient_boosting"
        
        return model_overrides if model_overrides else None

    def _determine_priority(self, task_meta: Dict[str, Any]) -> int:
        """Determine task priority (1-10, higher is more important)."""
        agent = task_meta.get("agent", "")
        action = task_meta.get("action", "")
        
        # Priority agents get higher priority
        if agent in self.priority_agents:
            return 8
        
        # Critical actions get high priority
        critical_actions = ["emergency_analysis", "real_time_prediction"]
        if action in critical_actions:
            return 9
        
        # Data loading and preparation are foundational
        if action in ["load_data", "clean_data", "validate_data"]:
            return 7
        
        # Analysis and modeling are medium priority
        if action in ["analyze_data", "train_model", "evaluate_model"]:
            return 5
        
        # Visualization and reporting are lower priority
        if action in ["create_visualization", "generate_report"]:
            return 3
        
        # Default priority
        return 5

    def _determine_memory_allocation(self, task_meta: Dict[str, Any], resource_type: ResourceType) -> int:
        """Determine memory allocation in GB."""
        action = task_meta.get("action", "")
        params = task_meta.get("params", {})
        
        # Base allocation by resource type
        base_memory = {
            ResourceType.CPU: 2,
            ResourceType.GPU: 8,
            ResourceType.MEMORY_OPTIMIZED: 16,
            ResourceType.COMPUTE_OPTIMIZED: 4
        }.get(resource_type, 2)
        
        # Adjust based on action
        if action in ["load_large_dataset", "feature_engineering"]:
            base_memory *= 2
        elif action in ["train_deep_model", "hyperparameter_tuning"]:
            base_memory *= 3
        
        # Adjust based on dataset size
        dataset_size = params.get("dataset_size", 0)
        if dataset_size > 1000000:
            base_memory *= 2
        elif dataset_size > 100000:
            base_memory *= 1.5
        
        # Cap at maximum
        max_memory = self.resource_limits.get("max_memory_per_task_gb", 16)
        return min(int(base_memory), max_memory)

    def evaluate_workflow_priority(self, run_id: str, workflow_meta: Dict[str, Any]) -> int:
        """
        Evaluate the priority of an entire workflow.
        
        Args:
            run_id: Workflow run ID
            workflow_meta: Workflow metadata
            
        Returns:
            Priority score (1-10)
        """
        tasks = workflow_meta.get("tasks", [])
        
        # Calculate priority based on constituent tasks
        if not tasks:
            return 5
        
        max_priority = 0
        for task in tasks:
            task_priority = self._determine_priority(task)
            max_priority = max(max_priority, task_priority)
        
        # Adjust for workflow characteristics
        task_count = len(tasks)
        if task_count > 20:
            max_priority += 1  # Complex workflows get slight boost
        
        # Check for time-sensitive workflows
        metadata = workflow_meta.get("metadata", {})
        if metadata.get("urgent", False):
            max_priority += 2
        
        return min(max_priority, 10)

    def should_auto_retry(self, task_meta: Dict[str, Any], failure_reason: str) -> bool:
        """
        Decide if a failed task should be automatically retried.
        
        Args:
            task_meta: Task metadata
            failure_reason: Reason for failure
            
        Returns:
            True if task should be retried
        """
        action = task_meta.get("action", "")
        
        # Don't retry destructive actions
        destructive_actions = ["delete_data", "drop_table", "reset_model"]
        if action in destructive_actions:
            return False
        
        # Check failure reason
        transient_failures = [
            "network_timeout", "resource_unavailable", "temporary_service_error"
        ]
        
        for transient in transient_failures:
            if transient in failure_reason.lower():
                return True
        
        # Don't retry for data validation errors
        if "validation_error" in failure_reason.lower():
            return False
        
        # Default to retry for most failures
        return True

    def get_statistics(self) -> Dict[str, Any]:
        """Get decision engine statistics."""
        return {
            "config_loaded": bool(self.config),
            "gpu_agents": list(self.gpu_agents),
            "cpu_agents": list(self.cpu_agents),
            "resource_limits": self.resource_limits,
            "blocked_actions": list(self.blocked_actions),
            "maintenance_windows": self.maintenance_windows
        } 