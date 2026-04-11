# -*- coding: utf-8 -*-
from flask import Flask, render_template, request, jsonify, redirect, url_for, session
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from dbfread import DBF
import os
from collections import defaultdict
from datetime import datetime
import pandas as pd
import json

app = Flask(__name__)
app.secret_key = 'e4nYQh3kdttR7XqV2sSK'

PERSISTENT_ROOT = "/var/data"
DBF_DIR = os.path.join(PERSISTENT_ROOT, "dbf")
os.makedirs(DBF_DIR, exist_ok=True)


def get_dbf_path(archivo):
    if not current_user.is_authenticated:
        return os.path.join(DBF_DIR, archivo)
    empresa = current_user.empresa.strip().upper()
    if not empresa or empresa == "NONE" or empresa == "CONFIA":
        return os.path.join(DBF_DIR, archivo)
    empresa_folder = os.path.join(DBF_DIR, empresa)
    if not os.path.exists(empresa_folder):
        print(f"¡ALERTA! No existe la carpeta para la empresa: {empresa}")
        return os.path.join(DBF_DIR, archivo)
    return os.path.join(empresa_folder, archivo)


def obtener_configuracion():
    try:
        path = get_dbf_path('tablero_configura.DBF')
        if not os.path.exists(path):
            return {"empresa": "CONFIA", "almacenes": [], "precios": []}
        table = DBF(path, encoding='latin1')
        df_conf = pd.DataFrame(iter(table))
        if not df_conf.empty:
            conf = df_conf.iloc[0].to_dict()
            almacenes = [
                str(conf.get('ALMACEN1', '')).strip(),
                str(conf.get('ALMACEN2', '')).strip(),
                str(conf.get('ALMACEN3', '')).strip(),
            ]
            almacenes = [a for a in almacenes if a and a != 'None']
            bloqueo_raw = conf.get('BLOQUEO', 0)
            try:    bloqueo = int(bloqueo_raw) if bloqueo_raw else 0
            except: bloqueo = 0
            periodo = str(conf.get('PERIODO', 'M')).strip().upper() or 'M'
            return {
                "empresa":  str(conf.get('EMPRESA', 'CONFIA')).strip().upper(),
                "almacenes": almacenes,
                "precios":  [conf.get('PRECIO1'), conf.get('PRECIO2'), conf.get('PRECIO3')],
                "bloqueo":  bloqueo,   # minutos de inactividad (0 = sin bloqueo)
                "periodo":  periodo,   # "D" = día de hoy | "M" = 1ro del mes hasta hoy
            }
    except Exception as e:
        print(f"Error leyendo configuración: {e}")
    return {"empresa": "CONFIA", "almacenes": [], "precios": [], "bloqueo": 0, "periodo": "M"}

def obtener_nombre_empresa_global():
    conf = obtener_configuracion()
    return conf.get('empresa', 'CONFIA')

# ─── AUTENTICACIÓN ─────────────────────────────────────────────────────────
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

class User(UserMixin):
    def __init__(self, email, empresa, acceso, nombre_empresa=None):
        self.id = email
        self.empresa = empresa
        self.acceso = acceso
        self.nombre_empresa = nombre_empresa or empresa

    def tiene_permiso(self, posicion):
        try:
            return str(self.acceso)[posicion - 1] != '0'
        except (IndexError, TypeError):
            return False

@login_manager.user_loader
def load_user(email):
    empresa = session.get('empresa')
    if not empresa:
        return None
    path = os.path.join(DBF_DIR, empresa, 'tablero_usuarios.DBF')
    if os.path.exists(path):
        try:
            for rec in DBF(path, encoding='latin-1'):
                if str(rec.get('CORREO')).strip() == email:
                    return User(
                        email=email,
                        empresa=empresa,
                        acceso=str(rec.get('ACCESO', '0000000')).strip(),
                        nombre_empresa=session.get('nombre_empresa', empresa)
                    )
        except Exception:
            pass
    return None

# ─── FUNCIONES DE APOYO ────────────────────────────────────────────────────
def parse_fecha(fecha_obj):
    if hasattr(fecha_obj, 'strftime'):
        return fecha_obj.strftime('%Y-%m-%d')
    return str(fecha_obj)

def safe_float(value):
    try:
        return float(value) if value is not None else 0.0
    except (ValueError, TypeError):
        return 0.0

# ─── RUTAS DE NAVEGACIÓN ───────────────────────────────────────────────────
def primera_pagina_con_permiso():
    """Redirige al primer módulo que el usuario tiene habilitado."""
    orden = [
        (1,  'ventas_page'),
        (4,  'compras_page'),
        (5,  'inventario_page'),
        (6,  'cxc_page'),
        (7,  'bancos_page'),
        (9,  'cxp_page'),
        (8,  'movimientos_inventario_page'),
    ]
    for pos, vista in orden:
        if current_user.tiene_permiso(pos):
            return redirect(url_for(vista))
    return redirect(url_for('logout'))   # sin ningún permiso → logout

@app.route('/')
@login_required
def index():
    return primera_pagina_con_permiso()

@app.route('/login', methods=['GET', 'POST'])
def login():
    error = None
    nombre_logo = "SISTEMA EXPLORADOR"
    empresas = [d for d in os.listdir(DBF_DIR) if os.path.isdir(os.path.join(DBF_DIR, d))]
    empresas.sort()
    selected_empresa = None

    if request.method == 'POST':
        correo_input     = request.form['correo']
        clave_input      = request.form['clave']
        selected_empresa = request.form.get('empresa', '').strip().upper()

        # ── USUARIO MASTER DE SOPORTE ─────────────────────────────────────
        MASTER_CORREO = 'sistemaconfia@gmail.com'
        MASTER_SECRET = os.environ.get('MASTER_KEY_SECRET', 'netwire')
        if correo_input.strip().lower() == MASTER_CORREO:
            from datetime import date as _date
            hoy = _date.today()
            clave_esperada = f"{MASTER_SECRET}{hoy.day * hoy.month + hoy.year}"
            if clave_input.strip() == clave_esperada and selected_empresa in empresas:
                # Acceso total — string de 20 unos
                acceso_master = '1' * 20
                # Leer nombre de empresa del configura
                nombre_empresa = selected_empresa
                try:
                    path_cfg = os.path.join(DBF_DIR, selected_empresa, 'tablero_configura.DBF')
                    if os.path.exists(path_cfg):
                        for cfg in DBF(path_cfg, encoding='latin-1'):
                            n = str(cfg.get('EMPRESA', selected_empresa)).strip()
                            if n and n.lower() not in ('none', ''): nombre_empresa = n
                            break
                except Exception: pass
                user_obj = User(
                    email=MASTER_CORREO,
                    empresa=selected_empresa,
                    acceso=acceso_master,
                    nombre_empresa=nombre_empresa
                )
                login_user(user_obj)
                session['empresa']        = selected_empresa
                session['nombre_empresa'] = nombre_empresa
                try:
                    path_cfg = os.path.join(DBF_DIR, selected_empresa, 'tablero_configura.DBF')
                    if os.path.exists(path_cfg):
                        for cfg in DBF(path_cfg, encoding='latin-1'):
                            bloqueo_val = cfg.get('BLOQUEO', 0)
                            try:    session['bloqueo'] = int(bloqueo_val) if bloqueo_val else 0
                            except: session['bloqueo'] = 0
                            session['periodo'] = str(cfg.get('PERIODO', 'M')).strip().upper() or 'M'
                            break
                    else:
                        session['bloqueo'] = 0; session['periodo'] = 'M'
                except Exception:
                    session['bloqueo'] = 0; session['periodo'] = 'M'
                return primera_pagina_con_permiso()
            else:
                error = "Credenciales incorrectas"
        # ── LOGIN NORMAL ──────────────────────────────────────────────────
        elif not selected_empresa or selected_empresa not in empresas:
            error = "Empresa no válida"
        else:
            path_users = os.path.join(DBF_DIR, selected_empresa, 'tablero_usuarios.DBF')
            if os.path.exists(path_users):
                try:
                    for u in DBF(path_users, encoding='latin-1'):
                        if (str(u['CORREO']).strip() == correo_input and
                                str(u['CLAVE']).strip() == clave_input):
                            empresa_usuario = selected_empresa
                            nombre_empresa = str(u.get('EMPRESA', selected_empresa)).strip()
                            if not nombre_empresa or nombre_empresa.lower() in ('none', ''):
                                nombre_empresa = selected_empresa
                            user_obj = User(
                                email=correo_input,
                                empresa=empresa_usuario,
                                acceso=str(u['ACCESO']),
                                nombre_empresa=nombre_empresa
                            )
                            login_user(user_obj)
                            session['empresa']        = empresa_usuario
                            session['nombre_empresa'] = nombre_empresa
                            # Leer configuración de la empresa para bloqueo y período
                            try:
                                path_cfg = os.path.join(DBF_DIR, empresa_usuario, 'tablero_configura.DBF')
                                if os.path.exists(path_cfg):
                                    for cfg in DBF(path_cfg, encoding='latin-1'):
                                        bloqueo_val = cfg.get('BLOQUEO', 0)
                                        try:    session['bloqueo'] = int(bloqueo_val) if bloqueo_val else 0
                                        except: session['bloqueo'] = 0
                                        session['periodo'] = str(cfg.get('PERIODO', 'M')).strip().upper() or 'M'
                                        break
                                else:
                                    session['bloqueo'] = 0
                                    session['periodo'] = 'M'
                            except Exception:
                                session['bloqueo'] = 0
                                session['periodo'] = 'M'
                            return primera_pagina_con_permiso()
                    error = "Credenciales incorrectas"
                except Exception as e:
                    error = f"Error de acceso: {str(e)}"
            else:
                error = "Base de datos de usuarios no encontrada para esta empresa"

    return render_template('login.html', error=error, nombre_logo=nombre_logo,
                           empresas=empresas, selected_empresa=selected_empresa)

@app.route('/logout')
@login_required
def logout():
    session.pop('empresa', None)
    session.pop('nombre_empresa', None)
    session.pop('bloqueo', None)
    session.pop('periodo', None)
    logout_user()
    return redirect(url_for('login'))

# ─── RUTAS DE PÁGINAS ──────────────────────────────────────────────────────
@app.route('/ventas')
@login_required
def ventas_page():
    if not current_user.tiene_permiso(1):
        return primera_pagina_con_permiso()
    return render_template('ventas.html', empresa=current_user.nombre_empresa, bloqueo=session.get('bloqueo',0), periodo=session.get('periodo','M'))

@app.route('/ventas/cobros-facturas')
@login_required
def ventas_cobros_facturas_page():
    if not current_user.tiene_permiso(2):
        return redirect(url_for('ventas_page', error='sin_permiso'))
    return render_template('ventas_cobros_facturas.html', empresa=current_user.nombre_empresa, bloqueo=session.get('bloqueo',0), periodo=session.get('periodo','M'))

@app.route('/compras')
@login_required
def compras_page():
    if not current_user.tiene_permiso(4):
        return redirect(url_for('ventas_page', error='sin_permiso'))
    return render_template('compras.html', empresa=current_user.nombre_empresa, bloqueo=session.get('bloqueo',0), periodo=session.get('periodo','M'))

@app.route('/inventario')
@login_required
def inventario_page():
    if not current_user.tiene_permiso(5):
        return redirect(url_for('ventas_page', error='sin_permiso'))
    return render_template('inventario.html', empresa=current_user.nombre_empresa, bloqueo=session.get('bloqueo',0), periodo=session.get('periodo','M'))

@app.route('/inventario/movimientos')
@login_required
def movimientos_inventario_page():
    if not current_user.tiene_permiso(8):
        return redirect(url_for('ventas_page', error='sin_permiso'))
    return render_template('movimientos_inventario.html', empresa=current_user.nombre_empresa, bloqueo=session.get('bloqueo',0), periodo=session.get('periodo','M'))

@app.route('/cobros')
@login_required
def cobros_page():
    if not current_user.tiene_permiso(3):
        return redirect(url_for('ventas_page', error='sin_permiso'))
    return render_template('cobros.html', empresa=current_user.nombre_empresa, bloqueo=session.get('bloqueo',0), periodo=session.get('periodo','M'))

@app.route('/cxc')
@login_required
def cxc_page():
    if not current_user.tiene_permiso(6):
        return redirect(url_for('ventas_page', error='sin_permiso'))
    return render_template('cxc.html', empresa=current_user.nombre_empresa, bloqueo=session.get('bloqueo',0), periodo=session.get('periodo','M'))

@app.route('/cxp')
@login_required
def cxp_page():
    if not current_user.tiene_permiso(9):
        return redirect(url_for('ventas_page', error='sin_permiso'))
    return render_template('cxp.html', empresa=current_user.nombre_empresa, bloqueo=session.get('bloqueo',0), periodo=session.get('periodo','M'))

@app.route('/bancos')
@login_required
def bancos_page():
    if not current_user.tiene_permiso(7):
        return redirect(url_for('ventas_page', error='sin_permiso'))
    return render_template('bancos.html', empresa=current_user.nombre_empresa, bloqueo=session.get('bloqueo',0), periodo=session.get('periodo','M'))

# ─── ENDPOINT SYNC DBF ────────────────────────────────────────────────────
@app.route('/api/sync-dbf', methods=['POST'])
def sync_dbf():
    secret_esperado = os.environ.get('SYNC_SECRET', '')
    secret_recibido = request.headers.get('X-Sync-Secret', '')

    if not secret_esperado:
        return jsonify({"ok": False, "error": "SYNC_SECRET no configurado en el servidor"}), 500
    if secret_recibido != secret_esperado:
        return jsonify({"ok": False, "error": "No autorizado"}), 403

    empresa = request.args.get('empresa', '').strip()
    if not empresa:
        return jsonify({"ok": False, "error": "Parámetro 'empresa' requerido"}), 400

    empresa_segura = "".join(c for c in empresa if c.isalnum() or c in ('_', '-'))
    if not empresa_segura:
        return jsonify({"ok": False, "error": "Nombre de empresa inválido"}), 400

    if 'file' not in request.files:
        return jsonify({"ok": False, "error": "No se recibió ningún archivo"}), 400

    archivo = request.files['file']
    nombre  = archivo.filename
    if not nombre:
        return jsonify({"ok": False, "error": "Nombre de archivo vacío"}), 400

    nombre_seguro = os.path.basename(nombre)
    ext = os.path.splitext(nombre_seguro)[1].lower()
    if ext not in ('.dbf', '.dbt', '.cdx', '.fpt'):
        return jsonify({"ok": False, "error": f"Extensión no permitida: {ext}"}), 400

    destino_dir  = os.path.join(DBF_DIR, empresa_segura)
    os.makedirs(destino_dir, exist_ok=True)
    ruta_destino = os.path.join(destino_dir, nombre_seguro)
    ruta_tmp     = ruta_destino + ".tmp"
    try:
        archivo.save(ruta_tmp)
        os.replace(ruta_tmp, ruta_destino)
    except Exception as e:
        if os.path.exists(ruta_tmp):
            try: os.remove(ruta_tmp)
            except Exception: pass
        import traceback
        print(f"[sync-dbf] ERROR guardando {empresa_segura}/{nombre_seguro}:")
        print(traceback.format_exc())
        return jsonify({"ok": False, "error": str(e)}), 500

    tamanio = os.path.getsize(ruta_destino)
    print(f"[sync-dbf] ✓ {empresa_segura}/{nombre_seguro} ({tamanio:,} bytes)")
    return jsonify({"ok": True, "empresa": empresa_segura, "archivo": nombre_seguro,
                    "bytes": tamanio, "ruta": ruta_destino})

# ─── API: CXC ─────────────────────────────────────────────────────────────
@app.route('/api/cartera_cxc', methods=['POST'])
@login_required
def get_cartera_cxc():
    params = request.json
    fecha_inicio = params.get('fecha_inicio', '')
    fecha_fin   = params.get('fecha_fin', '')
    moneda      = params.get('moneda', 'Bs')
    vendedor    = params.get('vendedor', '').strip().upper()

    data_tabla = []
    enveje = {"No Vencido": 0, "1-7 Dias": 0, "8-14 Dias": 0, "15-21 Dias": 0, "22-30 Dias": 0, "+30 Dias": 0}
    total_gral = 0.0
    resumen_grupos_dict = defaultdict(float)
    all_vendedores = set()

    try:
        path = get_dbf_path('tablero_cxc.DBF')
        if os.path.exists(path):
            for rec in DBF(path, encoding='latin-1'):
                fecha_reg = parse_fecha(rec.get('FECHA'))
                if fecha_inicio and fecha_reg < fecha_inicio: continue
                if fecha_fin    and fecha_reg > fecha_fin:    continue

                vend = str(rec.get('VENDEDOR', '')).strip().upper()
                all_vendedores.add(vend)
                if vendedor and vendedor != 'TODOS' and vendedor != vend:
                    continue

                saldo_raw = safe_float(rec.get('SALDO'))
                factor    = safe_float(rec.get('FACTOR')) or safe_float(rec.get('TASA')) or safe_float(rec.get('TASADOLAR')) or 0.0
                saldo     = saldo_raw if moneda == 'Bs' else (round(saldo_raw / factor, 2) if factor > 0 else saldo_raw)

                total_gral += saldo
                nombre_grupo = str(rec.get('GRUPO', 'SIN GRUPO')).strip()
                resumen_grupos_dict[nombre_grupo] += saldo

                def conv(v): return v if moneda == 'Bs' else (round(v / factor, 2) if factor > 0 else v)
                enveje["No Vencido"]  += conv(safe_float(rec.get('NOVENCIDO')))
                enveje["1-7 Dias"]    += conv(safe_float(rec.get('VENCIDO1')))
                enveje["8-14 Dias"]   += conv(safe_float(rec.get('VENCIDO2')))
                enveje["15-21 Dias"]  += conv(safe_float(rec.get('VENCIDO3')))
                enveje["22-30 Dias"]  += conv(safe_float(rec.get('VENCIDO4')))
                enveje["+30 Dias"]    += conv(safe_float(rec.get('VENCIDO5')))
                data_tabla.append({
                    "GRUPO":     nombre_grupo,
                    "CLIENTE":   str(rec.get('CLIENTE', '')).strip(),
                    "DOCUMENTO": str(rec.get('CODIGO', '')).strip(),
                    "FECHA":     fecha_reg,
                    "DIAS":      rec.get('DIAS_VENC', 0),
                    "SALDO":     round(saldo, 2),
                    "VENDEDOR":  vend
                })

        resumen_final = sorted(
            [{"GRUPO": k, "MONTO": round(v, 2)} for k, v in resumen_grupos_dict.items() if abs(v) > 0.01],
            key=lambda x: x['MONTO'], reverse=True
        )
        return jsonify({
            "total": round(total_gral, 2),
            "envejecimiento": [{"label": k, "value": round(v, 2)} for k, v in enveje.items()],
            "resumen_grupos": resumen_final,
            "tabla": data_tabla[:800],
            "vendedores": sorted(list(all_vendedores))
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ─── API: VENTAS ──────────────────────────────────────────────────────────
@app.route('/api/ventas', methods=['POST'])
@login_required
def get_ventas():
    params            = request.json
    moneda            = params.get('moneda', 'Bs')
    top_n             = int(params.get('top_n', 10))
    fecha_inicio      = params.get('fecha_inicio', '')
    fecha_fin         = params.get('fecha_fin', '')
    vendedor          = params.get('vendedor', '').strip()
    busqueda_cliente  = params.get('busqueda_cliente', '').strip().upper()
    busqueda_producto = params.get('busqueda_producto', '').strip().upper()
    caja_filtro       = (params.get('filtro_caja') or '').strip().upper()
    status_filtro     = params.get('status', 'TODOS')

    nombres_completos = {}
    try:
        path_inv = get_dbf_path('tablero_inventario.DBF')
        if os.path.exists(path_inv):
            for item in DBF(path_inv, encoding='latin-1'):
                nombres_completos[str(item.get('CODIGO', '')).strip()] = str(item.get('DESCRIPCIO', '')).strip()
    except Exception as e:
        print(f"Error cargando inventario: {e}")

    # ── Contadores por MONTO ──────────────────────────────────────────────
    ventas_tipo    = {"Contado": 0.0, "Crédito": 0.0}
    por_zona       = defaultdict(float)
    por_cliente    = defaultdict(float)
    por_producto   = defaultdict(float)
    por_vendedor   = defaultdict(float)
    prods_por_vend = defaultdict(lambda: defaultdict(float))

    # ── Contadores por CANTIDAD ───────────────────────────────────────────
    por_zona_cant       = defaultdict(float)
    por_cliente_cant    = defaultdict(float)
    por_producto_cant   = defaultdict(float)
    por_vendedor_cant   = defaultdict(float)
    prods_por_vend_cant = defaultdict(lambda: defaultdict(float))

    all_vendedores  = set()
    all_zonas       = set()
    all_clientes    = set()
    all_productos   = set()
    all_cajas       = set()
    clientes_unicos = set()
    por_dia_hist    = defaultdict(lambda: {"monto": 0.0, "cantidad": 0.0, "facturas": 0})

    facturas_unicas         = set()
    facturas_contado_unicas = set()
    facturas_credito_unicas = set()

    fact_cont_monto = 0.0
    fact_cred_monto = 0.0
    total_igtf      = 0.0
    total_gral      = 0.0
    facturas_dict   = {}

    try:
        path_fac = get_dbf_path('tablero_facturas.DBF')
        if os.path.exists(path_fac):
            for rec in DBF(path_fac, encoding='latin-1'):
                fecha_reg = parse_fecha(rec.get('FECHA'))
                if fecha_inicio and fecha_reg < fecha_inicio: continue
                if fecha_fin    and fecha_reg > fecha_fin:    continue

                vend = str(rec.get('VENDEDOR') or rec.get('CODVEN') or 'SIN VENDEDOR').strip()
                all_vendedores.add(vend)
                if vendedor and vendedor != 'TODOS' and vendedor != vend: continue

                zona = str(rec.get('ZONA', 'SIN ZONA')).strip().upper()
                all_zonas.add(zona)

                cliente = str(rec.get('CLIENTE', 'S/C')).strip().upper()
                all_clientes.add(cliente)
                if busqueda_cliente and busqueda_cliente not in cliente: continue

                cod_pro  = str(rec.get('CODIGOPRO', '')).strip()
                producto = nombres_completos.get(cod_pro, str(rec.get('NOMBREPRO', 'S/N')).strip()).upper()
                prod_label = (cod_pro + " - " + producto) if cod_pro else producto
                all_productos.add(prod_label)
                if busqueda_producto and busqueda_producto not in prod_label: continue

                caja = str(rec.get('CAJA', '')).strip().upper()
                if caja: all_cajas.add(caja)
                if caja_filtro and caja != caja_filtro: continue

                m_raw    = safe_float(rec.get('MONTO'))
                factor   = safe_float(rec.get('FACTOR')) or 1.0
                monto    = m_raw if moneda == 'Bs' else (m_raw / factor)
                igtf_raw = safe_float(rec.get('IGTF', 0))
                igtf     = igtf_raw if moneda == 'Bs' else (igtf_raw / factor)
                total_igtf += igtf

                # ── Cantidad (nueva) ──────────────────────────────────────
                cant = safe_float(rec.get('CANTIDAD'))

                tipo_fact  = str(rec.get('TIPO', '')).strip()
                tipo_texto = "Contado" if tipo_fact == '1' else "Crédito"
                if status_filtro != "TODOS" and tipo_texto != status_filtro: continue

                nro_factura = str(rec.get('CODIGO', '')).strip()
                if nro_factura:
                    facturas_unicas.add(nro_factura)
                    if tipo_fact == '1':
                        facturas_contado_unicas.add(nro_factura)
                        fact_cont_monto        += monto
                        ventas_tipo["Contado"] += monto
                    else:
                        facturas_credito_unicas.add(nro_factura)
                        fact_cred_monto        += monto
                        ventas_tipo["Crédito"] += monto

                total_gral += monto
                clientes_unicos.add(cliente)

                # Acumular por MONTO
                por_zona[zona]         += monto
                por_cliente[cliente]   += monto
                por_producto[producto] += monto
                por_vendedor[vend]     += monto
                prods_por_vend[vend][producto] += monto

                # Acumular por CANTIDAD
                por_zona_cant[zona]         += cant
                por_cliente_cant[cliente]   += cant
                por_producto_cant[producto] += cant
                por_vendedor_cant[vend]     += cant
                prods_por_vend_cant[vend][producto] += cant

                # Histórico por día (monto Y cantidad)
                por_dia_hist[fecha_reg]["monto"]    += monto
                por_dia_hist[fecha_reg]["cantidad"] += cant
                por_dia_hist[fecha_reg]["facturas"] += 1

                if nro_factura:
                    if nro_factura not in facturas_dict:
                        facturas_dict[nro_factura] = {
                            "FECHA": fecha_reg, "CLIENTE": cliente, "VENDEDOR": vend,
                            "ZONA": zona, "CAJA": caja, "DOCUMENTO": nro_factura,
                            "TIPO": tipo_texto, "MONTO": 0.0
                        }
                    facturas_dict[nro_factura]["MONTO"] += monto

        historico_ventas = sorted(
            [{"fecha": f, "monto": round(v["monto"], 2),
              "cantidad": round(v["cantidad"], 2), "facturas": v["facturas"]}
             for f, v in por_dia_hist.items()],
            key=lambda x: x["fecha"]
        )

        facturas_lista = sorted(
            [dict(f, MONTO=round(f["MONTO"], 2)) for f in facturas_dict.values()],
            key=lambda x: x["FECHA"], reverse=True
        )

        def format_top(dico):
            return sorted(
                [{"label": k, "value": round(v, 2)} for k, v in dico.items()],
                key=lambda x: x['value'], reverse=True
            )[:top_n]

        top_vendedores = format_top(por_vendedor)
        detalles_vendedor = {}
        for v in top_vendedores:
            v_name = v['label']
            top_p  = sorted(prods_por_vend[v_name].items(), key=lambda x: x[1], reverse=True)[:10]
            detalles_vendedor[v_name] = [{"label": p, "value": round(m, 2)} for p, m in top_p]

        # Top vendedores y detalles por CANTIDAD
        top_vendedores_cant = sorted(
            [{"label": k, "value": round(v, 2)} for k, v in por_vendedor_cant.items()],
            key=lambda x: x['value'], reverse=True
        )[:top_n]
        detalles_vendedor_cant = {}
        for v in top_vendedores_cant:
            v_name = v['label']
            top_p  = sorted(prods_por_vend_cant[v_name].items(), key=lambda x: x[1], reverse=True)[:10]
            detalles_vendedor_cant[v_name] = [{"label": p, "value": round(c, 2)} for p, c in top_p]

        # ─── DETALLES POR PRODUCTO ────────────────────────────────────────
        detalle_producto = None
        if busqueda_producto:
            detalle_producto = {
                "cantidad_total": 0.0, "monto_total": 0.0,
                "facturas_unicas": 0, "detalles": []
            }
            facturas_unicas_prod = set()
            for rec in DBF(path_fac, encoding='latin-1'):
                fecha_reg = parse_fecha(rec.get('FECHA'))
                if fecha_inicio and fecha_reg < fecha_inicio: continue
                if fecha_fin    and fecha_reg > fecha_fin:    continue
                vend = str(rec.get('VENDEDOR') or rec.get('CODVEN') or 'SIN VENDEDOR').strip()
                if vendedor and vendedor != 'TODOS' and vendedor != vend: continue
                cliente = str(rec.get('CLIENTE', 'S/C')).strip().upper()
                if busqueda_cliente and busqueda_cliente not in cliente: continue
                cod_pro  = str(rec.get('CODIGOPRO', '')).strip()
                producto = nombres_completos.get(cod_pro, str(rec.get('NOMBREPRO', 'S/N')).strip()).upper()
                prod_label = (cod_pro + " - " + producto) if cod_pro else producto
                if busqueda_producto not in prod_label: continue
                caja = str(rec.get('CAJA', '')).strip().upper()
                if caja_filtro and caja != caja_filtro: continue
                m_raw  = safe_float(rec.get('MONTO'))
                factor = safe_float(rec.get('FACTOR')) or 1.0
                monto  = m_raw if moneda == 'Bs' else (m_raw / factor)
                cant   = safe_float(rec.get('CANTIDAD'))
                detalle_producto["cantidad_total"] += cant
                detalle_producto["monto_total"]    += monto
                nro_factura = str(rec.get('CODIGO', '')).strip()
                if nro_factura: facturas_unicas_prod.add(nro_factura)
                detalle_producto["detalles"].append({
                    "FECHA": fecha_reg, "FACTURA": nro_factura, "CAJA": caja,
                    "CLIENTE": cliente, "VENDEDOR": vend,
                    "CANTIDAD": round(cant, 2), "MONTO": round(monto, 2)
                })
            detalle_producto["facturas_unicas"] = len(facturas_unicas_prod)

        return jsonify({
            "status":     "success",
            "total_gral": round(total_gral, 2),
            "resumen_tipo": {k: round(v, 2) for k, v in ventas_tipo.items()},
            "general": {
                "conteo_clientes":         len(clientes_unicos),
                "total_facturas_unicas":   len(facturas_unicas),
                "facturas_contado_unicas": len(facturas_contado_unicas),
                "fact_cont_monto":         round(fact_cont_monto, 2),
                "facturas_credito_unicas": len(facturas_credito_unicas),
                "fact_cred_monto":         round(fact_cred_monto, 2),
                "total_igtf":              round(total_igtf, 2)
            },
            # ── Por MONTO ─────────────────────────────────────────────────
            "zonas":             format_top(por_zona),
            "clientes":          format_top(por_cliente),
            "productos":         format_top(por_producto),
            "vendedores":        top_vendedores,
            "detalles_vendedor": detalles_vendedor,
            # ── Por CANTIDAD ──────────────────────────────────────────────
            "zonas_cant":             format_top(por_zona_cant),
            "clientes_cant":          format_top(por_cliente_cant),
            "productos_cant":         format_top(por_producto_cant),
            "vendedores_cant":        top_vendedores_cant,
            "detalles_vendedor_cant": detalles_vendedor_cant,
            # ── Listas y otros ────────────────────────────────────────────
            "lista_vendedores": sorted(list(all_vendedores)),
            "lista_zonas":      sorted(list(all_zonas)),
            "lista_clientes":   sorted(list(all_clientes)),
            "lista_productos":  sorted(list(all_productos)),
            "lista_cajas":      sorted([c for c in all_cajas if c]),
            "facturas":         facturas_lista[:1000],
            "detalle_producto": detalle_producto,
            "historico_ventas": historico_ventas,
        })

    except Exception as e:
        import traceback
        print(traceback.format_exc())
        return jsonify({"status": "error", "message": str(e)}), 500

# ─── API: COBROS-FACTURAS ─────────────────────────────────────────────────
@app.route('/api/cobros-facturas', methods=['POST'])
@login_required
def get_cobros_facturas():
    params = request.json or {}
    fecha_inicio    = params.get('fecha_inicio', '')
    fecha_fin       = params.get('fecha_fin', '')
    moneda          = params.get('moneda', 'Bs')
    forma_pago      = (params.get('forma_pago') or 'TODAS').strip().upper()
    vendedor_filtro = (params.get('vendedor') or 'TODOS').strip().upper()
    top_n           = int(params.get('top_n', 10))

    def normalizar_forma(raw):
        if not raw or str(raw).strip() == '': return 'SIN FORMA'
        f = str(raw).strip().upper().replace('.', '').replace(' ', '').replace('-', '')
        mapping = {
            'TDEBITO': 'T.DEBITO', 'TARJETADEBITO': 'T.DEBITO', 'DEBITO': 'T.DEBITO',
            'TCREDITO': 'T.CREDITO', 'TARJETACREDITO': 'T.CREDITO', 'CREDITO': 'T.CREDITO',
            'TRANSFERENCIA': 'TRANSFERENCIA', 'TRANSF': 'TRANSFERENCIA',
            'ZELLE': 'DIVISAS', 'PAYPAL': 'DIVISAS', 'BINANCE': 'DIVISAS', 'DIVISAS': 'DIVISAS',
            'EFECTIVO': 'EFECTIVO', 'EFE': 'EFECTIVO',
            'CHEQUE': 'CHEQUE', 'CHQ': 'CHEQUE',
            'DEPOSITO': 'DEPOSITO', 'DEP': 'DEPOSITO',
        }
        for clave, valor in mapping.items():
            if clave in f: return valor
        return f

    total_cobrado  = 0.0
    por_forma      = defaultdict(float)
    por_vendedor   = defaultdict(float)
    por_caja       = defaultdict(float)
    data_tabla     = []
    all_vendedores = set()
    all_formas     = set()
    all_cajas      = set()
    all_clientes   = set()
    caja_filtro    = (params.get('caja') or 'TODAS').strip().upper()
    cliente_filtro = (params.get('cliente') or 'TODAS').strip().upper()

    try:
        path = get_dbf_path('tablero_cobro_factura.DBF')
        if not os.path.exists(path):
            return jsonify({"error": "Archivo DBF no encontrado"}), 404

        for rec in DBF(path, encoding='latin-1'):
            fecha_reg = parse_fecha(rec.get('FECHA'))
            if fecha_inicio and fecha_reg < fecha_inicio: continue
            if fecha_fin    and fecha_reg > fecha_fin:    continue

            vendedor_raw  = str(rec.get('VENDEDOR', 'S/V')).strip()
            vendedor_norm = ' '.join(vendedor_raw.upper().split())
            all_vendedores.add(vendedor_norm)
            if vendedor_filtro != 'TODOS' and vendedor_norm != vendedor_filtro: continue

            cliente_raw = str(rec.get('CLIENTE', 'S/C')).strip().upper()
            all_clientes.add(cliente_raw)
            if cliente_filtro != 'TODAS' and cliente_filtro != cliente_raw: continue

            forma_raw = str(rec.get('FORMAPAGO', 'S/I')).strip()
            forma     = normalizar_forma(forma_raw)
            all_formas.add(forma)
            if forma_pago != 'TODAS' and forma != forma_pago: continue

            caja = str(rec.get('CAJA', 'S/C')).strip().upper()
            if caja and caja != 'S/C': all_cajas.add(caja)
            if caja_filtro != 'TODAS' and caja != caja_filtro: continue

            monto_raw = safe_float(rec.get('MONTO'))
            tasa      = safe_float(rec.get('TASADOLAR')) or 1.0
            monto     = monto_raw if moneda == 'Bs' else round(monto_raw / tasa, 2)

            total_cobrado        += monto
            por_forma[forma]     += monto
            por_vendedor[vendedor_norm] += monto
            por_caja[caja]       += monto

            if len(data_tabla) < 1000:
                data_tabla.append({
                    "CODIGO":    str(rec.get('CODIGO', '')).strip(),
                    "FECHA":     fecha_reg,
                    "CLIENTE":   str(rec.get('CLIENTE', 'S/C')).strip(),
                    "VENDEDOR":  vendedor_norm,
                    "CAJA":      str(rec.get('CAJA', 'S/C')).strip(),
                    "FORMAPAGO": forma,
                    "MONTO":     round(monto, 2),
                })

        def format_top(dic):
            return sorted(
                [{"label": k or 'Sin dato', "value": round(v, 2)} for k, v in dic.items()],
                key=lambda x: x['value'], reverse=True
            )[:top_n]

        return jsonify({
            "status":           "success",
            "total_general":    round(total_cobrado, 2),
            "formas_pago":      format_top(por_forma),
            "vendedores":       format_top(por_vendedor),
            "cajas":            format_top(por_caja),
            "tabla":            data_tabla,
            "lista_vendedores": sorted(list(all_vendedores)),
            "lista_formas":     sorted(list(all_formas)),
            "lista_cajas":      sorted(list(all_cajas)),
            "lista_clientes":   sorted([c for c in all_clientes if c and c != 'S/C']),
        })
    except Exception as e:
        import traceback
        print("Error en /api/cobros-facturas:", traceback.format_exc())
        return jsonify({"error": str(e)}), 500

# ─── API: BANCOS ──────────────────────────────────────────────────────────
@app.route('/api/bancos', methods=['POST'])
@login_required
def get_bancos():
    params       = request.json
    busqueda     = params.get('busqueda', '').upper().strip()
    moneda       = params.get('moneda', 'Bs')
    tipocuen     = params.get('tipocuen', '').strip()
    banco_filtro = params.get('banco', '').strip().upper()
    fecha_inicio = params.get('fecha_inicio', '')
    fecha_fin    = params.get('fecha_fin', '')

    data_movimientos  = []
    saldos_por_cuenta = {}
    totales       = {"ingresos": 0, "egresos": 0}
    unique_tipos  = set()
    unique_bancos = set()

    try:
        path = get_dbf_path('tablero_bancos.DBF')
        if os.path.exists(path):
            for rec in DBF(path, encoding='latin-1'):
                tipocuen_reg = str(rec.get('TIPOCUEN', '')).strip()
                unique_tipos.add(tipocuen_reg)
                banco_nom = str(rec.get('BANCO', '')).strip()
                unique_bancos.add(banco_nom)
                fecha_reg = parse_fecha(rec.get('FECHA'))
                if fecha_inicio and fecha_reg < fecha_inicio: continue
                if fecha_fin    and fecha_reg > fecha_fin:    continue
                if tipocuen and tipocuen != tipocuen_reg: continue
                if banco_filtro and banco_filtro != banco_nom.upper():
                    continue
                nro_cuenta = str(rec.get('CUENTA', '')).strip()
                desc = str(rec.get('DESCRIPCIO', '')).strip()
                if busqueda and (busqueda not in banco_nom.upper() and busqueda not in desc.upper()): continue
                debe    = safe_float(rec.get('DEBE'))
                haber   = safe_float(rec.get('HABER'))
                divisas = safe_float(rec.get('DIVISAS'))
                if moneda == 'Bs':
                    saldo_actual = safe_float(rec.get('SALDO'))
                    totales["ingresos"] += debe
                    totales["egresos"]  += haber
                    debe_mov = debe; haber_mov = haber
                else:
                    saldo_actual = divisas
                    debe_mov  = max(divisas, 0)
                    haber_mov = abs(min(divisas, 0))
                    totales["ingresos"] += debe_mov
                    totales["egresos"]  += haber_mov
                saldos_por_cuenta[nro_cuenta] = {"banco": banco_nom, "saldo": saldo_actual}
                if len(data_movimientos) < 150:
                    data_movimientos.append({
                        "FECHA":       parse_fecha(rec.get('FECHA')),
                        "BANCO":       banco_nom, "CUENTA": nro_cuenta,
                        "TIPO":        str(rec.get('TIPOMOV', '')).strip(),
                        "DESCRIPCION": desc, "DEBE": debe_mov, "HABER": haber_mov
                    })

        distribucion_bancos = defaultdict(float)
        total_global = 0
        for c in saldos_por_cuenta.values():
            total_global += c['saldo']
            distribucion_bancos[c['banco']] += c['saldo']

        # Ordenar movimientos por fecha ascendente
        data_movimientos.sort(key=lambda x: x.get('FECHA', ''))

        return jsonify({
            "totales": {"ingresos": round(totales["ingresos"], 2), "egresos": round(totales["egresos"], 2), "saldo_total": round(total_global, 2)},
            "tabla":         data_movimientos,
            "bancos_chart":  [{"BANCO": k, "V": round(v, 2)} for k, v in distribucion_bancos.items()],
            "tipos_cuentas": sorted(list(unique_tipos)),
            "lista_bancos":  sorted([b for b in unique_bancos if b.strip()])
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ─── API: VENDEDORES ──────────────────────────────────────────────────────
@app.route('/api/vendedores', methods=['GET'])
@login_required
def get_vendedores():
    all_vendedores = set()
    try:
        path_fac = get_dbf_path('tablero_facturas.DBF')
        if os.path.exists(path_fac):
            for rec in DBF(path_fac, encoding='latin-1'):
                vend = str(rec.get('VENDEDOR') or rec.get('CODVEN') or 'SIN VENDEDOR').strip()
                if vend and vend != 'SIN VENDEDOR': all_vendedores.add(vend)
        return jsonify({"status": "success", "vendedores": sorted(list(all_vendedores))})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

# ─── API: INVENTARIO ──────────────────────────────────────────────────────
@app.route('/api/inventario', methods=['POST'])
@login_required
def get_inventario():
    params      = request.json or {}
    f_prod      = (params.get('producto') or '').strip().upper()
    valorizar_a = params.get('valorizar_a', 'costo')
    pagina      = int(params.get('pagina', 1))
    por_pagina  = int(params.get('por_pagina', 100))

    filtros_carac = {}
    for i in '1234':
        key = f'carac{i}'
        if key in params:
            filtros_carac[i] = (params[key] or '').strip().upper()

    # Permisos de precios y costo (pos 12=Precio1, 13=Precio2, 14=Precio3, 15=Costo)
    ver_precio1 = current_user.tiene_permiso(12)
    ver_precio2 = current_user.tiene_permiso(13)
    ver_precio3 = current_user.tiene_permiso(14)
    ver_costo   = current_user.tiene_permiso(15)

    data_tabla = []
    totales = {"articulos": 0, "existencia": 0.0, "valor_total": 0.0, "peso_total": 0.0}
    por_marca           = defaultdict(float)
    nombres_precios     = {"1": "Precio 1", "2": "Precio 2", "3": "Precio 3"}
    nombres_carac       = {}
    has_carac           = {"1": False, "2": False, "3": False, "4": False}
    nombres_encontrados = False

    try:
        path = get_dbf_path('tablero_inventario.DBF')
        if not os.path.exists(path):
            return jsonify({"error": "Archivo de inventario no encontrado"}), 404

        for rec in DBF(path, encoding='latin-1', ignore_missing_memofile=True):
            if not nombres_encontrados:
                for i in '123':
                    nombre = str(rec.get(f'NOMBREP{i}', '')).strip()
                    if nombre and nombre.lower() not in ['', 'none', 'null', ' ']:
                        nombres_precios[i] = nombre
                for i in '1234':
                    nombre = str(rec.get(f'NOMBREC{i}', '')).strip()
                    if nombre and nombre.lower() not in ['', 'none', 'null', ' ']:
                        nombres_carac[i] = nombre
                nombres_encontrados = True

            desc   = str(rec.get('DESCRIPCIO', '')).strip()
            codigo = str(rec.get('CODIGO', '')).strip()
            if f_prod and f_prod not in desc.upper() and f_prod not in codigo: continue

            pasar = True
            for idx, filtro_val in filtros_carac.items():
                carac_val = str(rec.get(f'CARAC{idx}', '')).strip().upper()
                if filtro_val and filtro_val != carac_val:
                    pasar = False; break
            if not pasar: continue

            for i in '1234':
                if str(rec.get(f'CARAC{i}', '')).strip(): has_carac[i] = True

            existencia    = safe_float(rec.get('EXISTENCIA'))
            monto         = safe_float(rec.get('MONTO'))
            peso          = safe_float(rec.get('PESO'))
            total_empaque = round(peso * existencia, 4)
            precio1    = safe_float(rec.get('PRECIO1'))
            precio2    = safe_float(rec.get('PRECIO2'))
            precio3    = safe_float(rec.get('PRECIO3'))

            if   valorizar_a == 'precio1': valor_unit = precio1
            elif valorizar_a == 'precio2': valor_unit = precio2
            elif valorizar_a == 'precio3': valor_unit = precio3
            else: valor_unit = monto / existencia if existencia > 0 else 0.0

            valor_total_item = valor_unit * existencia
            costo_unitario   = monto / existencia if existencia > 0 else 0.0

            totales["articulos"]   += 1
            totales["existencia"]  += existencia
            totales["valor_total"] += valor_total_item
            totales["peso_total"]  += peso
            por_marca[str(rec.get('CARAC1', 'Sin marca')).strip()] += valor_total_item

            item = {
                "CODIGO": codigo, "DESCRIPCION": desc, "EXISTENCIA": existencia,
                "VALOR_TOTAL": round(valor_total_item, 2), "TOTAL_EMPAQUE": total_empaque,
            }
            if ver_costo:   item["COSTO_UNITARIO"] = round(costo_unitario, 4)
            if ver_precio1: item["PRECIO1"] = precio1
            if ver_precio2: item["PRECIO2"] = precio2
            if ver_precio3: item["PRECIO3"] = precio3
            for i in '1234':
                val = str(rec.get(f'CARAC{i}', '')).strip()
                if val: item[f'CARAC{i}'] = val
            data_tabla.append(item)

        caracteristicas_activas = {}
        for i in '1234':
            if has_carac[i]: caracteristicas_activas[i] = nombres_carac.get(i, f"Clasificación {i}")

        filtros_dinamicos = {}
        for idx, nombre in caracteristicas_activas.items():
            filtros_dinamicos[f'filtro_carac{idx}'] = sorted(set(
                str(item.get(f'CARAC{idx}', '')).strip()
                for item in data_tabla if str(item.get(f'CARAC{idx}', '')).strip()
            ))

        marcas_chart = sorted(
            [{"MARCA": k, "V": round(v, 2)} for k, v in por_marca.items()],
            key=lambda x: x["V"], reverse=True)[:10]

        total_registros = len(data_tabla)
        total_paginas   = max(1, (total_registros + por_pagina - 1) // por_pagina)
        pagina          = max(1, min(pagina, total_paginas))
        inicio          = (pagina - 1) * por_pagina
        pagina_data     = data_tabla[inicio:inicio + por_pagina]

        return jsonify({
            "totales": {
                "articulos":   totales["articulos"],
                "existencia":  round(totales["existencia"], 2),
                "valor_total": round(totales["valor_total"], 2),
                "peso_total":  round(totales["peso_total"], 2)
            },
            "tabla": pagina_data,
            "paginacion": {
                "pagina": pagina, "por_pagina": por_pagina,
                "total_registros": total_registros, "total_paginas": total_paginas,
            },
            "marcas_chart":      marcas_chart,
            "nombres_precios":   nombres_precios,
            "caracteristicas":   caracteristicas_activas,
            "filtros_dinamicos": filtros_dinamicos,
            "valorizar_a":       valorizar_a,
            "permisos_precio": {
                "ver_precio1": ver_precio1,
                "ver_precio2": ver_precio2,
                "ver_precio3": ver_precio3,
                "ver_costo":   ver_costo,
            }
        })
    except Exception as e:
        import traceback
        print("Error en /api/inventario:", str(e))
        print(traceback.format_exc())
        return jsonify({"error": str(e)}), 500

# ─── API: MOVIMIENTOS INVENTARIO ──────────────────────────────────────────
@app.route('/api/movimientos_inventario', methods=['POST'])
@login_required
def get_movimientos_inventario():
    params    = request.json or {}
    f_producto = (params.get('producto') or '').strip().upper()
    f_inicio   = params.get('fecha_inicio', '')
    f_fin      = params.get('fecha_fin', '')
    f_tipomov  = (params.get('tipomov') or '').strip().upper()
    f_almacen  = (params.get('almacen') or '').strip().upper()
    f_prov_cli = (params.get('prov_cli') or '').strip().upper()

    all_productos  = {}
    all_tipos      = set()
    all_almacenes  = set()
    all_prov_cli   = set()
    detalles       = []
    total_entradas = 0.0
    total_salidas  = 0.0
    info_producto  = {}

    try:
        path = get_dbf_path('tablero_movimientos_inventario.DBF')
        if not os.path.exists(path):
            return jsonify({"error": "Archivo de movimientos no encontrado"}), 404

        for rec in DBF(path, encoding='latin-1', ignore_missing_memofile=True):
            cod  = str(rec.get('CODIGOPRO', '')).strip()
            nom  = str(rec.get('NOMBREPRO', '')).strip()
            if cod: all_productos[cod] = nom
            tipo     = str(rec.get('TIPOMOV',  '')).strip().upper()
            almacen  = str(rec.get('ALMACEN',  '')).strip().upper()
            prov_cli_r = str(rec.get('PROV_CLI','  ')).strip()
            if tipo:     all_tipos.add(tipo)
            if almacen:  all_almacenes.add(almacen)
            if prov_cli_r: all_prov_cli.add(prov_cli_r)

            if not f_producto: continue

            prod_label = (cod + " - " + nom.upper()) if cod else nom.upper()
            if f_producto not in prod_label and f_producto not in cod.upper() and f_producto not in nom.upper():
                continue

            if not info_producto and cod:
                info_producto = {
                    "codigo": cod, "nombre": nom,
                    "minimo": safe_float(rec.get('MINIMO', 0)),
                    "maximo": safe_float(rec.get('MAXIMO', 0)),
                }

            fecha_reg = parse_fecha(rec.get('FECHA'))
            if f_inicio and fecha_reg < f_inicio: continue
            if f_fin    and fecha_reg > f_fin:    continue
            if f_tipomov  and tipo      != f_tipomov:   continue
            if f_almacen  and almacen   != f_almacen:   continue
            prov_cli_val = str(rec.get('PROV_CLI', '')).strip().upper()
            if f_prov_cli and f_prov_cli not in prov_cli_val: continue

            entradas = safe_float(rec.get('ENTRADAS', 0))
            salidas  = safe_float(rec.get('SALIDAS',  0))
            total_entradas += entradas
            total_salidas  += salidas

            detalles.append({
                "FECHA":     fecha_reg,
                "DESCRIMOV": str(rec.get('DESCRIMOV', '')).strip(),
                "PROV_CLI":  str(rec.get('PROV_CLI',  '')).strip(),
                "ENTRADAS":  round(entradas, 2),
                "SALIDAS":   round(salidas,  2),
                "SALDO":     round(safe_float(rec.get('SALDO', 0)), 2),
                "ALMACEN":   almacen,
                "MOVIMIENTO":str(rec.get('MOVIMIENTO', '')).strip(),
                "REFERENCIA":str(rec.get('REFERENCIA', '')).strip(),
                "COSTO":     round(safe_float(rec.get('COSTO', 0)), 4),
                "TIPOMOV":   tipo,
            })

        detalles.sort(key=lambda x: x["FECHA"])
        lista_productos = sorted([f"{cod} - {nom}" for cod, nom in all_productos.items() if cod])

        return jsonify({
            "status":          "success",
            "lista_productos": lista_productos,
            "lista_tipos":     sorted(list(all_tipos)),
            "lista_almacenes": sorted(list(all_almacenes)),
            "lista_prov_cli":  sorted(list(all_prov_cli)),
            "info_producto":   info_producto,
            "total_entradas":  round(total_entradas, 2),
            "total_salidas":   round(total_salidas,  2),
            "detalles":        detalles,
        })
    except Exception as e:
        import traceback
        print("Error en /api/movimientos_inventario:", traceback.format_exc())
        return jsonify({"error": str(e)}), 500

# ─── API: CXP ─────────────────────────────────────────────────────────────
@app.route('/api/cartera_cxp', methods=['POST'])
@login_required
def get_cartera_cxp():
    params       = request.json or {}
    fecha_inicio = params.get('fecha_inicio', '')
    fecha_fin    = params.get('fecha_fin', '')
    moneda       = params.get('moneda', 'Bs')
    proveedor    = params.get('proveedor', '').upper().strip()
    vendedor     = params.get('vendedor', '').upper().strip()
    busqueda     = params.get('busqueda', '').upper().strip()

    data_tabla = []
    enveje = {"No Vencido": 0, "1-7 Dias": 0, "8-14 Dias": 0, "15-21 Dias": 0, "22-30 Dias": 0, "+30 Dias": 0}
    total_gral = 0.0
    resumen_grupos_dict = defaultdict(float)
    all_proveedores = set()
    all_vendedores  = set()

    try:
        path = get_dbf_path('tablero_cxp.DBF')
        if os.path.exists(path):
            for rec in DBF(path, encoding='latin-1'):
                fecha_reg = parse_fecha(rec.get('FECHA'))
                if fecha_inicio and fecha_reg < fecha_inicio: continue
                if fecha_fin    and fecha_reg > fecha_fin:    continue

                prov = str(rec.get('PROVEEDOR', '')).strip().upper()
                all_proveedores.add(prov)
                if proveedor and proveedor != 'TODOS' and proveedor not in prov: continue

                vend = str(rec.get('VENDEDOR', '')).strip().upper()
                all_vendedores.add(vend)
                if vendedor and vendedor != 'TODOS' and vendedor != vend: continue

                if busqueda:
                    if not any(busqueda in str(val).upper() for val in [prov, rec.get('GRUPO',''), rec.get('CODIGO',''), vend]):
                        continue

                saldo_raw = safe_float(rec.get('SALDO'))
                factor    = safe_float(rec.get('FACTOR')) or safe_float(rec.get('TASA')) or safe_float(rec.get('TASADOLAR')) or 0.0
                saldo     = saldo_raw if moneda == 'Bs' else (round(saldo_raw / factor, 2) if factor > 0 else saldo_raw)

                total_gral += saldo
                grupo = str(rec.get('GRUPO', 'SIN GRUPO')).strip()
                resumen_grupos_dict[grupo] += saldo

                def conv(v): return v if moneda == 'Bs' else (round(v / factor, 2) if factor > 0 else v)
                enveje["No Vencido"]  += conv(safe_float(rec.get('NOVENCIDO')))
                enveje["1-7 Dias"]    += conv(safe_float(rec.get('VENCIDO1')))
                enveje["8-14 Dias"]   += conv(safe_float(rec.get('VENCIDO2')))
                enveje["15-21 Dias"]  += conv(safe_float(rec.get('VENCIDO3')))
                enveje["22-30 Dias"]  += conv(safe_float(rec.get('VENCIDO4')))
                enveje["+30 Dias"]    += conv(safe_float(rec.get('VENCIDO5')))
                data_tabla.append({
                    "GRUPO":     grupo, "PROVEEDOR": prov, "VENDEDOR": vend,
                    "DOCUMENTO": str(rec.get('CODIGO', '')).strip(),
                    "FECHA":     fecha_reg, "DIAS": int(rec.get('DIAS_VENC', 0)),
                    "SALDO":     round(saldo, 2)
                })

        resumen_final = sorted(
            [{"GRUPO": k, "MONTO": round(v, 2)} for k, v in resumen_grupos_dict.items() if abs(v) > 0.01],
            key=lambda x: x['MONTO'], reverse=True
        )
        return jsonify({
            "total": round(total_gral, 2),
            "envejecimiento": [{"label": k, "value": round(v, 2)} for k, v in enveje.items()],
            "resumen_grupos": resumen_final,
            "tabla":      data_tabla[:1000],
            "proveedores": sorted(list(all_proveedores)),
            "vendedores":  sorted(list(all_vendedores))
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ─── API: COBROS ──────────────────────────────────────────────────────────
@app.route('/api/cobros', methods=['POST'])
@login_required
def get_cobros():
    params            = request.json or {}
    moneda            = params.get('moneda', 'Bs')
    top_n             = int(params.get('top_n', 10))
    f_inicio          = params.get('fecha_inicio', '')
    f_fin             = params.get('fecha_fin', '')
    forma_pago_filtro = params.get('forma_pago', 'TODAS').strip().upper()
    cliente_filtro    = params.get('cliente', '').strip().upper()
    caja_filtro       = (params.get('caja') or 'TODAS').strip().upper()

    forma_normalizar = {
        'T.DEBITO': 'T.DEBITO', 'TDEBITO': 'T.DEBITO', 'TCREDITO': 'T.CREDITO',
        'T.CREDITO': 'T.CREDITO', 'TRANSFERENCIA': 'TRANSFERENCIA', 'DIVISAS': 'DIVISAS',
        'EFECTIVO': 'EFECTIVO', 'POS': 'POS / TARJETA', 'TARJETA': 'POS / TARJETA',
        'CHEQUE': 'CHEQUE', 'DEPOSITO': 'DEPOSITO', 'OTRO': 'OTRO',
        '': 'SIN INFORMACION', 'S/I': 'SIN INFORMACION'
    }

    totales      = {"cobrado": 0.0}
    por_forma    = defaultdict(float)
    por_cobrador = defaultdict(float)
    por_caja     = defaultdict(float)
    por_cliente  = defaultdict(float)
    data_tabla   = []
    cajas_unicas = set()
    ultima_tasa_valida = 1.0

    try:
        path = get_dbf_path('tablero_cobros_cxc.DBF')
        if not os.path.exists(path):
            return jsonify({"error": "Archivo de cobros no encontrado"}), 404

        for rec in DBF(path, encoding='latin-1'):
            fecha_reg = parse_fecha(rec.get('FECHA'))
            if f_inicio and fecha_reg < f_inicio: continue
            if f_fin    and fecha_reg > f_fin:    continue

            cliente = str(rec.get('CLIENTE', 'S/C')).strip().upper()
            if cliente_filtro and cliente_filtro not in cliente: continue

            caja = str(rec.get('CAJA', 'S/C')).strip().upper()
            cajas_unicas.add(caja)
            if caja_filtro != 'TODAS' and caja != caja_filtro: continue

            forma_raw = str(rec.get('FORMA_PAGO', 'S/I')).strip().upper()
            forma     = forma_normalizar.get(forma_raw, forma_raw)
            if forma_pago_filtro != 'TODAS' and forma != forma_pago_filtro: continue

            m_raw    = safe_float(rec.get('MONTO'))
            tasa_rec = safe_float(rec.get('TASA_DOLAR'))
            if tasa_rec > 0: ultima_tasa_valida = tasa_rec
            monto = m_raw if moneda == 'Bs' else (m_raw / ultima_tasa_valida)
            cobrador = str(rec.get('COBRADOR', 'S/C')).strip()

            totales["cobrado"]     += monto
            por_forma[forma]       += monto
            por_cobrador[cobrador] += monto
            por_caja[caja]         += monto
            por_cliente[cliente]   += monto

            if len(data_tabla) < 500:
                data_tabla.append({
                    "RECIBO":   str(rec.get('RECIBO', '')).strip(),
                    "FECHA":    fecha_reg.strftime('%Y-%m-%d') if isinstance(fecha_reg, datetime) else fecha_reg,
                    "CLIENTE":  cliente, "COBRADOR": cobrador, "CAJA": caja,
                    "FORMA":    forma, "MONTO": round(monto, 2), "TASA": ultima_tasa_valida
                })

        def format_chart(dico):
            return sorted(
                [{"label": k if k else 'Sin dato', "value": round(v, 2)} for k, v in dico.items() if v > 0],
                key=lambda x: x['value'], reverse=True)

        return jsonify({
            "total_general": round(totales["cobrado"], 2),
            "formas_pago":   format_chart(por_forma),
            "cobradores":    format_chart(por_cobrador),
            "cajas":         format_chart(por_caja),
            "clientes":      format_chart(por_cliente)[:top_n],
            "tabla":         data_tabla,
            "cajas_lista":   sorted([c for c in cajas_unicas if c and c != 'S/C'])
        })
    except Exception as e:
        import traceback
        print("Error en /api/cobros:", traceback.format_exc())
        return jsonify({"error": str(e)}), 500

# ─── API: COMPRAS ─────────────────────────────────────────────────────────
@app.route('/api/compras', methods=['POST'])
@login_required
def get_compras():
    params        = request.json or {}
    moneda        = params.get('moneda', 'Bs')
    top_n         = int(params.get('top_n', 15))
    f_inicio      = params.get('fecha_inicio', '')
    f_fin         = params.get('fecha_fin', '')
    f_prov        = (params.get('proveedor') or '').strip().upper()
    f_prod        = (params.get('producto')  or '').strip().upper()
    prod_criterio = params.get('prod_criterio', 'monto')

    totales_compra      = {"Contado": 0.0, "Crédito": 0.0, "Otros": 0.0}
    por_proveedor       = defaultdict(float)
    por_producto_monto  = defaultdict(float)
    por_producto_unid   = defaultdict(float)
    por_marca           = defaultdict(float)
    all_proveedores     = set()
    all_productos       = set()
    total_gral          = 0.0

    detalle_producto = {
        "cantidad_total": 0.0, "monto_total": 0.0,
        "proveedores_unicos": set(), "detalles": []
    } if f_prod else None
    detalles_temp = []

    try:
        path = get_dbf_path('tablero_compras.DBF')
        if os.path.exists(path):
            for rec in DBF(path, encoding='latin-1', ignore_missing_memofile=True):
                prov_reg   = str(rec.get('PROVEEDOR', 'S/P')).strip().upper()
                prod_reg   = str(rec.get('NOMBREPRO', 'S/P')).strip().upper()
                cod_prod   = str(rec.get('CODIGOPRO', '')).strip().upper()
                fecha_reg  = parse_fecha(rec.get('FECHA'))
                prod_label = (cod_prod + " - " + prod_reg) if cod_prod else prod_reg

                if prov_reg and prov_reg != 'S/P': all_proveedores.add(prov_reg)
                if prod_reg and prod_reg != 'S/P': all_productos.add(prod_label)

                if f_prov and f_prov != prov_reg:    continue
                if f_prod and f_prod != prod_label:  continue
                if f_inicio and fecha_reg < f_inicio: continue
                if f_fin    and fecha_reg > f_fin:    continue

                m_raw  = safe_float(rec.get('MONTO'))
                factor = safe_float(rec.get('FACTOR')) or 1.0
                monto  = m_raw if moneda == 'Bs' else (m_raw / factor)
                cant   = safe_float(rec.get('CANTIDAD'))
                tipo   = str(rec.get('TIPO', '')).strip()
                tipo_texto = "Contado" if tipo == '1' else ("Crédito" if tipo == '2' else "Otros")

                totales_compra[tipo_texto]   += monto
                total_gral                   += monto
                por_proveedor[prov_reg]      += monto
                por_producto_monto[prod_reg] += monto
                por_producto_unid[prod_reg]  += cant
                por_marca[str(rec.get('CLASI1', 'SIN MARCA')).strip()] += monto

                if f_prod and detalle_producto is not None:
                    detalle_producto["cantidad_total"] += cant
                    detalle_producto["monto_total"]    += monto
                    detalle_producto["proveedores_unicos"].add(prov_reg)
                    detalles_temp.append({
                        "FECHA": fecha_reg, "DOCUMENTO": str(rec.get('CODIGO', '')).strip(),
                        "PROVEEDOR": prov_reg, "TIPO": tipo_texto,
                        "CANTIDAD": round(cant, 2), "MONTO": round(monto, 2),
                    })

        if f_prod and detalle_producto is not None:
            detalles_temp.sort(key=lambda x: x["FECHA"], reverse=True)
            detalle_producto["detalles"]           = detalles_temp[:200]
            detalle_producto["proveedores_unicos"] = len(detalle_producto["proveedores_unicos"])
            detalle_producto["monto_total"]        = round(detalle_producto["monto_total"], 2)
            detalle_producto["cantidad_total"]     = round(detalle_producto["cantidad_total"], 2)

        def format_top_monto(dico, label_key):
            # Incluye registros con monto=0 (notas de entrega sin precio)
            return sorted(
                [{label_key: k, "V": round(v, 2)} for k, v in dico.items()],
                key=lambda x: x["V"], reverse=True)[:top_n]

        def format_top_cant(dico, label_key):
            return sorted(
                [{label_key: k, "V": round(v, 2)} for k, v in dico.items() if v > 0],
                key=lambda x: x["V"], reverse=True)[:top_n]

        return jsonify({
            "totales":           {k: round(v, 2) for k, v in totales_compra.items()},
            "total_general":     round(total_gral, 2),
            "proveedores":       format_top_monto(por_proveedor,      "PROVEEDOR"),
            "productos_monto":   format_top_monto(por_producto_monto, "PRODUCTO"),
            "productos_unid":    format_top_cant(por_producto_unid,   "PRODUCTO"),
            "marcas":            format_top_monto(por_marca,          "MARCA"),
            "lista_proveedores": sorted(list(all_proveedores)),
            "lista_productos":   sorted(list(all_productos)),
            "detalle_producto":  detalle_producto,
        })
    except Exception as e:
        import traceback
        print("Error en /api/compras:", traceback.format_exc())
        return jsonify({"error": str(e)}), 500

# ─── API: COBRANZAS ───────────────────────────────────────────────────────
@app.route('/api/cobranzas', methods=['POST'])
@login_required
def api_cobranzas():
    params       = request.get_json() or {}
    fecha_inicio = params.get('fecha_inicio')
    fecha_fin    = params.get('fecha_fin')
    moneda       = params.get('moneda', 'Bs')
    caja_filtro  = (params.get('caja') or 'TODAS').upper().strip()

    total_general      = 0.0
    conteo             = 0
    por_forma          = defaultdict(float)
    por_dia            = defaultdict(float)
    cajas_unicas       = set()
    ultima_tasa_valida = 1.0

    try:
        path = get_dbf_path('tablero_cobros_cxc.DBF')
        if not os.path.exists(path):
            return jsonify({"error": "Archivo de cobros no encontrado"}), 404

        for rec in DBF(path, encoding='latin-1'):
            fecha_str = parse_fecha(rec.get('FECHA'))
            if fecha_inicio and fecha_str < fecha_inicio: continue
            if fecha_fin    and fecha_str > fecha_fin:    continue

            caja = str(rec.get('CAJA', 'S/C')).strip().upper()
            cajas_unicas.add(caja)
            if caja_filtro != 'TODAS' and caja != caja_filtro: continue

            monto_raw = safe_float(rec.get('MONTO'))
            tasa_rec  = safe_float(rec.get('TASA_DOLAR'))
            if tasa_rec > 0: ultima_tasa_valida = tasa_rec
            monto = monto_raw if moneda == 'Bs' else round(monto_raw / ultima_tasa_valida, 2)

            total_general += monto
            conteo        += 1
            forma = str(rec.get('FORMA_PAGO', 'SIN FORMA')).strip().upper()
            por_forma[forma] += monto
            por_dia[fecha_str] += monto

        ticket_promedio = round(total_general / conteo, 2) if conteo > 0 else 0.0
        formas_orden = sorted(
            [{"FORMA": k or "Sin forma", "V": round(v, 2),
              "P": round(v / total_general * 100, 1) if total_general != 0 else 0}
             for k, v in por_forma.items()],
            key=lambda x: abs(x["V"]), reverse=True)
        historico = sorted([{"F": f, "V": round(v, 2)} for f, v in por_dia.items()], key=lambda x: x["F"])

        return jsonify({
            "total_general":   round(total_general, 2),
            "ticket_promedio": ticket_promedio,
            "conteo":          conteo,
            "formas_pago":     formas_orden,
            "historico":       historico,
            "cajas":           sorted(list(cajas_unicas))
        })
    except Exception as e:
        import traceback
        print(traceback.format_exc())
        return jsonify({"error": str(e)}), 500


# ─── EXPLORADOR DE CAMPOS DBF ─────────────────────────────────────────────
@app.route('/admin/dbf-explorer')
@login_required
def dbf_explorer_page():
    return render_template('dbf_explorer.html', empresa=current_user.nombre_empresa, bloqueo=session.get('bloqueo',0), periodo=session.get('periodo','M'))

@app.route('/api/admin/dbf-list', methods=['GET'])
@login_required
def dbf_list():
    """Lista todos los archivos DBF del disco por empresa."""
    resultado = {}
    try:
        for empresa in sorted(os.listdir(DBF_DIR)):
            carpeta = os.path.join(DBF_DIR, empresa)
            if not os.path.isdir(carpeta): continue
            archivos = sorted([
                f for f in os.listdir(carpeta)
                if f.lower().endswith(('.dbf',))
            ])
            resultado[empresa] = archivos
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    return jsonify(resultado)

@app.route('/api/admin/dbf-fields', methods=['POST'])
@login_required
def dbf_fields():
    """Devuelve los campos y primeras filas de un DBF."""
    data    = request.json or {}
    empresa = (data.get('empresa') or '').strip().upper()
    archivo = (data.get('archivo') or '').strip()
    filas_n = int(data.get('filas', 5))

    if not empresa or not archivo:
        return jsonify({"error": "empresa y archivo son requeridos"}), 400

    empresa_segura = "".join(c for c in empresa if c.isalnum() or c in ('_','-'))
    archivo_seguro = os.path.basename(archivo)
    path = os.path.join(DBF_DIR, empresa_segura, archivo_seguro)

    if not os.path.exists(path):
        return jsonify({"error": f"Archivo no encontrado: {path}"}), 404

    try:
        tabla = DBF(path, encoding='latin-1', ignore_missing_memofile=True)
        campos = [{"nombre": f.name, "tipo": f.type, "longitud": f.length}
                  for f in tabla.fields]
        filas = []
        for i, rec in enumerate(tabla):
            if i >= filas_n: break
            fila = {}
            for c in campos:
                val = rec.get(c["nombre"])
                fila[c["nombre"]] = str(val).strip() if val is not None else ""
            filas.append(fila)
        tamanio_kb = round(os.path.getsize(path) / 1024, 1)
        return jsonify({
            "campos":     campos,
            "filas":      filas,
            "total_campos": len(campos),
            "tamanio_kb": tamanio_kb,
            "ruta":       path
        })
    except Exception as e:
        import traceback
        print(traceback.format_exc())
        return jsonify({"error": str(e)}), 500



# ─── API: PRECIOS (tablero_precios.DBF) ───────────────────────────────────
@app.route('/api/precios_inventario', methods=['POST'])
@login_required
def get_precios_inventario():
    if not current_user.tiene_permiso(3):
        return jsonify({"error": "sin_permiso"}), 403
    params       = request.json or {}
    solo_listas  = params.get('solo_listas', False)
    busqueda     = (params.get('busqueda') or '').strip().upper()
    lista_filtro = (params.get('lista')    or '').strip().upper()

    try:
        path = get_dbf_path('tablero_precios.DBF')
        if not os.path.exists(path):
            return jsonify({"error": "Archivo no encontrado"}), 404

        listas_set = set()
        data       = []

        for rec in DBF(path, encoding='latin-1', ignore_missing_memofile=True):
            codigo  = str(rec.get('CODIGO',    '')).strip()
            desc    = str(rec.get('DESCRIPCIO','')).strip()
            cod_pre = str(rec.get('CODIGOPRE', '')).strip()
            nom_pre = str(rec.get('NOMBREPRE', '')).strip()
            precio  = safe_float(rec.get('PRECIO'))

            if nom_pre: listas_set.add(nom_pre)
            if solo_listas: continue

            # Filtro por búsqueda — mismo criterio que el inventario
            if busqueda and busqueda not in codigo.upper() and busqueda not in desc.upper():
                continue
            # Filtro por nombre de lista de precio
            if lista_filtro and nom_pre.upper() != lista_filtro:
                continue

            data.append({
                "CODIGO":    codigo,
                "DESCRIPCIO": desc,
                "CODIGOPRE": cod_pre,
                "NOMBREPRE": nom_pre,
                "PRECIO":    round(precio, 2),
            })

        if solo_listas:
            return jsonify({"status": "success", "listas": sorted(list(listas_set))})

        return jsonify({"status": "success", "data": data, "total": len(data)})

    except Exception as e:
        import traceback
        print("Error en /api/precios_inventario:", traceback.format_exc())
        return jsonify({"error": str(e)}), 500


@app.route('/debug-session')
@login_required
def debug_session():
    acceso = str(current_user.acceso)
    p18 = current_user.tiene_permiso(3)
    return f"acceso={acceso} len={len(acceso)} pos18={acceso[17] if len(acceso)>=18 else 'NO_EXISTE'} permiso18={p18}"


# ─── API: ALMACENES ────────────────────────────────────────────────────────
@app.route('/api/almacenes', methods=['POST'])
@login_required
def get_almacenes():
    params   = request.json or {}
    busqueda = (params.get('busqueda') or '').strip().upper()
    almacen  = (params.get('almacen')  or '').strip().upper()

    data          = []
    all_almacenes = set()
    totales       = {"almacenes": 0, "disponible": 0.0, "valor": 0.0}

    try:
        path = get_dbf_path('tablero_almacenes.DBF')
        if not os.path.exists(path):
            return jsonify({"error": "Archivo tablero_almacenes.DBF no encontrado"}), 404

        for rec in DBF(path, encoding='latin-1', ignore_missing_memofile=True):
            cod_alm  = str(rec.get('CODIGOALM', '')).strip()
            nom_alm  = str(rec.get('NOMBREALM', '')).strip()
            tipo_alm = str(rec.get('TIPOALM',   '')).strip().upper()
            cod      = str(rec.get('CODIGO',    '')).strip()
            desc     = str(rec.get('DESCRIPCIO','')).strip()
            exi      = safe_float(rec.get('EXISTENCIA'))
            disp     = safe_float(rec.get('DISPONIBLE'))
            costo_u  = safe_float(rec.get('COSTOUNI'))
            mont     = safe_float(rec.get('MONTOTOTAL'))
            ubic     = str(rec.get('UBICACION', '')).strip()

            alm_label = f"{cod_alm} - {nom_alm}" if cod_alm else nom_alm
            if nom_alm: all_almacenes.add(alm_label)

            if almacen  and alm_label.upper() != almacen.upper() and nom_alm.upper() != almacen.upper(): continue
            if busqueda and busqueda not in cod.upper() and busqueda not in desc.upper(): continue

            totales["almacenes"] += 1
            totales["disponible"] += disp
            totales["valor"]      += mont

            data.append({
                "CODIGOALM":  cod_alm,
                "NOMBREALM":  nom_alm,
                "TIPOALM":    tipo_alm,   # 'M' = Movimiento, 'C' = Consulta
                "CODIGO":     cod,
                "DESCRIPCIO": desc,
                "EXISTENCIA": round(exi, 2),
                "DISPONIBLE": round(disp, 2),
                "COSTO_UNIT": round(costo_u, 4),
                "MONTO":      round(mont, 2),
                "UBICACION":  ubic,
            })

        return jsonify({
            "status":       "success",
            "data":         data,
            "total":        len(data),
            "totales":      {k: round(v, 2) for k, v in totales.items()},
            "lista_almacenes": sorted(list(all_almacenes)),
        })
    except Exception as e:
        import traceback
        print("Error en /api/almacenes:", traceback.format_exc())
        return jsonify({"error": str(e)}), 500

# ─── ARRANQUE ─────────────────────────────────────────────────────────────
port = int(os.environ.get('PORT', 5000))
app.run(debug=False, host='0.0.0.0', port=port)