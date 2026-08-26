from flask import Flask
import os

from config import config_by_name
from extensions import db, migrate, mail, jwt, cors

#use app factory pattern to create the app instance, and to allow for different configurations to be used in different environments
def create_app(config_name : str = None) -> Flask:
    """
    match the config_name to the appropriate config class and initialize the app with it
    if config_name is not provided, check the FLASK_ENV environment variable
    or default to "development"
    """
    config_name = config_name or os.environ.get("FLASK_ENV", "development")

    app = Flask(__name__)
    #load all settings from the config class into the app's config
    app.config.from_object(config_by_name[config_name])

    #initialize the extensions with the app
    db.init_app(app)
    migrate.init_app(app, db)
    mail.init_app(app)
    jwt.init_app(app)
    cors.init_app(app,origins=app.config["CORS_ORIGINS"], supports_credentials=True)
    mail.init_app(app)

    """import models here to avoid circular imports, and to ensure they are registered with SQLAlchemy"""
    from foundations import models as foundation_models
    from origination import models as origination_models
    from underwriting import models as underwriting_models

    from foundations.routes import foundation_bp
    app.register_blueprint(foundation_bp, url_prefix="/api/auth")

    from origination.routes import origination_bp
    app.register_blueprint(origination_bp, url_prefix="/api/origination")

    from underwriting.routes import underwriting_bp
    app.register_blueprint(underwriting_bp, url_prefix="/api/underwriting")

    from foundations.auth import register_jwt_callbacks
    register_jwt_callbacks(jwt)

    #provide a working route you can visit to check if the app is running, and to test the health of the app
    @app.get("/api/health")
    def health():
        return {"status": "ok"}

    return app

if __name__ == "__main__":
    app = create_app()
    app.run(debug=True)
