#Actively in Use
"""
Configuration management for EDA Server.
Loads and validates settings from config.yaml.
"""

import yaml
from pathlib import Path
from typing import Dict, Any, List, Optional, Literal
from pydantic import BaseModel, Field

class RetryConfig(BaseModel):
    max_retries: int = Field(3, ge=0)
    backoff_base_s: int = Field(30, gt=0)
    backoff_max_s: int = Field(300, gt=0)

class SchedulingConfig(BaseModel):
    sla_task_complete_s: int = Field(600, gt=0)  # 10 minutes
    sla_workflow_complete_s: int = Field(3600, gt=0)  # 1 hour

class WorkloadEstimateConfig(BaseModel):
    tasks_per_hour: int = Field(30, gt=0)
    avg_task_duration_s: int = Field(240, gt=0)  # 4 minutes

class DeadlockConfig(BaseModel):
    check_interval_s: int = Field(60, gt=0)        # how often the loop scans MongoDB
    pending_stale_s: int = Field(900, gt=0)        # task idle threshold (15 min)
    workflow_stale_s: int = Field(3600, gt=0)      # workflow idle threshold (1 hour)
    cancel_on_deadlock: bool = Field(True)         # auto-cancel or just alert
    alert_webhook: str = Field("")                 # optional Slack / PagerDuty URL
    max_dependency_depth: int = Field(50, gt=0)    # prevent infinite dependency chains

class OrchestratorConfig(BaseModel):
    max_concurrent_workflows: int = Field(1, gt=0)
    retry: RetryConfig = Field(default_factory=lambda: RetryConfig())
    scheduling: SchedulingConfig = Field(default_factory=lambda: SchedulingConfig())
    workload_estimate: WorkloadEstimateConfig = Field(default_factory=lambda: WorkloadEstimateConfig())
    deadlock: DeadlockConfig = Field(default_factory=lambda: DeadlockConfig())

class MissingDataConfig(BaseModel):
    column_drop_threshold: float = Field(0.50, ge=0.0, le=1.0)
    row_drop_threshold: float = Field(0.50, ge=0.0, le=1.0)
    systematic_correlation_threshold: float = Field(0.70, ge=0.0, le=1.0)
    imputation: Dict[str, float] = Field(default_factory=dict)

class OutlierDetectionConfig(BaseModel):
    iqr_factor: float = Field(1.5, gt=0.0)
    contamination_default: float = Field(0.05, ge=0.0, le=1.0)
    mahalanobis_confidence: float = Field(0.975, ge=0.0, le=1.0)
    max_columns_visualized: int = Field(10, gt=0)
    sample_size_limit: int = Field(10000, gt=0)

class SchemaInferenceConfig(BaseModel):
    id_uniqueness_threshold: float = Field(0.90, ge=0.0, le=1.0)
    datetime_success_rate: float = Field(0.80, ge=0.0, le=1.0)
    precision_sample_size: int = Field(100, gt=0)
    max_sample_values: int = Field(5, gt=0)

class FeatureTransformationConfig(BaseModel):
    rare_category_threshold: float = Field(0.005, ge=0.0, le=1.0)
    vif_severe_threshold: float = Field(10.0, gt=0.0)
    vif_moderate_threshold: float = Field(5.0, gt=0.0)
    boxcox_epsilon: float = Field(1e-6, gt=0.0)
    skew_improvement_threshold: float = Field(0.5, gt=0.0)
    binning_n_bins: int = Field(5, gt=1)
    supervised_binning_min_samples: int = Field(10, gt=0)

class VisualizationConfig(BaseModel):
    correlation_sample_size: int = Field(10000, gt=0)
    max_points_scatter: int = Field(5000, gt=0)
    figure_dpi: int = Field(150, gt=0)
    correlation_label_threshold: float = Field(0.5, ge=0.0, le=1.0)

class PerformanceConfig(BaseModel):
    memory_warning_threshold: int = Field(1000, gt=0)  # MB
    max_rows_processed: int = Field(100000, gt=0)
    chunk_size: int = Field(10000, gt=0)

class CheckpointsConfig(BaseModel):
    require_approval: bool = True
    approval_timeout: int = Field(300, gt=0)  # seconds
    auto_approve_small_changes: bool = True

class LLMConfig(BaseModel):
    model_version: str = Field("claude-3-sonnet-20240229")
    max_input_length: int = Field(10000, gt=0)
    llm_max_tokens: int = Field(4000, gt=0)
    llm_max_retries: int = Field(3, ge=0)
    temperature: float = Field(0.0, ge=0.0, le=2.0)
    rail_schema_path: str = Field("orchestrator/rail_schema.xml")
    system_prompt: str = Field(default="")

class RulesConfig(BaseModel):
    rule_mappings: Dict[str, Dict[str, Any]] = Field(default_factory=dict)

class InfrastructureConfig(BaseModel):
    mongo_url: str = Field("mongodb://localhost:27017")
    db_name: str = Field("deepline")
    kafka_bootstrap_servers: str = Field("localhost:9092")
    task_requests_topic: str = Field("task.requests")
    task_events_topic: str = Field("task.events")

class RateLimitsConfig(BaseModel):
    requests_per_minute: int = Field(60, gt=0)
    requests_per_hour: int = Field(1000, gt=0)
    burst_requests: int = Field(10, gt=0)

class SLAConfig(BaseModel):
    check_interval_seconds: int = Field(30, gt=0)
    task_timeout_seconds: int = Field(600, gt=0)
    workflow_timeout_seconds: int = Field(3600, gt=0)

class CacheConfig(BaseModel):
    redis_url: str = Field("redis://localhost:6379")
    namespace: str = Field("master_orchestrator")
    default_ttl: int = Field(3600, gt=0)

class DecisionConfig(BaseModel):
    gpu_agents: List[str] = Field(default_factory=lambda: ["ml_agent", "deep_learning_agent"])
    cpu_agents: List[str] = Field(default_factory=lambda: ["eda_agent", "data_agent"])
    max_task_count: int = Field(100, ge=1)
    blocked_actions: List[str] = Field(default_factory=list)
    priority_agents: List[str] = Field(default_factory=list)
    maintenance_windows: List[Dict[str, Any]] = Field(default_factory=list)
    resource_limits: Dict[str, Any] = Field(default_factory=lambda: {
        "max_concurrent_gpu_tasks": 2,
        "max_concurrent_cpu_tasks": 10,
        "max_memory_per_task_gb": 16
    })
    model_rules: Dict[str, Any] = Field(default_factory=dict)

class TelemetryConfig(BaseModel):
    enabled: bool = Field(True)
    service_name: str = Field("master-orchestrator")
    service_version: str = Field("1.0.0")
    otlp_endpoint: Optional[str] = Field(None)

class WorkflowEngineRetryConfig(BaseModel):
    max_retries: int = Field(3, ge=0)
    backoff_base_s: int = Field(15, gt=0)
    backoff_max_s: int = Field(300, gt=0)
    poll_interval_s: float = Field(1.0, gt=0)

class WorkflowEngineDeadlockConfig(BaseModel):
    check_interval_s: int = Field(60, gt=0)
    pending_stale_s: int = Field(900, gt=0)  # 15 minutes
    workflow_stale_s: int = Field(3600, gt=0)  # 1 hour
    max_dependency_depth: int = Field(50, gt=0)

class WorkflowEngineConfig(BaseModel):
    alpha: float = Field(1.0, gt=0)  # Runtime weight
    beta: float = Field(2.0, gt=0)   # User priority weight
    gamma: float = Field(3.0, gt=0)  # Deadline urgency weight
    redis_url: str = Field("redis://localhost:6379")
    max_workers_per_agent: Dict[str, int] = Field(default_factory=lambda: {
        "eda_agent": 3,
        "ml_agent": 2,
        "analysis_agent": 4,
        "feature_agent": 2
    })
    agent_urls: Dict[str, str] = Field(default_factory=lambda: {
        "eda_agent": "http://localhost:8001",
        "ml_agent": "http://localhost:8002", 
        "analysis_agent": "http://localhost:8003",
        "feature_agent": "http://localhost:8004"
    })
    enabled_agents: List[str] = Field(default_factory=lambda: ["eda_agent", "ml_agent", "analysis_agent", "feature_agent"])
    task_timeout_s: int = Field(600, gt=0)  # 10 minutes
    poll_interval_s: float = Field(0.2, gt=0)
    retry: WorkflowEngineRetryConfig = Field(default_factory=lambda: WorkflowEngineRetryConfig())
    deadlock: WorkflowEngineDeadlockConfig = Field(default_factory=lambda: WorkflowEngineDeadlockConfig())

class LlmConfig(BaseModel):
    endpoint: str = Field("http://localhost:11434/api/generate")
    fallback_provider: str = Field("openai")
    model_name: str = Field("llama2-13b")
    temperature: float = Field(0.0, ge=0.0, le=2.0)
    max_tokens: int = Field(800, gt=0, le=4000)

class DslRepairConfig(BaseModel):
    enable_auto_repair: bool = Field(True)
    max_repair_attempts: int = Field(3, gt=0, le=10)
    timeout_seconds: int = Field(30, gt=0, le=300)
    strict_json_output: bool = Field(True)
    log_repair_attempts: bool = Field(True)

class AgentActionsConfig(BaseModel):
    eda: List[str] = Field(default_factory=lambda: ["analyze", "clean", "transform", "explore", "preprocess"])
    fe: List[str] = Field(default_factory=lambda: ["create_visualization", "build_dashboard", "generate_report", "create_chart", "export_data"])
    model: List[str] = Field(default_factory=lambda: ["train", "predict", "evaluate", "tune", "deploy"])
    custom: List[str] = Field(default_factory=lambda: ["execute", "process", "run_script", "call_api"])

class AgentRoutingConfig(BaseModel):
    mode: Literal["header", "topic"] = Field("header")
    default_topic: str = Field("task.requests")
    topic_prefix: str = Field("task.requests.")

class MasterOrchestratorConfig(BaseModel):
    infrastructure: InfrastructureConfig = Field(default_factory=lambda: InfrastructureConfig())
    orchestrator: OrchestratorConfig = Field(default_factory=lambda: OrchestratorConfig())
    llm: LlmConfig = Field(default_factory=lambda: LlmConfig())
    dsl_repair: DslRepairConfig = Field(default_factory=lambda: DslRepairConfig())
    agent_actions: AgentActionsConfig = Field(default_factory=lambda: AgentActionsConfig())
    agent_routing: AgentRoutingConfig = Field(default_factory=lambda: AgentRoutingConfig())

class EDAConfig(BaseModel):
    missing_data: MissingDataConfig
    outlier_detection: OutlierDetectionConfig
    schema_inference: SchemaInferenceConfig
    feature_transformation: FeatureTransformationConfig
    visualization: VisualizationConfig
    performance: PerformanceConfig
    checkpoints: CheckpointsConfig
    orchestrator: OrchestratorConfig
    master_orchestrator: MasterOrchestratorConfig = Field(default_factory=lambda: MasterOrchestratorConfig())
    workflow_engine: WorkflowEngineConfig = Field(default_factory=lambda: WorkflowEngineConfig())

def load_config(config_path: str = "config.yaml") -> EDAConfig:
    """
    Load configuration from YAML file with validation.
    
    Args:
        config_path: Path to configuration file
        
    Returns:
        Validated configuration object
        
    Raises:
        FileNotFoundError: If config file doesn't exist
        yaml.YAMLError: If config file is invalid YAML
        ValidationError: If config values are invalid
    """
    config_file = Path(config_path)
    if not config_file.exists():
        raise FileNotFoundError(f"Configuration file not found: {config_path}")
    
    with open(config_file, 'r') as f:
        config_data = yaml.safe_load(f)
    
    return EDAConfig(**config_data)

def get_config() -> EDAConfig:
    """
    Get the global configuration instance.
    Creates default config if none exists.
    """
    try:
        return load_config()
    except (FileNotFoundError, yaml.YAMLError, Exception):
        # Return default configuration if file is missing or invalid
        print("Warning: Using default configuration. Create config.yaml for customization.")
        return EDAConfig(
            missing_data=MissingDataConfig(),
            outlier_detection=OutlierDetectionConfig(),
            schema_inference=SchemaInferenceConfig(),
            feature_transformation=FeatureTransformationConfig(),
            visualization=VisualizationConfig(),
            performance=PerformanceConfig(),
            checkpoints=CheckpointsConfig(),
            orchestrator=OrchestratorConfig(
                retry=RetryConfig(),
                scheduling=SchedulingConfig(),
                workload_estimate=WorkloadEstimateConfig()
            ),
            master_orchestrator=MasterOrchestratorConfig(
                llm=LlmConfig(),
                rules=RulesConfig(),
                infrastructure=InfrastructureConfig(),
                rate_limits=RateLimitsConfig(),
                sla=SLAConfig(),
                cache=CacheConfig()
            )
        )

# Global configuration instance
config = get_config() 