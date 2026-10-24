# ========================================================================
# Gestionale OMG Application - Complete System with Auto-QR & Notifications
# Copyright (c) 2026 Marco Pavan. All Rights Reserved.
# Designed & Developed by Marco Pavan
# ========================================================================

import os
import csv
import io
import re
from datetime import datetime, timedelta
import pandas as pd
import psycopg2
from psycopg2.extras import RealDictCursor
from flask import Flask, render_template, request, redirect, url_for, flash, session, send_file, Response, jsonify
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
        cur.execute(
            "INSERT INTO log_attivita (username, descrizione) VALUES (%s, %s);",
            (username, descrizione)
        )
        conn.commit()
        cur.close()
        conn.close()
    except Exception as e:
        print(f"Errore registrazione log: {e}")

def crea_notifica(destinatario, titolo, messaggio, link=""):
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO notifiche (destinatario, titolo, messaggio, link)
            VALUES (%s, %s, %s, %s);
        """, (destinatario, titolo, messaggio, link))
        conn.commit()
        cur.close()
        conn.close()
    except Exception as e:
        print(f"Errore inserimento notifica: {e}")

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
        
        permessi_lista = [
            ("puo_vedere_magazzino", "INT DEFAULT 1"),
            ("puo_aggiungere_prodotti", "INT DEFAULT 1"),
            ("puo_modificare_prodotti", "INT DEFAULT 1"),
            ("puo_caricare_scaricare", "INT DEFAULT 1"),
            ("puo_eliminare", "INT DEFAULT 0"),
            ("puo_vedere_pesante", "INT DEFAULT 1"),
            ("puo_vedere_manutenzione", "INT DEFAULT 1"),
            ("puo_aprire_manutenzioni", "INT DEFAULT 1"),
            ("puo_gestire_interventi", "INT DEFAULT 1"),
            ("puo_assegnare_manutenzioni", "INT DEFAULT 1"),
            ("puo_eliminare_interventi", "INT DEFAULT 0"),
            ("puo_vedere_manutenzioni_esterne", "INT DEFAULT 1"),
            ("puo_vedere_storico_manutenzioni", "INT DEFAULT 1"),
            ("puo_eliminare_storico", "INT DEFAULT 0"),
            ("puo_gestire_fornitori", "INT DEFAULT 1"),
            ("puo_importare_fornitori", "INT DEFAULT 1"),
            ("puo_gestire_documenti", "INT DEFAULT 1"),
            ("puo_eliminare_documenti", "INT DEFAULT 0"),
            ("puo_vedere_promemoria", "INT DEFAULT 1"),
            ("puo_assegnare_promemoria", "INT DEFAULT 0"),
            ("puo_vedere_report_ore", "INT DEFAULT 1")
        ]
        
        for p_col, p_type in permessi_lista:
            cur.execute(f"ALTER TABLE utenti ADD COLUMN IF NOT EXISTS {p_col} {p_type};")
        
        cur.execute("SELECT * FROM utenti WHERE username = 'admin';")
        if not cur.fetchone():
            hashed_pw = generate_password_hash("admin")
            cur.execute("""
                INSERT INTO utenti (username, password, is_admin, puo_vedere_magazzino, puo_aggiungere_prodotti, puo_modificare_prodotti, puo_caricare_scaricare, puo_eliminare, puo_vedere_pesante, puo_vedere_manutenzione, puo_aprire_manutenzioni, puo_gestire_interventi, puo_assegnare_manutenzioni, puo_eliminare_interventi, puo_vedere_manutenzioni_esterne, puo_vedere_storico_manutenzioni, puo_eliminare_storico, puo_gestire_fornitori, puo_importare_fornitori, puo_gestire_documenti, puo_eliminare_documenti, puo_vedere_promemoria, puo_assegnare_promemoria, puo_vedere_report_ore)
                VALUES (%s, %s, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1);
            """, ('admin', hashed_pw))

        # Allineamento automatico della sequenza ID
        cur.execute("""
            SELECT setval('prodotti_id_seq', COALESCE((SELECT MAX(id) FROM prodotti), 0) + 1, false);
        """)

        conn.commit()
        cur.close()
        conn.close()
        print("Database e permessi Gestionale OMG inizializzati.")
    except Exception as e:
        print(f"Errore init_db: {e}")

init_db()

@app.before_request
def require_login():
    allowed_routes = ['login', 'registra', 'static']
    if request.endpoint and request.endpoint not in allowed_routes and 'username' not in session:
        return redirect(url_for('login'))

@app.route("/api/notifiche")
def api_notifiche():
    username = session.get('username')
    if not username:
        return jsonify([])
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT id, titolo, messaggio, link, letta, creato_il 
        FROM notifiche 
        WHERE destinatario = %s 
        ORDER BY creato_il DESC LIMIT 15;
    """, (username,))
    notifiche = cur.fetchall()
    cur.close()
    conn.close()
    return jsonify(notifiche)

@app.route("/api/notifiche/segna_lette", methods=["POST"])
def api_segna_lette():
    username = session.get('username')
    if username:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("UPDATE notifiche SET letta = TRUE WHERE destinatario = %s;", (username,))
        conn.commit()
        cur.close()
        conn.close()
    return jsonify({"status": "ok"})

@app.route("/")
@app.route("/index")
@app.route("/index.html")
def index():
    prodotti = []
    prodotti_sotto_soglia = []
    promemoria_urgenti = 0
    interventi_aperti_count = 0
    interventi_in_lavoro_count = 0
    notifiche_attive = []
    
    username = session.get('username')
    is_admin = session.get('is_admin')
    puo_assegnare = session.get('puo_assegnare_promemoria')
    
    totale_pezzi_tutti = 0
    totale_articoli_tutti = 0
    
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        cur.execute("SELECT * FROM prodotti ORDER BY nome ASC;")
        tutti = cur.fetchall()
        
        # Totale pezzi e articoli uniti (Standard + Pesante)
        totale_articoli_tutti = len(tutti)
        totale_pezzi_tutti = sum(p.get('quantita', 0) for p in tutti)
        
        # Recupero notifiche non lette per l'utente loggato
        if username:
            cur.execute("""
                SELECT id, titolo, messaggio, link, to_char(creato_il, 'YYYY-MM-DD HH24:MI') as data 
                FROM notifiche 
                WHERE destinatario = %s AND letta = FALSE 
                ORDER BY creato_il DESC;
            """, (username,))
            notifiche_attive = cur.fetchall()
        
        if is_admin or puo_assegnare:
            cur.execute("SELECT COUNT(*) as count FROM promemoria WHERE completato = FALSE;")
        else:
            cur.execute("SELECT COUNT(*) as count FROM promemoria WHERE completato = FALSE AND (assegnato_a = %s OR assegnato_a IS NULL OR assegnato_a = '');", (username,))
        res_p = cur.fetchone()
        if res_p:
            promemoria_urgenti = res_p['count']
            
        cur.execute("SELECT COUNT(*) as count FROM richieste_manutenzione WHERE stato = 'Aperta';")
        interventi_aperti_count = cur.fetchone()['count']
        cur.execute("SELECT COUNT(*) as count FROM richieste_manutenzione WHERE stato IN ('In Lavoro', 'In Pausa');")
        interventi_in_lavoro_count = cur.fetchone()['count']
        
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
                           promemoria_urgenti=promemoria_urgenti,
                           interventi_aperti_count=interventi_aperti_count,
                           interventi_in_lavoro_count=interventi_in_lavoro_count,
                           notifiche_attive=notifiche_attive,
                           totale_pezzi_tutti=totale_pezzi_tutti,
                           totale_articoli_tutti=totale_articoli_tutti)

@app.route("/login", methods=["GET", "POST"])
@app.route("/login.html", methods=["GET", "POST"])
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
                for k in user.keys():
                    if k.startswith('puo_'):
                        session[k] = user.get(k, 1)
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
@app.route("/registra.html", methods=["GET", "POST"])
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
                    INSERT INTO utenti (username, password, is_admin, puo_vedere_magazzino, puo_aggiungere_prodotti, puo_modificare_prodotti, puo_caricare_scaricare, puo_eliminare, puo_vedere_pesante, puo_vedere_manutenzione, puo_aprire_manutenzioni, puo_gestire_interventi, puo_assegnare_manutenzioni, puo_eliminare_interventi, puo_vedere_manutenzioni_esterne, puo_vedere_storico_manutenzioni, puo_eliminare_storico, puo_gestire_fornitori, puo_importare_fornitori, puo_gestire_documenti, puo_eliminare_documenti, puo_vedere_promemoria, puo_assegnare_promemoria, puo_vedere_report_ore)
                    VALUES (%s, %s, 0, 1, 1, 1, 1, 0, 1, 1, 1, 1, 1, 0, 1, 1, 0, 1, 1, 1, 0, 1, 0, 1);
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

@app.route("/admin_utenti")
def admin_utenti():
    if not session.get('is_admin'):
        flash("Accesso riservato.", "error")
        return redirect(url_for('index'))
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM utenti ORDER BY username ASC;")
    utenti = cur.fetchall()
    cur.execute("SELECT * FROM log_attivita ORDER BY data_ora DESC LIMIT 100;")
    logs = cur.fetchall()
    cur.close()
    conn.close()
    return render_template("admin_utenti.html", utenti=utenti, logs=logs)

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
        writer.writerow([p.get('qr_code', ''), p.get('nome', ''), p.get('sap', ''), p.get('quantita', 0), p.get('posizione', ''), p.get('peso', ''), 'Si' if p.get('magazzino_pesante') else 'No'])
    return Response(output.getvalue(), mimetype="text/csv", headers={"Content-disposition": "attachment; filename=Inventario_Gestionale_OMG.csv"})

@app.route("/carico", methods=["GET", "POST"])
def carico():
    if request.method == "POST":
        qr = request.form.get("qr_code")
        qta = int(request.form.get("quantita", 1))
        if qr:
            conn = get_db_connection()
            cur = conn.cursor()
            cur.execute("UPDATE prodotti SET quantita = quantita + %s WHERE qr_code = %s;", (qta, qr))
            conn.commit()
            cur.close()
            conn.close()
            flash("Carico effettuato!", "success")
            return redirect(url_for("gestisci_prodotto", qr_code=qr))
    return render_template("carico.html")

@app.route("/scarico", methods=["GET", "POST"])
def scarico():
    if request.method == "POST":
        qr = request.form.get("qr_code")
        qta = int(request.form.get("quantita", 1))
        if qr:
            conn = get_db_connection()
            cur = conn.cursor()
            cur.execute("UPDATE prodotti SET quantita = GREATEST(0, quantita - %s) WHERE qr_code = %s;", (qta, qr))
            conn.commit()
            cur.close()
            conn.close()
            flash("Scarico effettuato!", "success")
            return redirect(url_for("gestisci_prodotto", qr_code=qr))
    return render_template("scarico.html")

@app.route("/scanner_globale", methods=["GET", "POST"])
def scanner_globale():
    if request.method == "POST":
        qr = request.form.get("qr_code", "").strip()
        if qr:
            return redirect(url_for("gestisci_prodotto", qr_code=qr))
    return render_template("scanner_globale.html")

@app.route("/gestisci/<qr_code>")
def gestisci_prodotto(qr_code):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM prodotti WHERE qr_code = %s;", (qr_code,))
    prodotto = cur.fetchone()
    cur.close()
    conn.close()
    if not prodotto:
        flash("Prodotto non trovato.", "error")
        return redirect(url_for("index"))
    return render_template("gestisci.html", prodotto=prodotto, fornitori=[])

@app.route("/aggiungi", methods=["POST"])
def aggiungi_prodotto():
    if not (session.get('is_admin') or session.get('puo_aggiungere_prodotti', 1)):
        flash("Permesso negato.", "error")
        return redirect(url_for("index"))

    nome = request.form.get("nome")
    sap = request.form.get("sap", "")
    peso = request.form.get("peso", "")
    quantita = int(request.form.get("quantita", 0) or 0)
    soglia_minima = int(request.form.get("soglia_minima", 3) or 3)
    posizione = request.form.get("posizione", "")
    flag_sezione = 1 if request.form.get("magazzino_pesante") else 0

    if not nome:
        flash("Il nome dell'articolo è obbligatorio!", "error")
        return redirect(url_for("index"))

    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # 1. Inserimento temporaneo con QR 'TEMP' per risalire all'ID progressivo
        cur.execute("""
            INSERT INTO prodotti (qr_code, nome, sap, peso, quantita, posizione, magazzino_pesante, soglia_minima)
            VALUES ('TEMP', %s, %s, %s, %s, %s, %s, %s)
            RETURNING id;
        """, (nome, sap, peso, quantita, posizione, flag_sezione, soglia_minima))
        
        row = cur.fetchone()
        prodotto_id = row['id'] if isinstance(row, dict) else row[0]
        
        # 2. Generazione del QR code progressivo (es. OMG-0001, OMG-0002...)
        qr_code_progressivo = f"OMG-{prodotto_id:04d}"
        
        # 3. Aggiornamento con il QR code definitivo
        cur.execute("""
            UPDATE prodotti SET qr_code = %s WHERE id = %s;
        """, (qr_code_progressivo, prodotto_id))
        
        conn.commit()
        cur.close()
        conn.close()
        registra_log(f"Aggiunto prodotto: {nome} (QR: {qr_code_progressivo})")
        flash(f"Prodotto salvato con successo! QR Code generato: {qr_code_progressivo}", "success")
    except Exception as e:
        flash(f"Errore: {e}", "error")

    if flag_sezione == 1:
        return redirect(url_for("magazzino_pesante"))
    return redirect(url_for("index"))

@app.route("/magazzino_pesante")
def magazzino_pesante():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM prodotti WHERE magazzino_pesante = 1 ORDER BY nome ASC;")
    prodotti = cur.fetchall()
    cur.close()
    conn.close()
    return render_template("magazzino_pesante.html", prodotti=prodotti)

@app.route("/stampa_tutti_qr")
def stampa_tutti_qr():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM prodotti ORDER BY nome ASC;")
    prodotti = cur.fetchall()
    cur.close()
    conn.close()
    return render_template("stampa_tutti_qr.html", prodotti=prodotti)

@app.route("/richieste_manutenzione")
def richieste_manutenzione():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM richieste_manutenzione ORDER BY id DESC;")
    richieste = cur.fetchall()
    cur.close()
    conn.close()
    return render_template("richieste_manutenzione.html", richieste=richieste, lista_utenti=[], lista_prodotti=[])

@app.route("/promemoria")
def promemoria():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM promemoria ORDER BY id DESC;")
    lista = cur.fetchall()
    cur.close()
    conn.close()
    return render_template("promemoria.html", promemoria=lista, lista_utenti=[])

@app.route("/fornitori")
def fornitori():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM fornitori ORDER BY nome_azienda ASC;")
    lista = cur.fetchall()
    cur.close()
    conn.close()
    return render_template("fornitori.html", fornitori=lista)

@app.route("/documenti", defaults={"cartella_id": None})
@app.route("/documenti/<int:cartella_id>")
def documenti(cartella_id=None):
    return render_template("documenti.html", cartella_corrente=None, sottocartelle=[], lista_file=[], percorso_breadcrumb=[])

@app.route("/cambi_serie")
def cambi_serie():
    return render_template("cambi_serie.html", cambi=[])

@app.route("/report_ore")
def report_ore():
    return render_template("report_ore.html", chart_tecnici_labels=[], chart_tecnici_values=[], chart_tipi_labels=[], chart_tipi_values=[], interventi=[])

@app.route("/storico_manutenzioni")
def storico_manutenzioni():
    return render_template("storico_manutenzioni.html", storico=[])

@app.route("/esportazioni")
def esportazioni():
    return render_template("esportazioni.html")

if __name__ == "__main__":
    app.run(debug=True)
