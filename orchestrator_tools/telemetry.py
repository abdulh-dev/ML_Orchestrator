#Actively in Use
"""
Telemetry and Tracing for the Master Orchestrator.

Provides OpenTelemetry distributed tracing, correlation IDs, and performance monitoring.
"""

import uuid
import logging
from typing import Dict, Any, Optional, Callable
from datetime import datetime
from functools import wraps
from contextlib import contextmanager
import asyncio

try:
    from opentelemetry import trace, context, baggage
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.instrumentation.requests import RequestsInstrumentor
    from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
    from opentelemetry.propagate import extract, inject
    TELEMETRY_AVAILABLE = True
except ImportError:
    TELEMETRY_AVAILABLE = False

logger = logging.getLogger(__name__)

class CorrelationID:
    """Manages correlation IDs for request tracing."""
    
    @staticmethod
    def generate() -> str:
        """Generate a new correlation ID."""
        return str(uuid.uuid4())
    
    @staticmethod
    def from_headers(headers: Dict[str, str]) -> Optional[str]:
        """Extract correlation ID from HTTP headers."""
        return headers.get("X-Correlation-ID") or headers.get("x-correlation-id")
    
    @staticmethod
    def to_headers(correlation_id: str) -> Dict[str, str]:
        """Convert correlation ID to HTTP headers."""
        return {"X-Correlation-ID": correlation_id}

class TelemetryManager:
    """Manages OpenTelemetry tracing and correlation IDs."""
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize telemetry manager.
        
        Args:
            config: Configuration dictionary for telemetry settings
        """
        self.config = config
        self.enabled = config.get("enabled", True) and TELEMETRY_AVAILABLE
        self.service_name = config.get("service_name", "master-orchestrator")
        self.tracer = None
        
        if self.enabled:
            self._setup_tracing()
        else:
            logger.warning("Telemetry disabled or OpenTelemetry not available")

    def _setup_tracing(self):
        """Set up OpenTelemetry tracing."""
        try:
            # Create resource with service information
            resource = Resource.create({
                "service.name": self.service_name,
                "service.version": self.config.get("service_version", "1.0.0"),
                "service.instance.id": str(uuid.uuid4())
            })
            
            # Set up tracer provider
            tracer_provider = TracerProvider(resource=resource)
            trace.set_tracer_provider(tracer_provider)
            
            # Set up exporter (OTLP)
            otlp_endpoint = self.config.get("otlp_endpoint")
            if otlp_endpoint:
                otlp_exporter = OTLPSpanExporter(endpoint=otlp_endpoint)
                span_processor = BatchSpanProcessor(otlp_exporter)
                tracer_provider.add_span_processor(span_processor)
            
            # Get tracer
            self.tracer = trace.get_tracer(self.service_name)
            
            # Instrument HTTP clients
            RequestsInstrumentor().instrument()
            HTTPXClientInstrumentor().instrument()
            
            logger.info(f"Telemetry initialized for service: {self.service_name}")
            
        except Exception as e:
            logger.error(f"Failed to initialize telemetry: {e}")
            self.enabled = False

    def start_span(self, operation_name: str, **attributes) -> Any:
        """
        Start a new span.
        
        Args:
            operation_name: Name of the operation
            **attributes: Additional span attributes
            
        Returns:
            Span object or None if telemetry disabled
        """
        if not self.enabled or not self.tracer:
            return None
        
        span = self.tracer.start_span(operation_name)
        
        # Set common attributes
        span.set_attribute("service.name", self.service_name)
        span.set_attribute("timestamp", datetime.utcnow().isoformat())
        
        # Set custom attributes
        for key, value in attributes.items():
            if value is not None:
                span.set_attribute(key, str(value))
        
        return span

    @contextmanager
    def trace_operation(self, operation_name: str, **attributes):
        """
        Context manager for tracing operations.
        
        Args:
            operation_name: Name of the operation
            **attributes: Additional span attributes
        """
        span = self.start_span(operation_name, **attributes)
        
        try:
            if span:
                with trace.use_span(span):
                    yield span
            else:
                yield None
        except Exception as e:
            if span:
                span.set_status(trace.Status(trace.StatusCode.ERROR, str(e)))
                span.set_attribute("error", True)
                span.set_attribute("error.message", str(e))
            raise
        finally:
            if span:
                span.end()

    def trace_async_operation(self, operation_name: str, **attributes):
        """
        Decorator for tracing async operations.
        
        Args:
            operation_name: Name of the operation
            **attributes: Additional span attributes
        """
        def decorator(func: Callable) -> Callable:
            @wraps(func)
            async def wrapper(*args, **kwargs):
                with self.trace_operation(operation_name, **attributes) as span:
                    if span:
                        # Add function information to span
                        span.set_attribute("function.name", func.__name__)
                        span.set_attribute("function.module", func.__module__)
                    
                    return await func(*args, **kwargs)
            return wrapper
        return decorator

    def trace_sync_operation(self, operation_name: str, **attributes):
        """
        Decorator for tracing sync operations.
        
        Args:
            operation_name: Name of the operation
            **attributes: Additional span attributes
        """
        def decorator(func: Callable) -> Callable:
            @wraps(func)
            def wrapper(*args, **kwargs):
                with self.trace_operation(operation_name, **attributes) as span:
                    if span:
                        # Add function information to span
                        span.set_attribute("function.name", func.__name__)
                        span.set_attribute("function.module", func.__module__)
                    
                    return func(*args, **kwargs)
            return wrapper
        return decorator

    def add_baggage(self, key: str, value: str):
        """Add baggage to current context."""
        if self.enabled:
            ctx = baggage.set_baggage(key, value)
            context.attach(ctx)

    def get_baggage(self, key: str) -> Optional[str]:
        """Get baggage from current context."""
        if self.enabled:
            return baggage.get_baggage(key)
        return None

    def propagate_context_to_kafka(self, headers: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Propagate tracing context to Kafka headers.
        
        Args:
            headers: Existing headers dict
            
        Returns:
            Headers dict with tracing context
        """
        if not self.enabled:
            return headers or {}
        
        kafka_headers = headers or {}
        
        # Inject OpenTelemetry context
        inject(kafka_headers)
        
        return kafka_headers

    def extract_context_from_kafka(self, headers: Dict[str, Any]):
        """
        Extract tracing context from Kafka headers.
        
        Args:
            headers: Kafka message headers
        """
        if not self.enabled:
            return
        
        # Extract OpenTelemetry context
        ctx = extract(headers)
        context.attach(ctx)

    def create_workflow_span(self, run_id: str, operation: str, **attributes):
        """
        Create a span specifically for workflow operations.
        
        Args:
            run_id: Workflow run ID
            operation: Operation name
            **attributes: Additional attributes
        """
        return self.start_span(
            f"workflow.{operation}",
            run_id=run_id,
            operation_type="workflow",
            **attributes
        )

    def create_task_span(self, run_id: str, task_id: str, operation: str, **attributes):
        """
        Create a span specifically for task operations.
        
        Args:
            run_id: Workflow run ID
            task_id: Task ID
            operation: Operation name
            **attributes: Additional attributes
        """
        return self.start_span(
            f"task.{operation}",
            run_id=run_id,
            task_id=task_id,
            operation_type="task",
            **attributes
        )

    def get_current_trace_id(self) -> Optional[str]:
        """Get the current trace ID."""
        if not self.enabled:
            return None
        
        current_span = trace.get_current_span()
        if current_span and current_span.get_span_context().is_valid:
            return format(current_span.get_span_context().trace_id, '032x')
        return None

    def get_current_span_id(self) -> Optional[str]:
        """Get the current span ID."""
        if not self.enabled:
            return None
        
        current_span = trace.get_current_span()
        if current_span and current_span.get_span_context().is_valid:
            return format(current_span.get_span_context().span_id, '016x')
        return None

# Global telemetry manager instance
_telemetry_manager: Optional[TelemetryManager] = None

def initialize_telemetry(config: Dict[str, Any]) -> TelemetryManager:
    """Initialize global telemetry manager."""
    global _telemetry_manager
    _telemetry_manager = TelemetryManager(config)
    return _telemetry_manager

def get_telemetry_manager() -> Optional[TelemetryManager]:
    """Get the global telemetry manager."""
    return _telemetry_manager

# Convenience functions for common operations
def start_span(operation_name: str, **attributes):
    """Start a span using the global telemetry manager."""
    manager = get_telemetry_manager()
    if manager:
        return manager.start_span(operation_name, **attributes)
    return None

def trace_operation(operation_name: str, **attributes):
    """Trace an operation using the global telemetry manager."""
    manager = get_telemetry_manager()
    if manager:
        return manager.trace_operation(operation_name, **attributes)
    
    # Return a no-op context manager if telemetry is disabled
    @contextmanager
    def noop_context():
        yield None
    
    return noop_context()

def trace_async(operation_name: str, **attributes):
    """Decorator for async operations using the global telemetry manager."""
    manager = get_telemetry_manager()
    if manager:
        return manager.trace_async_operation(operation_name, **attributes)
    
    # Return a no-op decorator if telemetry is disabled
    def noop_decorator(func):
        return func
    
    return noop_decorator

def trace_sync(operation_name: str, **attributes):
    """Decorator for sync operations using the global telemetry manager."""
    manager = get_telemetry_manager()
    if manager:
        return manager.trace_sync_operation(operation_name, **attributes)
    
    # Return a no-op decorator if telemetry is disabled
    def noop_decorator(func):
        return func
    
    return noop_decorator

def get_correlation_id() -> str:
    """Get or generate a correlation ID."""
    manager = get_telemetry_manager()
    if manager:
        # Try to get from baggage first
        correlation_id = manager.get_baggage("correlation_id")
        if correlation_id:
            return correlation_id
    
    # Generate new correlation ID
    return CorrelationID.generate()

def set_correlation_id(correlation_id: str):
    """Set correlation ID in the current context."""
    manager = get_telemetry_manager()
    if manager:
        manager.add_baggage("correlation_id", correlation_id) 