""" single source of truth for all extensions used in the app """

from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_mail import Mail
from flask_jwt_extended import JWTManager
from flask_cors import CORS

db = SQLAlchemy()
migrate = Migrate()
mail = Mail()
jwt = JWTManager()
cors = CORS()
