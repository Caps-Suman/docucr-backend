#!/usr/bin/env python3
"""
Test script for Document List Configuration APIs
"""
import requests
import json
import sys

# Configuration
BASE_URL = "http://localhost:8000"
API_URL = f"{BASE_URL}/api/document-list-config"

# Test data
test_config = {
    "columns": [
        {
            "id": "name",
            "label": "Document Name",
            "visible": True,
            "order": 1,
            "width": 200,
            "type": "text",
            "required": False
        },
        {
            "id": "status",
            "label": "Status",
            "visible": True,
            "order": 2,
            "width": 120,
            "type": "text",
            "required": True
        },
        {
            "id": "uploadedAt",
            "label": "Uploaded",
            "visible": True,
            "order": 3,
            "width": 150,
            "type": "date",
            "required": False
        }
    ],
    "viewportWidth": 1920
}

def test_api_endpoints():
    """Test all document list config API endpoints"""
    
    print("🧪 Testing Document List Configuration APIs")
    print("=" * 50)
    
    # Note: This test assumes you have authentication set up
    # You may need to modify the headers to include proper auth tokens
    headers = {
        "Content-Type": "application/json",
        # Add authentication headers here if needed
        # "Authorization": "Bearer your_token_here"
    }
    
    try:
        # Test 1: GET configuration (should return empty initially)
        print("1️⃣  Testing GET /api/document-list-config")
        response = requests.get(API_URL, headers=headers)
        print(f"   Status: {response.status_code}")
        if response.status_code == 200:
            data = response.json()
            print(f"   Response: {json.dumps(data, indent=2)}")
        else:
            print(f"   Error: {response.text}")
        print()
        
        # Test 2: PUT configuration (save new config)
        print("2️⃣  Testing PUT /api/document-list-config")
        response = requests.put(API_URL, headers=headers, json=test_config)
        print(f"   Status: {response.status_code}")
        if response.status_code == 200:
            data = response.json()
            print(f"   Response: {json.dumps(data, indent=2)}")
        else:
            print(f"   Error: {response.text}")
        print()
        
        # Test 3: GET configuration again (should return saved config)
        print("3️⃣  Testing GET /api/document-list-config (after save)")
        response = requests.get(API_URL, headers=headers)
        print(f"   Status: {response.status_code}")
        if response.status_code == 200:
            data = response.json()
            print(f"   Response: {json.dumps(data, indent=2)}")
        else:
            print(f"   Error: {response.text}")
        print()
        
        # Test 4: DELETE configuration (reset to default)
        print("4️⃣  Testing DELETE /api/document-list-config")
        response = requests.delete(API_URL, headers=headers)
        print(f"   Status: {response.status_code}")
        if response.status_code == 200:
            data = response.json()
            print(f"   Response: {json.dumps(data, indent=2)}")
        else:
            print(f"   Error: {response.text}")
        print()
        
        # Test 5: GET configuration after delete (should be empty)
        print("5️⃣  Testing GET /api/document-list-config (after delete)")
        response = requests.get(API_URL, headers=headers)
        print(f"   Status: {response.status_code}")
        if response.status_code == 200:
            data = response.json()
            print(f"   Response: {json.dumps(data, indent=2)}")
        else:
            print(f"   Error: {response.text}")
        print()
        
        print("✅ API tests completed!")
        
    except requests.exceptions.ConnectionError:
        print("❌ Error: Could not connect to the API server.")
        print("   Make sure the backend server is running on http://localhost:8000")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    test_api_endpoints()