#!/usr/bin/env python3
"""
Preserve PoC: Basic end-to-end demo.

Demonstrates: PII scrubbing → API query → response restoration.

Usage:
    # Option 1: Set in .env file at project root
    # Option 2: export DEEPINFRA_API_KEY=your_key_here
    python poc/demo_basic.py
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

    # Configure with aggressive PII detection and known names
    config = PreserveConfig(
        sensitivity_level=SensitivityLevel.AGGRESSIVE,
        known_names=["John Doe", "Sarah Chen"],
    )

    client = PreserveClient(
        api_key=api_key,
        model="meta-llama/Llama-3.3-70B-Instruct",
        config=config,
    )

    # A prompt with realistic PII
    prompt = (
        "I'm Dr. Sarah Chen (sarah.chen@hospital.org). I have a patient named "
        "John Doe, SSN 123-45-6789, DOB 03/15/1985, phone (555) 867-5309. "
        "He presented with chest pain and elevated troponin levels. "
        "His insurance ID is from Aetna. Please suggest a follow-up care plan."
    )

    messages = [
        {"role": "system", "content": "You are a medical assistant. Be concise."},
        {"role": "user", "content": prompt},
    ]

    # --- Step 1: Preview what would be sent ---
    print("=" * 70)
    print("STEP 1: ORIGINAL PROMPT")
    print("=" * 70)
    print(prompt)
    print()

    sanitized_messages, placeholder_map = client.scrub_only(messages)

    print("=" * 70)
    print("STEP 2: SANITIZED PROMPT (what leaves your machine)")
    print("=" * 70)
    print(sanitized_messages[1]["content"])
    print()

    print("=" * 70)
    print("STEP 3: PLACEHOLDER MAP")
    print("=" * 70)
    for ph, orig in placeholder_map.entries.items():
        print(f"  {ph:20s} → {orig}")
    print()

    # --- Step 2: Actually send the query ---
    print("=" * 70)
    print("STEP 4: SENDING SANITIZED QUERY TO DEEPINFRA...")
    print("=" * 70)

    response = client.chat(messages)

    print()
    print("=" * 70)
    print("STEP 5: RAW RESPONSE (with placeholders)")
    print("=" * 70)
    print(response.raw_response)
    print()

    print("=" * 70)
    print("STEP 6: RESTORED RESPONSE (PII re-inserted locally)")
    print("=" * 70)
    print(response.restored_response)
    print()

    # --- Step 3: Audit summary ---
    print("=" * 70)
    print("STEP 7: AUDIT SUMMARY")
    print("=" * 70)
    summary = client.audit_log.summary()
    print(f"  Total operations:  {summary['total_operations']}")
    print(f"  Total PII scrubbed: {summary['total_pii_scrubbed']}")
    print(f"  PII by type:       {summary['pii_by_type']}")
    print(f"  API tokens used:   {response.usage}")
    print()


if __name__ == "__main__":
    main()
