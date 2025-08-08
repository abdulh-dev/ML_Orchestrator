#Actively in Use
"""
Agent Registry

Provides runtime access to agent capabilities and validation functions.
Exposes the agent-action matrix from configuration for UI and validation.
"""

import logging
from typing import Dict, List, Set, Optional
from config import get_config

logger = logging.getLogger(__name__)

# Global agent matrix cache
_agent_matrix: Optional[Dict[str, List[str]]] = None
_agent_names: Optional[Set[str]] = None

def get_agent_matrix() -> Dict[str, List[str]]:
    """
    Get the current agent-action matrix.
    
    Returns:
        Dictionary mapping agent names to their allowed actions
    """
    global _agent_matrix
    if _agent_matrix is None:
        config = get_config()
        _agent_matrix = {
            "eda": config.master_orchestrator.agent_actions.eda,
            "fe": config.master_orchestrator.agent_actions.fe,
            "model": config.master_orchestrator.agent_actions.model,
            "custom": config.master_orchestrator.agent_actions.custom
        }
        logger.info(f"Agent matrix loaded: {list(_agent_matrix.keys())}")
    
    return _agent_matrix

def get_agent_names() -> Set[str]:
    """
    Get the set of valid agent names.
    
    Returns:
        Set of valid agent names
    """
    global _agent_names
    if _agent_names is None:
        _agent_names = set(get_agent_matrix().keys())
    
    return _agent_names

def get_agent_actions(agent: str) -> List[str]:
    """
    Get the list of valid actions for a given agent.
    
    Args:
        agent: Agent name
        
    Returns:
        List of valid actions for the agent
    """
    matrix = get_agent_matrix()
    return matrix.get(agent, [])

def is_valid_agent(agent: str) -> bool:
    """
    Check if an agent name is valid.
    
    Args:
        agent: Agent name to validate
        
    Returns:
        True if agent is valid, False otherwise
    """
    return agent in get_agent_names()

def is_valid_action(agent: str, action: str) -> bool:
    """
    Check if an action is valid for a given agent.
    
    Args:
        agent: Agent name
        action: Action name to validate
        
    Returns:
        True if action is valid for the agent, False otherwise
    """
    if not is_valid_agent(agent):
        return False
    
    return action in get_agent_actions(agent)

def is_valid(agent: str, action: str) -> bool:
    """
    Check if an agent-action combination is valid.
    
    Args:
        agent: Agent name
        action: Action name
        
    Returns:
        True if the combination is valid, False otherwise
    """
    return is_valid_action(agent, action)

def get_agent_stats() -> Dict[str, Dict[str, any]]:
    """
    Get statistics about agents for dashboard/API.
    
    Returns:
        Dictionary with agent statistics
    """
    matrix = get_agent_matrix()
    stats = {}
    
    for agent, actions in matrix.items():
        stats[agent] = {
            "actions": actions,
            "action_count": len(actions),
            "status": "active"  # Could be extended with health checks
        }
    
    return stats

def refresh_agent_matrix():
    """
    Refresh the agent matrix from configuration.
    Useful for hot-reloading configuration changes.
    """
    global _agent_matrix, _agent_names
    _agent_matrix = None
    _agent_names = None
    logger.info("Agent matrix refreshed from configuration")

def validate_workflow_tasks(tasks: List[Dict[str, any]]) -> List[str]:
    """
    Validate all tasks in a workflow against the agent matrix.
    
    Args:
        tasks: List of task dictionaries
        
    Returns:
        List of validation error messages (empty if valid)
    """
    errors = []
    
    for i, task in enumerate(tasks):
        agent = task.get("agent")
        action = task.get("action")
        
        if not agent:
            errors.append(f"Task {i}: Missing 'agent' field")
            continue
            
        if not action:
            errors.append(f"Task {i}: Missing 'action' field")
            continue
        
        if not is_valid_agent(agent):
            errors.append(f"Task {i}: Invalid agent '{agent}'. Valid agents: {list(get_agent_names())}")
            continue
            
        if not is_valid_action(agent, action):
            valid_actions = get_agent_actions(agent)
            errors.append(f"Task {i}: Invalid action '{action}' for agent '{agent}'. Valid actions: {valid_actions}")
    
    return errors 