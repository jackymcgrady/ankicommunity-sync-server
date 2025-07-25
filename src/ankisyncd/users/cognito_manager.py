import os
import json
import boto3
from botocore.exceptions import ClientError
from ankisyncd import logging
from ankisyncd.users.simple_manager import SimpleUserManager

logger = logging.get_logger(__name__)


class CognitoUserManager(SimpleUserManager):
    """Authenticates users against AWS Cognito User Pool."""

    def __init__(self, config):
        # Extract collection_path from config
        collection_path = config.get('data_root', '')
        SimpleUserManager.__init__(self, collection_path)
        
        # Configuration parameters from config dict
        self.user_pool_id = config.get('cognito_user_pool_id')
        self.client_id = config.get('cognito_client_id')
        self.client_secret = config.get('cognito_client_secret')
        self.region = config.get('cognito_region', 'us-east-1')
        
        # Validate required configuration
        if not self.user_pool_id:
            raise ValueError("cognito_user_pool_id is required")
        if not self.client_id:
            raise ValueError("cognito_client_id is required")
        
        # Initialize Cognito client
        self.cognito_client = boto3.client('cognito-idp', region_name=self.region)
        
        # Debug: Print actual configuration values
        print(f"DEBUG: CognitoUserManager initialized with:")
        print(f"  user_pool_id: {self.user_pool_id}")
        print(f"  client_id: {self.client_id}")
        print(f"  client_secret: {'***' if self.client_secret else 'None'}")
        print(f"  region: {self.region}")
        
        # Cache for storing user sessions to avoid repeated Cognito calls
        self.user_session_cache = {}
        
        # Cache for mapping email identifiers to actual usernames
        self.username_cache = {}
        
        logger.info(f"Initialized CognitoUserManager for user pool: {self.user_pool_id}")

    def authenticate(self, username, password):
        """
        Authenticate user against AWS Cognito User Pool.
        Returns True if authentication succeeds, False otherwise.
        """
        try:
            # Check if we have a cached valid session for this user
            if username in self.user_session_cache:
                cached_session = self.user_session_cache[username]
                if self._is_session_valid(cached_session):
                    logger.info(f"Using cached session for user: {username}")
                    # Ensure we have the username mapping cached
                    if username not in self.username_cache:
                        try:
                            user_info = self.cognito_client.get_user(
                                AccessToken=cached_session['access_token']
                            )
                            self.username_cache[username] = user_info['Username']
                        except ClientError:
                            self.username_cache[username] = username
                    return True
                else:
                    # Remove expired session from cache
                    del self.user_session_cache[username]
                    if username in self.username_cache:
                        del self.username_cache[username]

            # Authenticate with Cognito
            auth_params = {
                'USERNAME': username,
                'PASSWORD': password
            }
            
            # Add client secret to auth params if configured
            if self.client_secret:
                auth_params['SECRET_HASH'] = self._calculate_secret_hash(username)

            print(f"DEBUG: Attempting auth for user: {username}")
            print(f"DEBUG: Using user_pool_id: {self.user_pool_id}")
            print(f"DEBUG: Using client_id: {self.client_id}")
            print(f"DEBUG: Has client_secret: {bool(self.client_secret)}")

            try:
                # Try standard user-level auth first (requires fewer permissions)
                response = self.cognito_client.initiate_auth(
                    ClientId=self.client_id,
                    AuthFlow='USER_PASSWORD_AUTH',
                    AuthParameters=auth_params
                )
                print(f"DEBUG: Successfully used USER_PASSWORD_AUTH flow")
            except Exception as e:
                print(f"DEBUG: USER_PASSWORD_AUTH failed: {e}")
                # Fallback to admin auth
                response = self.cognito_client.admin_initiate_auth(
                    UserPoolId=self.user_pool_id,
                    ClientId=self.client_id,
                    AuthFlow='ADMIN_NO_SRP_AUTH',
                    AuthParameters=auth_params
                )
                print(f"DEBUG: Fell back to ADMIN_NO_SRP_AUTH flow")

            # Handle successful authentication
            if 'AuthenticationResult' in response:
                auth_result = response['AuthenticationResult']
                
                # Cache the session for future use
                self.user_session_cache[username] = {
                    'access_token': auth_result['AccessToken'],
                    'refresh_token': auth_result.get('RefreshToken'),
                    'id_token': auth_result.get('IdToken'),
                    'expires_in': auth_result.get('ExpiresIn', 3600),
                    'token_type': auth_result.get('TokenType', 'Bearer')
                }
                
                # Get the actual username from Cognito user attributes
                try:
                    user_info = self.cognito_client.get_user(
                        AccessToken=auth_result['AccessToken']
                    )
                    # Extract username from user attributes
                    actual_username = user_info['Username']
                    self.username_cache[username] = actual_username
                    logger.info(f"Authentication succeeded for user: {username}, actual username: {actual_username}")
                except ClientError as e:
                    logger.warning(f"Could not retrieve username for {username}: {e}")
                    # Fallback to email identifier if we can't get the username
                    self.username_cache[username] = username
                
                # Create user directory using the actual username
                actual_user = self.username_cache.get(username, username)
                self._create_user_dir(actual_user)
                
                return True
            
            # Handle challenges (MFA, password change, etc.)
            elif 'ChallengeName' in response:
                challenge_name = response['ChallengeName']
                logger.warning(f"Authentication challenge for user {username}: {challenge_name}")
                # For now, we don't support challenges in the sync server
                return False
            
            logger.info(f"Authentication failed for user: {username} - Unknown response")
            return False
            
        except ClientError as e:
            error_code = e.response['Error']['Code']
            error_message = e.response['Error']['Message']
            
            if error_code == 'NotAuthorizedException':
                logger.info(f"Authentication failed for user: {username} - Invalid credentials")
            elif error_code == 'UserNotFoundException':
                logger.info(f"Authentication failed for user: {username} - User not found")
            elif error_code == 'UserNotConfirmedException':
                logger.info(f"Authentication failed for user: {username} - User not confirmed")
            elif error_code == 'PasswordResetRequiredException':
                logger.info(f"Authentication failed for user: {username} - Password reset required")
            elif error_code == 'TooManyRequestsException':
                logger.warning(f"Authentication failed for user: {username} - Too many requests")
            else:
                logger.error(f"Authentication error for user: {username} - {error_code}: {error_message}")
            
            return False
        
        except Exception as e:
            logger.error(f"Unexpected error during authentication for user: {username} - {str(e)}")
            return False

    def _calculate_secret_hash(self, username):
        """Calculate secret hash for Cognito client secret."""
        import hmac
        import hashlib
        import base64
        
        message = username + self.client_id
        secret_hash = hmac.new(
            self.client_secret.encode('utf-8'),
            message.encode('utf-8'),
            hashlib.sha256
        ).digest()
        
        return base64.b64encode(secret_hash).decode()

    def _is_session_valid(self, session):
        """Check if a cached session is still valid."""
        try:
            # For simplicity, we'll validate by making a simple call to Cognito
            # In a production system, you might want to check token expiration locally
            response = self.cognito_client.get_user(
                AccessToken=session['access_token']
            )
            return True
        except ClientError as e:
            if e.response['Error']['Code'] in ['NotAuthorizedException', 'TokenExpiredException']:
                return False
            # For other errors, assume session is invalid
            return False
        except Exception:
            return False

    def get_user_info(self, username):
        """Get user information from Cognito (optional utility method)."""
        if username not in self.user_session_cache:
            return None
        
        try:
            session = self.user_session_cache[username]
            response = self.cognito_client.get_user(
                AccessToken=session['access_token']
            )
            return response
        except ClientError as e:
            logger.error(f"Error getting user info for {username}: {e}")
            return None

    def refresh_user_session(self, username):
        """Refresh user session using refresh token."""
        if username not in self.user_session_cache:
            return False
        
        session = self.user_session_cache[username]
        refresh_token = session.get('refresh_token')
        
        if not refresh_token:
            return False
        
        try:
            auth_params = {
                'REFRESH_TOKEN': refresh_token
            }
            
            if self.client_secret:
                auth_params['SECRET_HASH'] = self._calculate_secret_hash(username)
            
            response = self.cognito_client.admin_initiate_auth(
                UserPoolId=self.user_pool_id,
                ClientId=self.client_id,
                AuthFlow='REFRESH_TOKEN_AUTH',
                AuthParameters=auth_params
            )
            
            if 'AuthenticationResult' in response:
                auth_result = response['AuthenticationResult']
                
                # Update cached session
                self.user_session_cache[username].update({
                    'access_token': auth_result['AccessToken'],
                    'id_token': auth_result.get('IdToken'),
                    'expires_in': auth_result.get('ExpiresIn', 3600),
                    'token_type': auth_result.get('TokenType', 'Bearer')
                })
                
                logger.info(f"Session refreshed for user: {username}")
                return True
            
            return False
            
        except ClientError as e:
            logger.error(f"Error refreshing session for {username}: {e}")
            # Remove invalid session from cache
            del self.user_session_cache[username]
            return False

    def clear_user_session(self, username):
        """Clear cached session for a user."""
        if username in self.user_session_cache:
            del self.user_session_cache[username]
            logger.info(f"Cleared cached session for user: {username}")

    def userdir(self, username):
        """
        Returns the directory name for the given user.
        For Cognito, we use the actual username from user attributes, not the email identifier.
        """
        # Return the cached actual username, or fallback to the email identifier
        return self.username_cache.get(username, username)