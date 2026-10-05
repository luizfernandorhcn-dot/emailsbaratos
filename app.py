import os
import sqlite3
import uuid
import json
import logging
from datetime import datetime
from functools import wraps
import jinja2
from flask import Flask, render_template, request, jsonify, session, redirect, url_for, send_from_directory
import requests

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'loja_keys_super_secret_key_2026_xyz')

DB_PATH = os.path.join(BASE_DIR, 'database.db')

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with get_db() as conn:
        cursor = conn.cursor()
        
        # Configurações do sistema
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        ''')
        
        # Categorias
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS categories (
                code TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                price REAL NOT NULL,
                badge TEXT,
                description TEXT
            )
        ''')
        
        # Estoque
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS keys (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                category_code TEXT NOT NULL,
                key_value TEXT NOT NULL,
                status TEXT DEFAULT 'available',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                sold_at TIMESTAMP,
                order_id TEXT,
                FOREIGN KEY (category_code) REFERENCES categories(code)
            )
        ''')
        
        # Pedidos e Pagamentos
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS orders (
                id TEXT PRIMARY KEY,
                category_code TEXT NOT NULL,
                amount REAL NOT NULL,
                status TEXT DEFAULT 'pending',
                payer_email TEXT,
                mp_payment_id TEXT,
                qr_code TEXT,
                qr_code_base64 TEXT,
                delivered_key TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (category_code) REFERENCES categories(code)
            )
        ''')
        
        # Credenciais oficiais e Senha Mestra
        MP_ACCESS_TOKEN = 'APP_USR-5018438626901279-100420-f423d886185a97e1962841e55156ec32-3386945777'
        SECURE_PASSWORD = 'Z8#mK9!vP2@wL5$qF7'
        cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('admin_password', ?)", (SECURE_PASSWORD,))
        cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('mp_access_token', ?)", (MP_ACCESS_TOKEN,))
        cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('test_mode', 'false')")
        cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('store_name', 'DIGITAL STORE')")
        
        # Categorias solicitadas: GOOGLE, X, FACE
        default_categories = [
            ('G', 'GOOGLE', 3.50, 'Mais Vendido', 'Acesso imediato com entrega automática após confirmação do PIX.'),
            ('X', 'X', 3.50, 'Disponível', 'Acesso imediato com entrega automática após confirmação do PIX.'),
            ('F', 'FACE', 3.50, 'Destaque', 'Acesso imediato com entrega automática após confirmação do PIX.')
        ]
        
        for code, name, price, badge, desc in default_categories:
            cursor.execute('''
                INSERT OR REPLACE INTO categories (code, name, price, badge, description)
                VALUES (?, ?, ?, ?, ?)
            ''', (code, name, price, badge, desc))
            
        conn.commit()

init_db()

def get_setting(key, default=''):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT value FROM settings WHERE key = ?", (key,))
        row = cursor.fetchone()
        return row['value'] if row else default

def set_setting(key, value):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, value))
        conn.commit()

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('is_admin'):
            return jsonify({'success': False, 'message': 'Acesso não autorizado'}), 401
        return f(*args, **kwargs)
    return decorated_function

# ==========================================================
# CONFIGURAÇÃO DE TEMPLATES MULTI-DIRETÓRIO & EMBUTIDOS
# ==========================================================

# Lê templates do disco se existirem
def load_file_content(path, default=""):
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return f.read()
        except Exception:
            pass
    return default

index_file_on_disk = os.path.join(BASE_DIR, 'templates', 'index.html')
if not os.path.exists(index_file_on_disk):
    index_file_on_disk = os.path.join(BASE_DIR, 'index.html')

admin_file_on_disk = os.path.join(BASE_DIR, 'templates', 'admin.html')
if not os.path.exists(admin_file_on_disk):
    admin_file_on_disk = os.path.join(BASE_DIR, 'admin.html')

search_template_dirs = [
    os.path.join(BASE_DIR, 'templates'),
    BASE_DIR
]
try:
    for root, dirs, files in os.walk(BASE_DIR):
        if 'index.html' in files or 'admin.html' in files:
            if root not in search_template_dirs:
                search_template_dirs.append(root)
except Exception:
    pass

# Templates embutidos de segurança máxima caso arquivos não tenham sido enviados ao GitHub
EMBEDDED_INDEX = load_file_content(index_file_on_disk, """<!DOCTYPE html>
<html lang="pt-BR" class="dark"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"><title>DIGITAL STORE</title><script src="https://cdn.tailwindcss.com"></script><link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.1/css/all.min.css"><script src="https://cdn.jsdelivr.net/npm/canvas-confetti@1.6.0/dist/confetti.browser.min.js"></script><link rel="stylesheet" href="/static/css/style.css"></head><body class="bg-[#090d16] text-white p-4"><div class="max-w-4xl mx-auto py-10 text-center"><h1 class="text-3xl font-black mb-2">DIGITAL STORE</h1><p class="text-slate-400 mb-8">Entrega Automática via PIX</p><div id="categories-grid" class="grid grid-cols-1 md:grid-cols-3 gap-6"></div></div><script src="/static/js/store.js"></script></body></html>""")

EMBEDDED_ADMIN = load_file_content(admin_file_on_disk, """<!DOCTYPE html>
<html lang="pt-BR" class="dark"><head><meta charset="UTF-8"><title>Painel</title><script src="https://cdn.tailwindcss.com"></script><link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.1/css/all.min.css"><link rel="stylesheet" href="/static/css/style.css"></head><body class="bg-[#090d16] text-white p-6"><div id="login-container" class="max-w-sm mx-auto my-20 p-6 bg-slate-900 rounded-2xl"><form id="admin-login-form" onsubmit="handleLogin(event)"><input type="password" id="admin-password-input" placeholder="Senha mestra" class="w-full p-3 rounded bg-slate-800 mb-3"><button type="submit" id="btn-login" class="w-full p-3 bg-indigo-600 rounded font-bold">Entrar</button></form></div><div id="admin-dashboard" class="hidden max-w-4xl mx-auto"><h2 class="text-2xl font-bold mb-4">Painel de Estoque</h2><div id="stat-revenue" class="text-xl font-bold mb-4">R$ 0,00</div><textarea id="keys-textarea" class="w-full p-3 rounded bg-slate-800 text-white mb-2"></textarea><select id="key-category-select" class="p-2 bg-slate-800 mb-2"><option value="G">GOOGLE</option><option value="X">X</option><option value="F">FACE</option></select><button onclick="handleAddKeys(event)" id="btn-submit-keys" class="p-3 bg-emerald-500 text-black font-bold rounded">Salvar</button></div><script src="/static/js/admin.js"></script></body></html>""")

# Configura o carregador do Jinja2 para NUNCA dar TemplateNotFound
app.jinja_env.loader = jinja2.ChoiceLoader([
    jinja2.FileSystemLoader(search_template_dirs),
    jinja2.DictLoader({
        'index.html': EMBEDDED_INDEX,
        'admin.html': EMBEDDED_ADMIN
    })
])

# Rotas de fallback para arquivos estáticos (CSS / JS)
@app.route('/static/<path:filename>')
def serve_custom_static(filename):
    static_folder = os.path.join(BASE_DIR, 'static')
    full_path = os.path.join(static_folder, filename)
    if os.path.exists(full_path):
        return send_from_directory(static_folder, filename)
    if os.path.exists(os.path.join(BASE_DIR, filename)):
        return send_from_directory(BASE_DIR, filename)
    base_name = os.path.basename(filename)
    if os.path.exists(os.path.join(BASE_DIR, base_name)):
        return send_from_directory(BASE_DIR, base_name)
    return "Arquivo não encontrado", 404

# ==========================================================
# ROTAS PÚBLICAS / CLIENTE
# ==========================================================

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/store-info', methods=['GET'])
def get_store_info():
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT c.code, c.name, c.price, c.badge, c.description,
                   COUNT(k.id) as stock
            FROM categories c
            LEFT JOIN keys k ON c.code = k.category_code AND k.status = 'available'
            GROUP BY c.code
            ORDER BY c.code ASC
        ''')
        categories = [dict(row) for row in cursor.fetchall()]
        
        mp_token = get_setting('mp_access_token', '').strip()
        test_mode = get_setting('test_mode', 'false') == 'true'
        has_mp = bool(mp_token)
        store_name = get_setting('store_name', 'DIGITAL STORE')
        
        return jsonify({
            'success': True,
            'categories': categories,
            'has_mercadopago': has_mp,
            'test_mode': test_mode,
            'store_name': store_name
        })

@app.route('/api/create-order', methods=['POST'])
def create_order():
    data = request.get_json() or {}
    category_code = data.get('category_code', '').upper()
    payer_email = data.get('payer_email', '').strip()
    payer_cpf = data.get('payer_cpf', '').strip()
    clean_cpf = ''.join(filter(str.isdigit, payer_cpf))
    
    if not payer_email or '@' not in payer_email:
        payer_email = "comprador@gmail.com"
    
    if category_code not in ['G', 'X', 'F']:
        return jsonify({'success': False, 'message': 'Categoria inválida. Escolha GOOGLE, X ou FACE'}), 400
        
    with get_db() as conn:
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT COUNT(*) as count FROM keys
            WHERE category_code = ? AND status = 'available'
        ''', (category_code,))
        stock_count = cursor.fetchone()['count']
        
        if stock_count <= 0:
            return jsonify({'success': False, 'message': f'Desculpe, o item está esgotado no momento.'}), 400

        cursor.execute("SELECT * FROM categories WHERE code = ?", (category_code,))
        category = cursor.fetchone()
        price = category['price'] if category else 3.50

        order_id = f"PED_{datetime.now().strftime('%Y%m%d%H%M%S')}_{uuid.uuid4().hex[:6]}"
        
        mp_token = get_setting('mp_access_token', '').strip()
        test_mode = get_setting('test_mode', 'false') == 'true'
        
        qr_code = ""
        qr_code_base64 = ""
        mp_payment_id = ""
        
        if mp_token:
            try:
                headers = {
                    "Authorization": f"Bearer {mp_token}",
                    "Content-Type": "application/json",
                    "X-Idempotency-Key": str(uuid.uuid4())
                }
                
                payer_payload = {
                    "email": payer_email,
                    "first_name": "Cliente"
                }
                if len(clean_cpf) == 11:
                    payer_payload["identification"] = {
                        "type": "CPF",
                        "number": clean_cpf
                    }
                
                payload = {
                    "transaction_amount": float(price),
                    "description": f"Compra {category['name']} - {order_id}",
                    "payment_method_id": "pix",
                    "payer": payer_payload
                }
                
                response = requests.post(
                    "https://api.mercadopago.com/v1/payments",
                    headers=headers,
                    json=payload,
                    timeout=15
                )
                
                if response.status_code in [200, 201]:
                    res_data = response.json()
                    mp_payment_id = str(res_data.get('id', ''))
                    poi = res_data.get('point_of_interaction', {})
                    td = poi.get('transaction_data', {})
                    qr_code = td.get('qr_code', '')
                    qr_code_base64 = td.get('qr_code_base64', '')
                else:
                    logging.error(f"Erro Mercado Pago: {response.text}")
                    try:
                        err_json = response.json()
                        err_msg = err_json.get('message') or err_json.get('cause', [{}])[0].get('description') or response.text
                    except Exception:
                        err_msg = response.text
                    return jsonify({
                        'success': False,
                        'message': f"O Mercado Pago recusou a criação do PIX: {err_msg}"
                    }), 400
            except Exception as e:
                logging.error(f"Exceção ao chamar Mercado Pago: {str(e)}")
                return jsonify({'success': False, 'message': f'Erro ao conectar com Mercado Pago: {str(e)}'}), 500
        else:
            if not test_mode:
                return jsonify({'success': False, 'message': 'Access Token não configurado'}), 400
                    
        is_mock = False
        if not qr_code:
            is_mock = True
            qr_code = f"00020126580014br.gov.bcb.pix0136{uuid.uuid4()}520400005303986540{price:.2f}5802BR5913LOJA_DE_KEYS6009SAO_PAULO62070503***6304DEMO"
            mp_payment_id = f"SIM_{uuid.uuid4().hex[:10]}"
            
        cursor.execute('''
            INSERT INTO orders (id, category_code, amount, status, payer_email, mp_payment_id, qr_code, qr_code_base64)
            VALUES (?, ?, ?, 'pending', ?, ?, ?, ?)
        ''', (order_id, category_code, price, payer_email, mp_payment_id, qr_code, qr_code_base64))
        conn.commit()

        return jsonify({
            'success': True,
            'order_id': order_id,
            'amount': price,
            'category_name': category['name'],
            'qr_code': qr_code,
            'qr_code_base64': qr_code_base64,
            'is_mock': is_mock,
            'test_mode': test_mode or not bool(mp_token)
        })

@app.route('/api/order-status/<order_id>', methods=['GET'])
def check_order_status(order_id):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM orders WHERE id = ?", (order_id,))
        order = cursor.fetchone()
        
        if not order:
            return jsonify({'success': False, 'message': 'Pedido não encontrado'}), 404
            
        if order['status'] == 'approved':
            return jsonify({
                'success': True,
                'status': 'approved',
                'delivered_key': order['delivered_key'],
                'category_code': order['category_code'],
                'amount': order['amount']
            })
            
        mp_payment_id = order['mp_payment_id']
        mp_token = get_setting('mp_access_token', '').strip()
        
        if mp_token and mp_payment_id and not mp_payment_id.startswith('SIM_'):
            try:
                headers = {"Authorization": f"Bearer {mp_token}"}
                mp_resp = requests.get(
                    f"https://api.mercadopago.com/v1/payments/{mp_payment_id}",
                    headers=headers,
                    timeout=8
                )
                if mp_resp.status_code == 200:
                    payment_data = mp_resp.json()
                    current_status = payment_data.get('status')
                    
                    if current_status == 'approved':
                        delivered_key = _deliver_key_to_order(conn, order_id, order['category_code'])
                        if delivered_key:
                            return jsonify({
                                'success': True,
                                'status': 'approved',
                                'delivered_key': delivered_key,
                                'category_code': order['category_code'],
                                'amount': order['amount']
                            })
                        else:
                            return jsonify({
                                'success': True,
                                'status': 'out_of_stock',
                                'message': 'Sem estoque disponível.'
                            })
            except Exception as e:
                logging.error(f"Erro ao verificar pagamento MP: {str(e)}")
                
        return jsonify({
            'success': True,
            'status': order['status'],
            'order_id': order['id']
        })

@app.route('/api/simulate-payment/<order_id>', methods=['POST'])
def simulate_payment(order_id):
    test_mode = get_setting('test_mode', 'false') == 'true'
    mp_token = get_setting('mp_access_token', '').strip()
    
    if not test_mode and bool(mp_token):
        return jsonify({'success': False, 'message': 'Modo teste desativado'}), 403
        
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM orders WHERE id = ?", (order_id,))
        order = cursor.fetchone()
        
        if not order:
            return jsonify({'success': False, 'message': 'Pedido não encontrado'}), 404
            
        if order['status'] == 'approved':
            return jsonify({'success': True, 'status': 'approved', 'delivered_key': order['delivered_key']})
            
        delivered_key = _deliver_key_to_order(conn, order_id, order['category_code'])
        if delivered_key:
            return jsonify({
                'success': True,
                'status': 'approved',
                'delivered_key': delivered_key
            })
        else:
            return jsonify({
                'success': False,
                'status': 'out_of_stock',
                'message': 'Sem estoque disponível.'
            }), 400

def _deliver_key_to_order(conn, order_id, category_code):
    cursor = conn.cursor()
    cursor.execute('''
        SELECT id, key_value FROM keys
        WHERE category_code = ? AND status = 'available'
        ORDER BY id ASC LIMIT 1
    ''', (category_code,))
    available_key = cursor.fetchone()
    
    if not available_key:
        cursor.execute("UPDATE orders SET status = 'out_of_stock', updated_at = CURRENT_TIMESTAMP WHERE id = ?", (order_id,))
        conn.commit()
        return None
        
    key_id = available_key['id']
    key_value = available_key['key_value']
    
    cursor.execute('''
        UPDATE keys
        SET status = 'sold', sold_at = CURRENT_TIMESTAMP, order_id = ?
        WHERE id = ?
    ''', (order_id, key_id))
    
    cursor.execute('''
        UPDATE orders
        SET status = 'approved', delivered_key = ?, updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
    ''', (key_value, order_id))
    
    conn.commit()
    return key_value

# ==========================================================
# ÁREA ADMINISTRATIVA SEGURA
# ==========================================================

login_attempts = {}

@app.route('/painel-gestao-77x')
def admin_page():
    return render_template('admin.html')

@app.route('/admin')
def fake_admin_trap():
    return "Página não encontrada.", 404

@app.route('/api/admin/login', methods=['POST'])
def admin_login():
    import time
    client_ip = request.remote_addr or '127.0.0.1'
    now = time.time()
    
    attempt_info = login_attempts.get(client_ip, {'count': 0, 'locked_until': 0})
    
    if now < attempt_info.get('locked_until', 0):
        remaining = int(attempt_info['locked_until'] - now)
        return jsonify({
            'success': False,
            'message': f'Acesso bloqueado por segurança. Tente em {remaining} segundos.'
        }), 429
        
    data = request.get_json() or {}
    password = data.get('password', '')
    saved_password = get_setting('admin_password', 'Z8#mK9!vP2@wL5$qF7')
    
    if password == saved_password:
        login_attempts.pop(client_ip, None)
        session['is_admin'] = True
        return jsonify({'success': True, 'message': 'Login realizado com sucesso'})
        
    time.sleep(1)
    attempt_info['count'] = attempt_info.get('count', 0) + 1
    
    if attempt_info['count'] >= 5:
        attempt_info['locked_until'] = now + 600
        login_attempts[client_ip] = attempt_info
        return jsonify({
            'success': False,
            'message': 'Limite de 5 tentativas excedido. Bloqueado por 10 minutos.'
        }), 429
        
    login_attempts[client_ip] = attempt_info
    remaining_attempts = 5 - attempt_info['count']
    return jsonify({
        'success': False,
        'message': f'Senha incorreta! ({remaining_attempts} tentativa(s) restante(s)).'
    }), 401

@app.route('/api/admin/logout', methods=['POST'])
def admin_logout():
    session.pop('is_admin', None)
    return jsonify({'success': True})

@app.route('/api/admin/check-auth', methods=['GET'])
def check_admin_auth():
    return jsonify({'authenticated': session.get('is_admin', False)})

@app.route('/api/admin/dashboard-stats', methods=['GET'])
@admin_required
def admin_dashboard_stats():
    with get_db() as conn:
        cursor = conn.cursor()
        
        cursor.execute("SELECT COALESCE(SUM(amount), 0) as total FROM orders WHERE status = 'approved'")
        total_revenue = cursor.fetchone()['total']
        
        cursor.execute("SELECT COUNT(*) as count FROM keys WHERE status = 'sold'")
        total_sold = cursor.fetchone()['count']
        
        cursor.execute('''
            SELECT 
                c.code, c.name, c.price,
                SUM(CASE WHEN k.status = 'available' THEN 1 ELSE 0 END) as available_stock,
                SUM(CASE WHEN k.status = 'sold' THEN 1 ELSE 0 END) as sold_stock
            FROM categories c
            LEFT JOIN keys k ON c.code = k.category_code
            GROUP BY c.code
            ORDER BY c.code ASC
        ''')
        stock_by_cat = [dict(row) for row in cursor.fetchall()]
        
        cursor.execute('''
            SELECT o.id, o.category_code, o.amount, o.status, o.delivered_key, o.created_at, o.mp_payment_id
            FROM orders o
            ORDER BY o.created_at DESC LIMIT 15
        ''')
        recent_orders = [dict(row) for row in cursor.fetchall()]
        
        return jsonify({
            'success': True,
            'total_revenue': total_revenue,
            'total_sold': total_sold,
            'stock_by_category': stock_by_cat,
            'recent_orders': recent_orders,
            'mp_configured': bool(get_setting('mp_access_token', '').strip()),
            'test_mode': get_setting('test_mode', 'false') == 'true'
        })

@app.route('/api/admin/keys', methods=['GET'])
@admin_required
def admin_get_keys():
    category = request.args.get('category', '').upper()
    status = request.args.get('status', '')
    
    with get_db() as conn:
        cursor = conn.cursor()
        query = "SELECT id, category_code, key_value, status, created_at, sold_at, order_id FROM keys WHERE 1=1"
        params = []
        
        if category in ['G', 'X', 'F']:
            query += " AND category_code = ?"
            params.append(category)
            
        if status in ['available', 'sold']:
            query += " AND status = ?"
            params.append(status)
            
        query += " ORDER BY id DESC LIMIT 200"
        cursor.execute(query, params)
        keys = [dict(row) for row in cursor.fetchall()]
        
        return jsonify({'success': True, 'keys': keys})

@app.route('/api/admin/keys/add', methods=['POST'])
@admin_required
def admin_add_keys():
    data = request.get_json() or {}
    category_code = data.get('category_code', '').upper()
    raw_keys = data.get('keys_text', '')
    
    if category_code not in ['G', 'X', 'F']:
        return jsonify({'success': False, 'message': 'Categoria inválida. Selecione GOOGLE, X ou FACE.'}), 400
        
    lines = [line.strip() for line in raw_keys.splitlines() if line.strip()]
    
    if not lines:
        return jsonify({'success': False, 'message': 'Nenhum item informado.'}), 400
        
    added_count = 0
    duplicates_count = 0
    
    with get_db() as conn:
        cursor = conn.cursor()
        for key_str in lines:
            cursor.execute("SELECT id FROM keys WHERE key_value = ?", (key_str,))
            if cursor.fetchone():
                duplicates_count += 1
                continue
                
            cursor.execute('''
                INSERT INTO keys (category_code, key_value, status)
                VALUES (?, ?, 'available')
            ''', (category_code, key_str))
            added_count += 1
            
        conn.commit()
        
    names_map = {'G': 'GOOGLE', 'X': 'X', 'F': 'FACE'}
    cat_label = names_map.get(category_code, category_code)
    msg = f"{added_count} itens adicionados com sucesso a {cat_label}!"
    if duplicates_count > 0:
        msg += f" ({duplicates_count} duplicados ignorados)."
        
    return jsonify({
        'success': True,
        'message': msg,
        'added_count': added_count,
        'duplicates_count': duplicates_count
    })

@app.route('/api/admin/keys/<int:key_id>', methods=['DELETE'])
@admin_required
def admin_delete_key(key_id):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM keys WHERE id = ? AND status = 'available'", (key_id,))
        deleted = cursor.rowcount
        conn.commit()
        
    if deleted:
        return jsonify({'success': True, 'message': 'Item removido com sucesso.'})
    return jsonify({'success': False, 'message': 'Item não encontrado ou já vendido'}), 400

@app.route('/api/admin/settings', methods=['GET', 'POST'])
@admin_required
def admin_settings():
    if request.method == 'GET':
        return jsonify({
            'success': True,
            'mp_access_token': get_setting('mp_access_token', ''),
            'test_mode': get_setting('test_mode', 'false') == 'true',
            'store_name': get_setting('store_name', 'DIGITAL STORE')
        })
        
    data = request.get_json() or {}
    if 'mp_access_token' in data:
        set_setting('mp_access_token', data['mp_access_token'].strip())
        
    if 'test_mode' in data:
        set_setting('test_mode', 'true' if data['test_mode'] else 'false')
        
    if 'store_name' in data:
        set_setting('store_name', data['store_name'].strip() or 'DIGITAL STORE')
        
    if 'new_password' in data and data['new_password'].strip():
        set_setting('admin_password', data['new_password'].strip())
        
    return jsonify({'success': True, 'message': 'Configurações salvas com sucesso!'})

@app.route('/api/admin/test-mercadopago', methods=['POST'])
@admin_required
def test_mercadopago_connection():
    data = request.get_json() or {}
    token = data.get('token', '').strip() or get_setting('mp_access_token', '').strip()
    
    if not token:
        return jsonify({'success': False, 'message': 'Informe um Access Token'}), 400
        
    try:
        headers = {"Authorization": f"Bearer {token}"}
        resp = requests.get("https://api.mercadopago.com/users/me", headers=headers, timeout=8)
        if resp.status_code == 200:
            user_data = resp.json()
            email = user_data.get('email', 'Email não informado')
            nickname = user_data.get('nickname', 'Vendedor')
            return jsonify({
                'success': True,
                'message': f'Conexão bem sucedida! Vendedor: {nickname} ({email})'
            })
        else:
            return jsonify({'success': False, 'message': f'Token inválido: HTTP {resp.status_code}'}), 400
    except Exception as e:
        return jsonify({'success': False, 'message': f'Erro ao conectar: {str(e)}'}), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    print("=" * 60)
    print(f"🚀 SISTEMA INICIADO COM SUCESSO!")
    print(f"🛒 Vitrine da Loja: http://127.0.0.1:{port}")
    print(f"🔐 Painel Secreto: http://127.0.0.1:{port}/painel-gestao-77x")
    print(f"🔑 Senha Segura: Z8#mK9!vP2@wL5$qF7")
    print("=" * 60)
    app.run(host='0.0.0.0', port=port, debug=False)
