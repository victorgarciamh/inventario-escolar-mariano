from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from web.extensions import db
from web.models import Usuario
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta
import os

auth_bp = Blueprint('auth', __name__)

MAX_INTENTOS = 5
BLOQUEO_MINUTOS = 15

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if 'usuario_id' in session:
        return redirect(url_for('inventario.dashboard'))

    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()

        # Verificar bloqueo
        intentos     = session.get('login_intentos', 0)
        bloqueado_en = session.get('login_bloqueado_en')

        if bloqueado_en:
            bloqueado_en = datetime.fromisoformat(bloqueado_en)
            if datetime.now() < bloqueado_en + timedelta(minutes=BLOQUEO_MINUTOS):
                minutos_restantes = int(((bloqueado_en + timedelta(minutes=BLOQUEO_MINUTOS)) - datetime.now()).seconds / 60) + 1
                flash(f'Demasiados intentos fallidos. Espera {minutos_restantes} minuto(s) para intentar de nuevo.', 'danger')
                return render_template('auth/login.html')
            else:
                # Bloqueo expirado, resetear
                session.pop('login_intentos', None)
                session.pop('login_bloqueado_en', None)
                intentos = 0

        usuario = Usuario.query.filter_by(username=username).first()

        if usuario and check_password_hash(usuario.password_hash, password):
            # Login exitoso — limpiar contadores
            session.pop('login_intentos', None)
            session.pop('login_bloqueado_en', None)
            session['usuario_id'] = usuario.id
            session['usuario_nombre'] = usuario.nombre
            flash(f'Bienvenida, {usuario.nombre} 👋', 'success')
            return redirect(url_for('inventario.dashboard'))
        else:
            intentos += 1
            session['login_intentos'] = intentos
            restantes = MAX_INTENTOS - intentos

            if intentos >= MAX_INTENTOS:
                session['login_bloqueado_en'] = datetime.now().isoformat()
                flash(f'Demasiados intentos fallidos. Cuenta bloqueada por {BLOQUEO_MINUTOS} minutos.', 'danger')
            else:
                flash(f'Usuario o contraseña incorrectos. Te quedan {restantes} intento(s).', 'danger')

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