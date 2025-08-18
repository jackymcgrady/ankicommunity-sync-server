import os
import json
import jwt
import boto3
from botocore.exceptions import ClientError
from ankisyncd import logging
from ankisyncd.users.simple_manager import SimpleUserManager
from .db_manager import DatabaseManager

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
        
        # Cache for mapping usernames to UUIDs
        self.uuid_cache = {}
        
        # Initialize database manager
        try:
            self.db_manager = DatabaseManager()
        except Exception as e:
            logger.warning(f"Failed to initialize database manager: {e}")
            self.db_manager = None
        
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
                # For refresh, use the actual Cognito username, not the email identifier
                actual_username = self.username_cache.get(username, username)
                auth_params['SECRET_HASH'] = self._calculate_secret_hash(actual_username)

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
                
                # Extract UUID and username from tokens
                try:
                    user_info = self.cognito_client.get_user(
                        AccessToken=auth_result['AccessToken']
                    )
                    actual_username = user_info['Username']
                    self.username_cache[username] = actual_username
                    
                    # Extract UUID from ID token
                    id_token = auth_result.get('IdToken')
                    user_uuid = None
                    if id_token:
                        try:
                            # Decode without verification for now (tokens are from trusted source)
                            decoded_token = jwt.decode(id_token, options={"verify_signature": False})
                            user_uuid = decoded_token.get('sub')
                            if user_uuid:
                                self.uuid_cache[username] = user_uuid
                                logger.info(f"Extracted UUID {user_uuid} for user {username}")
                        except Exception as e:
                            logger.warning(f"Failed to decode ID token for {username}: {e}")
                    
                    # Note: User profile creation is now handled by the webapp during signup
                    
                    logger.info(f"Authentication succeeded for user: {username}, actual username: {actual_username}, UUID: {user_uuid}")
                    
                except ClientError as e:
                    logger.warning(f"Could not retrieve user info for {username}: {e}")
                    self.username_cache[username] = username
                
                # Note: User directory creation is now handled by the webapp during signup
                # Directory should already exist at ./efs/collections/{uuid}/
                
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
        
        result = base64.b64encode(secret_hash).decode()
        logger.debug(f"SECRET_HASH calculation: username='{username}', client_id='{self.client_id}', hash='{result}'")
        return result

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
                # For refresh, use the actual Cognito username, not the email identifier
                actual_username = self.username_cache.get(username, username)
                auth_params['SECRET_HASH'] = self._calculate_secret_hash(actual_username)
            
            # Use same API as authentication for consistency
            try:
                response = self.cognito_client.initiate_auth(
                    ClientId=self.client_id,
                    AuthFlow='REFRESH_TOKEN_AUTH',
                    AuthParameters=auth_params
                )
            except Exception as e:
                # Fallback to admin auth if user-level fails
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

    def refresh_user_session_with_token(self, username, refresh_token, actual_username=None):
        """Refresh user session using provided refresh token (for persistent storage)."""
        if not refresh_token:
            return False
        
        # Try refresh with different username formats for SecretHash
        usernames_to_try = []
        if actual_username:
            usernames_to_try.append(actual_username)
        if username in self.username_cache:
            usernames_to_try.append(self.username_cache[username])
        usernames_to_try.append(username)  # Original as fallback
        
        # Remove duplicates while preserving order
        usernames_to_try = list(dict.fromkeys(usernames_to_try))
        
        last_error = None
        for username_for_hash in usernames_to_try:
            try:
                auth_params = {
                    'REFRESH_TOKEN': refresh_token
                }
                
                if self.client_secret:
                    auth_params['SECRET_HASH'] = self._calculate_secret_hash(username_for_hash)
                
                # Use same API as authentication for consistency
                try:
                    response = self.cognito_client.initiate_auth(
                        ClientId=self.client_id,
                        AuthFlow='REFRESH_TOKEN_AUTH',
                        AuthParameters=auth_params
                    )
                except Exception as e:
                    # Fallback to admin auth if user-level fails
                    response = self.cognito_client.admin_initiate_auth(
                        UserPoolId=self.user_pool_id,
                        ClientId=self.client_id,
                        AuthFlow='REFRESH_TOKEN_AUTH',
                        AuthParameters=auth_params
                    )
                
                if 'AuthenticationResult' in response:
                    auth_result = response['AuthenticationResult']
                    
                    # Create or update cached session
                    self.user_session_cache[username] = {
                        'access_token': auth_result['AccessToken'],
                        'refresh_token': refresh_token,  # Keep the original refresh token
                        'id_token': auth_result.get('IdToken'),
                        'expires_in': auth_result.get('ExpiresIn', 3600),
                        'token_type': auth_result.get('TokenType', 'Bearer')
                    }
                    
                    # Update username cache if we used the actual username for hash
                    if username_for_hash != username:
                        self.username_cache[username] = username_for_hash
                        logger.info(f"Username cache updated during refresh: {username} -> {username_for_hash}")
                    
                    logger.info(f"Session refreshed from stored token for user: {username} using username: {username_for_hash}")
                    return True
                    
            except ClientError as e:
                last_error = e
                logger.debug(f"Refresh failed with username '{username_for_hash}': {e}")
                continue  # Try next username format
                
        # All username formats failed
        logger.error(f"Error refreshing session with stored token for {username}: {last_error}")
        # Remove from cache if it exists
        if username in self.user_session_cache:
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
        For Cognito, we use the UUID if available, otherwise the actual username.
        """
        # First try cached UUID
        if username in self.uuid_cache:
            return self.uuid_cache[username]
        
        # If not cached, try to get from database using actual username
        if self.db_manager:
            try:
                actual_username = self.username_cache.get(username, username)
                profile = self.db_manager.get_user_profile_by_name(actual_username)
                if profile and profile.get('uuid'):
                    # Cache the UUID for future use
                    self.uuid_cache[username] = str(profile['uuid'])
                    logger.info(f"Found UUID from database for {username}: {profile['uuid']}")
                    return str(profile['uuid'])
            except Exception as e:
                logger.warning(f"Could not get UUID from database for {username}: {e}")
        
        # Fallback to actual username, or email identifier
        return self.username_cache.get(username, username)