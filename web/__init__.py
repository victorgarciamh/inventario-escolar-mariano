from flask import Flask, render_template, redirect, url_for
from .config import Config
from .extensions import db
from .routes.auth import auth_bp
from .routes.inventario import inventario_bp
import os

def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    # Crear carpeta de uploads si no existe
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

    # Inicializar base de datos
    db.init_app(app)

    # Registrar Blueprints
    app.register_blueprint(auth_bp, url_prefix='/auth')
    app.register_blueprint(inventario_bp, url_prefix='/inventario')

    # Ruta principal — redirige al inventario si hay sesión, si no al login
    @app.route('/')
    def index():
        return redirect(url_for('auth.login'))

    # Crear tablas
    with app.app_context():
        db.create_all()

    return app