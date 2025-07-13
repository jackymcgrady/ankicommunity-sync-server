#!/usr/bin/env python3
import http.server
import socketserver
import os
import sys

class ChallengeHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory='./certbot/www', **kwargs)
    
    def do_GET(self):
        print(f"Challenge request: {self.path}")
        return super().do_GET()

if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 80
    
    # Create the challenge directory if it doesn't exist
    os.makedirs('./certbot/www', exist_ok=True)
    
    with socketserver.TCPServer(("", port), ChallengeHandler) as httpd:
        print(f"Serving HTTP challenge on port {port}")
        print(f"Challenge directory: ./certbot/www")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nShutting down challenge server...") 