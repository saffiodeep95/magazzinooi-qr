import os
import io
import base64
import qrcode
import psycopg2
from psycopg2.extras import RealDictCursor
from flask import Flask, render_template, request, redirect, url_for, flash, session
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, date

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "chiave-segreta-magazzino-omg")

DATABASE_URL = os.environ.get("DATABASE_URL")

def get_db_connection():
    if not DATABASE_URL:
        print("DATABASE_URL non impostata!")
        return None
    try:
        conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
        return conn
    except Exception as e:
        print(f"Errore di connessione al database: {e}")
        return None

def init_db():
    conn = get_db_connection()
    if conn:
        try:
            cur = conn.cursor()
            cur.execute("""
                CREATE TABLE IF NOT EXISTS utenti (
                    id SERIAL PRIMARY KEY,
                    username VARCHAR(255) UNIQUE NOT NULL,
                    password TEXT NOT NULL,
                    is_admin BOOLEAN DEFAULT FALSE,
                    puoi_cancellare BOOLEAN DEFAULT FALSE,
                    puoi_assistenza BOOLEAN DEFAULT FALSE
                );
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS prodotti (
                    id SERIAL PRIMARY KEY,
                    qr_code VARCHAR(255) UNIQUE NOT NULL,
                    nome VARCHAR(255) NOT NULL,
                    quantita INT DEFAULT 0,
                    posizione VARCHAR(255),
                    sap VARCHAR(255),
                    modificato_da VARCHAR(255),
                    stato VARCHAR(50) DEFAULT 'Disponibile',
                    cliente_manutenzione VARCHAR(255),
                    data_spedizione DATE,
                    data_rientro DATE,
                    note_manutenzione TEXT,
                    materiale_ritornato TEXT,
                    ordine_arrivato BOOLEAN DEFAULT FALSE
                );
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS storico_manutenzioni (
                    id SERIAL PRIMARY KEY,
                    qr_code VARCHAR(255) NOT NULL,
                    nome_prodotto VARCHAR(255),
                    cliente VARCHAR(255),
                    data_spedizione DATE,
                    data_rientro DATE,
                    note_manutenzione TEXT,
                    materiale_ritornato TEXT,
                    chiuso_da VARCHAR(255)
                );
            """)

            cur.execute("ALTER TABLE prodotti ADD COLUMN IF NOT EXISTS sap VARCHAR(255);")
            cur.execute("ALTER TABLE prodotti ADD COLUMN IF NOT EXISTS modificato_da VARCHAR(255);")
            cur.execute("ALTER TABLE prodotti ADD COLUMN IF NOT EXISTS stato VARCHAR(50) DEFAULT 'Disponibile';")
            cur.execute("ALTER TABLE prodotti ADD COLUMN IF NOT EXISTS cliente_manutenzione VARCHAR(255);")
            cur.execute("ALTER TABLE prodotti ADD COLUMN IF NOT EXISTS data_spedizione DATE;")
            cur.execute("ALTER TABLE prodotti ADD COLUMN IF NOT EXISTS data_rientro DATE;")
            cur.execute("ALTER TABLE prodotti ADD COLUMN IF NOT EXISTS note_manutenzione TEXT;")
            cur.execute("ALTER TABLE prodotti ADD COLUMN IF NOT EXISTS materiale_ritornato TEXT;")
            cur.execute("ALTER TABLE prodotti ADD COLUMN IF NOT EXISTS ordine_arrivato BOOLEAN DEFAULT FALSE;")
            
            cur.execute("ALTER TABLE utenti ADD COLUMN IF NOT EXISTS is_admin BOOLEAN DEFAULT FALSE;")
            cur.execute("ALTER TABLE utenti ADD COLUMN IF NOT EXISTS puoi_cancellare BOOLEAN DEFAULT FALSE;")
            cur.execute("ALTER TABLE utenti ADD COLUMN IF NOT EXISTS puoi_assistenza BOOLEAN DEFAULT FALSE;")
            
            admin_pass = generate_password_hash("admin123")
            cur.execute("""
                INSERT INTO utenti (username, password, is_admin, puoi_cancellare, puoi_assistenza) 
                VALUES ('admin', %s, TRUE, TRUE, TRUE)
                ON CONFLICT (username) DO UPDATE SET 
                    password = EXCLUDED.password, 
                    is_admin = TRUE,
                    puoi_cancellare = TRUE,
                    puoi_assistenza = TRUE;
            """, (admin_pass,))

            conn.commit()
            cur.close()
            conn.close()
        except Exception as e:
            print(f"Errore inizializzazione DB: {e}")

init_db()

def genera_qr_base64(testo):
    qr = qrcode.QRCode(version=1, box_size=5, border=2)
    qr.add_data(testo)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buffered = io.BytesIO()
    img.save(buffered, format="PNG")
    return base64.b64encode(buffered.getvalue()).decode("utf-8")

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        conn = get_db_connection()
        if conn:
            cur = conn.cursor()
            cur.execute("SELECT * FROM utenti WHERE username = %s;", (username,))
            utente = cur.fetchone()
            cur.close()
            conn.close()
            if utente and check_password_hash(utente['password'], password):
                session['user'] = utente['username']
                session['is_admin'] = utente['is_admin']
                session['puoi_cancellare'] = utente['puoi_cancellare']
                session['puoi_assistenza'] = utente['puoi_assistenza']
                return redirect(url_for('index'))
            flash("Credenziali non valide.", "error")
    return render_template("login.html")

@app.route('/registra', methods=['GET', 'POST'])
def registra():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        if not username or not password:
            flash("Compila tutti i campi!", "error")
            return redirect(url_for('registra'))
        
        conn = get_db_connection()
        if conn:
            try:
                cur = conn.cursor()
                cur.execute("INSERT INTO utenti (username, password, is_admin, puoi_cancellare, puoi_assistenza) VALUES (%s, %s, FALSE, FALSE, FALSE);", (username, generate_password_hash(password)))
                conn.commit()
                cur.close()
                conn.close()
                flash("Account creato con successo! Ora puoi effettuare il login.", "success")
                return redirect(url_for('login'))
            except psycopg2.errors.UniqueViolation:
                flash("Questo username è già registrato.", "error")
    return render_template("registra.html")

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/')
def index():
    if 'user' not in session: return redirect(url_for('login'))
    search_query = request.args.get('q', '').strip()
    conn = get_db_connection()
    if not conn: return render_template("index.html", prodotti=[], search_query=search_query, num_critici=0, num_attenzione=0)
    cur = conn.cursor()
    if search_query:
        cur.execute("SELECT * FROM prodotti WHERE qr_code ILIKE %s OR nome ILIKE %s OR sap ILIKE %s OR cliente_manutenzione ILIKE %s ORDER BY nome ASC;", (f"%{search_query}%", f"%{search_query}%", f"%{search_query}%", f"%{search_query}%"))
    else:
        cur.execute("SELECT * FROM prodotti ORDER BY nome ASC;")
    prodotti_db = cur.fetchall()
    
    cur.execute("SELECT data_spedizione FROM prodotti WHERE stato = 'In Manutenzione' AND data_spedizione IS NOT NULL;")
    maint_attive = cur.fetchall()
    
    cur.close()
    conn.close()
    
    oggi = date.today()
    num_critici = 0
    num_attenzione = 0
    for m in maint_attive:
        d_sped = m['data_spedizione']
        if isinstance(d_sped, str):
            d_sped = datetime.strptime(d_sped, '%Y-%m-%d').date()
        giorni = (oggi - d_sped).days
        if giorni >= 30:
            num_critici += 1
        elif giorni >= 15:
            num_attenzione += 1

    prodotti = [{**dict(p), 'qr_img': genera_qr_base64(url_for('gestisci_prodotto', qr_code=p['qr_code'], _external=True))} for p in prodotti_db]
    return render_template("index.html", prodotti=prodotti, search_query=search_query, num_critici=num_critici, num_attenzione=num_attenzione)

@app.route('/manutenzioni')
def lista_manutenzioni():
    if 'user' not in session: return redirect(url_for('login'))
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM prodotti WHERE stato = 'In Manutenzione' ORDER BY data_rientro ASC NULLS LAST;")
    prodotti_db = cur.fetchall()
    cur.execute("SELECT * FROM storico_manutenzioni ORDER BY id DESC;")
    storico_db = cur.fetchall()
    cur.close()
    conn.close()
    
    oggi = date.today()
    prodotti = []
    for p in prodotti_db:
        p_dict = dict(p)
        p_dict['qr_img'] = genera_qr_base64(url_for('gestisci_prodotto', qr_code=p['qr_code'], _external=True))
        if p['data_spedizione']:
            d_sped = p['data_spedizione']
            if isinstance(d_sped, str):
                d_sped = datetime.strptime(d_sped, '%Y-%m-%d').date()
            giorni_trascorsi = (oggi - d_sped).days
            p_dict['giorni_trascorsi'] = giorni_trascorsi
            if giorni_trascorsi >= 30:
                p_dict['livello_avviso'] = 'critico'
            elif giorni_trascorsi >= 15:
                p_dict['livello_avviso'] = 'attenzione'
            else:
                p_dict['livello_avviso'] = 'normale'
        else:
            p_dict['giorni_trascorsi'] = 0
            p_dict['livello_avviso'] = 'normale'
        prodotti.append(p_dict)

    return render_template("manutenzioni.html", prodotti=prodotti, storico=storico_db)

@app.route('/gestisci/<qr_code>')
def gestisci_prodotto(qr_code):
    if 'user' not in session: return redirect(url_for('login'))
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM prodotti WHERE qr_code = %s;", (qr_code,))
    prodotto = cur.fetchone()
    
    cur.execute("SELECT * FROM storico_manutenzioni WHERE qr_code = %s ORDER BY id DESC;", (qr_code,))
    storico_prodotto = cur.fetchall()
    
    cur.close()
    conn.close()
    if not prodotto:
        flash("Prodotto non trovato.", "error")
        return redirect(url_for('index'))
    
    prodotto_dict = dict(prodotto)
    prodotto_dict['qr_img'] = genera_qr_base64(url_for('gestisci_prodotto', qr_code=qr_code, _external=True))
    return render_template("gestisci.html", prodotto=prodotto_dict, storico=storico_prodotto)

@app.route('/aggiungi', methods=['POST'])
def aggiungi_prodotto():
    if 'user' not in session: return redirect(url_for('login'))
    qr_code = request.form.get('qr_code')
    nome = request.form.get('nome')
    quantita = int(request.form.get('quantita', 0) or 0)
    posizione = request.form.get('posizione', '')
    sap = request.form.get('sap', '')
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO prodotti (qr_code, nome, quantita, posizione, sap, modificato_da, stato, ordine_arrivato)
        VALUES (%s, %s, %s, %s, %s, %s, 'Disponibile', FALSE)
        ON CONFLICT (qr_code) DO UPDATE SET
            nome = EXCLUDED.nome, quantita = EXCLUDED.quantita, posizione = EXCLUDED.posizione, sap = EXCLUDED.sap, modificato_da = EXCLUDED.modificato_da;
    """, (qr_code, nome, quantita, posizione, sap, session['user']))
    conn.commit()
    cur.close()
    conn.close()
    flash("Prodotto salvato con successo.", "success")
    return redirect(url_for('index'))

@app.route('/manutenzione', methods=['POST'])
def manutenzione():
    if 'user' not in session or (not session.get('is_admin') and not session.get('puoi_assistenza')):
        return redirect(url_for('index'))
    qr_code = request.form.get('qr_code')
    cliente = request.form.get('cliente_manutenzione', '').strip()
    data_spedizione = request.form.get('data_spedizione') or None
    data_rientro = request.form.get('data_rientro') or None
    note = request.form.get('note_manutenzione', '').strip()
    
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        UPDATE prodotti 
        SET stato = 'In Manutenzione', cliente_manutenzione = %s, data_spedizione = %s, data_rientro = %s, note_manutenzione = %s, ordine_arrivato = FALSE, modificato_da = %s 
        WHERE qr_code = %s;
    """, (cliente, data_spedizione, data_rientro, note, session['user'], qr_code))
    conn.commit()
    cur.close()
    conn.close()
    flash("Pezzo inviato in manutenzione.", "success")
    return redirect(url_for('gestisci_prodotto', qr_code=qr_code))

@app.route('/aggiorna_ordine', methods=['POST'])
def aggiorna_ordine():
    if 'user' not in session or (not session.get('is_admin') and not session.get('puoi_assistenza')):
        return redirect(url_for('index'))
    qr_code = request.form.get('qr_code')
    ordine_arrivato = True if request.form.get('ordine_arrivato') == 'on' else False
    
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("UPDATE prodotti SET ordine_arrivato = %s WHERE qr_code = %s;", (ordine_arrivato, qr_code))
    conn.commit()
    cur.close()
    conn.close()
    return redirect(url_for('gestisci_prodotto', qr_code=qr_code))

@app.route('/rientro', methods=['POST'])
def rientro():
    if 'user' not in session or (not session.get('is_admin') and not session.get('puoi_assistenza')):
        return redirect(url_for('index'))
    qr_code = request.form.get('qr_code')
    materiale_ritornato = request.form.get('materiale_ritornato', '').strip()
    data_rientro_effettiva = datetime.now().strftime('%Y-%m-%d')
    
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT nome, cliente_manutenzione, data_spedizione, note_manutenzione FROM prodotti WHERE qr_code = %s;", (qr_code,))
    prod = cur.fetchone()
    
    if prod:
        cur.execute("""
            INSERT INTO storico_manutenzioni (qr_code, nome_prodotto, cliente, data_spedizione, data_rientro, note_manutenzione, materiale_ritornato, chiuso_da)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s);
        """, (qr_code, prod['nome'], prod['cliente_manutenzione'], prod['data_spedizione'], data_rientro_effettiva, prod['note_manutenzione'], materiale_ritornato, session['user']))

    cur.execute("""
        UPDATE prodotti 
        SET stato = 'Disponibile', cliente_manutenzione = NULL, data_spedizione = NULL, data_rientro = NULL, note_manutenzione = NULL, materiale_ritornato = %s, ordine_arrivato = FALSE, modificato_da = %s 
        WHERE qr_code = %s;
    """, (materiale_ritornato, session['user'], qr_code))
    conn.commit()
    cur.close()
    conn.close()
    flash("Rientro registrato e salvato nello storico!", "success")
    return redirect(url_for('gestisci_prodotto', qr_code=qr_code))

@app.route('/cancella/<qr_code>', methods=['POST'])
def cancella_prodotto(qr_code):
    if 'user' not in session or (not session.get('is_admin') and not session.get('puoi_cancellare')):
        return redirect(url_for('index'))
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM prodotti WHERE qr_code = %s;", (qr_code,))
    cur.execute("DELETE FROM storico_manutenzioni WHERE qr_code = %s;", (qr_code,))
    conn.commit()
    cur.close()
    conn.close()
    return redirect(url_for('index'))

@app.route('/carico', methods=['POST'])
def carico():
    if 'user' not in session: return redirect(url_for('login'))
    qr_code, quantita = request.form.get('qr_code'), int(request.form.get('quantita', 1) or 1)
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("UPDATE prodotti SET quantita = quantita + %s, modificato_da = %s WHERE qr_code = %s;", (quantita, session['user'], qr_code))
    conn.commit()
    cur.close()
    conn.close()
    return redirect(url_for('gestisci_prodotto', qr_code=qr_code))

@app.route('/scarico', methods=['POST'])
def scarico():
    if 'user' not in session: return redirect(url_for('login'))
    qr_code, quantita = request.form.get('qr_code'), int(request.form.get('quantita', 1) or 1)
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("UPDATE prodotti SET quantita = GREATEST(0, quantita - %s), modificato_da = %s WHERE qr_code = %s;", (quantita, session['user'], qr_code))
    conn.commit()
    cur.close()
    conn.close()
    return redirect(url_for('gestisci_prodotto', qr_code=qr_code))

@app.route('/admin/utenti')
def gestione_utenti():
    if 'user' not in session or not session.get('is_admin'): return redirect(url_for('index'))
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT id, username, is_admin, puoi_cancellare, puoi_assistenza FROM utenti ORDER BY id ASC;")
    utenti = cur.fetchall()
    cur.close()
    conn.close()
    return render_template("admin_utenti.html", utenti=utenti)

@app.route('/admin/toggle_permesso/<int:user_id>/<tipo>', methods=['POST'])
def toggle_permesso(user_id, tipo):
    if 'user' not in session or not session.get('is_admin'): return redirect(url_for('index'))
    conn = get_db_connection()
    cur = conn.cursor()
    col = 'puoi_cancellare' if tipo == 'cancellare' else 'puoi_assistenza'
    cur.execute(f"SELECT {col} FROM utenti WHERE id = %s;", (user_id,))
    res = cur.fetchone()
    if res:
        cur.execute(f"UPDATE utenti SET {col} = %s WHERE id = %s;", (not res[col], user_id))
        conn.commit()
    cur.close()
    conn.close()
    return redirect(url_for('gestione_utenti'))

@app.route('/admin/reset_password/<int:user_id>', methods=['POST'])
def reset_password(user_id):
    if 'user' not in session or not session.get('is_admin'): return redirect(url_for('index'))
    nuova_password = request.form.get('nuova_password', '').strip()
    if nuova_password:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("UPDATE utenti SET password = %s WHERE id = %s;", (generate_password_hash(nuova_password), user_id))
        conn.commit()
        cur.close()
        conn.close()
    return redirect(url_for('gestione_utenti'))

@app.route('/admin/elimina_utente/<int:user_id>', methods=['POST'])
def elimina_utente(user_id):
    if 'user' not in session or not session.get('is_admin'): return redirect(url_for('index'))
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM utenti WHERE id = %s AND username != %s;", (user_id, session['user']))
    conn.commit()
    cur.close()
    conn.close()
    return redirect(url_for('gestione_utenti'))

if __name__ == '_main_':
    app.run(host='0.0.0.0', port=5000, debug=True)
