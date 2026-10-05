import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'database.db')

sample_keys = [
    # KEYS G
    ('G', 'G-PREM-8941-K782-90A1'),
    ('G', 'G-PREM-3329-L901-44B2'),
    ('G', 'G-PREM-7712-M455-88C3'),
    ('G', 'G-PREM-1209-N612-55D4'),
    ('G', 'G-PREM-6543-P789-22E5'),
    
    # KEYS X
    ('X', 'X-ULTRA-9981-Q123-77F1'),
    ('X', 'X-ULTRA-4521-R456-88G2'),
    ('X', 'X-ULTRA-7832-S789-99H3'),
    ('X', 'X-ULTRA-1122-T012-33I4'),
    ('X', 'X-ULTRA-6655-U345-44J5'),

    # KEYS F
    ('F', 'F-FAST-7761-V678-55K1'),
    ('F', 'F-FAST-2341-W901-66L2'),
    ('F', 'F-FAST-8890-Y234-77M3'),
    ('F', 'F-FAST-3344-Z567-88N4'),
    ('F', 'F-FAST-9911-A890-99P5'),
]

def populate():
    if not os.path.exists(DB_PATH):
        print("Banco de dados ainda não inicializado. Execute app.py primeiro.")
        return
        
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    
    added = 0
    for cat, key_val in sample_keys:
        cur.execute("SELECT id FROM keys WHERE key_value = ?", (key_val,))
        if not cur.fetchone():
            cur.execute("INSERT INTO keys (category_code, key_value, status) VALUES (?, ?, 'available')", (cat, key_val))
            added += 1
            
    conn.commit()
    conn.close()
    print(f"Sucesso! {added} chaves de exemplo foram adicionadas ao estoque:")
    print(" - KEYS G: 5 unidades")
    print(" - KEYS X: 5 unidades")
    print(" - KEYS F: 5 unidades")
    print("Você pode removê-las a qualquer momento na Área Administrativa.")

if __name__ == '__main__':
    populate()
