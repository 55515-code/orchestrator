# Live Monitoring & Kilo Code Integration Proposal

**Date:** 2026-08-02  
**Status:** Research Complete - Ready for Implementation  
**Priority:** High

## Executive Summary

This proposal outlines a comprehensive approach to adding live monitoring capabilities and integrating Kilo Code into the Local Agent Substrate application. The solution leverages existing infrastructure (Prometheus metrics, FastAPI) while introducing real-time communication via Server-Sent Events (SSE) and WebSocket, plus OpenTelemetry for distributed tracing.

**Key Recommendations:**
- **Real-time updates:** Server-Sent Events (SSE) for monitoring dashboards, WebSocket for interactive Kilo Code sessions
- **Observability:** OpenTelemetry with auto-instrumentation + manual spans for business logic
- **Kilo Code integration:** OpenAI-compatible API gateway with local model fallback
- **Performance target:** <200µs overhead per request, sub-500ms latency for live updates

---

## 1. Current State Assessment

### 1.1 Existing Infrastructure

**✅ What We Have:**
- **Prometheus metrics** (`substrate/dashboard/metrics.py`): Node health, chain metrics, deployment metrics
- **Health endpoints**: `/healthz`, `/dashboard/health`, `/dashboard/status`
- **FastAPI framework**: Already supports WebSocket and SSE natively
- **OpenTelemetry dependencies declared** in `pyproject.toml` but **NOT implemented**
- **SQLite database** with basic metrics tracking

**❌ Critical Gaps:**
- No real-time communication (WebSocket/SSE) in main ops panel
- OpenTelemetry dependencies installed but not used
- No distributed tracing or trace context propagation
- No centralized logging or log correlation
- No database performance monitoring
- No alerting infrastructure
- Metrics are ephemeral (in-memory only, no persistence)

### 1.2 Kilo Code Integration Status

**Current State:**
- Substrate uses `roo-router` for local model routing
- No direct Kilo Code API integration
- No cloud model gateway configured

**Opportunity:**
Kilo Code provides an OpenAI-compatible API gateway with access to 500+ models at zero markup, plus support for local models (Ollama, LM Studio). This aligns perfectly with the substrate's "local-first, cloud-optional" philosophy.

---

## 2. Live Monitoring Solutions Evaluation

### 2.1 Real-Time Communication Options

| Solution | Direction | Complexity | Browser Support | Proxy Friendly | Best For |
|----------|-----------|------------|-----------------|----------------|----------|
| **Server-Sent Events (SSE)** | Server → Client | Low | Universal (except IE) | ✅ Yes | Dashboards, metrics streaming |
| **WebSocket** | Bidirectional | Medium | Universal | ⚠️ Sometimes | Interactive sessions, Kilo Code |
| **Long Polling** | Simulated | High | Universal | ✅ Yes | Legacy systems (avoid) |

**Recommendation:** **Hybrid approach**
- **SSE** for monitoring dashboards (one-way data flow, simpler, automatic reconnection)
- **WebSocket** for Kilo Code interactive sessions (bidirectional, command execution)

### 2.2 Observability Stack Options

#### Option A: OpenTelemetry + Prometheus + Jaeger (Recommended)

**Pros:**
- ✅ Industry standard (CNCF project, vendor-neutral)
- ✅ Already declared in `pyproject.toml`
- ✅ Auto-instrumentation for FastAPI, SQLAlchemy, httpx
- ✅ Exports to any OTLP-compatible backend
- ✅ Sub-200µs overhead with proper configuration
- ✅ Supports traces, metrics, logs with correlation

**Cons:**
- ⚠️ Requires backend setup (Jaeger/Tempo for traces)
- ⚠️ Learning curve for manual span creation

**Implementation Effort:** Medium (2-3 days)

#### Option B: Pydantic Logfire (Alternative)

**Pros:**
- ✅ Zero-config auto-instrumentation
- ✅ Python-centric insights
- ✅ Built on OpenTelemetry (can export to any backend)
- ✅ Excellent for AI/LLM observability

**Cons:**
- ❌ Server application is closed-source
- ❌ Self-hosting requires enterprise license
- ❌ Vendor lock-in risk

**Implementation Effort:** Low (1 day)

#### Option C: Tracely (Alternative)

**Pros:**
- ✅ Zero-config, 30-second setup
- ✅ Live request streaming
- ✅ Automatic PII redaction
- ✅ Sub-1ms overhead

**Cons:**
- ❌ Newer project, less mature
- ❌ Limited documentation
- ❌ Unclear long-term viability

**Implementation Effort:** Low (1 day)

**Decision:** **Option A (OpenTelemetry + Prometheus + Jaeger)** - Industry standard, already partially implemented, maximum flexibility.

### 2.3 Performance Considerations

**OpenTelemetry Overhead (Production-Grade Configuration):**

| Component | Overhead | Configuration |
|-----------|----------|---------------|
| Span creation | <1ms | `BatchSpanProcessor` |
| Network I/O | Off critical path | Async export |
| Memory | ~50MB baseline | `max_queue_size=8192` |
| CPU | <1% at 10k RPS | `schedule_delay_millis=2000` |

**Key Configuration:**
```python
span_processor = BatchSpanProcessor(
    otlp_exporter,
    max_queue_size=8192,         # Absorb traffic spikes
    schedule_delay_millis=2000,  # Flush every 2s
    max_export_batch_size=1024   # Efficient batching
)
```

---

## 3. Kilo Code Integration Options

### 3.1 Integration Architecture

**Option A: Kilo Gateway as Primary Provider (Recommended)**

```
┌─────────────────┐
│  Substrate App  │
│                 │
│  ┌───────────┐  │
│  │ LangChain │──┼──▶ Kilo Gateway (api.kilo.ai)
│  │ OpenAI    │  │         │
│  └───────────┘  │         ├─▶ Claude Opus 4.7
│                 │         ├─▶ GPT-5.5
│  ┌───────────┐  │         ├─▶ Gemini 3.1 Pro
│  │  Ollama   │──┼──▶ Local Models (fallback)
│  └───────────┘  │
└─────────────────┘
```

**Pros:**
- ✅ 500+ models at zero markup
- ✅ OpenAI-compatible API (works with LangChain)
- ✅ Automatic model updates
- ✅ BYOK support for cost optimization
- ✅ Local model fallback via Ollama

**Cons:**
- ⚠️ Requires Kilo Code account (free tier available)
- ⚠️ External dependency for cloud models

**Implementation Effort:** Low (1-2 days)

**Option B: Direct Provider Integration**

**Pros:**
- ✅ No third-party gateway
- ✅ Direct API key management

**Cons:**
- ❌ Manual model switching
- ❌ Multiple API keys to manage
- ❌ No unified billing
- ❌ More complex configuration

**Decision:** **Option A (Kilo Gateway)** - Simplifies model management, aligns with substrate's "zero external dependencies" goal via free tier + local fallback.

### 3.2 Kilo Code Features to Integrate

**Priority 1 (Core):**
- Chat completions via OpenAI-compatible API
- Model switching (Claude, GPT, Gemini, local)
- Streaming responses for real-time interaction
- Tool calling for substrate operations

**Priority 2 (Advanced):**
- Fill-in-the-middle (FIM) completions for code generation
- Agent modes (Code, Plan, Debug, Review)
- MCP (Model Context Protocol) for tool integration
- Cloud agents for remote execution

**Priority 3 (Nice-to-Have):**
- Code reviews via Kilo Code API
- Inline autocomplete
- Session persistence across devices

---

## 4. Recommended Implementation Plan

### Phase 1: Foundation (Days 1-3)

**Goal:** Establish real-time communication and basic observability

#### 1.1 SSE for Live Monitoring (Day 1)

**Files to Create/Modify:**
- `substrate/realtime.py` (new) - SSE endpoint manager
- `substrate/web.py` - Add `/stream/metrics` endpoint
- `substrate/static/app.js` - EventSource client

**Implementation:**
```python
# substrate/realtime.py
from fastapi import APIRouter
from fastapi.responses import StreamingResponse
import asyncio
import json

router = APIRouter()

@router.get("/stream/metrics")
async def stream_metrics():
    """SSE endpoint for real-time metrics"""
    async def event_generator():
        while True:
            metrics = collect_metrics()  # Reuse existing dashboard_payload
            yield f"data: {json.dumps(metrics)}\n\n"
            await asyncio.sleep(1)  # 1-second updates
    
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )
```

**Frontend Integration:**
```javascript
// substrate/static/app.js
const eventSource = new EventSource('/stream/metrics');
eventSource.onmessage = (event) => {
    const metrics = JSON.parse(event.data);
    updateDashboard(metrics);
};
```

#### 1.2 OpenTelemetry Auto-Instrumentation (Day 2)

**Files to Create/Modify:**
- `substrate/telemetry.py` (new) - OTel initialization
- `substrate/web.py` - Instrument FastAPI app
- `pyproject.toml` - Add missing dependencies

**Dependencies to Add:**
```toml
opentelemetry-exporter-otlp-proto-http>=1.41.0
opentelemetry-instrumentation-sqlalchemy>=0.63b0
opentelemetry-instrumentation-httpx>=0.63b0
```

**Implementation:**
```python
# substrate/telemetry.py
from opentelemetry import trace, metrics
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

def setup_telemetry(app):
    resource = Resource(attributes={
        "service.name": "local-agent-substrate",
        "service.version": "0.2.0"
    })
    
    provider = TracerProvider(resource=resource)
    exporter = OTLPSpanExporter(endpoint="http://localhost:4318/v1/traces")
    processor = BatchSpanProcessor(
        exporter,
        max_queue_size=8192,
        schedule_delay_millis=2000
    )
    provider.add_span_processor(processor)
    trace.set_tracer_provider(provider)
    
    # Auto-instrument FastAPI
    FastAPIInstrumentor.instrument_app(app)
```

#### 1.3 Manual Spans for Business Logic (Day 3)

**Files to Modify:**
- `substrate/orchestrator.py` - Add spans to `run_task`, `run_chain`
- `substrate/registry.py` - Add spans to repository scanning
- `substrate/db.py` - Add spans to database operations

**Example:**
```python
# substrate/orchestrator.py
from opentelemetry import trace

tracer = trace.get_tracer(__name__)

async def run_task(self, task_id: str, **kwargs):
    with tracer.start_as_current_span("run_task") as span:
        span.set_attribute("task.id", task_id)
        span.set_attribute("task.stage", kwargs.get("stage"))
        
        # Business logic here
        result = await self._execute_task(task_id, **kwargs)
        
        span.set_attribute("task.status", result.status)
        return result
```

### Phase 2: Kilo Code Integration (Days 4-5)

**Goal:** Integrate Kilo Code as primary AI provider

#### 2.1 Kilo Gateway Configuration (Day 4)

**Files to Create/Modify:**
- `substrate/providers/kilo.py` (new) - Kilo provider
- `substrate/providers/__init__.py` - Register Kilo provider
- `workspace.yaml` - Add Kilo configuration

**Implementation:**
```python
# substrate/providers/kilo.py
from langchain_openai import ChatOpenAI
from .base import Provider

class KiloProvider(Provider):
    def __init__(self, api_key: str):
        self.llm = ChatOpenAI(
            model="anthropic/claude-sonnet-4.5",
            api_key=api_key,
            base_url="https://api.kilo.ai/api/gateway"
        )
    
    async def chat(self, messages: list[dict]) -> str:
        response = await self.llm.ainvoke(messages)
        return response.content
```

**Configuration:**
```yaml
# workspace.yaml
providers:
  kilo:
    enabled: true
    api_key: "${KILO_API_KEY}"  # From environment
    default_model: "anthropic/claude-sonnet-4.5"
    fallback_models:
      - "openai/gpt-5.5"
      - "google/gemini-3.1-pro"
  
  ollama:
    enabled: true
    base_url: "http://localhost:11434"
    default_model: "llama3.2"
```

#### 2.2 WebSocket for Interactive Sessions (Day 5)

**Files to Create/Modify:**
- `substrate/web.py` - Add `/ws/kilo` WebSocket endpoint
- `substrate/static/app.js` - WebSocket client for Kilo Code
- `substrate/templates/dashboard.html` - Add Kilo Code chat interface

**Implementation:**
```python
# substrate/web.py
from fastapi import WebSocket, WebSocketDisconnect

class KiloSessionManager:
    def __init__(self):
        self.active_sessions: dict[str, WebSocket] = {}
    
    async def connect(self, websocket: WebSocket, session_id: str):
        await websocket.accept()
        self.active_sessions[session_id] = websocket
    
    def disconnect(self, session_id: str):
        self.active_sessions.pop(session_id, None)
    
    async def send_message(self, session_id: str, message: str):
        if session_id in self.active_sessions:
            await self.active_sessions[session_id].send_text(message)

kilo_manager = KiloSessionManager()

@app.websocket("/ws/kilo/{session_id}")
async def kilo_websocket(websocket: WebSocket, session_id: str):
    await kilo_manager.connect(websocket, session_id)
    try:
        while True:
            data = await websocket.receive_json()
            # Process message with Kilo Code
            response = await process_with_kilo(data["message"])
            await websocket.send_json({"response": response})
    except WebSocketDisconnect:
        kilo_manager.disconnect(session_id)
```

### Phase 3: Advanced Features (Days 6-7)

**Goal:** Add distributed tracing, alerting, and advanced Kilo Code features

#### 3.1 Distributed Tracing (Day 6)

**Files to Modify:**
- `substrate/orchestrator.py` - Propagate trace context across task chains
- `substrate/providers/kilo.py` - Add spans for LLM calls
- `substrate/db.py` - Add SQLAlchemy instrumentation

**Implementation:**
```python
# Propagate trace context
from opentelemetry import context, trace

async def run_chain(self, chain_path: list[str]):
    with tracer.start_as_current_span("run_chain") as span:
        span.set_attribute("chain.length", len(chain_path))
        
        for i, task_id in enumerate(chain_path):
            # Create child span for each task
            with tracer.start_as_current_span(f"chain_step_{i}") as child_span:
                child_span.set_attribute("task.id", task_id)
                await self.run_task(task_id)
```

#### 3.2 Alerting Infrastructure (Day 7)

**Files to Create:**
- `substrate/alerting.py` (new) - Alert rules and notifications
- `substrate/alerting_rules.yaml` (new) - Alert definitions

**Implementation:**
```python
# substrate/alerting.py
from dataclasses import dataclass
from typing import Callable

@dataclass
class AlertRule:
    name: str
    condition: Callable[[dict], bool]
    severity: str  # "critical", "warning", "info"
    message_template: str

class AlertManager:
    def __init__(self):
        self.rules: list[AlertRule] = []
    
    def add_rule(self, rule: AlertRule):
        self.rules.append(rule)
    
    async def evaluate(self, metrics: dict):
        for rule in self.rules:
            if rule.condition(metrics):
                await self.send_alert(rule, metrics)
    
    async def send_alert(self, rule: AlertRule, metrics: dict):
        message = rule.message_template.format(**metrics)
        # Send to configured channels (email, Slack, webhook)
        print(f"[{rule.severity.upper()}] {rule.name}: {message}")

# Example rule
alert_manager = AlertManager()
alert_manager.add_rule(AlertRule(
    name="high_error_rate",
    condition=lambda m: m.get("error_rate", 0) > 0.05,
    severity="critical",
    message_template="Error rate is {error_rate:.2%}"
))
```

#### 3.3 Kilo Code Agent Modes (Day 7)

**Files to Modify:**
- `substrate/providers/kilo.py` - Add agent mode support
- `substrate/static/app.js` - UI for mode selection

**Implementation:**
```python
# substrate/providers/kilo.py
class KiloAgentMode:
    CODE = "code"
    PLAN = "plan"
    DEBUG = "debug"
    REVIEW = "review"

async def run_with_mode(self, mode: str, prompt: str):
    system_prompts = {
        KiloAgentMode.CODE: "You are a code generation agent...",
        KiloAgentMode.PLAN: "You are an architecture planning agent...",
        KiloAgentMode.DEBUG: "You are a debugging agent...",
        KiloAgentMode.REVIEW: "You are a code review agent..."
    }
    
    messages = [
        {"role": "system", "content": system_prompts[mode]},
        {"role": "user", "content": prompt}
    ]
    
    return await self.chat(messages)
```

---

## 5. Deployment & Operations

### 5.1 Local Development Setup

**Step 1: Install Dependencies**
```bash
uv sync --extra dev
```

**Step 2: Start Observability Stack (Docker)**
```bash
# docker-compose.yml
version: '3.8'
services:
  jaeger:
    image: jaegertracing/all-in-one:latest
    ports:
      - "4317:4317"   # OTLP gRPC
      - "4318:4318"   # OTLP HTTP
      - "16686:16686" # Jaeger UI
  
  prometheus:
    image: prom/prometheus:latest
    ports:
      - "9090:9090"
    volumes:
      - ./prometheus.yml:/etc/prometheus/prometheus.yml
```

**Step 3: Configure Environment**
```bash
export KILO_API_KEY="your-kilo-api-key"
export OTEL_EXPORTER_OTLP_ENDPOINT="http://localhost:4318"
export OTEL_SERVICE_NAME="local-agent-substrate"
```

**Step 4: Start Substrate**
```bash
uv run python scripts/substrate_cli.py serve
```

### 5.2 Production Deployment

**OpenTelemetry Collector Configuration:**
```yaml
# otel-collector-config.yaml
receivers:
  otlp:
    protocols:
      grpc:
        endpoint: 0.0.0.0:4317
      http:
        endpoint: 0.0.0.0:4318

processors:
  batch:
    send_batch_size: 1024
    timeout: 2s
  memory_limiter:
    check_interval: 1s
    limit_mib: 512

exporters:
  otlp/jaeger:
    endpoint: jaeger:4317
    tls:
      insecure: true
  prometheus:
    endpoint: 0.0.0.0:8889

service:
  pipelines:
    traces:
      receivers: [otlp]
      processors: [memory_limiter, batch]
      exporters: [otlp/jaeger]
    metrics:
      receivers: [otlp]
      processors: [memory_limiter, batch]
      exporters: [prometheus]
```

### 5.3 Monitoring Dashboard

**Grafana Dashboard Panels:**
1. **Request Rate** - `rate(http_server_request_duration_seconds_count[5m])`
2. **Error Rate** - `rate(http_server_request_duration_seconds_count{status_code=~"5.."}[5m])`
3. **Latency (P50/P95/P99)** - `histogram_quantile(0.95, rate(http_server_request_duration_seconds_bucket[5m]))`
4. **Active WebSocket Connections** - `websocket_connections_total`
5. **Kilo Code API Calls** - `kilo_api_calls_total{model="..."}`
6. **Database Query Duration** - `histogram_quantile(0.95, rate(db_query_duration_seconds_bucket[5m]))`

---

## 6. Testing Strategy

### 6.1 Unit Tests

**Test Coverage Targets:**
- `substrate/realtime.py` - SSE endpoint, connection management
- `substrate/telemetry.py` - OTel initialization, span creation
- `substrate/providers/kilo.py` - Kilo API calls, error handling

**Example Test:**
```python
# tests/test_realtime.py
import pytest
from fastapi.testclient import TestClient
from substrate.web import app

def test_sse_metrics_endpoint():
    client = TestClient(app)
    with client.stream("GET", "/stream/metrics") as response:
        assert response.status_code == 200
        assert response.headers["content-type"] == "text/event-stream"
        
        # Read first event
        for line in response.iter_lines():
            if line.startswith("data:"):
                metrics = json.loads(line[5:])
                assert "status" in metrics
                break
```

### 6.2 Integration Tests

**Test Scenarios:**
1. SSE connection stays open and receives updates
2. WebSocket session handles multiple concurrent clients
3. OpenTelemetry spans are created for all HTTP requests
4. Kilo Code API calls are traced and logged
5. Alert rules trigger on threshold violations

### 6.3 Load Tests

**Tools:** `locust` or `k6`

**Test Plan:**
```python
# locustfile.py
from locust import HttpUser, task, between

class SubstrateUser(HttpUser):
    wait_time = between(1, 3)
    
    @task(3)
    def get_dashboard(self):
        self.client.get("/legacy")
    
    @task(2)
    def stream_metrics(self):
        with self.client.get("/stream/metrics", stream=True) as response:
            for _ in range(10):  # Read 10 events
                next(response.iter_lines())
    
    @task(1)
    def run_task(self):
        self.client.post("/api/actions/run-task", json={
            "repo_slug": "substrate-core",
            "task_id": "scan"
        })
```

**Performance Targets:**
- 1000 concurrent SSE connections: <100ms latency
- 100 concurrent WebSocket sessions: <200ms latency
- OpenTelemetry overhead: <200µs per request
- Kilo Code API response time: <2s (model-dependent)

---

## 7. Risk Mitigation

### 7.1 Technical Risks

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| OpenTelemetry overhead >200µs | High | Medium | Use `BatchSpanProcessor`, tune batch size, exclude health endpoints |
| Kilo API rate limiting | Medium | Low | Implement exponential backoff, fallback to local models |
| WebSocket connection drops | Medium | High | Auto-reconnect with exponential backoff, heartbeat ping/pong |
| SSE memory leak (unbounded connections) | High | Low | Connection timeout, max connections limit, cleanup on disconnect |
| Jaeger/Tempo storage costs | Medium | Medium | Tail-based sampling (100% errors, 1% healthy traces) |

### 7.2 Security Considerations

**API Key Management:**
- Store `KILO_API_KEY` in environment variables, never in code
- Use OS keyring for local development (already implemented in substrate)
- Rotate keys quarterly

**WebSocket Security:**
- Validate session tokens on connection
- Implement rate limiting (100 messages/minute per session)
- Sanitize all user input before passing to Kilo Code

**SSE Security:**
- No authentication required for read-only metrics (public dashboard)
- Add optional token-based auth for sensitive metrics
- CORS policy: restrict to same-origin

**OpenTelemetry Security:**
- Redact sensitive data (API keys, passwords) from spans
- Use OTLP over HTTPS in production
- Implement trace sampling to reduce data exposure

---

## 8. Success Metrics

### 8.1 Technical Metrics

- ✅ **Latency:** <200µs OTel overhead, <500ms SSE update latency
- ✅ **Reliability:** 99.9% WebSocket/SSE connection uptime
- ✅ **Observability:** 100% of HTTP requests traced, 100% of errors captured
- ✅ **Performance:** Support 1000 concurrent SSE connections, 100 WebSocket sessions

### 8.2 User Experience Metrics

- ✅ **Dashboard Refresh:** Real-time updates (no manual refresh needed)
- ✅ **Kilo Code Response:** <2s average response time
- ✅ **Error Visibility:** All errors visible in Jaeger within 5s
- ✅ **Alert Latency:** Alerts trigger within 30s of threshold violation

### 8.3 Business Metrics

- ✅ **Developer Productivity:** 20% reduction in debugging time (via tracing)
- ✅ **Model Cost:** 30% reduction via Kilo Gateway (zero markup) + local fallback
- ✅ **Incident Response:** 50% faster MTTR (mean time to resolution)

---

## 9. Future Enhancements

### 9.1 Phase 4 (Post-MVP)

**Priority 1:**
- **MCP (Model Context Protocol)** integration for tool calling
- **Cloud agents** for remote execution
- **Code reviews** via Kilo Code API

**Priority 2:**
- **Grafana Tempo** for long-term trace storage
- **Alertmanager** for notification routing (Slack, PagerDuty)
- **Anomaly detection** via ML-based alerting

**Priority 3:**
- **Multi-tenancy** for team-based monitoring
- **Custom dashboards** per user/role
- **Mobile app** for on-call monitoring

### 9.2 Advanced Features

- **AI-powered alerting:** Use Kilo Code to analyze traces and suggest fixes
- **Automated runbooks:** Trigger substrate tasks based on alerts
- **Cost optimization:** Track Kilo API usage and suggest cheaper models
- **Compliance:** Audit logs for all AI interactions

---

## 10. Conclusion

This proposal provides a clear, phased approach to adding live monitoring and Kilo Code integration to the Local Agent Substrate. The solution:

1. **Leverages existing infrastructure** (Prometheus, FastAPI, OpenTelemetry dependencies)
2. **Minimizes risk** via industry-standard tools (SSE, WebSocket, OpenTelemetry)
3. **Delivers immediate value** (real-time dashboards, distributed tracing)
4. **Scales gracefully** (supports 1000+ connections, multi-backend export)
5. **Aligns with substrate philosophy** (local-first, cloud-optional, zero markup)

**Next Steps:**
1. Review and approve this proposal
2. Create implementation branch: `feature/live-monitoring-kilo-integration`
3. Begin Phase 1 (SSE + OpenTelemetry) - estimated 3 days
4. Deploy to staging environment for validation
5. Roll out to production after 1-week soak test

**Total Estimated Effort:** 7-10 days (1 developer)  
**Risk Level:** Low (proven technologies, incremental rollout)  
**ROI:** High (improved observability, reduced debugging time, cost savings via Kilo Gateway)

---

## Appendix A: Reference Implementations

**SSE Dashboard:**
- https://fastapi.tiangolo.com/tutorial/server-sent-events/
- https://oneuptime.com/blog/post/2026-01-25-build-realtime-dashboards-fastapi/

**OpenTelemetry FastAPI:**
- https://opentelemetry.io/docs/instrumentation/python/
- https://cubeapm.com/faqs/fastapi-opentelemetry-instrumentation/

**Kilo Code API:**
- https://kilo.ai/docs/gateway/api-reference
- https://kilo.ai/docs/gateway/sdks-and-frameworks

## Appendix B: Configuration Templates

**Environment Variables:**
```bash
# Kilo Code
KILO_API_KEY=your-api-key-here
KILO_DEFAULT_MODEL=anthropic/claude-sonnet-4.5

# OpenTelemetry
OTEL_SERVICE_NAME=local-agent-substrate
OTEL_SERVICE_VERSION=0.2.0
OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4318
OTEL_EXPORTER_OTLP_PROTOCOL=http/protobuf
OTEL_PYTHON_FASTAPI_EXCLUDED_URLS=healthz,metrics,readyz

# Alerting
ALERT_EMAIL_RECIPIENT=oncall@example.com
ALERT_SLACK_WEBHOOK=https://hooks.slack.com/services/...
```

**Prometheus Scrape Config:**
```yaml
# prometheus.yml
scrape_configs:
  - job_name: 'substrate'
    scrape_interval: 15s
    static_configs:
      - targets: ['localhost:8090']
    metrics_path: '/dashboard/metrics'
```

---

**Document Version:** 1.0  
**Last Updated:** 2026-08-02  
**Author:** Substrate Maintainer Agent  
**Reviewers:** [Pending]
