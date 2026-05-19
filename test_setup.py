#!/usr/bin/env python3
"""
Test script to verify the job scraping tool setup
"""

import sys
import subprocess
import importlib.util
import os

def check_python_version():
    """Check if Python version is 3.8+"""
    version = sys.version_info
    if version.major < 3 or (version.major == 3 and version.minor < 8):
        print("❌ Python 3.8+ is required. Current version:", sys.version)
        return False
    print(f"✅ Python version: {sys.version.split()[0]}")
    return True

def check_package(package_name):
    """Check if a Python package is installed"""
    try:
        spec = importlib.util.find_spec(package_name)
        if spec is not None:
            print(f"✅ {package_name} is installed")
            return True
        else:
            print(f"❌ {package_name} is not installed")
            return False
    except ImportError:
        print(f"❌ {package_name} is not installed")
        return False

def check_node_npm():
    """Check if Node.js and npm are installed"""
    try:
        # Check Node.js
        result = subprocess.run(['node', '--version'], capture_output=True, text=True)
        if result.returncode == 0:
            print(f"✅ Node.js version: {result.stdout.strip()}")
            node_ok = True
        else:
            print("❌ Node.js is not installed")
            node_ok = False
        
        # Check npm
        result = subprocess.run(['npm', '--version'], capture_output=True, text=True)
        if result.returncode == 0:
            print(f"✅ npm version: {result.stdout.strip()}")
            npm_ok = True
        else:
            print("❌ npm is not installed")
            npm_ok = False
            
        return node_ok and npm_ok
    except FileNotFoundError:
        print("❌ Node.js and npm are not installed")
        return False

def check_file_structure():
    """Check if all required files exist"""
    required_files = [
        'requirements.txt',
        'backend/main.py',
        'backend/job_scraper.py',
        'frontend/package.json',
        'frontend/src/App.js',
        'frontend/src/components/JobScraperForm.js',
        'frontend/src/components/JobResultsTable.js',
        'frontend/src/services/api.js'
    ]
    
    all_files_exist = True
    for file_path in required_files:
        if os.path.exists(file_path):
            print(f"✅ {file_path} exists")
        else:
            print(f"❌ {file_path} is missing")
            all_files_exist = False
    
    return all_files_exist

def main():
    print("🔍 Checking Job Scraping Tool Setup...\n")
    
    checks = [
        ("Python Version", check_python_version),
        ("File Structure", check_file_structure),
        ("Node.js and npm", check_node_npm),
    ]
    
    # Check required Python packages
    required_packages = [
        'fastapi', 'uvicorn', 'crawl4ai', 'openai', 
        'pydantic', 'aiofiles', 'pandas', 'httpx', 
        'beautifulsoup4', 'lxml', 'selenium'
    ]
    
    all_passed = True
    
    for check_name, check_func in checks:
        print(f"\n📋 {check_name}:")
        if not check_func():
            all_passed = False
    
    print(f"\n📋 Python Packages:")
    for package in required_packages:
        if not check_package(package):
            all_passed = False
    
    print("\n" + "="*50)
    
    if all_passed:
        print("🎉 All checks passed! Your setup is ready.")
        print("\nTo start the application:")
        print("1. Run: python backend/main.py (in one terminal)")
        print("2. Run: cd frontend && npm start (in another terminal)")
        print("3. Open http://localhost:3000 in your browser")
    else:
        print("⚠️  Some checks failed. Please install missing dependencies:")
        print("1. Install Python packages: pip install -r requirements.txt")
        print("2. Install Node.js from: https://nodejs.org/")
        print("3. Install frontend packages: cd frontend && npm install")

if __name__ == "__main__":
    main()
