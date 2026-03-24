import os
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-key")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin123")
ADMIN_API_KEY = os.getenv("ADMIN_API_KEY", "dev-admin-api-key")
TEST_USER_USERNAME = os.getenv("TEST_USER_USERNAME", "__test__")
TEST_USER_PASSWORD = os.getenv("TEST_USER_PASSWORD", "test-password-dev")

DB_PATH = os.getenv("DB_PATH", os.path.join(os.path.dirname(__file__), "life_agent.db"))
LOG_DIR = os.getenv("LOG_DIR", os.path.join(os.path.dirname(__file__), "logs"))
COOKIE_SECURE = os.getenv("COOKIE_SECURE", "false").lower() == "true"

MODEL_BIG = "gpt-5"
MODEL_SMALL = "gpt-5-mini"

SESSION_EXPIRE_HOURS = 72

SMTP_HOST = os.getenv("MAIL_HOST", "smtp.hostinger.com")
SMTP_PORT = int(os.getenv("MAIL_PORT", "587"))
SMTP_USER = os.getenv("MAIL_USERNAME", "")
SMTP_PASS = os.getenv("MAIL_PASSWORD", "")
SMTP_FROM = os.getenv("MAIL_FROM_ADDRESS", "noreply@alcivartech.com")
SMTP_FROM_NAME = os.getenv("MAIL_FROM_NAME", "Life Agent")
APP_URL = os.getenv("APP_URL", "http://localhost:5173")
