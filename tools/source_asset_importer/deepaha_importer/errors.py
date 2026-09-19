"""Safe errors: never echo credentials, complete requests or SQL parameters."""

class ImporterError(Exception):
    def __init__(self, code: str, message: str, status: int = 400, details=None):
        super().__init__(message)
        self.code, self.message, self.status = code, message, status
        self.details = details or []

    def as_dict(self):
        return {'error': {'code': self.code, 'message': self.message, 'details': self.details}}
