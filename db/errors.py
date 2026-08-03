"""Errors raised by the stable stored-message boundary."""


class StoredMessageError(ValueError):
    """Base error for stored-message conversion and integrity failures."""


class UnsupportedStoredMessageError(StoredMessageError):
    """Raised when a framework message cannot enter the stable protocol."""


class MessageIntegrityError(StoredMessageError):
    """Raised when database columns and payload data disagree."""
