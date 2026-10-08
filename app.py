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
            cur.execute("SELECT id, qr_code, nome, quantita, posizione, sap, modificato_da, stato, cliente_manutenzione, data_spedizione, data_rientro, note_manutenzione, materiale_ritornato, ordine_arrivato FROM prodotti ORDER BY id DESC;")
            rows = cur.fetchall()
            for r in rows:
                prodotti.append({
                    'id': r[0],
                    'qr_code': r[1],
                    'nome': r[2],
                    'quantita': r[3],
                    'posizione': r[4],
                    'sap': r[5],
                    'modificato_da': r[6],
                    'stato': r[7],
                    'cliente_manutenzione': r[8],
                    'data_spedizione': r[9],
                    'data_rientro': r[10],
                    'note_manutenzione': r[11],
                    'materiale_ritornato': r[12],
                    'ordine_arrivato': r[13]
                })
            cur.close()
            conn.close()
        except Exception as e:
            print(f"Errore caricamento prodotti in index: {e}")
        
    return render_template('index.html', prodotti=prodotti)

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

# --- GESTIONE ANAGRAFICA CLIENTI ---
@app.route('/clienti')
@app.route('/lista_clienti')
def clienti():
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

# --- AGGIORNAMENTO MANUTENZIONE (Con salvataggio automatico cliente) ---
@app.route('/aggiorna_manutenzione/<int:id>', methods=['POST'])
def aggiorna_manutenzione(id):
    if 'username' not in session:
        return redirect(url_for('login'))
        
    cliente = request.form.get('cliente_manutenzione', '').strip()
    stato = request.form.get('stato', '')
    note = request.form.get('note_manutenzione', '')
    data_spedizione = request.form.get('data_spedizione') or None
    data_rientro = request.form.get('data_rientro') or None
    
    conn = get_db_connection()
    if conn:
        try:
            cur = conn.cursor()
            
            # Registrazione automatica del cliente se inserito e non presente nel DB
            if cliente:
                cur.execute("SELECT id FROM clienti WHERE LOWER(nome_azienda) = LOWER(%s);", (cliente,))
                esistente = cur.fetchone()
                if not esistente:
                    cur.execute("INSERT INTO clienti (nome_azienda) VALUES (%s);", (cliente,))
            
            # Recupera dati attuali del prodotto
            cur.execute("SELECT qr_code, nome FROM prodotti WHERE id = %s;", (id,))
            prod = cur.fetchone()
            
            if prod:
                qr_code, nome_prodotto = prod[0], prod[1]
                
                # Aggiorna il prodotto nel magazzino
                cur.execute("""
                    UPDATE prodotti 
                    SET cliente_manutenzione = %s, stato = %s, note_manutenzione = %s, 
                        data_spedizione = %s, data_rientro = %s, modificato_da = %s
                    WHERE id = %s;
                """, (cliente if cliente else None, stato, note, 
                      data_spedizione, data_rientro, 
                      session['username'], id))
                
                # Registra nello storico se in manutenzione o spedito
                if stato in ['In Manutenzione', 'Spedito']:
                    cur.execute("""
                        INSERT INTO storico_manutenzioni 
                        (qr_code, nome_prodotto, cliente, data_spedizione, data_rientro, note_manutenzione, chiuso_da)
                        VALUES (%s, %s, %s, %s, %s, %s, %s);
                    """, (qr_code, nome_prodotto, cliente if cliente else None, 
                          data_spedizione, data_rientro, 
                          note, session['username']))
                    
            conn.commit()
            cur.close()
            conn.close()
            flash("Manutenzione salvata e cliente registrato con successo!")
        except Exception as e:
            print(f"Errore aggiornamento manutenzione: {e}")
            flash("Errore durante il salvataggio.")
            
    return redirect(url_for('index'))

if __name__ == '_main_':
    app.run(host='0.0.0.0', port5000, debug=True)
