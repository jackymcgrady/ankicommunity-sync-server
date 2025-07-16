from webob.exc import HTTPBadRequest as BadRequestException

# AWS Cognito Authentication Exceptions
class CognitoAuthenticationException(Exception):
    """Base exception for Cognito authentication errors."""
    def __init__(self, message, error_code=None):
        super().__init__(message)
        self.error_code = error_code

class CognitoInvalidCredentialsException(CognitoAuthenticationException):
    """User provided invalid credentials."""
    pass

class CognitoUserNotConfirmedException(CognitoAuthenticationException):
    """User account is not confirmed (email/phone verification required)."""
    pass

class CognitoPasswordResetRequiredException(CognitoAuthenticationException):
    """User needs to reset their password."""
    pass

class CognitoPasswordChangeRequiredException(CognitoAuthenticationException):
    """User needs to change their password."""
    pass
