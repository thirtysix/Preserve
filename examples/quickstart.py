#!/usr/bin/env python3
"""Minimal quickstart example for Preserve."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from preserve import create_client, SensitivityLevel

# Create a privacy-preserving client
client = create_client(
    api_key=os.environ["DEEPINFRA_API_KEY"],
    model="meta-llama/Llama-3.3-70B-Instruct",
    sensitivity_level=SensitivityLevel.STANDARD,
)

# Send a query — PII is automatically scrubbed before it leaves your machine
response = client.chat([
    {"role": "user", "content": "Summarize this: John Smith (john@acme.com, SSN 111-22-3333) filed a complaint."}
])

# The response has PII re-inserted locally
print(response.text)
