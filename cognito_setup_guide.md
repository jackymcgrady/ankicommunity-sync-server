# AWS Cognito User Provisioning Setup Guide

This guide explains how to set up automatic user provisioning when new users are added to AWS Cognito.

## Overview

When a user completes registration and email verification in AWS Cognito, the system will automatically:
1. Add the user to the sync server's auth database (if using SQLite fallback)
2. Create a collection folder named after the user's username

## Components

### 1. Lambda Function (`src/cognito_user_provisioner.py`)
- Handles Cognito post-confirmation triggers
- Calls the sync server's provisioning endpoint
- Automatically provisions users after they confirm their accounts

### 2. Sync Server Endpoint (`/provision-user`)
- Added to `src/ankisyncd/sync_app.py`
- Secured with API key authentication
- Creates user directories and adds users to auth database

## Setup Instructions

### Step 1: Deploy Lambda Function

1. **Create Lambda Function:**
   ```bash
   # Package the Lambda function
   cd src/
   zip cognito_provisioner.zip cognito_user_provisioner.py
   
   # Create Lambda function (replace ROLE_ARN with your Lambda execution role)
   aws lambda create-function \
     --function-name ankipi-cognito-provisioner \
     --runtime python3.9 \
     --role arn:aws:iam::YOUR_ACCOUNT:role/lambda-execution-role \
     --handler cognito_user_provisioner.lambda_handler \
     --zip-file fileb://cognito_provisioner.zip \
     --region ap-southeast-1
   ```

2. **Set Environment Variables:**
   ```bash
   aws lambda update-function-configuration \
     --function-name ankipi-cognito-provisioner \
     --environment Variables='{
       "SYNC_SERVER_URL":"https://ankipi.com",
       "SYNC_SERVER_API_KEY":"ankipi-provision-key-12345"
     }' \
     --region ap-southeast-1
   ```

3. **Add Lambda Layer for requests library:**
   ```bash
   # Create layer for requests library
   mkdir python
   pip install requests -t python/
   zip -r requests-layer.zip python/
   
   aws lambda publish-layer-version \
     --layer-name requests-layer \
     --zip-file fileb://requests-layer.zip \
     --compatible-runtimes python3.9 \
     --region ap-southeast-1
   
   # Add layer to function (replace LAYER_ARN with the output from above)
   aws lambda update-function-configuration \
     --function-name ankipi-cognito-provisioner \
     --layers LAYER_ARN \
     --region ap-southeast-1
   ```

### Step 2: Configure Cognito Trigger

1. **Add Post-Confirmation Trigger:**
   ```bash
   aws cognito-idp update-user-pool \
     --user-pool-id ap-southeast-1_O92soCD1L \
     --lambda-config PostConfirmation=arn:aws:lambda:ap-southeast-1:YOUR_ACCOUNT:function:ankipi-cognito-provisioner \
     --region ap-southeast-1
   ```

2. **Grant Cognito Permission to Invoke Lambda:**
   ```bash
   aws lambda add-permission \
     --function-name ankipi-cognito-provisioner \
     --statement-id cognito-trigger \
     --action lambda:InvokeFunction \
     --principal cognito-idp.amazonaws.com \
     --source-arn arn:aws:cognito-idp:ap-southeast-1:YOUR_ACCOUNT:userpool/ap-southeast-1_O92soCD1L \
     --region ap-southeast-1
   ```

### Step 3: Update Sync Server Configuration

The sync server configuration has been updated in `src/ankisyncd-cognito.conf`:

```ini
# User provisioning API key (for Cognito triggers)
provision_api_key = ankipi-provision-key-12345
```

**Important**: Change this API key to a secure random value in production!

### Step 4: Restart Sync Server

```bash
# Restart the sync server to load the new configuration
sudo systemctl restart ankisyncd
# or however you restart your sync server
```

## Testing

### Test the Provisioning Endpoint

```bash
# Test the provisioning endpoint directly
curl -X POST https://ankipi.com/provision-user \
  -H "Content-Type: application/json" \
  -H "X-API-Key: ankipi-provision-key-12345" \
  -d '{
    "username": "testuser@example.com",
    "email": "testuser@example.com",
    "cognito_user_id": "test-user-id",
    "user_attributes": {
      "email": "testuser@example.com",
      "email_verified": "true"
    }
  }'
```

Expected response:
```json
{
  "success": true,
  "message": "User testuser@example.com provisioned successfully",
  "user_directory": "/path/to/collections/testuser",
  "username": "testuser"
}
```

### Test Lambda Function Locally

```bash
cd src/
python cognito_user_provisioner.py
```

### Test Complete Flow

1. Register a new user in your Cognito User Pool
2. Complete email verification
3. Check sync server logs for provisioning messages
4. Verify user directory was created in `data/collections/`

## Security Considerations

1. **Change the API Key**: The default API key is for testing only
2. **Use HTTPS**: Ensure all communication uses HTTPS
3. **IAM Permissions**: Use least-privilege IAM roles for Lambda
4. **Monitoring**: Set up CloudWatch logs for Lambda function

## Troubleshooting

### Common Issues

1. **"API key required" error**: Check Lambda environment variables
2. **"Invalid API key" error**: Ensure API keys match in Lambda and sync server config
3. **Connection timeout**: Check network connectivity from Lambda to sync server
4. **User directory not created**: Check sync server logs and file permissions

### Logs

- **Lambda logs**: CloudWatch Logs group `/aws/lambda/ankipi-cognito-provisioner`
- **Sync server logs**: Check your sync server log files

### Manual User Provisioning

If needed, you can provision users manually:

```bash
curl -X POST https://ankipi.com/provision-user \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-api-key" \
  -d '{
    "username": "user@example.com",
    "email": "user@example.com"
  }'
```