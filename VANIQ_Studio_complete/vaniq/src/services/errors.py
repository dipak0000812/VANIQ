class ServiceError(Exception):
    """Business-rule failure with an HTTP-friendly status and stable machine code."""

    def __init__(self, message: str, code: str = "error", status: int = 400):
        super().__init__(message)
        self.message, self.code, self.status = message, code, status
