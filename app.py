# ========================================================================
# Magazzino Web Application
# Copyright (c) 2026 Marco Pavan. All Rights Reserved.
# Designed & Developed by Marco Pavan
# ========================================================================

import os
import csv
import io
import psycopg2
from psycopg2.extras import RealDictCursor
from flask import Flask, render_template, request, redirect, url_for, flash, session, send_file
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "chiave-segreta-magazzino")

DATABASE_URL = os.environ.get("DATABASE_URL")

def get_db_connection():
    return psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)

def init_db():
    if not DATABASE_URL:
        print("DATABASE_URL non impostata!")
        return
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        cur.execute("""
            CREATE TABLE IF NOT EXISTS prodotti (
                id SERIAL PRIMARY KEY,
                qr_code VARCHAR(255) UNIQUE NOT NULL,
                nome VARCHAR(255) NOT NULL,
                sap VARCHAR(255),
                peso VARCHAR(255),
                quantita INT DEFAULT 0,
                posizione VARCHAR(255),
                magazzino_pesante INT DEFAULT 0,
                in_manutenzione BOOLEAN DEFAULT FALSE,
                cliente_manutenzione VARCHAR(255),
                quantita_manutenzione INT DEFAULT 0,
                data_spedizione VARCHAR(255),
                data_riconsegna VARCHAR(255),
                vettore VARCHAR(255),
                ordine_amministrativo BOOLEAN DEFAULT FALSE,
                note_manutenzione TEXT
            );
        """)
        
        cur.execute("""
            CREATE TABLE IF NOT EXISTS clienti (
                id SERIAL PRIMARY KEY,
                nome_azienda VARCHAR(255) NOT NULL,
                indirizzo VARCHAR(255),
                p_iva VARCHAR(255),
                telefono VARCHAR(255),
                email VARCHAR(255)
            );
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS utenti (
                id SERIAL PRIMARY KEY,
                username VARCHAR(255) UNIQUE NOT NULL,
                password VARCHAR(255) NOT NULL,
                is_admin INT DEFAULT 0,
                puo_vedere_manutenzione INT DEFAULT 1,
                puo_eliminare INT DEFAULT 0,
                puo_eliminare_storico INT DEFAULT 0,
                puo_gestire_documenti INT DEFAULT 1
            );
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS storico_manutenzioni (
                id SERIAL PRIMARY KEY,
                registrato_il TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                nome_prodotto VARCHAR(255),
                qr_code VARCHAR(255),
                sap VARCHAR(255),
                cliente VARCHAR(255),
                quantita INT,
                data_spedizione VARCHAR(255),
                data_riconsegna VARCHAR(255),
                vettore VARCHAR(255),
                ordine_amministrativo BOOLEAN DEFAULT FALSE,
                note TEXT
            );
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS cartelle (
                id SERIAL PRIMARY KEY,
                nome VARCHAR(255) NOT NULL,
                parent_id INT REFERENCES cartelle(id) ON DELETE CASCADE
            );
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS documenti (
                id SERIAL PRIMARY KEY,
                cartella_id INT REFERENCES cartelle(id) ON DELETE CASCADE,
                nome_file VARCHAR(255) NOT NULL,
                tipo_file VARCHAR(255),
                dati_file BYTEA NOT NULL,
                caricato_il TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        
        cur.execute("ALTER TABLE prodotti ADD COLUMN IF NOT EXISTS magazzino_pesante INT DEFAULT 0;")
        cur.execute("ALTER TABLE prodotti ADD COLUMN IF NOT EXISTS peso VARCHAR(255);")
        cur.execute("ALTER TABLE prodotti ADD COLUMN IF NOT EXISTS in_manutenzione BOOLEAN DEFAULT FALSE;")
        cur.execute("ALTER TABLE prodotti ADD COLUMN IF NOT EXISTS cliente_manutenzione VARCHAR(255);")
        cur.execute("ALTER TABLE prodotti ADD COLUMN IF NOT EXISTS quantita_manutenzione INT DEFAULT 0;")
        cur.execute("ALTER TABLE prodotti ADD COLUMN IF NOT EXISTS data_spedizione VARCHAR(255);")
        cur.execute("ALTER TABLE prodotti ADD COLUMN IF NOT EXISTS data_riconsegna VARCHAR(255);")
        cur.execute("ALTER TABLE prodotti ADD COLUMN IF NOT EXISTS vettore VARCHAR(255);")
        cur.execute("ALTER TABLE prodotti ADD COLUMN IF NOT EXISTS ordine_amministrativo BOOLEAN DEFAULT FALSE;")
        cur.execute("ALTER TABLE prodotti ADD COLUMN IF NOT EXISTS note_manutenzione TEXT;")
        cur.execute("ALTER TABLE storico_manutenzioni ADD COLUMN IF NOT EXISTS ordine_amministrativo BOOLEAN DEFAULT FALSE;")
        cur.execute("ALTER TABLE utenti ADD COLUMN IF NOT EXISTS puo_gestire_documenti INT DEFAULT 1;")

        cur.execute("SELECT * FROM utenti WHERE username = 'admin';")
        if not cur.fetchone():
            hashed_pw = generate_password_hash("admin")
            cur.execute("INSERT INTO utenti (username, password, is_admin, puo_vedere_manutenzione, puo_eliminare, puo_eliminare_storico, puo_gestire_documenti) VALUES (%s, %s, 1, 1, 1, 1, 1);", ('admin', hashed_pw))

        conn.commit()
        cur.close()
        conn.close()
        print("Database inizializzato con successo.")
    except Exception as e:
        print(f"Errore init_db: {e}")

init_db()

@app.before_request
def require_login():
    allowed_routes = ['login', 'registra', 'static']
    if request.endpoint and request.endpoint not in allowed_routes and 'username' not in session:
        return redirect(url_for('login'))

@app.route("/")
def index():
    prodotti = []
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT * FROM prodotti ORDER BY nome ASC;")
        tutti = cur.fetchall()
        cur.close()
        conn.close()
        
        for p in tutti:
            val_pesante = p.get('magazzino_pesante')
            is_pesante = (val_pesante == 1 or val_pesante == '1' or val_pesante is True or val_pesante == 1.0)
            if not is_pesante:
                prodotti.append(p)
    except Exception as e:
        print(f"Errore index: {e}")
    return render_template("index.html", prodotti=prodotti)

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")
        try:
            conn = get_db_connection()
            cur = conn.cursor()
            cur.execute("SELECT * FROM utenti WHERE username = %s;", (username,))
            user = cur.fetchone()
            cur.close()
            conn.close()
            
            if user and check_password_hash(user['password'], password):
                session['username'] = user['username']
                session['is_admin'] = user['is_admin']
                session['puo_vedere_manutenzione'] = user['puo_vedere_manutenzione']
                session['puo_eliminare'] = user['puo_eliminare']
                session['puo_eliminare_storico'] = user['puo_eliminare_storico']
                session['puo_gestire_documenti'] = user.get('puo_gestire_documenti', 1)
                return redirect(url_for('index'))
            else:
                flash("Credenziali non valide!", "error")
        except Exception as e:
            flash(f"Errore login: {e}", "error")
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route("/registra", methods=["GET", "POST"])
def registra():
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")
        if username and password:
            try:
                conn = get_db_connection()
                cur = conn.cursor()
                hashed_pw = generate_password_hash(password)
                cur.execute("INSERT INTO utenti (username, password) VALUES (%s, %s);", (username, hashed_pw))
                conn.commit()
                cur.close()
                conn.close()
                flash("Registrazione completata! Ora puoi effettuare il login.", "success")
                return redirect(url_for('login'))
            except Exception as e:
                flash("Username già esistente o errore di registrazione.", "error")
    return render_template("registra.html")

@app.route("/admin_utenti")
def admin_utenti():
    if not session.get('is_admin'):
        flash("Accesso negato.", "error")
        return redirect(url_for('index'))
    utenti = []
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT * FROM utenti ORDER BY username ASC;")
        utenti = cur.fetchall()
        cur.close()
        conn.close()
    except Exception as e:
        print(f"Errore admin: {e}")
    return render_template("admin_utenti.html", utenti=utenti)

@app.route("/toggle_permesso/<int:user_id>/<tipo>", methods=["POST"])
def toggle_permesso(user_id, tipo):
    if not session.get('is_admin'):
        return redirect(url_for('index'))
    conn = get_db_connection()
    cur = conn.cursor()
    if tipo == 'manutenzione':
        cur.execute("UPDATE utenti SET puo_vedere_manutenzione = NOT puo_vedere_manutenzione WHERE id = %s;", (user_id,))
    elif tipo == 'eliminazione':
        cur.execute("UPDATE utenti SET puo_eliminare = NOT puo_eliminare WHERE id = %s;", (user_id,))
    elif tipo == 'eliminazione_storico':
        cur.execute("UPDATE utenti SET puo_eliminare_storico = NOT puo_eliminare_storico WHERE id = %s;", (user_id,))
    elif tipo == 'documenti':
        cur.execute("UPDATE utenti SET puo_gestire_documenti = NOT puo_gestire_documenti WHERE id = %s;", (user_id,))
    conn.commit()
    cur.close()
    conn.close()
    return redirect(url_for('admin_utenti'))

@app.route("/reset_password/<int:user_id>", methods=["POST"])
def reset_password(user_id):
    if not session.get('is_admin'):
        return redirect(url_for('index'))
    nuova_password = request.form.get("nuova_password")
    if nuova_password:
        conn = get_db_connection()
        cur = conn.cursor()
        hashed_pw = generate_password_hash(nuova_password)
        cur.execute("UPDATE utenti SET password = %s WHERE id = %s;", (hashed_pw, user_id))
        conn.commit()
        cur.close()
        conn.close()
        flash("Password aggiornata con successo!", "success")
    return redirect(url_for('admin_utenti'))

@app.route("/elimina_utente/<int:user_id>", methods=["POST"])
def elimina_utente(user_id):
    if not session.get('is_admin'):
        return redirect(url_for('index'))
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM utenti WHERE id = %s AND username != 'admin';", (user_id,))
    conn.commit()
    cur.close()
    conn.close()
    return redirect(url_for('admin_utenti'))

@app.route("/clienti", methods=["GET", "POST"])
def clienti():
    conn = get_db_connection()
    cur = conn.cursor()
    if request.method == "POST":
        nome_azienda = request.form.get("nome_azienda")
        indirizzo = request.form.get("indirizzo", "")
        p_iva = request.form.get("p_iva", "")
        telefono = request.form.get("telefono", "")
        email = request.form.get("email", "")
        if nome_azienda:
            cur.execute(
                "INSERT INTO clienti (nome_azienda, indirizzo, p_iva, telefono, email) VALUES (%s, %s, %s, %s, %s);",
                (nome_azienda, indirizzo, p_iva, telefono, email)
            )
            conn.commit()
            flash("Cliente aggiunto con successo!", "success")
        return redirect(url_for("clienti"))
    
    cur.execute("SELECT * FROM clienti ORDER BY nome_azienda ASC;")
    lista_clienti = cur.fetchall()
    cur.close()
    conn.close()
    return render_template("clienti.html", clienti=lista_clienti)

@app.route("/aggiungi_cliente", methods=["POST"])
def aggiungi_cliente():
    return clienti()

@app.route("/elimina_cliente/<int:cliente_id>", methods=["POST"])
def elimina_cliente(cliente_id):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM clienti WHERE id = %s;", (cliente_id,))
    conn.commit()
    cur.close()
    conn.close()
    flash("Cliente eliminato con successo.", "success")
    return redirect(url_for("clienti"))

@app.route("/upload", methods=["GET", "POST"])
def upload():
    if request.method == "POST":
        file_csv = request.files.get("file_csv")
        if file_csv and file_csv.filename.endswith('.csv'):
            try:
                stream = io.TextIOWrapper(file_csv.stream, encoding="utf-8")
                reader = csv.reader(stream)
                conn = get_db_connection()
                cur = conn.cursor()
                count = 0
                for row in reader:
                    if len(row) >= 2:
                        qr_code = row[0].strip()
                        nome = row[1].strip()
                        sap = row[2].strip() if len(row) > 2 and row[2] else ""
                        quantita = int(row[3].strip()) if len(row) > 3 and row[3].strip().isdigit() else 0
                        posizione = row[4].strip() if len(row) > 4 and row[4] else ""
                        
                        cur.execute("""
                            INSERT INTO prodotti (qr_code, nome, sap, quantita, posizione)
                            VALUES (%s, %s, %s, %s, %s)
                            ON CONFLICT (qr_code)
                            DO UPDATE SET 
                                nome = EXCLUDED.nome,
                                sap = EXCLUDED.sap,
                                quantita = prodotti.quantita + EXCLUDED.quantita,
                                posizione = EXCLUDED.posizione;
                        """, (qr_code, nome, sap, quantita, posizione))
                        count += 1
                conn.commit()
                cur.close()
                conn.close()
                flash(f"Importati/Aggiornati con successo {count} articoli dal file CSV!", "success")
            except Exception as e:
                flash(f"Errore durante l'elaborazione del CSV: {e}", "error")
        else:
            flash("Si prega di caricare un file CSV valido.", "error")
        return redirect(url_for("upload"))
    return render_template("upload.html")

@app.route("/stampa_tutti_qr")
def stampa_tutti_qr():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM prodotti ORDER BY nome ASC;")
    prodotti = cur.fetchall()
    cur.close()
    conn.close()
    return render_template("stampa_tutti_qr.html", prodotti=prodotti)

@app.route("/stampa_singolo_qr/<qr_code>")
def stampa_singolo_qr(qr_code):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM prodotti WHERE qr_code = %s;", (qr_code,))
    prodotto = cur.fetchone()
    cur.close()
    conn.close()
    if not prodotto:
        flash("Prodotto non trovato.", "error")
        return redirect(url_for("index"))
    return render_template("stampa_singolo_qr.html", prodotto=prodotto)

@app.route("/magazzino_pesante")
def magazzino_pesante():
    prodotti = []
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT * FROM prodotti ORDER BY nome ASC;")
        tutti = cur.fetchall()
        cur.close()
        conn.close()
        
        for p in tutti:
            val = p.get('magazzino_pesante')
            if val == 1 or val == '1' or val is True or val == 1.0:
                prodotti.append(p)
    except Exception as e:
        print(f"Errore magazzino_pesante: {e}")
        prodotti = []
        
    return render_template("magazzino_pesante.html", prodotti=prodotti)

@app.route("/manutenzioni")
def manutenzioni():
    prodotti = []
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT * FROM prodotti ORDER BY nome ASC;")
        tutti = cur.fetchall()
        cur.close()
        conn.close()
        
        for p in tutti:
            val = p.get('in_manutenzione')
            if val == 1 or val == '1' or val is True or val == 1.0:
                prodotti.append(p)
    except Exception as e:
        print(f"Errore manutenzioni: {e}")
        prodotti = []
        
    return render_template("manutenzioni.html", prodotti=prodotti)

@app.route("/storico_manutenzioni")
def storico_manutenzioni():
    storico = []
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT * FROM storico_manutenzioni ORDER BY registrato_il DESC;")
        storico = cur.fetchall()
        cur.close()
        conn.close()
    except Exception as e:
        print(f"Errore storico: {e}")
    return render_template("storico_manutenzioni.html", storico=storico)

@app.route("/elimina_storico_manutenzione/<int:storico_id>", methods=["POST"])
def elimina_storico_manutenzione(storico_id):
    if not (session.get('is_admin') or session.get('puo_eliminare_storico')):
        flash("Permesso negato.", "error")
        return redirect(url_for('storico_manutenzioni'))
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM storico_manutenzioni WHERE id = %s;", (storico_id,))
    conn.commit()
    cur.close()
    conn.close()
    flash("Record eliminato dallo storico.", "success")
    return redirect(url_for('storico_manutenzioni'))

@app.route("/stampa_bolla/<qr_code>")
def stampa_bolla(qr_code):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM prodotti WHERE qr_code = %s;", (qr_code,))
    prodotto = cur.fetchone()
    cliente = None
    if prodotto and prodotto.get('cliente_manutenzione'):
        cur.execute("SELECT * FROM clienti WHERE nome_azienda = %s;", (prodotto['cliente_manutenzione'],))
        cliente = cur.fetchone()
    cur.close()
    conn.close()
    if not prodotto:
        flash("Prodotto non trovato.", "error")
        return redirect(url_for("index"))
    return render_template("bolla.html", prodotto=prodotto, cliente=cliente)

@app.route("/carico", methods=["GET", "POST"])
def carico():
    if request.method == "POST":
        qr_code = request.form.get("qr_code")
        quantita = int(request.form.get("quantita", 1))
        if qr_code:
            try:
                conn = get_db_connection()
                cur = conn.cursor()
                cur.execute("UPDATE prodotti SET quantita = quantita + %s WHERE qr_code = %s;", (quantita, qr_code))
                conn.commit()
                cur.close()
                conn.close()
                flash(f"Carico di {quantita} pz effettuato con successo!", "success")
                return redirect(url_for("gestisci_prodotto", qr_code=qr_code))
            except Exception as e:
                flash(f"Errore durante il carico: {e}", "error")
    return render_template("carico.html")

@app.route("/scarico", methods=["GET", "POST"])
def scarico():
    if request.method == "POST":
        qr_code = request.form.get("qr_code")
        quantita = int(request.form.get("quantita", 1))
        if qr_code:
            try:
                conn = get_db_connection()
                cur = conn.cursor()
                cur.execute("UPDATE prodotti SET quantita = GREATEST(0, quantita - %s) WHERE qr_code = %s;", (quantita, qr_code))
                conn.commit()
                cur.close()
                conn.close()
                flash(f"Scarico di {quantita} pz effettuato con successo!", "success")
                return redirect(url_for("gestisci_prodotto", qr_code=qr_code))
            except Exception as e:
                flash(f"Errore durante lo scarico: {e}", "error")
    return render_template("scarico.html")

# --- SCANNER GLOBALE (CERCA IN TUTTI I MAGAZZINI) ---
@app.route("/scanner_globale", methods=["GET", "POST"])
def scanner_globale():
    if request.method == "POST":
        qr_code = request.form.get("qr_code", "").strip()
        if qr_code:
            conn = get_db_connection()
            cur = conn.cursor()
            cur.execute("SELECT * FROM prodotti WHERE qr_code = %s;", (qr_code,))
            prodotto = cur.fetchone()
            cur.close()
            conn.close()
            
            if prodotto:
                return redirect(url_for("gestisci_prodotto", qr_code=qr_code))
            else:
                flash(f"Nessun articolo trovato con QR Code: {qr_code}", "error")
    return render_template("scanner_globale.html")

@app.route("/gestisci/<qr_code>")
def gestisci_prodotto(qr_code):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM prodotti WHERE qr_code = %s;", (qr_code,))
    prodotto = cur.fetchone()
    
    lista_clienti = []
    try:
        cur.execute("SELECT * FROM clienti ORDER BY nome_azienda ASC;")
        lista_clienti = cur.fetchall()
    except Exception:
        pass

    cur.close()
    conn.close()

    if not prodotto:
        flash("Prodotto non trovato nel sistema!", "error")
        return redirect(url_for("index"))

    return render_template("gestisci.html", prodotto=prodotto, clienti=lista_clienti)

@app.route("/aggiorna/<qr_code>", methods=["POST"])
def aggiorna_prodotto(qr_code):
    nome = request.form.get("nome")
    sap = request.form.get("sap", "")
    posizione = request.form.get("posizione", "")
    peso = request.form.get("peso", "")
    flag_sezione = 1 if request.form.get("magazzino_pesante") else 0
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("""
            UPDATE prodotti 
            SET nome = %s, sap = %s, posizione = %s, peso = %s, magazzino_pesante = %s
            WHERE qr_code = %s;
        """, (nome, sap, posizione, peso, flag_sezione, qr_code))
        conn.commit()
        cur.close()
        conn.close()
        flash("Articolo e dati magazzino aggiornati con successo!", "success")
    except Exception as e:
        flash(f"Errore durante l'aggiornamento: {e}", "error")
    return redirect(url_for("gestisci_prodotto", qr_code=qr_code))

@app.route("/aggiungi", methods=["POST"])
def aggiungi_prodotto():
    qr_code = request.form.get("qr_code")
    nome = request.form.get("nome")
    sap = request.form.get("sap", "")
    peso = request.form.get("peso", "")
    quantita = int(request.form.get("quantita", 0))
    posizione = request.form.get("posizione", "")
    flag_sezione = 1 if request.form.get("magazzino_pesante") else 0

    if not qr_code or not nome:
        flash("QR Code e Nome sono obbligatori!", "error")
        return redirect(url_for("index"))

    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO prodotti (qr_code, nome, sap, peso, quantita, posizione, magazzino_pesante)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (qr_code)
            DO UPDATE SET 
                quantita = prodotti.quantita + EXCLUDED.quantita,
                nome = EXCLUDED.nome,
                sap = EXCLUDED.sap,
                peso = EXCLUDED.peso,
                posizione = EXCLUDED.posizione,
                magazzino_pesante = EXCLUDED.magazzino_pesante;
            """,
            (qr_code, nome, sap, peso, quantita, posizione, flag_sezione)
        )
        conn.commit()
        cur.close()
        conn.close()
        flash("Prodotto salvato con successo!", "success")
    except Exception as e:
        flash(f"Errore nell'inserimento: {e}", "error")

    if flag_sezione == 1:
        return redirect(url_for("magazzino_pesante"))
    return redirect(url_for("index"))

@app.route("/manda_manutenzione/<qr_code>", methods=["POST"])
def manda_manutenzione(qr_code):
    cliente_manutenzione = request.form.get("cliente_manutenzione")
    quantita_manutenzione = int(request.form.get("quantita_manutenzione", 1))
    
    data_spedizione = request.form.get("data_spedizione", "").strip()
    if not data_spedizione:
        data_spedizione = None
        
    data_riconsegna = request.form.get("data_riconsegna", "").strip()
    if not data_riconsegna:
        data_riconsegna = None

    vettore = request.form.get("vettore", "").strip()
    ordine_amministrativo = True if request.form.get("ordine_amministrativo") else False
    note_manutenzione = request.form.get("note_manutenzione", "").strip()

    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        cur.execute("SELECT * FROM prodotti WHERE qr_code = %s;", (qr_code,))
        prod = cur.fetchone()
        
        cur.execute("""
            UPDATE prodotti 
            SET quantita = GREATEST(0, quantita - %s),
                in_manutenzione = TRUE,
                cliente_manutenzione = %s,
                quantita_manutenzione = %s,
                data_spedizione = %s,
                data_riconsegna = %s,
                vettore = %s,
                ordine_amministrativo = %s,
                note_manutenzione = %s
            WHERE qr_code = %s;
        """, (quantita_manutenzione, cliente_manutenzione, quantita_manutenzione, data_spedizione, data_riconsegna, vettore, ordine_amministrativo, note_manutenzione, qr_code))
        
        if prod:
            cur.execute("""
                INSERT INTO storico_manutenzioni (nome_prodotto, qr_code, sap, cliente, quantita, data_spedizione, data_riconsegna, vettore, ordine_amministrativo, note)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s);
            """, (prod['nome'], qr_code, prod['sap'], cliente_manutenzione, quantita_manutenzione, data_spedizione, data_riconsegna, vettore, ordine_amministrativo, note_manutenzione))

        conn.commit()
        cur.close()
        conn.close()
        flash("Articolo inviato in manutenzione e registrato nello storico con successo!", "success")
    except Exception as e:
        flash(f"Errore: {e}", "error")
    return redirect(url_for("gestisci_prodotto", qr_code=qr_code))

@app.route("/ripristina_magazzino/<qr_code>", methods=["POST"])
def ripristina_magazzino(qr_code):
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("""
            UPDATE prodotti 
            SET quantita = quantita + quantita_manutenzione,
                in_manutenzione = FALSE,
                cliente_manutenzione = NULL,
                quantita_manutenzione = 0,
                data_spedizione = NULL,
                data_riconsegna = NULL,
                vettore = NULL,
                ordine_amministrativo = FALSE,
                note_manutenzione = NULL
            WHERE qr_code = %s;
        """, (qr_code,))
        conn.commit()
        cur.close()
        conn.close()
        flash("Articolo rientrato in magazzino con successo!", "success")
    except Exception as e:
        flash(f"Errore: {e}", "error")
    return redirect(url_for("gestisci_prodotto", qr_code=qr_code))

@app.route("/elimina", methods=["POST"])
def elimina_prodotto():
    qr_code = request.form.get("qr_code")
    if not qr_code:
        flash("QR Code non valido per l'eliminazione!", "error")
        return redirect(url_for("index"))

    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("DELETE FROM prodotti WHERE qr_code = %s;", (qr_code,))
        conn.commit()
        cur.close()
        conn.close()
        flash("Articolo eliminato dal magazzino con successo!", "success")
    except Exception as e:
        flash(f"Errore durante l'eliminazione: {e}", "error")

    return redirect(url_for("index"))

# --- GESTIONE DOCUMENTALE CON PERMESSI ---
@app.route("/documenti", defaults={"cartella_id": None}, methods=["GET", "POST"])
@app.route("/documenti/<int:cartella_id>", methods=["GET", "POST"])
def documenti(cartella_id):
    if not (session.get('is_admin') or session.get('puo_gestire_documenti')):
        flash("Accesso ai documenti non autorizzato.", "error")
        return redirect(url_for('index'))

    conn = get_db_connection()
    cur = conn.cursor()

    cartella_corrente = None
    percorso_breadcrumb = []

    if cartella_id:
        cur.execute("SELECT * FROM cartelle WHERE id = %s;", (cartella_id,))
        cartella_corrente = cur.fetchone()
        
        curr = cartella_corrente
        while curr:
            percorso_breadcrumb.insert(0, curr)
            if curr['parent_id']:
                cur.execute("SELECT * FROM cartelle WHERE id = %s;", (curr['parent_id'],))
                curr = cur.fetchone()
            else:
                curr = None

    if request.method == "POST":
        azione = request.form.get("azione")
        
        if azione == "crea_cartella":
            nome_cartella = request.form.get("nome_cartella")
            if nome_cartella:
                cur.execute("INSERT INTO cartelle (nome, parent_id) VALUES (%s, %s);", (nome_cartella, cartella_id))
                conn.commit()
                flash("Cartella creata con successo!", "success")
                
        elif azione == "carica_file":
            file_caricato = request.files.get("file_caricato")
            if file_caricato and file_caricato.filename:
                nome_file = file_caricato.filename
                tipo_file = file_caricato.mimetype
                dati_file = file_caricato.read()
                
                cur.execute("""
                    INSERT INTO documenti (cartella_id, nome_file, tipo_file, dati_file)
                    VALUES (%s, %s, %s, %s);
                """, (cartella_id, nome_file, tipo_file, dati_file))
                conn.commit()
                flash("File caricato con successo!", "success")
                
        cur.close()
        conn.close()
        return redirect(url_for("documenti", cartella_id=cartella_id) if cartella_id else url_for("documenti"))

    if cartella_id:
        cur.execute("SELECT * FROM cartelle WHERE parent_id = %s ORDER BY nome ASC;", (cartella_id,))
    else:
        cur.execute("SELECT * FROM cartelle WHERE parent_id IS NULL ORDER BY nome ASC;")
    sottocartelle = cur.fetchall()

    if cartella_id:
        cur.execute("SELECT id, nome_file, tipo_file, caricato_il FROM documenti WHERE cartella_id = %s ORDER BY nome_file ASC;", (cartella_id,))
    else:
        cur.execute("SELECT id, nome_file, tipo_file, caricato_il FROM documenti WHERE cartella_id IS NULL ORDER BY nome_file ASC;")
    lista_file = cur.fetchall()

    cur.close()
    conn.close()

    return render_template("documenti.html", 
                           cartella_corrente=cartella_corrente, 
                           sottocartelle=sottocartelle, 
                           lista_file=lista_file, 
                           percorso_breadcrumb=percorso_breadcrumb)

@app.route("/scarica_file/<int:file_id>")
def scarica_file(file_id):
    if not (session.get('is_admin') or session.get('puo_gestire_documenti')):
        flash("Accesso negato.", "error")
        return redirect(url_for('index'))

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT nome_file, tipo_file, dati_file FROM documenti WHERE id = %s;", (file_id,))
    file_data = cur.fetchone()
    cur.close()
    conn.close()

    if file_data:
        return send_file(
            io.BytesIO(file_data['dati_file']),
            mimetype=file_data['tipo_file'],
            as_attachment=True,
            download_name=file_data['nome_file']
        )
    flash("File non trovato.", "error")
    return redirect(url_for("documenti"))

@app.route("/elimina_cartella/<int:cartella_id>", methods=["POST"])
def elimina_cartella(cartella_id):
    if not session.get('is_admin'):
        flash("Solo l'amministratore può eliminare le cartelle.", "error")
        return redirect(url_for('documenti'))

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT parent_id FROM cartelle WHERE id = %s;", (cartella_id,))
    res = cur.fetchone()
    parent_id = res['parent_id'] if res else None

    cur.execute("DELETE FROM cartelle WHERE id = %s;", (cartella_id,))
    conn.commit()
    cur.close()
    conn.close()
    flash("Cartella eliminata con successo.", "success")
    
    if parent_id:
        return redirect(url_for("documenti", cartella_id=parent_id))
    return redirect(url_for("documenti"))

@app.route("/elimina_file/<int:file_id>", methods=["POST"])
def elimina_file(file_id):
    if not session.get('is_admin'):
        flash("Solo l'amministratore può eliminare i documenti.", "error")
        return redirect(url_for('documenti'))

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT cartella_id FROM documenti WHERE id = %s;", (file_id,))
    res = cur.fetchone()
    cartella_id = res['cartella_id'] if res else None

    cur.execute("DELETE FROM documenti WHERE id = %s;", (file_id,))
    conn.commit()
    cur.close()
    conn.close()
    flash("File eliminato con successo.", "success")
    
    if cartella_id:
        return redirect(url_for("documenti", cartella_id=cartella_id))
    return redirect(url_for("documenti"))

if _name_ == "__main__":
    app.run(debug=True)
