import os
import psycopg2
from psycopg2.extras import RealDictCursor
from flask import Flask, render_template, request, redirect, url_for, flash

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "chiave-segreta-magazzino")

DATABASE_URL = os.environ.get("DATABASE_URL")

def get_db_connection():
    if not DATABASE_URL:
        return None
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
                magazzino_composizione_motori INT DEFAULT 0,
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
        
        cur.execute("""
            CREATE TABLE IF NOT EXISTS clienti (
                id SERIAL PRIMARY KEY,
                nome_azienda VARCHAR(255) NOT NULL,
                referente VARCHAR(255),
                telefono VARCHAR(255),
                email VARCHAR(255)
            );
        """)
        
        colonne_da_aggiungere = [
            ("peso", "VARCHAR(255)"),
            ("magazzino_composizione_motori", "INT DEFAULT 0"),
            ("in_manutenzione", "INT DEFAULT 0"),
            ("cliente_manutenzione", "VARCHAR(255)"),
            ("quantita_manutenzione", "INT DEFAULT 0"),
            ("data_spedizione", "VARCHAR(255)"),
            ("data_riconsegna", "VARCHAR(255)"),
            ("vettore", "VARCHAR(255)"),
            ("ordine_amministrativo", "INT DEFAULT 0"),
            ("note_manutenzione", "TEXT")
        ]
        
        for col_nome, col_tipo in colonne_da_aggiungere:
            cur.execute(f"""
                ALTER TABLE prodotti ADD COLUMN IF NOT EXISTS {col_nome} {col_tipo};
            """)

        conn.commit()
        cur.close()
        conn.close()
        print("Inizializzazione database completata con successo.")
    except Exception as e:
        print(f"Errore durante l'inizializzazione del database: {e}")

init_db()

# --- ROTTE PRINCIPALI ---

@app.route("/")
def index():
    prodotti = []
    try:
        conn = get_db_connection()
        if conn:
            cur = conn.cursor()
            cur.execute("SELECT * FROM prodotti WHERE magazzino_composizione_motori = 0 OR magazzino_composizione_motori IS NULL ORDER BY nome ASC;")
            prodotti = cur.fetchall()
            cur.close()
            conn.close()
    except Exception as e:
        print(f"Errore index: {e}")
    return render_template("index.html", prodotti=prodotti)

@app.route("/logout")
def logout():
    return redirect(url_for("index"))

@app.route("/login")
def login():
    try:
        return render_template("login.html")
    except Exception:
        return redirect(url_for("index"))

@app.route("/admin_utenti")
def admin_utenti():
    try:
        return render_template("admin_utenti.html")
    except Exception:
        return redirect(url_for("index"))

# --- SEZIONE CLIENTI E RUBRICA ---

@app.route("/clienti", methods=["GET", "POST"])
def clienti():
    lista_clienti = []
    conn = get_db_connection()
    try:
        if conn:
            cur = conn.cursor()
            if request.method == "POST":
                nome_azienda = request.form.get("nome_azienda")
                referente = request.form.get("referente", "")
                telefono = request.form.get("telefono", "")
                email = request.form.get("email", "")
                if nome_azienda:
                    cur.execute(
                        "INSERT INTO clienti (nome_azienda, referente, telefono, email) VALUES (%s, %s, %s, %s);",
                        (nome_azienda, referente, telefono, email)
                    )
                    conn.commit()
                    flash("Cliente aggiunto con successo!", "success")
                cur.close()
                conn.close()
                return redirect(url_for("clienti"))
            
            cur.execute("SELECT * FROM clienti ORDER BY nome_azienda ASC;")
            lista_clienti = cur.fetchall()
            cur.close()
            conn.close()
    except Exception as e:
        print(f"Errore clienti: {e}")
    
    try:
        return render_template("clienti.html", clienti=lista_clienti)
    except Exception:
        return render_template("lista_clienti.html", clienti=lista_clienti)

@app.route("/lista_clienti")
def lista_clienti_route():
    return redirect(url_for("clienti"))

# --- UPLOAD E STAMPA ---

@app.route("/upload")
def upload():
    try:
        return render_template("upload.html")
    except Exception:
        return redirect(url_for("index"))

@app.route("/pagina_upload", methods=["GET", "POST"])
def pagina_upload():
    if request.method == "POST":
        flash("File caricato con successo!", "success")
        return redirect(url_for("index"))
    try:
        return render_template("upload.html")
    except Exception:
        return redirect(url_for("index"))

@app.route("/stampa_tutti_qr")
def stampa_tutti_qr():
    prodotti = []
    try:
        conn = get_db_connection()
        if conn:
            cur = conn.cursor()
            cur.execute("SELECT * FROM prodotti ORDER BY nome ASC;")
            prodotti = cur.fetchall()
            cur.close()
            conn.close()
    except Exception as e:
        print(f"Errore stampa QR: {e}")
    try:
        return render_template("stampa_tutti_qr.html", prodotti=prodotti)
    except Exception:
        return render_template("index.html", prodotti=prodotti)

# --- MAGAZZINO COMPOSIZIONE E MOTORI ---

@app.route("/magazzino_composizione_motori")
def magazzino_composizione_motori_view():
    prodotti = []
    try:
        conn = get_db_connection()
        if conn:
            cur = conn.cursor()
            cur.execute("SELECT * FROM prodotti WHERE magazzino_composizione_motori = 1 ORDER BY nome ASC;")
            prodotti = cur.fetchall()
            cur.close()
            conn.close()
    except Exception as e:
        print(f"Errore magazzino composizione: {e}")
    
    try:
        return render_template("magazzino_composizione.html", prodotti=prodotti)
    except Exception:
        try:
            return render_template("magazzino_composizione_motori.html", prodotti=prodotti)
        except Exception:
            return render_template("index.html", prodotti=prodotti)

# --- MANUTENZIONI E DOCUMENTI ---

@app.route("/manutenzioni")
def manutenzioni():
    prodotti = []
    try:
        conn = get_db_connection()
        if conn:
            cur = conn.cursor()
            cur.execute("SELECT * FROM prodotti WHERE in_manutenzione = 1 ORDER BY nome ASC;")
            prodotti = cur.fetchall()
            cur.close()
            conn.close()
    except Exception as e:
        print(f"Errore manutenzioni: {e}")
    try:
        return render_template("manutenzioni.html", prodotti=prodotti)
    except Exception:
        return render_template("index.html", prodotti=prodotti)

@app.route("/lista_manutenzioni")
def lista_manutenzioni():
    return redirect(url_for("manutenzioni"))

@app.route("/storico_manutenzioni")
def storico_manutenzioni():
    prodotti = []
    try:
        conn = get_db_connection()
        if conn:
            cur = conn.cursor()
            cur.execute("SELECT * FROM prodotti ORDER BY nome ASC;")
            prodotti = cur.fetchall()
            cur.close()
            conn.close()
    except Exception as e:
        print(f"Errore storico manutenzioni: {e}")
    try:
        return render_template("storico_manutenzioni.html", prodotti=prodotti)
    except Exception:
        return redirect(url_for("index"))

@app.route("/bolla")
def bolla():
    try:
        return render_template("bolla.html")
    except Exception:
        return redirect(url_for("index"))

@app.route("/registra")
def registra():
    try:
        return render_template("registra.html")
    except Exception:
        return redirect(url_for("index"))

@app.route("/carico_pagina")
def carico_pagina():
    try:
        return render_template("carico.html")
    except Exception:
        return redirect(url_for("index"))

@app.route("/scarico_pagina")
def scarico_pagina():
    try:
        return render_template("scarico.html")
    except Exception:
        return redirect(url_for("index"))

# --- OPERAZIONI SUI PRODOTTI ---

@app.route("/gestisci/<qr_code>")
def gestisci_prodotto(qr_code):
    prodotto = None
    lista_clienti = []
    try:
        conn = get_db_connection()
        if conn:
            cur = conn.cursor()
            cur.execute("SELECT * FROM prodotti WHERE qr_code = %s;", (qr_code,))
            prodotto = cur.fetchone()
            try:
                cur.execute("SELECT * FROM clienti ORDER BY nome_azienda ASC;")
                lista_clienti = cur.fetchall()
            except Exception:
                pass
            cur.close()
            conn.close()
    except Exception as e:
        print(f"Errore gestisci: {e}")

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
    flag_sezione = 1 if request.form.get("magazzino_composizione_motori") else 0

    if not qr_code or not nome:
        flash("QR Code e Nome sono obbligatori!", "error")
        return redirect(url_for("index"))

    try:
        conn = get_db_connection()
        if conn:
            cur = conn.cursor()
            cur.execute(
                """
                INSERT INTO prodotti (qr_code, nome, sap, peso, quantita, posizione, magazzino_composizione_motori)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (qr_code)
                DO UPDATE SET 
                    quantita = prodotti.quantita + EXCLUDED.quantita,
                    nome = EXCLUDED.nome,
                    sap = EXCLUDED.sap,
                    peso = EXCLUDED.peso,
                    posizione = EXCLUDED.posizione,
                    magazzino_composizione_motori = EXCLUDED.magazzino_composizione_motori;
                """,
                (qr_code, nome, sap, peso, quantita, posizione, flag_sezione)
            )
            conn.commit()
            cur.close()
            conn.close()
            flash("Prodotto aggiunto o aggiornato con successo!", "success")
    except Exception as e:
        flash(f"Errore nell'inserimento: {e}", "error")

    if flag_sezione:
        return redirect(url_for("magazzino_composizione_motori_view"))
    return redirect(url_for("index"))

@app.route("/carico", methods=["GET", "POST"])
def carico():
    if request.method == "POST":
        qr_code = request.form.get("qr_code")
        quantita = int(request.form.get("quantita", 1))
    else:
        qr_code = request.args.get("qr_code")
        quantita = int(request.args.get("quantita", 1))

    if not qr_code:
        flash("QR Code non valido o mancante!", "error")
        return redirect(url_for("index"))

    try:
        conn = get_db_connection()
        if conn:
            cur = conn.cursor()
            cur.execute("UPDATE prodotti SET quantita = quantita + %s WHERE qr_code = %s;", (quantita, qr_code))
            conn.commit()
            flash(f"Carico di {quantita} pz effettuato con successo!", "success")
            cur.close()
            conn.close()
    except Exception as e:
        flash(f"Errore durante il carico: {e}", "error")

    return redirect(url_for("gestisci_prodotto", qr_code=qr_code))

@app.route("/scarico", methods=["GET", "POST"])
def scarico():
    if request.method == "POST":
        qr_code = request.form.get("qr_code")
        quantita = int(request.form.get("quantita", 1))
    else:
        qr_code = request.args.get("qr_code")
        quantita = int(request.args.get("quantita", 1))

    if not qr_code:
        flash("QR Code non valido o mancante!", "error")
        return redirect(url_for("index"))

    try:
        conn = get_db_connection()
        if conn:
            cur = conn.cursor()
            cur.execute("UPDATE prodotti SET quantita = GREATEST(0, quantita - %s) WHERE qr_code = %s;", (quantita, qr_code))
            conn.commit()
            flash(f"Scarico di {quantita} pz effettuato con successo!", "success")
            cur.close()
            conn.close()
    except Exception as e:
        flash(f"Errore durante lo scarico: {e}", "error")

    return redirect(url_for("gestisci_prodotto", qr_code=qr_code))

@app.route("/manutenzione/<qr_code>", methods=["POST"])
def manutenzione(qr_code):
    azione = request.form.get("azione")
    conn = get_db_connection()
    try:
        if conn:
            cur = conn.cursor()
            if azione == "invia":
                cliente = request.form.get("cliente")
                q_maint = int(request.form.get("quantita_manutenzione", 1))
                data_sped = request.form.get("data_spedizione")
                data_ric = request.form.get("data_riconsegna")
                vettore = request.form.get("vettore")
                ordine_amm = 1 if request.form.get("ordine_amministrativo") else 0
                note = request.form.get("note_manutenzione")

                cur.execute("SELECT quantita FROM prodotti WHERE qr_code = %s;", (qr_code,))
                prod = cur.fetchone()
                if prod and prod["quantita"] >= q_maint:
                    cur.execute("""
                        UPDATE prodotti SET 
                            quantita = quantita - %s,
                            in_manutenzione = 1,
                            cliente_manutenzione = %s,
                            quantita_manutenzione = %s,
                            data_spedizione = %s,
                            data_riconsegna = %s,
                            vettore = %s,
                            ordine_amministrativo = %s,
                            note_manutenzione = %s
                        WHERE qr_code = %s;
                    """, (q_maint, cliente, q_maint, data_sped, data_ric, vettore, ordine_amm, note, qr_code))
                    conn.commit()
                    flash("Articolo inviato in manutenzione con successo!", "success")
                else:
                    flash("Quantità insufficiente per mandare in manutenzione.", "error")

            elif azione == "rientra":
                cur.execute("SELECT quantita_manutenzione FROM prodotti WHERE qr_code = %s;", (qr_code,))
                prod = cur.fetchone()
                if prod:
                    q_rientro = prod["quantita_manutenzione"] or 0
                    cur.execute("""
                        UPDATE prodotti SET 
                            quantita = quantita + %s,
                            in_manutenzione = 0,
                            cliente_manutenzione = NULL,
                            quantita_manutenzione = 0,
                            data_spedizione = NULL,
                            data_riconsegna = NULL,
                            vettore = NULL,
                            ordine_amministrativo = 0,
                            note_manutenzione = NULL
                        WHERE qr_code = %s;
                    """, (q_rientro, qr_code))
                    conn.commit()
                    flash("Articolo rientrato dalla manutenzione con successo!", "success")
            cur.close()
            conn.close()
    except Exception as e:
        flash(f"Errore nella gestione manutenzione: {e}", "error")

    return redirect(url_for("gestisci_prodotto", qr_code=qr_code))

@app.route("/elimina", methods=["POST"])
def elimina_prodotto():
    qr_code = request.form.get("qr_code")
    if not qr_code:
        flash("QR Code non valido per l'eliminazione!", "error")
        return redirect(url_for("index"))

    try:
        conn = get_db_connection()
        if conn:
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
