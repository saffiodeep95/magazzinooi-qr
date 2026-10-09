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
        return
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Creazione tabelle principali
        cur.execute("""
            CREATE TABLE IF NOT EXISTS utenti (
                id SERIAL PRIMARY KEY,
                username VARCHAR(255) UNIQUE NOT NULL,
                password TEXT NOT NULL,
                is_admin BOOLEAN DEFAULT FALSE,
                puo_vedere_manutenzione BOOLEAN DEFAULT FALSE,
                puo_eliminare BOOLEAN DEFAULT FALSE
            );
            CREATE TABLE IF NOT EXISTS prodotti (
                id SERIAL PRIMARY KEY,
                qr_code VARCHAR(255) UNIQUE NOT NULL,
                nome VARCHAR(255) NOT NULL,
                quantita INT DEFAULT 0,
                posizione VARCHAR(255),
                sap VARCHAR(255),
                in_manutenzione BOOLEAN DEFAULT FALSE,
                cliente_manutenzione VARCHAR(255),
                quantita_manutenzione INT DEFAULT 0,
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
        
        # Ricostruzione pulita della tabella storico per evitare errori di colonne mancanti
        cur.execute("DROP TABLE IF EXISTS storico_manutenzioni;")
        cur.execute("""
            CREATE TABLE storico_manutenzioni (
                id SERIAL PRIMARY KEY,
                qr_code VARCHAR(255) NOT NULL,
                nome_prodotto VARCHAR(255) NOT NULL,
                sap VARCHAR(255),
                cliente VARCHAR(255),
                quantita INT,
                data_spedizione DATE,
                data_riconsegna DATE,
                vettore VARCHAR(255),
                ordine_amministrativo BOOLEAN,
                note TEXT,
                registrato_il TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)

        # Aggiornamenti sicuri per eventuali colonne prodotti/utenti mancanti
        cur.execute("ALTER TABLE utenti ADD COLUMN IF NOT EXISTS puo_vedere_manutenzione BOOLEAN DEFAULT FALSE;")
        cur.execute("ALTER TABLE utenti ADD COLUMN IF NOT EXISTS puo_eliminare BOOLEAN DEFAULT FALSE;")
        
        cur.execute("ALTER TABLE prodotti ADD COLUMN IF NOT EXISTS in_manutenzione BOOLEAN DEFAULT FALSE;")
        cur.execute("ALTER TABLE prodotti ADD COLUMN IF NOT EXISTS cliente_manutenzione VARCHAR(255);")
        cur.execute("ALTER TABLE prodotti ADD COLUMN IF NOT EXISTS quantita_manutenzione INT DEFAULT 0;")
        cur.execute("ALTER TABLE prodotti ADD COLUMN IF NOT EXISTS data_spedizione DATE;")
        cur.execute("ALTER TABLE prodotti ADD COLUMN IF NOT EXISTS data_riconsegna DATE;")
        cur.execute("ALTER TABLE prodotti ADD COLUMN IF NOT EXISTS ordine_amministrativo BOOLEAN DEFAULT FALSE;")
        cur.execute("ALTER TABLE prodotti ADD COLUMN IF NOT EXISTS vettore VARCHAR(255);")
        cur.execute("ALTER TABLE prodotti ADD COLUMN IF NOT EXISTS note_manutenzione TEXT;")

        admin_pass = generate_password_hash("admin123")
        cur.execute("""
            INSERT INTO utenti (username, password, is_admin, puo_vedere_manutenzione, puo_eliminare) 
            VALUES ('admin', %s, TRUE, TRUE, TRUE)
            ON CONFLICT (username) DO UPDATE 
            SET is_admin = TRUE, puo_vedere_manutenzione = TRUE, puo_eliminare = TRUE;
        """, (admin_pass,))
        
        conn.commit()
        cur.close()
        conn.close()
    except Exception as e:
        print(f"Errore DB Init: {e}")

init_db()

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
                session["puo_eliminare"] = bool(user.get("puo_eliminare", False))
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
                cur.execute("INSERT INTO utenti (username, password, is_admin, puo_vedere_manutenzione, puo_eliminare) VALUES (%s, %s, FALSE, FALSE, FALSE);", (username, hashed))
                conn.commit()
                cur.close()
                conn.close()
                flash("Registrazione avvenuta con successo! In attesa di abilitazione dall'Admin.", "success")
                return redirect(url_for("login"))
            except Exception as e:
                flash("Errore: utente già esistente.", "error")
    return render_template("registra.html")

@app.route("/admin/utenti")
def admin_utenti():
    if not session.get("is_admin"):
        flash("Accesso negato.", "error")
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

@app.route("/admin/toggle_permesso/<int:user_id>/<tipo>", methods=["POST"])
def toggle_permesso(user_id, tipo):
    if not session.get("is_admin"):
        return redirect(url_for("index"))
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        if tipo == "manutenzione":
            cur.execute("UPDATE utenti SET puo_vedere_manutenzione = NOT puo_vedere_manutenzione WHERE id = %s;", (user_id,))
        elif tipo == "eliminazione":
            cur.execute("UPDATE utenti SET puo_eliminare = NOT puo_eliminare WHERE id = %s;", (user_id,))
        conn.commit()
        cur.close()
        conn.close()
        flash("Permessi aggiornati con successo.", "success")
    except Exception as e:
        flash(f"Errore: {e}", "error")
    return redirect(url_for("admin_utenti"))

@app.route("/admin/reset_password/<int:user_id>", methods=["POST"])
def reset_password(user_id):
    if not session.get("is_admin"):
        return redirect(url_for("index"))
    nuova_password = request.form.get("nuova_password", "").strip()
    if not nuova_password:
        flash("La nuova password non può essere vuota.", "error")
        return redirect(url_for("admin_utenti"))
    try:
        hashed = generate_password_hash(nuova_password)
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("UPDATE utenti SET password = %s WHERE id = %s;", (hashed, user_id))
        conn.commit()
        cur.close()
        conn.close()
        flash("Password resettata con successo.", "success")
    except Exception as e:
        flash(f"Errore: {e}", "error")
    return redirect(url_for("admin_utenti"))

@app.route("/admin/elimina_utente/<int:user_id>", methods=["POST"])
def elimina_utente(user_id):
    if not session.get("is_admin"):
        return redirect(url_for("index"))
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("DELETE FROM utenti WHERE id = %s;", (user_id,))
        conn.commit()
        cur.close()
        conn.close()
        flash("Utente eliminato.", "success")
    except Exception as e:
        flash(f"Errore: {e}", "error")
    return redirect(url_for("admin_utenti"))

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
        flash("Prodotto non trovato!", "error")
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
                INSERT INTO prodotti (qr_code, nome, sap, quantita, posizione, in_manutenzione)
                VALUES (%s, %s, %s, %s, %s, FALSE)
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
            flash("Prodotto salvato con successo!", "success")
        except Exception as e:
            flash(f"Errore: {e}", "error")

    return redirect(url_for("index"))

@app.route("/upload", methods=["GET", "POST"])
def pagina_upload():
    if "username" not in session:
        return redirect(url_for("login"))
        
    if request.method == "POST":
        file = request.files.get("file_csv")
        if not file:
            flash("Nessun file selezionato.", "error")
            return redirect(url_for("pagina_upload"))
        
        try:
            stream = io.TextIOWrapper(file.stream, encoding="utf-8")
            csv_reader = csv.reader(stream)
            
            first_row = next(csv_reader, None)
            if first_row and any("qr" in cell.lower() or "codice" in cell.lower() or "nome" in cell.lower() for cell in first_row):
                pass
            else:
                if first_row and len(first_row) >= 2:
                    process_csv_row(first_row)

            contatore = 0
            for row in csv_reader:
                if len(row) >= 2 and row[0].strip():
                    process_csv_row(row)
                    contatore += 1
                    
            flash(f"Importazione completata con successo! Articoli elaborati: {contatore + (1 if first_row else 0)}", "success")
            return redirect(url_for("index"))
        except Exception as e:
            flash(f"Errore durante l'importazione: {e}", "error")
            
    return render_template("upload.html")

def process_csv_row(row):
    qr_code = row[0].strip()
    nome = row[1].strip()
    sap = row[2].strip() if len(row) > 2 and row[2] else ""
    try:
        quantita = int(row[3].strip()) if len(row) > 3 and row[3] else 0
    except ValueError:
        quantita = 0
    posizione = row[4].strip() if len(row) > 4 and row[4] else ""
    
    if qr_code and nome:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO prodotti (qr_code, nome, sap, quantita, posizione, in_manutenzione)
            VALUES (%s, %s, %s, %s, %s, FALSE)
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

@app.route("/stampa_tutti_qr")
def stampa_tutti_qr():
    if "username" not in session:
        return redirect(url_for("login"))
    prodotti = []
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT * FROM prodotti ORDER BY nome ASC;")
        prodotti = cur.fetchall()
        cur.close()
        conn.close()
    except Exception as e:
        print(f"Errore stampa massiva QR: {e}")
    return render_template("stampa_tutti_qr.html", prodotti=prodotti)

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
                flash(f"Carico di {quantita} pz effettuato!", "success")
                return redirect(url_for("gestisci_prodotto", qr_code=qr_code))
            except Exception as e:
                flash(f"Errore: {e}", "error")
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
                flash(f"Scarico di {quantita} pz effettuato!", "success")
                return redirect(url_for("gestisci_prodotto", qr_code=qr_code))
            except Exception as e:
                flash(f"Errore: {e}", "error")
    return render_template("scarico.html")

@app.route("/elimina", methods=["POST"])
def elimina_prodotto():
    if "username" not in session:
        return redirect(url_for("login"))
    if not session.get("is_admin") and not session.get("puo_eliminare"):
        flash("Non hai i permessi per eliminare i prodotti.", "error")
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
            flash("Articolo eliminato.", "success")
        except Exception as e:
            flash(f"Errore: {e}", "error")

    return redirect(url_for("index"))

@app.route("/manda_manutenzione/<qr_code>", methods=["POST"])
def manda_manutenzione(qr_code):
    if "username" not in session:
        return redirect(url_for("login"))
    if not session.get("is_admin") and not session.get("puo_vedere_manutenzione"):
        flash("Non hai i permessi per gestire le manutenzioni.", "error")
        return redirect(url_for("gestisci_prodotto", qr_code=qr_code))

    cliente = request.form.get("cliente_manutenzione", "").strip()
    qta_maint = int(request.form.get("quantita_manutenzione", 1) or 1)
    data_spedizione = request.form.get("data_spedizione") or None
    data_riconsegna = request.form.get("data_riconsegna") or None
    ordine_amministrativo = True if request.form.get("ordine_amministrativo") == "on" else False
    vettore = request.form.get("vettore", "")
    note = request.form.get("note_manutenzione", "")

    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        if cliente:
            cur.execute("""
                INSERT INTO clienti (nome_azienda)
                VALUES (%s)
                ON CONFLICT (nome_azienda) DO NOTHING;
            """, (cliente,))

        cur.execute("SELECT * FROM prodotti WHERE qr_code = %s;", (qr_code,))
        prod = cur.fetchone()
        
        if prod:
            qta_magazzino = prod["quantita"]
            gia_in_maint = prod["in_manutenzione"]
            
            if not gia_in_maint:
                nuova_qta = max(0, qta_magazzino - qta_maint)
                cur.execute("""
                    UPDATE prodotti 
                    SET quantita = %s, in_manutenzione = TRUE, cliente_manutenzione = %s, 
                        quantita_manutenzione = %s, data_spedizione = %s, data_riconsegna = %s, 
                        ordine_amministrativo = %s, vettore = %s, note_manutenzione = %s
                    WHERE qr_code = %s;
                """, (nuova_qta, cliente if cliente else None, qta_maint, data_spedizione, data_riconsegna, ordine_amministrativo, vettore if vettore else None, note, qr_code))
            else:
                cur.execute("""
                    UPDATE prodotti 
                    SET cliente_manutenzione = %s, quantita_manutenzione = %s, data_spedizione = %s, 
                        data_riconsegna = %s, ordine_amministrativo = %s, vettore = %s, note_manutenzione = %s
                    WHERE qr_code = %s;
                """, (cliente if cliente else None, qta_maint, data_spedizione, data_riconsegna, ordine_amministrativo, vettore if vettore else None, note, qr_code))

            # Registrazione sicura nell'archivio storico
            cur.execute("""
                INSERT INTO storico_manutenzioni (qr_code, nome_prodotto, sap, cliente, quantita, data_spedizione, data_riconsegna, vettore, ordine_amministrativo, note)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s);
            """, (qr_code, prod["nome"], prod["sap"], cliente, qta_maint, data_spedizione, data_riconsegna, vettore, ordine_amministrativo, note))

        conn.commit()
        cur.close()
        conn.close()
        flash("Manutenzione salvata e registrata nello storico!", "success")
    except Exception as e:
        flash(f"Errore: {e}", "error")
        
    return redirect(url_for("gestisci_prodotto", qr_code=qr_code))

@app.route("/ripristina_magazzino/<qr_code>", methods=["POST"])
def ripristina_magazzino(qr_code):
    if "username" not in session:
        return redirect(url_for("login"))
    if not session.get("is_admin") and not session.get("puo_vedere_manutenzione"):
        flash("Non hai i permessi.", "error")
        return redirect(url_for("gestisci_prodotto", qr_code=qr_code))

    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT quantita, quantita_manutenzione, in_manutenzione FROM prodotti WHERE qr_code = %s;", (qr_code,))
        prod = cur.fetchone()
        
        if prod and prod["in_manutenzione"]:
            qta_magazzino = prod["quantita"]
            qta_maint = prod["quantita_manutenzione"] or 0
            nuova_qta = qta_magazzino + qta_maint
            
            cur.execute("""
                UPDATE prodotti 
                SET quantita = %s, in_manutenzione = FALSE, cliente_manutenzione = NULL,
                    quantita_manutenzione = 0, data_spedizione = NULL, data_riconsegna = NULL,
                    ordine_amministrativo = FALSE, vettore = NULL, note_manutenzione = NULL
                WHERE qr_code = %s;
            """, (nuova_qta, qr_code))
            conn.commit()
            flash("Prodotto ripristinato in magazzino e pezzi ricaricati!", "success")
        
        cur.close()
        conn.close()
    except Exception as e:
        flash(f"Errore: {e}", "error")

    return redirect(url_for("gestisci_prodotto", qr_code=qr_code))

@app.route("/storico_manutenzioni")
def storico_manutenzioni():
    if "username" not in session:
        return redirect(url_for("login"))
    if not session.get("is_admin") and not session.get("puo_vedere_manutenzione"):
        flash("Accesso negato.", "error")
        return redirect(url_for("index"))

    storico = []
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT * FROM storico_manutenzioni ORDER BY id DESC;")
        storico = cur.fetchall()
        cur.close()
        conn.close()
    except Exception as e:
        print(f"Errore storico: {e}")
    return render_template("storico_manutenzioni.html", storico=storico)

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
        flash("Prodotto non trovato.", "error")
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
                SET indirizzo = EXCLUDED.indirizzo, p_iva = EXCLUDED.p_iva, 
                    telefono = EXCLUDED.telefono, email = EXCLUDED.email;
                """,
                (nome_azienda, indirizzo, p_iva, telefono, email)
            )
            conn.commit()
            cur.close()
            conn.close()
            flash("Cliente salvato!", "success")
        except Exception as e:
            flash(f"Errore: {e}", "error")

    return redirect(url_for("clienti"))

@app.route("/elimina_cliente/<int:cliente_id>", methods=["POST"])
def elimina_cliente(cliente_id):
    if "username" not in session:
        return redirect(url_for("login"))
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("DELETE FROM clienti WHERE id = %s;", (cliente_id,))
        conn.commit()
        cur.close()
        conn.close()
        flash("Cliente eliminato dalla rubrica.", "success")
    except Exception as e:
        flash(f"Errore eliminazione cliente: {e}", "error")
    return redirect(url_for("clienti"))

@app.route("/manutenzioni")
@app.route("/lista_manutenzioni")
def lista_manutenzioni():
    if "username" not in session:
        return redirect(url_for("login"))
    if not session.get("is_admin") and not session.get("puo_vedere_manutenzione"):
        flash("Accesso negato.", "error")
        return redirect(url_for("index"))

    prodotti_maint = []
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT * FROM prodotti WHERE in_manutenzione = TRUE ORDER BY data_riconsegna ASC NULLS LAST;")
        prodotti_maint = cur.fetchall()
        cur.close()
        conn.close()
    except Exception as e:
        print(f"Errore manutenzioni: {e}")
    return render_template("manutenzioni.html", prodotti=prodotti_maint)

if __name__ == "_main_":
    app.run(host="0.0.0.0", port=5000, debug=True)
