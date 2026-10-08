import os
import qrcode
import io
import base64
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, session, flash, send_file
from werkzeug.security import generate_password_hash, check_password_hash
import psycopg2
from urllib.parse import urlparse

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'chiave_segreta_default')

# --- CONFIGURAZIONE DATABASE POSTGRESQL (RENDER) ---
def get_db_connection():
    database_url = os.environ.get('DATABASE_URL')
    if database_url:
        url = urlparse(database_url)
        conn = psycopg2.connect(
            database=url.path[1:],
            user=url.username,
            password=url.password,
            host=url.hostname,
            port=url.port
        )
        return conn
    return None

# --- INIZIALIZZAZIONE DEL DATABASE E RIPRISTINO ADMIN ---
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
                CREATE TABLE IF NOT EXISTS clienti (
                    id SERIAL PRIMARY KEY,
                    nome_azienda VARCHAR(255) UNIQUE NOT NULL,
                    indirizzo TEXT,
                    p_iva VARCHAR(50),
                    codice_fiscale VARCHAR(50),
                    telefono VARCHAR(50),
                    email VARCHAR(100)
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
            print("Database inizializzato con successo.")
        except Exception as e:
            print(f"Errore inizializzazione DB: {e}")

init_db()

# --- ROTTA PRINCIPALE (HOME) ---
@app.route('/')
def index():
    if 'username' not in session:
        return redirect(url_for('login'))
    
    conn = get_db_connection()
    prodotti = []
    if conn:
        try:
            cur = conn.cursor()
            cur.execute("SELECT * FROM prodotti ORDER BY id DESC;")
            rows = cur.fetchall()
            for r in rows:
                prodotti.append({
                    'id': r[0],
                    'qr_code': r[1],
                    'nome': r[2],
                    'quantita': r[3] if len(r) > 3 else 0,
                    'posizione': r[4] if len(r) > 4 else '',
                    'sap': r[5] if len(r) > 5 else '',
                    'modificato_da': r[6] if len(r) > 6 else '',
                    'stato': r[7] if len(r) > 7 else 'Disponibile',
                    'cliente_manutenzione': r[8] if len(r) > 8 else '',
                    'data_spedizione': r[9] if len(r) > 9 else None,
                    'data_rientro': r[10] if len(r) > 10 else None,
                    'note_manutenzione': r[11] if len(r) > 11 else '',
                    'materiale_ritornato': r[12] if len(r) > 12 else '',
                    'ordine_arrivato': r[13] if len(r) > 13 else False
                })
            cur.close()
            conn.close()
        except Exception as e:
            print(f"Errore caricamento prodotti in index: {e}")
        
    return render_template('index.html', prodotti=prodotti)

# --- AGGIUNTA O AGGIORNAMENTO PRODOTTO ---
@app.route('/aggiungi_prodotto', methods=['POST'])
def aggiungi_prodotto():
    if 'username' not in session:
        return redirect(url_for('login'))
        
    qr_code = request.form.get('qr_code', '').strip()
    nome = request.form.get('nome', '').strip()
    sap = request.form.get('sap', '').strip()
    quantita = request.form.get('quantita', 1)
    posizione = request.form.get('posizione', '').strip()
    
    try:
        quantita = int(quantita)
    except ValueError:
        quantita = 1
        
    if qr_code and nome:
        conn = get_db_connection()
        if conn:
            try:
                cur = conn.cursor()
                cur.execute("""
                    INSERT INTO prodotti (qr_code, nome, sap, quantita, posizione, modificato_da, stato)
                    VALUES (%s, %s, %s, %s, %s, %s, 'Disponibile')
                    ON CONFLICT (qr_code) DO UPDATE 
                    SET nome = EXCLUDED.nome, 
                        sap = EXCLUDED.sap, 
                        quantita = EXCLUDED.quantita, 
                        posizione = EXCLUDED.posizione, 
                        modificato_da = EXCLUDED.modificato_da;
                """, (qr_code, nome, sap if sap else None, quantita, posizione if posizione else None, session['username']))
                
                conn.commit()
                cur.close()
                conn.close()
                flash("Prodotto salvato con successo nel magazzino!")
            except Exception as e:
                print(f"Errore salvataggio prodotto: {e}")
                flash("Errore durante il salvataggio del prodotto.")
                
    return redirect(url_for('index'))

# --- ROTTA LISTA MANUTENZIONI E STORICO ---
@app.route('/manutenzioni')
def lista_manutenzioni():
    if 'username' not in session:
        return redirect(url_for('login'))
        
    conn = get_db_connection()
    prodotti_maint = []
    storico_list = []
    if conn:
        try:
            cur = conn.cursor()
            cur.execute("SELECT * FROM prodotti WHERE stato = 'In Manutenzione' ORDER BY id DESC;")
            prodotti_maint = cur.fetchall()
            
            cur.execute("SELECT * FROM storico_manutenzioni ORDER BY id DESC;")
            storico_list = cur.fetchall()
            
            cur.close()
            conn.close()
        except Exception as e:
            print(f"Errore caricamento manutenzioni: {e}")
            
    return render_template('manutenzioni.html', prodotti=prodotti_maint, storico=storico_list)

# --- ROTTA LOGIN ---
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        
        conn = get_db_connection()
        if conn:
            try:
                cur = conn.cursor()
                cur.execute("SELECT * FROM utenti WHERE username = %s;", (username,))
                user = cur.fetchone()
                cur.close()
                conn.close()
                
                if user:
                    pwd_db = user[2]
                    is_valid = False
                    try:
                        if pwd_db and (pwd_db.startswith('pbkdf2:') or pwd_db.startswith('scrypt:') or pwd_db.startswith('$')):
                            is_valid = check_password_hash(pwd_db, password)
                        else:
                            is_valid = (pwd_db == password)
                    except Exception:
                        is_valid = (pwd_db == password)
                    
                    if is_valid:
                        session['username'] = user[1]
                        session['is_admin'] = user[3]
                        session['puoi_cancellare'] = user[4]
                        session['puoi_assistenza'] = user[5]
                        return redirect(url_for('index'))
            except Exception as e:
                print(f"Errore durante il login: {e}")
                
            flash("Credenziali non valide.")
                
    return render_template('login.html')

# --- ROTTA REGISTRAZIONE NUOVO UTENTE ---
@app.route('/registra', methods=['GET', 'POST'])
def registra():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        
        if not username or not password:
            flash("Compila tutti i campi.")
            return redirect(url_for('registra'))

        hashed_password = generate_password_hash(password)
        conn = get_db_connection()
        if conn:
            try:
                cur = conn.cursor()
                cur.execute("""
                    INSERT INTO utenti (username, password, is_admin, puoi_cancellare, puoi_assistenza)
                    VALUES (%s, %s, FALSE, FALSE, FALSE);
                """, (username, hashed_password))
                conn.commit()
                cur.close()
                conn.close()
                flash("Registrazione avvenuta con successo! Ora puoi effettuare il login.")
                return redirect(url_for('login'))
            except Exception as e:
                print(f"Errore durante la registrazione: {e}")
                flash("Errore: username già esistente o non valido.")
                
    return render_template('registra.html')

# --- ROTTA LOGOUT ---
@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

# --- GESTIONE ANAGRAFICA CLIENTI (Supporta sia clienti che lista_clienti) ---
def _gestisci_clienti():
    if 'username' not in session:
        return redirect(url_for('login'))
        
    conn = get_db_connection()
    clienti_list = []
    if conn:
        try:
            cur = conn.cursor()
            cur.execute("SELECT * FROM clienti ORDER BY nome_azienda ASC;")
            clienti_raw = cur.fetchall()
            
            for c in clienti_raw:
                cliente_id, nome_azienda, indirizzo, p_iva, cf, tel, email = c
                
                cur.execute("SELECT COUNT(*) FROM prodotti WHERE cliente_manutenzione = %s;", (nome_azienda,))
                count_prodotti = cur.fetchone()[0]
                
                clienti_list.append({
                    'id': cliente_id,
                    'nome_azienda': nome_azienda,
                    'indirizzo': indirizzo,
                    'p_iva': p_iva,
                    'codice_fiscale': cf,
                    'telefono': tel,
                    'email': email,
                    'num_prodotti': count_prodotti
                })
                
            cur.close()
            conn.close()
        except Exception as e:
            print(f"Errore caricamento clienti: {e}")
        
    return render_template('clienti.html', clienti=clienti_list)

@app.route('/clienti')
def clienti():
    return _gestisci_clienti()

@app.route('/lista_clienti')
def lista_clienti():
    return _gestisci_clienti()

@app.route('/aggiungi_cliente', methods=['POST'])
def aggiungi_cliente():
    if 'username' not in session:
        return redirect(url_for('login'))
        
    nome_azienda = request.form.get('nome_azienda', '').strip()
    indirizzo = request.form.get('indirizzo', '')
    p_iva = request.form.get('p_iva', '')
    codice_fiscale = request.form.get('codice_fiscale', '')
    telefono = request.form.get('telefono', '')
    email = request.form.get('email', '')
    
    if nome_azienda:
        conn = get_db_connection()
        if conn:
            try:
                cur = conn.cursor()
                cur.execute("""
                    INSERT INTO clienti (nome_azienda, indirizzo, p_iva, codice_fiscale, telefono, email)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    ON CONFLICT (nome_azienda) DO UPDATE 
                    SET indirizzo = EXCLUDED.indirizzo, 
                        p_iva = EXCLUDED.p_iva, 
                        codice_fiscale = EXCLUDED.codice_fiscale, 
                        telefono = EXCLUDED.telefono, 
                        email = EXCLUDED.email;
                """, (nome_azienda, indirizzo, p_iva, codice_fiscale, telefono, email))
                conn.commit()
                cur.close()
                conn.close()
                flash("Cliente salvato con successo!")
            except Exception as e:
                print(f"Errore salvataggio cliente: {e}")
                flash("Errore durante il salvataggio del cliente.")
                
    return redirect(url_for('clienti'))

@app.route('/elimina_cliente/<int:cliente_id>', methods=['POST'])
def elimina_cliente(cliente_id):
    if 'username' not in session or not session.get('is_admin'):
        return redirect(url_for('login'))
        
    conn = get_db_connection()
    if conn:
        try:
            cur = conn.cursor()
            cur.execute("DELETE FROM clienti WHERE id = %s;", (cliente_id,))
            conn.commit()
            cur.close()
            conn.close()
            flash("Cliente eliminato dal database.")
        except Exception as e:
            print(f"Errore eliminazione cliente: {e}")
        
    return redirect(url_for('clienti'))

if __name__ == '_main_':
    app.run(host='0.0.0.0', port=5000, debug=True)
