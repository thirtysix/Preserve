#!/usr/bin/env python3
"""
Preserve PoC: Comparison demo.

Side-by-side comparison of sending a query WITH vs WITHOUT privacy scrubbing.
Shows exactly what data leaves the machine in each case.

Usage:
    # Option 1: Set in .env file at project root
    # Option 2: export DEEPINFRA_API_KEY=your_key_here
    python poc/demo_comparison.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))

from preserve import PreserveClient, PreserveConfig, SensitivityLevel


def main():
    api_key = os.environ.get("DEEPINFRA_API_KEY")
    if not api_key:
        print("ERROR: Set DEEPINFRA_API_KEY environment variable")
        sys.exit(1)

    config = PreserveConfig(
        sensitivity_level=SensitivityLevel.AGGRESSIVE,
        known_names=["Emily Rodriguez", "Marcus Thompson"],
    )

    client = PreserveClient(
        api_key=api_key,
        model="meta-llama/Llama-3.3-70B-Instruct",
        config=config,
    )

    prompt = (
        "Employee Emily Rodriguez (emily.rodriguez@acme-corp.com, SSN 456-78-9012) "
        "reported a workplace injury on 03/20/2025. Her supervisor Marcus Thompson "
        "(ext. (555) 234-5678) witnessed the incident. Emily's home address is "
        "742 Evergreen Terrace. Please draft an incident report summary."
    )

    messages = [
        {"role": "system", "content": "You are an HR assistant. Be professional and concise."},
        {"role": "user", "content": prompt},
    ]

    # --- WITHOUT SCRUBBING ---
    print("=" * 70)
    print("SCENARIO A: WITHOUT PRIVACY SCRUBBING")
    print("  What leaves your machine → the provider sees everything")
    print("=" * 70)
    print()
    print("SENT TO API:")
    print(f"  {prompt[:100]}...")
    print()

    response_unscrubbed = client.chat(messages, scrub=False)
    print("RESPONSE:")
    print(response_unscrubbed.raw_response)
    print()

    # --- WITH SCRUBBING ---
    print("=" * 70)
    print("SCENARIO B: WITH PRESERVE PRIVACY SCRUBBING")
    print("  What leaves your machine → provider sees only placeholders")
    print("=" * 70)
    print()

    sanitized, pm = client.scrub_only(messages)
    print("SENT TO API:")
    print(f"  {sanitized[1]['content'][:100]}...")
    print()
    print("PLACEHOLDER MAP (stays local):")
    for ph, orig in pm.entries.items():
        print(f"  {ph:20s} → {orig}")
    print()

    response_scrubbed = client.chat(messages, scrub=True)
    print("RAW RESPONSE (from API):")
    print(response_scrubbed.raw_response)
    print()
    print("RESTORED RESPONSE (local re-insertion):")
    print(response_scrubbed.restored_response)
    print()

    # --- RISK COMPARISON ---
    print("=" * 70)
    print("RISK COMPARISON")
    print("=" * 70)

    pii_items = [
        ("Name", "Emily Rodriguez"),
        ("Email", "emily.rodriguez@acme-corp.com"),
        ("SSN", "456-78-9012"),
        ("Name", "Marcus Thompson"),
        ("Phone", "(555) 234-5678"),
        ("Address", "742 Evergreen Terrace"),
    ]

    print(f"\n  {'PII Item':<15} {'Type':<10} {'Sent (A)?':<12} {'Sent (B)?':<12}")
    print(f"  {'-'*15} {'-'*10} {'-'*12} {'-'*12}")
    for pii_type, value in pii_items:
        in_a = "YES" if value in prompt else "NO"
        in_b = "NO" if value not in sanitized[1]["content"] else "YES"
        risk_a = "EXPOSED" if in_a == "YES" else "safe"
        risk_b = "safe" if in_b == "NO" else "EXPOSED"
        print(f"  {value:<15} {pii_type:<10} {risk_a:<12} {risk_b:<12}")

    print()
    summary = client.audit_log.summary()
    print(f"  Total PII items scrubbed in session: {summary['total_pii_scrubbed']}")
    print()


if __name__ == "__main__":
    main()
