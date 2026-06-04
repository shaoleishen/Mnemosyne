#!/usr/bin/env python3
"""Test Vision API with a simple text request."""

import os
import requests
import json

# Load environment variables
def load_env():
    env_path = os.path.join(os.path.dirname(__file__), '.env')
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#'):
                key, value = line.split('=', 1)
                os.environ[key] = value

load_env()

api_key = os.environ.get('VISION_API_KEY')
base_url = os.environ.get('VISION_API_BASE_URL')
model = os.environ.get('VISION_MODEL')

print(f"API Key: {api_key[:10]}...")
print(f"Base URL: {base_url}")
print(f"Model: {model}")

# Test simple text request
url = f"{base_url}/chat/completions"
headers = {
    "Authorization": f"Bearer {api_key}",
    "Content-Type": "application/json"
}

data = {
    "model": model,
    "messages": [
        {
            "role": "user",
            "content": "Hello, this is a connection test. Reply with one word: OK"
        }
    ],
    "max_tokens": 10
}

try:
    response = requests.post(url, headers=headers, json=data, timeout=30)
    print(f"Status Code: {response.status_code}")
    if response.status_code == 200:
        result = response.json()
        print("Response:", json.dumps(result, indent=2))
    else:
        print("Error:", response.text)
except Exception as e:
    print(f"Exception: {e}")
