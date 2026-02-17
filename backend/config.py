import os
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-key")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin123")

DB_PATH = os.getenv("DB_PATH", os.path.join(os.path.dirname(__file__), "life_agent.db"))
LOG_DIR = os.getenv("LOG_DIR", os.path.join(os.path.dirname(__file__), "logs"))
COOKIE_SECURE = os.getenv("COOKIE_SECURE", "false").lower() == "true"

MODEL_BIG = "gpt-5"
MODEL_SMALL = "gpt-5-mini"

SESSION_EXPIRE_HOURS = 72
