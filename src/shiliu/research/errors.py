from __future__ import annotations


class ResearchError(RuntimeError):
    code = "research_error"
    http_status = 400

    def as_dict(self) -> dict[str, str]:
        return {"code": self.code, "message": str(self)}


class ResearchNotFound(ResearchError):
    code = "research_not_found"
    http_status = 404


class ResearchConflict(ResearchError):
    code = "research_conflict"
    http_status = 409


class ResearchValidationError(ResearchError):
    code = "research_validation_error"
    http_status = 400


class ResearchUnsafeState(ResearchConflict):
    code = "research_unsafe_state"


class SimulatedCrash(RuntimeError):
    pass
