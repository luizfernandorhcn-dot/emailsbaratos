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

# Procura templates TANTO na pasta templates/ QUANTO soltos na pasta raiz do GitHub
template_dirs = [
    os.path.join(BASE_DIR, 'templates'),
    BASE_DIR
]
app.jinja_loader = jinja2.FileSystemLoader(template_dirs)

# Fallback para arquivos estáticos (CSS/JS) caso tenham sido enviados soltos
@app.route('/static/<path:filename>')
def serve_custom_static(filename):
    static_folder = os.path.join(BASE_DIR, 'static')
    if os.path.exists(os.path.join(static_folder, filename)):
        return send_from_directory(static_folder, filename)
    if os.path.exists(os.path.join(BASE_DIR, filename)):
        return send_from_directory(BASE_DIR, filename)
    base_name = os.path.basename(filename)
    if os.path.exists(os.path.join(BASE_DIR, base_name)):
        return send_from_directory(BASE_DIR, base_name)
    return "Arquivo não encontrado", 404

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
        
        # Categorias de Keys
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS categories (
                code TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                price REAL NOT NULL,
                badge TEXT,
                description TEXT
            )
        ''')
        
        # Estoque de Keys
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
        
        # Configurações do sistema com o seu Access Token Oficial e Senha Forte
        MP_ACCESS_TOKEN = 'APP_USR-5018438626901279-100420-f423d886185a97e1962841e55156ec32-3386945777'
        SECURE_PASSWORD = 'Z8#mK9!vP2@wL5$qF7'
        cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('admin_password', ?)", (SECURE_PASSWORD,))
        cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('mp_access_token', ?)", (MP_ACCESS_TOKEN,))
        cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('test_mode', 'false')")
        cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('store_name', 'KEYSTORE PRO')")
        
        # Inserir ou atualizar as 3 categorias solicitadas: GOOGLE, X, FACE
        cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('store_name', 'DIGITAL STORE')")
        
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

@app.errorhandler(Exception)
def handle_exception(e):
    import traceback
    trace = traceback.format_exc()
    logging.error(f"Erro 500 no Servidor: {trace}")
    return f"""
    <div style="font-family: monospace; padding: 25px; background: #0f172a; color: #f87171; border: 1px solid #ef4444; border-radius: 12px; margin: 30px auto; max-width: 800px;">
        <h3 style="color: #ef4444; margin-top: 0;">⚠️ Detalhes do Erro no Servidor:</h3>
        <p style="color: #94a3b8; font-size: 13px;">Copie a mensagem abaixo para identificar o problema:</p>
        <pre style="background: #020617; padding: 15px; border-radius: 8px; color: #f1f5f9; overflow-x: auto; font-size: 12px; white-space: pre-wrap;">{trace}</pre>
    </div>
    """, 500

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
        store_name = get_setting('store_name', 'KEYSTORE PRO')
        
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
        return jsonify({'success': False, 'message': 'Categoria inválida. Escolha KEYS G, KEYS X ou KEYS F'}), 400
        
    with get_db() as conn:
        cursor = conn.cursor()
        
        # Verificar estoque disponível
        cursor.execute('''
            SELECT COUNT(*) as count FROM keys
            WHERE category_code = ? AND status = 'available'
        ''', (category_code,))
        stock_count = cursor.fetchone()['count']
        
        if stock_count <= 0:
            return jsonify({'success': False, 'message': f'Desculpe, as {category_code} estão esgotadas no momento.'}), 400

        cursor.execute("SELECT * FROM categories WHERE code = ?", (category_code,))
        category = cursor.fetchone()
        price = category['price'] if category else 3.50

        order_id = f"PED_{datetime.now().strftime('%Y%m%d%H%M%S')}_{uuid.uuid4().hex[:6]}"
        
        mp_token = get_setting('mp_access_token', '').strip()
        test_mode = get_setting('test_mode', 'false') == 'true'
        
        qr_code = ""
        qr_code_base64 = ""
        mp_payment_id = ""
        
        # Se houver token do Mercado Pago, gerar PIX real
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
            # Sem token configurado
            if not test_mode:
                return jsonify({
                    'success': False,
                    'message': 'Nenhum Access Token configurado. Configure no painel /admin.'
                }), 400
                    
        # Caso esteja em modo teste sem token do MP
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
            
        # Se já aprovado, retorna a key entregue
        if order['status'] == 'approved':
            return jsonify({
                'success': True,
                'status': 'approved',
                'delivered_key': order['delivered_key'],
                'category_code': order['category_code'],
                'amount': order['amount']
            })
            
        # Se pendente e temos pagamento no Mercado Pago real, consulta o status no MP
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
                        # Atribuir Key e finalizar pedido
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
                                'message': 'Pagamento recebido, mas o estoque esgotou no momento da confirmação. Entre em contato com o suporte.'
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
    """Permite testar a aprovação e entrega de key sem gastar dinheiro real (Modo Teste)"""
    test_mode = get_setting('test_mode', 'false') == 'true'
    mp_token = get_setting('mp_access_token', '').strip()
    
    # Permitir se estiver em modo teste ou se ainda não tiver configurado MP
    if not test_mode and bool(mp_token):
        return jsonify({'success': False, 'message': 'Modo de teste desativado nas configurações'}), 403
        
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
                'message': 'Sem estoque disponível para esta categoria.'
            }), 400

def _deliver_key_to_order(conn, order_id, category_code):
    cursor = conn.cursor()
    # Buscar primeira key disponível
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
    
    # Marcar key como vendida
    cursor.execute('''
        UPDATE keys
        SET status = 'sold', sold_at = CURRENT_TIMESTAMP, order_id = ?
        WHERE id = ?
    ''', (order_id, key_id))
    
    # Atualizar pedido como aprovado
    cursor.execute('''
        UPDATE orders
        SET status = 'approved', delivered_key = ?, updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
    ''', (key_value, order_id))
    
    conn.commit()
    return key_value

# Webhook para Mercado Pago (notificação instantânea)
@app.route('/api/webhook/mercadopago', methods=['POST'])
def mp_webhook():
    topic = request.args.get('topic') or request.args.get('type')
    payment_id = request.args.get('id') or request.args.get('data.id')
    
    if not payment_id and request.is_json:
        data = request.get_json()
        payment_id = data.get('data', {}).get('id') or data.get('id')
        
    if payment_id:
        mp_token = get_setting('mp_access_token', '').strip()
        if mp_token:
            try:
                headers = {"Authorization": f"Bearer {mp_token}"}
                mp_resp = requests.get(
                    f"https://api.mercadopago.com/v1/payments/{payment_id}",
                    headers=headers,
                    timeout=10
                )
                if mp_resp.status_code == 200:
                    payment = mp_resp.json()
                    if payment.get('status') == 'approved':
                        with get_db() as conn:
                            cursor = conn.cursor()
                            cursor.execute("SELECT id, category_code, status FROM orders WHERE mp_payment_id = ?", (str(payment_id),))
                            order = cursor.fetchone()
                            if order and order['status'] != 'approved':
                                _deliver_key_to_order(conn, order['id'], order['category_code'])
            except Exception as e:
                logging.error(f"Erro webhook MP: {e}")
                
    return jsonify({"status": "ok"}), 200

# ==========================================================
# ÁREA ADMINISTRATIVA SEGURA
# ==========================================================

login_attempts = {}

@app.route('/painel-gestao-77x')
def admin_page():
    return render_template('admin.html')

@app.route('/admin')
def fake_admin_trap():
    """Retorna 404 intencional para despistar bots e invasores"""
    return "Página não encontrada.", 404

@app.route('/api/admin/login', methods=['POST'])
def admin_login():
    import time
    client_ip = request.remote_addr or '127.0.0.1'
    now = time.time()
    
    attempt_info = login_attempts.get(client_ip, {'count': 0, 'locked_until': 0})
    
    # Se estiver bloqueado temporariamente
    if now < attempt_info.get('locked_until', 0):
        remaining = int(attempt_info['locked_until'] - now)
        return jsonify({
            'success': False,
            'message': f'Muitas tentativas incorretas. Acesso bloqueado por segurança por mais {remaining} segundos.'
        }), 429
        
    data = request.get_json() or {}
    password = data.get('password', '')
    saved_password = get_setting('admin_password', 'Z8#mK9!vP2@wL5$qF7')
    
    if password == saved_password:
        login_attempts.pop(client_ip, None)
        session['is_admin'] = True
        return jsonify({'success': True, 'message': 'Login realizado com sucesso'})
        
    # Falha de login - proteção contra força bruta
    time.sleep(1) # Delay de 1 segundo para impedir ataques automatizados
    attempt_info['count'] = attempt_info.get('count', 0) + 1
    
    if attempt_info['count'] >= 5:
        attempt_info['locked_until'] = now + 600 # Bloqueia por 10 minutos
        login_attempts[client_ip] = attempt_info
        return jsonify({
            'success': False,
            'message': 'Limite de 5 tentativas incorretas excedido! Painel bloqueado por 10 minutos.'
        }), 429
        
    login_attempts[client_ip] = attempt_info
    remaining_attempts = 5 - attempt_info['count']
    return jsonify({
        'success': False,
        'message': f'Senha incorreta! ({remaining_attempts} tentativa(s) restante(s) antes do bloqueio).'
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
        
        # Total Faturamento
        cursor.execute("SELECT COALESCE(SUM(amount), 0) as total FROM orders WHERE status = 'approved'")
        total_revenue = cursor.fetchone()['total']
        
        # Total Keys Vendidas
        cursor.execute("SELECT COUNT(*) as count FROM keys WHERE status = 'sold'")
        total_sold = cursor.fetchone()['count']
        
        # Estoque por categoria
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
        
        # Vendas recentes
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
        return jsonify({'success': False, 'message': 'Categoria inválida. Selecione KEYS G, KEYS X ou KEYS F.'}), 400
        
    lines = [line.strip() for line in raw_keys.splitlines() if line.strip()]
    
    if not lines:
        return jsonify({'success': False, 'message': 'Nenhuma key foi informada. Insira ao menos uma key no formulário.'}), 400
        
    added_count = 0
    duplicates_count = 0
    
    with get_db() as conn:
        cursor = conn.cursor()
        for key_str in lines:
            # Checar se já existe no banco
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
    msg = f"{added_count} itens adicionados com sucesso à categoria {cat_label}!"
    if duplicates_count > 0:
        msg += f" ({duplicates_count} ignorados por já existirem no sistema)."
        
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
        return jsonify({'success': True, 'message': 'Key removida com sucesso.'})
    return jsonify({'success': False, 'message': 'Key não encontrada ou já foi vendida'}), 400

@app.route('/api/admin/keys/clear', methods=['POST'])
@admin_required
def admin_clear_category_stock():
    data = request.get_json() or {}
    category_code = data.get('category_code', '').upper()
    
    if category_code not in ['G', 'X', 'F']:
        return jsonify({'success': False, 'message': 'Categoria inválida'}), 400
        
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM keys WHERE category_code = ? AND status = 'available'", (category_code,))
        count = cursor.rowcount
        conn.commit()
        
    return jsonify({'success': True, 'message': f'{count} keys disponíveis da categoria KEYS {category_code} foram removidas.'})

@app.route('/api/admin/settings', methods=['GET', 'POST'])
@admin_required
def admin_settings():
    if request.method == 'GET':
        return jsonify({
            'success': True,
            'mp_access_token': get_setting('mp_access_token', ''),
            'test_mode': get_setting('test_mode', 'false') == 'true',
            'store_name': get_setting('store_name', 'KEYSTORE PRO')
        })
        
    data = request.get_json() or {}
    if 'mp_access_token' in data:
        set_setting('mp_access_token', data['mp_access_token'].strip())
        
    if 'test_mode' in data:
        set_setting('test_mode', 'true' if data['test_mode'] else 'false')
        
    if 'store_name' in data:
        set_setting('store_name', data['store_name'].strip() or 'KEYSTORE PRO')
        
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
        # Testa endpoint de consulta de usuários do MP
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
            return jsonify({
                'success': False,
                'message': f'Token inválido ou não autorizado: HTTP {resp.status_code}'
            }), 400
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
