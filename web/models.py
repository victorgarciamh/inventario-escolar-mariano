from datetime import datetime
from .extensions import db

class Usuario(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    nombre = db.Column(db.String(100), nullable=False)
    fecha_creacion = db.Column(db.DateTime, default=datetime.utcnow)

class Ubicacion(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(100), nullable=False)
    tipo = db.Column(db.String(20), nullable=False)  # 'salon' o 'bodega'
    descripcion = db.Column(db.Text, nullable=True)
    articulos = db.relationship('Articulo', back_populates='ubicacion', lazy=True)

class Articulo(db.Model):
    id = db.Column(db.Integer, primary_key=True)

    # Campos básicos
    nombre = db.Column(db.String(200), nullable=False)
    descripcion = db.Column(db.Text, nullable=True)
    categoria = db.Column(db.String(100), nullable=True)

    # Campos del tarjetón
    tipo_bien = db.Column(db.String(50), default='3-Activo')          # 3-Activo, Consumible, etc.
    numero_inventario   = db.Column(db.String(100), nullable=True)
    numero_inventario_2 = db.Column(db.String(100), nullable=True)
    cantidad = db.Column(db.Integer, default=1)
    precio_unitario = db.Column(db.Float, default=0.0)
    tipo_adquisicion = db.Column(db.String(100), nullable=True)       # Gasto operación, Donación, etc.

    # Estado y ubicación
    estado = db.Column(db.String(20), default='Bueno')
    ubicacion_id = db.Column(db.Integer, db.ForeignKey('ubicacion.id'), nullable=True)
    foto_url = db.Column(db.String(300), nullable=True)

    # Metadatos
    fecha_registro = db.Column(db.DateTime, default=datetime.utcnow)
    ultima_actualizacion = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    ubicacion = db.relationship('Ubicacion', back_populates='articulos')

    @property
    def total(self):
        return round((self.cantidad or 0) * (self.precio_unitario or 0), 2)

class Movimiento(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    articulo_id = db.Column(db.Integer, db.ForeignKey('articulo.id'), nullable=False)
    tipo = db.Column(db.String(20), nullable=False)
    cantidad = db.Column(db.Integer, default=0)
    descripcion = db.Column(db.Text, nullable=True)
    fecha = db.Column(db.DateTime, default=datetime.utcnow)
    realizado_por = db.Column(db.String(100))
    articulo = db.relationship('Articulo', backref='movimientos')