#!/usr/bin/env python3

import zstandard as zstd
import json
import requests

def test_zstd_client():
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

    print(f'Original JSON: {json_data}')
    print(f'Compressed size: {len(compressed_data)} bytes')
    print(f'Headers: {headers}')

    # Send request
    try:
        response = requests.post('http://127.0.0.1:27702/sync/hostKey', 
                               data=compressed_data, 
                               headers=headers)
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
        print(f'Request failed: {e}')

if __name__ == '__main__':
    test_zstd_client() 