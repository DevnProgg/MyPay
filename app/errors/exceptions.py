class AppError(Exception):
    status_code = 500
    error = "Application error"

    def __init__(self, message, status_code=None):
        super().__init__(message)
        if status_code:
            self.status_code = status_code
        self.message = message


class ValidationError(AppError):
    status_code = 400
    error = "Validation error"

class PaymentNotFound(AppError):
    status_code = 404
    error = "Payment not found"

class Unauthorized(AppError):
    status_code = 401
    error = "Unauthorized"

class BadRequest(AppError):
    status_code = 400
    error = "Bad request"

class AccountNotFound(AppError):
    status_code = 404
    error = "Account not found"