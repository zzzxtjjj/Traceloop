class TradeLoopError(Exception):
    """Base class for user-facing domain errors."""

    code = "TRADELOOP_ERROR"


class ProjectAccessDeniedError(TradeLoopError):
    code = "PROJECT_ACCESS_DENIED"


class CrossProjectReferenceError(TradeLoopError):
    code = "CROSS_PROJECT_REFERENCE"


class EvidenceRequiredError(TradeLoopError):
    code = "EVIDENCE_REQUIRED"


class InvalidStateTransitionError(TradeLoopError):
    code = "INVALID_STATE_TRANSITION"


class DuplicateImportError(TradeLoopError):
    code = "DUPLICATE_IMPORT"


class ModelNotConfiguredError(TradeLoopError):
    code = "MODEL_NOT_CONFIGURED"


class ModelTimeoutError(TradeLoopError):
    code = "MODEL_TIMEOUT"


class ModelOutputValidationError(TradeLoopError):
    code = "MODEL_BAD_JSON"


class RuleSourceError(TradeLoopError):
    code = "RULE_SOURCE_INVALID"

