"""Concise typed errors for the optional Gemini boundary."""


class ParserError(Exception): pass


class ConfigurationError(ParserError): pass
class ProviderError(ParserError): pass
class ProviderAuthenticationError(ProviderError): pass
class ProviderPermissionError(ProviderError): pass
class ProviderRequestError(ProviderError): pass
class ProviderEmptyResponseError(ProviderError): pass
class ProviderSchemaError(ProviderError): pass
class UnsupportedPayloadError(ParserError): pass
