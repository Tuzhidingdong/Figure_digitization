class SfdError(Exception):
    """Base error for expected application failures."""


class InputContractError(SfdError):
    """An upstream input does not satisfy the minimum adapter contract."""


class StalePatchError(SfdError):
    """A review patch is based on an obsolete result."""


class OptionalDependencyError(SfdError):
    """A requested optional feature is unavailable because a dependency is missing."""
