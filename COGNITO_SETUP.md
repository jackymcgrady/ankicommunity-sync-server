# AWS Cognito Authentication Setup

This guide explains how to configure the Anki Sync Server to use AWS Cognito for user authentication instead of the local SQLite database.

## Overview

The Cognito integration allows you to:
- Use AWS Cognito User Pools for user authentication
- Have users sign up at your custom domain (e.g., signup.ankipi.com)
- Authenticate via the sync server (e.g., sync.ankipi.com)
- Support email/phone verification during signup
- Leverage AWS security features and user management

## Prerequisites

1. AWS Account with Cognito access
2. Existing Anki Sync Server installation
3. boto3 Python package installed

## Setup Steps

### 1. Install Dependencies

```bash
pip install boto3
```

### 2. Create AWS Cognito User Pool

1. Go to AWS Console → Cognito → User Pools
2. Create a new User Pool with these settings:
   - **Sign-in options**: Username, Email, Phone number (choose what you prefer)
   - **Password policy**: Configure as needed
   - **MFA**: Optional (recommended for security)
   - **User verification**: Email or SMS verification
   - **Attributes**: Require email as minimum

3. Configure App Client:
   - Create an app client for your sync server
   - **App client settings**:
     - Enable "ADMIN_NO_SRP_AUTH" auth flow
     - Generate client secret (recommended)
   - Note down:
     - User Pool ID (e.g., us-east-1_XXXXXXXXX)
     - App Client ID
     - App Client Secret

### 3. Configure Sync Server

#### Option A: Configuration File

Copy the example configuration:
```bash
cp src/ankisyncd.cognito.conf src/ankisyncd.conf
```

Edit the configuration file and update with your actual values:
```ini
[sync_app]
user_manager = ankisyncd.users.cognito_manager.CognitoUserManager
cognito_user_pool_id = your-actual-user-pool-id
cognito_client_id = your-actual-client-id
cognito_client_secret = your-actual-client-secret
cognito_region = your-aws-region
```

#### Option B: Environment Variables

Copy the example environment file:
```bash
cp env.cognito.example .env
```

Edit `.env` and update with your actual values:
```env
ANKISYNCD_USER_MANAGER=ankisyncd.users.cognito_manager.CognitoUserManager
ANKISYNCD_COGNITO_USER_POOL_ID=your-actual-user-pool-id
ANKISYNCD_COGNITO_CLIENT_ID=your-actual-client-id
ANKISYNCD_COGNITO_CLIENT_SECRET=your-actual-client-secret
ANKISYNCD_COGNITO_REGION=your-aws-region
```

### 4. AWS Credentials Setup

The sync server needs AWS credentials to access Cognito. Choose one method:

#### Option A: IAM Role (Recommended for EC2)
If running on EC2, attach an IAM role with the following policy:

```json
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Action": [
                "cognito-idp:AdminInitiateAuth",
                "cognito-idp:GetUser",
                "cognito-idp:AdminGetUser"
            ],
            "Resource": "arn:aws:cognito-idp:REGION:ACCOUNT-ID:userpool/USER-POOL-ID"
        }
    ]
}
```

#### Option B: Access Keys
Set environment variables:
```bash
export AWS_ACCESS_KEY_ID=your-access-key
export AWS_SECRET_ACCESS_KEY=your-secret-key
export AWS_DEFAULT_REGION=us-east-1
```

### 5. User Signup Flow

#### Set up signup.ankipi.com
Create a web application for user registration that:
1. Collects user information (username, email, password)
2. Calls Cognito CreateUser API
3. Handles email/phone verification
4. Provides users with their final username and password

#### Example signup flow:
1. User visits signup.ankipi.com
2. User fills registration form
3. System creates user in Cognito
4. User receives verification email/SMS
5. User confirms account
6. User gets username and password to use in Anki client

### 6. Client Configuration

Users configure their Anki clients to:
1. Use custom sync server: `https://sync.ankipi.com`
2. Login with username and password from signup process

## Authentication Flow

1. User opens Anki client and attempts to sync
2. Client sends username/password to sync server
3. Sync server authenticates with Cognito using `AdminInitiateAuth`
4. If successful, server creates session and returns session key
5. Session is cached for performance
6. Subsequent requests use session key

## Security Features

- **Session caching**: Reduces Cognito API calls
- **Token refresh**: Automatic refresh of expired tokens
- **Error handling**: Proper handling of various auth errors
- **MFA support**: Can be configured in Cognito User Pool

## Troubleshooting

### Common Issues

1. **Authentication fails**: Check User Pool ID and Client ID
2. **Access denied**: Verify IAM permissions
3. **User not found**: Ensure user exists in Cognito
4. **Session invalid**: Check token expiration and refresh logic

### Debug Logging

Enable debug logging in the sync server to see authentication details:
```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

### Test Authentication

You can test the authentication manually:

```python
import boto3

client = boto3.client('cognito-idp', region_name='us-east-1')

response = client.admin_initiate_auth(
    UserPoolId='us-east-1_XXXXXXXXX',
    ClientId='your-client-id',
    AuthFlow='ADMIN_NO_SRP_AUTH',
    AuthParameters={
        'USERNAME': 'testuser',
        'PASSWORD': 'testpassword'
    }
)

print(response)
```

## Migration from SQLite

If you're migrating from SQLite authentication:

1. Export existing users from SQLite database
2. Create corresponding users in Cognito
3. Update configuration to use Cognito
4. Test authentication
5. Remove old auth.db file

## Performance Considerations

- Session caching reduces API calls
- Consider implementing connection pooling for high-traffic scenarios
- Monitor Cognito API limits and costs

## Cost Optimization

- Use Cognito's free tier (50,000 MAUs)
- Implement session caching to reduce API calls
- Consider regional deployment to reduce latency

## Backup and Recovery

- User data is stored in Cognito (managed by AWS)
- Collection data remains in local files
- Regular backups of collection data still recommended