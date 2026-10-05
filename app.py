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
# TEMPLATES 100% COMPLETOS EMBUTIDOS (AUTO-SUFICIENTES)
# ==========================================================

FULL_INDEX_HTML = """<!DOCTYPE html>
<html lang="pt-BR" class="dark">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>DIGITAL STORE | Entrega Automática via PIX</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.1/css/all.min.css">
    <script src="https://cdn.jsdelivr.net/npm/canvas-confetti@1.6.0/dist/confetti.browser.min.js"></script>
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800;900&family=JetBrains+Mono:wght@400;600;700&display=swap');
        body { font-family: 'Plus Jakarta Sans', sans-serif; background-color: #090d16; color: #f1f5f9; }
        code, pre, .font-mono { font-family: 'JetBrains Mono', monospace; }
        ::-webkit-scrollbar { width: 6px; }
        ::-webkit-scrollbar-thumb { background: #1e293b; border-radius: 9999px; }
    </style>
</head>
<body class="bg-[#090d16] text-slate-100 min-h-screen flex flex-col font-sans selection:bg-emerald-500 selection:text-white antialiased">
    <!-- Header -->
    <header class="border-b border-slate-800/60 bg-[#090d16]/80 backdrop-blur-md sticky top-0 z-30">
        <div class="max-w-6xl mx-auto px-4 sm:px-6 h-18 flex items-center justify-between py-4">
            <div class="flex items-center gap-3">
                <div class="w-10 h-10 rounded-xl bg-slate-800/80 border border-slate-700/60 flex items-center justify-center text-emerald-400 text-lg">
                    <i class="fa-solid fa-cube"></i>
                </div>
                <div>
                    <span id="store-title" class="font-extrabold text-lg tracking-tight text-white block">DIGITAL STORE</span>
                    <span class="text-[11px] text-emerald-400 font-medium flex items-center gap-1.5 -mt-0.5">
                        <span class="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse"></span>
                        Entrega Automática 24h
                    </span>
                </div>
            </div>

            <div class="flex items-center gap-3">
                <div class="hidden sm:flex items-center gap-2 px-3 py-1.5 rounded-full bg-slate-900/90 border border-slate-800 text-xs text-slate-400">
                    <i class="fa-brands fa-pix text-emerald-400 text-sm"></i>
                    <span>PIX Instantâneo</span>
                </div>
                <a href="https://wa.me/5582991738022?text=Olá!%20Preciso%20de%20suporte%20na%20loja." target="_blank" class="flex items-center gap-2 px-3.5 py-1.5 rounded-xl bg-emerald-500/10 hover:bg-emerald-500/20 text-emerald-400 border border-emerald-500/30 text-xs font-bold transition">
                    <i class="fa-brands fa-whatsapp text-sm"></i>
                    <span>Suporte</span>
                </a>
            </div>
        </div>
    </header>

    <!-- Main -->
    <main class="flex-1 max-w-6xl mx-auto px-4 sm:px-6 py-12 sm:py-16 w-full flex flex-col justify-center">
        <div class="text-center max-w-2xl mx-auto mb-12 sm:mb-16">
            <div class="inline-flex items-center gap-2 px-3.5 py-1 rounded-full bg-slate-800/80 border border-slate-700/80 text-emerald-400 text-xs font-semibold mb-4">
                <i class="fa-brands fa-pix"></i>
                <span>Pagamento via PIX • Liberação Imediata</span>
            </div>
            <h1 class="text-3xl sm:text-5xl font-black text-white tracking-tight mb-4">Selecione o seu produto</h1>
            <p class="text-slate-400 text-sm sm:text-base leading-relaxed">
                Preço fixo de <span class="text-emerald-400 font-bold">R$ 3,50</span> cada. O produto é entregue diretamente na sua tela na mesma hora após o pagamento.
            </p>
        </div>

        <!-- Cards -->
        <div id="categories-grid" class="grid grid-cols-1 md:grid-cols-3 gap-6 max-w-5xl mx-auto w-full">
            <div class="animate-pulse bg-slate-900/40 rounded-2xl border border-slate-800/80 p-8 h-80"></div>
            <div class="animate-pulse bg-slate-900/40 rounded-2xl border border-slate-800/80 p-8 h-80"></div>
            <div class="animate-pulse bg-slate-900/40 rounded-2xl border border-slate-800/80 p-8 h-80"></div>
        </div>

        <!-- How it works -->
        <div class="mt-20 pt-10 border-t border-slate-800/60 max-w-4xl mx-auto w-full">
            <div class="grid grid-cols-1 sm:grid-cols-3 gap-6 text-center">
                <div class="p-4">
                    <div class="w-10 h-10 rounded-xl bg-slate-800/60 border border-slate-700/50 flex items-center justify-center text-slate-300 font-bold mx-auto mb-3 text-sm">1</div>
                    <h4 class="text-sm font-bold text-white mb-1">Escolha a opção</h4>
                    <p class="text-xs text-slate-400">Escolha entre GOOGLE, X ou FACE pelo valor de R$ 3,50.</p>
                </div>
                <div class="p-4">
                    <div class="w-10 h-10 rounded-xl bg-slate-800/60 border border-slate-700/50 flex items-center justify-center text-emerald-400 font-bold mx-auto mb-3 text-sm">2</div>
                    <h4 class="text-sm font-bold text-white mb-1">Pague via PIX</h4>
                    <p class="text-xs text-slate-400">Escaneie o QR Code ou use o código PIX Copia e Cola pelo seu banco.</p>
                </div>
                <div class="p-4">
                    <div class="w-10 h-10 rounded-xl bg-slate-800/60 border border-slate-700/50 flex items-center justify-center text-blue-400 font-bold mx-auto mb-3 text-sm">3</div>
                    <h4 class="text-sm font-bold text-white mb-1">Receba na Hora</h4>
                    <p class="text-xs text-slate-400">O sistema aprova em segundos e entrega na tela com cópia instantânea.</p>
                </div>
            </div>
        </div>
    </main>

    <!-- Modal Checkout -->
    <div id="checkout-modal" class="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-sm hidden opacity-0 transition-opacity duration-200">
        <div class="relative w-full max-w-md bg-[#0f172a] border border-slate-800 rounded-3xl shadow-2xl p-6 sm:p-7 overflow-hidden">
            <button onclick="closeModal()" class="absolute top-4 right-4 w-8 h-8 rounded-full bg-slate-800/80 text-slate-400 hover:text-white flex items-center justify-center transition">
                <i class="fa-solid fa-xmark text-sm"></i>
            </button>

            <!-- STEP 1 -->
            <div id="step-confirm">
                <div class="flex items-center gap-3 mb-5">
                    <div id="modal-product-icon" class="w-12 h-12 rounded-2xl bg-slate-800 border border-slate-700/60 flex items-center justify-center text-white text-xl">
                        <i class="fa-solid fa-cart-shopping"></i>
                    </div>
                    <div>
                        <h3 class="text-lg font-bold text-white" id="modal-product-title">Comprar</h3>
                        <p class="text-xs text-slate-400">Entrega imediata via PIX</p>
                    </div>
                </div>

                <div class="bg-slate-900/90 rounded-2xl p-4 border border-slate-800/80 mb-5 space-y-2.5">
                    <div class="flex justify-between items-center text-xs">
                        <span class="text-slate-400">Item selecionado:</span>
                        <span class="font-bold text-white text-sm" id="modal-category-name">GOOGLE</span>
                    </div>
                    <div class="flex justify-between items-center text-xs">
                        <span class="text-slate-400">Entrega:</span>
                        <span class="text-emerald-400 font-semibold flex items-center gap-1">
                            <i class="fa-solid fa-bolt text-[10px]"></i> Imediata na tela
                        </span>
                    </div>
                    <div class="pt-2 border-t border-slate-800 flex justify-between items-center">
                        <span class="text-xs font-semibold text-slate-300">Total a pagar:</span>
                        <span class="text-xl font-black text-emerald-400">R$ 3,50</span>
                    </div>
                </div>

                <div class="mb-5 space-y-3">
                    <div>
                        <label class="block text-[11px] font-semibold text-slate-400 uppercase tracking-wider mb-1">Seu E-mail (opcional):</label>
                        <input type="email" id="buyer-email" placeholder="seu@email.com" class="w-full px-3.5 py-2.5 rounded-xl bg-slate-900 border border-slate-700/80 text-white placeholder-slate-500 focus:outline-none focus:border-emerald-500 transition text-xs">
                    </div>
                    <div>
                        <label class="block text-[11px] font-semibold text-slate-400 uppercase tracking-wider mb-1">CPF (opcional):</label>
                        <input type="text" id="buyer-cpf" placeholder="000.000.000-00" maxlength="14" class="w-full px-3.5 py-2.5 rounded-xl bg-slate-900 border border-slate-700/80 text-white placeholder-slate-500 focus:outline-none focus:border-emerald-500 transition text-xs font-mono">
                    </div>
                </div>

                <button id="btn-generate-pix" onclick="processCheckout()" class="w-full py-3.5 rounded-xl bg-emerald-500 hover:bg-emerald-400 text-slate-950 font-bold text-sm flex items-center justify-center gap-2 shadow-lg shadow-emerald-500/20 transition active:scale-[0.99]">
                    <i class="fa-brands fa-pix text-base"></i>
                    <span>Gerar PIX de R$ 3,50</span>
                </button>
            </div>

            <!-- STEP 2 -->
            <div id="step-payment" class="hidden">
                <div class="text-center mb-4">
                    <div class="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-emerald-500/10 text-emerald-400 text-xs font-bold mb-2">
                        <i class="fa-solid fa-spinner fa-spin text-[10px]"></i>
                        Aguardando Pagamento
                    </div>
                    <h3 class="text-lg font-bold text-white">Escaneie o QR Code</h3>
                    <p class="text-xs text-slate-400">Valor exato: <strong class="text-emerald-400">R$ 3,50</strong></p>
                </div>

                <div class="bg-white p-3.5 rounded-2xl w-56 h-56 mx-auto mb-4 shadow-xl flex items-center justify-center border-2 border-slate-700 relative overflow-hidden">
                    <img id="pix-qr-img" src="" alt="QR Code PIX" class="w-full h-full object-contain">
                    <div id="qr-loading-spinner" class="absolute inset-0 bg-white flex items-center justify-center">
                        <i class="fa-solid fa-circle-notch fa-spin text-2xl text-emerald-600"></i>
                    </div>
                </div>

                <div class="mb-4">
                    <label class="block text-[11px] font-semibold text-slate-400 uppercase tracking-wider mb-1.5 flex justify-between">
                        <span>Código PIX Copia e Cola:</span>
                        <span id="copy-feedback" class="text-emerald-400 font-bold hidden">Copiado!</span>
                    </label>
                    <div class="flex gap-2">
                        <input type="text" id="pix-code-input" readonly class="w-full px-3 py-2 rounded-xl bg-slate-900 border border-slate-700 text-xs text-slate-300 font-mono focus:outline-none select-all truncate">
                        <button onclick="copyPixCode()" class="px-3.5 py-2 rounded-xl bg-indigo-600 hover:bg-indigo-500 text-white font-semibold text-xs flex items-center gap-1.5 transition shrink-0">
                            <i class="fa-solid fa-copy"></i>
                            <span>Copiar</span>
                        </button>
                    </div>
                </div>

                <div class="flex items-center justify-center gap-2 text-xs text-slate-400 bg-slate-900/60 py-2 rounded-xl border border-slate-800 mb-3">
                    <span class="w-2 h-2 rounded-full bg-emerald-500 animate-pulse"></span>
                    <span>Identificando pagamento em tempo real...</span>
                </div>

                <div class="text-center mb-2">
                    <a href="https://wa.me/5582991738022?text=Olá!%20Preciso%20de%20ajuda%20com%20meu%20pagamento%20PIX." target="_blank" class="text-[11px] text-emerald-400 hover:text-emerald-300 font-medium inline-flex items-center gap-1.5 transition">
                        <i class="fa-brands fa-whatsapp text-sm"></i>
                        <span>Dúvidas ou problemas? Falar no WhatsApp</span>
                    </a>
                </div>

                <div id="simulation-box" class="hidden pt-2 border-t border-slate-800 text-center"></div>
            </div>

            <!-- STEP 3 -->
            <div id="step-success" class="hidden text-center py-2">
                <div class="w-14 h-14 rounded-full bg-emerald-500/20 border border-emerald-500 flex items-center justify-center text-emerald-400 text-2xl mx-auto mb-3 animate-bounce">
                    <i class="fa-solid fa-check"></i>
                </div>
                <h3 class="text-xl font-black text-white mb-1">Pagamento Aprovado!</h3>
                <p class="text-xs text-slate-400 mb-5">Aqui está o seu item exclusivo:</p>

                <div class="bg-slate-900/90 border border-emerald-500/40 rounded-2xl p-4 mb-5">
                    <div class="text-[11px] uppercase tracking-wider text-emerald-400 font-bold mb-1 flex items-center justify-center gap-1.5">
                        <i class="fa-solid fa-box-open"></i>
                        Seu Acesso
                    </div>
                    <div id="delivered-key-text" class="text-base sm:text-lg font-mono font-bold text-white tracking-wider select-all break-all py-2">
                        CARREGANDO...
                    </div>
                    <div class="mt-2 flex justify-center gap-2">
                        <button onclick="copyDeliveredKey()" class="px-3.5 py-1.5 rounded-xl bg-emerald-500 hover:bg-emerald-400 text-slate-950 font-bold text-xs flex items-center gap-1.5 transition">
                            <i class="fa-solid fa-copy"></i>
                            <span id="copy-key-btn-text">Copiar</span>
                        </button>
                        <button onclick="downloadKeyTxt()" class="px-3.5 py-1.5 rounded-xl bg-slate-800 hover:bg-slate-700 text-white font-medium text-xs flex items-center gap-1.5 transition">
                            <i class="fa-solid fa-download"></i>
                            <span>Salvar .txt</span>
                        </button>
                    </div>
                </div>

                <button onclick="closeModal(); loadStore();" class="w-full py-3 rounded-xl bg-slate-800 hover:bg-slate-700 text-white font-semibold text-xs transition">
                    Fechar e Voltar à Loja
                </button>
            </div>
        </div>
    </div>

    <!-- Floating WhatsApp -->
    <a href="https://wa.me/5582991738022?text=Olá!%20Vim%20pelo%20site%20e%20preciso%20de%20suporte." target="_blank" class="fixed bottom-6 right-6 z-40 flex items-center gap-2.5 px-4 py-3 bg-[#25D366] hover:bg-[#20ba5a] text-white font-bold text-xs rounded-full shadow-xl shadow-emerald-950/40 transition-all duration-300 hover:scale-105 active:scale-95">
        <i class="fa-brands fa-whatsapp text-lg"></i>
        <span>Suporte WhatsApp</span>
    </a>

    <!-- Footer -->
    <footer class="border-t border-slate-800/60 bg-[#090d16] py-6 text-center text-xs text-slate-500">
        <div class="max-w-6xl mx-auto px-4 flex flex-col sm:flex-row items-center justify-between gap-3">
            <p>© 2026 DIGITAL STORE. Pagamentos via Mercado Pago.</p>
            <div class="flex items-center gap-3 text-slate-400 text-[11px]">
                <a href="https://wa.me/5582991738022?text=Olá!%20Preciso%20de%20suporte." target="_blank" class="hover:text-emerald-400 transition flex items-center gap-1">
                    <i class="fa-brands fa-whatsapp text-emerald-400"></i>
                    <span>Suporte: (82) 99173-8022</span>
                </a>
            </div>
        </div>
    </footer>

    <!-- Logic Script Inline -->
    <script>
        let currentCategory = null;
        let currentOrderId = null;
        let pollingInterval = null;
        let currentDeliveredKey = "";

        document.addEventListener('DOMContentLoaded', () => { loadStore(); });

        async function loadStore() {
            try {
                const resp = await fetch('/api/store-info');
                const data = await resp.json();
                if (!data.success) return;
                if (data.store_name) document.getElementById('store-title').textContent = data.store_name;
                renderCards(data.categories);
            } catch (err) { console.error(err); }
        }

        function renderCards(categories) {
            const grid = document.getElementById('categories-grid');
            grid.innerHTML = '';
            categories.forEach(cat => {
                const isAvailable = cat.stock > 0;
                let brandIcon = 'fa-solid fa-cube text-emerald-400';
                let brandClass = 'bg-emerald-500/10 border-emerald-500/20';

                if (cat.code === 'G') {
                    brandIcon = 'fa-brands fa-google text-red-400';
                    brandClass = 'bg-red-500/10 border-red-500/20';
                } else if (cat.code === 'X') {
                    brandIcon = 'fa-brands fa-x-twitter text-white';
                    brandClass = 'bg-white/10 border-white/20';
                } else if (cat.code === 'F') {
                    brandIcon = 'fa-brands fa-facebook-f text-blue-400';
                    brandClass = 'bg-blue-500/10 border-blue-500/20';
                }

                const card = document.createElement('div');
                card.className = 'relative bg-[#0f172a] border border-slate-800/90 rounded-2xl p-6 sm:p-7 flex flex-col justify-between transition-all duration-300 hover:border-slate-700 shadow-lg hover:shadow-xl hover:-translate-y-1';
                card.innerHTML = `
                    <div>
                        <div class="flex items-center justify-between mb-6">
                            <div class="w-12 h-12 rounded-2xl ${brandClass} border flex items-center justify-center text-xl shadow-sm">
                                <i class="${brandIcon}"></i>
                            </div>
                            <span class="px-2.5 py-0.5 rounded-full text-[10px] font-bold uppercase tracking-wider bg-slate-800/80 text-slate-300 border border-slate-700/60">
                                ${cat.badge || 'Disponível'}
                            </span>
                        </div>
                        <h3 class="text-2xl font-black text-white tracking-tight mb-1.5">${cat.name}</h3>
                        <p class="text-xs text-slate-400 leading-relaxed mb-6">${cat.description || 'Entrega imediata na tela após confirmação do PIX.'}</p>
                    </div>
                    <div>
                        <div class="pt-4 border-t border-slate-800/80 mb-5 flex items-baseline justify-between">
                            <div>
                                <span class="text-[11px] text-slate-400 block font-medium">Preço</span>
                                <div class="flex items-baseline gap-1">
                                    <span class="text-xs text-slate-400 font-bold">R$</span>
                                    <span class="text-2xl font-black text-white">3,50</span>
                                </div>
                            </div>
                            <div class="text-right">
                                <span class="text-[11px] text-slate-400 block font-medium">Estoque</span>
                                ${isAvailable ? `
                                    <span class="text-xs font-bold text-emerald-400 flex items-center gap-1.5 justify-end">
                                        <span class="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse"></span>
                                        ${cat.stock} disp.
                                    </span>
                                ` : `
                                    <span class="text-xs font-bold text-rose-400 flex items-center gap-1.5 justify-end">
                                        <span class="w-1.5 h-1.5 rounded-full bg-rose-500"></span>
                                        Esgotado
                                    </span>
                                `}
                            </div>
                        </div>
                        <button onclick="openBuyModal('${cat.code}', '${cat.name}')" ${!isAvailable ? 'disabled' : ''} class="w-full py-3.5 rounded-xl font-bold text-xs transition flex items-center justify-center gap-2 ${isAvailable ? 'bg-emerald-500 hover:bg-emerald-400 text-slate-950 shadow-md shadow-emerald-500/10 active:scale-[0.98]' : 'bg-slate-800 text-slate-500 cursor-not-allowed border border-slate-700/50 shadow-none'}">
                            <i class="fa-brands fa-pix text-sm"></i>
                            <span>${isAvailable ? 'Comprar por R$ 3,50' : 'Sem Estoque'}</span>
                        </button>
                    </div>
                `;
                grid.appendChild(card);
            });
        }

        function openBuyModal(code, name) {
            currentCategory = code;
            currentOrderId = null;
            if (pollingInterval) clearInterval(pollingInterval);
            document.getElementById('modal-category-name').textContent = name;
            document.getElementById('modal-product-title').textContent = `Comprar ${name}`;

            const iconContainer = document.getElementById('modal-product-icon');
            if (code === 'G') iconContainer.innerHTML = '<i class="fa-brands fa-google text-red-400"></i>';
            else if (code === 'X') iconContainer.innerHTML = '<i class="fa-brands fa-x-twitter text-white"></i>';
            else if (code === 'F') iconContainer.innerHTML = '<i class="fa-brands fa-facebook-f text-blue-400"></i>';
            else iconContainer.innerHTML = '<i class="fa-solid fa-cube text-emerald-400"></i>';

            document.getElementById('step-confirm').classList.remove('hidden');
            document.getElementById('step-payment').classList.add('hidden');
            document.getElementById('step-success').classList.add('hidden');

            const modal = document.getElementById('checkout-modal');
            modal.classList.remove('hidden');
            setTimeout(() => modal.classList.remove('opacity-0'), 10);
        }

        function closeModal() {
            if (pollingInterval) clearInterval(pollingInterval);
            const modal = document.getElementById('checkout-modal');
            modal.classList.add('opacity-0');
            setTimeout(() => modal.classList.add('hidden'), 200);
        }

        async function processCheckout() {
            const btn = document.getElementById('btn-generate-pix');
            const originalText = btn.innerHTML;
            btn.disabled = true;
            btn.innerHTML = '<i class="fa-solid fa-circle-notch fa-spin"></i> Gerando PIX...';

            const email = document.getElementById('buyer-email').value.trim();
            const cpf = document.getElementById('buyer-cpf') ? document.getElementById('buyer-cpf').value.trim() : '';

            try {
                const resp = await fetch('/api/create-order', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ category_code: currentCategory, payer_email: email, payer_cpf: cpf })
                });
                const data = await resp.json();
                if (!data.success) {
                    alert(data.message || 'Erro ao criar pedido.');
                    btn.disabled = false;
                    btn.innerHTML = originalText;
                    return;
                }
                currentOrderId = data.order_id;
                document.getElementById('step-confirm').classList.add('hidden');
                document.getElementById('step-payment').classList.remove('hidden');

                const qrImg = document.getElementById('pix-qr-img');
                const spinner = document.getElementById('qr-loading-spinner');
                spinner.classList.remove('hidden');

                if (data.qr_code_base64) {
                    qrImg.src = 'data:image/png;base64,' + data.qr_code_base64;
                    qrImg.onload = () => spinner.classList.add('hidden');
                } else if (data.qr_code) {
                    qrImg.src = 'https://api.qrserver.com/v1/create-qr-code/?size=220x220&margin=8&data=' + encodeURIComponent(data.qr_code);
                    qrImg.onload = () => spinner.classList.add('hidden');
                }
                document.getElementById('pix-code-input').value = data.qr_code;

                const simBox = document.getElementById('simulation-box');
                if (data.is_mock) {
                    simBox.innerHTML = `
                        <div class="p-2.5 bg-amber-500/20 border border-amber-500/30 rounded-xl text-amber-300 text-[11px] mb-2 text-left">
                            <p class="font-bold"><i class="fa-solid fa-triangle-exclamation mr-1"></i> Modo Demonstração:</p>
                            <p class="mt-0.5">Clique abaixo para simular e testar a entrega imediata:</p>
                        </div>
                        <button onclick="simulateOrderApproval()" class="w-full py-2.5 px-3 rounded-xl bg-amber-500 hover:bg-amber-400 text-slate-950 text-xs font-bold transition">
                            Simular Pagamento e Receber
                        </button>
                    `;
                    simBox.classList.remove('hidden');
                } else if (data.test_mode) {
                    simBox.innerHTML = '<button onclick="simulateOrderApproval()" class="w-full py-2 px-3 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-300 text-xs transition">Simular Pagamento para Teste</button>';
                    simBox.classList.remove('hidden');
                } else {
                    simBox.classList.add('hidden');
                }

                startPolling(data.order_id);
            } catch (err) {
                alert('Erro: ' + err.message);
            } finally {
                btn.disabled = false;
                btn.innerHTML = originalText;
            }
        }

        function startPolling(orderId) {
            if (pollingInterval) clearInterval(pollingInterval);
            pollingInterval = setInterval(async () => {
                try {
                    const resp = await fetch('/api/order-status/' + orderId);
                    const data = await resp.json();
                    if (data.success && data.status === 'approved') {
                        clearInterval(pollingInterval);
                        showSuccessScreen(data.delivered_key);
                    }
                } catch (e) {}
            }, 2500);
        }

        function showSuccessScreen(content) {
            currentDeliveredKey = content;
            document.getElementById('step-payment').classList.add('hidden');
            document.getElementById('step-success').classList.remove('hidden');
            document.getElementById('delivered-key-text').textContent = content;
            if (typeof confetti === 'function') confetti({ particleCount: 80, spread: 60, origin: { y: 0.6 } });
        }

        function copyPixCode() {
            const input = document.getElementById('pix-code-input');
            navigator.clipboard.writeText(input.value).then(() => {
                const feedback = document.getElementById('copy-feedback');
                feedback.classList.remove('hidden');
                setTimeout(() => feedback.classList.add('hidden'), 2000);
            });
        }

        function copyDeliveredKey() {
            navigator.clipboard.writeText(currentDeliveredKey).then(() => {
                const btn = document.getElementById('copy-key-btn-text');
                btn.textContent = "Copiado!";
                setTimeout(() => btn.textContent = "Copiar", 2000);
            });
        }

        function downloadKeyTxt() {
            const names = { 'G': 'GOOGLE', 'X': 'X', 'F': 'FACE' };
            const prod = names[currentCategory] || currentCategory;
            const content = `COMPROVANTE DE ENTREGA\\nProduto: ${prod}\\nValor: R$ 3,50\\nPedido: ${currentOrderId}\\nData: ${new Date().toLocaleString('pt-BR')}\\n\\nCONTEUDO:\\n${currentDeliveredKey}`;
            const blob = new Blob([content], { type: 'text/plain;charset=utf-8' });
            const a = document.createElement('a');
            a.href = URL.createObjectURL(blob);
            a.download = `${prod}_${currentOrderId}.txt`;
            a.click();
        }

        async function simulateOrderApproval() {
            if (!currentOrderId) return;
            try {
                const resp = await fetch('/api/simulate-payment/' + currentOrderId, { method: 'POST' });
                const data = await resp.json();
                if (data.success && data.status === 'approved') {
                    clearInterval(pollingInterval);
                    showSuccessScreen(data.delivered_key);
                } else {
                    alert(data.message || 'Erro');
                }
            } catch (e) { alert(e.message); }
        }
    </script>
</body>
</html>"""

FULL_ADMIN_HTML = """<!DOCTYPE html>
<html lang="pt-BR" class="dark">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Painel Administrativo | Gerenciador de Estoque</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.1/css/all.min.css">
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800;900&family=JetBrains+Mono:wght@400;600;700&display=swap');
        body { font-family: 'Plus Jakarta Sans', sans-serif; background-color: #090d16; color: #f1f5f9; }
        code, pre, .font-mono { font-family: 'JetBrains Mono', monospace; }
    </style>
</head>
<body class="bg-[#090d16] text-slate-100 min-h-screen font-sans selection:bg-indigo-500 selection:text-white antialiased">
    <!-- LOGIN SCREEN -->
    <div id="login-container" class="min-h-screen flex items-center justify-center p-4">
        <div class="w-full max-w-sm bg-[#0f172a] border border-slate-800 rounded-3xl p-7 shadow-2xl">
            <div class="text-center mb-6">
                <div class="w-12 h-12 rounded-2xl bg-indigo-500/10 border border-indigo-500/20 text-indigo-400 flex items-center justify-center text-xl mx-auto mb-3">
                    <i class="fa-solid fa-lock"></i>
                </div>
                <h2 class="text-xl font-black text-white">Painel Administrativo</h2>
                <p class="text-xs text-slate-400 mt-0.5">Gerenciador de Estoque</p>
            </div>

            <form id="admin-login-form" onsubmit="handleLogin(event)" class="space-y-4">
                <div>
                    <label class="block text-[11px] font-semibold text-slate-400 uppercase tracking-wider mb-1.5">Senha de Acesso:</label>
                    <input type="password" id="admin-password-input" required placeholder="Digite a senha mestra" class="w-full px-3.5 py-2.5 rounded-xl bg-slate-900 border border-slate-700 text-white placeholder-slate-500 focus:outline-none focus:border-indigo-500 transition text-xs">
                </div>
                <div id="login-error" class="hidden p-2.5 rounded-xl bg-rose-500/10 border border-rose-500/20 text-rose-400 text-xs font-semibold"></div>
                <button type="submit" id="btn-login" class="w-full py-2.5 rounded-xl bg-indigo-600 hover:bg-indigo-500 text-white font-bold text-xs transition flex items-center justify-center gap-2">
                    <i class="fa-solid fa-arrow-right-to-bracket"></i>
                    <span>Entrar no Painel</span>
                </button>
            </form>
            <div class="mt-5 text-center">
                <a href="/" class="text-xs text-slate-400 hover:text-white transition flex items-center justify-center gap-1.5">
                    <i class="fa-solid fa-arrow-left text-[10px]"></i>
                    <span>Voltar para a Loja</span>
                </a>
            </div>
        </div>
    </div>

    <!-- PAINEL DASHBOARD -->
    <div id="admin-dashboard" class="hidden min-h-screen flex flex-col">
        <header class="border-b border-slate-800/80 bg-[#090d16]/90 backdrop-blur-md sticky top-0 z-30">
            <div class="max-w-6xl mx-auto px-4 sm:px-6 h-16 flex items-center justify-between">
                <div class="flex items-center gap-3">
                    <div class="w-8 h-8 rounded-xl bg-indigo-500/20 border border-indigo-500/30 flex items-center justify-center text-indigo-400 text-sm">
                        <i class="fa-solid fa-cube"></i>
                    </div>
                    <div>
                        <h1 class="font-extrabold text-sm tracking-tight text-white">Painel de Estoque</h1>
                        <span class="text-[10px] text-slate-400 block -mt-0.5">GOOGLE • X • FACE</span>
                    </div>
                </div>
                <div class="flex items-center gap-2.5">
                    <a href="/" target="_blank" class="px-3 py-1.5 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-300 text-xs font-medium border border-slate-700/80 transition flex items-center gap-1.5">
                        <i class="fa-solid fa-arrow-up-right-from-square text-[10px] text-emerald-400"></i>
                        <span>Ver Loja</span>
                    </a>
                    <button onclick="handleLogout()" class="px-3 py-1.5 rounded-xl bg-rose-500/10 hover:bg-rose-500/20 text-rose-300 text-xs font-medium border border-rose-500/20 transition flex items-center gap-1.5">
                        <i class="fa-solid fa-power-off text-[10px]"></i>
                        <span>Sair</span>
                    </button>
                </div>
            </div>
        </header>

        <main class="flex-1 max-w-6xl mx-auto px-4 sm:px-6 py-6 sm:py-8 w-full">
            <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
                <div class="bg-[#0f172a] border border-slate-800 rounded-2xl p-4">
                    <span class="text-[11px] font-semibold text-slate-400 uppercase tracking-wider block mb-1">Faturamento</span>
                    <div class="text-xl font-black text-white" id="stat-revenue">R$ 0,00</div>
                    <p class="text-[10px] text-slate-500 mt-0.5">Vendas aprovadas</p>
                </div>
                <div class="bg-[#0f172a] border border-slate-800 rounded-2xl p-4 border-l-4 border-l-red-500">
                    <span class="text-[11px] font-bold text-slate-300 flex items-center gap-1.5 mb-1"><i class="fa-brands fa-google text-red-400"></i> GOOGLE</span>
                    <div class="text-xl font-black text-white" id="stat-stock-g">0</div>
                    <p class="text-[10px] text-slate-400 mt-0.5" id="stat-sold-g">0 vendidos</p>
                </div>
                <div class="bg-[#0f172a] border border-slate-800 rounded-2xl p-4 border-l-4 border-l-slate-400">
                    <span class="text-[11px] font-bold text-slate-300 flex items-center gap-1.5 mb-1"><i class="fa-brands fa-x-twitter text-white"></i> X</span>
                    <div class="text-xl font-black text-white" id="stat-stock-x">0</div>
                    <p class="text-[10px] text-slate-400 mt-0.5" id="stat-sold-x">0 vendidos</p>
                </div>
                <div class="bg-[#0f172a] border border-slate-800 rounded-2xl p-4 border-l-4 border-l-blue-500">
                    <span class="text-[11px] font-bold text-slate-300 flex items-center gap-1.5 mb-1"><i class="fa-brands fa-facebook-f text-blue-400"></i> FACE</span>
                    <div class="text-xl font-black text-white" id="stat-stock-f">0</div>
                    <p class="text-[10px] text-slate-400 mt-0.5" id="stat-sold-f">0 vendidos</p>
                </div>
            </div>

            <!-- Tabs -->
            <div class="flex border-b border-slate-800 mb-6 gap-2 text-xs">
                <button onclick="switchTab('stock')" id="tab-btn-stock" class="px-4 py-2.5 font-bold border-b-2 border-indigo-500 text-white flex items-center gap-2 transition">
                    <i class="fa-solid fa-boxes-stacked"></i><span>Adicionar ao Estoque</span>
                </button>
                <button onclick="switchTab('orders')" id="tab-btn-orders" class="px-4 py-2.5 font-medium border-b-2 border-transparent text-slate-400 hover:text-slate-200 flex items-center gap-2 transition">
                    <i class="fa-solid fa-receipt"></i><span>Vendas</span>
                </button>
                <button onclick="switchTab('settings')" id="tab-btn-settings" class="px-4 py-2.5 font-medium border-b-2 border-transparent text-slate-400 hover:text-slate-200 flex items-center gap-2 transition">
                    <i class="fa-solid fa-gear"></i><span>Configurações & Mercado Pago</span>
                </button>
            </div>

            <!-- TAB 1: ESTOQUE -->
            <div id="tab-content-stock" class="space-y-6">
                <div class="bg-[#0f172a] border border-slate-800 rounded-2xl p-5 sm:p-6">
                    <h2 class="text-base font-bold text-white mb-1">Formulário de Inserção de Estoque</h2>
                    <p class="text-xs text-slate-400 mb-5">Escolha GOOGLE, X ou FACE e cole a lista de itens (um por linha).</p>
                    <form id="add-keys-form" onsubmit="handleAddKeys(event)" class="space-y-4">
                        <div class="grid grid-cols-1 sm:grid-cols-3 gap-4">
                            <div>
                                <label class="block text-[11px] font-bold text-slate-300 uppercase tracking-wider mb-1.5">Produto:</label>
                                <select id="key-category-select" required class="w-full px-3.5 py-2.5 rounded-xl bg-slate-900 border border-slate-700 text-white font-semibold text-xs focus:outline-none">
                                    <option value="G">GOOGLE (R$ 3,50)</option>
                                    <option value="X">X (R$ 3,50)</option>
                                    <option value="F">FACE (R$ 3,50)</option>
                                </select>
                            </div>
                            <div class="sm:col-span-2">
                                <label class="block text-[11px] font-bold text-slate-300 uppercase tracking-wider mb-1.5 flex justify-between">
                                    <span>Cole os itens (um por linha):</span>
                                    <span id="line-counter" class="text-slate-500 text-xs font-mono">0 itens digitados</span>
                                </label>
                                <textarea id="keys-textarea" rows="5" required oninput="updateLineCounter()" placeholder="Cole aqui seus itens, um em cada linha..." class="w-full px-3.5 py-2.5 rounded-xl bg-slate-900 border border-slate-700 text-white font-mono text-xs placeholder-slate-600 focus:outline-none focus:border-emerald-500 transition resize-y"></textarea>
                            </div>
                        </div>
                        <div id="add-feedback" class="hidden p-3 rounded-xl text-xs font-semibold"></div>
                        <div class="flex justify-end">
                            <button type="submit" id="btn-submit-keys" class="px-5 py-2.5 rounded-xl bg-emerald-500 hover:bg-emerald-400 text-slate-950 font-bold text-xs transition flex items-center gap-2">
                                <i class="fa-solid fa-cloud-arrow-up"></i><span>Salvar no Estoque</span>
                            </button>
                        </div>
                    </form>
                </div>

                <div class="bg-[#0f172a] border border-slate-800 rounded-2xl p-5 sm:p-6">
                    <div class="flex flex-col sm:flex-row sm:items-center justify-between gap-3 mb-4">
                        <h3 class="text-sm font-bold text-white">Itens Cadastrados no Estoque</h3>
                        <div class="flex flex-wrap items-center gap-2">
                            <select id="filter-category" onchange="loadKeysTable()" class="px-3 py-1.5 rounded-xl bg-slate-900 border border-slate-700 text-xs text-slate-200">
                                <option value="">Todos</option><option value="G">GOOGLE</option><option value="X">X</option><option value="F">FACE</option>
                            </select>
                            <select id="filter-status" onchange="loadKeysTable()" class="px-3 py-1.5 rounded-xl bg-slate-900 border border-slate-700 text-xs text-slate-200">
                                <option value="available">Disponíveis</option><option value="sold">Vendidos</option><option value="">Todos</option>
                            </select>
                            <button onclick="loadKeysTable()" class="p-2 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-300 text-xs transition"><i class="fa-solid fa-arrows-rotate"></i></button>
                        </div>
                    </div>
                    <div class="overflow-x-auto rounded-xl border border-slate-800">
                        <table class="w-full text-left text-xs">
                            <thead class="bg-slate-900/80 text-slate-400 uppercase text-[10px] border-b border-slate-800">
                                <tr><th class="px-3.5 py-2.5 font-semibold">ID</th><th class="px-3.5 py-2.5 font-semibold">Produto</th><th class="px-3.5 py-2.5 font-semibold">Conteúdo</th><th class="px-3.5 py-2.5 font-semibold">Status</th><th class="px-3.5 py-2.5 font-semibold">Data</th><th class="px-3.5 py-2.5 font-semibold text-right">Ação</th></tr>
                            </thead>
                            <tbody id="keys-table-body" class="divide-y divide-slate-800 font-mono text-[11px]">
                                <tr><td colspan="6" class="px-3 py-6 text-center text-slate-500 font-sans">Carregando...</td></tr>
                            </tbody>
                        </table>
                    </div>
                </div>
            </div>

            <!-- TAB 2: VENDAS -->
            <div id="tab-content-orders" class="hidden space-y-4">
                <div class="bg-[#0f172a] border border-slate-800 rounded-2xl p-5 sm:p-6">
                    <h3 class="text-sm font-bold text-white mb-4">Histórico de Pedidos</h3>
                    <div class="overflow-x-auto rounded-xl border border-slate-800">
                        <table class="w-full text-left text-xs">
                            <thead class="bg-slate-900/80 text-slate-400 uppercase text-[10px] border-b border-slate-800">
                                <tr><th class="px-3.5 py-2.5 font-semibold">ID Pedido</th><th class="px-3.5 py-2.5 font-semibold">Produto</th><th class="px-3.5 py-2.5 font-semibold">Valor</th><th class="px-3.5 py-2.5 font-semibold">Status</th><th class="px-3.5 py-2.5 font-semibold">Entregue</th><th class="px-3.5 py-2.5 font-semibold">Data</th></tr>
                            </thead>
                            <tbody id="orders-table-body" class="divide-y divide-slate-800">
                                <tr><td colspan="6" class="px-3 py-6 text-center text-slate-500">Nenhum pedido registrado ainda.</td></tr>
                            </tbody>
                        </table>
                    </div>
                </div>
            </div>

            <!-- TAB 3: CONFIGURAÇÕES -->
            <div id="tab-content-settings" class="hidden space-y-4">
                <div class="bg-[#0f172a] border border-slate-800 rounded-2xl p-5 sm:p-6 max-w-2xl">
                    <h3 class="text-sm font-bold text-white mb-4 flex items-center gap-2"><i class="fa-brands fa-pix text-emerald-400"></i><span>Configurações & Mercado Pago</span></h3>
                    <form id="settings-form" onsubmit="handleSaveSettings(event)" class="space-y-4">
                        <div>
                            <label class="block text-[11px] font-bold text-slate-300 uppercase tracking-wider mb-1">Access Token do Mercado Pago:</label>
                            <input type="password" id="input-mp-token" placeholder="APP_USR-..." class="w-full px-3.5 py-2.5 rounded-xl bg-slate-900 border border-slate-700 text-white font-mono text-xs focus:outline-none">
                        </div>
                        <div class="flex items-center justify-between p-3.5 bg-slate-900/60 rounded-xl border border-slate-800">
                            <div><span class="block text-xs font-bold text-white">Modo Demonstração</span><span class="text-[11px] text-slate-400">Permite simular aprovação para testes sem gastar dinheiro.</span></div>
                            <input type="checkbox" id="input-test-mode" class="w-4 h-4 rounded text-emerald-500">
                        </div>
                        <div>
                            <label class="block text-[11px] font-bold text-slate-300 uppercase tracking-wider mb-1">Nome da Loja:</label>
                            <input type="text" id="input-store-name" placeholder="DIGITAL STORE" class="w-full px-3.5 py-2.5 rounded-xl bg-slate-900 border border-slate-700 text-white text-xs focus:outline-none">
                        </div>
                        <div>
                            <label class="block text-[11px] font-bold text-slate-300 uppercase tracking-wider mb-1">Nova Senha do Painel (opcional):</label>
                            <input type="password" id="input-new-password" placeholder="Deixe em branco para manter a atual" class="w-full px-3.5 py-2.5 rounded-xl bg-slate-900 border border-slate-700 text-white text-xs focus:outline-none">
                        </div>
                        <div id="settings-feedback" class="hidden p-2.5 rounded-xl text-xs font-semibold"></div>
                        <div class="flex items-center justify-between pt-2">
                            <button type="button" onclick="testMercadoPagoToken()" class="px-3.5 py-2 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-300 text-xs font-medium border border-slate-700 transition">Testar Conexão</button>
                            <button type="submit" class="px-5 py-2 rounded-xl bg-indigo-600 hover:bg-indigo-500 text-white font-bold text-xs transition">Salvar Alterações</button>
                        </div>
                    </form>
                </div>
            </div>
        </main>
    </div>

    <!-- Admin JS Inline -->
    <script>
        let currentTab = 'stock';
        document.addEventListener('DOMContentLoaded', () => { checkAuth(); });

        async function checkAuth() {
            try {
                const resp = await fetch('/api/admin/check-auth');
                const data = await resp.json();
                if (data.authenticated) showDashboard(); else showLogin();
            } catch (err) { showLogin(); }
        }

        function showLogin() {
            document.getElementById('login-container').classList.remove('hidden');
            document.getElementById('admin-dashboard').classList.add('hidden');
        }

        function showDashboard() {
            document.getElementById('login-container').classList.add('hidden');
            document.getElementById('admin-dashboard').classList.remove('hidden');
            loadDashboardStats();
            loadKeysTable();
            loadSettings();
        }

        async function handleLogin(e) {
            e.preventDefault();
            const password = document.getElementById('admin-password-input').value;
            const errorBox = document.getElementById('login-error');
            const btn = document.getElementById('btn-login');
            btn.disabled = true;
            btn.innerHTML = 'Entrando...';
            errorBox.classList.add('hidden');

            try {
                const resp = await fetch('/api/admin/login', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ password })
                });
                const data = await resp.json();
                if (data.success) {
                    showDashboard();
                } else {
                    errorBox.textContent = data.message || 'Senha incorreta';
                    errorBox.classList.remove('hidden');
                }
            } catch (err) {
                errorBox.textContent = 'Erro ao conectar';
                errorBox.classList.remove('hidden');
            } finally {
                btn.disabled = false;
                btn.innerHTML = '<i class="fa-solid fa-arrow-right-to-bracket mr-1"></i> Entrar no Painel';
            }
        }

        async function handleLogout() {
            await fetch('/api/admin/logout', { method: 'POST' });
            window.location.reload();
        }

        function switchTab(tab) {
            currentTab = tab;
            ['stock', 'orders', 'settings'].forEach(t => {
                const btn = document.getElementById(`tab-btn-${t}`);
                const content = document.getElementById(`tab-content-${t}`);
                if (t === tab) {
                    btn.classList.add('border-indigo-500', 'text-white');
                    btn.classList.remove('border-transparent', 'text-slate-400');
                    content.classList.remove('hidden');
                } else {
                    btn.classList.remove('border-indigo-500', 'text-white');
                    btn.classList.add('border-transparent', 'text-slate-400');
                    content.classList.add('hidden');
                }
            });
            if (tab === 'stock') loadKeysTable();
            else if (tab === 'orders') loadDashboardStats();
            else if (tab === 'settings') loadSettings();
        }

        async function loadDashboardStats() {
            try {
                const resp = await fetch('/api/admin/dashboard-stats');
                const data = await resp.json();
                if (!data.success) return;
                document.getElementById('stat-revenue').textContent = `R$ ${data.total_revenue.toFixed(2).replace('.', ',')}`;
                data.stock_by_category.forEach(cat => {
                    const code = cat.code.toLowerCase();
                    const sEl = document.getElementById(`stat-stock-${code}`);
                    const soEl = document.getElementById(`stat-sold-${code}`);
                    if (sEl) sEl.textContent = cat.available_stock;
                    if (soEl) soEl.textContent = `${cat.sold_stock} vendidos`;
                });
                renderOrdersTable(data.recent_orders);
            } catch (err) {}
        }

        function renderOrdersTable(orders) {
            const tbody = document.getElementById('orders-table-body');
            if (!orders || orders.length === 0) {
                tbody.innerHTML = '<tr><td colspan="6" class="px-3 py-6 text-center text-slate-500">Nenhum pedido registrado ainda.</td></tr>';
                return;
            }
            const map = { 'G': 'GOOGLE', 'X': 'X', 'F': 'FACE' };
            tbody.innerHTML = orders.map(o => {
                let badge = '<span class="px-2 py-0.5 rounded-full text-[10px] font-bold bg-amber-500/10 text-amber-400">Pendente</span>';
                if (o.status === 'approved') badge = '<span class="px-2 py-0.5 rounded-full text-[10px] font-bold bg-emerald-500/10 text-emerald-400">Aprovado</span>';
                else if (o.status === 'out_of_stock') badge = '<span class="px-2 py-0.5 rounded-full text-[10px] font-bold bg-rose-500/10 text-rose-400">Sem Estoque</span>';
                return `
                    <tr class="hover:bg-slate-900/40 transition">
                        <td class="px-3.5 py-2.5 font-mono text-slate-300">${o.id}</td>
                        <td class="px-3.5 py-2.5 font-bold text-white">${map[o.category_code] || o.category_code}</td>
                        <td class="px-3.5 py-2.5 font-bold text-emerald-400">R$ ${o.amount.toFixed(2).replace('.', ',')}</td>
                        <td class="px-3.5 py-2.5">${badge}</td>
                        <td class="px-3.5 py-2.5 font-mono text-xs text-indigo-300 select-all">${o.delivered_key || '—'}</td>
                        <td class="px-3.5 py-2.5 text-slate-400 text-[11px]">${new Date(o.created_at).toLocaleString('pt-BR')}</td>
                    </tr>
                `;
            }).join('');
        }

        function updateLineCounter() {
            const text = document.getElementById('keys-textarea').value;
            const lines = text.split('\\n').filter(l => l.trim().length > 0);
            document.getElementById('line-counter').textContent = `${lines.length} itens digitados`;
        }

        async function handleAddKeys(e) {
            e.preventDefault();
            const category = document.getElementById('key-category-select').value;
            const rawKeys = document.getElementById('keys-textarea').value;
            const feedback = document.getElementById('add-feedback');
            const btn = document.getElementById('btn-submit-keys');

            btn.disabled = true;
            btn.innerHTML = 'Salvando...';
            try {
                const resp = await fetch('/api/admin/keys/add', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ category_code: category, keys_text: rawKeys })
                });
                const data = await resp.json();
                if (data.success) {
                    feedback.className = 'p-3 rounded-xl text-xs font-semibold bg-emerald-500/10 border border-emerald-500/20 text-emerald-400';
                    feedback.innerHTML = `<i class="fa-solid fa-check mr-2"></i> ${data.message}`;
                    document.getElementById('keys-textarea').value = '';
                    updateLineCounter();
                    loadDashboardStats();
                    loadKeysTable();
                } else {
                    feedback.className = 'p-3 rounded-xl text-xs font-semibold bg-rose-500/10 border border-rose-500/20 text-rose-400';
                    feedback.innerHTML = `<i class="fa-solid fa-triangle-exclamation mr-2"></i> ${data.message}`;
                }
            } catch (err) {
                feedback.className = 'p-3 rounded-xl text-xs font-semibold bg-rose-500/10 border border-rose-500/20 text-rose-400';
                feedback.innerHTML = 'Erro ao conectar ao servidor.';
            } finally {
                btn.disabled = false;
                btn.innerHTML = '<i class="fa-solid fa-cloud-arrow-up mr-1"></i> Salvar no Estoque';
            }
        }

        async function loadKeysTable() {
            const category = document.getElementById('filter-category').value;
            const status = document.getElementById('filter-status').value;
            const tbody = document.getElementById('keys-table-body');
            const map = { 'G': 'GOOGLE', 'X': 'X', 'F': 'FACE' };

            try {
                const q = new URLSearchParams();
                if (category) q.append('category', category);
                if (status) q.append('status', status);
                const resp = await fetch('/api/admin/keys?' + q.toString());
                const data = await resp.json();
                if (!data.success || !data.keys || data.keys.length === 0) {
                    tbody.innerHTML = '<tr><td colspan="6" class="px-3 py-6 text-center text-slate-500">Nenhum item em estoque.</td></tr>';
                    return;
                }
                tbody.innerHTML = data.keys.map(k => `
                    <tr class="hover:bg-slate-900/40 transition">
                        <td class="px-3.5 py-2.5 text-slate-400">${k.id}</td>
                        <td class="px-3.5 py-2.5 font-bold text-white font-sans">${map[k.category_code] || k.category_code}</td>
                        <td class="px-3.5 py-2.5 font-mono text-slate-200 select-all">${k.key_value}</td>
                        <td class="px-3.5 py-2.5">${k.status === 'available' ? '<span class="px-2 py-0.5 rounded-full text-[10px] font-bold bg-emerald-500/10 text-emerald-400">Disponível</span>' : '<span class="px-2 py-0.5 rounded-full text-[10px] font-bold bg-slate-800 text-slate-400">Vendido</span>'}</td>
                        <td class="px-3.5 py-2.5 text-slate-400 text-xs">${new Date(k.created_at).toLocaleDateString('pt-BR')}</td>
                        <td class="px-3.5 py-2.5 text-right">${k.status === 'available' ? `<button onclick="deleteKey(${k.id})" class="px-2 py-1 rounded bg-rose-500/10 text-rose-400 text-xs hover:bg-rose-500/20"><i class="fa-solid fa-trash-can"></i></button>` : '—'}</td>
                    </tr>
                `).join('');
            } catch (e) {}
        }

        async function deleteKey(id) {
            if (!confirm('Remover item?')) return;
            const resp = await fetch('/api/admin/keys/' + id, { method: 'DELETE' });
            loadDashboardStats();
            loadKeysTable();
        }

        async function loadSettings() {
            try {
                const resp = await fetch('/api/admin/settings');
                const data = await resp.json();
                if (!data.success) return;
                document.getElementById('input-mp-token').value = data.mp_access_token || '';
                document.getElementById('input-test-mode').checked = data.test_mode;
                document.getElementById('input-store-name').value = data.store_name || 'DIGITAL STORE';
            } catch (e) {}
        }

        async function handleSaveSettings(e) {
            e.preventDefault();
            const token = document.getElementById('input-mp-token').value;
            const testMode = document.getElementById('input-test-mode').checked;
            const storeName = document.getElementById('input-store-name').value;
            const newPassword = document.getElementById('input-new-password').value;
            const fb = document.getElementById('settings-feedback');

            const resp = await fetch('/api/admin/settings', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ mp_access_token: token, test_mode: testMode, store_name: storeName, new_password: newPassword })
            });
            const data = await resp.json();
            if (data.success) {
                fb.className = 'p-2.5 rounded-xl text-xs font-semibold bg-emerald-500/10 text-emerald-400 block';
                fb.textContent = data.message;
                setTimeout(() => fb.classList.add('hidden'), 3000);
            }
        }

        async function testMercadoPagoToken() {
            const token = document.getElementById('input-mp-token').value.trim();
            const fb = document.getElementById('settings-feedback');
            fb.className = 'p-2.5 rounded-xl text-xs font-semibold bg-indigo-500/10 text-indigo-400 block';
            fb.textContent = 'Verificando com Mercado Pago...';
            try {
                const resp = await fetch('/api/admin/test-mercadopago', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ token })
                });
                const data = await resp.json();
                fb.className = data.success ? 'p-2.5 rounded-xl text-xs font-semibold bg-emerald-500/10 text-emerald-400 block' : 'p-2.5 rounded-xl text-xs font-semibold bg-rose-500/10 text-rose-400 block';
                fb.textContent = data.message;
            } catch (e) {
                fb.className = 'p-2.5 rounded-xl text-xs font-semibold bg-rose-500/10 text-rose-400 block';
                fb.textContent = 'Erro ao testar: ' + e.message;
            }
        }
    </script>
</body>
</html>"""

# Configura o carregador do Jinja2 para usar os templates completos
app.jinja_env.loader = jinja2.DictLoader({
    'index.html': FULL_INDEX_HTML,
    'admin.html': FULL_ADMIN_HTML
})

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
