# 2-Minute Demo Script: Production LLM API Gateway

Follow this step-by-step walkthrough to demonstrate the core capabilities of the gateway to an engineering reviewer in under two minutes.

---

## Step 1: Start the Service

In your terminal, launch the application using `docker compose` (or local uvicorn):

```bash
# Option A: With Docker Compose (starts API, PostgreSQL, Redis)
docker compose up -d

# Option B: Local development mode
source .venv/bin/activate
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

Verify service liveness and readiness:
```bash
curl -s http://localhost:8000/health | jq .
curl -s http://localhost:8000/ready | jq .
```

---

## Step 2: Generate a Client API Key

Create an active client key with a custom rate limit of 3 requests per minute:

```bash
python scripts/create_api_key.py --name "Demo Client" --rate-limit 3
```

Copy the generated `RAW API KEY` (e.g. `gw_live_abc123...`). Export it for testing:
```bash
export GATEWAY_KEY="<paste-your-raw-key-here>"
```

---

## Step 3: Open OpenAPI Documentation

Open your browser to:
[http://localhost:8000/docs](http://localhost:8000/docs)

Showcase:
- Tags: `Generation` and `System`
- Response schemas: `LLMResponse`, `ErrorResponse`, `ReadyResponse`
- Interactive OpenAPI schema at `http://localhost:8000/openapi.json`

---

## Step 4: Make a Successful Generation Request & Inspect Correlation ID

Send a request via `curl`:

```bash
curl -i -X POST http://localhost:8000/v1/generate \
  -H "X-API-Key: $GATEWAY_KEY" \
  -H "X-Request-ID: demo-trace-001" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "gpt-4o",
    "messages": [
      {"role": "system", "content": "You are a concise engineering tutor."},
      {"role": "user", "content": "What is an idempotency key?"}
    ],
    "temperature": 0.2,
    "max_tokens": 100
  }'
```

**Highlight**:
1. Response header: `X-Request-ID: demo-trace-001` (preserved from client)
2. Response headers: `X-RateLimit-Limit: 3`, `X-RateLimit-Remaining: 2`, `X-RateLimit-Reset: <timestamp>`
3. Normalized response shape:
```json
{
  "request_id": "demo-trace-001",
  "provider": "openai",
  "model": "gpt-4o",
  "content": "An idempotency key is a unique token...",
  "input_tokens": 24,
  "output_tokens": 30,
  "total_tokens": 54,
  "finish_reason": "stop",
  "latency_ms": 482.15
}
```

---

## Step 5: Trigger Rate Limiting (HTTP 429)

Send 3 rapid requests to exhaust the quota:

```bash
for i in {1..3}; do
  curl -s -o /dev/null -w "Request $i: HTTP %{http_code}\n" -X POST http://localhost:8000/v1/generate \
    -H "X-API-Key: $GATEWAY_KEY" \
    -H "Content-Type: application/json" \
    -d '{"model": "gpt-4o", "messages": [{"role": "user", "content": "ping"}]}';
done
```

The 3rd or 4th request returns:
```
HTTP/1.1 429 Too Many Requests
Retry-After: 58
X-RateLimit-Limit: 3
X-RateLimit-Remaining: 0
X-RateLimit-Reset: 1789809600
```
```json
{
  "error": {
    "code": "RATE_LIMITED",
    "message": "Rate limit of 3 requests/minute exceeded. Try again in 58s.",
    "request_id": "req_8af19401..."
  }
}
```

---

## Step 6: Demonstrate Structured Error Handling (Validation)

Send an invalid request with an unsupported temperature ($2.5$) and empty messages:

```bash
curl -i -X POST http://localhost:8000/v1/generate \
  -H "X-API-Key: $GATEWAY_KEY" \
  -H "Content-Type: application/json" \
  -d '{"model": "gpt-4o", "messages": [], "temperature": 2.5}'
```

Returns `422 Unprocessable Entity`:
```json
{
  "error": {
    "code": "INVALID_REQUEST",
    "message": "Request validation failed.",
    "request_id": "req_7294bb...",
    "details": {
      "validation_errors": [
        {"loc": ["body", "messages"], "msg": "List should have at least 1 item after validation"},
        {"loc": ["body", "temperature"], "msg": "Input should be less than or equal to 2"}
      ]
    }
  }
}
```

---

## Step 7: Demonstrate Webhook Signing

Send a request with `webhook_url`:

```bash
curl -i -X POST http://localhost:8000/v1/generate \
  -H "X-API-Key: $GATEWAY_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "gpt-4o",
    "messages": [{"role": "user", "content": "Run async generation"}],
    "webhook_url": "https://webhook.site/your-custom-url"
  }'
```

Check the receiving endpoint for headers:
- `X-Webhook-Signature: v1=<hmac-sha256-hex>`
- `X-Webhook-ID: evt_...`
- `X-Webhook-Timestamp: 2026-09-19T...`
- `X-Request-ID: req_...`

Run the verification function in `examples/client.py` to confirm the signature matches.

---

## Step 8: Run the Test Suite

Run the full automated test suite to show 100% passing tests:

```bash
pytest -v
```

Output:
```
============================== 40 passed in 4.47s ==============================
```
