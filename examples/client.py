#!/usr/bin/env python3
"""Example Python client demonstrating how to interact with the LLM API Gateway."""

import hashlib
import hmac
import sys

import httpx


class LLMGatewayClient:
    """Lightweight client for the Production LLM API Gateway."""

    def __init__(self, base_url: str, api_key: str, webhook_secret: str | None = None) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.webhook_secret = webhook_secret

    def generate(
        self,
        model: str,
        prompt: str,
        system_prompt: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 1000,
        webhook_url: str | None = None,
    ) -> dict:
        """Submit a chat completion request to the gateway."""
        url = f"{self.base_url}/v1/generate"
        headers = {
            "X-API-Key": self.api_key,
            "Content-Type": "application/json",
        }

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        payload = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if webhook_url:
            payload["webhook_url"] = webhook_url

        with httpx.Client(timeout=45.0) as client:
            response = client.post(url, json=payload, headers=headers)

            # Print rate-limit metadata returned in headers
            limit = response.headers.get("X-RateLimit-Limit")
            remaining = response.headers.get("X-RateLimit-Remaining")
            reset_epoch = response.headers.get("X-RateLimit-Reset")
            request_id = response.headers.get("X-Request-ID")

            print(f"[Gateway Trace] Request ID: {request_id}")
            print(f"[Rate Limit] Limit: {limit} | Remaining: {remaining} | Reset: {reset_epoch}")

            if response.status_code == 200:
                return response.json()
            elif response.status_code == 429:
                retry_after = response.headers.get("Retry-After", "unknown")
                print(f"[Error 429] Rate limit exceeded. Retry after {retry_after}s.")
                return response.json()
            else:
                print(f"[Error {response.status_code}] {response.text}")
                return response.json()

    def verify_webhook(self, payload_bytes: bytes, signature_header: str) -> bool:
        """Verify the HMAC-SHA256 signature of an incoming webhook event.

        Args:
            payload_bytes: Raw HTTP request body bytes as received.
            signature_header: The value of the X-Webhook-Signature header (e.g. 'v1=abc...').
        """
        if not self.webhook_secret:
            raise ValueError("webhook_secret is required to verify signatures.")

        # Strip 'v1=' prefix if present
        expected_sig = signature_header.replace("v1=", "").strip()
        computed_sig = hmac.new(
            key=self.webhook_secret.encode("utf-8"),
            msg=payload_bytes,
            digestmod=hashlib.sha256,
        ).hexdigest()

        return hmac.compare_digest(computed_sig, expected_sig)


def main() -> None:
    gateway_url = "http://localhost:8080"
    api_key = "gw_live_your_api_key_here"

    print("=" * 60)
    print("LLM API Gateway Client Example")
    print("=" * 60)

    client = LLMGatewayClient(base_url=gateway_url, api_key=api_key)

    # 1. Health check
    try:
        with httpx.Client() as http:
            health = http.get(f"{gateway_url}/health").json()
            print(f"Gateway Health: {health['status']} (v{health['version']})")
    except Exception as exc:
        print(f"Could not reach gateway at {gateway_url}: {exc}")
        print("Start the gateway with: uvicorn app.main:app --port 8080")
        sys.exit(1)

    # 2. Synchronous chat completion
    print("\nSending prompt: 'Explain the difference between TCP and UDP in 2 sentences.'")
    result = client.generate(
        model="gpt-4o",
        prompt="Explain the difference between TCP and UDP in 2 sentences.",
        system_prompt="You are a concise networking tutor.",
        temperature=0.3,
        max_tokens=100,
    )

    if "error" in result:
        print(f"Generation failed: {result['error']['message']}")
    else:
        print(f"\nResponse from {result['provider']} ({result['model']}):")
        print(result["content"])
        print(f"\nTokens used: {result['total_tokens']} | Latency: {result['latency_ms']}ms")


if __name__ == "__main__":
    main()
