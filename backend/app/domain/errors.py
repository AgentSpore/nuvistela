class DomainError(Exception):
    """Base for rule violations the API maps to HTTP statuses."""


class Unauthorized(DomainError):
    pass


class Forbidden(DomainError):
    pass


class NotFound(DomainError):
    pass
