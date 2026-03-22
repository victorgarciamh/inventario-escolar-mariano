from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from web.extensions import db
from web.models import Usuario
from werkzeug.security import generate_password_hash, check_password_hash
import os

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

@auth_bp.route('/recuperar', methods=['GET', 'POST'])
def recuperar():
    if request.method == 'POST':
        palabra       = request.form.get('palabra_secreta', '').strip()
        nueva_pass    = request.form.get('nueva_password', '').strip()
        confirmar     = request.form.get('confirmar_password', '').strip()
        palabra_real  = os.environ.get('PALABRA_SECRETA', '')

        if not palabra_real:
            flash('La función de recuperación no está configurada', 'danger')
            return redirect(url_for('auth.recuperar'))

        if palabra != palabra_real:
            flash('Palabra secreta incorrecta', 'danger')
            return redirect(url_for('auth.recuperar'))

        if len(nueva_pass) < 6:
            flash('La contraseña debe tener al menos 6 caracteres', 'danger')
            return redirect(url_for('auth.recuperar'))

        if nueva_pass != confirmar:
            flash('Las contraseñas no coinciden', 'danger')
            return redirect(url_for('auth.recuperar'))

        # Cambiar contraseña del único usuario (directora)
        usuario = Usuario.query.first()
        if usuario:
            usuario.password_hash = generate_password_hash(nueva_pass)
            db.session.commit()
            flash('Contraseña actualizada correctamente. Ya puedes iniciar sesión.', 'success')
            return redirect(url_for('auth.login'))
        else:
            flash('No se encontró ningún usuario', 'danger')

    return render_template('auth/recuperar.html')

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