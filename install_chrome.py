#!/usr/bin/env python3
"""
Chrome Browser Installation Script for Ubuntu
This script helps install Google Chrome browser for Selenium web scraping.
"""

import subprocess
import sys
import os
from pathlib import Path

def run_command(command, description=""):
    """Run a shell command and return success status"""
    try:
        print(f"🔄 {description}")
        print(f"Running: {command}")
        result = subprocess.run(command, shell=True, check=True, capture_output=True, text=True)
        print(f"✅ {description} - Success")
        if result.stdout:
            print(f"Output: {result.stdout}")
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ {description} - Failed")
        print(f"Error: {e.stderr}")
        return False

def check_chrome_installed():
    """Check if Chrome is already installed"""
    try:
        result = subprocess.run(['google-chrome', '--version'], capture_output=True, text=True)
        if result.returncode == 0:
            print(f"✅ Chrome is already installed: {result.stdout.strip()}")
            return True
    except FileNotFoundError:
        pass
    
    print("❌ Chrome is not installed")
    return False

def install_chrome_ubuntu():
    """Install Chrome on Ubuntu/Debian systems"""
    print("🚀 Installing Google Chrome on Ubuntu...")
    
    commands = [
        {
            "cmd": "wget -q -O - https://dl.google.com/linux/linux_signing_key.pub | sudo apt-key add -",
            "desc": "Adding Google Chrome repository key"
        },
        {
            "cmd": "echo 'deb [arch=amd64] http://dl.google.com/linux/chrome/deb/ stable main' | sudo tee /etc/apt/sources.list.d/google-chrome.list",
            "desc": "Adding Google Chrome repository"
        },
        {
            "cmd": "sudo apt update",
            "desc": "Updating package lists"
        },
        {
            "cmd": "sudo apt install -y google-chrome-stable",
            "desc": "Installing Google Chrome"
        }
    ]
    
    for command_info in commands:
        if not run_command(command_info["cmd"], command_info["desc"]):
            return False
    
    return True

def install_chrome_alternative():
    """Alternative Chrome installation method using wget"""
    print("🔄 Trying alternative Chrome installation method...")
    
    commands = [
        {
            "cmd": "wget -O /tmp/google-chrome-stable_current_amd64.deb https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb",
            "desc": "Downloading Chrome .deb package"
        },
        {
            "cmd": "sudo dpkg -i /tmp/google-chrome-stable_current_amd64.deb",
            "desc": "Installing Chrome .deb package"
        },
        {
            "cmd": "sudo apt-get install -f -y",
            "desc": "Fixing any dependency issues"
        }
    ]
    
    for command_info in commands:
        if not run_command(command_info["cmd"], command_info["desc"]):
            if "dpkg" in command_info["cmd"]:
                # Continue to fix dependencies even if dpkg fails initially
                continue
            return False
    
    return True

def verify_installation():
    """Verify Chrome installation"""
    print("🔍 Verifying Chrome installation...")
    
    if check_chrome_installed():
        print("🎉 Chrome installation verified successfully!")
        
        # Also check Chrome location
        try:
            result = subprocess.run(['which', 'google-chrome'], capture_output=True, text=True)
            if result.returncode == 0:
                chrome_path = result.stdout.strip()
                print(f"📍 Chrome location: {chrome_path}")
        except:
            pass
        
        return True
    else:
        print("❌ Chrome installation verification failed")
        return False

def main():
    """Main installation process"""
    print("=" * 60)
    print("🌐 Google Chrome Installation Script")
    print("=" * 60)
    
    # Check if already installed
    if check_chrome_installed():
        print("✅ Chrome is already installed. No action needed.")
        return True
    
    # Detect OS
    try:
        with open('/etc/os-release', 'r') as f:
            os_info = f.read().lower()
        
        if 'ubuntu' in os_info or 'debian' in os_info:
            print("🐧 Detected Ubuntu/Debian system")
        else:
            print("⚠️  Warning: This script is designed for Ubuntu/Debian systems")
    except:
        print("⚠️  Could not detect OS version")
    
    print("\n📋 Installation Steps:")
    print("1. Add Google Chrome repository")
    print("2. Update package lists")
    print("3. Install Google Chrome")
    print("4. Verify installation")
    
    print(f"\n🔐 Note: This script requires sudo privileges to install system packages")
    
    # Try primary installation method
    success = install_chrome_ubuntu()
    
    # If primary method fails, try alternative
    if not success:
        print("\n🔄 Primary installation failed, trying alternative method...")
        success = install_chrome_alternative()
    
    # Verify installation
    if success:
        success = verify_installation()
    
    if success:
        print("\n🎉 Installation completed successfully!")
        print("\n📝 Next steps:")
        print("1. Your Selenium script should now work with Chrome")
        print("2. Try running your job scraping script again")
        print("3. Chrome will run in headless mode for web scraping")
    else:
        print("\n❌ Installation failed!")
        print("\n🔧 Manual installation steps:")
        print("1. sudo apt update")
        print("2. wget -O /tmp/chrome.deb https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb")
        print("3. sudo dpkg -i /tmp/chrome.deb")
        print("4. sudo apt-get install -f -y")
    
    return success

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
