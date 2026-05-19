#!/usr/bin/env python3
"""
SSL Certificate Setup Script for Backend
This script helps set up SSL certificates for your backend server
"""

import subprocess
import os
import sys
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

def install_certbot():
    """Install Certbot for SSL certificates"""
    print("🔧 Installing Certbot...")
    
    commands = [
        "sudo apt update",
        "sudo apt install -y certbot python3-certbot-nginx",
        "sudo apt install -y nginx"
    ]
    
    for cmd in commands:
        if not run_command(cmd, f"Running: {cmd}"):
            return False
    return True

def generate_ssl_certificate(domain):
    """Generate SSL certificate using Certbot"""
    print(f"🔐 Generating SSL certificate for {domain}...")
    
    # Stop any existing services
    run_command("sudo systemctl stop nginx", "Stopping Nginx")
    
    # Generate certificate
    cert_command = f"sudo certbot certonly --standalone -d {domain} --non-interactive --agree-tos --email admin@{domain}"
    
    if run_command(cert_command, f"Generating SSL certificate for {domain}"):
        print(f"✅ SSL certificate generated for {domain}")
        return True
    else:
        print(f"❌ Failed to generate SSL certificate for {domain}")
        return False

def create_nginx_config(domain, backend_port=8888):
    """Create Nginx configuration for SSL proxy"""
    config_content = f"""
server {{
    listen 80;
    server_name {domain};
    return 301 https://$server_name$request_uri;
}}

server {{
    listen 443 ssl http2;
    server_name {domain};

    ssl_certificate /etc/letsencrypt/live/{domain}/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/{domain}/privkey.pem;
    
    # SSL configuration
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers ECDHE-RSA-AES256-GCM-SHA512:DHE-RSA-AES256-GCM-SHA512:ECDHE-RSA-AES256-GCM-SHA384:DHE-RSA-AES256-GCM-SHA384;
    ssl_prefer_server_ciphers off;
    ssl_session_cache shared:SSL:10m;
    ssl_session_timeout 10m;

    # CORS headers
    add_header 'Access-Control-Allow-Origin' '*' always;
    add_header 'Access-Control-Allow-Methods' 'GET, POST, PUT, DELETE, OPTIONS' always;
    add_header 'Access-Control-Allow-Headers' 'DNT,User-Agent,X-Requested-With,If-Modified-Since,Cache-Control,Content-Type,Range' always;
    add_header 'Access-Control-Allow-Credentials' 'true' always;

    # Handle preflight requests
    if ($request_method = 'OPTIONS') {{
        add_header 'Access-Control-Allow-Origin' '*';
        add_header 'Access-Control-Allow-Methods' 'GET, POST, PUT, DELETE, OPTIONS';
        add_header 'Access-Control-Allow-Headers' 'DNT,User-Agent,X-Requested-With,If-Modified-Since,Cache-Control,Content-Type,Range';
        add_header 'Access-Control-Max-Age' 1728000;
        add_header 'Content-Type' 'text/plain; charset=utf-8';
        add_header 'Content-Length' 0;
        return 204;
    }}

    location / {{
        proxy_pass http://localhost:{backend_port};
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        
        # CORS headers for proxy
        proxy_hide_header 'Access-Control-Allow-Origin';
        add_header 'Access-Control-Allow-Origin' '*' always;
    }}
}}
"""
    
    config_file = f"/etc/nginx/sites-available/{domain}"
    
    try:
        with open(config_file, 'w') as f:
            f.write(config_content)
        print(f"✅ Nginx configuration created: {config_file}")
        return True
    except Exception as e:
        print(f"❌ Failed to create Nginx config: {e}")
        return False

def setup_ssl_proxy(domain, backend_port=8888):
    """Set up SSL proxy using Nginx"""
    print(f"🌐 Setting up SSL proxy for {domain}...")
    
    # Create Nginx config
    if not create_nginx_config(domain, backend_port):
        return False
    
    # Enable site
    enable_cmd = f"sudo ln -sf /etc/nginx/sites-available/{domain} /etc/nginx/sites-enabled/"
    if not run_command(enable_cmd, "Enabling Nginx site"):
        return False
    
    # Test Nginx config
    if not run_command("sudo nginx -t", "Testing Nginx configuration"):
        return False
    
    # Start Nginx
    if not run_command("sudo systemctl start nginx", "Starting Nginx"):
        return False
    
    if not run_command("sudo systemctl enable nginx", "Enabling Nginx"):
        return False
    
    print(f"✅ SSL proxy setup complete!")
    print(f"🌐 Your backend is now available at: https://{domain}")
    return True

def main():
    """Main setup process"""
    print("🔐 SSL Certificate Setup for Backend")
    print("=" * 50)
    
    # Get domain from user
    domain = input("Enter your domain (e.g., api.mininglifeonline.com): ").strip()
    if not domain:
        print("❌ Domain is required")
        return False
    
    print(f"\n📋 Setup plan for {domain}:")
    print("1. Install Certbot and Nginx")
    print("2. Generate SSL certificate")
    print("3. Configure Nginx as SSL proxy")
    print("4. Start services")
    
    # Step 1: Install dependencies
    if not install_certbot():
        print("❌ Failed to install dependencies")
        return False
    
    # Step 2: Generate SSL certificate
    if not generate_ssl_certificate(domain):
        print("❌ Failed to generate SSL certificate")
        return False
    
    # Step 3: Setup SSL proxy
    if not setup_ssl_proxy(domain):
        print("❌ Failed to setup SSL proxy")
        return False
    
    print(f"\n🎉 Setup complete!")
    print(f"✅ Backend HTTPS URL: https://{domain}")
    print(f"✅ Update your frontend to use: https://{domain}/scrape")
    
    return True

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
