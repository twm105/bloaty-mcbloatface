#!/usr/bin/env python3
"""Test script to run diagnosis with custom parameters."""
import requests
import json

url = "http://localhost:8000/diagnosis/analyze"
payload = {
    "web_search_enabled": False,
    "min_meals": 1,
    "min_symptom_occurrences": 1
}

print(f"Sending request: {json.dumps(payload, indent=2)}")
response = requests.post(url, json=payload)

print(f"Status: {response.status_code}")
print(f"Response: {json.dumps(response.json(), indent=2)}")
