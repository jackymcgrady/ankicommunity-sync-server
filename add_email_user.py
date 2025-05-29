#!/usr/bin/env python3

import sqlite3
import hashlib

def hash_password(password):
    return hashlib.md5(password.encode('utf-8')).hexdigest()

# Connect to the database
conn = sqlite3.connect('./auth.db')
cursor = conn.cursor()

# Add user with email format for testing
email = 'test@example.com'
password = 'test123'
hashed_password = hash_password(password)

# Insert user (correct table name is 'auth')
cursor.execute('INSERT OR REPLACE INTO auth (username, hash) VALUES (?, ?)', (email, hashed_password))
conn.commit()
conn.close()

print(f'Added user: {email} with password: test123') 