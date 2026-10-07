import os
import io
import base64
import qrcode
import psycopg2
from psycopg2.extras import RealDictCursor
from flask import Flask, render_template, request, redirect, url_for, flash, session
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(_name_)
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
            # Tabella Utenti con colonna is_admin
            cur.execute("""
                CREATE TABLE IF NOT EXISTS utenti (
                    id SERIAL PRIMARY KEY,
                    username VARCHAR(255) UNIQUE NOT NULL,
                    password TEXT NOT NULL,
                    is_admin BOOLEAN DEFAULT FALSE
                );
            """)
            # Tabella Prodotti
            cur.execute("""
                CREATE TABLE IF NOT EXISTS prodotti (
                    id SERIAL PRIMARY KEY,
                    qr_code VARCHAR(255) UNIQUE NOT NULL,
                    nome VARCHAR(255) NOT NULL,
                    quantita INT DEFAULT 0,
                    posizione VARCHAR(255),
                    sap VARCHAR(255),
                    modificato_da VARCHAR(255)
                );
            """)
            cur.execute("ALTER TABLE prodotti ADD COLUMN IF NOT EXISTS sap VARCHAR(255);")
            cur.execute("ALTER TABLE prodotti ADD COLUMN IF NOT EXISTS modificato_da VARCHAR(255);")
            cur.execute("ALTER TABLE utenti ADD COLUMN IF NOT EXISTS is_admin BOOLEAN DEFAULT FALSE;")
            
            # FORZA o CREA l'account admin (Username: admin, Password: admin123)
            admin_pass = generate_password_hash("admin123")
            cur.execute("""
                INSERT INTO utenti (username, password, is_admin) 
                VALUES ('admin', %s, TRUE)
                ON CONFLICT (username) DO UPDATE SET 
                    password = EXCLUDED.password, 
                    is_admin = TRUE;
            """, (admin_pass,))

            conn.commit()
            cur.close()
            conn.close()
            print("Database inizializzato e account admin sincronizzato con successo.")
        except Exception as e:
            print(f"Errore durante l'inizializzazione del database: {e}")

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

        if not username or not password:
            flash("Inserisci username e password!", "error")
            return redirect(url_for('login'))

        conn = get_db_connection()
        if not conn:
            flash("Errore di connessione al database", "error")
            return redirect(url_for('login'))
        
        try:
            cur = conn.cursor()
            cur.execute("SELECT * FROM utenti WHERE username = %s;", (username,))
            utente = cur.fetchone()
            cur.close()
            conn.close()

            if utente and check_password_hash(utente['password'], password):
                session['user'] = utente['username']
                session['is_admin'] = utente['is_admin']
                flash(f"Benvenuto, {utente['username']}!", "success")
                return redirect(url_for('index'))
            else:
                flash("Credenziali non valide o utente inesistente.", "error")
        except Exception as e:
            flash(f"Errore durante il login: {e}", "error")

    return render_template("login.html")

@app.route('/registra', methods=['GET', 'POST'])
def registra():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')

        if not username or not password:
            flash("Compila tutti i campi!", "error")
            return redirect(url_for('registra'))

        hashed_password = generate_password_hash(password)
        conn = get_db_connection()
        if not conn:
            flash("Errore di connessione al database", "error")
            return redirect(url_for('registra'))
        
        try:
            cur = conn.cursor()
            cur.execute("INSERT INTO utenti (username, password, is_admin) VALUES (%s, %s, FALSE);", (username, hashed_password))
            conn.commit()
            cur.close()
            conn.close()
            flash("Account creato con successo! Ora puoi effettuare il login.", "success")
            return redirect(url_for('login'))
        except psycopg2.errors.UniqueViolation:
            flash("Questo username è già registrato. Scegline un altro.", "error")
        except Exception as e:
            flash(f"Errore durante la registrazione: {e}", "error")

    return render_template("registra.html")

@app.route('/logout')
def logout():
    session.clear()
    flash("Logout effettuato con successo.", "success")
    return redirect(url_for('login'))

@app.route('/admin/utenti')
def gestione_utenti():
    if 'user' not in session or not session.get('is_admin'):
        flash("Accesso negato. Solo gli amministratori possono gestire gli utenti.", "error")
        return redirect(url_for('index'))

    conn = get_db_connection()
    if not conn:
        return redirect(url_for('index'))
    try:
        cur = conn.cursor()
        cur.execute("SELECT id, username, is_admin FROM utenti ORDER BY id ASC;")
        utenti = cur.fetchall()
        cur.close()
        conn.close()
        return render_template("admin_utenti.html", utenti=utenti)
    except Exception as e:
        flash(f"Errore nel recupero utenti: {e}", "error")
        return redirect(url_for('index'))

@app.route('/admin/reset_password/<int:user_id>', methods=['POST'])
def reset_password(user_id):
    if 'user' not in session or not session.get('is_admin'):
        flash("Accesso negato.", "error")
        return redirect(url_for('index'))

    nuova_password = request.form.get('nuova_password', '').strip()
    if not nuova_password:
        flash("La nuova password non può essere vuota.", "error")
        return redirect(url_for('gestione_utenti'))

    hashed_pw = generate_password_hash(nuova_password)
    conn = get_db_connection()
    if not conn:
        return redirect(url_for('index'))
    try:
        cur = conn.cursor()
        cur.execute("UPDATE utenti SET password = %s WHERE id = %s;", (hashed_pw, user_id))
        conn.commit()
        cur.close()
        conn.close()
        flash("Password resettata con successo per l'utente.", "success")
    except Exception as e:
        flash(f"Errore durante il reset: {e}", "error")

    return redirect(url_for('gestione_utenti'))

@app.route('/admin/elimina_utente/<int:user_id>', methods=['POST'])
def elimina_utente(user_id):
    if 'user' not in session or not session.get('is_admin'):
        flash("Accesso negato.", "error")
        return redirect(url_for('index'))

    conn = get_db_connection()
    if not conn:
        return redirect(url_for('index'))
    try:
        cur = conn.cursor()
        cur.execute("SELECT username FROM utenti WHERE id = %s;", (user_id,))
        u = cur.fetchone()
        if u and u['username'] == session['user']:
            flash("Non puoi eliminare il tuo stesso account amministratore!", "error")
        else:
            cur.execute("DELETE FROM utenti WHERE id = %s;", (user_id,))
            conn.commit()
            flash("Account eliminato con successo.", "success")
        cur.close()
        conn.close()
    except Exception as e:
        flash(f"Errore durante l'eliminazione: {e}", "error")

    return redirect(url_for('gestione_utenti'))

@app.route('/')
def index():
    if 'user' not in session:
        return redirect(url_for('login'))

    search_query = request.args.get('q', '').strip()
    conn = get_db_connection()
    if not conn:
        return render_template("index.html", prodotti=[], search_query=search_query)
    try:
        cur = conn.cursor()
        if search_query:
            cur.execute("""
                SELECT id, qr_code, nome, quantita, posizione, sap, modificato_da 
                FROM prodotti 
                WHERE qr_code ILIKE %s OR nome ILIKE %s OR sap ILIKE %s
                ORDER BY nome ASC;
            """, (f"%{search_query}%", f"%{search_query}%", f"%{search_query}%"))
        else:
            cur.execute("SELECT id, qr_code, nome, quantita, posizione, sap, modificato_da FROM prodotti ORDER BY nome ASC;")
        
        prodotti_db = cur.fetchall()
        cur.close()
        conn.close()
        
        prodotti = []
        for p in prodotti_db:
            p_dict = dict(p)
            url_azione = url_for('gestisci_prodotto', qr_code=p['qr_code'], _external=True)
            p_dict['qr_img'] = genera_qr_base64(url_azione)
            prodotti.append(p_dict)

        return render_template("index.html", prodotti=prodotti, search_query=search_query)
    except Exception as e:
        print(f"Errore nella rotta index: {e}")
        return render_template("index.html", prodotti=[], search_query=search_query)

@app.route('/gestisci/<qr_code>')
def gestisci_prodotto(qr_code):
    if 'user' not in session:
        return redirect(url_for('login'))

    conn = get_db_connection()
    if not conn:
        flash("Errore di connessione al database", "error")
        return redirect(url_for('index'))
    try:
        cur = conn.cursor()
        cur.execute("SELECT id, qr_code, nome, quantita, posizione, sap, modificato_da FROM prodotti WHERE qr_code = %s;", (qr_code,))
        prodotto = cur.fetchone()
        cur.close()
        conn.close()
        if not prodotto:
            flash("Prodotto non trovato nel sistema!", "error")
            return redirect(url_for('index'))
        
        prodotto_dict = dict(prodotto)
        url_azione = url_for('gestisci_prodotto', qr_code=qr_code, _external=True)
        prodotto_dict['qr_img'] = genera_qr_base64(url_azione)

        return render_template("gestisci.html", prodotto=prodotto_dict)
    except Exception as e:
        flash(f"Errore: {e}", "error")
        return redirect(url_for('index'))

@app.route('/aggiungi', methods=['POST'])
def aggiungi_prodotto():
    if 'user' not in session:
        return redirect(url_for('login'))

    qr_code = request.form.get('qr_code')
    nome = request.form.get('nome')
    try:
        quantita = int(request.form.get('quantita', 0))
    except ValueError:
        quantita = 0
    posizione = request.form.get('posizione', '')
    sap = request.form.get('sap', '')
    utente_corrente = session['user']

    if not qr_code or not nome:
        flash("QR Code e Nome sono obbligatori!", "error")
        return redirect(url_for('index'))

    conn = get_db_connection()
    if not conn:
        flash("Errore di connessione al database", "error")
        return redirect(url_for('index'))
    try:
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO prodotti (qr_code, nome, quantita, posizione, sap, modificato_da)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (qr_code) DO UPDATE SET
                nome = EXCLUDED.nome,
                quantita = EXCLUDED.quantita,
                posizione = EXCLUDED.posizione,
                sap = EXCLUDED.sap,
                modificato_da = EXCLUDED.modificato_da;
        """, (qr_code, nome, quantita, posizione, sap, utente_corrente))
            
        conn.commit()
        cur.close()
        conn.close()
        flash(f"Prodotto salvato con successo da {utente_corrente}!", "success")
    except Exception as e:
        flash(f"Errore nell'inserimento: {e}", "error")
    return redirect(url_for('index'))

@app.route('/cancella/<qr_code>', methods=['POST'])
def cancella_prodotto(qr_code):
    if 'user' not in session:
        return redirect(url_for('login'))

    conn = get_db_connection()
    if not conn:
        flash("Errore di connessione al database", "error")
        return redirect(url_for('index'))
    try:
        cur = conn.cursor()
        cur.execute("DELETE FROM prodotti WHERE qr_code = %s;", (qr_code,))
        conn.commit()
        cur.close()
        conn.close()
        flash("Prodotto eliminato con successo!", "success")
    except Exception as e:
        flash(f"Errore durante l'eliminazione: {e}", "error")
    return redirect(url_for('index'))

@app.route('/carico', methods=['POST'])
def carico():
    if 'user' not in session:
        return redirect(url_for('login'))

    qr_code = request.form.get('qr_code')
    try:
        quantita = int(request.form.get('quantita', 1))
    except ValueError:
        quantita = 1
    utente_corrente = session['user']

    if not qr_code:
        flash("QR Code non valido o mancante!", "error")
        return redirect(url_for('index'))

    conn = get_db_connection()
    if not conn:
        flash("Errore di connessione al database", "error")
        return redirect(url_for('index'))
    try:
        cur = conn.cursor()
        cur.execute("UPDATE prodotti SET quantita = quantita + %s, modificato_da = %s WHERE qr_code = %s;", (quantita, utente_corrente, qr_code))
        if cur.rowcount == 0:
            flash("Prodotto non trovato!", "error")
        else:
            conn.commit()
            flash(f"Carico di {quantita} pz effettuato da {utente_corrente}!", "success")
        cur.close()
        conn.close()
    except Exception as e:
        flash(f"Errore durante il carico: {e}", "error")
    
    return redirect(url_for('gestisci_prodotto', qr_code=qr_code))

@app.route('/scarico', methods=['POST'])
def scarico():
    if 'user' not in session:
        return redirect(url_for('login'))

    qr_code = request.form.get('qr_code')
    try:
        quantita = int(request.form.get('quantita', 1))
    except ValueError:
        quantita = 1
    utente_corrente = session['user']

    if not qr_code:
        flash("QR Code non valido o mancante!", "error")
        return redirect(url_for('index'))

    conn = get_db_connection()
    if not conn:
        flash("Errore di connessione al database", "error")
        return redirect(url_for('index'))
    try:
        cur = conn.cursor()
        cur.execute("UPDATE prodotti SET quantita = GREATEST(0, quantita - %s), modificato_da = %s WHERE qr_code = %s;", (quantita, utente_corrente, qr_code))
        if cur.rowcount == 0:
            flash("Prodotto non trovato!", "error")
        else:
            conn.commit()
            flash(f"Scarico di {quantita} pz effettuato da {utente_corrente}!", "success")
        cur.close()
        conn.close()
    except Exception as e:
        flash(f"Errore durante lo scarico: {e}", "error")

    return redirect(url_for('gestisci_prodotto', qr_code=qr_code))

if _name_ == '_main_':
    app.run(host='0.0.0.0', port=5000, debug=True)
