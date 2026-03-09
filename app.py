from flask import Flask, render_template, request, jsonify, redirect, url_for, session
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from dbfread import DBF
import os
from collections import defaultdict
from datetime import datetime
import pandas as pd
import json
#"import google.genai as genai


app = Flask(__name__)
app.secret_key = 'clave_secreta_muy_segura_confia_2026'


# ─── CONFIGURACIÓN DE RUTAS ────────────────────────────────────────────────
# BASE_DIR = os.path.dirname(os.path.abspath(__file__))
# DBF_DIR = os.path.join(BASE_DIR, "dbf")

# Ruta absoluta al disco persistente (Render lo monta aquí)
PERSISTENT_ROOT = "/var/data"

# Carpeta principal para todos tus DBF (puedes usar subcarpetas como ahora)
DBF_DIR = os.path.join(PERSISTENT_ROOT, "dbf")

# Asegúrate de que exista (ejecútalo al inicio de tu app, por ejemplo en app.py)
os.makedirs(DBF_DIR, exist_ok=True)


def get_dbf_path(archivo):
    """
    Devuelve la ruta completa al archivo .DBF según la empresa del usuario actual
    """
    if not current_user.is_authenticated:
        # Fallback para login o casos sin usuario
        return os.path.join(DBF_DIR, archivo)
    
    empresa = current_user.empresa.strip().upper()
    if not empresa or empresa == "NONE" or empresa == "CONFIA":
        # Empresas sin carpeta propia o fallback
        return os.path.join(DBF_DIR, archivo)
    
    # Ruta por empresa
    empresa_folder = os.path.join(DBF_DIR, empresa)
    if not os.path.exists(empresa_folder):
        print(f"¡ALERTA! No existe la carpeta para la empresa: {empresa}")
        return os.path.join(DBF_DIR, archivo)  # fallback
    
    return os.path.join(empresa_folder, archivo)


def obtener_configuracion():
    """Lee la configuración base del sistema"""
    try:
        path = get_dbf_path('tablero_configura.dbf')
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

            return {
                "empresa": str(conf.get('EMPRESA', 'CONFIA')).strip().upper(),
                "almacenes": almacenes,
                "precios": [conf.get('PRECIO1'), conf.get('PRECIO2'), conf.get('PRECIO3')]
            }
    except Exception as e:
        print(f"Error leyendo configuración: {e}")

    return {"empresa": "CONFIA", "almacenes": [], "precios": []}

def obtener_nombre_empresa_global():
    conf = obtener_configuracion()
    return conf.get('empresa', 'CONFIA')

# ─── CONFIGURACIÓN DE AUTENTICACIÓN ────────────────────────────────────────
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

class User(UserMixin):
    def __init__(self, email, empresa, acceso):
        self.id = email
        self.empresa = empresa
        self.acceso = acceso

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
                        acceso=str(rec.get('ACCESO', '0000000')).strip()
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
@app.route('/')
@login_required
def index():
    return redirect(url_for('ventas_page'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    error = None
    nombre_logo = "SISTEMA EXPLORADOR"

    empresas = [d for d in os.listdir(DBF_DIR) if os.path.isdir(os.path.join(DBF_DIR, d))]
    empresas.sort()

    selected_empresa = None

    if request.method == 'POST':
        correo_input = request.form['correo']
        clave_input = request.form['clave']
        selected_empresa = request.form.get('empresa', '').strip().upper()

        if not selected_empresa or selected_empresa not in empresas:
            error = "Empresa no válida"
        else:
            path_users = os.path.join(DBF_DIR, selected_empresa, 'tablero_usuarios.DBF')
            if os.path.exists(path_users):
                try:
                    for u in DBF(path_users, encoding='latin-1'):
                        if (str(u['CORREO']).strip() == correo_input and
                                str(u['CLAVE']).strip() == clave_input):
                            empresa_usuario = selected_empresa

                            user_obj = User(
                                email=correo_input,
                                empresa=empresa_usuario,
                                acceso=str(u['ACCESO'])
                            )
                            login_user(user_obj)
                            session['empresa'] = empresa_usuario
                            return redirect(url_for('ventas_page'))
                    error = "Credenciales incorrectas"
                except Exception as e:
                    error = f"Error de acceso: {str(e)}"
            else:
                error = "Base de datos de usuarios no encontrada para esta empresa"

    return render_template('login.html', error=error, nombre_logo=nombre_logo, empresas=empresas, selected_empresa=selected_empresa)

@app.route('/logout')
@login_required
def logout():
    session.pop('empresa', None)
    logout_user()
    return redirect(url_for('login'))

# ─── RUTAS DE PÁGINAS ──────────────────────────────────────────────────────
@app.route('/ventas')
@login_required
def ventas_page():
    return render_template('ventas.html', empresa=current_user.empresa)

@app.route('/ventas/cobros-facturas')
@login_required
def ventas_cobros_facturas_page():
    if not current_user.tiene_permiso(1):
        return redirect(url_for('ventas_page', error='sin_permiso'))
    return render_template('ventas_cobros_facturas.html', empresa=current_user.empresa)

@app.route('/compras')
@login_required
def compras_page():
    if not current_user.tiene_permiso(2):
        return redirect(url_for('ventas_page', error='sin_permiso'))
    return render_template('compras.html', empresa=current_user.empresa)

@app.route('/inventario')
@login_required
def inventario_page():
    if not current_user.tiene_permiso(6):
        return redirect(url_for('ventas_page', error='sin_permiso'))
    return render_template('inventario.html', empresa=current_user.empresa)

@app.route('/cobros')
@login_required
def cobros_page():
    if not current_user.tiene_permiso(3):
        return redirect(url_for('ventas_page', error='sin_permiso'))
    return render_template('cobros.html', empresa=current_user.empresa)

@app.route('/cxc')
@login_required
def cxc_page():
    if not current_user.tiene_permiso(3):
        return redirect(url_for('ventas_page', error='sin_permiso'))
    return render_template('cxc.html', empresa=current_user.empresa)

@app.route('/cxp')
@login_required
def cxp_page():
    if not current_user.tiene_permiso(5):
        return redirect(url_for('ventas_page', error='sin_permiso'))
    return render_template('cxp.html', empresa=current_user.empresa)

@app.route('/bancos')
@login_required
def bancos_page():
    if not current_user.tiene_permiso(7):
        return redirect(url_for('ventas_page', error='sin_permiso'))
    return render_template('bancos.html', empresa=current_user.empresa)

# ─── ENDPOINTS DE API ──────────────────────────────────────────────────────

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
                if fecha_fin   and fecha_reg > fecha_fin:   continue

                vend = str(rec.get('VENDEDOR', '')).strip().upper()
                all_vendedores.add(vend)
                if vendedor and vendedor != 'TODOS' and vendedor != vend:
                    continue

                saldo_raw = safe_float(rec.get('SALDO'))
                tasa_dolar = 36.0
                saldo = saldo_raw if moneda == 'Bs' else round(saldo_raw / tasa_dolar, 2)

                total_gral += saldo
                nombre_grupo = str(rec.get('GRUPO', 'SIN GRUPO')).strip()
                resumen_grupos_dict[nombre_grupo] += saldo

                enveje["No Vencido"]  += safe_float(rec.get('NOVENCIDO'))
                enveje["1-7 Dias"]    += safe_float(rec.get('VENCIDO1'))
                enveje["8-14 Dias"]   += safe_float(rec.get('VENCIDO2'))
                enveje["15-21 Dias"]  += safe_float(rec.get('VENCIDO3'))
                enveje["22-30 Dias"]  += safe_float(rec.get('VENCIDO4'))
                enveje["+30 Dias"]    += safe_float(rec.get('VENCIDO5'))
                data_tabla.append({
                    "GRUPO": nombre_grupo,
                    "CLIENTE": str(rec.get('CLIENTE', '')).strip(),
                    "DOCUMENTO": str(rec.get('CODIGO', '')).strip(),
                    "FECHA": fecha_reg,
                    "DIAS": rec.get('DIAS_VENC', 0),
                    "SALDO": round(saldo, 2),
                    "VENDEDOR": vend
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

@app.route('/api/ventas', methods=['POST'])
@login_required
def get_ventas():
    params = request.json
    moneda = params.get('moneda', 'Bs')
    top_n = int(params.get('top_n', 10))
    fecha_inicio = params.get('fecha_inicio', '')
    fecha_fin = params.get('fecha_fin', '')
    vendedor = params.get('vendedor', '').strip()
    busqueda_cliente = params.get('busqueda_cliente', '').strip().upper()
    busqueda_producto = params.get('busqueda_producto', '').strip().upper()
    # ✅ CORRECCIÓN: leer filtro_caja (TomSelect, match exacto) en lugar de busqueda_caja (texto libre)
    filtro_caja = (params.get('filtro_caja') or params.get('busqueda_caja', '')).strip().upper()
    status_filtro = params.get('status', 'TODOS')

    nombres_completos = {}
    try:
        path_inv = get_dbf_path('tablero_inventario.DBF')
        if os.path.exists(path_inv):
            for item in DBF(path_inv, encoding='latin-1'):
                nombres_completos[str(item.get('CODIGO', '')).strip()] = str(item.get('DESCRIPCIO', '')).strip()
    except Exception as e:
        print(f"Error cargando inventario: {e}")

    # Inicialización de contadores generales
    ventas_tipo = {"Contado": 0.0, "Crédito": 0.0}
    por_zona = defaultdict(float)
    por_cliente = defaultdict(float)
    por_producto = defaultdict(float)
    por_vendedor = defaultdict(float)
    prods_por_vend = defaultdict(lambda: defaultdict(float))

    all_vendedores = set()
    all_zonas = set()
    all_clientes = set()
    all_productos = set()
    all_cajas = set()          # ✅ NUEVO: recolectar todas las cajas para el TomSelect
    clientes_unicos = set()

    facturas_unicas = set()
    facturas_contado_unicas = set()
    facturas_credito_unicas = set()

    fact_cont_monto = 0.0
    fact_cred_monto = 0.0
    total_igtf = 0.0
    total_gral = 0.0

    facturas_lista = []

    detalle_producto = {
        "cantidad_total": 0.0,
        "monto_total": 0.0,
        "facturas_unicas": set(),
        "detalles": []
    } if busqueda_producto else None

    detalles_temp = []

    try:
        path_fac = get_dbf_path('tablero_facturas.DBF')
        if os.path.exists(path_fac):
            for rec in DBF(path_fac, encoding='latin-1'):
                fecha_reg = parse_fecha(rec.get('FECHA'))

                if fecha_inicio and fecha_reg < fecha_inicio: continue
                if fecha_fin and fecha_reg > fecha_fin: continue

                vend = str(rec.get('VENDEDOR') or rec.get('CODVEN') or 'SIN VENDEDOR').strip()
                all_vendedores.add(vend)
                if vendedor and vendedor != 'TODOS' and vendedor != vend:
                    continue

                zona = str(rec.get('ZONA', 'SIN ZONA')).strip().upper()
                all_zonas.add(zona)

                cliente = str(rec.get('CLIENTE', 'S/C')).strip().upper()
                all_clientes.add(cliente)
                if busqueda_cliente and busqueda_cliente not in cliente:
                    continue

                cod_pro = str(rec.get('CODIGOPRO', '')).strip()
                producto = nombres_completos.get(cod_pro, str(rec.get('NOMBREPRO', 'S/N')).strip()).upper()
                all_productos.add(producto)

                if busqueda_producto and busqueda_producto not in producto:
                    continue

                caja = str(rec.get('CAJA', '')).strip().upper()
                if caja:
                    all_cajas.add(caja)   # ✅ Recolectar caja ANTES del filtro

                # ✅ CORRECCIÓN: match exacto (TomSelect lista) en lugar de búsqueda parcial
                if filtro_caja and filtro_caja != caja:
                    continue

                m_raw = safe_float(rec.get('MONTO'))
                factor = safe_float(rec.get('FACTOR')) or 1.0
                monto = m_raw if moneda == 'Bs' else (m_raw / factor)

                tipo_fact = str(rec.get('TIPO', '')).strip()
                tipo_texto = "Contado" if tipo_fact == '1' else "Crédito"

                if status_filtro != "TODOS" and tipo_texto != status_filtro:
                    continue

                nro_factura = str(rec.get('CODIGO', '')).strip()
                if nro_factura:
                    facturas_unicas.add(nro_factura)
                    if tipo_fact == '1':
                        facturas_contado_unicas.add(nro_factura)
                        fact_cont_monto += monto
                        ventas_tipo["Contado"] += monto
                    else:
                        facturas_credito_unicas.add(nro_factura)
                        fact_cred_monto += monto
                        ventas_tipo["Crédito"] += monto

                # ✅ IGTF — sumar el impuesto del registro
                total_igtf += safe_float(rec.get('IGTF'))

                total_gral += monto
                por_zona[zona] += monto
                por_cliente[cliente] += monto
                por_producto[producto] += monto
                por_vendedor[vend] += monto
                prods_por_vend[vend][producto] += monto
                clientes_unicos.add(cliente)

                facturas_lista.append({
                    "FECHA": fecha_reg,
                    "CLIENTE": cliente,
                    "VENDEDOR": vend,
                    "ZONA": zona,
                    "CAJA": caja,
                    "DOCUMENTO": nro_factura,
                    "TIPO": tipo_texto,
                    "MONTO": round(monto, 2)
                })

                if busqueda_producto:
                    cant = safe_float(rec.get('CANTIDAD'))
                    detalle_producto["cantidad_total"] += cant
                    detalle_producto["monto_total"] += monto
                    if nro_factura:
                        detalle_producto["facturas_unicas"].add(nro_factura)
                    detalles_temp.append({
                        "FECHA": fecha_reg,
                        "FACTURA": nro_factura,
                        "CAJA": caja,
                        "CLIENTE": cliente,
                        "VENDEDOR": vend,
                        "CANTIDAD": round(cant, 2),
                        "MONTO": round(monto, 2)
                    })

        if busqueda_producto:
            detalles_temp.sort(key=lambda x: x["FECHA"], reverse=True)
            detalle_producto["detalles"] = detalles_temp[:10]
            detalle_producto["facturas_unicas"] = len(detalle_producto["facturas_unicas"])

        def format_top(dico):
            return sorted(
                [{"label": k, "value": round(v, 2)} for k, v in dico.items()],
                key=lambda x: x['value'],
                reverse=True
            )[:top_n]

        top_vendedores = format_top(por_vendedor)

        detalles_vendedor = {}
        for v in top_vendedores:
            v_name = v['label']
            top_p = sorted(
                prods_por_vend[v_name].items(),
                key=lambda x: x[1],
                reverse=True
            )[:10]
            detalles_vendedor[v_name] = [
                {"label": p, "value": round(m, 2)}
                for p, m in top_p
            ]

        return jsonify({
            "status": "success",
            "total_gral": round(total_gral, 2),
            "resumen_tipo": {k: round(v, 2) for k, v in ventas_tipo.items()},
            "general": {
                "conteo_clientes": len(clientes_unicos),
                "total_facturas_unicas": len(facturas_unicas),
                "facturas_contado_unicas": len(facturas_contado_unicas),
                "fact_cont_monto": round(fact_cont_monto, 2),
                "facturas_credito_unicas": len(facturas_credito_unicas),
                "fact_cred_monto": round(fact_cred_monto, 2),
                "total_igtf": round(total_igtf, 2)
            },
            "zonas": format_top(por_zona),
            "clientes": format_top(por_cliente),
            "productos": format_top(por_producto),
            "vendedores": top_vendedores,
            "detalles_vendedor": detalles_vendedor,
            "lista_vendedores": sorted(list(all_vendedores)),
            "lista_zonas": sorted(list(all_zonas)),
            "lista_clientes": sorted(list(all_clientes)),
            "lista_productos": sorted(list(all_productos)),
            "lista_cajas": sorted(list(all_cajas)),   # ✅ NUEVO: para TomSelect de caja
            "facturas": facturas_lista[:1000],
            "detalle_producto": detalle_producto
        })

    except Exception as e:
        import traceback
        print(traceback.format_exc())
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500
    
# Asumiendo que tienes estas funciones ya definidas en tu proyecto:
# from tu_modulo import DBF, parse_fecha, safe_float, get_dbf_path, login_required

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
    # ✅ CORRECCIÓN 1: leer filtro_caja (match exacto desde TomSelect)
    filtro_caja     = (params.get('filtro_caja') or '').strip().upper()
    # ✅ CORRECCIÓN 2: leer cliente (búsqueda parcial)
    filtro_cliente  = (params.get('cliente') or '').strip().upper()

    def normalizar_forma(raw):
        if not raw or str(raw).strip() == '':
            return 'SIN FORMA'
        f = str(raw).strip().upper().replace('.', '').replace(' ', '')
        mapa = {
            'TDEBITO':       'T.DEBITO',
            'TCREDITO':      'T.CREDITO',
            'TRANSFERENCIA': 'TRANSFERENCIA',
            'DIVISAS':       'DIVISAS',
            'EFECTIVO':      'EFECTIVO',
            'POS':           'POS / TARJETA',
            'TARJETA':       'POS / TARJETA',
            'CHEQUE':        'CHEQUE',
            'DEPOSITO':      'DEPOSITO',
            'OTRO':          'OTRO',
        }
        return mapa.get(f, str(raw).strip().upper()) or 'SIN FORMA'

    total_cobrado   = 0.0
    por_forma       = defaultdict(float)
    por_vendedor    = defaultdict(float)
    por_caja        = defaultdict(float)
    data_tabla      = []

    all_vendedores  = set()
    all_formas      = set()
    all_cajas       = set()   # ✅ CORRECCIÓN 3: recolectar todas las cajas para TomSelect

    try:
        path = get_dbf_path('tablero_facturas.DBF')
        if not os.path.exists(path):
            return jsonify({"error": "Archivo de facturas no encontrado"}), 404

        for rec in DBF(path, encoding='latin-1'):
            fecha_reg = parse_fecha(rec.get('FECHA'))

            if fecha_inicio and fecha_reg < fecha_inicio: continue
            if fecha_fin    and fecha_reg > fecha_fin:    continue

            vendedor_norm = str(rec.get('VENDEDOR') or rec.get('CODVEN') or 'S/V').strip().upper()
            all_vendedores.add(vendedor_norm)

            caja = str(rec.get('CAJA', '')).strip().upper()
            if caja:
                all_cajas.add(caja)   # recolectar ANTES del filtro

            forma_raw = str(rec.get('FORMAPAGO') or rec.get('FORMA_PAGO') or '').strip()
            forma = normalizar_forma(forma_raw)
            all_formas.add(forma)

            cliente = str(rec.get('CLIENTE', 'S/C')).strip().upper()

            # ── Aplicar filtros ──────────────────────────────────────────
            if vendedor_filtro and vendedor_filtro != 'TODOS' and vendedor_filtro != vendedor_norm:
                continue

            # ✅ Filtro caja — match EXACTO (viene de TomSelect con valores reales)
            if filtro_caja and filtro_caja != caja:
                continue

            # ✅ Filtro cliente — búsqueda parcial (input texto)
            if filtro_cliente and filtro_cliente not in cliente:
                continue

            if forma_pago and forma_pago != 'TODAS' and forma_pago != forma:
                continue

            m_raw  = safe_float(rec.get('MONTO'))
            tasa   = safe_float(rec.get('FACTOR') or rec.get('TASADOLAR')) or 1.0
            monto  = m_raw if moneda == 'Bs' else (m_raw / tasa)

            total_cobrado       += monto
            por_forma[forma]    += monto
            por_vendedor[vendedor_norm] += monto
            por_caja[caja]      += monto

            if len(data_tabla) < 1000:
                data_tabla.append({
                    "CODIGO":    str(rec.get('CODIGO', '')).strip(),
                    "FECHA":     fecha_reg,
                    "CLIENTE":   cliente,
                    "VENDEDOR":  vendedor_norm,
                    "CAJA":      caja,
                    "FORMAPAGO": forma,
                    "MONTO":     round(monto, 2),
                })

        def format_top(dic):
            return sorted(
                [{"label": k or 'Sin dato', "value": round(v, 2)} for k, v in dic.items()],
                key=lambda x: x['value'], reverse=True
            )[:top_n]

        return jsonify({
            "status":          "success",
            "total_general":   round(total_cobrado, 2),
            "formas_pago":     format_top(por_forma),
            "vendedores":      format_top(por_vendedor),
            "cajas":           format_top(por_caja),
            "tabla":           data_tabla,
            "lista_vendedores": sorted(list(all_vendedores)),
            "lista_formas":    sorted([f for f in all_formas if f and f != 'SIN FORMA']),
            "lista_cajas":     sorted(list(all_cajas)),   # ✅ para poblar TomSelect de caja
        })

    except Exception as e:
        import traceback
        print("Error en /api/cobros-facturas:", traceback.format_exc())
        return jsonify({"error": str(e)}), 500
    

@app.route('/api/bancos', methods=['POST'])
@login_required
def get_bancos():
    params = request.json
    busqueda    = params.get('busqueda', '').upper().strip()
    moneda      = params.get('moneda', 'Bs')
    tipocuen    = params.get('tipocuen', '').strip()
    banco_filtro = params.get('banco', '').strip().upper()   # ← NUEVO: filtro por banco seleccionado

    data_movimientos = []
    saldos_por_cuenta = {} 
    totales = {"ingresos": 0, "egresos": 0}
    unique_tipos  = set()
    unique_bancos = set()   # ← Para poblar el select del frontend

    try:
        path = get_dbf_path('tablero_bancos.DBF')
        if os.path.exists(path):
            for rec in DBF(path, encoding='latin-1'):
                tipocuen_reg = str(rec.get('TIPOCUEN', '')).strip()
                unique_tipos.add(tipocuen_reg)

                banco_nom = str(rec.get('BANCO', '')).strip()
                unique_bancos.add(banco_nom)  # recolectamos todos los bancos

                if tipocuen and tipocuen != tipocuen_reg: 
                    continue

                # Filtro por banco (solo si se seleccionó uno específico)
                if banco_filtro and banco_filtro != banco_nom.upper():
                    continue

                nro_cuenta = str(rec.get('CUENTA', '')).strip()
                desc = str(rec.get('DESCRIPCIO', '')).strip()
                if busqueda and (busqueda not in banco_nom.upper() and busqueda not in desc.upper()):
                    continue

                debe = safe_float(rec.get('DEBE'))
                haber = safe_float(rec.get('HABER'))
                divisas = safe_float(rec.get('DIVISAS'))

                if moneda == 'Bs':
                    saldo_actual = safe_float(rec.get('SALDO'))
                    totales["ingresos"] += debe
                    totales["egresos"] += haber
                    debe_mov = debe
                    haber_mov = haber
                else:
                    saldo_actual = divisas
                    debe_mov = max(divisas, 0)
                    haber_mov = abs(min(divisas, 0))
                    totales["ingresos"] += debe_mov
                    totales["egresos"] += haber_mov

                saldos_por_cuenta[nro_cuenta] = {"banco": banco_nom, "saldo": saldo_actual}

                if len(data_movimientos) < 150:
                    data_movimientos.append({
                        "FECHA": parse_fecha(rec.get('FECHA')),
                        "BANCO": banco_nom,
                        "CUENTA": nro_cuenta,
                        "TIPO": str(rec.get('TIPOMOV', '')).strip(),
                        "DESCRIPCION": desc,
                        "DEBE": debe_mov,
                        "HABER": haber_mov
                    })

        distribucion_bancos = defaultdict(float)
        total_global = 0
        for c in saldos_por_cuenta.values():
            total_global += c['saldo']
            distribucion_bancos[c['banco']] += c['saldo']

        return jsonify({
            "totales": {
                "ingresos": round(totales["ingresos"], 2),
                "egresos": round(totales["egresos"], 2),
                "saldo_total": round(total_global, 2)
            },
            "tabla": data_movimientos,
            "bancos_chart": [{"BANCO": k, "V": round(v, 2)} for k, v in distribucion_bancos.items()],
            "tipos_cuentas": sorted(list(unique_tipos)),
            "lista_bancos": sorted([b for b in unique_bancos if b.strip()])  # ← Esto llena el select
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    
@app.route('/api/vendedores', methods=['GET'])
@login_required
def get_vendedores():
    all_vendedores = set()
    try:
        path_fac = get_dbf_path('tablero_facturas.DBF')
        if os.path.exists(path_fac):
            for rec in DBF(path_fac, encoding='latin-1'):
                vend = str(rec.get('VENDEDOR') or rec.get('CODVEN') or 'SIN VENDEDOR').strip()
                if vend and vend != 'SIN VENDEDOR':
                    all_vendedores.add(vend)
        return jsonify({
            "status": "success",
            "vendedores": sorted(list(all_vendedores))
        })
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500    


@app.route('/api/inventario', methods=['POST'])
@login_required
def get_inventario():
    params = request.json or {}
    
    f_prod          = (params.get('producto') or '').strip().upper()
    valorizar_a     = params.get('valorizar_a', 'costo')
    
    # Filtros dinámicos por característica (carac1, carac2, etc.)
    filtros_carac = {}
    for i in '1234':
        key = f'carac{i}'
        if key in params:
            filtros_carac[i] = (params[key] or '').strip().upper()

    data_tabla = []
    totales = {
        "articulos": 0,
        "existencia": 0.0,
        "valor_total": 0.0,
        "kilos": 0.0
    }
    por_marca = defaultdict(float)  # Usaremos CARAC1 como ejemplo para gráfico, pero se puede hacer dinámico después
    
    nombres_precios = {"1": "Precio 1", "2": "Precio 2", "3": "Precio 3"}
    nombres_carac   = {}
    has_carac       = {"1": False, "2": False, "3": False, "4": False}
    nombres_encontrados = False

    try:
        path = get_dbf_path('tablero_inventario.DBF')
        if not os.path.exists(path):
            return jsonify({"error": "Archivo de inventario no encontrado"}), 404

        for rec in DBF(path, encoding='latin-1', ignore_missing_memofile=True):
            if not nombres_encontrados:
                for i in '123':
                    np_key = f'NOMBREP{i}'
                    nombre = str(rec.get(np_key, '')).strip()
                    if nombre and nombre.lower() not in ['', 'none', 'null', ' ']:
                        nombres_precios[i] = nombre
                for i in '1234':
                    nc_key = f'NOMBREC{i}'
                    nombre = str(rec.get(nc_key, '')).strip()
                    if nombre and nombre.lower() not in ['', 'none', 'null', ' ']:
                        nombres_carac[i] = nombre
                nombres_encontrados = True

            desc = str(rec.get('DESCRIPCIO', '')).strip()
            codigo = str(rec.get('CODIGO', '')).strip()

            if f_prod and f_prod not in desc.upper() and f_prod not in codigo:
                continue

            # Filtros dinámicos por característica
            pasar = True
            for idx, filtro_val in filtros_carac.items():
                carac_val = str(rec.get(f'CARAC{idx}', '')).strip().upper()
                if filtro_val and filtro_val not in carac_val:
                    pasar = False
                    break
            if not pasar:
                continue

            # Detectar presencia de datos en características
            for i in '1234':
                val = str(rec.get(f'CARAC{i}', '')).strip()
                if val:
                    has_carac[i] = True

            existencia = safe_float(rec.get('EXISTENCIA'))
            monto = safe_float(rec.get('MONTO'))
            kilos = safe_float(rec.get('KILOS'))
            precio1 = safe_float(rec.get('PRECIO1'))
            precio2 = safe_float(rec.get('PRECIO2'))
            precio3 = safe_float(rec.get('PRECIO3'))

            if valorizar_a == 'precio1':
                valor_unit = precio1
            elif valorizar_a == 'precio2':
                valor_unit = precio2
            elif valorizar_a == 'precio3':
                valor_unit = precio3
            else:
                valor_unit = monto / existencia if existencia > 0 else 0.0

            valor_total_item = valor_unit * existencia

            totales["articulos"] += 1
            totales["existencia"] += existencia
            totales["valor_total"] += valor_total_item
            totales["kilos"] += kilos
            por_marca[str(rec.get('CARAC1', 'Sin marca')).strip()] += valor_total_item

            costo_unitario = monto / existencia if existencia > 0 else 0.0

            if len(data_tabla) < 1500:
                item = {
                    "CODIGO": codigo,
                    "DESCRIPCION": desc,
                    "EXISTENCIA": existencia,
                    "COSTO_UNITARIO": round(costo_unitario, 4),
                    "PRECIO1": precio1,
                    "PRECIO2": precio2,
                    "PRECIO3": precio3,
                    "VALOR_TOTAL": round(valor_total_item, 2),
                    "TOTAL_EMPAQUE": kilos,
                }
                # Agregar todas las características presentes
                for i in '1234':
                    val = str(rec.get(f'CARAC{i}', '')).strip()
                    if val:
                        item[f'CARAC{i}'] = val
                data_tabla.append(item)

        # Características activas (solo las que tienen datos)
        caracteristicas_activas = {}
        for i in '1234':
            if has_carac[i]:
                caracteristicas_activas[i] = nombres_carac.get(i, f"Clasificación {i}")

        # Listas únicas para cada característica activa
        filtros_dinamicos = {}
        for idx, nombre in caracteristicas_activas.items():
            valores = sorted(set(
                str(item.get(f'CARAC{idx}', '')).strip()
                for item in data_tabla
                if str(item.get(f'CARAC{idx}', '')).strip()
            ))
            filtros_dinamicos[f'filtro_carac{idx}'] = valores

        # Gráfico (por ahora usamos CARAC1 como ejemplo; se puede hacer configurable después)
        marcas_chart = sorted(
            [{"MARCA": k, "V": round(v, 2)} for k, v in por_marca.items()],
            key=lambda x: x["V"], reverse=True
        )[:10]

        return jsonify({
            "totales": {
                "articulos": totales["articulos"],
                "existencia": round(totales["existencia"], 2),
                "valor_total": round(totales["valor_total"], 2),
                "kilos": round(totales["kilos"], 2)
            },
            "tabla": data_tabla,
            "marcas_chart": marcas_chart,
            "nombres_precios": nombres_precios,
            "caracteristicas": caracteristicas_activas,       # {"1": "Marca", "2": "Grupo", ...}
            "filtros_dinamicos": filtros_dinamicos,           # {"filtro_carac1": [...], "filtro_carac2": [...]}
            "valorizar_a": valorizar_a
        })

    except Exception as e:
        import traceback
        print("Error en /api/inventario:", str(e))
        print(traceback.format_exc())
        return jsonify({"error": str(e)}), 500


@app.route('/api/cartera_cxp', methods=['POST'])
@login_required
def get_cartera_cxp():
    params = request.json or {}
    fecha_inicio = params.get('fecha_inicio', '')
    fecha_fin   = params.get('fecha_fin', '')
    moneda      = params.get('moneda', 'Bs')
    proveedor   = params.get('proveedor', '').upper().strip()
    vendedor    = params.get('vendedor', '').upper().strip()
    busqueda    = params.get('busqueda', '').upper().strip()

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
                if fecha_fin   and fecha_reg > fecha_fin:   continue

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
                tasa_dolar = 36.0
                saldo = saldo_raw if moneda == 'Bs' else round(saldo_raw / tasa_dolar, 2)

                total_gral += saldo
                grupo = str(rec.get('GRUPO', 'SIN GRUPO')).strip()
                resumen_grupos_dict[grupo] += saldo

                enveje["No Vencido"]  += safe_float(rec.get('NOVENCIDO'))
                enveje["1-7 Dias"]    += safe_float(rec.get('VENCIDO1'))
                enveje["8-14 Dias"]   += safe_float(rec.get('VENCIDO2'))
                enveje["15-21 Dias"]  += safe_float(rec.get('VENCIDO3'))
                enveje["22-30 Dias"]  += safe_float(rec.get('VENCIDO4'))
                enveje["+30 Dias"]    += safe_float(rec.get('VENCIDO5'))
                data_tabla.append({
                    "GRUPO": grupo,
                    "PROVEEDOR": prov,
                    "VENDEDOR": vend,
                    "DOCUMENTO": str(rec.get('CODIGO', '')).strip(),
                    "FECHA": fecha_reg,
                    "DIAS": int(rec.get('DIAS_VENC', 0)),
                    "SALDO": round(saldo, 2)
                })

        resumen_final = sorted(
            [{"GRUPO": k, "MONTO": round(v, 2)} for k, v in resumen_grupos_dict.items() if abs(v) > 0.01],
            key=lambda x: x['MONTO'], reverse=True
        )

        return jsonify({
            "total": round(total_gral, 2),
            "envejecimiento": [{"label": k, "value": round(v, 2)} for k, v in enveje.items()],
            "resumen_grupos": resumen_final,
            "tabla": data_tabla[:1000],
            "proveedores": sorted(list(all_proveedores)),
            "vendedores": sorted(list(all_vendedores))
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/cobros', methods=['POST'])
@login_required
def get_cobros():
    params = request.json or {}
    moneda = params.get('moneda', 'Bs')
    top_n = int(params.get('top_n', 10))
    f_inicio = params.get('fecha_inicio', '')
    f_fin = params.get('fecha_fin', '')
    
    forma_pago_filtro = params.get('forma_pago', 'TODAS').strip().upper()
    cliente_filtro = params.get('cliente', '').strip().upper()
    caja_filtro = (params.get('caja') or 'TODAS').strip().upper()   # ← NUEVO

    forma_normalizar = {
        'T.DEBITO': 'T.DEBITO',
        'TDEBITO': 'T.DEBITO',
        'TCREDITO': 'T.CREDITO',
        'T.CREDITO': 'T.CREDITO',
        'TRANSFERENCIA': 'TRANSFERENCIA',
        'DIVISAS': 'DIVISAS',
        'EFECTIVO': 'EFECTIVO',
        'POS': 'POS / TARJETA',
        'TARJETA': 'POS / TARJETA',
        'CHEQUE': 'CHEQUE',
        'DEPOSITO': 'DEPOSITO',
        'OTRO': 'OTRO',
        '': 'SIN INFORMACION',
        'S/I': 'SIN INFORMACION'
    }

    totales = {"cobrado": 0.0}
    por_forma = defaultdict(float)
    por_cobrador = defaultdict(float)
    por_caja = defaultdict(float)
    por_cliente = defaultdict(float)
    data_tabla = []
    cajas_unicas = set()   # ← NUEVO

    try:
        path = get_dbf_path('tablero_cobros_cxc.DBF')
        if not os.path.exists(path):
            return jsonify({"error": "Archivo de cobros no encontrado"}), 404

        for rec in DBF(path, encoding='latin-1'):
            fecha_reg = parse_fecha(rec.get('FECHA'))
            
            if f_inicio and fecha_reg < f_inicio: continue
            if f_fin and fecha_reg > f_fin: continue

            cliente = str(rec.get('CLIENTE', 'S/C')).strip().upper()
            if cliente_filtro and cliente_filtro not in cliente:
                continue

            caja = str(rec.get('CAJA', 'S/C')).strip().upper()
            cajas_unicas.add(caja)   # ← recolectamos todas

            if caja_filtro != 'TODAS' and caja != caja_filtro:
                continue   # ← filtro por caja

            forma_raw = str(rec.get('FORMA_PAGO', 'S/I')).strip().upper()
            forma = forma_normalizar.get(forma_raw, forma_raw)

            if forma_pago_filtro != 'TODAS' and forma != forma_pago_filtro:
                continue

            m_raw = safe_float(rec.get('MONTO'))
            tasa = safe_float(rec.get('TASA_DOLAR')) or 1.0
            monto = m_raw if moneda == 'Bs' else (m_raw / tasa)

            cobrador = str(rec.get('COBRADOR', 'S/C')).strip()

            totales["cobrado"] += monto
            por_forma[forma] += monto
            por_cobrador[cobrador] += monto
            por_caja[caja] += monto
            por_cliente[cliente] += monto

            if len(data_tabla) < 500:
                data_tabla.append({
                    "RECIBO": str(rec.get('RECIBO', '')).strip(),
                    "FECHA": fecha_reg.strftime('%Y-%m-%d') if isinstance(fecha_reg, datetime) else fecha_reg,
                    "CLIENTE": cliente,
                    "COBRADOR": cobrador,
                    "CAJA": caja,
                    "FORMA": forma,
                    "MONTO": round(monto, 2),
                    "TASA": tasa
                })

        def format_chart(dico):
            return sorted(
                [{"label": k if k else 'Sin dato', "value": round(v, 2)} 
                 for k, v in dico.items() if v > 0],
                key=lambda x: x['value'], reverse=True
            )

        return jsonify({
            "total_general": round(totales["cobrado"], 2),
            "formas_pago": format_chart(por_forma),
            "cobradores": format_chart(por_cobrador),
            "cajas": format_chart(por_caja),
            "clientes": format_chart(por_cliente)[:top_n],
            "tabla": data_tabla,
            "cajas_lista": sorted([c for c in cajas_unicas if c and c != 'S/C'])   # ← lo que necesitas
        })

    except Exception as e:
        import traceback
        print("Error en /api/cobros:", traceback.format_exc())
        return jsonify({"error": str(e)}), 500
    
@app.route('/api/compras', methods=['POST'])
@login_required
def get_compras():
    params       = request.json or {}
    moneda       = params.get('moneda', 'Bs')
    top_n        = int(params.get('top_n', 15))
    f_inicio     = params.get('fecha_inicio', '')
    f_fin        = params.get('fecha_fin', '')
    # ✅ Filtros desde TomSelect — match exacto si viene valor, vacío = todos
    f_prov       = (params.get('proveedor') or '').strip().upper()
    f_prod       = (params.get('producto')  or '').strip().upper()
    prod_criterio = params.get('prod_criterio', 'monto')

    totales_compra      = {"Contado": 0.0, "Crédito": 0.0, "Otros": 0.0}
    por_proveedor       = defaultdict(float)
    por_producto_monto  = defaultdict(float)
    por_producto_unid   = defaultdict(float)
    por_marca           = defaultdict(float)

    # ✅ Listas para poblar TomSelects
    all_proveedores = set()
    all_productos   = set()

    total_gral = 0.0

    # ✅ Detalle del producto seleccionado (qué proveedor, cuándo, cuánto)
    detalle_producto = {
        "cantidad_total":    0.0,
        "monto_total":       0.0,
        "proveedores_unicos": set(),
        "detalles":          []
    } if f_prod else None

    detalles_temp = []

    try:
        path = get_dbf_path('tablero_compras.DBF')
        if os.path.exists(path):
            for rec in DBF(path, encoding='latin-1', ignore_missing_memofile=True):
                prov_reg  = str(rec.get('PROVEEDOR', 'S/P')).strip().upper()
                prod_reg  = str(rec.get('NOMBREPRO', 'S/P')).strip().upper()
                fecha_reg = parse_fecha(rec.get('FECHA'))

                # Recolectar listas ANTES de filtrar
                all_proveedores.add(prov_reg)
                all_productos.add(prod_reg)

                # ── Filtros activos ──────────────────────────────────────
                # Proveedor: match exacto si viene del TomSelect
                if f_prov and f_prov != prov_reg:
                    continue
                # Producto: búsqueda parcial (puede ser substring)
                if f_prod and f_prod not in prod_reg:
                    continue
                if f_inicio and fecha_reg < f_inicio:
                    continue
                if f_fin and fecha_reg > f_fin:
                    continue

                m_raw  = safe_float(rec.get('MONTO'))
                factor = safe_float(rec.get('FACTOR')) or 1.0
                monto  = m_raw if moneda == 'Bs' else (m_raw / factor)
                cant   = safe_float(rec.get('CANTIDAD'))
                tipo   = str(rec.get('TIPO', '')).strip()

                tipo_texto = "Contado" if tipo == '1' else ("Crédito" if tipo == '2' else "Otros")
                totales_compra[tipo_texto] += monto
                total_gral += monto

                por_proveedor[prov_reg]      += monto
                por_producto_monto[prod_reg] += monto
                por_producto_unid[prod_reg]  += cant
                por_marca[str(rec.get('CLASI1', 'SIN MARCA')).strip()] += monto

                # ✅ Acumular detalle si hay producto seleccionado
                if f_prod and detalle_producto is not None:
                    detalle_producto["cantidad_total"] += cant
                    detalle_producto["monto_total"]    += monto
                    detalle_producto["proveedores_unicos"].add(prov_reg)
                    nro_doc = str(rec.get('CODIGO', '')).strip()
                    detalles_temp.append({
                        "FECHA":     fecha_reg,
                        "DOCUMENTO": nro_doc,
                        "PROVEEDOR": prov_reg,
                        "TIPO":      tipo_texto,
                        "CANTIDAD":  round(cant, 2),
                        "MONTO":     round(monto, 2),
                    })

        # Ordenar detalles del producto por fecha desc, tomar top 200
        if f_prod and detalle_producto is not None:
            detalles_temp.sort(key=lambda x: x["FECHA"], reverse=True)
            detalle_producto["detalles"]          = detalles_temp[:200]
            detalle_producto["proveedores_unicos"] = len(detalle_producto["proveedores_unicos"])
            detalle_producto["monto_total"]        = round(detalle_producto["monto_total"], 2)
            detalle_producto["cantidad_total"]     = round(detalle_producto["cantidad_total"], 2)

        def format_top(dico, label_key):
            return sorted(
                [{label_key: k, "V": round(v, 2)} for k, v in dico.items() if v > 0],
                key=lambda x: x["V"], reverse=True
            )[:top_n]

        return jsonify({
            "totales":          {k: round(v, 2) for k, v in totales_compra.items()},
            "total_general":    round(total_gral, 2),
            "proveedores":      format_top(por_proveedor,      "PROVEEDOR"),
            "productos_monto":  format_top(por_producto_monto, "PRODUCTO"),
            "productos_unid":   format_top(por_producto_unid,  "PRODUCTO"),
            "marcas":           format_top(por_marca,          "MARCA"),
            # ✅ Listas para TomSelects
            "lista_proveedores": sorted([p for p in all_proveedores if p and p != 'S/P']),
            "lista_productos":   sorted([p for p in all_productos   if p and p != 'S/P']),
            # ✅ Detalle del producto seleccionado
            "detalle_producto":  detalle_producto,
        })

    except Exception as e:
        import traceback
        print("Error en /api/compras:", traceback.format_exc())
        return jsonify({"error": str(e)}), 500
    
@app.route('/api/cobranzas', methods=['POST'])
@login_required
def api_cobranzas():
    params = request.get_json() or {}
    fecha_inicio = params.get('fecha_inicio')
    fecha_fin    = params.get('fecha_fin')
    moneda       = params.get('moneda', 'Bs')
    caja_filtro  = (params.get('caja') or 'TODAS').upper().strip()

    total_general = 0.0
    conteo = 0
    por_forma = defaultdict(float)
    por_dia = defaultdict(float)
    cajas_unicas = set()
    formas_orden = []

    try:
        path = get_dbf_path('tablero_cobros_cxc.DBF')  # ajusta el nombre si es diferente
        if not os.path.exists(path):
            return jsonify({"error": "Archivo de cobros no encontrado"}), 404

        for rec in DBF(path, encoding='latin-1'):
            fecha_str = parse_fecha(rec.get('FECHA'))
            if fecha_inicio and fecha_str < fecha_inicio: continue
            if fecha_fin and fecha_str > fecha_fin: continue

            caja = str(rec.get('CAJA', 'S/C')).strip().upper()
            cajas_unicas.add(caja)

            if caja_filtro != 'TODAS' and caja != caja_filtro:
                continue

            monto_raw = safe_float(rec.get('MONTO'))
            tasa = safe_float(rec.get('TASA_DOLAR') or 1.0)
            monto = monto_raw if moneda == 'Bs' else round(monto_raw / tasa, 2)

            # Se suma tal cual → negativos restan (contabilidad neta)
            total_general += monto
            conteo += 1
            forma = str(rec.get('FORMA_PAGO', 'SIN FORMA')).strip().upper()
            por_forma[forma] += monto
            por_dia[fecha_str] += monto

        ticket_promedio = round(total_general / conteo, 2) if conteo > 0 else 0.0

        formas_orden = sorted(
            [{"FORMA": k or "Sin forma", "V": round(v, 2), "P": round(v / total_general * 100, 1) if total_general != 0 else 0}
             for k, v in por_forma.items()],
            key=lambda x: abs(x["V"]), reverse=True
        )

        historico = sorted(
            [{"F": f, "V": round(v, 2)} for f, v in por_dia.items()],
            key=lambda x: x["F"]
        )

        return jsonify({
            "total_general": round(total_general, 2),
            "ticket_promedio": ticket_promedio,
            "conteo": conteo,
            "formas_pago": formas_orden,
            "historico": historico,
            "cajas": sorted(list(cajas_unicas))
        })

    except Exception as e:
        import traceback
        print(traceback.format_exc())
        return jsonify({"error": str(e)}), 500

port = int(os.environ.get('PORT', 5000))
app.run(debug=False, host='0.0.0.0', port=port)