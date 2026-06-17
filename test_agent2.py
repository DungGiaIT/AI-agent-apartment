#!/usr/bin/env python3
"""Quick test script for Agent 2 API endpoints."""
import json
import sys
sys.path.insert(0, '/Users/ttcenter/AI-agent-apartment')
sys.path.insert(0, '/Users/ttcenter/AI-agent-apartment/venv/lib/python3.12/site-packages')

import httpx

BASE_URL = "http://localhost:8000"

def test_health():
    r = httpx.get(f"{BASE_URL}/api/search/health", timeout=5)
    print(f"✅ Health: {r.json()}")

def test_search_clarification():
    """Test with a vague query — should ask for clarification."""
    payload = {
        "query": "tìm căn rẻ rẻ đi",
        "tenant_id": "test-001",
        "conversation_history": []
    }
    r = httpx.post(f"{BASE_URL}/api/search", json=payload, timeout=30)
    data = r.json()
    print(f"\n--- Test 1: Vague query (should ask clarification) ---")
    print(f"Status: {r.status_code}")
    if data.get('data'):
        print(f"next_action: {data['data']['next_action']}")
        print(f"bot_response: {data['data']['bot_response'][:200]}")
    else:
        print(f"Response: {json.dumps(data, ensure_ascii=False, indent=2)[:400]}")

def test_search_with_constraints():
    """Test with specific constraints."""
    payload = {
        "query": "Tôi cần căn hộ khoảng 60m², ngân sách tối đa 10 triệu/tháng, quận Hải Châu",
        "tenant_id": "test-002",
        "conversation_history": []
    }
    r = httpx.post(f"{BASE_URL}/api/search", json=payload, timeout=45)
    data = r.json()
    print(f"\n--- Test 2: Specific constraints search ---")
    print(f"Status: {r.status_code}")
    if data.get('data'):
        print(f"next_action: {data['data']['next_action']}")
        print(f"recommendations: {len(data['data']['recommendations'])} căn")
        print(f"bot_response: {data['data']['bot_response'][:300]}")
    else:
        print(f"Response: {json.dumps(data, ensure_ascii=False, indent=2)[:400]}")

if __name__ == "__main__":
    test_health()
    test_search_clarification()
    test_search_with_constraints()
    print("\n✅ All tests done!")
