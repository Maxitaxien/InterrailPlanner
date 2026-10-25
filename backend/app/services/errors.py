class PlanningError(Exception):
    def __init__(self, code: str, message: str, details: dict | None = None, status: int = 422):
        self.code, self.message, self.details, self.status = code, message, details or {}, status
