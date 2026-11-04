from __future__ import annotations


class EngineError(ValueError):
    """A loan-term problem the lender can fix.

    ``code`` is stable and translated by the frontend (PRD section 9: the server returns a
    code, the app shows the message in the current language). ``params`` fill placeholders.
    """

    def __init__(self, code: str, **params: object) -> None:
        super().__init__(code)
        self.code = code
        self.params: dict[str, object] = params
