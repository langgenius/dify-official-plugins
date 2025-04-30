class LinearApiException(Exception):
    """Base exception for all Linear API errors"""
    def __init__(self, errors):
        self.errors = errors
        message = self._format_error_message(errors)
        super().__init__(message)
    
    def _format_error_message(self, errors):
        if isinstance(errors, list):
            # Format GraphQL errors
            messages = []
            for error in errors:
                if isinstance(error, dict):
                    messages.append(error.get('message', str(error)))
                else:
                    messages.append(str(error))
            return "; ".join(messages)
        else:
            # Single error message
            return str(errors)


class LinearAuthenticationException(LinearApiException):
    """Exception raised for authentication errors"""
    pass


class LinearRateLimitException(LinearApiException):
    """Exception raised when the API rate limit is exceeded"""
    pass


class LinearResourceNotFoundException(LinearApiException):
    """Exception raised when a requested resource is not found"""
    pass


class LinearValidationException(LinearApiException):
    """Exception raised for input validation errors"""
    pass


class LinearNetworkException(Exception):
    """Exception raised for network-related errors"""
    pass


# Legacy exception for backwards compatibility
class LinearQueryException(LinearApiException):
    """Legacy exception class for backwards compatibility"""
    pass