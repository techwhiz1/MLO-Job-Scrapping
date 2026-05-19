#!/usr/bin/env python3
"""
Port Testing Script
Test if specific ports are open and responding
"""

import socket
import requests
import subprocess
import sys
from urllib.parse import urljoin

def test_port_open(host, port):
    """Test if a port is open using socket"""
    try:
        with socket.create_connection((host, port), timeout=3):
            return True
    except (socket.error, socket.timeout):
        return False

def test_http_endpoint(url):
    """Test HTTP endpoint"""
    try:
        response = requests.get(url, timeout=5)
        return response.status_code, response.text[:200]
    except requests.exceptions.RequestException as e:
        return None, str(e)

def get_process_on_port(port):
    """Get process information for a specific port"""
    try:
        result = subprocess.run(['sudo', 'netstat', '-tlnp'], 
                              capture_output=True, text=True)
        for line in result.stdout.split('\n'):
            if f':{port}' in line and 'LISTEN' in line:
                return line.strip()
    except:
        pass
    return None

def main():
    """Test common ports"""
    print("🔍 Port Testing Script")
    print("=" * 50)
    
    # Ports to test
    test_ports = [
        (8888, "Backend API"),
        (4014, "Frontend"),
        (3000, "React Dev Server"),
        (8080, "Alternative Web Server"),
        (5000, "Flask/Other")
    ]
    
    print("\n📋 Port Status:")
    for port, description in test_ports:
        is_open = test_port_open('localhost', port)
        status = "✅ OPEN" if is_open else "❌ CLOSED"
        print(f"Port {port:4d} ({description:20s}): {status}")
        
        if is_open:
            process_info = get_process_on_port(port)
            if process_info:
                print(f"     Process: {process_info.split()[-1] if process_info else 'Unknown'}")
    
    print("\n🌐 HTTP Endpoint Tests:")
    
    # Test backend endpoints
    backend_endpoints = [
        "http://localhost:8888/",
        "http://localhost:8888/cors-test"
    ]
    
    for url in backend_endpoints:
        print(f"\nTesting: {url}")
        status_code, response = test_http_endpoint(url)
        if status_code:
            print(f"  ✅ Status: {status_code}")
            print(f"  📄 Response: {response}")
        else:
            print(f"  ❌ Error: {response}")
    
    print("\n🔧 Useful Commands:")
    print("  sudo netstat -tlnp | grep :8888  # Check backend port")
    print("  curl http://localhost:8888/      # Test backend")
    print("  pm2 status                       # Check PM2 processes")
    print("  pm2 logs job-scraping-backend    # Check backend logs")

if __name__ == "__main__":
    main()

