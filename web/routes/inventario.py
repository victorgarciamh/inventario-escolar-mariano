from flask import Blueprint, render_template, request, redirect, url_for, flash, session, send_file, jsonify
from web.extensions import db
from web.models import Articulo, Ubicacion, Movimiento
from werkzeug.utils import secure_filename
from datetime import datetime
from io import BytesIO
import os

inventario_bp = Blueprint('inventario', __name__)

def require_login(f):
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'usuario_id' not in session:
            flash('Debes iniciar sesión', 'danger')
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in {'png', 'jpg', 'jpeg', 'webp'}

def subir_foto(foto, filename):
    """Sube foto a S3/iDrive e2 o guarda localmente como fallback"""
    import boto3
    from io import BytesIO

    endpoint  = os.environ.get('S3_ENDPOINT')
    key       = os.environ.get('S3_KEY')
    secret    = os.environ.get('S3_SECRET')
    bucket    = os.environ.get('S3_BUCKET_NAME', 'inventario')
    s3_ok     = bool(endpoint and key and secret)

    foto.seek(0)
    contenido = foto.read()
    foto.seek(0)

    if s3_ok:
        try:
            client = boto3.client('s3',
                endpoint_url=endpoint,
                aws_access_key_id=key,
                aws_secret_access_key=secret,
                region_name='us-west-1'
            )
            s3_key = f"fotos/{filename}"
            client.upload_fileobj(
                BytesIO(contenido),
                bucket,
                s3_key,
                ExtraArgs={'ContentType': foto.content_type or 'image/jpeg'}
            )
            return f"s3:{s3_key}"  # marcador para saber que está en S3
        except Exception as e:
            print(f"Error S3: {e}")

    # Fallback local
    from flask import current_app
    os.makedirs(current_app.config['UPLOAD_FOLDER'], exist_ok=True)
    ruta = os.path.join(current_app.config['UPLOAD_FOLDER'], filename)
    with open(ruta, 'wb') as f:
        f.write(contenido)
    return filename

def url_foto(foto_url):
    """Devuelve la URL pública de una foto"""
    if not foto_url:
        return None
    if foto_url.startswith('s3:'):
        s3_key   = foto_url[3:]
        endpoint = os.environ.get('S3_ENDPOINT', '')
        bucket   = os.environ.get('S3_BUCKET_NAME', 'inventario')
        return f"{endpoint}/{bucket}/{s3_key}"
    return None  # foto local — se sirve desde static

# --- DASHBOARD ---
@inventario_bp.route('/')
@require_login
def dashboard():
    ultimos_movimientos = Movimiento.query.order_by(Movimiento.fecha.desc()).limit(5).all()
    return render_template('inventario/dashboard.html',
                           ultimos_movimientos=ultimos_movimientos,
                           now=datetime.now())

# --- INVENTARIO PRINCIPAL (tabla + captura inline) ---
@inventario_bp.route('/articulos', methods=['GET', 'POST'])
@require_login
def lista_articulos():
    if request.method == 'POST':
        # Captura inline desde la tabla
        nombre          = request.form.get('nombre', '').strip()
        tipo_bien       = request.form.get('tipo_bien', '3-Activo')
        numero_inv      = request.form.get('numero_inventario', '').strip()
        numero_inv_2    = request.form.get('numero_inventario_2', '').strip()
        descripcion     = request.form.get('descripcion', '').strip()
        categoria       = request.form.get('categoria', '').strip()
        cantidad        = int(request.form.get('cantidad') or 1)
        precio_unitario = float(request.form.get('precio_unitario') or 0)
        tipo_adq        = request.form.get('tipo_adquisicion', '').strip()
        estado          = request.form.get('estado', 'Bueno')
        ubicacion_id    = request.form.get('ubicacion_id') or None
        foto_url        = None

        if not nombre:
            flash('El nombre del artículo es obligatorio', 'danger')
            return redirect(url_for('inventario.lista_articulos'))

        if 'foto' in request.files:
            foto = request.files['foto']
            if foto and foto.filename != '' and allowed_file(foto.filename):
                filename = secure_filename(
                    f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{foto.filename}")
                foto_url = subir_foto(foto, filename)

        nuevo = Articulo(
            nombre=nombre,
            tipo_bien=tipo_bien,
            numero_inventario=numero_inv,
            numero_inventario_2=numero_inv_2,
            descripcion=descripcion,
            categoria=categoria,
            cantidad=cantidad,
            precio_unitario=precio_unitario,
            tipo_adquisicion=tipo_adq,
            estado=estado,
            ubicacion_id=ubicacion_id,
            foto_url=foto_url
        )
        db.session.add(nuevo)
        db.session.flush()

        db.session.add(Movimiento(
            articulo_id=nuevo.id, tipo='entrada',
            cantidad=cantidad, descripcion='Registro inicial',
            realizado_por=session.get('usuario_nombre')
        ))
        db.session.commit()
        flash(f'Artículo "{nombre}" agregado', 'success')
        return redirect(url_for('inventario.lista_articulos',
                                ubicacion=request.form.get('_filtro_ubicacion'),
                                tipo=request.form.get('_filtro_tipo'),
                                estado=request.form.get('_filtro_estado')))

    # GET — filtros
    filtro_ubicacion = request.args.get('ubicacion')
    filtro_estado    = request.args.get('estado')
    filtro_tipo      = request.args.get('tipo')
    filtro_categoria = request.args.get('categoria')

    query = Articulo.query
    if filtro_ubicacion:
        query = query.filter_by(ubicacion_id=filtro_ubicacion)
    if filtro_estado:
        query = query.filter_by(estado=filtro_estado)
    if filtro_categoria:
        query = query.filter_by(categoria=filtro_categoria)
    if filtro_tipo:
        query = query.join(Ubicacion).filter(Ubicacion.tipo == filtro_tipo)

    POR_PAGINA = 34
    pagina     = request.args.get('pagina', 1, type=int)

    paginacion  = query.order_by(Articulo.nombre).paginate(page=pagina, per_page=POR_PAGINA, error_out=False)
    articulos   = paginacion.items
    ubicaciones = Ubicacion.query.order_by(Ubicacion.nombre).all()
    salones     = Ubicacion.query.filter_by(tipo='salon').order_by(Ubicacion.nombre).all()
    bodegas     = Ubicacion.query.filter_by(tipo='bodega').order_by(Ubicacion.nombre).all()

    categorias = db.session.query(Articulo.categoria).filter(
        Articulo.categoria != None, Articulo.categoria != ''
    ).distinct().order_by(Articulo.categoria).all()
    categorias = [c[0] for c in categorias]

    ubicacion_sel = Ubicacion.query.get(filtro_ubicacion) if filtro_ubicacion else None

    return render_template('inventario/articulos.html',
                           articulos=articulos,
                           paginacion=paginacion,
                           ubicaciones=ubicaciones,
                           salones=salones,
                           bodegas=bodegas,
                           categorias=categorias,
                           ubicacion_sel=ubicacion_sel,
                           filtro_ubicacion=filtro_ubicacion or '',
                           filtro_estado=filtro_estado or '',
                           filtro_tipo=filtro_tipo or '',
                           filtro_categoria=filtro_categoria or '',
                           now=datetime.now())

# --- EDITAR ---
@inventario_bp.route('/articulos/editar/<int:id>', methods=['GET', 'POST'])
@require_login
def editar_articulo(id):
    articulo    = Articulo.query.get_or_404(id)
    ubicaciones = Ubicacion.query.order_by(Ubicacion.nombre).all()

    if request.method == 'POST':
        articulo.nombre           = request.form.get('nombre', '').strip()
        articulo.tipo_bien        = request.form.get('tipo_bien', '3-Activo')
        articulo.numero_inventario = request.form.get('numero_inventario', '').strip()
        articulo.numero_inventario_2 = request.form.get('numero_inventario_2', '').strip()
        articulo.descripcion      = request.form.get('descripcion', '').strip()
        articulo.categoria        = request.form.get('categoria', '').strip()
        articulo.cantidad         = int(request.form.get('cantidad') or 1)
        articulo.precio_unitario  = float(request.form.get('precio_unitario') or 0)
        articulo.tipo_adquisicion = request.form.get('tipo_adquisicion', '').strip()
        articulo.estado           = request.form.get('estado', 'Bueno')
        articulo.ubicacion_id     = request.form.get('ubicacion_id') or None

        if 'foto' in request.files:
            foto = request.files['foto']
            if foto and foto.filename != '' and allowed_file(foto.filename):
                filename = secure_filename(
                    f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{foto.filename}")
                articulo.foto_url = subir_foto(foto, filename)

        db.session.add(Movimiento(
            articulo_id=articulo.id, tipo='edicion', cantidad=0,
            descripcion='Editado', realizado_por=session.get('usuario_nombre')
        ))
        db.session.commit()
        flash(f'Artículo "{articulo.nombre}" actualizado', 'success')
        return redirect(url_for('inventario.lista_articulos'))

    return render_template('inventario/editar_articulo.html',
                           articulo=articulo, ubicaciones=ubicaciones, now=datetime.now())

# --- ELIMINAR ---
@inventario_bp.route('/articulos/eliminar/<int:id>')
@require_login
def eliminar_articulo(id):
    articulo = Articulo.query.get_or_404(id)
    nombre = articulo.nombre
    db.session.delete(articulo)
    db.session.commit()
    flash(f'Artículo "{nombre}" eliminado', 'warning')
    return redirect(url_for('inventario.lista_articulos'))

# --- UBICACIONES ---
@inventario_bp.route('/ubicaciones')
@require_login
def ubicaciones():
    salones = Ubicacion.query.filter_by(tipo='salon').order_by(Ubicacion.nombre).all()
    bodegas = Ubicacion.query.filter_by(tipo='bodega').order_by(Ubicacion.nombre).all()
    return render_template('inventario/ubicaciones.html',
                           salones=salones, bodegas=bodegas, now=datetime.now())

@inventario_bp.route('/ubicaciones/agregar', methods=['POST'])
@require_login
def agregar_ubicacion():
    nombre      = request.form.get('nombre', '').strip()
    tipo        = request.form.get('tipo', 'salon')
    descripcion = request.form.get('descripcion', '').strip()
    db.session.add(Ubicacion(nombre=nombre, tipo=tipo, descripcion=descripcion))
    db.session.commit()
    flash(f'Ubicación "{nombre}" agregada', 'success')
    return redirect(url_for('inventario.ubicaciones'))

@inventario_bp.route('/ubicaciones/eliminar/<int:id>')
@require_login
def eliminar_ubicacion(id):
    ubicacion = Ubicacion.query.get_or_404(id)
    nombre = ubicacion.nombre
    db.session.delete(ubicacion)
    db.session.commit()
    flash(f'Ubicación "{nombre}" eliminada', 'warning')
    return redirect(url_for('inventario.ubicaciones'))

@inventario_bp.route('/ubicaciones/<int:id>')
@require_login
def ver_ubicacion(id):
    ubicacion = Ubicacion.query.get_or_404(id)
    articulos = Articulo.query.filter_by(ubicacion_id=id).order_by(Articulo.nombre).all()
    return redirect(url_for('inventario.lista_articulos', ubicacion=id))

# --- EXPORTAR PDF COMPLETO (FORMATO WEB) ---
@inventario_bp.route('/exportar-pdf')
@require_login
def exportar_pdf():
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib import colors
    from reportlab.lib.units import cm, inch
    from reportlab.platypus import (SimpleDocTemplate, Table, TableStyle,
                                    Paragraph, Spacer, HRFlowable, KeepTogether)
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
    import os

    tipo         = request.args.get('tipo', 'general')
    ubicacion_id = request.args.get('ubicacion_id')

    # Paleta moderna
    INDIGO      = colors.HexColor('#1e3a5f')
    INDIGO_DARK = colors.HexColor('#0f2744')
    DARK        = colors.HexColor('#0f172a')
    SLATE       = colors.HexColor('#475569')
    MUTED       = colors.HexColor('#94a3b8')
    BORDER      = colors.HexColor('#e2e8f0')
    WHITE       = colors.white
    ALT         = colors.HexColor('#f8fafc')
    SUCCESS     = colors.HexColor('#d1fae5')
    SUCCESS_TXT = colors.HexColor('#065f46')
    WARN        = colors.HexColor('#fef3c7')
    WARN_TXT    = colors.HexColor('#92400e')
    DANGER      = colors.HexColor('#fee2e2')
    DANGER_TXT  = colors.HexColor('#991b1b')
    FOOTER_BG   = colors.HexColor('#1e293b')

    pw, ph = landscape(A4)
    margin = 1.8 * cm
    content_w = pw - 2 * margin

    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=landscape(A4),
        topMargin=margin, bottomMargin=margin,
        leftMargin=margin, rightMargin=margin)

    styles = getSampleStyleSheet()

    def ps(name, **kw):
        return ParagraphStyle(name, parent=styles['Normal'], **kw)

    cell    = ps('cell',   fontSize=8,  leading=10, fontName='Helvetica')
    cell_b  = ps('cellb',  fontSize=8,  leading=10, fontName='Helvetica-Bold')
    cell_r  = ps('cellr',  fontSize=8,  leading=10, fontName='Helvetica',      alignment=TA_RIGHT)
    cell_c  = ps('cellc',  fontSize=8,  leading=10, fontName='Helvetica',      alignment=TA_CENTER)
    hdr_c   = ps('hdrc',   fontSize=8,  leading=10, fontName='Helvetica-Bold', alignment=TA_CENTER, textColor=WHITE)
    title   = ps('title',  fontSize=22, leading=26, fontName='Helvetica-Bold', textColor=colors.HexColor('#1e3a5f'), spaceAfter=2)
    subtitle= ps('sub',    fontSize=9,  leading=12, fontName='Helvetica',      textColor=SLATE, spaceAfter=0)
    section = ps('sec',    fontSize=11, leading=14, fontName='Helvetica-Bold', textColor=colors.HexColor('#1e3a5f'), spaceBefore=16, spaceAfter=6)
    footer  = ps('foot',   fontSize=7,  leading=9,  fontName='Helvetica',      textColor=MUTED, alignment=TA_RIGHT)

    elements = []
    now_str = datetime.now().strftime("%d/%m/%Y %H:%M")

    # Determinar grupos
    if tipo == 'general':
        titulo = 'Inventario General'
        articulos_q = Articulo.query.order_by(Articulo.nombre).all()
        grupos = [('', articulos_q)]
    elif tipo == 'salones':
        titulo = 'Inventario por Salones'
        locs = Ubicacion.query.filter_by(tipo='salon').order_by(Ubicacion.nombre).all()
        grupos = [(loc.nombre, Articulo.query.filter_by(ubicacion_id=loc.id).order_by(Articulo.nombre).all()) for loc in locs]
        sin_ub = Articulo.query.filter_by(ubicacion_id=None).all()
        if sin_ub: grupos.append(('Sin ubicación', sin_ub))
    elif tipo == 'bodegas':
        titulo = 'Inventario por Bodegas'
        locs = Ubicacion.query.filter_by(tipo='bodega').order_by(Ubicacion.nombre).all()
        grupos = [(loc.nombre, Articulo.query.filter_by(ubicacion_id=loc.id).order_by(Articulo.nombre).all()) for loc in locs]
    elif tipo == 'ubicacion' and ubicacion_id:
        loc = Ubicacion.query.get_or_404(ubicacion_id)
        titulo = f'Inventario — {loc.nombre}'
        articulos_q = Articulo.query.filter_by(ubicacion_id=ubicacion_id).order_by(Articulo.nombre).all()
        grupos = [(loc.nombre, articulos_q)]
    else:
        titulo = 'Inventario General'
        articulos_q = Articulo.query.order_by(Articulo.nombre).all()
        grupos = [('', articulos_q)]

    total_general = sum(a.cantidad for g, arts in grupos for a in arts)
    monto_general = sum(a.total    for g, arts in grupos for a in arts)
    num_articulos = sum(len(arts)  for g, arts in grupos)

    # ── ENCABEZADO ──
    # Barra de color superior
    barra = Table([['']], colWidths=[content_w])
    barra.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), INDIGO),
        ('TOPPADDING',    (0,0), (-1,-1), 4),
        ('BOTTOMPADDING', (0,0), (-1,-1), 4),
    ]))
    elements.append(barra)
    elements.append(Spacer(1, 10))

    # Título + meta
    elements.append(Paragraph(titulo, title))
    elements.append(Paragraph(
        f'Generado el {now_str}  •  '
        f'Total artículos: <b>{num_articulos}</b>  •  '
        f'Total piezas: <b>{total_general}</b>  •  '
        f'Importe total: <b>${monto_general:,.2f}</b>',
        subtitle))
    elements.append(Spacer(1, 10))
    elements.append(HRFlowable(width=content_w, thickness=1.5, color=colors.HexColor('#1e3a5f'), spaceAfter=14))

    # ── COLUMNAS ──
    # #, Tipo, Cant, Nombre/Desc, Categoría, P.Unit, Total, Núm.Inv, Tipo Adq, Estado, Ubicación
    col_w = [
        0.55*cm,  # #
        1.7*cm,   # Tipo
        0.9*cm,   # Cant
        5.8*cm,   # Nombre
        2.2*cm,   # Categoría
        1.6*cm,   # P.Unit
        1.6*cm,   # Total
        2.6*cm,   # Núm.Inv
        2.8*cm,   # Tipo Adq
        1.5*cm,   # Estado
        2.2*cm,   # Ubicación
    ]

    hdrs = ['#','Tipo','Cant.','Nombre / Descripción','Categoría',
            'P. Unit.','Total','Núm. Inventario','Tipo Adquisición','Estado','Ubicación']

    for grupo_nombre, articulos in grupos:
        if not articulos:
            continue

        if grupo_nombre:
            elements.append(Paragraph(f'📍 {grupo_nombre}  ({len(articulos)} artículos)', section))

        data = [[Paragraph(h, hdr_c) for h in hdrs]]
        total_grupo = 0

        for i, a in enumerate(articulos, 1):
            ta = a.total
            total_grupo += ta

            # Color del estado
            desc_text = f'<b>{a.nombre}</b>'
            if a.descripcion:
                desc_text += f'<br/><font size="7" color="#64748b">{a.descripcion[:70]}</font>'

            data.append([
                Paragraph(str(i),                     cell_c),
                Paragraph(a.tipo_bien or '—',         cell_c),
                Paragraph(str(a.cantidad),             cell_c),
                Paragraph(desc_text,                   cell),
                Paragraph(a.categoria or '—',          cell_c),
                Paragraph(f'${a.precio_unitario:,.2f}' if a.precio_unitario else '—', cell_r),
                Paragraph(f'${ta:,.2f}' if ta else '—', cell_r),
                Paragraph(a.numero_inventario or '—',  cell_c),
                Paragraph(a.tipo_adquisicion or '—',   cell),
                Paragraph(a.estado,                    cell_c),
                Paragraph(a.ubicacion.nombre if a.ubicacion else '—', cell),
            ])

        # Fila subtotal
        bold_c = ps(f'bc{id(articulos)}', fontSize=8, leading=10, fontName='Helvetica-Bold', alignment=TA_CENTER)
        bold_r = ps(f'br{id(articulos)}', fontSize=8, leading=10, fontName='Helvetica-Bold', alignment=TA_RIGHT)
        bold_l = ps(f'bl{id(articulos)}', fontSize=8, leading=10, fontName='Helvetica-Bold')
        data.append([
            Paragraph('', cell),
            Paragraph('', cell),
            Paragraph(str(sum(a.cantidad for a in articulos)), bold_c),
            Paragraph(f'{len(articulos)} artículos en total', bold_l),
            Paragraph('', cell), Paragraph('', cell),
            Paragraph(f'${total_grupo:,.2f}', bold_r),
            Paragraph('', cell), Paragraph('', cell),
            Paragraph('', cell), Paragraph('', cell),
        ])

        tabla = Table(data, colWidths=col_w, repeatRows=1)

        # Determinar filas por estado para colorear
        style_cmds = [
            ('BACKGROUND',    (0,0),  (-1,0),  INDIGO_DARK),
            ('TEXTCOLOR',     (0,0),  (-1,0),  WHITE),
            ('FONTNAME',      (0,0),  (-1,0),  'Helvetica-Bold'),
            ('FONTSIZE',      (0,0),  (-1,0),  8),
            ('VALIGN',        (0,0),  (-1,-1), 'MIDDLE'),
            ('ALIGN',         (0,0),  (-1,0),  'CENTER'),
            ('TOPPADDING',    (0,0),  (-1,0),  8),
            ('BOTTOMPADDING', (0,0),  (-1,0),  8),
            ('FONTNAME',      (0,1),  (-1,-1), 'Helvetica'),
            ('FONTSIZE',      (0,1),  (-1,-1), 8),
            ('TOPPADDING',    (0,1),  (-1,-1), 5),
            ('BOTTOMPADDING', (0,1),  (-1,-1), 5),
            ('GRID',          (0,0),  (-1,-1), 0.3, BORDER),
            ('LINEBELOW',     (0,0),  (-1,0),  1.5, colors.HexColor('#1e3a5f')),
            ('ROWBACKGROUNDS',(0,1),  (-1,-2), [WHITE, ALT]),
            # Fila total
            ('BACKGROUND',    (0,-1), (-1,-1), colors.HexColor('#e8edf5')),
            ('FONTNAME',      (0,-1), (-1,-1), 'Helvetica-Bold'),
            ('LINEABOVE',     (0,-1), (-1,-1), 1, colors.HexColor('#1e3a5f')),
            ('LINEBELOW',     (0,-1), (-1,-1), 1.5, colors.HexColor('#0f2744')),
        ]

        # Colorear estado por fila
        for row_idx, (_, a) in enumerate([(None, None)] + [(None, a) for a in articulos], 0):
            if row_idx == 0 or a is None:
                continue
            if a.estado == 'Bueno':
                style_cmds.append(('TEXTCOLOR', (9, row_idx), (9, row_idx), SUCCESS_TXT))
                style_cmds.append(('BACKGROUND', (9, row_idx), (9, row_idx), SUCCESS))
            elif a.estado == 'Regular':
                style_cmds.append(('TEXTCOLOR', (9, row_idx), (9, row_idx), WARN_TXT))
                style_cmds.append(('BACKGROUND', (9, row_idx), (9, row_idx), WARN))
            elif a.estado == 'Malo':
                style_cmds.append(('TEXTCOLOR', (9, row_idx), (9, row_idx), DANGER_TXT))
                style_cmds.append(('BACKGROUND', (9, row_idx), (9, row_idx), DANGER))

        tabla.setStyle(TableStyle(style_cmds))
        elements.append(tabla)
        elements.append(Spacer(1, 8))

    # ── PIE ──
    elements.append(Spacer(1, 8))
    elements.append(HRFlowable(width=content_w, thickness=0.5, color=BORDER, spaceAfter=6))
    elements.append(Paragraph(
        f'Escuela Mariano Escobedo  •  Sistema de Inventario Escolar  •  {now_str}',
        footer))

    doc.build(elements)
    buffer.seek(0)
    nombre_archivo = f"inventario_{tipo}_{datetime.now().strftime('%Y%m%d')}.pdf"
    return send_file(buffer, mimetype='application/pdf',
                     as_attachment=False, download_name=nombre_archivo)

# --- EXPORTAR PDF FORMATO OFICIAL (TARJETÓN DE BIENES) ---
@inventario_bp.route('/exportar-pdf-oficial')
@require_login
def exportar_pdf_oficial():
    from reportlab.lib.pagesizes import landscape, letter
    from reportlab.lib import colors
    from reportlab.lib.units import cm, inch
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image as RLImage
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
    import os

    tipo         = request.args.get('tipo', 'general')
    ubicacion_id = request.args.get('ubicacion_id')

    # Obtener artículos según filtro
    if tipo == 'ubicacion' and ubicacion_id:
        loc       = Ubicacion.query.get_or_404(ubicacion_id)
        articulos = Articulo.query.filter_by(ubicacion_id=ubicacion_id).order_by(Articulo.nombre).all()
    elif tipo == 'salones':
        articulos = Articulo.query.join(Ubicacion).filter(Ubicacion.tipo == 'salon').order_by(Articulo.nombre).all()
    elif tipo == 'bodegas':
        articulos = Articulo.query.join(Ubicacion).filter(Ubicacion.tipo == 'bodega').order_by(Articulo.nombre).all()
    else:
        articulos = Articulo.query.order_by(Articulo.nombre).all()

    total_bienes  = sum(a.cantidad for a in articulos)
    importe_total = sum(a.total for a in articulos)

    # Colores
    GRIS_HDR = colors.HexColor('#D9D9D9')
    NEGRO    = colors.black
    BLANCO   = colors.white
    GRIS_ALT = colors.HexColor('#F5F5F5')

    buffer = BytesIO()
    pw, ph = landscape(letter)
    margin = 0.5 * inch
    doc = SimpleDocTemplate(
        buffer,
        pagesize=landscape(letter),
        topMargin=margin, bottomMargin=margin,
        leftMargin=margin, rightMargin=margin
    )

    styles     = getSampleStyleSheet()
    cell_c     = ParagraphStyle('cc', fontName='Helvetica',      fontSize=7,  alignment=TA_CENTER, leading=9)
    cell_l     = ParagraphStyle('cl', fontName='Helvetica',      fontSize=7,  alignment=TA_LEFT,   leading=9)
    cell_r     = ParagraphStyle('cr', fontName='Helvetica',      fontSize=7,  alignment=TA_RIGHT,  leading=9)
    hdr_bold_c = ParagraphStyle('hbc',fontName='Helvetica-Bold', fontSize=8,  alignment=TA_CENTER, leading=10)
    hdr_bold_l = ParagraphStyle('hbl',fontName='Helvetica-Bold', fontSize=8,  alignment=TA_LEFT,   leading=10)
    inst_title = ParagraphStyle('it', fontName='Helvetica-Bold', fontSize=9,  alignment=TA_CENTER, leading=11)
    inst_big   = ParagraphStyle('ib', fontName='Helvetica-Bold', fontSize=16, alignment=TA_CENTER, leading=18, spaceAfter=2)
    inst_info  = ParagraphStyle('ii', fontName='Helvetica',      fontSize=8,  alignment=TA_LEFT,   leading=11)
    inst_info_b= ParagraphStyle('iib',fontName='Helvetica-Bold', fontSize=8,  alignment=TA_LEFT,   leading=11)
    date_style = ParagraphStyle('ds', fontName='Helvetica',      fontSize=8,  alignment=TA_RIGHT,  leading=10)

    elements = []
    content_w = pw - 2 * margin

    # ── LOGO ──
    logo_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'logo_iebem.png')
    # Fallback: try relative path
    if not os.path.exists(logo_path):
        logo_path = 'logo_iebem.png'

    logo_h = 0.75 * inch
    logo_w = logo_h * (963 / 299)  # maintain aspect ratio

    # ── ENCABEZADO: 3 columnas [logo | titulo central | fecha] ──
    col_logo  = logo_w + 0.1*inch
    col_fecha = 1.5 * inch
    col_titulo = content_w - col_logo - col_fecha

    try:
        logo_img = RLImage(logo_path, width=logo_w, height=logo_h)
        logo_cell = logo_img
    except Exception:
        logo_cell = Paragraph('IEBEM', hdr_bold_c)

    hdr_data = [[
        logo_cell,
        [
            Paragraph('DIRECCION DE ADMINISTRACION', inst_title),
            Paragraph('DEPARTAMENTO DE ADQUISICIONES', inst_title),
            Paragraph('TARJETÓN DE BIENES', inst_big),
        ],
        Paragraph(datetime.now().strftime('%d de %B de %Y')
            .replace('January','enero').replace('February','febrero').replace('March','marzo')
            .replace('April','abril').replace('May','mayo').replace('June','junio')
            .replace('July','julio').replace('August','agosto').replace('September','septiembre')
            .replace('October','octubre').replace('November','noviembre').replace('December','diciembre'),
            date_style),
    ]]

    hdr_table = Table(hdr_data, colWidths=[col_logo, col_titulo, col_fecha])
    hdr_table.setStyle(TableStyle([
        ('VALIGN',        (0,0), (-1,-1), 'MIDDLE'),
        ('TOPPADDING',    (0,0), (-1,-1), 4),
        ('BOTTOMPADDING', (0,0), (-1,-1), 4),
        ('LEFTPADDING',   (0,0), (-1,-1), 6),
        ('RIGHTPADDING',  (0,0), (-1,-1), 6),
        ('ALIGN',         (0,0), (0,0),   'CENTER'),
        ('ALIGN',         (1,0), (1,0),   'CENTER'),
        ('ALIGN',         (2,0), (2,0),   'RIGHT'),
    ]))
    elements.append(hdr_table)

    # ── DATOS DE LA ESCUELA ──
    escuela_data = [[
        Paragraph('<b>Centro de Trabajo:</b>  17DPR01938 - MARIANO ESCOBEDO', inst_info),
        Paragraph(f'<b>TOTAL DE BIENES:</b>  {total_bienes}', inst_info),
    ],[
        Paragraph('<b>U. Administrativa:</b>  3090 - MARIANO ESCOBEDO', inst_info),
        Paragraph(f'<b>IMPORTE TOTAL DE BIENES</b>  ${importe_total:,.2f}', inst_info),
    ],[
        Paragraph('<b>Dirección:</b>  CALLE PIO QUINTO GALIZ 6 ZACATEPEC 62780 ZACATEPEC DE HIDALGO', inst_info),
        Paragraph('', inst_info),
    ]]

    esc_table = Table(escuela_data, colWidths=[content_w * 0.6, content_w * 0.4])
    esc_table.setStyle(TableStyle([
        ('TOPPADDING',    (0,0), (-1,-1), 2),
        ('BOTTOMPADDING', (0,0), (-1,-1), 2),
        ('LEFTPADDING',   (0,0), (-1,-1), 4),
        ('RIGHTPADDING',  (0,0), (-1,-1), 4),
        ('LINEBELOW',     (0,-1), (-1,-1), 0.5, NEGRO),
    ]))
    elements.append(esc_table)
    elements.append(Spacer(1, 4))

    # ── TABLA PRINCIPAL ──
    # NUMERO DE INVENTARIO dividido en 2 sub-columnas (~9 dígitos cada una)
    # TIPO:900, CANT:550, DESC:3800, P.UNIT:800, TOTAL:800, NUM1:1250, NUM2:1250, TIPO.ADQ:2050
    total_dxa = 900+550+3800+800+800+1250+1250+2050
    col_w = [content_w * (x/total_dxa) for x in [900,550,3800,800,800,1250,1250,2050]]

    # Fila 1: encabezados normales + NUMERO DE INVENTARIO hace span de 2 cols
    # Usamos una tabla anidada para el header con span
    from reportlab.platypus import TableStyle as TS

    header_row = [
        Paragraph('<b>TIPO</b>',                    hdr_bold_c),
        Paragraph('<b>CANT</b>',                    hdr_bold_c),
        Paragraph('<b>DESCRIPCION DEL BIEN</b>',    hdr_bold_c),
        Paragraph('<b>PRECIO<br/>UNIT.</b>',        hdr_bold_c),
        Paragraph('<b>TOTAL</b>',                   hdr_bold_c),
        Paragraph('<b>NUMERO DE INVENTARIO</b>',    hdr_bold_c),
        Paragraph('',                               hdr_bold_c),
        Paragraph('<b>TIPO<br/>ADQUISICION</b>',    hdr_bold_c),
    ]
    data = [header_row]

    for a in articulos:
        desc = a.nombre
        if a.descripcion:
            desc += f'<br/><font size="6" color="#555555">{a.descripcion[:80]}</font>'
        # Dividir numero_inventario en dos mitades si es largo
        num_inv = a.numero_inventario or ''
        mid = len(num_inv) // 2 if len(num_inv) > 9 else len(num_inv)
        num1 = num_inv[:mid] if len(num_inv) > 9 else num_inv
        num2 = num_inv[mid:] if len(num_inv) > 9 else ''
        data.append([
            Paragraph(a.tipo_bien or '',    cell_c),
            Paragraph(str(a.cantidad),      cell_c),
            Paragraph(desc,                 cell_l),
            Paragraph(f'${a.precio_unitario:,.2f}' if a.precio_unitario else '', cell_r),
            Paragraph(f'${a.total:,.2f}'    if a.total else '',                  cell_r),
            Paragraph(num1,                 cell_c),
            Paragraph(num2,                 cell_c),
            Paragraph(a.tipo_adquisicion or '', cell_l),
        ])

    tabla = Table(data, colWidths=col_w, repeatRows=1)
    tabla.setStyle(TableStyle([
        ('BACKGROUND',    (0,0), (-1,0), GRIS_HDR),
        ('FONTNAME',      (0,0), (-1,0), 'Helvetica-Bold'),
        ('FONTSIZE',      (0,0), (-1,0), 8),
        ('ALIGN',         (0,0), (-1,0), 'CENTER'),
        ('VALIGN',        (0,0), (-1,-1), 'MIDDLE'),
        ('TOPPADDING',    (0,0), (-1,0), 5),
        ('BOTTOMPADDING', (0,0), (-1,0), 5),
        ('FONTNAME',      (0,1), (-1,-1), 'Helvetica'),
        ('FONTSIZE',      (0,1), (-1,-1), 7),
        ('TOPPADDING',    (0,1), (-1,-1), 3),
        ('BOTTOMPADDING', (0,1), (-1,-1), 3),
        ('GRID',          (0,0), (-1,-1), 0.5, NEGRO),
        ('ROWBACKGROUNDS',(0,1), (-1,-1), [BLANCO, GRIS_ALT]),
        # Span de "NUMERO DE INVENTARIO" sobre las 2 sub-columnas en el header
        ('SPAN',          (5,0), (6,0)),
    ]))
    elements.append(tabla)

    doc.build(elements)
    buffer.seek(0)
    nombre_archivo = f"tarjeton_bienes_{tipo}_{datetime.now().strftime('%Y%m%d')}.pdf"
    return send_file(buffer, mimetype='application/pdf',
                     as_attachment=False, download_name=nombre_archivo)