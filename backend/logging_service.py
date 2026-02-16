from database import insert_row

def log_event(user_id: int | None, level: str, source: str, event: str, message: str, details: dict = None):
    insert_row("logs", {
        "user_id": user_id,
        "level": level,
        "source": source,
        "event": event,
        "message": message,
        "details": details or {},
    })

def log_info(source: str, event: str, message: str, user_id: int = None, details: dict = None):
    log_event(user_id, "info", source, event, message, details)

def log_error(source: str, event: str, message: str, user_id: int = None, details: dict = None):
    log_event(user_id, "error", source, event, message, details)

def log_warn(source: str, event: str, message: str, user_id: int = None, details: dict = None):
    log_event(user_id, "warn", source, event, message, details)
