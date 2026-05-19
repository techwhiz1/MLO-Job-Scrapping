#!/usr/bin/env python3
"""
HTTPS Proxy Server for Backend
This creates an HTTPS proxy that forwards requests to your HTTP backend
"""

import asyncio
import aiohttp
from aiohttp import web
import ssl
import json
from urllib.parse import urljoin

# Your backend URL
BACKEND_URL = "http://localhost:8888"

async def proxy_handler(request):
    """Handle proxy requests"""
    try:
        # Get the path from the request
        path = request.path
        if path == '/':
            path = '/'
        
        # Construct backend URL
        backend_url = f"{BACKEND_URL}{path}"
        
        # Get request data
        data = None
        if request.method in ['POST', 'PUT', 'PATCH']:
            data = await request.read()
        
        # Get headers (remove host header to avoid conflicts)
        headers = dict(request.headers)
        headers.pop('Host', None)
        headers.pop('host', None)
        
        # Make request to backend
        async with aiohttp.ClientSession() as session:
            async with session.request(
                method=request.method,
                url=backend_url,
                headers=headers,
                data=data,
                timeout=aiohttp.ClientTimeout(total=30)
            ) as response:
                
                # Get response data
                response_data = await response.read()
                
                # Create response with CORS headers
                return web.Response(
                    body=response_data,
                    status=response.status,
                    headers={
                        'Content-Type': response.headers.get('Content-Type', 'application/json'),
                        'Access-Control-Allow-Origin': '*',
                        'Access-Control-Allow-Methods': 'GET, POST, PUT, DELETE, OPTIONS',
                        'Access-Control-Allow-Headers': 'DNT,User-Agent,X-Requested-With,If-Modified-Since,Cache-Control,Content-Type,Range',
                        'Access-Control-Allow-Credentials': 'true'
                    }
                )
    
    except Exception as e:
        return web.Response(
            text=json.dumps({"error": str(e)}),
            status=500,
            headers={
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*'
            }
        )

async def options_handler(request):
    """Handle OPTIONS requests for CORS"""
    return web.Response(
        headers={
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Methods': 'GET, POST, PUT, DELETE, OPTIONS',
            'Access-Control-Allow-Headers': 'DNT,User-Agent,X-Requested-With,If-Modified-Since,Cache-Control,Content-Type,Range',
            'Access-Control-Allow-Credentials': 'true',
            'Access-Control-Max-Age': '1728000'
        }
    )

def create_ssl_context():
    """Create SSL context for HTTPS"""
    ssl_context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
    
    # For development, you can use self-signed certificates
    # In production, use proper certificates
    try:
        ssl_context.load_cert_chain('/etc/ssl/certs/ssl-cert-snakeoil.pem', '/etc/ssl/private/ssl-cert-snakeoil.key')
        print("✅ Using system SSL certificates")
    except:
        print("⚠️ SSL certificates not found, using self-signed")
        # Create self-signed certificate (development only)
        import subprocess
        subprocess.run([
            'openssl', 'req', '-x509', '-newkey', 'rsa:4096', '-keyout', 'key.pem', 
            '-out', 'cert.pem', '-days', '365', '-nodes', '-subj', '/CN=vps-fc1d7078.vps.ovh.us'
        ], check=True)
        ssl_context.load_cert_chain('cert.pem', 'key.pem')
    
    return ssl_context

async def main():
    """Main application"""
    app = web.Application()
    
    # Add routes
    app.router.add_route('*', '/{path:.*}', proxy_handler)
    app.router.add_route('OPTIONS', '/{path:.*}', options_handler)
    
    # Create SSL context
    ssl_context = create_ssl_context()
    
    # Start server
    print("🚀 Starting HTTPS Proxy Server...")
    print(f"📡 Backend URL: {BACKEND_URL}")
    print(f"🌐 Proxy URL: https://vps-fc1d7078.vps.ovh.us:8443")
    
    runner = web.AppRunner(app)
    await runner.setup()
    
    site = web.TCPSite(runner, '0.0.0.0', 8443, ssl_context=ssl_context)
    await site.start()
    
    print("✅ HTTPS Proxy Server is running!")
    print("🔗 Use this URL in your frontend: https://vps-fc1d7078.vps.ovh.us:8443")
    
    # Keep running
    try:
        await asyncio.Future()  # Run forever
    except KeyboardInterrupt:
        print("\n🛑 Shutting down proxy server...")
    finally:
        await runner.cleanup()

if __name__ == "__main__":
    asyncio.run(main())





