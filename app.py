import os
import io
import csv
from datetime import datetime
import psycopg2
from psycopg2.extras import RealDictCursor
from flask import Flask, render_template, request, redirect, url_for, flash, session, Response, jsonify
from werkzeug.security import generate_password_hash, check_password_hash

# ==============================================================================
# Magazzino OMG Application
# Copyright (c) 2026 Marco Pavan. All Rights Reserved.
# Designed & Developed by Marco Pavan
# ==============================================================================

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "super_segreto_omg_2026_marcopavan")

def get_db_connection():
    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        raise RuntimeError("DATABASE_URL non impostata nelle variabili d'ambiente.")
    conn = psycopg2.connect(db_url, cursor_factory=RealDictCursor)
    return conn

def registra_log(descrizione):
    try:
        username = session.get('username', 'Sistema')
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("INSERT INTO log_attivita (username, descrizione) VALUES (%s, %s);", (username, descrizione))
        conn.commit()
        cur.close()
        conn.close()
    except Exception as e:
        print(f"Errore registrazione log: {e}")

# --- INIZIALIZZAZIONE DEL DATABASE ---
def init_db():
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
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
            CREATE TABLE IF NOT EXISTS prodotti (
                qr_code VARCHAR(255) PRIMARY KEY,
                nome VARCHAR(255) NOT NULL,
                sap VARCHAR(255),
                quantita INT DEFAULT 0,
                posizione VARCHAR(255),
                peso VARCHAR(255),
                magazzino_pesante BOOLEAN DEFAULT FALSE,
                matricola VARCHAR(255),
                stato_pezzo VARCHAR(255) DEFAULT 'Nuovo',
                volte_riparato INT DEFAULT 0,
                in_manutenzione BOOLEAN DEFAULT FALSE,
                cliente_manutenzione VARCHAR(255),
                quantita_manutenzione INT DEFAULT 1,
                data_spedizione VARCHAR(255),
                data_riconsegna VARCHAR(255),
                vettore VARCHAR(255),
                ordine_amministrativo BOOLEAN DEFAULT FALSE,
                note TEXT
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
                note TEXT,
                esito VARCHAR(255)
            );
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS richieste_manutenzione (
                id SERIAL PRIMARY KEY,
                titolo VARCHAR(255) NOT NULL,
                impianto_macchina VARCHAR(255),
                descrizione TEXT,
                priorita VARCHAR(50) DEFAULT 'Media',
                stato VARCHAR(50) DEFAULT 'Aperta',
                tipo_guasto VARCHAR(50) DEFAULT 'Meccanico',
                assegnato_a VARCHAR(255),
                creato_da VARCHAR(255),
                inizio_lavoro TIMESTAMP,
                fine_lavoro TIMESTAMP,
                tempo_lavorato_minuti INT DEFAULT 0,
                note_lavoro TEXT,
                allegato_nome VARCHAR(255),
                allegato_dati BYTEA,
                creato_il TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS fornitori (
                id SERIAL PRIMARY KEY,
                nome_azienda VARCHAR(255) NOT NULL,
                contatto VARCHAR(255),
                telefono VARCHAR(255),
                email VARCHAR(255),
                settore_note TEXT
            );
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS log_attivita (
                id SERIAL PRIMARY KEY,
                data_ora TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                username VARCHAR(255),
                descrizione TEXT
            );
        """)

        # Colonne di migrazione sicure
        colonne_migrazione = [
            ("fornitori", "settore_note", "VARCHAR(255)"),
            ("prodotti", "soglia_minima", "INT DEFAULT 3"),
            ("prodotti", "matricola", "VARCHAR(255)"),
            ("prodotti", "stato_pezzo", "VARCHAR(255) DEFAULT 'Nuovo'"),
            ("prodotti", "volte_riparato", "INT DEFAULT 0"),
            ("storico_manutenzioni", "esito", "VARCHAR(255)"),
            ("richieste_manutenzione", "tipo_guasto", "VARCHAR(50) DEFAULT 'Meccanico'"),
            ("richieste_manutenzione", "tempo_lavorato_minuti", "INT DEFAULT 0"),
            ("utenti", "puo_aprire_manutenzioni", "INT DEFAULT 1"),
            ("utenti", "puo_assegnare_manutenzioni", "INT DEFAULT 1")
        ]

        for tabella, colonna, tipo in colonne_migrazione:
            cur.execute(f"ALTER TABLE {tabella} ADD COLUMN IF NOT EXISTS {colonna} {tipo};")

        # Crea utente admin di default se non esiste
        cur.execute("SELECT * FROM utenti WHERE username = 'admin';")
        if not cur.fetchone():
            hashed_pw = generate_password_hash("admin")
            cur.execute("""
                INSERT INTO utenti (username, password, is_admin, puo_vedere_manutenzione, puo_eliminare, puo_eliminare_storico, puo_gestire_documenti, puo_aprire_manutenzioni, puo_assegnare_manutenzioni) 
                VALUES (%s, %s, 1, 1, 1, 1, 1, 1, 1);
            """, ('admin', hashed_pw))

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

# --- AUTENTICAZIONE ---
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
                session['puo_vedere_manutenzione'] = user.get('puo_vedere_manutenzione', 1)
                session['puo_eliminare'] = user.get('puo_eliminare', 0)
                session['puo_eliminare_storico'] = user.get('puo_eliminare_storico', 0)
                session['puo_gestire_documenti'] = user.get('puo_gestire_documenti', 1)
                session['puo_aprire_manutenzioni'] = user.get('puo_aprire_manutenzioni', 1)
                session['puo_assegnare_manutenzioni'] = user.get('puo_assegnare_manutenzioni', 1)
                registra_log("Accesso effettuato al sistema")
                return redirect(url_for('index'))
            else:
                flash("Credenziali non valide!", "error")
        except Exception as e:
            flash(f"Errore login: {e}", "error")
    return render_template("login.html")

@app.route("/logout")
def logout():
    registra_log("Disconnessione dal sistema")
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
                cur.execute("""
                    INSERT INTO utenti (username, password, is_admin, puo_vedere_manutenzione, puo_eliminare, puo_eliminare_storico, puo_gestire_documenti, puo_aprire_manutenzioni, puo_assegnare_manutenzioni) 
                    VALUES (%s, %s, 0, 1, 0, 0, 1, 1, 1);
                """, (username, hashed_pw))
                conn.commit()
                cur.close()
                conn.close()
                registra_log(f"Registrato nuovo utente: {username}")
                flash("Registrazione completata! Ora puoi effettuare il login.", "success")
                return redirect(url_for('login'))
            except Exception as e:
                flash("Username già esistente o errore di registrazione.", "error")
    return render_template("registra.html")

# --- DASHBOARD PRINCIPALE ---
@app.route("/")
def index():
    prodotti = []
    prodotti_sotto_soglia = []
    interventi_aperti_count = 0
    interventi_in_lavoro_count = 0
    interventi_attesa_count = 0

    try:
        conn = get_db_connection()
        cur = conn.cursor()

        cur.execute("SELECT * FROM prodotti ORDER BY nome ASC;")
        tutti = cur.fetchall()

        cur.execute("SELECT COUNT(*) as count FROM richieste_manutenzione WHERE stato = 'Aperta';")
        interventi_aperti_count = cur.fetchone()['count']
        cur.execute("SELECT COUNT(*) as count FROM richieste_manutenzione WHERE stato IN ('In Lavoro', 'In Pausa');")
        interventi_in_lavoro_count = cur.fetchone()['count']
        cur.execute("SELECT COUNT(*) as count FROM richieste_manutenzione WHERE stato = 'Attesa Ricambio';")
        interventi_attesa_count = cur.fetchone()['count']

        cur.close()
        conn.close()

        for p in tutti:
            val_pesante = p.get('magazzino_pesante')
            is_pesante = (val_pesante == 1 or val_pesante == '1' or val_pesante is True or val_pesante == 1.0)
            if not is_pesante:
                prodotti.append(p)
                soglia = p.get('soglia_minima', 3) or 3
                if p.get('quantita', 0) <= soglia:
                    prodotti_sotto_soglia.append(p)
    except Exception as e:
        print(f"Errore index: {e}")

    return render_template("index.html",
                           prodotti=prodotti,
                           prodotti_sotto_soglia=prodotti_sotto_soglia,
                           interventi_aperti_count=interventi_aperti_count,
                           interventi_in_lavoro_count=interventi_in_lavoro_count,
                           interventi_attesa_count=interventi_attesa_count)

# --- ESPORTAZIONE CSV ---
@app.route("/esporta_inventario")
def esporta_inventario():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT qr_code, nome, sap, quantita, posizione, peso, magazzino_pesante FROM prodotti ORDER BY nome ASC;")
    prodotti = cur.fetchall()
    cur.close()
    conn.close()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['QR Code', 'Nome Articolo', 'SAP', 'Quantita', 'Posizione', 'Peso', 'Magazzino Pesante'])
    for p in prodotti:
        writer.writerow([p['qr_code'], p['nome'], p['sap'], p['quantita'], p['posizione'], p['peso'], 'Si' if p['magazzino_pesante'] else 'No'])

    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-disposition": "attachment; filename=Inventario_Magazzino.csv"}
    )

# --- GESTIONE PRODOTTI & SCHEDA ---
@app.route("/aggiungi_prodotto", methods=["POST"])
def aggiungi_prodotto():
    qr_code = request.form.get("qr_code", "").strip()
    nome = request.form.get("nome", "").strip()
    sap = request.form.get("sap", "").strip()
    quantita = int(request.form.get("quantita", 1))
    posizione = request.form.get("posizione", "").strip()
    peso = request.form.get("peso", "").strip()
    soglia_minima = int(request.form.get("soglia_minima", 3))
    magazzino_pesante = True if request.form.get("magazzino_pesante") else False
    matricola = request.form.get("matricola", "").strip()
    stato_pezzo = request.form.get("stato_pezzo", "Nuovo")

    if not qr_code or not nome:
        flash("QR Code e Nome Articolo sono obbligatori!", "error")
        return redirect(url_for("index"))

    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO prodotti (qr_code, nome, sap, quantita, posizione, peso, soglia_minima, magazzino_pesante, matricola, stato_pezzo)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s);
        """, (qr_code, nome, sap, quantita, posizione, peso, soglia_minima, magazzino_pesante, matricola, stato_pezzo))
        conn.commit()
        cur.close()
        conn.close()
        flash(f"Articolo {nome} salvato con successo!", "success")
    except Exception as e:
        flash(f"Errore salvataggio articolo (QR Code duplicato?): {e}", "error")

    return redirect(url_for("index"))

@app.route("/gestisci/<qr_code>")
def gestisci_prodotto(qr_code):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM prodotti WHERE qr_code = %s;", (qr_code,))
    prodotto = cur.fetchone()

    cur.execute("SELECT * FROM fornitori ORDER BY nome_azienda ASC;")
    fornitori = cur.fetchall()

    cur.execute("SELECT * FROM storico_manutenzioni WHERE qr_code = %s ORDER BY id DESC;", (qr_code,))
    storico_prodotto = cur.fetchall()

    cur.close()
    conn.close()

    if not prodotto:
        flash("Prodotto non trovato.", "error")
        return redirect(url_for("index"))

    return render_template("gestisci.html", prodotto=prodotto, fornitori=fornitori, storico_prodotto=storico_prodotto)

@app.route("/aggiorna_prodotto/<qr_code>", methods=["POST"])
def aggiorna_prodotto(qr_code):
    nome = request.form.get("nome", "").strip()
    sap = request.form.get("sap", "").strip()
    posizione = request.form.get("posizione", "").strip()
    peso = request.form.get("peso", "").strip()
    soglia_minima = int(request.form.get("soglia_minima", 3))
    magazzino_pesante = True if request.form.get("magazzino_pesante") else False
    matricola = request.form.get("matricola", "").strip()

    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("""
            UPDATE prodotti 
            SET nome = %s, sap = %s, posizione = %s, peso = %s, soglia_minima = %s, magazzino_pesante = %s, matricola = %s
            WHERE qr_code = %s;
        """, (nome, sap, posizione, peso, soglia_minima, magazzino_pesante, matricola, qr_code))
        conn.commit()
        cur.close()
        conn.close()
        flash("Articolo aggiornato con successo!", "success")
    except Exception as e:
        flash(f"Errore aggiornamento: {e}", "error")

    return redirect(url_for("gestisci_prodotto", qr_code=qr_code))

@app.route("/elimina_prodotto", methods=["POST"])
def elimina_prodotto():
    if not (session.get('is_admin') or session.get('puo_eliminare')):
        flash("Non hai i permessi per eliminare articoli.", "error")
        return redirect(url_for("index"))

    qr_code = request.form.get("qr_code")
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("DELETE FROM prodotti WHERE qr_code = %s;", (qr_code,))
        conn.commit()
        cur.close()
        conn.close()
        flash("Articolo eliminato.", "success")
    except Exception as e:
        flash(f"Errore eliminazione: {e}", "error")
    return redirect(url_for("index"))

# --- MANUTENZIONE ESTERNA & TERZISTI ---
@app.route("/manda_manutenzione/<qr_code>", methods=["POST"])
def manda_manutenzione(qr_code):
    cliente = request.form.get("cliente_manutenzione", "").strip()
    quantita = int(request.form.get("quantita_manutenzione", 1))
    data_spedizione = request.form.get("data_spedizione", "")
    data_riconsegna = request.form.get("data_riconsegna", "")
    vettore = request.form.get("vettore", "").strip()
    note = request.form.get("note_manutenzione", "").strip()

    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("""
            UPDATE prodotti 
            SET in_manutenzione = TRUE,
                cliente_manutenzione = %s,
                quantita_manutenzione = %s,
                data_spedizione = %s,
                data_riconsegna = %s,
                vettore = %s,
                note_manutenzione = %s,
                quantita = GREATEST(0, quantita - %s)
            WHERE qr_code = %s;
        """, (cliente, quantita, data_spedizione, data_riconsegna, vettore, note, quantita, qr_code))
        conn.commit()
        cur.close()
        conn.close()
        flash("Articolo inviato in manutenzione esterna.", "success")
    except Exception as e:
        flash(f"Errore invio in manutenzione: {e}", "error")

    return redirect(url_for("gestisci_prodotto", qr_code=qr_code))

@app.route("/ripristina_magazzino/<qr_code>", methods=["POST"])
def ripristina_magazzino(qr_code):
    esito = request.form.get("esito_riparazione", "Riparato e Collaudato")
    note_rientro = request.form.get("note_rientro", "").strip()

    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT * FROM prodotti WHERE qr_code = %s;", (qr_code,))
        prod = cur.fetchone()

        if prod:
            qta_rientro = prod.get('quantita_manutenzione', 1) or 1
            
            # Registra nello storico
            cur.execute("""
                INSERT INTO storico_manutenzioni (nome_prodotto, qr_code, sap, cliente, quantita, data_spedizione, data_riconsegna, vettore, note, esito)
                VALUES (%s, %s, %s, %s, %s, %s, CURRENT_DATE, %s, %s, %s);
            """, (prod['nome'], qr_code, prod['sap'], prod.get('cliente_manutenzione'), qta_rientro, prod.get('data_spedizione'), prod.get('vettore'), note_rientro, esito))

            # Ripristina in magazzino e aggiorna contatore riparazioni
            cur.execute("""
                UPDATE prodotti 
                SET quantita = quantita + %s,
                    volte_riparato = COALESCE(volte_riparato, 0) + 1,
                    stato_pezzo = %s,
                    in_manutenzione = FALSE,
                    cliente_manutenzione = NULL,
                    quantita_manutenzione = 1,
                    data_spedizione = NULL,
                    data_riconsegna = NULL,
                    vettore = NULL,
                    note_manutenzione = NULL
                WHERE qr_code = %s;
            """, (qta_rientro, esito, qr_code))

            conn.commit()
            flash(f"Articolo rientrato con successo! Esito: {esito}", "success")

        cur.close()
        conn.close()
    except Exception as e:
        flash(f"Errore rientro magazzino: {e}", "error")

    return redirect(url_for("gestisci_prodotto", qr_code=qr_code))

@app.route("/storico_manutenzioni")
def storico_manutenzioni():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM storico_manutenzioni ORDER BY id DESC;")
    storico = cur.fetchall()
    cur.close()
    conn.close()
    return render_template("storico_manutenzioni.html", storico=storico)

@app.route("/elimina_storico_manutenzione/<int:id>", methods=["POST"])
def elimina_storico_manutenzione(id):
    if not (session.get('is_admin') or session.get('puo_eliminare_storico')):
        flash("Non hai i permessi per eliminare elementi dallo storico.", "error")
        return redirect(url_for("storico_manutenzioni"))

    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("DELETE FROM storico_manutenzioni WHERE id = %s;", (id,))
        conn.commit()
        cur.close()
        conn.close()
        flash("Voce eliminata dallo storico.", "success")
    except Exception as e:
        flash(f"Errore eliminazione storico: {e}", "error")

    return redirect(url_for("storico_manutenzioni"))

# --- FORNITORI ---
@app.route("/aggiungi_fornitore", methods=["POST"])
def aggiungi_fornitore():
    nome_azienda = request.form.get("nome_azienda", "").strip()
    contatto = request.form.get("contatto", "").strip()
    telefono = request.form.get("telefono", "").strip()
    email = request.form.get("email", "").strip()
    settore_note = request.form.get("settore_note", "").strip()

    if not nome_azienda:
        flash("Il nome dell'azienda è obbligatorio!", "error")
        return redirect(url_for("index"))

    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO fornitori (nome_azienda, contatto, telefono, email, settore_note)
            VALUES (%s, %s, %s, %s, %s);
        """, (nome_azienda, contatto, telefono, email, settore_note))
        conn.commit()
        cur.close()
        conn.close()
        flash(f"Fornitore {nome_azienda} aggiunto con successo!", "success")
    except Exception as e:
        flash(f"Errore salvataggio fornitore: {e}", "error")

    return redirect(url_for("index"))

# --- STAMPE ---
@app.route("/stampa_bolla/<qr_code>")
def stampa_bolla(qr_code):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM prodotti WHERE qr_code = %s;", (qr_code,))
    prodotto = cur.fetchone()
    cur.close()
    conn.close()

    if not prodotto:
        flash("Prodotto non trovato.", "error")
        return redirect(url_for("index"))

    return render_template("bolla.html", prodotto=prodotto)

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

    return render_template("stampa_qr.html", prodotto=prodotto)

if __name__ == "_main_":
    app.run(debug=True, host="0.0.0.0", port=5000)
