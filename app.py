import os
import csv
import io
import psycopg2
from psycopg2.extras import RealDictCursor
from flask import Flask, render_template, request, redirect, url_for, flash, session
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
        
        # Tabella Prodotti
        cur.execute("""
            CREATE TABLE IF NOT EXISTS prodotti (
                id SERIAL PRIMARY KEY,
                qr_code VARCHAR(255) UNIQUE NOT NULL,
                nome VARCHAR(255) NOT NULL,
                sap VARCHAR(255),
                peso VARCHAR(255),
                quantita INT DEFAULT 0,
                posizione VARCHAR(255),
                magazzino_composizione INT DEFAULT 0,
                in_manutenzione INT DEFAULT 0,
                cliente_manutenzione VARCHAR(255),
                quantita_manutenzione INT DEFAULT 0,
                data_spedizione VARCHAR(255),
                data_riconsegna VARCHAR(255),
                vettore VARCHAR(255),
                ordine_amministrativo INT DEFAULT 0,
                note_manutenzione TEXT
            );
        """)
        
        # Tabella Clienti
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

        # Tabella Utenti
        cur.execute("""
            CREATE TABLE IF NOT EXISTS utenti (
                id SERIAL PRIMARY KEY,
                username VARCHAR(255) UNIQUE NOT NULL,
                password VARCHAR(255) NOT NULL,
                is_admin INT DEFAULT 0,
                puo_vedere_manutenzione INT DEFAULT 1,
                puo_eliminare INT DEFAULT 0,
                puo_eliminare_storico INT DEFAULT 0
            );
        """)

        # Tabella Storico Manutenzioni
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
                ordine_amministrativo INT DEFAULT 0,
                note TEXT
            );
        """)
        
        # Aggiunta sicura delle colonne se mancanti
        cur.execute("ALTER TABLE prodotti ADD COLUMN IF NOT EXISTS magazzino_composizione INT DEFAULT 0;")
        cur.execute("ALTER TABLE prodotti ADD COLUMN IF NOT EXISTS in_manutenzione INT DEFAULT 0;")
        cur.execute("ALTER TABLE prodotti ADD COLUMN IF NOT EXISTS cliente_manutenzione VARCHAR(255);")
        cur.execute("ALTER TABLE prodotti ADD COLUMN IF NOT EXISTS quantita_manutenzione INT DEFAULT 0;")
        cur.execute("ALTER TABLE prodotti ADD COLUMN IF NOT EXISTS data_spedizione VARCHAR(255);")
        cur.execute("ALTER TABLE prodotti ADD COLUMN IF NOT EXISTS data_riconsegna VARCHAR(255);")
        cur.execute("ALTER TABLE prodotti ADD COLUMN IF NOT EXISTS vettore VARCHAR(255);")
        cur.execute("ALTER TABLE prodotti ADD COLUMN IF NOT EXISTS ordine_amministrativo INT DEFAULT 0;")
        cur.execute("ALTER TABLE prodotti ADD COLUMN IF NOT EXISTS note_manutenzione TEXT;")

        # Admin predefinito
        cur.execute("SELECT * FROM utenti WHERE username = 'admin';")
        if not cur.fetchone():
            hashed_pw = generate_password_hash("admin")
            cur.execute("INSERT INTO utenti (username, password, is_admin, puo_vedere_manutenzione, puo_eliminare, puo_eliminare_storico) VALUES (%s, %s, 1, 1, 1, 1);", ('admin', hashed_pw))

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
        cur.execute("SELECT * FROM prodotti WHERE magazzino_composizione != 1 OR magazzino_composizione IS NULL ORDER BY nome ASC;")
        prodotti = cur.fetchall()
        cur.close()
        conn.close()
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

@app.route("/lista_clienti")
def lista_clienti():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM clienti ORDER BY nome_azienda ASC;")
    lista_clienti = cur.fetchall()
    cur.close()
    conn.close()
    return render_template("lista_clienti.html", clienti=lista_clienti)

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

@app.route("/pagina_upload", methods=["GET", "POST"])
def pagina_upload():
    return upload()

@app.route("/stampa_tutti_qr")
def stampa_tutti_qr():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM prodotti ORDER BY nome ASC;")
    prodotti = cur.fetchall()
    cur.close()
    conn.close()
    return render_template("stampa_tutti_qr.html", prodotti=prodotti)

@app.route("/magazzino_composizione")
def magazzino_composizione():
    prodotti = []
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT * FROM prodotti WHERE magazzino_composizione = 1 ORDER BY nome ASC;")
        prodotti = cur.fetchall()
        cur.close()
        conn.close()
    except Exception as e:
        print(f"Errore magazzino_composizione: {e}")
    return render_template("magazzino_composizione.html", prodotti=prodotti)

@app.route("/manutenzioni")
def manutenzioni():
    prodotti = []
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT * FROM prodotti WHERE in_manutenzione = 1 ORDER BY nome ASC;")
        prodotti = cur.fetchall()
        cur.close()
        conn.close()
    except Exception as e:
        print(f"Errore manutenzioni: {e}")
    return render_template("manutenzioni.html", prodotti=prodotti)

@app.route("/lista_manutenzioni")
def lista_manutenzioni():
    return redirect(url_for("manutenzioni"))

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

@app.route("/bolla")
def bolla():
    return render_template("bolla.html")

@app.route("/registra_pagina", methods=["GET", "POST"])
def registra_pagina():
    return render_template("registra.html")

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

@app.route("/aggiungi", methods=["POST"])
def aggiungi_prodotto():
    qr_code = request.form.get("qr_code")
    nome = request.form.get("nome")
    sap = request.form.get("sap", "")
    peso = request.form.get("peso", "")
    quantita = int(request.form.get("quantita", 0))
    posizione = request.form.get("posizione", "")
    flag_sezione = 1 if request.form.get("magazzino_composizione") else 0

    if not qr_code or not nome:
        flash("QR Code e Nome sono obbligatori!", "error")
        return redirect(url_for("index"))

    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO prodotti (qr_code, nome, sap, peso, quantita, posizione, magazzino_composizione)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (qr_code)
            DO UPDATE SET 
                quantita = prodotti.quantita + EXCLUDED.quantita,
                nome = EXCLUDED.nome,
                sap = EXCLUDED.sap,
                peso = EXCLUDED.peso,
                posizione = EXCLUDED.posizione,
                magazzino_composizione = EXCLUDED.magazzino_composizione;
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
        return redirect(url_for("magazzino_composizione"))
    return redirect(url_for("index"))

@app.route("/manda_manutenzione/<qr_code>", methods=["POST"])
def manda_manutenzione(qr_code):
    cliente_manutenzione = request.form.get("cliente_manutenzione")
    quantita_manutenzione = int(request.form.get("quantita_manutenzione", 1))
    data_spedizione = request.form.get("data_spedizione", "")
    data_riconsegna = request.form.get("data_riconsegna", "")
    vettore = request.form.get("vettore", "")
    ordine_amministrativo = 1 if request.form.get("ordine_amministrativo") else 0
    note_manutenzione = request.form.get("note_manutenzione", "")

    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        cur.execute("SELECT * FROM prodotti WHERE qr_code = %s;", (qr_code,))
        prod = cur.fetchone()
        
        cur.execute("""
            UPDATE prodotti 
            SET quantita = GREATEST(0, quantita - %s),
                in_manutenzione = 1,
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
                in_manutenzione = 0,
                cliente_manutenzione = NULL,
                quantita_manutenzione = 0,
                data_spedizione = NULL,
                data_riconsegna = NULL,
                vettore = NULL,
                ordine_amministrativo = 0,
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

if __name__ == "_main_":
    app.run(debug=True)
