from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_migrate import Migrate
from flask_babel import Babel
from flask_wtf.csrf import CSRFProtect
from flask_mail import Mail
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
import os
from contextlib import suppress

# Initialize extensions
db = SQLAlchemy()
login = LoginManager()
login.login_view = "auth.login"
login.login_message = None
login.login_message_category = "info"
migrate = Migrate()
babel = Babel()
csrf = CSRFProtect()
mail = Mail()
limiter = Limiter(
    key_func=get_remote_address,
    # IMPORTANT:
    # Do NOT apply low global rate limits to the entire web app, since every page load
    # pulls many static assets (CSS/JS/images), which can easily trigger 429 responses
    # and break core functionality (e.g. Service Worker registration).
    #
    # Rate limiting should be applied to specific abuse-prone endpoints only
    # (auth, API submissions, etc.) via @limiter.limit(...) or custom decorators.
    default_limits=[],
    storage_uri="memory://"  # Use in-memory storage (can be changed to Redis for production)
)

# Configure Babel to disable caching in development
def configure_babel(app):
    if app.config.get('DEBUG', False):
        # Disable caching in development mode
        # Point to app translations directory (Backoffice/app/translations). Multiple dirs can be ';' separated.
        # Flask-Babel resolves this relative to app.root_path, so "translations" is correct.
        app.config['BABEL_TRANSLATION_DIRECTORIES'] = 'translations'
        app.config['BABEL_DEFAULT_LOCALE'] = 'en'
        app.config['BABEL_DEFAULT_TIMEZONE'] = 'UTC'

        # Disable Babel caching in development
        app.config['BABEL_CACHE_ENABLED'] = False

        # Force reload translations on each request in debug mode
        @app.before_request
        def force_reload_translations():
            if app.config.get('DEBUG', False):
                from flask_babel import refresh
                with suppress(Exception):  # Ignore errors during refresh
                    refresh()
