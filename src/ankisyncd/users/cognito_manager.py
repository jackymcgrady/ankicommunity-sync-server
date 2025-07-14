import os
import boto3
from botocore.exceptions import ClientError, NoCredentialsError
from ankisyncd import logging
from ankisyncd.users.simple_manager import SimpleUserManager
from ankisyncd.exceptions import (
    CognitoInvalidCredentialsException,
    CognitoUserNotConfirmedException,
    CognitoPasswordResetRequiredException,
    CognitoPasswordChangeRequiredException
)

logger = logging.get_logger(__name__)


class CognitoUserManager(SimpleUserManager):
    """Authenticates users against AWS Cognito User Pool."""

    def __init__(self, collection_path=None, cognito_config=None):
        SimpleUserManager.__init__(self, collection_path)
        
        # Initialize Cognito configuration
        if cognito_config is None:
            cognito_config = {}
        
        self.region = cognito_config.get('region') or os.environ.get('AWS_COGNITO_REGION', 'ap-southeast-1')
        self.user_pool_id = cognito_config.get('user_pool_id') or os.environ.get('AWS_COGNITO_USER_POOL_ID')
        self.client_id = cognito_config.get('client_id') or os.environ.get('AWS_COGNITO_CLIENT_ID')
        
        if not self.user_pool_id:
            raise ValueError("AWS_COGNITO_USER_POOL_ID must be provided in config or environment")
        
        if not self.client_id:
            raise ValueError("AWS_COGNITO_CLIENT_ID must be provided in config or environment")
        
        # Initialize Cognito client
        try:
            self.cognito_client = boto3.client('cognito-idp', region_name=self.region)
            logger.info(f"Initialized Cognito client for region {self.region}, user pool {self.user_pool_id}")
        except NoCredentialsError:
            logger.error("AWS credentials not found. Please configure AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY")
            raise
        except Exception as e:
            logger.error(f"Failed to initialize Cognito client: {e}")
            raise

    def authenticate(self, username, password):
        """
        Authenticate user against AWS Cognito User Pool.
        Returns True if authentication succeeds, False otherwise.
        """
        try:
            # Use AdminInitiateAuth for server-side authentication
            response = self.cognito_client.admin_initiate_auth(
                UserPoolId=self.user_pool_id,
                ClientId=self.client_id,
                AuthFlow='ADMIN_NO_SRP_AUTH',
                AuthParameters={
                    'USERNAME': username,
                    'PASSWORD': password
                }
            )
            
            # Check if authentication was successful
            if response.get('AuthenticationResult'):
                logger.info(f"Cognito authentication successful for user: {username}")
                return True
            elif response.get('ChallengeName'):
                # Handle challenges (e.g., NEW_PASSWORD_REQUIRED, MFA)
                challenge = response.get('ChallengeName')
                logger.warning(f"Cognito authentication requires challenge '{challenge}' for user: {username}")
                # For sync server, we don't support interactive challenges
                return False
            else:
                logger.warning(f"Cognito authentication failed for user: {username} - unexpected response")
                return False
                
        except ClientError as e:
            error_code = e.response['Error']['Code']
            error_message = e.response['Error']['Message']
            
            # Map Cognito exceptions to sync-server error strings expected by Anki clients
            if error_code in ['NotAuthorizedException', 'UserNotFoundException']:
                logger.info(f"Cognito authentication failed for user: {username} - {error_code}")
                raise CognitoInvalidCredentialsException(f"Invalid credentials: {error_code}", error_code)
            elif error_code == 'UserNotConfirmedException':
                logger.warning(f"Cognito authentication failed for user: {username} - user not confirmed")
                raise CognitoUserNotConfirmedException(f"User account not confirmed: {error_message}", error_code)
            elif error_code == 'PasswordResetRequiredException':
                logger.warning(f"Cognito authentication failed for user: {username} - password reset required")
                raise CognitoPasswordResetRequiredException(f"Password reset required: {error_message}", error_code)
            elif error_code == 'PasswordChangeRequiredException':
                logger.warning(f"Cognito authentication failed for user: {username} - password change required")
                raise CognitoPasswordChangeRequiredException(f"Password change required: {error_message}", error_code)
            elif error_code == 'InvalidParameterException':
                logger.error(f"Cognito authentication error for user: {username} - invalid parameters: {error_message}")
                raise CognitoInvalidCredentialsException(f"Invalid parameters: {error_message}", error_code)
            elif error_code == 'TooManyRequestsException':
                logger.warning(f"Cognito authentication failed for user: {username} - too many requests")
                raise CognitoInvalidCredentialsException(f"Too many requests: {error_message}", error_code)
            else:
                logger.error(f"Cognito authentication error for user: {username} - {error_code}: {error_message}")
                raise CognitoInvalidCredentialsException(f"Authentication error: {error_code}", error_code)
            
        except Exception as e:
            logger.error(f"Unexpected error during Cognito authentication for user: {username} - {e}")
            return False

    def user_exists(self, username):
        """
        Check if user exists in Cognito User Pool.
        Note: This requires admin privileges to call AdminGetUser.
        """
        try:
            self.cognito_client.admin_get_user(
                UserPoolId=self.user_pool_id,
                Username=username
            )
            return True
        except ClientError as e:
            if e.response['Error']['Code'] == 'UserNotFoundException':
                return False
            else:
                logger.warning(f"Error checking if user exists: {e}")
                return False
        except Exception as e:
            logger.error(f"Unexpected error checking user existence: {e}")
            return False

    def user_list(self):
        """
        List all users in the Cognito User Pool.
        Note: This is not typically needed for sync server operation.
        """
        try:
            response = self.cognito_client.list_users(
                UserPoolId=self.user_pool_id,
                Limit=60  # Maximum allowed by AWS
            )
            users = []
            for user in response.get('Users', []):
                username = user.get('Username')
                if username:
                    users.append(username)
            
            # Handle pagination if needed
            while 'PaginationToken' in response:
                response = self.cognito_client.list_users(
                    UserPoolId=self.user_pool_id,
                    Limit=60,
                    PaginationToken=response['PaginationToken']
                )
                for user in response.get('Users', []):
                    username = user.get('Username')
                    if username:
                        users.append(username)
            
            return users
            
        except Exception as e:
            logger.error(f"Error listing users: {e}")
            return []

    def add_user(self, username, password):
        """
        Add user to Cognito User Pool.
        Note: This is typically done through the signup flow, not the sync server.
        """
        logger.warning("Adding users should be done through Cognito signup flow, not sync server")
        raise NotImplementedError("User creation should be done through Cognito signup interface")

    def del_user(self, username):
        """
        Delete user from Cognito User Pool.
        Note: This requires admin privileges.
        """
        logger.warning("Deleting users should be done through Cognito admin interface, not sync server")
        raise NotImplementedError("User deletion should be done through Cognito admin interface")

    def set_password_for_user(self, username, new_password):
        """
        Set password for user in Cognito User Pool.
        Note: This should be done through Cognito password reset flow.
        """
        logger.warning("Password changes should be done through Cognito password reset flow, not sync server")
        raise NotImplementedError("Password changes should be done through Cognito password reset flow") 