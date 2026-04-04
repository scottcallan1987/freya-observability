# freya-observability

Shared observability primitives for every Freya cluster.

## Usage

```python
from freya_observability.logger import configure_logging, get_logger
from freya_observability.tracing import TraceContext
from freya_observability.circuit_breaker import CircuitBreaker
from freya_observability.retry import retry_external_http, retry_inference, retry_db
from freya_observability.timeouts import FAST, NORMAL, LLM, CRAWL
from freya_observability.healthcheck import make_health_router
```

## Install (editable, from a sibling cluster's Docker build)

```
pip install -e /freya-observability
```

Each cluster's Dockerfile should `COPY freya-observability /freya-observability` and then `pip install -e /freya-observability` before installing the cluster package itself.
