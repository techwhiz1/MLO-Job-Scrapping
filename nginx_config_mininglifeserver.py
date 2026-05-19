#!/usr/bin/env python3
"""
Create Nginx Configuration for mininglifeserver.com
Forwards HTTPS requests to port 8888
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

def create_nginx_config():
    """Create Nginx configuration for mininglifeserver.com"""
    config_content = """
# HTTP to HTTPS redirect
server {
    listen 80;
    server_name mininglifeserver.com;
    return 301 https://$server_name$request_uri;
}

# HTTPS server - forwards to port 8888
server {
    listen 443 ssl http2;
    server_name mininglifeserver.com;

    # SSL certificates
    ssl_certificate /etc/letsencrypt/live/mininglifeserver.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/mininglifeserver.com/privkey.pem;
    
    # SSL configuration
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers ECDHE-RSA-AES256-GCM-SHA512:DHE-RSA-AES256-GCM-SHA512:ECDHE-RSA-AES256-GCM-SHA384:DHE-RSA-AES256-GCM-SHA384;
    ssl_prefer_server_ciphers off;
    ssl_session_cache shared:SSL:10m;
    ssl_session_timeout 10m;

    # CORS headers for all responses
    add_header 'Access-Control-Allow-Origin' '*' always;
    add_header 'Access-Control-Allow-Methods' 'GET, POST, PUT, DELETE, OPTIONS' always;
    add_header 'Access-Control-Allow-Headers' 'DNT,User-Agent,X-Requested-With,If-Modified-Since,Cache-Control,Content-Type,Range' always;
    add_header 'Access-Control-Allow-Credentials' 'true' always;

    # Handle preflight OPTIONS requests
    location / {
        if ($request_method = 'OPTIONS') {
            add_header 'Access-Control-Allow-Origin' '*' always;
            add_header 'Access-Control-Allow-Methods' 'GET, POST, PUT, DELETE, OPTIONS' always;
            add_header 'Access-Control-Allow-Headers' 'DNT,User-Agent,X-Requested-With,If-Modified-Since,Cache-Control,Content-Type,Range' always;
            add_header 'Access-Control-Max-Age' 1728000;
            add_header 'Content-Type' 'text/plain; charset=utf-8';
            add_header 'Content-Length' 0;
            return 204;
        }

        # Forward all requests to port 8888
        proxy_pass http://localhost:8888;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        
        # Proxy timeouts
        proxy_connect_timeout 60s;
        proxy_send_timeout 60s;
        proxy_read_timeout 60s;
        
        # Buffer settings
        proxy_buffering on;
        proxy_buffer_size 4k;
        proxy_buffers 8 4k;
    }
}
"""
    
    # Create config file in temp location first, then move with sudo
    temp_config_file = "/tmp/mininglifeserver_nginx.conf"
    config_file = "/etc/nginx/sites-available/mininglifeserver.com"
    
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

def setup_nginx():
    """Set up Nginx with the new configuration"""
    print("🌐 Setting up Nginx...")
    
    # 1. Stop Nginx
    run_command("sudo systemctl stop nginx", "Stopping Nginx")
    
    # 2. Remove any existing configs
    run_command("sudo rm -f /etc/nginx/sites-enabled/mininglifeserver.com", "Removing existing config")
    run_command("sudo rm -f /etc/nginx/sites-enabled/default", "Removing default site")
    
    # 3. Create new config
    if not create_nginx_config():
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
    
    print("✅ Nginx setup complete!")
    return True

def test_endpoint():
    """Test the endpoint"""
    print("🧪 Testing endpoint...")
    
    test_commands = [
        "curl -I https://mininglifeserver.com/",
        "curl https://mininglifeserver.com/",
        "curl -I https://mininglifeserver.com/cors-test",
        "curl https://mininglifeserver.com/cors-test"
    ]
    
    for cmd in test_commands:
        if run_command(cmd, f"Testing: {cmd}"):
            print(f"✅ Endpoint working: {cmd}")
        else:
            print(f"❌ Endpoint failed: {cmd}")
    
    return True

def main():
    """Main setup process"""
    print("🔧 Nginx Configuration for mininglifeserver.com")
    print("=" * 60)
    
    print("📋 This will:")
    print("1. Create Nginx config that forwards HTTPS to port 8888")
    print("2. Set up SSL with Let's Encrypt certificates")
    print("3. Configure CORS headers")
    print("4. Test the endpoint")
    
    if setup_nginx():
        print("\n🎉 Nginx configuration complete!")
        print("✅ HTTPS requests to mininglifeserver.com will be forwarded to port 8888")
        print("✅ Your API will be accessible at: https://mininglifeserver.com/scrape")
        
        # Test the endpoint
        test_endpoint()
        
        print("\n📝 Update your frontend to use:")
        print("   https://mininglifeserver.com/scrape")
    else:
        print("\n❌ Failed to setup Nginx")
        print("🔧 Manual steps:")
        print("1. sudo systemctl status nginx")
        print("2. sudo journalctl -xeu nginx.service")
        print("3. sudo nginx -t")

if __name__ == "__main__":
    main()



