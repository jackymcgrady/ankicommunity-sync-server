#!/usr/bin/env python3

import zstandard as zstd
import json
import requests

# Test email authentication with zstd compression
credentials = {'email': 'test@example.com', 'password': 'test123'}
json_data = json.dumps(credentials).encode('utf-8')
ctx = zstd.ZstdCompressor()
compressed_data = ctx.compress(json_data)

headers = {
    'Content-Type': 'application/octet-stream',
    'anki-sync': json.dumps({'v': 11, 'k': '', 'c': 'test-client', 's': 'test-session'})
}

print('Testing email authentication with zstd compression...')
print(f'Sending: {credentials}')
response = requests.post('http://127.0.0.1:27702/sync/hostKey', 
                        data=compressed_data, 
                        headers=headers)
print(f'Response status: {response.status_code}')

if response.status_code == 200:
    resp_ctx = zstd.ZstdDecompressor()
    decompressed = resp_ctx.decompress(response.content)
    result = json.loads(decompressed)
    print(f'Success! Response: {result}')
else:
    print(f'Error: {response.text}') 