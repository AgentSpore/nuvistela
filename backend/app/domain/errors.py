class DomainError(Exception):
    """Base for rule violations; the message is safe to show to the client."""


class Unauthorized(DomainError):
    pass


class Forbidden(DomainError):
    pass


class NotFound(DomainError):
    pass
