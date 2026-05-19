#!/usr/bin/env python3
"""
SSL Setup for VPS Domain: vps-fc1d7078.vps.ovh.us
This script sets up SSL certificate and Nginx proxy for your backend
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

def install_dependencies():
    """Install required packages"""
    print("📦 Installing dependencies...")
    
    commands = [
        "sudo apt update",
        "sudo apt install -y nginx certbot python3-certbot-nginx",
        "sudo apt install -y ufw"
    ]
    
    for cmd in commands:
        if not run_command(cmd, f"Installing: {cmd}"):
            return False
    return True

def setup_firewall():
    """Configure firewall for HTTP/HTTPS"""
    print("🔥 Configuring firewall...")
    
    commands = [
        "sudo ufw allow 'Nginx Full'",
        "sudo ufw allow ssh",
        "sudo ufw --force enable"
    ]
    
    for cmd in commands:
        if not run_command(cmd, f"Firewall: {cmd}"):
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

    # CORS headers for mixed content fix
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
        
        # Additional proxy settings
        proxy_connect_timeout 60s;
        proxy_send_timeout 60s;
        proxy_read_timeout 60s;
        
        # CORS headers for proxy
        proxy_hide_header 'Access-Control-Allow-Origin';
        add_header 'Access-Control-Allow-Origin' '*' always;
    }}
}}
"""
    
    # Create config file in temp location first, then move with sudo
    temp_config_file = f"/tmp/{domain}_nginx.conf"
    config_file = f"/etc/nginx/sites-available/{domain}"
    
    try:
        # Write to temp file first
        with open(temp_config_file, 'w') as f:
            f.write(config_content)
        print(f"✅ Nginx configuration created in temp: {temp_config_file}")
        
        # Move to nginx directory with sudo
        move_cmd = f"sudo mv {temp_config_file} {config_file}"
        if run_command(move_cmd, f"Moving config to {config_file}"):
            print(f"✅ Nginx configuration created: {config_file}")
            return True
        else:
            return False
            
    except Exception as e:
        print(f"❌ Failed to create Nginx config: {e}")
        return False

def setup_nginx_ssl_proxy(domain, backend_port=8888):
    """Set up Nginx SSL proxy"""
    print(f"🌐 Setting up Nginx SSL proxy for {domain}...")
    
    # Remove default site
    run_command("sudo rm -f /etc/nginx/sites-enabled/default", "Removing default Nginx site")
    
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
    
    print(f"✅ Nginx SSL proxy setup complete!")
    return True

def setup_ssl_renewal():
    """Set up automatic SSL renewal"""
    print("🔄 Setting up SSL certificate auto-renewal...")
    
    # Test renewal
    if run_command("sudo certbot renew --dry-run", "Testing SSL renewal"):
        print("✅ SSL auto-renewal configured")
        return True
    else:
        print("⚠️ SSL auto-renewal test failed, but continuing...")
        return True

def test_https_endpoint(domain):
    """Test the HTTPS endpoint"""
    print(f"🧪 Testing HTTPS endpoint: https://{domain}")
    
    test_commands = [
        f"curl -I https://{domain}/",
        f"curl -I https://{domain}/cors-test"
    ]
    
    for cmd in test_commands:
        if run_command(cmd, f"Testing: {cmd}"):
            print(f"✅ HTTPS endpoint working: {cmd}")
        else:
            print(f"❌ HTTPS endpoint failed: {cmd}")
    
    return True

def main():
    """Main setup process"""
    print("🔐 SSL Setup for VPS Domain")
    print("=" * 50)
    
    domain = "vps-fc1d7078.vps.ovh.us"
    backend_port = 8888
    
    print(f"🌐 Domain: {domain}")
    print(f"🔧 Backend Port: {backend_port}")
    print(f"🎯 Target: https://{domain}/scrape")
    
    print(f"\n📋 Setup steps:")
    print("1. Install dependencies (Nginx, Certbot)")
    print("2. Configure firewall")
    print("3. Generate SSL certificate")
    print("4. Configure Nginx SSL proxy")
    print("5. Test HTTPS endpoint")
    
    # Step 1: Install dependencies
    if not install_dependencies():
        print("❌ Failed to install dependencies")
        return False
    
    # Step 2: Setup firewall
    if not setup_firewall():
        print("❌ Failed to setup firewall")
        return False
    
    # Step 3: Generate SSL certificate
    if not generate_ssl_certificate(domain):
        print("❌ Failed to generate SSL certificate")
        return False
    
    # Step 4: Setup Nginx SSL proxy
    if not setup_nginx_ssl_proxy(domain, backend_port):
        print("❌ Failed to setup Nginx SSL proxy")
        return False
    
    # Step 5: Setup SSL renewal
    setup_ssl_renewal()
    
    # Step 6: Test HTTPS endpoint
    test_https_endpoint(domain)
    
    print(f"\n🎉 SSL Setup Complete!")
    print(f"✅ Backend HTTPS URL: https://{domain}")
    print(f"✅ API Endpoint: https://{domain}/scrape")
    print(f"✅ CORS Test: https://{domain}/cors-test")
    
    print(f"\n📝 Next steps:")
    print("1. Update your frontend to use: https://vps-fc1d7078.vps.ovh.us/scrape")
    print("2. Restart your PM2 backend: pm2 restart job-scraping-backend")
    print("3. Test the mixed content issue is resolved")
    
    return True

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
