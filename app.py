# ========================================================================
# Gestionale OMG Application - Complete System
# Copyright (c) 2026 Marco Pavan. All Rights Reserved.
# ========================================================================

import os
import csv
import io
from datetime import datetime
import psycopg2
from psycopg2.extras import RealDictCursor
from flask import Flask, render_template, request, redirect, url_for, flash, session, Response, jsonify
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "chiave-segreta-gestionale")

DATABASE_URL = os.environ.get("DATABASE_URL")

def get_db_connection():
    return psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)

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
        print(f"Errore log: {e}")

def init_db():
    if not DATABASE_URL:
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
                note_manutenzione TEXT,
                soglia_minima INT DEFAULT 3
            );
        """)
        
        cur.execute("""
            CREATE TABLE IF NOT EXISTS fornitori (
                id SERIAL PRIMARY KEY,
                nome_azienda VARCHAR(255) UNIQUE NOT NULL,
                settore_note VARCHAR(255),
                indirizzo VARCHAR(255),
                p_iva VARCHAR(255),
                telefono VARCHAR(255),
                email VARCHAR(255)
            );
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS contatti_tecnici (
                id SERIAL PRIMARY KEY,
                fornitore_id INT REFERENCES fornitori(id) ON DELETE CASCADE,
                nome VARCHAR(255) NOT NULL,
                telefono VARCHAR(255) NOT NULL,
                mansione VARCHAR(255),
                email VARCHAR(255)
            );
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS promemoria (
                id SERIAL PRIMARY KEY,
                titolo VARCHAR(255) NOT NULL,
                descrizione TEXT,
                data_scadenza VARCHAR(255),
                priorita VARCHAR(50) DEFAULT 'Media',
                ricorrenza VARCHAR(50) DEFAULT 'Nessuna',
                assegnato_a VARCHAR(255),
                completato BOOLEAN DEFAULT FALSE,
                creato_il TIMESTAMP DEFAULT CURRENT_TIMESTAMP
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
                assegnato_a TEXT,
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
            CREATE TABLE IF NOT EXISTS intervento_ricambi (
                id SERIAL PRIMARY KEY,
                intervento_id INT REFERENCES richieste_manutenzione(id) ON DELETE CASCADE,
                qr_code VARCHAR(255),
                nome_ricambio VARCHAR(255),
                quantita INT DEFAULT 1
            );
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS utenti (
                id SERIAL PRIMARY KEY,
                username VARCHAR(255) UNIQUE NOT NULL,
                password VARCHAR(255) NOT NULL,
                is_admin INT DEFAULT 0,
                puo_vedere_magazzino INT DEFAULT 1,
                puo_aggiungere_prodotti INT DEFAULT 1,
                puo_modificare_prodotti INT DEFAULT 1,
                puo_caricare_scaricare INT DEFAULT 1,
                puo_eliminare INT DEFAULT 0,
                puo_vedere_pesante INT DEFAULT 1,
                puo_vedere_manutenzione INT DEFAULT 1,
                puo_aprire_manutenzioni INT DEFAULT 1,
                puo_gestire_interventi INT DEFAULT 1,
                puo_assegnare_manutenzioni INT DEFAULT 1,
                puo_eliminare_interventi INT DEFAULT 0,
                puo_vedere_manutenzioni_esterne INT DEFAULT 1,
                puo_vedere_storico_manutenzioni INT DEFAULT 1,
                puo_eliminare_storico INT DEFAULT 0,
                puo_gestire_fornitori INT DEFAULT 1,
                puo_importare_fornitori INT DEFAULT 1,
                puo_gestire_documenti INT DEFAULT 1,
                puo_eliminare_documenti INT DEFAULT 0,
                puo_vedere_promemoria INT DEFAULT 1,
                puo_assegnare_promemoria INT DEFAULT 0,
                puo_vedere_report_ore INT DEFAULT 1
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
            CREATE TABLE IF NOT EXISTS log_attivita (
                id SERIAL PRIMARY KEY,
                data_ora TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                username VARCHAR(255),
                descrizione TEXT
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

        cur.execute("""
            CREATE TABLE IF NOT EXISTS notifiche (
                id SERIAL PRIMARY KEY,
                destinatario VARCHAR(255) NOT NULL,
                titolo VARCHAR(255) NOT NULL,
                messaggio TEXT NOT NULL,
                link VARCHAR(255),
                letta BOOLEAN DEFAULT FALSE,
                creato_il TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        
        cur.execute("SELECT * FROM utenti WHERE username = 'admin';")
        if not cur.fetchone():
            hashed_pw = generate_password_hash("admin")
            cur.execute("""
                INSERT INTO utenti (username, password, is_admin, puo_vedere_magazzino, puo_aggiungere_prodotti, puo_modificare_prodotti, puo_caricare_scaricare, puo_eliminare, puo_vedere_pesante, puo_vedere_manutenzione, puo_aprire_manutenzioni, puo_gestire_interventi, puo_assegnare_manutenzioni, puo_eliminare_interventi, puo_vedere_manutenzioni_esterne, puo_vedere_storico_manutenzioni, puo_eliminare_storico, puo_gestire_fornitori, puo_importare_fornitori, puo_gestire_documenti, puo_eliminare_documenti, puo_vedere_promemoria, puo_assegnare_promemoria, puo_vedere_report_ore)
                VALUES (%s, %s, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1);
            """, ('admin', hashed_pw))

        conn.commit()
        cur.close()
        conn.close()
    except Exception as e:
        print(f"Errore init_db: {e}")

init_db()

@app.before_request
def require_login():
    allowed_routes = ['login', 'registra', 'static']
    if request.endpoint and request.endpoint not in allowed_routes and 'username' not in session:
        return redirect(url_for('login'))

@app.route("/")
@app.route("/index")
def index():
    prodotti, prodotti_sotto_soglia = [], []
    promemoria_urgenti = 0
    interventi_aperti_count = 0
    interventi_in_lavoro_count = 0
    interventi_attesa_count = 0
    interventi_assegnati_count = 0
    notifiche_attive = []
    
    username = session.get('username')
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT * FROM prodotti ORDER BY nome ASC;")
        tutti = cur.fetchall()
        
        cur.execute("SELECT COUNT(*) as count FROM promemoria WHERE completato = FALSE;")
        res_p = cur.fetchone()
        if res_p:
            promemoria_urgenti = res_p['count']
            
        cur.execute("SELECT COUNT(*) as count FROM richieste_manutenzione WHERE stato = 'Aperta';")
        res_io = cur.fetchone()
        if res_io:
            interventi_aperti_count = res_io['count']

        cur.execute("SELECT COUNT(*) as count FROM richieste_manutenzione WHERE stato IN ('In Lavoro', 'In Pausa');")
        res_il = cur.fetchone()
        if res_il:
            interventi_in_lavoro_count = res_il['count']

        cur.execute("SELECT COUNT(*) as count FROM richieste_manutenzione WHERE stato = 'Attesa Ricambio';")
        res_ia = cur.fetchone()
        if res_ia:
            interventi_attesa_count = res_ia['count']

        if username:
            cur.execute("SELECT COUNT(*) as count FROM richieste_manutenzione WHERE stato != 'Completata' AND assegnato_a LIKE %s;", (f"%{username}%",))
            res_int = cur.fetchone()
            if res_int:
                interventi_assegnati_count = res_int['count']

            cur.execute("SELECT * FROM notifiche WHERE destinatario = %s AND letta = FALSE ORDER BY creato_il DESC;", (username,))
            for n in cur.fetchall():
                notifiche_attive.append({
                    'titolo': n['titolo'], 
                    'messaggio': n['messaggio'], 
                    'link': n['link'],
                    'data': n['creato_il'].strftime('%d/%m/%Y %H:%M') if n['creato_il'] else ''
                })

        cur.close()
        conn.close()
        
        for p in tutti:
            if not p.get('magazzino_pesante'):
                prodotti.append(p)
            if p.get('quantita', 0) <= (p.get('soglia_minima', 3) or 3):
                prodotti_sotto_soglia.append(p)
    except Exception as e:
        print(f"Errore index: {e}")
        
    return render_template("index.html", 
                           prodotti=prodotti, 
                           prodotti_sotto_soglia=prodotti_sotto_soglia,
                           promemoria_urgenti=promemoria_urgenti,
                           interventi_aperti_count=interventi_aperti_count,
                           interventi_in_lavoro_count=interventi_in_lavoro_count,
                           interventi_attesa_count=interventi_attesa_count,
                           interventi_assegnati_count=interventi_assegnati_count,
                           notifiche_attive=notifiche_attive)

@app.route("/magazzino_pesante")
def magazzino_pesante():
    prodotti = []
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT * FROM prodotti ORDER BY nome ASC;")
        for p in cur.fetchall():
            if p.get('magazzino_pesante'):
                prodotti.append(p)
        cur.close()
        conn.close()
    except Exception:
        pass
    return render_template("magazzino_pesante.html", prodotti=prodotti)

@app.route("/esportazioni")
def esportazioni():
    return render_template("esportazioni.html")

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
    return Response(output.getvalue(), mimetype="text/csv", headers={"Content-disposition": "attachment; filename=Inventario.csv"})

@app.route("/esporta_interventi")
def esporta_interventi():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT id, titolo, impianto_macchina, priorita, tipo_guasto, stato, assegnato_a, creato_da, inizio_lavoro, fine_lavoro, tempo_lavorato_minuti, note_lavoro FROM richieste_manutenzione ORDER BY creato_il DESC;")
    richieste = cur.fetchall()
    cur.close()
    conn.close()
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['ID', 'Titolo', 'Macchina', 'Priorità', 'Tipo Guasto', 'Stato', 'Assegnato A', 'Creato Da', 'Inizio', 'Fine', 'Minuti', 'Note'])
    for r in richieste:
        writer.writerow([r['id'], r['titolo'], r['impianto_macchina'], r['priorita'], r['tipo_guasto'], r['stato'], r['assegnato_a'], r['creato_da'], r['inizio_lavoro'], r['fine_lavoro'], r['tempo_lavorato_minuti'], r['note_lavoro']])
    return Response(output.getvalue(), mimetype="text/csv", headers={"Content-disposition": "attachment; filename=Report_Interventi.csv"})

@app.route("/stampa_tutti_qr")
def stampa_tutti_qr():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM prodotti ORDER BY nome ASC;")
    prodotti = cur.fetchall()
    cur.close()
    conn.close()
    return render_template("stampa_tutti_qr.html", prodotti=prodotti)

@app.route("/stampa_multipla_qr")
def stampa_multipla_qr():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM prodotti ORDER BY nome ASC;")
    prodotti = cur.fetchall()
    cur.close()
    conn.close()
    return render_template("stampa_multipla_qr.html", prodotti=prodotti)

@app.route("/stampa_singolo_qr/<qr_code>")
def stampa_singolo_qr(qr_code):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM prodotti WHERE qr_code = %s;", (qr_code,))
    prodotto = cur.fetchone()
    cur.close()
    conn.close()
    return render_template("stampa_singolo_qr.html", prodotto=prodotto)

@app.route("/stampa_intervento/<int:intervento_id>")
def stampa_intervento(intervento_id):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM richieste_manutenzione WHERE id = %s;", (intervento_id,))
    intervento = cur.fetchone()
    cur.close()
    conn.close()
    return render_template("stampa_intervento.html", intervento=intervento)

@app.route("/cambi_serie")
def cambi_serie():
    return render_template("cambi_serie.html", cambi=[])

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT * FROM utenti WHERE username = %s;", (username,))
        user = cur.fetchone()
        cur.close()
        conn.close()
        if user and check_password_hash(user['password'], password):
            session['username'] = user['username']
            session['is_admin'] = user['is_admin']
            registra_log("Login effettuato")
            return redirect(url_for('index'))
        flash("Credenziali non valide", "error")
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
            conn = get_db_connection()
            cur = conn.cursor()
            try:
                cur.execute("INSERT INTO utenti (username, password) VALUES (%s, %s);", (username, generate_password_hash(password)))
                conn.commit()
                flash("Registrazione completata", "success")
                return redirect(url_for('login'))
            except Exception:
                flash("Utente già esistente", "error")
            cur.close()
            conn.close()
    return render_template("registra.html")

@app.route("/admin_utenti")
def admin_utenti():
    if not session.get('is_admin'):
        return redirect(url_for('index'))
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM utenti ORDER BY username ASC;")
    utenti = cur.fetchall()
    cur.execute("SELECT * FROM log_attivita ORDER BY data_ora DESC LIMIT 50;")
    logs = cur.fetchall()
    cur.close()
    conn.close()
    return render_template("admin_utenti.html", utenti=utenti, logs=logs)

@app.route("/toggle_permesso/<int:user_id>/<campo>", methods=["POST"])
def toggle_permesso(user_id, campo):
    if session.get('is_admin') and campo.startswith("puo_"):
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute(f"UPDATE utenti SET {campo} = 1 - COALESCE({campo}, 0) WHERE id = %s;", (user_id,))
        conn.commit()
        cur.close()
        conn.close()
    return redirect(url_for('admin_utenti'))

@app.route("/reset_password/<int:user_id>", methods=["POST"])
def reset_password(user_id):
    if session.get('is_admin') and request.form.get("nuova_password"):
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("UPDATE utenti SET password = %s WHERE id = %s;", (generate_password_hash(request.form.get("nuova_password")), user_id))
        conn.commit()
        cur.close()
        conn.close()
    return redirect(url_for('admin_utenti'))

@app.route("/elimina_utente/<int:user_id>", methods=["POST"])
def elimina_utente(user_id):
    if session.get('is_admin'):
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("DELETE FROM utenti WHERE id = %s AND username != 'admin';", (user_id,))
        conn.commit()
        cur.close()
        conn.close()
    return redirect(url_for('admin_utenti'))

@app.route("/report_ore")
def report_ore():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT username FROM utenti ORDER BY username ASC;")
    utenti = cur.fetchall()
    cur.execute("SELECT * FROM richieste_manutenzione ORDER BY creato_il DESC;")
    interventi = cur.fetchall()
    cur.close()
    conn.close()
    return render_template("report_ore.html", utenti=utenti, interventi=interventi, totale_ore_generale=0, totale_interventi=len(interventi))

@app.route("/richieste_manutenzione", methods=["GET", "POST"])
def richieste_manutenzione():
    conn = get_db_connection()
    cur = conn.cursor()
    if request.method == "POST":
        titolo = request.form.get("titolo")
        if titolo:
            cur.execute("INSERT INTO richieste_manutenzione (titolo, impianto_macchina, descrizione, priorita, tipo_guasto, assegnato_a, creato_da, stato) VALUES (%s, %s, %s, %s, %s, %s, %s, 'Aperta');",
                        (titolo, request.form.get("impianto_macchina"), request.form.get("descrizione"), request.form.get("priorita", "Media"), request.form.get("tipo_guasto", "Meccanico"), request.form.get("assegnato_a"), session.get('username')))
            conn.commit()
        return redirect(url_for("richieste_manutenzione"))
    cur.execute("SELECT username FROM utenti ORDER BY username ASC;")
    lista_utenti = cur.fetchall()
    cur.execute("SELECT qr_code, nome, quantita FROM prodotti ORDER BY nome ASC;")
    lista_prodotti = cur.fetchall()
    cur.execute("SELECT * FROM richieste_manutenzione ORDER BY creato_il DESC;")
    richieste = cur.fetchall()
    cur.close()
    conn.close()
    return render_template("richieste_manutenzione.html", richieste=richieste, lista_utenti=lista_utenti, lista_prodotti=lista_prodotti, ricambi_per_intervento={})

@app.route("/cambia_stato_intervento/<int:intervento_id>", methods=["POST"])
def cambia_stato_intervento(intervento_id):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("UPDATE richieste_manutenzione SET stato = %s, note_lavoro = %s WHERE id = %s;", (request.form.get("stato"), request.form.get("note_lavoro"), intervento_id))
    conn.commit()
    cur.close()
    conn.close()
    return redirect(url_for("richieste_manutenzione"))

@app.route("/promemoria", methods=["GET", "POST"])
def promemoria():
    conn = get_db_connection()
    cur = conn.cursor()
    if request.method == "POST" and request.form.get("titolo"):
        cur.execute("INSERT INTO promemoria (titolo, descrizione, data_scadenza, priorita, ricorrenza, assegnato_a) VALUES (%s, %s, %s, %s, %s, %s);",
                    (request.form.get("titolo"), request.form.get("descrizione"), request.form.get("data_scadenza"), request.form.get("priorita"), request.form.get("ricorrenza"), request.form.get("assegnato_a")))
        conn.commit()
    cur.execute("SELECT * FROM promemoria ORDER BY completato ASC;")
    lista_promemoria = cur.fetchall()
    cur.execute("SELECT username FROM utenti ORDER BY username ASC;")
    lista_utenti = cur.fetchall()
    cur.close()
    conn.close()
    return render_template("promemoria.html", promemoria=lista_promemoria, lista_utenti=lista_utenti)

@app.route("/fornitori", methods=["GET", "POST"])
def fornitori():
    conn = get_db_connection()
    cur = conn.cursor()
    if request.method == "POST" and request.form.get("nome_azienda"):
        cur.execute("INSERT INTO fornitori (nome_azienda, settore_note, indirizzo, p_iva, telefono, email) VALUES (%s, %s, %s, %s, %s, %s) ON CONFLICT (nome_azienda) DO NOTHING;",
                    (request.form.get("nome_azienda"), request.form.get("settore_note"), request.form.get("indirizzo"), request.form.get("p_iva"), request.form.get("telefono"), request.form.get("email")))
        conn.commit()
    cur.execute("SELECT * FROM fornitori ORDER BY nome_azienda ASC;")
    lista = cur.fetchall()
    cur.close()
    conn.close()
    return render_template("fornitori.html", fornitori=lista)

@app.route("/fornitore/<int:forn_id>")
def dettaglio_fornitore(forn_id):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM fornitori WHERE id = %s;", (forn_id,))
    fornitore = cur.fetchone()
    cur.execute("SELECT * FROM contatti_tecnici WHERE fornitore_id = %s;", (forn_id,))
    contatti = cur.fetchall()
    cur.close()
    conn.close()
    return render_template("dettaglio_fornitore.html", fornitore=fornitore, contatti=contatti)

@app.route("/documenti", defaults={"cartella_id": None}, methods=["GET", "POST"])
@app.route("/documenti/<int:cartella_id>", methods=["GET", "POST"])
def documenti(cartella_id):
    conn = get_db_connection()
    cur = conn.cursor()
    if request.method == "POST":
        if request.form.get("azione") == "crea_cartella":
            cur.execute("INSERT INTO cartelle (nome, parent_id) VALUES (%s, %s);", (request.form.get("nome_cartella"), cartella_id))
            conn.commit()
        elif request.files.get("file_caricato"):
            f = request.files.get("file_caricato")
            cur.execute("INSERT INTO documenti (cartella_id, nome_file, tipo_file, dati_file) VALUES (%s, %s, %s, %s);", (cartella_id, f.filename, f.mimetype, f.read()))
            conn.commit()
    cur.execute("SELECT * FROM cartelle WHERE parent_id " + ("= %s" if cartella_id else "IS NULL"), (cartella_id,) if cartella_id else ())
    sottocartelle = cur.fetchall()
    cur.execute("SELECT id, nome_file FROM documenti WHERE cartella_id " + ("= %s" if cartella_id else "IS NULL"), (cartella_id,) if cartella_id else ())
    lista_file = cur.fetchall()
    cur.close()
    conn.close()
    return render_template("documenti.html", sottocartelle=sottocartelle, lista_file=lista_file, cartella_corrente=None, percorso_breadcrumb=[])

@app.route("/manutenzioni")
def manutenzioni():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM prodotti WHERE in_manutenzione = TRUE ORDER BY nome ASC;")
    prodotti = cur.fetchall()
    cur.close()
    conn.close()
    return render_template("manutenzioni.html", prodotti=prodotti)

@app.route("/storico_manutenzioni")
def storico_manutenzioni():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM storico_manutenzioni ORDER BY registrato_il DESC;")
    storico = cur.fetchall()
    cur.close()
    conn.close()
    return render_template("storico_manutenzioni.html", storico=storico)

@app.route("/carico", methods=["GET", "POST"])
def carico():
    if request.method == "POST" and request.form.get("qr_code"):
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("UPDATE prodotti SET quantita = quantita + %s WHERE qr_code = %s;", (int(request.form.get("quantita", 1)), request.form.get("qr_code")))
        conn.commit()
        cur.close()
        conn.close()
        return redirect(url_for("gestisci_prodotto", qr_code=request.form.get("qr_code")))
    return render_template("carico.html")

@app.route("/scarico", methods=["GET", "POST"])
def scarico():
    if request.method == "POST" and request.form.get("qr_code"):
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT quantita FROM prodotti WHERE qr_code = %s;", (request.form.get("qr_code"),))
        prod = cur.fetchone()
        if prod:
            nuova = max(0, prod['quantita'] - int(request.form.get("quantita", 1)))
            cur.execute("UPDATE prodotti SET quantita = %s WHERE qr_code = %s;", (nuova, request.form.get("qr_code")))
            conn.commit()
        cur.close()
        conn.close()
        return redirect(url_for("gestisci_prodotto", qr_code=request.form.get("qr_code")))
    return render_template("scarico.html")

@app.route("/scanner_globale", methods=["GET", "POST"])
def scanner_globale():
    if request.method == "POST" and request.form.get("qr_code"):
        return redirect(url_for("gestisci_prodotto", qr_code=request.form.get("qr_code").strip()))
    return render_template("scanner_globale.html")

@app.route("/gestisci/<qr_code>")
def gestisci_prodotto(qr_code):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM prodotti WHERE qr_code = %s;", (qr_code,))
    prodotto = cur.fetchone()
    cur.close()
    conn.close()
    return render_template("gestisci.html", prodotto=prodotto)

@app.route("/aggiorna_prodotto/<qr_code>", methods=["POST"])
def modifica_prodotto(qr_code):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("UPDATE prodotti SET nome = %s, sap = %s, peso = %s, posizione = %s, soglia_minima = %s WHERE qr_code = %s;",
                (request.form.get("nome"), request.form.get("sap"), request.form.get("peso"), request.form.get("posizione"), int(request.form.get("soglia_minima", 3)), qr_code))
    conn.commit()
    cur.close()
    conn.close()
    return redirect(url_for("gestisci_prodotto", qr_code=qr_code))

@app.route("/aggiungi_prodotto", methods=["POST"])
def aggiungi_prodotto():
    qr = request.form.get("qr_code")
    nome = request.form.get("nome")
    flag = 1 if request.form.get("magazzino_pesante") else 0
    if qr and nome:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("INSERT INTO prodotti (qr_code, nome, sap, quantita, posizione, magazzino_pesante) VALUES (%s, %s, %s, %s, %s, %s) ON CONFLICT (qr_code) DO UPDATE SET quantita = prodotti.quantita + EXCLUDED.quantita;",
                    (qr, nome, request.form.get("sap"), int(request.form.get("quantita", 0)), request.form.get("posizione"), flag))
        conn.commit()
        cur.close()
        conn.close()
    return redirect(url_for("magazzino_pesante") if flag == 1 else url_for("index"))

if __name__ == "__main__":
    app.run(debug=True)
