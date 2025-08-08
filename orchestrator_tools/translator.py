#Actively in Use
"""
Translator module for the Master Orchestrator.

Provides natural language to DSL workflow translation using LLM, rule-based, and hybrid approaches.
"""

import json
import yaml
import hashlib
import logging
import re
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime
from security import SecurityUtils
from cache_client import CacheClient

try:
    import guardrails as gd
    GUARDRAILS_AVAILABLE = True
except ImportError:
    GUARDRAILS_AVAILABLE = False

logger = logging.getLogger(__name__)

class NeedsHumanError(Exception):
    """Exception raised when human intervention is required."""
    
    def __init__(self, context: Dict[str, Any]):
        self.context = context
        super().__init__(f"Human intervention required: {context}")

class LLMTranslator:
    """LLM-based translator with Guardrails validation."""
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize LLM translator.
        
        Args:
            config: Configuration dictionary with LLM settings
        """
        self.config = config
        self.security = SecurityUtils(max_input_length=config.get("max_input_length", 10000))
        self.cache = CacheClient(namespace="llm_translation")
        
        # Guardrails setup
        self.guard = None
        if GUARDRAILS_AVAILABLE and config.get("rail_schema_path"):
            try:
                self.guard = gd.Guard.for_rail(config["rail_schema_path"])
                logger.info("Guardrails initialized successfully")
            except Exception as e:
                logger.warning(f"Failed to initialize Guardrails: {e}")
        
        # System prompt template
        self.system_prompt = config.get("system_prompt", self._default_system_prompt())
        
        # LLM settings
        self.model_version = config.get("model_version", "claude-3-sonnet-20240229")
        self.max_tokens = config.get("llm_max_tokens", 4000)
        self.max_retries = config.get("llm_max_retries", 3)
        self.temperature = config.get("temperature", 0.0)
    
    def _default_system_prompt(self) -> str:
        """Default system prompt for DSL generation."""
        return """You are a workflow orchestrator that converts natural language requests into structured DSL YAML.

Output ONLY valid JSON that follows this schema:
{
  "tasks": [
    {
      "id": "unique_task_id",
      "agent": "eda_agent|data_agent|ml_agent", 
      "action": "load_data|analyze_data|create_model|etc",
      "params": {"key": "value"},
      "depends_on": ["task_id1", "task_id2"]
    }
  ]
}

Rules:
1. Always include "tasks" array
2. Each task needs: id, agent, action
3. Use depends_on for task dependencies
4. Keep task IDs short and descriptive
5. Map user requests to appropriate agents and actions

Available agents:
- eda_agent: data loading, analysis, visualization
- data_agent: data processing, cleaning, transformation  
- ml_agent: model training, evaluation, prediction

Convert the user request to this JSON format."""

    def _build_llm_prompt(self, minimized_text: str) -> str:
        """
        Build complete prompt for LLM.
        
        Args:
            minimized_text: Sanitized and minimized user input
            
        Returns:
            Complete prompt string
        """
        return f"{self.system_prompt}\n\nUser Request: {minimized_text}\n\nJSON Response:"
    
    def _call_claude(self, prompt: str) -> str:
        """
        Call Claude API (placeholder implementation).
        
        Args:
            prompt: Prompt to send to Claude
            
        Returns:
            Raw response from Claude
        """
        # This is a placeholder - in the real implementation, you would:
        # 1. Import the MCP client or use direct API calls
        # 2. Call Claude with the prompt
        # 3. Return the response
        
        # For now, return a sample response for testing
        logger.warning("Using placeholder Claude implementation")
        return '{"tasks": [{"id": "load_task", "agent": "eda_agent", "action": "load_data", "params": {"file": "data.csv"}}]}'
    
    async def translate(self, user_text: str) -> Optional[Dict[str, Any]]:
        """
        Translate natural language to DSL workflow.
        
        Args:
            user_text: Natural language workflow description
            
        Returns:
            Parsed workflow dict or None if translation failed
        """
        try:
            # 1. Sanitize and minimize input
            clean_text = self.security.sanitize_input(user_text)
            minimized_text = self.security.minimize_context(clean_text, max_sentences=2)
            
            if not minimized_text.strip():
                logger.warning("Input text is empty after sanitization")
                return None
            
            # 2. Build prompt
            prompt = self._build_llm_prompt(minimized_text)
            
            # 3. Check cache
            cache_key = self._get_cache_key(prompt)
            cached_result = await self.cache.get(cache_key)
            if cached_result:
                logger.debug("Retrieved workflow from cache")
                return cached_result
            
            # 4. Call LLM with Guardrails validation
            workflow = await self._call_llm_with_validation(prompt)
            
            if workflow:
                # Cache successful result
                await self.cache.set(cache_key, workflow, ttl=3600)
                logger.info("Successfully translated user request to workflow")
                return workflow
            
            return None
            
        except Exception as e:
            logger.error(f"Error in LLM translation: {e}")
            return None
    
    async def _call_llm_with_validation(self, prompt: str) -> Optional[Dict[str, Any]]:
        """
        Call LLM with Guardrails validation and retries.
        
        Args:
            prompt: Complete prompt for LLM
            
        Returns:
            Validated workflow dict or None
        """
        for attempt in range(self.max_retries):
            try:
                logger.debug(f"LLM translation attempt {attempt + 1}/{self.max_retries}")
                
                if self.guard and GUARDRAILS_AVAILABLE:
                    # Use Guardrails validation
                    raw_response, validated_output, _ = self.guard(
                        self._call_claude,
                        prompt=prompt,
                        temperature=self.temperature,
                        max_tokens=self.max_tokens,
                        model=self.model_version
                    )
                    
                    if validated_output:
                        workflow = self._json_to_workflow(validated_output)
                        if workflow and self._validate_workflow_structure(workflow):
                            return workflow
                else:
                    # Direct LLM call without Guardrails
                    raw_response = self._call_claude(prompt)
                    workflow = self._parse_raw_response(raw_response)
                    if workflow and self._validate_workflow_structure(workflow):
                        return workflow
                
            except Exception as e:
                logger.warning(f"LLM call attempt {attempt + 1} failed: {e}")
                if attempt == self.max_retries - 1:
                    logger.error("All LLM translation attempts failed")
        
        return None
    
    def _parse_raw_response(self, raw_response: str) -> Optional[Dict[str, Any]]:
        """
        Parse raw LLM response to extract JSON.
        
        Args:
            raw_response: Raw response from LLM
            
        Returns:
            Parsed workflow dict or None
        """
        try:
            # Try to extract JSON from response
            cleaned_response = raw_response.strip()
            
            # Look for JSON content between common markers
            json_patterns = [
                r'```json\s*(.*?)\s*```',
                r'```\s*(.*?)\s*```',
                r'\{.*\}',
            ]
            
            for pattern in json_patterns:
                match = re.search(pattern, cleaned_response, re.DOTALL)
                if match:
                    json_str = match.group(1) if len(match.groups()) > 0 else match.group(0)
                    try:
                        return json.loads(json_str)
                    except json.JSONDecodeError:
                        continue
            
            # Try parsing the entire response as JSON
            return json.loads(cleaned_response)
            
        except Exception as e:
            logger.warning(f"Failed to parse LLM response: {e}")
            return None
    
    def _json_to_workflow(self, json_obj: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Convert JSON object to workflow format.
        
        Args:
            json_obj: JSON object from LLM
            
        Returns:
            Workflow dict or None
        """
        if not isinstance(json_obj, dict) or "tasks" not in json_obj:
            return None
        
        return json_obj
    
    def _validate_workflow_structure(self, workflow: Dict[str, Any]) -> bool:
        """
        Validate workflow structure and dependencies.
        
        Args:
            workflow: Workflow dict to validate
            
        Returns:
            True if valid, False otherwise
        """
        try:
            if not isinstance(workflow, dict) or "tasks" not in workflow:
                return False
            
            tasks = workflow["tasks"]
            if not isinstance(tasks, list) or len(tasks) == 0:
                return False
            
            task_ids = set()
            
            # Validate each task
            for task in tasks:
                if not isinstance(task, dict):
                    return False
                
                # Required fields
                required_fields = ["id", "agent", "action"]
                for field in required_fields:
                    if field not in task:
                        logger.warning(f"Task missing required field: {field}")
                        return False
                
                task_id = task["id"]
                if task_id in task_ids:
                    logger.warning(f"Duplicate task ID: {task_id}")
                    return False
                
                task_ids.add(task_id)
            
            # Validate dependencies
            for task in tasks:
                depends_on = task.get("depends_on", [])
                if depends_on:
                    for dep_id in depends_on:
                        if dep_id not in task_ids:
                            logger.warning(f"Task {task['id']} depends on unknown task: {dep_id}")
                            return False
            
            # Check for cycles (simple DFS approach)
            if self._has_cycles(tasks):
                logger.warning("Workflow has dependency cycles")
                return False
            
            return True
            
        except Exception as e:
            logger.warning(f"Workflow validation error: {e}")
            return False
    
    def _has_cycles(self, tasks: List[Dict[str, Any]]) -> bool:
        """
        Check for dependency cycles in task list.
        
        Args:
            tasks: List of task definitions
            
        Returns:
            True if cycles exist, False otherwise
        """
        # Build adjacency list
        graph = {}
        for task in tasks:
            task_id = task["id"]
            depends_on = task.get("depends_on", [])
            graph[task_id] = depends_on
        
        # DFS cycle detection
        visited = set()
        rec_stack = set()
        
        def dfs(node):
            if node in rec_stack:
                return True  # Cycle found
            if node in visited:
                return False
            
            visited.add(node)
            rec_stack.add(node)
            
            for neighbor in graph.get(node, []):
                if dfs(neighbor):
                    return True
            
            rec_stack.remove(node)
            return False
        
        for task_id in graph:
            if task_id not in visited:
                if dfs(task_id):
                    return True
        
        return False
    
    def _get_cache_key(self, prompt: str) -> str:
        """Generate cache key for prompt."""
        content = f"{prompt}:{self.model_version}:{self.temperature}"
        return hashlib.sha256(content.encode()).hexdigest()[:32]

    async def translate_strict(self, natural_language: str) -> str:
        """
        Translate natural language to DSL with strict validation.
        
        Args:
            natural_language: Natural language description
            
        Returns:
            Valid DSL YAML string
            
        Raises:
            NeedsHumanError: If translation requires human intervention
            ValueError: If translation fails after retries
        """
        # First attempt with LLM
        try:
            dsl = await self.translate(natural_language)
            
            # Basic validation
            import yaml
            parsed = yaml.safe_load(dsl)
            
            if not isinstance(parsed, dict) or "tasks" not in parsed:
                raise ValueError("LLM output does not match expected DSL structure")
            
            return dsl
            
        except NeedsHumanError:
            # Re-raise needs human errors
            raise
        except Exception as e:
            logger.warning(f"LLM translation failed: {e}")
            raise ValueError(f"Translation failed: {e}")
    
    async def generate_suggestions(self, 
                                 context: str, 
                                 domain: str = "data-science",
                                 complexity: str = "medium") -> List[Dict[str, Any]]:
        """
        Generate workflow suggestions based on context.
        
        Args:
            context: Description of what the user wants to achieve
            domain: Problem domain (data-science, ml, etc.)
            complexity: Desired complexity level
            
        Returns:
            List of workflow suggestions with descriptions and DSL
        """
        try:
            # Construct prompt for suggestion generation
            suggestion_prompt = f"""
            Generate 3 different workflow suggestions for the following request:
            
            Context: {context}
            Domain: {domain}
            Complexity: {complexity}
            
            For each suggestion, provide:
            1. A clear title (max 50 chars)
            2. A brief description (max 200 chars) 
            3. The complete DSL YAML workflow
            4. Estimated execution time
            
            Format as JSON array with objects containing: title, description, dsl, estimated_minutes
            
            Focus on practical, executable workflows with realistic task dependencies.
            """
            
            # Use LLM to generate suggestions
            if hasattr(self, 'llm_client') and self.llm_client:
                response = await self._call_llm(suggestion_prompt)
                
                # Parse response as JSON
                import json
                try:
                    suggestions = json.loads(response)
                    
                    # Validate and clean suggestions
                    validated_suggestions = []
                    for suggestion in suggestions:
                        if self._validate_suggestion(suggestion):
                            validated_suggestions.append(suggestion)
                    
                    return validated_suggestions[:3]  # Limit to 3 suggestions
                    
                except json.JSONDecodeError:
                    logger.error("LLM returned invalid JSON for suggestions")
                    # Fallback to rule-based suggestions
                    return self._generate_fallback_suggestions(context, domain, complexity)
            else:
                # No LLM available, use rule-based fallback
                return self._generate_fallback_suggestions(context, domain, complexity)
                
        except Exception as e:
            logger.error(f"Suggestion generation failed: {e}")
            # Return basic fallback suggestions
            return self._generate_fallback_suggestions(context, domain, complexity)
    
    def _validate_suggestion(self, suggestion: Dict[str, Any]) -> bool:
        """Validate a single suggestion."""
        required_fields = ["title", "description", "dsl", "estimated_minutes"]
        
        for field in required_fields:
            if field not in suggestion:
                return False
        
        # Validate DSL
        try:
            import yaml
            parsed = yaml.safe_load(suggestion["dsl"])
            if not isinstance(parsed, dict) or "tasks" not in parsed:
                return False
        except:
            return False
        
        return True
    
    def _generate_fallback_suggestions(self, 
                                     context: str, 
                                     domain: str, 
                                     complexity: str) -> List[Dict[str, Any]]:
        """Generate rule-based fallback suggestions."""
        suggestions = []
        
        # Basic data science workflows based on context keywords
        if "load" in context.lower() or "data" in context.lower():
            suggestions.append({
                "title": "Basic Data Loading & Analysis",
                "description": "Load dataset and perform basic exploratory data analysis",
                "dsl": """
name: "Basic Data Analysis"
tasks:
  - id: "load_data"
    agent: "eda_agent"
    action: "load_data"
    params:
      file: "data.csv"
  - id: "basic_info"
    agent: "eda_agent"
    action: "basic_info"
    depends_on: ["load_data"]
  - id: "missing_data"
    agent: "eda_agent"
    action: "missing_data_analysis"
    depends_on: ["load_data"]
""",
                "estimated_minutes": 5
            })
        
        if "model" in context.lower() or "train" in context.lower():
            suggestions.append({
                "title": "ML Model Training Pipeline",
                "description": "Complete machine learning model training and evaluation",
                "dsl": """
name: "ML Training Pipeline"
tasks:
  - id: "load_data"
    agent: "eda_agent"
    action: "load_data"
    params:
      file: "training_data.csv"
  - id: "preprocess"
    agent: "feature_agent"
    action: "preprocess_data"
    depends_on: ["load_data"]
  - id: "train_model"
    agent: "ml_agent"
    action: "train_model"
    params:
      algorithm: "random_forest"
    depends_on: ["preprocess"]
  - id: "evaluate"
    agent: "ml_agent"
    action: "evaluate_model"
    depends_on: ["train_model"]
""",
                "estimated_minutes": 15
            })
        
        if "visualization" in context.lower() or "plot" in context.lower():
            suggestions.append({
                "title": "Data Visualization Dashboard",
                "description": "Create comprehensive data visualizations and charts",
                "dsl": """
name: "Visualization Dashboard"
tasks:
  - id: "load_data"
    agent: "eda_agent"
    action: "load_data"
    params:
      file: "data.csv"
  - id: "distributions"
    agent: "eda_agent"
    action: "create_visualization"
    params:
      type: "distribution"
    depends_on: ["load_data"]
  - id: "correlations"
    agent: "eda_agent"
    action: "create_visualization"
    params:
      type: "correlation_heatmap"
    depends_on: ["load_data"]
  - id: "summary_stats"
    agent: "eda_agent"
    action: "statistical_summary"
    depends_on: ["load_data"]
""",
                "estimated_minutes": 8
            })
        
        # If no specific keywords found, provide a generic analysis workflow
        if not suggestions:
            suggestions.append({
                "title": "General Data Analysis",
                "description": "Comprehensive data analysis workflow",
                "dsl": """
name: "General Analysis"
tasks:
  - id: "load_data"
    agent: "eda_agent"
    action: "load_data"
    params:
      file: "data.csv"
  - id: "analyze"
    agent: "analysis_agent"
    action: "analyze_data"
    depends_on: ["load_data"]
""",
                "estimated_minutes": 10
            })
        
        return suggestions[:3]

class RuleBasedTranslator:
    """Rule-based translator for common patterns."""
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize rule-based translator.
        
        Args:
            config: Configuration with rule mappings
        """
        self.config = config
        self.rule_mappings = config.get("rule_mappings", self._default_rule_mappings())
        self.security = SecurityUtils()
    
    def _default_rule_mappings(self) -> Dict[str, Dict[str, Any]]:
        """Default rule mappings for common patterns."""
        return {
            "load data": {
                "id": "load_data_task",
                "agent": "eda_agent", 
                "action": "load_data",
                "params": {"file": "data.csv"}
            },
            "analyze data": {
                "id": "analyze_task",
                "agent": "eda_agent",
                "action": "analyze_data",
                "params": {}
            },
            "create visualization": {
                "id": "viz_task",
                "agent": "eda_agent",
                "action": "create_visualization",
                "params": {"type": "histogram"}
            },
            "train model": {
                "id": "train_task",
                "agent": "ml_agent",
                "action": "train_model",
                "params": {"algorithm": "random_forest"}
            },
            "evaluate model": {
                "id": "eval_task",
                "agent": "ml_agent",
                "action": "evaluate_model",
                "params": {}
            }
        }
    
    def translate(self, user_text: str) -> Optional[Dict[str, Any]]:
        """
        Translate using rule-based patterns.
        
        Args:
            user_text: User input text
            
        Returns:
            Workflow dict or None if no rules match
        """
        try:
            # Sanitize input
            clean_text = self.security.sanitize_input(user_text).lower()
            
            if not clean_text.strip():
                return None
            
            tasks = []
            task_counter = 1
            
            # Match patterns and build tasks
            for phrase, task_template in self.rule_mappings.items():
                if phrase.lower() in clean_text:
                    task = task_template.copy()
                    
                    # Make task ID unique
                    task["id"] = f"{task['id']}_{task_counter}"
                    task_counter += 1
                    
                    # Extract parameters from text if possible
                    task["params"] = self._extract_parameters(clean_text, phrase, task["params"])
                    
                    tasks.append(task)
            
            if not tasks:
                logger.debug("No rule-based patterns matched")
                return None
            
            # Build dependencies (simple sequential for now)
            for i in range(1, len(tasks)):
                tasks[i]["depends_on"] = [tasks[i-1]["id"]]
            
            workflow = {"tasks": tasks}
            logger.info(f"Rule-based translation created {len(tasks)} tasks")
            return workflow
            
        except Exception as e:
            logger.error(f"Error in rule-based translation: {e}")
            return None
    
    def _extract_parameters(self, text: str, phrase: str, default_params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Extract parameters from text based on phrase context.
        
        Args:
            text: Full text to search
            phrase: Matched phrase
            default_params: Default parameters
            
        Returns:
            Updated parameters dict
        """
        params = default_params.copy()
        
        # Look for file names
        file_patterns = [
            r'(\w+\.csv)',
            r'(\w+\.xlsx?)',
            r'(\w+\.json)',
        ]
        
        for pattern in file_patterns:
            match = re.search(pattern, text)
            if match:
                params["file"] = match.group(1)
                break
        
        # Look for visualization types
        if "visualization" in phrase or "plot" in phrase:
            viz_types = ["histogram", "scatter", "line", "bar", "box", "heatmap"]
            for viz_type in viz_types:
                if viz_type in text:
                    params["type"] = viz_type
                    break
        
        # Look for model types
        if "model" in phrase:
            model_types = ["random_forest", "linear_regression", "svm", "neural_network"]
            for model_type in model_types:
                if model_type.replace("_", " ") in text:
                    params["algorithm"] = model_type
                    break
        
        return params

class FallbackRouter:
    """Router that manages fallback between LLM and rule-based translation."""
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize fallback router.
        
        Args:
            config: Configuration for translators
        """
        self.config = config
        self.llm_translator = LLMTranslator(config.get("llm", {}))
        self.rule_translator = RuleBasedTranslator(config.get("rules", {}))
        
        # Fallback settings
        self.enable_human_fallback = config.get("enable_human_fallback", True)
        self.min_confidence_threshold = config.get("min_confidence_threshold", 0.7)
    
    async def resolve(self, user_text: str, llm_output: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Resolve user input to workflow using fallback strategy.
        
        Args:
            user_text: Original user input
            llm_output: Pre-computed LLM output (optional)
            
        Returns:
            Resolved workflow dict
            
        Raises:
            NeedsHumanError: If human intervention is required
        """
        translation_attempts = []
        
        try:
            # Try LLM translation first (if not provided)
            if llm_output is None:
                logger.debug("Attempting LLM translation")
                llm_output = await self.llm_translator.translate(user_text)
                translation_attempts.append({
                    "method": "llm",
                    "success": llm_output is not None,
                    "output": llm_output
                })
            
            if llm_output:
                logger.info("LLM translation successful")
                return llm_output
            
            # Fallback to rule-based translation
            logger.debug("Attempting rule-based translation")
            rule_output = self.rule_translator.translate(user_text)
            translation_attempts.append({
                "method": "rule_based", 
                "success": rule_output is not None,
                "output": rule_output
            })
            
            if rule_output:
                logger.info("Rule-based translation successful")
                return rule_output
            
            # Both methods failed - require human intervention
            if self.enable_human_fallback:
                logger.warning("All translation methods failed, requiring human intervention")
                
                context = {
                    "user_input": user_text,
                    "translation_attempts": translation_attempts,
                    "error_reason": "No translation method produced valid workflow",
                    "suggestions": self._generate_suggestions(user_text),
                    "timestamp": datetime.now().isoformat()
                }
                
                raise NeedsHumanError(context)
            else:
                logger.error("Translation failed and human fallback disabled")
                raise ValueError("Unable to translate user input to workflow")
                
        except NeedsHumanError:
            raise
        except Exception as e:
            logger.error(f"Error in fallback resolution: {e}")
            
            if self.enable_human_fallback:
                context = {
                    "user_input": user_text,
                    "translation_attempts": translation_attempts,
                    "error_reason": str(e),
                    "suggestions": [],
                    "timestamp": datetime.now().isoformat()
                }
                raise NeedsHumanError(context)
            else:
                raise
    
    def _generate_suggestions(self, user_text: str) -> List[str]:
        """
        Generate helpful suggestions for the user.
        
        Args:
            user_text: Original user input
            
        Returns:
            List of suggestion strings
        """
        suggestions = []
        
        # Basic suggestions based on content
        if "data" in user_text.lower():
            suggestions.append("Try specifying the exact filename (e.g., 'load customers.csv')")
            suggestions.append("Be more specific about the data analysis you want")
        
        if "model" in user_text.lower():
            suggestions.append("Specify the type of model (e.g., 'train random forest model')")
            suggestions.append("Include the target variable or prediction goal")
        
        if "visualiz" in user_text.lower() or "plot" in user_text.lower():
            suggestions.append("Specify the type of visualization (histogram, scatter, etc.)")
            suggestions.append("Mention which columns to visualize")
        
        # General suggestions
        suggestions.extend([
            "Break complex requests into simpler steps",
            "Use specific action words like 'load', 'analyze', 'create', 'train'",
            "Include file names and column names when relevant"
        ])
        
        return suggestions[:5]  # Limit to top 5 suggestions 