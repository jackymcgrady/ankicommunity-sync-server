#!/usr/bin/env python3
"""
Simple HTTPS proxy for Anki Sync Server
Forwards HTTPS requests to HTTP backend
"""
import asyncio
import ssl
import os
import subprocess
from aiohttp import web, ClientSession
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class HTTPSProxy:
    def __init__(self, backend_host='localhost', backend_port=27702, https_port=27703):
        self.backend_host = backend_host
        self.backend_port = backend_port
        self.https_port = https_port
        
    async def proxy_handler(self, request):
        """Forward all requests to HTTP backend"""
        # Build backend URL
        backend_url = f"http://{self.backend_host}:{self.backend_port}{request.path_qs}"
        
        logger.info(f"Proxying {request.method} {request.path} -> {backend_url}")
        
        async with ClientSession() as session:
            # Forward headers (except host)
            headers = dict(request.headers)
            headers.pop('host', None)
            
            # Read request body
            body = await request.read()
            
            # Make request to backend
            async with session.request(
                method=request.method,
                url=backend_url,
                headers=headers,
                data=body
            ) as resp:
                # Read response
                response_body = await resp.read()
                
                # Create response with same status and headers
                response = web.Response(
                    body=response_body,
                    status=resp.status,
                    headers=resp.headers
                )
                return response

    def setup_ssl_cert(self, cert_path='./certs'):
        """Generate self-signed cert if none exists"""
        os.makedirs(cert_path, exist_ok=True)
        cert_file = os.path.join(cert_path, 'server.crt')
        key_file = os.path.join(cert_path, 'server.key')
        
        if not os.path.exists(cert_file) or not os.path.exists(key_file):
            logger.info("Generating self-signed SSL certificate...")
            subprocess.run([
                'openssl', 'req', '-x509', '-newkey', 'rsa:2048',
                '-keyout', key_file, '-out', cert_file,
                '-days', '365', '-nodes',
                '-subj', '/C=US/ST=State/L=City/O=Organization/CN=sync.ankipi.com'
            ], check=True)
            logger.info("SSL certificate generated")
        
        return cert_file, key_file

    async def start_server(self):
        """Start HTTPS server"""
        # Set client_max_size to 2GB to handle large Anki collections
        app = web.Application(client_max_size=2048*1024*1024)
        app.router.add_route('*', '/{path:.*}', self.proxy_handler)
        
        # Setup SSL
        cert_file, key_file = self.setup_ssl_cert()
        ssl_context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
        ssl_context.load_cert_chain(cert_file, key_file)
        
        # Start server
        runner = web.AppRunner(app)
        await runner.setup()
        
        site = web.TCPSite(runner, '0.0.0.0', self.https_port, ssl_context=ssl_context)
        await site.start()
        
        logger.info(f"HTTPS proxy listening on port {self.https_port}")
        logger.info(f"Forwarding to HTTP backend at {self.backend_host}:{self.backend_port}")

async def main():
    proxy = HTTPSProxy()
    await proxy.start_server()
    
    # Keep running
    try:
        await asyncio.Event().wait()
    except KeyboardInterrupt:
        logger.info("Shutting down HTTPS proxy")

if __name__ == '__main__':
    asyncio.run(main())