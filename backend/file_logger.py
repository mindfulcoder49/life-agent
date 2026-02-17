import logging
import os
from logging.handlers import RotatingFileHandler
from datetime import datetime, timezone

from config import LOG_DIR
os.makedirs(LOG_DIR, exist_ok=True)

LOG_FILE = os.path.join(LOG_DIR, "life_agent.log")
DEBUG_LOG_FILE = os.path.join(LOG_DIR, "debug_conversations.log")

_handler = RotatingFileHandler(LOG_FILE, maxBytes=5_000_000, backupCount=3)
_handler.setFormatter(logging.Formatter(
    "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
))

logger = logging.getLogger("life_agent")
logger.setLevel(logging.DEBUG)
logger.addHandler(_handler)

_console = logging.StreamHandler()
_console.setFormatter(logging.Formatter("[%(levelname)s] %(name)s: %(message)s"))
_console.setLevel(logging.INFO)
logger.addHandler(_console)

# Debug conversation logger - full conversation transcripts
_debug_handler = RotatingFileHandler(DEBUG_LOG_FILE, maxBytes=10_000_000, backupCount=5)
_debug_handler.setFormatter(logging.Formatter("%(message)s"))

debug_logger = logging.getLogger("life_agent.debug")
debug_logger.setLevel(logging.DEBUG)
debug_logger.addHandler(_debug_handler)
debug_logger.propagate = False

# Debug logging toggle - off by default
_debug_enabled = False


def is_debug_enabled():
    return _debug_enabled


def set_debug_enabled(enabled: bool):
    global _debug_enabled
    _debug_enabled = enabled
    logger.info(f"Debug logging {'enabled' if enabled else 'disabled'}")


def log_conversation_turn(user_id, session_id, agent, direction, content, tool_calls=None):
    """Log a complete conversation entry for debug analysis."""
    if not _debug_enabled:
        return
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    sep = "=" * 60
    debug_logger.debug(f"\n{sep}")
    debug_logger.debug(f"[{now}] user={user_id} session={session_id} agent={agent}")
    debug_logger.debug(f"Direction: {direction}")
    debug_logger.debug(f"Content:\n{content}")
    if tool_calls:
        debug_logger.debug(f"Tool calls:")
        for tc in tool_calls:
            debug_logger.debug(f"  - {tc.get('name', '?')}({tc.get('args', {})})")
            if 'result' in tc:
                result_str = str(tc['result'])[:500]
                debug_logger.debug(f"    Result: {result_str}")
    debug_logger.debug(sep)
