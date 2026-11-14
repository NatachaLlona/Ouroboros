"""Repository and module paths independent of the caller's current directory."""
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
API_ROOT = PROJECT_ROOT / 'modules/api'
ASSISTANCE_ROOT = PROJECT_ROOT / 'modules/assistance'
DATABASE_ROOT = PROJECT_ROOT / 'modules/database'
FRONTEND_ROOT = PROJECT_ROOT / 'modules/frontend'


class ConfigurationError(ValueError):
    """An intentionally safe configuration failure."""
