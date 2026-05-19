#!/usr/bin/env python3
"""
Fix Nginx Configuration
Create a working Nginx config that doesn't conflict with port 8888
"""

import subprocess
import os

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

def create_simple_nginx_config():
    """Create a simple Nginx config that works"""
    config_content = """
# HTTP to HTTPS redirect
server {
    listen 80;
    server_name mininglifeserver.com;
    return 301 https://$server_name$request_uri;
}

# HTTPS server on standard port 443
server {
    listen 443 ssl http2;
    server_name mininglifeserver.com;

    ssl_certificate /etc/letsencrypt/live/mininglifeserver.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/mininglifeserver.com/privkey.pem;
    
    # SSL configuration
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers ECDHE-RSA-AES256-GCM-SHA512:DHE-RSA-AES256-GCM-SHA512:ECDHE-RSA-AES256-GCM-SHA384:DHE-RSA-AES256-GCM-SHA384;
    ssl_prefer_server_ciphers off;
    ssl_session_cache shared:SSL:10m;
    ssl_session_timeout 10m;

    location / {
        # Handle OPTIONS requests for CORS
        if ($request_method = 'OPTIONS') {
            add_header 'Access-Control-Allow-Origin' '*' always;
            add_header 'Access-Control-Allow-Methods' 'GET, POST, PUT, DELETE, OPTIONS' always;
            add_header 'Access-Control-Allow-Headers' 'DNT,User-Agent,X-Requested-With,If-Modified-Since,Cache-Control,Content-Type,Range' always;
            add_header 'Access-Control-Max-Age' 1728000;
            add_header 'Content-Type' 'text/plain; charset=utf-8';
            add_header 'Content-Length' 0;
            return 204;
        }

        # Proxy to backend
        proxy_pass http://localhost:8888;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        
        # Additional proxy settings
        proxy_connect_timeout 60s;
        proxy_send_timeout 60s;
        proxy_read_timeout 60s;
        
        # CORS headers for all responses
        add_header 'Access-Control-Allow-Origin' '*' always;
        add_header 'Access-Control-Allow-Methods' 'GET, POST, PUT, DELETE, OPTIONS' always;
        add_header 'Access-Control-Allow-Headers' 'DNT,User-Agent,X-Requested-With,If-Modified-Since,Cache-Control,Content-Type,Range' always;
        add_header 'Access-Control-Allow-Credentials' 'true' always;
    }
}
"""
    
    # Create config file in temp location first, then move with sudo
    temp_config_file = "/tmp/mininglifeserver_simple.conf"
    config_file = "/etc/nginx/sites-available/mininglifeserver.com"
    
    try:
        # Write to temp file first
        with open(temp_config_file, 'w') as f:
            f.write(config_content)
        print(f"✅ Simple Nginx configuration created in temp: {temp_config_file}")
        
        # Move to nginx directory with sudo
        move_cmd = f"sudo mv {temp_config_file} {config_file}"
        if run_command(move_cmd, f"Moving config to {config_file}"):
            print(f"✅ Simple Nginx configuration created: {config_file}")
            return True
        else:
            return False
            
    except Exception as e:
        print(f"❌ Failed to create Nginx config: {e}")
        return False

def fix_nginx_issues():
    """Fix common Nginx issues"""
    print("🔧 Fixing Nginx issues...")
    
    # 1. Stop Nginx
    run_command("sudo systemctl stop nginx", "Stopping Nginx")
    
    # 2. Remove problematic config
    run_command("sudo rm -f /etc/nginx/sites-enabled/mininglifeserver.com", "Removing problematic config")
    
    # 3. Create simple config
    if not create_simple_nginx_config():
        return False
    
    # 4. Enable the site
    enable_cmd = "sudo ln -sf /etc/nginx/sites-available/mininglifeserver.com /etc/nginx/sites-enabled/"
    if not run_command(enable_cmd, "Enabling Nginx site"):
        return False
    
    # 5. Test Nginx config
    if not run_command("sudo nginx -t", "Testing Nginx configuration"):
        return False
    
    # 6. Start Nginx
    if not run_command("sudo systemctl start nginx", "Starting Nginx"):
        return False
    
    if not run_command("sudo systemctl enable nginx", "Enabling Nginx"):
        return False
    
    print("✅ Nginx issues fixed!")
    return True

def main():
    """Main fix process"""
    print("🔧 Nginx Configuration Fix")
    print("=" * 50)
    
    print("📋 This will:")
    print("1. Stop Nginx")
    print("2. Remove problematic config")
    print("3. Create simple working config")
    print("4. Test and start Nginx")
    
    if fix_nginx_issues():
        print("\n🎉 Nginx fixed successfully!")
        print("✅ Your backend is now accessible at: https://mininglifeserver.com")
        print("✅ API endpoint: https://mininglifeserver.com/scrape")
        print("\n📝 Update your frontend to use: https://mininglifeserver.com/scrape")
    else:
        print("\n❌ Failed to fix Nginx")
        print("🔧 Manual steps:")
        print("1. sudo systemctl status nginx")
        print("2. sudo journalctl -xeu nginx.service")
        print("3. sudo nginx -t")

if __name__ == "__main__":
    main()




