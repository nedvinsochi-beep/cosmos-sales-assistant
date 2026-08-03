class BitrixError(RuntimeError):
    """Base Bitrix client error."""


class UnsafeMethodError(BitrixError):
    """Raised before any request when a method is not explicitly read-only."""


class BitrixResponseError(BitrixError):
    """Raised when Bitrix returns an error response."""
