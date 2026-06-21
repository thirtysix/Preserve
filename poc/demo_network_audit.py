#!/usr/bin/env python3
"""
Preserve PoC: Network audit demo.

Intercepts the actual HTTP request body to prove what data leaves the machine.
Uses httpx transport hooks to capture outgoing payloads.

Usage:
    # Option 1: Set in .env file at project root
    # Option 2: export DEEPINFRA_API_KEY=your_key_here
    python poc/demo_network_audit.py
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))

import httpx
from openai import OpenAI

from preserve import PreserveConfig, Scrubber, SensitivityLevel


class AuditTransport(httpx.BaseTransport):
    """HTTP transport that logs request bodies before forwarding them."""

    def __init__(self):
        self._real_transport = httpx.HTTPTransport()
        self.captured_requests: list[dict] = []

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        # Capture the outgoing request body
        body = request.content
        if body:
            try:
                parsed = json.loads(body)
                self.captured_requests.append({
                    "url": str(request.url),
                    "method": request.method,
                    "body": parsed,
                })
            except (json.JSONDecodeError, UnicodeDecodeError):
                self.captured_requests.append({
                    "url": str(request.url),
                    "method": request.method,
                    "body_raw": body.hex()[:200],
                })

        return self._real_transport.handle_request(request)

    def close(self):
        self._real_transport.close()


def main():
    api_key = os.environ.get("DEEPINFRA_API_KEY")
    if not api_key:
        print("ERROR: Set DEEPINFRA_API_KEY environment variable")
        sys.exit(1)

    # Set up our auditing transport
    audit_transport = AuditTransport()
    http_client = httpx.Client(transport=audit_transport)

    # Create OpenAI client with our auditing transport
    openai_client = OpenAI(
        base_url="https://api.deepinfra.com/v1/openai",
        api_key=api_key,
        http_client=http_client,
    )

    # Set up the scrubber
    config = PreserveConfig(
        sensitivity_level=SensitivityLevel.AGGRESSIVE,
        known_names=["Maria Garcia"],
    )
    scrubber = Scrubber(config)

    # Original prompt with PII
    prompt = (
        "Patient Maria Garcia (maria.garcia@email.com, SSN 789-01-2345) "
        "was admitted on 01/15/2025 with complaints of severe headaches. "
        "Emergency contact: (555) 987-6543. Please summarize the admission."
    )

    messages = [
        {"role": "system", "content": "You are a medical records assistant. Be brief."},
        {"role": "user", "content": prompt},
    ]

    # Scrub the messages
    sanitized_messages, placeholder_map, detections = scrubber.scrub_messages(messages)

    print("=" * 70)
    print("NETWORK AUDIT: What actually leaves your machine")
    print("=" * 70)
    print()

    print("ORIGINAL PROMPT (local only):")
    print(f"  {prompt}")
    print()

    print("SCRUBBED PROMPT (what will be sent):")
    print(f"  {sanitized_messages[1]['content']}")
    print()

    # Send the scrubbed query
    print("Sending request to DeepInfra API...")
    response = openai_client.chat.completions.create(
        model="meta-llama/Llama-3.3-70B-Instruct",
        messages=sanitized_messages,
    )
    print()

    # Analyze captured network traffic
    print("=" * 70)
    print("CAPTURED OUTGOING HTTP REQUEST BODY")
    print("=" * 70)
    print()

    for i, req in enumerate(audit_transport.captured_requests):
        print(f"Request #{i + 1}: {req['method']} {req['url']}")
        if "body" in req:
            body_json = json.dumps(req["body"], indent=2)
            print(body_json)
        print()

    # Verify no PII in captured traffic
    pii_values = [
        "Maria Garcia",
        "maria.garcia@email.com",
        "789-01-2345",
        "(555) 987-6543",
    ]

    print("=" * 70)
    print("PII LEAKAGE CHECK")
    print("=" * 70)
    print()

    captured_text = json.dumps(audit_transport.captured_requests)
    all_clean = True
    for pii in pii_values:
        found = pii in captured_text
        status = "LEAKED" if found else "NOT FOUND (safe)"
        if found:
            all_clean = False
        print(f"  {pii:<35} {status}")

    print()
    if all_clean:
        print("  RESULT: No PII detected in outgoing network traffic.")
    else:
        print("  WARNING: PII was found in outgoing network traffic!")

    print()

    # Show the response
    raw_text = response.choices[0].message.content or ""
    restored = placeholder_map.restore(raw_text)

    print("=" * 70)
    print("RESPONSE (restored locally)")
    print("=" * 70)
    print(restored)
    print()

    http_client.close()


if __name__ == "__main__":
    main()
