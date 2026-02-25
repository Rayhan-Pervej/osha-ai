import json
from flask import Flask
from flask_cors import CORS
from src.config import settings
from src.api.schemas.responses import register_error_handlers
from src.api.blueprints.health import health_bp
from src.api.blueprints.discover import discover_bp
from src.api.blueprints.generate import generate_bp
from src.api.blueprints.keys import keys_bp
from src.api.blueprints.logs import logs_bp

def create_app():
    app = Flask(__name__)

    cors_origins = json.loads(settings.API_CORS_ORIGINS)
    CORS(app, origins=cors_origins)

    app.register_blueprint(health_bp)
    app.register_blueprint(discover_bp)
    app.register_blueprint(generate_bp)
    app.register_blueprint(keys_bp)
    app.register_blueprint(logs_bp)

    register_error_handlers(app)

    return app