#!/usr/bin/env python3
"""
AWS Lambda function to handle Cognito post-confirmation trigger.
This function automatically provisions users in the sync server when they complete
Cognito registration.
"""

import json
import os
import boto3
import requests
from botocore.exceptions import ClientError

# Configuration - Set these environment variables in Lambda
SYNC_SERVER_URL = os.environ.get('SYNC_SERVER_URL', 'https://ankipi.com')
SYNC_SERVER_PROVISION_ENDPOINT = f"{SYNC_SERVER_URL}/provision-user"
SYNC_SERVER_API_KEY = os.environ.get('SYNC_SERVER_API_KEY', 'ankipi-provision-key-12345')

def lambda_handler(event, context):
    """
    Lambda handler for Cognito post-confirmation trigger.
    
    This function is called automatically when a user confirms their account
    in Cognito (after email verification or admin confirmation).
    """
    
    try:
        # Extract user information from the Cognito event
        user_pool_id = event['userPoolId']
        username = event['userName']
        user_attributes = event['request']['userAttributes']
        
        # Extract email (primary identifier for sync server)
        email = user_attributes.get('email', username)
        
        print(f"Processing post-confirmation for user: {username}, email: {email}")
        
        # Call sync server to provision the user
        provision_response = provision_user_on_sync_server(username, email, user_attributes)
        
        if provision_response['success']:
            print(f"Successfully provisioned user {username} on sync server")
        else:
            print(f"Failed to provision user {username}: {provision_response['error']}")
            # Don't fail the Cognito flow - user can still authenticate
        
        # Return the event unchanged (required for Cognito trigger)
        return event
        
    except Exception as e:
        print(f"Error in post-confirmation trigger: {str(e)}")
        # Don't fail the Cognito confirmation process
        return event

def provision_user_on_sync_server(username, email, user_attributes):
    """
    Call the sync server API to provision a new user.
    """
    try:
        # Prepare user data
        user_data = {
            'username': username,
            'email': email,
            'cognito_user_id': username,
            'user_attributes': user_attributes
        }
        
        headers = {
            'Content-Type': 'application/json'
        }
        
        # Add API key if configured
        if SYNC_SERVER_API_KEY:
            headers['X-API-Key'] = SYNC_SERVER_API_KEY
        
        # Make request to sync server
        response = requests.post(
            SYNC_SERVER_PROVISION_ENDPOINT,
            json=user_data,
            headers=headers,
            timeout=30
        )
        
        if response.status_code == 200:
            return {'success': True, 'data': response.json()}
        else:
            return {
                'success': False, 
                'error': f"HTTP {response.status_code}: {response.text}"
            }
            
    except requests.exceptions.RequestException as e:
        return {'success': False, 'error': f"Request failed: {str(e)}"}
    except Exception as e:
        return {'success': False, 'error': f"Unexpected error: {str(e)}"}

# For testing locally
if __name__ == "__main__":
    # Test event structure
    test_event = {
        "version": "1",
        "region": "ap-southeast-1",
        "userPoolId": "ap-southeast-1_O92soCD1L",
        "userName": "testuser@example.com",
        "callerContext": {
            "awsRequestId": "test-request-id"
        },
        "triggerSource": "PostConfirmation_ConfirmSignUp",
        "request": {
            "userAttributes": {
                "email": "testuser@example.com",
                "email_verified": "true",
                "sub": "test-sub-id"
            }
        },
        "response": {}
    }
    
    result = lambda_handler(test_event, None)
    print(f"Test result: {json.dumps(result, indent=2)}")