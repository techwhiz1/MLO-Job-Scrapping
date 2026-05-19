#!/usr/bin/env python3
"""
Backend Testing Script
Test various endpoints of your job scraping backend
"""

import requests
import json
import sys
from urllib.parse import urljoin

def test_endpoint(url, description=""):
    """Test a specific endpoint"""
    try:
        print(f"🔄 Testing: {description}")
        print(f"URL: {url}")
        
        response = requests.get(url, timeout=10)
        
        print(f"✅ Status: {response.status_code}")
        print(f"📄 Response: {response.text[:200]}...")
        
        if response.headers.get('content-type', '').startswith('application/json'):
            try:
                json_data = response.json()
                print(f"📋 JSON: {json.dumps(json_data, indent=2)}")
            except:
                pass
        
        return True
        
    except requests.exceptions.ConnectionError:
        print(f"❌ Connection Error: Cannot connect to {url}")
        return False
    except requests.exceptions.Timeout:
        print(f"❌ Timeout: Request timed out for {url}")
        return False
    except Exception as e:
        print(f"❌ Error: {str(e)}")
        return False

def main():
    """Test all backend endpoints"""
    print("🧪 Backend Testing Script")
    print("=" * 50)
    
    # Test endpoints
    endpoints = [
        ("http://localhost:8888/", "Root endpoint"),
        ("http://localhost:8888/cors-test", "CORS test endpoint"),
        ("http://vps-fc1d7078.vps.ovh.us:8888/", "External root endpoint"),
        ("http://vps-fc1d7078.vps.ovh.us:8888/cors-test", "External CORS test"),
    ]
    
    print("\n📋 Testing endpoints:")
    for url, description in endpoints:
        print(f"\n{'='*60}")
        test_endpoint(url, description)
    
    print(f"\n🔧 Manual curl commands:")
    print("curl http://localhost:8888/")
    print("curl http://localhost:8888/cors-test")
    print("curl -v http://vps-fc1d7078.vps.ovh.us:8888/")
    print("curl -v http://vps-fc1d7078.vps.ovh.us:8888/cors-test")

if __name__ == "__main__":
    main()





