"""The one error type the API raises. The handler turns it into
{"error": {"code", "message", "details"}} with its status; the message is
plain English for the UI and never carries a traceback."""


class ApiError(Exception):
    def __init__(self, status, code, message, details=None, headers=None):
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message
        self.details = details
        self.headers = headers or {}

    def body(self):
        err = {"code": self.code, "message": self.message}
        if self.details is not None:
            err["details"] = self.details
        return {"error": err}
