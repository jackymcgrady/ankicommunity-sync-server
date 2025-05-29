#!/usr/bin/env python3

import http.server
import socketserver
import json
import logging
from urllib.parse import urlparse, parse_qs

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class DebugSyncHandler(http.server.BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        logger.info(f"[DEBUG SERVER] {format % args}")

    def do_POST(self):
        """Handle POST requests to understand what Anki client sends/expects"""
        
        # Log request details
        logger.info(f"=== ANKI CLIENT REQUEST ===")
        logger.info(f"Path: {self.path}")
        logger.info(f"Headers: {dict(self.headers)}")
        
        # Read body
        content_length = int(self.headers.get('content-length', 0))
        if content_length > 0:
            body = self.rfile.read(content_length)
            logger.info(f"Body length: {len(body)}")
            logger.info(f"Body (first 100 bytes): {body[:100]}")
        else:
            body = b""
            logger.info(f"Empty body")
        
        # Parse anki-sync header
        anki_sync_header = self.headers.get('anki-sync', '')
        if anki_sync_header:
            try:
                sync_data = json.loads(anki_sync_header)
                logger.info(f"Anki-Sync header parsed: {sync_data}")
            except:
                logger.info(f"Anki-Sync header raw: {anki_sync_header}")
        
        # For hostKey requests, try different response strategies
        if '/hostKey' in self.path:
            self.handle_hostkey_request(body, anki_sync_header)
        else:
            # Generic response
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b"Not Found")
    
    def handle_hostkey_request(self, body, anki_sync_header):
        """Test different hostKey response strategies"""
        
        if len(body) == 0:
            logger.info(">>> EMPTY HOSTKEY REQUEST - Testing response strategies")
            
            # Strategy 1: HTTP 401 with WWW-Authenticate header
            self.send_response(401)
            self.send_header('WWW-Authenticate', 'Basic realm="Anki Sync"')
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            response = {"error": "Authentication required", "method": "Basic"}
            self.wfile.write(json.dumps(response).encode('utf-8'))
            
        else:
            logger.info(">>> HOSTKEY REQUEST WITH DATA")
            try:
                # Try to parse as JSON
                data = json.loads(body.decode('utf-8'))
                logger.info(f"Parsed JSON: {data}")
                
                # Simulate successful authentication
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                response = {"key": "debug_host_key_12345"}
                self.wfile.write(json.dumps(response).encode('utf-8'))
                
            except Exception as e:
                logger.info(f"Failed to parse body: {e}")
                self.send_response(400)
                self.end_headers()
                self.wfile.write(b"Bad Request")

def start_debug_server():
    PORT = 27704
    
    with socketserver.TCPServer(("", PORT), DebugSyncHandler) as httpd:
        logger.info(f"Debug Anki Sync Server running on port {PORT}")
        logger.info(f"Configure Anki to use: http://localhost:{PORT}")
        logger.info("This server will log all requests from Anki client...")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            logger.info("Shutting down debug server...")

if __name__ == "__main__":
    start_debug_server() 