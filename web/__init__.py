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

    # Ruta para servir fotos desde S3 o local
    @app.route('/foto/<path:foto_url>')
    def servir_foto(foto_url):
        import boto3
        from flask import redirect as redir, send_from_directory
        from io import BytesIO

        if foto_url.startswith('s3:'):
            s3_key      = foto_url[3:]
            endpoint    = os.environ.get('S3_ENDPOINT')
            bucket      = os.environ.get('S3_BUCKET_NAME', 'inventario')
            url_publica = f"{endpoint}/{bucket}/{s3_key}"
            return redir(url_publica)

        return send_from_directory(app.config['UPLOAD_FOLDER'], foto_url)

    # Crear tablas
    with app.app_context():
        db.create_all()

    return app