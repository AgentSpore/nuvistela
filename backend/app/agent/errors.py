"""Typed agent errors so callers (workers, adapters) can retry or degrade deliberately."""


class AgentError(Exception):
    """Base class of game master failures."""


class AgentConfigError(AgentError):
    """LLM settings are missing; fail at startup, not on the first event."""


class AgentBudgetExceededError(AgentError):
    """A request or token limit stopped the run; do not retry the same event blindly."""


class AgentUnavailableError(AgentError):
    """The model timed out, was unreachable or returned unusable output; safe to retry later."""


class AgentBusyError(AgentError):
    """Another turn of the same family is running; the caller may retry shortly."""
