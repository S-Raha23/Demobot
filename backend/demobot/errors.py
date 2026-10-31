class DemoBotError(Exception):
    """An expected failure: an upper-snake code, a message, the stage and an HTTP status."""

    def __init__(self, code: str, message: str, stage: str | None = None, http: int = 400) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message
        self.stage = stage
        self.http = http

    def as_dict(self) -> dict[str, str | None]:
        return {"code": self.code, "message": self.message, "stage": self.stage}
