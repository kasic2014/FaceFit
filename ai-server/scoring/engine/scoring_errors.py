"""Stable error codes for the scoring package."""


class ScoringError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


PROFILE_INVALID = "SCORING_PROFILE_INVALID"
PROFILE_NOT_APPROVED = "SCORING_PROFILE_NOT_APPROVED"
EXPERIMENTAL_NOT_ENABLED = "EXPERIMENTAL_SCORING_NOT_EXPLICITLY_ENABLED"
UNSUPPORTED_METRIC = "UNSUPPORTED_METRIC"
