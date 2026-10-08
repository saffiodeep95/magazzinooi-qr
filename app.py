import os
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
        return
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS utenti (
                id SERIAL PRIMARY KEY,
                username VARCHAR(255) UNIQUE NOT NULL,
                password TEXT NOT NULL,
                is_admin BOOLEAN DEFAULT FALSE
            );
            CREATE TABLE IF NOT EXISTS prodotti (
                id SERIAL PRIMARY KEY,
                qr_code VARCHAR(255) UNIQUE NOT NULL,
                nome VARCHAR(255) NOT NULL,
                quantita INT DEFAULT 0,
                posizione VARCHAR(255),
                sap VARCHAR(255),
                stato VARCHAR(50) DEFAULT 'Disponibile',
                cliente_manutenzione VARCHAR(255),
                note_manutenzione TEXT
            );
            CREATE TABLE IF NOT EXISTS clienti (
                id SERIAL PRIMARY KEY,
                nome_azienda VARCHAR(255) UNIQUE NOT NULL,
                indirizzo TEXT,
                p_iva VARCHAR(50),
                telefono VARCHAR(50),
                email VARCHAR(100)
            );
        """)
        # Crea un utente admin predefinito se non esiste
        admin_pass = generate_password_hash("admin123")
        cur.execute("""
            INSERT INTO utenti (username, password, is_admin) 
            VALUES ('admin', %s, TRUE)
            ON CONFLICT (username) DO NOTHING;
        """, (admin_pass,))
        
        conn.commit()
        cur.close()
        conn.close()
    except Exception as e:
        print(f"Errore inizializzazione DB: {e}")

init_db()

# --- HOME (index.html) ---
@app.route("/")
def index():
    prodotti = []
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT * FROM prodotti ORDER BY id DESC;")
        prodotti = cur.fetchall()
        cur.close()
        conn.close()
    except Exception as e:
        print(f"Errore caricamento index: {e}")
    return render_template("index.html", prodotti=prodotti)

# --- LOGIN & AUTH ---
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        try:
            conn = get_db_connection()
            cur = conn.cursor()
            cur.execute("SELECT * FROM utenti WHERE username = %s;", (username,))
            user = cur.fetchone()
            cur.close()
            conn.close()
            
            if user and check_password_hash(user["password"], password):
                session["username"] = user["username"]
                session["is_admin"] = user["is_admin"]
                return redirect(url_for("index"))
            else:
                flash("Credenziali non valide.", "error")
        except Exception as e:
            print(f"Errore login: {e}")
            flash("Errore durante il login.", "error")
            
    return render_template("login.html")

@app.route("/registra", methods=["GET", "POST"])
def registra():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        if username and password:
            try:
                hashed = generate_password_hash(password)
                conn = get_db_connection()
                cur = conn.cursor()
                cur.execute("INSERT INTO utenti (username, password, is_admin) VALUES (%s, %s, FALSE);", (username, hashed))
                conn.commit()
                cur.close()
                conn.close()
                flash("Registrazione avvenuta con successo!", "success")
                return redirect(url_for("login"))
            except Exception as e:
                flash(f"Errore durante la registrazione: {e}", "error")
    return render_template("registra.html")

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

# --- GESTIONE SINGOLO PRODOTTO (gestisci.html) ---
@app.route("/gestisci/<qr_code>")
def gestisci_prodotto(qr_code):
    prodotto = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT * FROM prodotti WHERE qr_code = %s;", (qr_code,))
        prodotto = cur.fetchone()
        cur.close()
        conn.close()
    except Exception as e:
        print(f"Errore gestisci: {e}")

    if not prodotto:
        flash("Prodotto non trovato nel sistema!", "error")
        return redirect(url_for("index"))

    return render_template("gestisci.html", prodotto=prodotto)

# --- AGGIUNGI / CREA PRODOTTO ---
@app.route("/aggiungi", methods=["POST"])
def aggiungi_prodotto():
    qr_code = request.form.get("qr_code", "").strip()
    nome = request.form.get("nome", "").strip()
    sap = request.form.get("sap", "").strip()
    quantita = int(request.form.get("quantita", 1) or 1)
    posizione = request.form.get("posizione", "").strip()

    if qr_code and nome:
        try:
            conn = get_db_connection()
            cur = conn.cursor()
            cur.execute(
                """
                INSERT INTO prodotti (qr_code, nome, sap, quantita, posizione, stato)
                VALUES (%s, %s, %s, %s, %s, 'Disponibile')
                ON CONFLICT (qr_code)
                DO UPDATE SET nome = EXCLUDED.nome,
                              sap = EXCLUDED.sap,
                              quantita = EXCLUDED.quantita,
                              posizione = EXCLUDED.posizione;
                """,
                (qr_code, nome, sap if sap else None, quantita, posizione if posizione else None)
            )
            conn.commit()
            cur.close()
            conn.close()
            flash("Prodotto salvato con successo!", "success")
        except Exception as e:
            flash(f"Errore nell'inserimento: {e}", "error")

    return redirect(url_for("index"))

# --- CARICO (carico.html) ---
@app.route("/carico", methods=["GET", "POST"])
def carico():
    if request.method == "POST":
        qr_code = request.form.get("qr_code", "").strip()
        quantita = int(request.form.get("quantita", 1) or 1)
        if qr_code:
            try:
                conn = get_db_connection()
                cur = conn.cursor()
                cur.execute("UPDATE prodotti SET quantita = quantita + %s WHERE qr_code = %s;", (quantita, qr_code))
                conn.commit()
                cur.close()
                conn.close()
                flash(f"Carico di {quantita} pz effettuato!", "success")
                return redirect(url_for("gestisci_prodotto", qr_code=qr_code))
            except Exception as e:
                flash(f"Errore durante il carico: {e}", "error")
    return render_template("carico.html")

# --- SCARICO (scarico.html) ---
@app.route("/scarico", methods=["GET", "POST"])
def scarico():
    if request.method == "POST":
        qr_code = request.form.get("qr_code", "").strip()
        quantita = int(request.form.get("quantita", 1) or 1)
        if qr_code:
            try:
                conn = get_db_connection()
                cur = conn.cursor()
                cur.execute("UPDATE prodotti SET quantita = GREATEST(0, quantita - %s) WHERE qr_code = %s;", (quantita, qr_code))
                conn.commit()
                cur.close()
                conn.close()
                flash(f"Scarico di {quantita} pz effettuato!", "success")
                return redirect(url_for("gestisci_prodotto", qr_code=qr_code))
            except Exception as e:
                flash(f"Errore durante lo scarico: {e}", "error")
    return render_template("scarico.html")

# --- ELIMINA PRODOTTO ---
@app.route("/elimina", methods=["POST"])
def elimina_prodotto():
    qr_code = request.form.get("qr_code", "").strip()
    if qr_code:
        try:
            conn = get_db_connection()
            cur = conn.cursor()
            cur.execute("DELETE FROM prodotti WHERE qr_code = %s;", (qr_code,))
            conn.commit()
            cur.close()
            conn.close()
            flash("Articolo eliminato con successo!", "success")
        except Exception as e:
            flash(f"Errore durante l'eliminazione: {e}", "error")
    return redirect(url_for("index"))

# --- SEZIONE CLIENTI (clienti.html e lista_clienti.html) ---
@app.route("/clienti")
@app.route("/lista_clienti")
def clienti():
    clienti_list = []
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT * FROM clienti ORDER BY nome_azienda ASC;")
        clienti_list = cur.fetchall()
        cur.close()
        conn.close()
    except Exception as e:
        print(f"Errore clienti: {e}")
    
    # Se esiste specifica preferenza, gestisce entrambi i template o usa clienti.html come standard
    return render_template("clienti.html", clienti=clienti_list)

@app.route("/aggiungi_cliente", methods=["POST"])
def aggiungi_cliente():
    nome_azienda = request.form.get("nome_azienda", "").strip()
    indirizzo = request.form.get("indirizzo", "")
    p_iva = request.form.get("p_iva", "")
    telefono = request.form.get("telefono", "")
    email = request.form.get("email", "")

    if nome_azienda:
        try:
            conn = get_db_connection()
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO clienti (nome_azienda, indirizzo, p_iva, telefono, email)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (nome_azienda) DO UPDATE 
                SET indirizzo = EXCLUDED.indirizzo, p_iva = EXCLUDED.p_iva, telefono = EXCLUDED.telefono, email = EXCLUDED.email;
            """, (nome_azienda, indirizzo, p_iva, telefono, email))
            conn.commit()
            cur.close()
            conn.close()
            flash("Cliente salvato con successo!", "success")
        except Exception as e:
            flash(f"Errore salvataggio cliente: {e}", "error")

    return redirect(url_for("clienti"))

# --- SEZIONE MANUTENZIONI (manutenzioni.html) ---
@app.route("/manutenzioni")
@app.route("/lista_manutenzioni")
def lista_manutenzioni():
    prodotti_maint = []
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT * FROM prodotti WHERE stato = 'In Manutenzione' ORDER BY id DESC;")
        prodotti_maint = cur.fetchall()
        cur.close()
        conn.close()
    except Exception as e:
        print(f"Errore manutenzioni: {e}")
    
    return render_template("manutenzioni.html", prodotti=prodotti_maint)

if __name__ == "_main_":
    app.run(host="0.0.0.0", port=5000, debug=True)
