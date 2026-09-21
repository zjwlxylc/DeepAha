class DomainError(Exception):
    def __init__(self, message: str, status: int = 400, code: str = 'INVALID_REQUEST'):
        super().__init__(message)
        self.message, self.status, self.code = message, status, code


def require(condition, message, status=400, code='INVALID_REQUEST'):
    if not condition:
        raise DomainError(message, status, code)
