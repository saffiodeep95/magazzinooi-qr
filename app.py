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
        
        # Crea le tabelle se non esistono
        cur.execute("""
            CREATE TABLE IF NOT EXISTS utenti (
                id SERIAL PRIMARY KEY,
                username VARCHAR(255) UNIQUE NOT NULL,
                password TEXT NOT NULL,
                is_admin BOOLEAN DEFAULT FALSE,
                puo_vedere_manutenzione BOOLEAN DEFAULT FALSE
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
                quantita_manutenzione INT DEFAULT 1,
                data_spedizione DATE,
                data_riconsegna DATE,
                ordine_amministrativo BOOLEAN DEFAULT FALSE,
                vettore VARCHAR(255),
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
        
        # Aggiunge la colonna 'puo_vedere_manutenzione' se la tabella utenti esisteva già senza di essa
        cur.execute("""
            ALTER TABLE utenti ADD COLUMN IF NOT EXISTS puo_vedere_manutenzione BOOLEAN DEFAULT FALSE;
        """)

        # Crea utente admin di default con permessi pieni
        admin_pass = generate_password_hash("admin123")
        cur.execute("""
            INSERT INTO utenti (username, password, is_admin, puo_vedere_manutenzione) 
            VALUES ('admin', %s, TRUE, TRUE)
            ON CONFLICT (username) DO UPDATE 
            SET is_admin = TRUE, puo_vedere_manutenzione = TRUE;
        """, (admin_pass,))
        
        conn.commit()
        cur.close()
        conn.close()
        print("Database inizializzato e aggiornato con successo.")
    except Exception as e:
        print(f"Errore DB Init: {e}")

init_db()

# --- AUTENTICAZIONE ---
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
                session["is_admin"] = bool(user.get("is_admin", False))
                session["puo_vedere_manutenzione"] = bool(user.get("puo_vedere_manutenzione", False))
                return redirect(url_for("index"))
            else:
                flash("Credenziali non valide.", "error")
        except Exception as e:
            flash(f"Errore durante il login: {e}", "error")
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

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
                cur.execute("INSERT INTO utenti (username, password, is_admin, puo_vedere_manutenzione) VALUES (%s, %s, FALSE, FALSE);", (username, hashed))
                conn.commit()
                cur.close()
                conn.close()
                flash("Registrazione avvenuta con successo! In attesa di abilitazione dall'Admin.", "success")
                return redirect(url_for("login"))
            except Exception as e:
                flash(f"Errore: utente già esistente.", "error")
    return render_template("registra.html")

# --- PANNELLO ADMIN UTENTI E PERMESSI ---
@app.route("/admin/utenti")
def admin_utenti():
    if not session.get("is_admin"):
        flash("Accesso negato: area riservata agli amministratori.", "error")
        return redirect(url_for("index"))
    
    utenti_list = []
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT * FROM utenti ORDER BY id ASC;")
        utenti_list = cur.fetchall()
        cur.close()
        conn.close()
    except Exception as e:
        print(f"Errore utenti: {e}")
    return render_template("admin_utenti.html", utenti=utenti_list)

@app.route("/admin/toggle_permesso/<int:user_id>", methods=["POST"])
def toggle_permesso(user_id):
    if not session.get("is_admin"):
        flash("Accesso negato.", "error")
        return redirect(url_for("index"))
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("UPDATE utenti SET puo_vedere_manutenzione = NOT puo_vedere_manutenzione WHERE id = %s;", (user_id,))
        conn.commit()
        cur.close()
        conn.close()
        flash("Permessi utente aggiornati con successo.", "success")
    except Exception as e:
        flash(f"Errore aggiornamento permessi: {e}", "error")
    return redirect(url_for("admin_utenti"))

@app.route("/admin/elimina_utente/<int:user_id>", methods=["POST"])
def elimina_utente(user_id):
    if not session.get("is_admin"):
        flash("Accesso negato.", "error")
        return redirect(url_for("index"))
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("DELETE FROM utenti WHERE id = %s;", (user_id,))
        conn.commit()
        cur.close()
        conn.close()
        flash("Utente eliminato con successo.", "success")
    except Exception as e:
        flash(f"Errore eliminazione utente: {e}", "error")
    return redirect(url_for("admin_utenti"))

# --- MAGAZZINO ---
@app.route("/")
def index():
    if "username" not in session:
        return redirect(url_for("login"))
    prodotti = []
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT * FROM prodotti ORDER BY id DESC;")
        prodotti = cur.fetchall()
        cur.close()
        conn.close()
    except Exception as e:
        print(f"Errore index: {e}")
    return render_template("index.html", prodotti=prodotti)

@app.route("/gestisci/<qr_code>")
def gestisci_prodotto(qr_code):
    if "username" not in session:
        return redirect(url_for("login"))
    prodotto = None
    clienti_list = []
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT * FROM prodotti WHERE qr_code = %s;", (qr_code,))
        prodotto = cur.fetchone()
        cur.execute("SELECT * FROM clienti ORDER BY nome_azienda ASC;")
        clienti_list = cur.fetchall()
        cur.close()
        conn.close()
    except Exception as e:
        print(f"Errore gestisci: {e}")

    if not prodotto:
        flash("Prodotto non trovato nel sistema!", "error")
        return redirect(url_for("index"))

    return render_template("gestisci.html", prodotto=prodotto, clienti=clienti_list)

@app.route("/aggiungi", methods=["POST"])
def aggiungi_prodotto():
    if "username" not in session:
        return redirect(url_for("login"))
    qr_code = request.form.get("qr_code")
    nome = request.form.get("nome")
    sap = request.form.get("sap", "")
    quantita = int(request.form.get("quantita", 0) or 0)
    posizione = request.form.get("posizione", "")

    if qr_code and nome:
        try:
            conn = get_db_connection()
            cur = conn.cursor()
            cur.execute(
                """
                INSERT INTO prodotti (qr_code, nome, sap, quantita, posizione, stato)
                VALUES (%s, %s, %s, %s, %s, 'Disponibile')
                ON CONFLICT (qr_code)
                DO UPDATE SET quantita = prodotti.quantita + EXCLUDED.quantita,
                              nome = EXCLUDED.nome,
                              sap = EXCLUDED.sap,
                              posizione = EXCLUDED.posizione;
                """,
                (qr_code, nome, sap, quantita, posizione)
            )
            conn.commit()
            cur.close()
            conn.close()
            flash("Prodotto aggiunto o aggiornato con successo!", "success")
        except Exception as e:
            flash(f"Errore nell'inserimento: {e}", "error")

    return redirect(url_for("index"))

@app.route("/carico", methods=["GET", "POST"])
def carico():
    if "username" not in session:
        return redirect(url_for("login"))
    if request.method == "POST":
        qr_code = request.form.get("qr_code")
        quantita = int(request.form.get("quantita", 1) or 1)
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
    if "username" not in session:
        return redirect(url_for("login"))
    if request.method == "POST":
        qr_code = request.form.get("qr_code")
        quantita = int(request.form.get("quantita", 1) or 1)
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

@app.route("/elimina", methods=["POST"])
def elimina_prodotto():
    if "username" not in session:
        return redirect(url_for("login"))
    
    if not session.get("is_admin"):
        flash("Accesso negato: solo l'amministratore può eliminare i prodotti dal magazzino.", "error")
        return redirect(url_for("index"))

    qr_code = request.form.get("qr_code")
    if qr_code:
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

@app.route("/stato_manutenzione/<qr_code>", methods=["POST"])
def stato_manutenzione(qr_code):
    if "username" not in session:
        return redirect(url_for("login"))
    
    if not session.get("is_admin") and not session.get("puo_vedere_manutenzione"):
        flash("Non hai i permessi necessari per modificare o gestire le manutenzioni.", "error")
        return redirect(url_for("gestisci_prodotto", qr_code=qr_code))

    nuovo_stato = request.form.get("stato", "In Manutenzione")
    cliente = request.form.get("cliente_manutenzione", "")
    qta_maint = int(request.form.get("quantita_manutenzione", 1) or 1)
    data_spedizione = request.form.get("data_spedizione") or None
    data_riconsegna = request.form.get("data_riconsegna") or None
    ordine_amministrativo = True if request.form.get("ordine_amministrativo") == "on" else False
    vettore = request.form.get("vettore", "")
    note = request.form.get("note_manutenzione", "")

    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("""
            UPDATE prodotti 
            SET stato = %s, 
                cliente_manutenzione = %s, 
                quantita_manutenzione = %s,
                data_spedizione = %s, 
                data_riconsegna = %s, 
                ordine_amministrativo = %s,
                vettore = %s,
                note_manutenzione = %s
            WHERE qr_code = %s;
        """, (nuovo_stato, cliente if cliente else None, qta_maint, data_spedizione, data_riconsegna, ordine_amministrativo, vettore if vettore else None, note, qr_code))
        conn.commit()
        cur.close()
        conn.close()
        flash("Dati manutenzione aggiornati con successo!", "success")
    except Exception as e:
        flash(f"Errore aggiornamento manutenzione: {e}", "error")
    return redirect(url_for("gestisci_prodotto", qr_code=qr_code))

@app.route("/bolla/<qr_code>")
def stampa_bolla(qr_code):
    if "username" not in session:
        return redirect(url_for("login"))
    prodotto = None
    cliente_info = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT * FROM prodotti WHERE qr_code = %s;", (qr_code,))
        prodotto = cur.fetchone()
        if prodotto and prodotto["cliente_manutenzione"]:
            cur.execute("SELECT * FROM clienti WHERE nome_azienda = %s;", (prodotto["cliente_manutenzione"],))
            cliente_info = cur.fetchone()
        cur.close()
        conn.close()
    except Exception as e:
        print(f"Errore bolla: {e}")

    if not prodotto:
        flash("Prodotto non trovato per la stampa della bolla.", "error")
        return redirect(url_for("index"))

    return render_template("bolla.html", prodotto=prodotto, cliente=cliente_info)

@app.route("/clienti")
@app.route("/lista_clienti")
def clienti():
    if "username" not in session:
        return redirect(url_for("login"))
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
    return render_template("clienti.html", clienti=clienti_list)

@app.route("/aggiungi_cliente", methods=["POST"])
def aggiungi_cliente():
    if "username" not in session:
        return redirect(url_for("login"))
    nome_azienda = request.form.get("nome_azienda", "").strip()
    indirizzo = request.form.get("indirizzo", "")
    p_iva = request.form.get("p_iva", "")
    telefono = request.form.get("telefono", "")
    email = request.form.get("email", "")

    if nome_azienda:
        try:
            conn = get_db_connection()
            cur = conn.cursor()
            cur.execute(
                """
                INSERT INTO clienti (nome_azienda, indirizzo, p_iva, telefono, email)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (nome_azienda) DO UPDATE 
                SET indirizzo = EXCLUDED.indirizzo, 
                    p_iva = EXCLUDED.p_iva, 
                    telefono = EXCLUDED.telefono, 
                    email = EXCLUDED.email;
                """,
                (nome_azienda, indirizzo, p_iva, telefono, email)
            )
            conn.commit()
            cur.close()
            conn.close()
            flash("Cliente salvato con successo!", "success")
        except Exception as e:
            flash(f"Errore salvataggio cliente: {e}", "error")

    return redirect(url_for("clienti"))

@app.route("/manutenzioni")
@app.route("/lista_manutenzioni")
def lista_manutenzioni():
    if "username" not in session:
        return redirect(url_for("login"))
    
    if not session.get("is_admin") and not session.get("puo_vedere_manutenzione"):
        flash("Accesso negato: l'amministratore non ti ha autorizzato a visualizzare la sezione manutenzioni.", "error")
        return redirect(url_for("index"))

    prodotti_maint = []
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT * FROM prodotti WHERE stato = 'In Manutenzione' ORDER BY data_riconsegna ASC NULLS LAST;")
        prodotti_maint = cur.fetchall()
        cur.close()
        conn.close()
    except Exception as e:
        print(f"Errore manutenzioni: {e}")
    return render_template("manutenzioni.html", prodotti=prodotti_maint)

if __name__ == "_main_":
    app.run(host="0.0.0.0", port=5000, debug=True)
