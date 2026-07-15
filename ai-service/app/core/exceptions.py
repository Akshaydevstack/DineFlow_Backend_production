from fastapi import HTTPException, status

class AIServiceException(Exception):
    """Base exception for DineFlow AI Service."""
    def __init__(self, message: str, status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR):
        self.message = message
        self.status_code = status_code
        super().__init__(self.message)

class ResourceExhaustedException(AIServiceException):
    """Exception raised when Google Gemini API quota is exhausted."""
    def __init__(self, message: str = "AI is busy, please try again in a few minutes"):
        super().__init__(message, status_code=status.HTTP_429_TOO_MANY_REQUESTS)
