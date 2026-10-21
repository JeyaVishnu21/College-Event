import os
from pathlib import Path
from dotenv import load_dotenv

# Locate and load the .env file in the backend directory
BACKEND_DIR = Path(__file__).resolve().parent.parent
ENV_PATH = BACKEND_DIR / '.env'

if ENV_PATH.exists():
    load_dotenv(dotenv_path=ENV_PATH)
else:
    load_dotenv()

class Settings:
    """Application configuration loaded safely from environment variables."""
    # Server settings
    HOST: str = os.getenv('HOST', '127.0.0.1')
    PORT: int = int(os.getenv('PORT', 5000))
    DEBUG: bool = os.getenv('DEBUG', 'True').lower() in ('true', '1', 'yes')

    # Security
    SECRET_KEY: str = os.getenv('SECRET_KEY', 'default-dev-secret-key-replace-in-production')

    # MySQL Database settings (Placeholder for Stage 2)
    DB_HOST: str = os.getenv('DB_HOST', 'localhost')
    DB_PORT: int = int(os.getenv('DB_PORT', 3306))
    DB_USER: str = os.getenv('DB_USER', 'root')
    DB_PASSWORD: str = os.getenv('DB_PASSWORD', '')
    DB_NAME: str = os.getenv('DB_NAME', 'crowd_event_db')

    # Registration secret code for administrator accounts
    ADMINISTRATOR_REGISTRATION_CODE: str = os.getenv('ADMINISTRATOR_REGISTRATION_CODE', os.getenv('MANAGEMENT_REGISTRATION_CODE', 'college_mgmt_secret_2026'))
    MANAGEMENT_REGISTRATION_CODE: str = ADMINISTRATOR_REGISTRATION_CODE

    # CORS origins
    CORS_ORIGINS: list[str] = [
        origin.strip()
        for origin in os.getenv('CORS_ORIGINS', 'http://localhost:3000,http://127.0.0.1:3000,http://localhost:5173,http://127.0.0.1:5173').split(',')
        if origin.strip()
    ]

    # Image Upload settings (Stage 6)
    UPLOAD_FOLDER: Path = Path(os.getenv('UPLOAD_FOLDER', str(BACKEND_DIR / 'uploads' / 'event_images')))
    MAX_CONTENT_LENGTH: int = int(os.getenv('MAX_CONTENT_LENGTH', 10 * 1024 * 1024))  # 10 MB
    ALLOWED_IMAGE_EXTENSIONS: set = {'jpg', 'jpeg', 'png'}
    ALLOWED_IMAGE_MIMETYPES: set = {'image/jpeg', 'image/png'}

settings = Settings()
os.makedirs(settings.UPLOAD_FOLDER, exist_ok=True)
