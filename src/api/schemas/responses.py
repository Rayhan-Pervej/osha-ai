from flask import jsonify
from marshmallow import ValidationError


def success(data: dict, status: int = 200):
    return jsonify(data), status


def error(code: str, message: str, status: int = 400):
    return jsonify({"error": code, "message": message}), status


def validation_error(exc: ValidationError):
    return jsonify({
        "error": "validation_error",
        "message": "Invalid request",
        "fields": exc.messages,
    }), 400


def register_error_handlers(app):
    @app.errorhandler(404)
    def not_found(_):
        return jsonify({"error": "not_found", "message": "Endpoint does not exist"}), 404

    @app.errorhandler(405)
    def method_not_allowed(_):
        return jsonify({"error": "method_not_allowed", "message": "HTTP method not allowed"}), 405

    @app.errorhandler(500)
    def internal_error(_):
        return jsonify({"error": "internal_error", "message": "An unexpected error occurred"}), 500
