from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate

from flask_app.config import Config

app = Flask(__name__, template_folder='../templates', static_folder='../static')
app.config.from_object(Config)
db = SQLAlchemy(app)
migrate = Migrate(app, db)

from flask_app.routes import main
from flask_app.routes import api
from flask_app.routes import events
from flask_app.routes import interactions
from flask_app.routes import connection_types
from flask_app.routes import relationships
from flask_app.routes import platforms
from flask_app import models