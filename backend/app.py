"""
Crowd Event Management System - Backend Application Entrypoint
--------------------------------------------------------------
Stage 1: Project Foundation & Health Check API.
"""

from datetime import timedelta, date, time
from flask import Flask, jsonify
from flask.json.provider import DefaultJSONProvider
from flask_cors import CORS
from config.settings import settings
from routes.health import health_bp


class CustomJSONProvider(DefaultJSONProvider):
    """Extends Flask's JSON provider to cleanly serialize timedelta, date, and time."""
    def default(self, o):
        if isinstance(o, timedelta):
            total_seconds = int(o.total_seconds())
            hours = total_seconds // 3600
            minutes = (total_seconds % 3600) // 60
            seconds = total_seconds % 60
            return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
        if isinstance(o, (date, time)):
            return o.isoformat()
        return super().default(o)


def create_app() -> Flask:
    """Application factory for the Flask backend."""
    app = Flask(__name__)
    app.json_provider_class = CustomJSONProvider
    app.json = CustomJSONProvider(app)

    # Apply configuration
    app.config['SECRET_KEY'] = settings.SECRET_KEY
    app.config['JSON_SORT_KEYS'] = False
    app.config['SESSION_COOKIE_HTTPONLY'] = True
    app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
    app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=7)

    # Enable Cross-Origin Resource Sharing (CORS) with credentials support for session cookies
    CORS(app, supports_credentials=True, resources={
        r"/api/*": {
            "origins": settings.CORS_ORIGINS,
            "methods": ["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
            "allow_headers": ["Content-Type", "Authorization"]
        }
    })

    # Register Blueprints
    from routes.auth import auth_bp
    from routes.protected_test import protected_bp
    from routes.venues import venues_bp
    from routes.events import events_bp
    from routes.dashboards import dashboards_bp
    from routes.images import images_bp, serve_event_image_direct
    from routes.public import public_bp
    from routes.fest import fest_bp
    from routes.reports import reports_bp
    from routes.alerts import alerts_bp

    app.register_blueprint(health_bp, url_prefix='/api')
    app.register_blueprint(auth_bp, url_prefix='/api/auth')
    app.register_blueprint(protected_bp, url_prefix='/api')
    app.register_blueprint(venues_bp, url_prefix='/api/venues')
    app.register_blueprint(events_bp, url_prefix='/api')
    app.register_blueprint(dashboards_bp, url_prefix='/api')
    app.register_blueprint(images_bp, url_prefix='/api')
    app.register_blueprint(public_bp, url_prefix='/api/public')
    app.register_blueprint(fest_bp, url_prefix='/api')
    app.register_blueprint(reports_bp, url_prefix='/api')
    app.register_blueprint(alerts_bp, url_prefix='/api')


    # Serve uploaded images directly at /uploads/event_images/<filename>
    app.add_url_rule(
        '/uploads/event_images/<path:filename>',
        'serve_event_image_direct',
        serve_event_image_direct,
        methods=['GET']
    )

    @app.route('/', methods=['GET'])
    def root():
        """Friendly index route with API information."""
        return jsonify({
            "service": "Crowd Event Management System API",
            "version": "1.0.0",
            "stage": "Stage 1 — Project Foundation",
            "documentation": {
                "health_check": "/api/health"
            }
        }), 200

    @app.errorhandler(404)
    def not_found_handler(error):
        return jsonify({
            "error": "Not Found",
            "message": "The requested endpoint does not exist."
        }), 404

    @app.errorhandler(500)
    def internal_error_handler(error):
        return jsonify({
            "error": "Internal Server Error",
            "message": "An unexpected server error occurred."
        }), 500

    return app


if __name__ == '__main__':
    from config.init_db import check_database_readiness, initialize_database

    # Lightweight database check at server startup
    try:
        readiness = check_database_readiness()
        if not readiness['ready']:
            print(f"[INFO] Database readiness check: {readiness['message']}")
            print("[INFO] Automatically initializing database via canonical schema.sql...")
            initialize_database(verbose=True)
        else:
            print(f"[OK] Database readiness: {readiness['message']}")
    except Exception as db_err:
        print(f"[WARNING] Database readiness check encountered an issue: {db_err}")
        print("          Run 'python backend/config/init_db.py' to initialize the database manually.")

    app = create_app()
    print(f"==================================================")
    print(f" Crowd Event Management System - Backend API ")
    print(f" Server running at: http://{settings.HOST}:{settings.PORT}")
    print(f" Health check:      http://{settings.HOST}:{settings.PORT}/api/health")
    print(f"==================================================")
    app.run(
        host=settings.HOST,
        port=settings.PORT,
        debug=settings.DEBUG
    )
