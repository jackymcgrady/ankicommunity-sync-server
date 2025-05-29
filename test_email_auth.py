#!/usr/bin/env python3

import zstandard as zstd
import json
import requests
import urllib3

# Disable SSL warnings for testing
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

def test_email_field():
    """Test authentication with email field instead of username field"""
    
    # Test 1: Traditional username field (should work)
    credentials = {'u': 'test', 'p': 'test123'}
    test_request("Traditional u/p fields", credentials)
    
    # Test 2: Modern username field (should work)
    credentials = {'username': 'test', 'password': 'test123'}
    test_request("Modern username/password fields", credentials)
    
    # Test 3: Email field (this might be what client is trying)
    credentials = {'email': 'test@example.com', 'password': 'test123'}
    test_request("Email/password fields", credentials)
    
    # Test 4: Empty request (discovery)
    test_request("Empty discovery request", {})

def test_request(test_name, credentials):
    print(f"\n=== {test_name} ===")
    
    json_data = json.dumps(credentials).encode('utf-8')
    ctx = zstd.ZstdCompressor()
    compressed_data = ctx.compress(json_data)

    headers = {
        'Content-Type': 'application/octet-stream',
        'anki-sync': json.dumps({'v': 11, 'k': '', 'c': 'test-client', 's': 'test-session'})
    }

    print(f'Sending: {credentials}')

    try:
        response = requests.post('https://localhost:27703/sync/hostKey', 
                               data=compressed_data, 
                               headers=headers,
                               verify=False)
        print(f'Response status: {response.status_code}')
        
        if response.status_code == 200:
            try:
                resp_ctx = zstd.ZstdDecompressor()
                decompressed = resp_ctx.decompress(response.content)
                result = json.loads(decompressed)
                print(f'Success! Response: {result}')
            except Exception as e:
                print(f'Could not decompress response: {e}')
                print(f'Raw response: {response.content}')
        else:
            print(f'Error: {response.text}')
    except Exception as e:
        print(f'Request failed: {e}')

if __name__ == '__main__':
    test_email_field() 