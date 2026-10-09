# observability/

Shared structured logging, and later tracing and cost/latency tracking.

```python
from observability.logging import get_logger, log_context

log = get_logger(__name__)
with log_context(alert_id="a-1"):  # adds request_id, and trace_id when in Lambda
    log.info("tool_called", extra={"tool": "get_health"})
```
