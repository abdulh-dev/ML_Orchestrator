#Actively in Use
"""
DSL Repair Pipeline

Provides automatic repair and validation of workflow DSL using Guardrails-AI
and LLM-based repair capabilities.
"""

import json
import time
import yaml
import hashlib
import logging
import asyncio
from typing import Dict, Any, Optional, List
from pathlib import Path

try:
    from guardrails import Guard
    from guardrails.validators import ValidatorError
    GUARDRAILS_AVAILABLE = True
except ImportError:
    GUARDRAILS_AVAILABLE = False

from motor.motor_asyncio import AsyncIOMotorDatabase
from pydantic import ValidationError

from llm_client import call_llm
from config import get_config
from translator import NeedsHumanError
from agent_registry import is_valid, validate_workflow_tasks

logger = logging.getLogger(__name__)

# Schema path relative to mcp-server directory
_schema_path = Path(__file__).parent.parent / "schemas" / "dsl_schema.json"

# Common key renames
RENAME_MAP = {
    "param": "params",
    "dependson": "depends_on",
    "dependencies": "depends_on",
    "task_id": "id",
    "workflow_name": "name",
    "workflow_description": "description"
}

# Initialize Guard if available
guard = None
if GUARDRAILS_AVAILABLE and _schema_path.exists():
    try:
        guard = Guard.from_pydantic(
            output_class=None,  # We'll handle validation manually
            json_schema=str(_schema_path)
        )
        logger.info("Guardrails guard initialized successfully")
    except Exception as e:
        logger.warning(f"Failed to initialize Guardrails guard: {e}")
        guard = None

def _validate_agent_action(agent: str, action: str, config) -> bool:
    """Validate that the action is valid for the given agent."""
    return is_valid(agent, action)

def _detect_circular_dependencies(tasks: List[Dict[str, Any]]) -> List[str]:
    """Detect circular dependencies in tasks."""
    task_names = {task.get("name", f"task_{i}"): i for i, task in enumerate(tasks)}
    visited = set()
    rec_stack = set()
    cycles = []
    
    def dfs(task_idx: int, path: List[str]):
        task = tasks[task_idx]
        task_name = task.get("name", f"task_{task_idx}")
        
        if task_idx in rec_stack:
            cycle_start = path.index(task_name)
            cycles.append(path[cycle_start:] + [task_name])
            return
            
        if task_idx in visited:
            return
            
        visited.add(task_idx)
        rec_stack.add(task_idx)
        path.append(task_name)
        
        for dep in task.get("depends_on", []):
            if dep in task_names:
                dfs(task_names[dep], path.copy())
        
        rec_stack.remove(task_idx)
        path.pop()
    
    for i in range(len(tasks)):
        if i not in visited:
            dfs(i, [])
    
    return cycles

def _quick_fixes(yaml_str: str) -> str:
    """Apply quick fixes to YAML string."""
    try:
        doc = yaml.safe_load(yaml_str) or {}
    except yaml.YAMLError:
        # Try to fix basic YAML syntax issues
        yaml_str = yaml_str.replace("\t", "  ")  # Replace tabs with spaces
        doc = yaml.safe_load(yaml_str) or {}
    
    # Ensure workflow section exists
    if "workflow" not in doc:
        doc["workflow"] = {"name": "unnamed_workflow"}
    
    # Fix task-level issues
    for task in doc.get("tasks", []):
        # Rename common misspellings
        for bad_key, good_key in RENAME_MAP.items():
            if bad_key in task:
                task[good_key] = task.pop(bad_key)
        
        # Fill defaults
        task.setdefault("params", {})
        task.setdefault("depends_on", [])
        
        # Ensure required fields have defaults
        if not task.get("name"):
            task["name"] = f"task_{hash(str(task)) % 10000}"
    
    # Fill workflow defaults
    workflow = doc["workflow"]
    workflow.setdefault("priority", 5)
    workflow.setdefault("sla_minutes", 60)
    
    return yaml.safe_dump(doc, default_flow_style=False, sort_keys=False)

async def _llm_repair_step(original: str, error: Exception, config) -> str:
    """Use LLM to repair the YAML."""
    prompt = f"""You are a YAML repair bot. Fix the user's workflow YAML so it passes validation.

### Original YAML:
```yaml
{original}
```

### Validation Error:
{error}

### Requirements:
1. Fix any syntax errors, indentation issues, or missing fields
2. Ensure all required fields are present: workflow.name, tasks[].name, tasks[].agent, tasks[].action
3. Use valid agents: eda, fe, model, custom
4. Fix any circular dependencies
5. Return ONLY valid YAML in the same DSL format

### Valid Agent-Action combinations:
- eda: analyze, clean, transform, explore, preprocess
- fe: create_visualization, build_dashboard, generate_report, create_chart, export_data
- model: train, predict, evaluate, tune, deploy
- custom: execute, process, run_script, call_api

Return the repaired YAML:"""

    try:
        response = await call_llm(
            prompt,
            temperature=0.0,
            max_tokens=config.master_orchestrator.llm.max_tokens
        )
        
        # Extract YAML from response (handle markdown code blocks)
        if "```yaml" in response:
            start = response.find("```yaml") + 7
            end = response.find("```", start)
            if end != -1:
                response = response[start:end].strip()
        elif "```" in response:
            start = response.find("```") + 3
            end = response.find("```", start)
            if end != -1:
                response = response[start:end].strip()
        
        return response
    except Exception as e:
        logger.error(f"LLM repair failed: {e}")
        raise

async def repair_dsl(original_yaml: str, db: AsyncIOMotorDatabase) -> Dict[str, Any]:
    """
    Attempt to repair and validate DSL YAML.
    
    Args:
        original_yaml: The original YAML string
        db: MongoDB database connection for logging
        
    Returns:
        Validated workflow dictionary
        
    Raises:
        NeedsHumanError: If repair fails after max attempts
    """
    config = get_config()
    doc_id = hashlib.sha256(original_yaml.encode()).hexdigest()[:16]
    attempts = 0
    last_error = None
    repaired_yaml = original_yaml
    
    logger.info(f"Starting DSL repair for document {doc_id}")
    
    while attempts < config.master_orchestrator.dsl_repair.max_repair_attempts:
        try:
            # 1. Apply quick fixes
            repaired_yaml = _quick_fixes(repaired_yaml)
            
            # 2. Parse YAML
            parsed = yaml.safe_load(repaired_yaml)
            if not parsed:
                raise ValueError("Empty or invalid YAML")
            
            # 3. Validate with Guardrails if available
            if guard:
                try:
                    _, validated_obj, _ = guard(repaired_yaml)
                    parsed = validated_obj
                except Exception as guard_error:
                    logger.warning(f"Guardrails validation failed: {guard_error}")
                    # Continue with manual validation
            
            # 4. Manual validation
            if "workflow" not in parsed:
                raise ValueError("Missing 'workflow' section")
            
            if "tasks" not in parsed or not parsed["tasks"]:
                raise ValueError("Missing or empty 'tasks' section")
            
            # 5. Validate agent-action combinations using agent registry
            agent_errors = validate_workflow_tasks(parsed["tasks"])
            if agent_errors:
                raise ValueError(f"Agent validation failed: {'; '.join(agent_errors)}")
            
            # 6. Check for circular dependencies
            cycles = _detect_circular_dependencies(parsed["tasks"])
            if cycles:
                raise ValueError(f"Circular dependencies detected: {cycles}")
            
            # Success! Log and return
            if config.master_orchestrator.dsl_repair.log_repair_attempts:
                await db.dsl_repair_logs.insert_one({
                    "doc_id": doc_id,
                    "original_yaml": original_yaml,
                    "repaired_yaml": repaired_yaml,
                    "repair_attempts": attempts,
                    "final_status": "success",
                    "error_details": None,
                    "created_at": time.time()
                })
            
            logger.info(f"DSL repair successful for {doc_id} after {attempts} attempts")
            return parsed
            
        except Exception as e:
            last_error = e
            attempts += 1
            logger.warning(f"DSL repair attempt {attempts} failed: {e}")
            
            # Try LLM repair if enabled and not the last attempt
            if (config.master_orchestrator.dsl_repair.enable_auto_repair and 
                attempts < config.master_orchestrator.dsl_repair.max_repair_attempts):
                try:
                    repaired_yaml = await _llm_repair_step(original_yaml, e, config)
                except Exception as llm_error:
                    logger.error(f"LLM repair step failed: {llm_error}")
                    # Continue with next attempt
    
    # All attempts failed - log and raise
    if config.master_orchestrator.dsl_repair.log_repair_attempts:
        await db.dsl_repair_logs.insert_one({
            "doc_id": doc_id,
            "original_yaml": original_yaml,
            "repaired_yaml": repaired_yaml,
            "repair_attempts": attempts,
            "final_status": "failed",
            "error_details": str(last_error),
            "created_at": time.time()
        })
    
    # Send alert if webhook configured
    webhook_url = config.master_orchestrator.orchestrator.deadlock.alert_webhook
    if webhook_url:
        try:
            import httpx
            alert_payload = {
                "text": f"🔧 DSL Repair Failed: Document {doc_id}",
                "attachments": [{
                    "color": "warning",
                    "fields": [
                        {"title": "Document ID", "value": doc_id, "short": True},
                        {"title": "Attempts", "value": str(attempts), "short": True},
                        {"title": "Error", "value": str(last_error), "short": False}
                    ]
                }]
            }
            async with httpx.AsyncClient(timeout=10.0) as client:
                await client.post(webhook_url, json=alert_payload)
        except Exception as alert_error:
            logger.error(f"Failed to send repair alert: {alert_error}")
    
    raise NeedsHumanError(
        f"DSL repair failed after {attempts} attempts",
        context={
            "error": str(last_error),
            "doc_id": doc_id,
            "attempts": attempts
        }
    )

async def repair(original_yaml: str, db: AsyncIOMotorDatabase) -> Dict[str, Any]:
    """
    Convenience function for DSL repair with timeout.
    
    Args:
        original_yaml: The original YAML string
        db: MongoDB database connection
        
    Returns:
        Validated workflow dictionary
    """
    config = get_config()
    timeout = config.master_orchestrator.dsl_repair.timeout_seconds
    
    return await asyncio.wait_for(
        repair_dsl(original_yaml, db),
        timeout=timeout
    ) 