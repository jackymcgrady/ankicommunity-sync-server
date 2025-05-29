#!/usr/bin/env python3

import zstandard as zstd
import json
import requests
import urllib3

# Disable SSL warnings for testing
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

def test_https_client():
    # Create the exact request the Anki client should send
    credentials = {'u': 'test', 'p': 'test123'}
    json_data = json.dumps(credentials).encode('utf-8')

    # Compress with zstd like the client does
    ctx = zstd.ZstdCompressor()
    compressed_data = ctx.compress(json_data)

    headers = {
        'Content-Type': 'application/octet-stream',
        'anki-sync': json.dumps({'v': 11, 'k': '', 'c': 'test-client', 's': 'test-session'})
    }

    print(f'Testing HTTPS connection...')
    print(f'Original JSON: {json_data}')
    print(f'Compressed size: {len(compressed_data)} bytes')
    print(f'Headers: {headers}')

    # Path to mkcert CA certificate
    ca_cert_path = "/Users/huyuping/Library/Application Support/mkcert/rootCA.pem"

    # Send request to HTTPS proxy
    try:
        response = requests.post('https://localhost:27703/sync/hostKey', 
                               data=compressed_data, 
                               headers=headers,
                               verify=ca_cert_path)  # Use mkcert CA certificate
        print(f'Response status: {response.status_code}')
        if response.status_code == 200:
            # Decompress response
            resp_ctx = zstd.ZstdDecompressor()
            decompressed = resp_ctx.decompress(response.content)
            result = json.loads(decompressed)
            print(f'Success! Host key: {result}')
        else:
            print(f'Error: {response.text}')
    except Exception as e:
        print(f'HTTPS request failed: {e}')
        
    # Also test with system default (should work since mkcert installed the CA)
    print("\nTesting with system default CA...")
    try:
        response = requests.post('https://localhost:27703/sync/hostKey', 
                               data=compressed_data, 
                               headers=headers,
                               verify=True)  # System default CA bundle
        print(f'Response status: {response.status_code}')
        if response.status_code == 200:
            # Decompress response
            resp_ctx = zstd.ZstdDecompressor()
            decompressed = resp_ctx.decompress(response.content)
            result = json.loads(decompressed)
            print(f'Success with system CA! Host key: {result}')
        else:
            print(f'Error: {response.text}')
    except Exception as e:
        print(f'System CA test failed: {e}')

if __name__ == '__main__':
    test_https_client() 