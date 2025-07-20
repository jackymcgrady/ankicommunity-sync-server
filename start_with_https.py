#!/usr/bin/env python3
"""
Start both Anki sync server and HTTPS proxy
"""
import subprocess
import sys
import time
import signal
import os

def start_sync_server():
    """Start the main sync server with Cognito authentication"""
    env = os.environ.copy()
    env['ANKISYNCD_CONFIG_PATH'] = '/app/src/ankisyncd-cognito.conf'
    return subprocess.Popen([
        sys.executable, '-m', 'ankisyncd'
    ], cwd='/app/src', env=env)

def start_https_proxy():
    """Start the HTTPS proxy"""
    return subprocess.Popen([
        sys.executable, '/app/src/https_proxy.py'
    ], cwd='/app')

def main():
    # Install openssl if not present
    try:
        subprocess.run(['which', 'openssl'], check=True, capture_output=True)
    except subprocess.CalledProcessError:
        print("Installing openssl...")
        subprocess.run(['apt-get', 'update'], check=True)
        subprocess.run(['apt-get', 'install', '-y', 'openssl'], check=True)
    
    print("Starting Anki Sync Server with HTTPS proxy...")
    
    # Start both processes
    sync_server = start_sync_server()
    time.sleep(2)  # Give sync server time to start
    https_proxy = start_https_proxy()
    
    def signal_handler(signum, frame):
        print("\nShutting down...")
        https_proxy.terminate()
        sync_server.terminate()
        https_proxy.wait()
        sync_server.wait()
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    print("✅ Anki Sync Server running on HTTP port 27702")
    print("✅ HTTPS Proxy running on port 27703")
    print("✅ Access via: https://localhost:27703")
    
    # Wait for processes
    try:
        while True:
            if sync_server.poll() is not None:
                print("❌ Sync server died, exiting")
                break
            if https_proxy.poll() is not None:
                print("❌ HTTPS proxy died, exiting")
                break
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    
    # Cleanup
    signal_handler(None, None)

if __name__ == '__main__':
    main()