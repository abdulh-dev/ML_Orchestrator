#Actively in Use
"""
Security utilities for the Master Orchestrator.

Provides input sanitization, prompt injection defense, and other security measures.
"""

import re
import bleach
import validators
from typing import List, Set
import logging

logger = logging.getLogger(__name__)

class SecurityUtils:
    """Security utilities for input sanitization and validation."""
    
    # Dangerous patterns that should be removed
    DANGEROUS_PATTERNS = [
        r"<system>.*?</system>",
        r"IGNORE\s+ALL\s+INSTRUCTIONS",
        r"IGNORE\s+PREVIOUS\s+INSTRUCTIONS", 
        r"DISREGARD\s+ALL\s+PREVIOUS\s+INSTRUCTIONS",
        r"<script.*?>.*?</script>",
        r"javascript:",
        r"data:text/html",
        r"eval\s*\(",
        r"exec\s*\(",
        r"__import__",
        r"subprocess\.",
        r"os\.",
        r"sys\.",
    ]
    
    # Suspicious tokens that should be escaped
    SUSPICIOUS_TOKENS = {
        "{{", "}}", "{%", "%}", "<%", "%>", 
        "<!", "-->", "/*", "*/", "//",
        ";", "|", "&", "$", "`"
    }
    
    def __init__(self, max_input_length: int = 10000):
        self.max_input_length = max_input_length
        self.pattern_regex = re.compile("|".join(self.DANGEROUS_PATTERNS), re.IGNORECASE | re.DOTALL)
    
    def sanitize_input(self, user_text: str) -> str:
        """
        Sanitize user input by removing dangerous patterns and limiting length.
        
        Args:
            user_text: Raw user input
            
        Returns:
            Sanitized text safe for processing
        """
        if not user_text or not isinstance(user_text, str):
            return ""
        
        # Remove dangerous patterns
        text = self.pattern_regex.sub("", user_text)
        
        # Remove HTML/XML tags
        text = bleach.clean(text, tags=[], attributes={}, strip=True)
        
        # Escape suspicious tokens
        for token in self.SUSPICIOUS_TOKENS:
            text = text.replace(token, f"\\{token}")
        
        # Truncate to max length
        text = text[:self.max_input_length]
        
        # Remove excessive whitespace
        text = re.sub(r'\s+', ' ', text).strip()
        
        logger.debug(f"Sanitized input: {len(user_text)} -> {len(text)} chars")
        return text
    
    def minimize_context(self, user_text: str, max_sentences: int = 2) -> str:
        """
        Extract key sentences to minimize context for LLM processing.
        
        Args:
            user_text: Input text to minimize
            max_sentences: Maximum number of sentences to keep
            
        Returns:
            Minimized text with key information
        """
        if not user_text:
            return ""
        
        # Split into sentences (simple approach)
        sentences = re.split(r'[.!?]+', user_text)
        sentences = [s.strip() for s in sentences if s.strip()]
        
        if len(sentences) <= max_sentences:
            return user_text
        
        # Prioritize sentences with question words or action verbs
        priority_patterns = [
            r'\b(what|how|why|when|where|which|who)\b',
            r'\b(analyze|create|generate|load|process|run|execute)\b',
            r'\b(data|dataset|model|workflow|task)\b'
        ]
        
        scored_sentences = []
        for sentence in sentences:
            score = 0
            for pattern in priority_patterns:
                score += len(re.findall(pattern, sentence, re.IGNORECASE))
            scored_sentences.append((score, sentence))
        
        # Sort by score and take top sentences
        scored_sentences.sort(key=lambda x: x[0], reverse=True)
        top_sentences = [s[1] for s in scored_sentences[:max_sentences]]
        
        return ". ".join(top_sentences) + "."
    
    def validate_workflow_yaml(self, yaml_content: str) -> bool:
        """
        Validate that YAML content doesn't contain dangerous constructs.
        
        Args:
            yaml_content: YAML content to validate
            
        Returns:
            True if safe, False if dangerous
        """
        if not yaml_content:
            return False
        
        # Check for dangerous YAML constructs
        dangerous_yaml_patterns = [
            r'!!python/',  # Python object serialization
            r'!!binary',   # Binary data
            r'!!exec',     # Execution
            r'!!eval',     # Evaluation
            r'&\w+',       # YAML anchors (can be misused)
        ]
        
        for pattern in dangerous_yaml_patterns:
            if re.search(pattern, yaml_content, re.IGNORECASE):
                logger.warning(f"Dangerous YAML pattern detected: {pattern}")
                return False
        
        return True
    
    def extract_urls(self, text: str) -> List[str]:
        """
        Extract and validate URLs from text.
        
        Args:
            text: Text to extract URLs from
            
        Returns:
            List of valid URLs
        """
        url_pattern = r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+'
        urls = re.findall(url_pattern, text)
        
        valid_urls = []
        for url in urls:
            if validators.url(url):
                valid_urls.append(url)
            else:
                logger.warning(f"Invalid URL detected: {url}")
        
        return valid_urls
    
    def is_safe_filename(self, filename: str) -> bool:
        """
        Check if a filename is safe for use.
        
        Args:
            filename: Filename to validate
            
        Returns:
            True if safe, False if dangerous
        """
        if not filename or not isinstance(filename, str):
            return False
        
        # Check for path traversal
        if ".." in filename or "/" in filename or "\\" in filename:
            return False
        
        # Check for dangerous file extensions
        dangerous_extensions = {
            ".exe", ".bat", ".sh", ".py", ".js", ".php", 
            ".jsp", ".asp", ".aspx", ".pl", ".rb"
        }
        
        file_ext = filename.lower().split(".")[-1] if "." in filename else ""
        if f".{file_ext}" in dangerous_extensions:
            return False
        
        # Check filename length
        if len(filename) > 255:
            return False
        
        return True 