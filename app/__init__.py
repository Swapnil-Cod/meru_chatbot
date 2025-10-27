from flask import Flask
from app.db import init_db
from config import Config
import os

def create_app():
    # Set template and static folders to project root
    template_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'templates'))
    static_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'static'))

    app = Flask(__name__, template_folder=template_dir, static_folder=static_dir)

    # Initialize MySQL database
    init_db(Config.DB_CONFIG)

    # Set OpenAI API key in environment (routes.py will use it)
    if Config.OPENAI_API_KEY:
        os.environ["OPENAI_API_KEY"] = Config.OPENAI_API_KEY

    # Register routes
    from app.routes import main
    app.register_blueprint(main)

    return app
