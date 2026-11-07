"""Concise typed errors for provider and persistence boundaries."""


class ParserError(Exception):
    pass


class ConfigurationError(ParserError):
    pass


class ProviderError(ParserError):
    pass


class ProviderAuthenticationError(ProviderError):
    pass


class ProviderPermissionError(ProviderError):
    pass


class ProviderRequestError(ProviderError):
    pass


class ProviderEmptyResponseError(ProviderError):
    pass


class ProviderSchemaError(ProviderError):
    pass


class UnsupportedPayloadError(ParserError):
    pass


class DatabaseApiError(ParserError):
    pass


class DatabaseApiUnavailableError(DatabaseApiError):
    pass


class DatabaseApiValidationError(DatabaseApiError):
    pass


class DatabaseApiConflictError(DatabaseApiError):
    pass


class DatabaseApiRequestError(DatabaseApiError):
    pass
