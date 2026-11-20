class DomainError(Exception):
    """Base for rule violations; the message is safe to show to the client."""


class Unauthorized(DomainError):
    pass


class Forbidden(DomainError):
    pass


class NotFound(DomainError):
    pass


class RateLimited(DomainError):
    pass


class AdmissionRefused(DomainError):
    """New-player admission is closed for now; `code` is `rate_limited` or `daily_full`."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class Conflict(DomainError):
    pass
