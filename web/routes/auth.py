from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from web.extensions import db
from web.models import Usuario
from werkzeug.security import generate_password_hash, check_password_hash

auth_bp = Blueprint('auth', __name__)

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if 'usuario_id' in session:
        return redirect(url_for('inventario.dashboard'))

    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()

        usuario = Usuario.query.filter_by(username=username).first()

        if usuario and check_password_hash(usuario.password_hash, password):
            session['usuario_id'] = usuario.id
            session['usuario_nombre'] = usuario.nombre
            flash(f'Bienvenida, {usuario.nombre} 👋', 'success')
            return redirect(url_for('inventario.dashboard'))
        else:
            flash('Usuario o contraseña incorrectos', 'danger')

    return render_template('auth/login.html')

@auth_bp.route('/logout')
def logout():
    session.clear()
    flash('Sesión cerrada correctamente', 'success')
    return redirect(url_for('auth.login'))

@auth_bp.route('/crear-admin')
def crear_admin():
    """Ruta temporal para crear el usuario directora — eliminar después del primer uso"""
    existe = Usuario.query.filter_by(username='directora').first()
    if existe:
        return 'El usuario ya existe'
    
    nuevo = Usuario(
        username='directora',
        password_hash=generate_password_hash('admin1234'),
        nombre='Directora'
    )
    db.session.add(nuevo)
    db.session.commit()
    return 'Usuario directora creado. Contraseña: admin1234'