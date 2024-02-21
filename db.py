from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
import os

# Initialize SQLAlchemy and Migrate without binding to a specific Flask app
db = SQLAlchemy()
migrate = Migrate()

def init_db(app):
    """
    Initialize the database with the Flask app, applying secure configuration.
    This function configures the database connection including support for SSL if needed.
    It assumes that environment variables are managed through a secure method and are set.
    """
    # Securely fetch database credentials
    db_user = os.getenv("DB_USER")
    db_pass = os.getenv("DB_PASS")
    db_name = os.getenv("DB_NAME")
    db_host = os.getenv("DB_HOST", "localhost")
    ssl_cert = os.getenv("DB_SSL_CERT")  # Path to SSL certificate, if applicable
    
    # Verify that mandatory environment variables are set
    if not all([db_user, db_pass, db_name, db_host]):
        raise ValueError("Critical database configuration environment variables are missing.")
    
    # Construct the database URI with SSL options if provided
    db_uri = f"mysql+pymysql://{db_user}:{db_pass}@{db_host}/{db_name}"
    if ssl_cert:
        db_uri += f"?ssl_ca={ssl_cert}"
    
    # Set SQLAlchemy configurations
    app.config["SQLALCHEMY_DATABASE_URI"] = db_uri
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

    # Bind SQLAlchemy and Migrate to the app
    db.init_app(app)
    migrate.init_app(app, db)
