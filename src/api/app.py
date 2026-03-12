import json
from flask import Flask
from flask_cors import CORS
from src.config import settings
from src.api.schemas.responses import register_error_handlers
from src.api.blueprints.health import health_bp
from src.api.blueprints.keys import keys_bp
from src.api.blueprints.logs import logs_bp
from src.api.blueprints.chat import chat_bp

def create_app():
    app = Flask(__name__)
    settings.validate()
    try:
        cors_origins = json.loads(settings.API_CORS_ORIGINS)
    except (json.JSONDecodeError, TypeError):
        cors_origins = ["http://localhost:3000"]

    CORS(app, origins=cors_origins)

    app.register_blueprint(health_bp)
    app.register_blueprint(keys_bp)
    app.register_blueprint(logs_bp)
    app.register_blueprint(chat_bp)

    register_error_handlers(app)

    return app
