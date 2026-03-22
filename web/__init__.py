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

    # Ruta para servir fotos desde S3 con URL prefirmada (2 horas)
    @app.route('/foto/<path:foto_url>')
    def servir_foto(foto_url):
        import boto3
        from flask import redirect as redir, send_from_directory
        from botocore.config import Config as BotoConfig

        if foto_url.startswith('s3:'):
            s3_key   = foto_url[3:]
            endpoint = os.environ.get('S3_ENDPOINT')
            key      = os.environ.get('S3_KEY')
            secret   = os.environ.get('S3_SECRET')
            bucket   = os.environ.get('S3_BUCKET_NAME', 'inventario')

            try:
                client = boto3.client('s3',
                    endpoint_url=endpoint,
                    aws_access_key_id=key,
                    aws_secret_access_key=secret,
                    region_name='us-west-1',
                    config=BotoConfig(signature_version='s3v4')
                )
                url_firmada = client.generate_presigned_url(
                    'get_object',
                    Params={'Bucket': bucket, 'Key': s3_key},
                    ExpiresIn=7200  # 2 horas
                )
                return redir(url_firmada)
            except Exception as e:
                return f"Error al obtener foto: {str(e)}", 500

        return send_from_directory(app.config['UPLOAD_FOLDER'], foto_url)

    # Crear tablas
    with app.app_context():
        db.create_all()

    return app