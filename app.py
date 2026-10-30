# ========================================================================
# Gestionale OMG Application - System with Push Notifications & Ore Report
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

        cur.execute("""
            CREATE TABLE IF NOT EXISTS cambi_serie (
                id SERIAL PRIMARY KEY,
                forno VARCHAR(50),
                linea VARCHAR(50),
                data_cambio VARCHAR(50),
                nome_bottiglia VARCHAR(255),
                tempo_cambio VARCHAR(50),
                altezza_paratie VARCHAR(50),
                num_bottiglie_tempera INT DEFAULT 0,
                quantita_trattamento VARCHAR(50),
                creato_il TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS nastri (
                id SERIAL PRIMARY KEY,
                codice VARCHAR(255) UNIQUE,
                nome VARCHAR(255) NOT NULL,
                posizione VARCHAR(255),
                stato VARCHAR(50) DEFAULT 'In Uso',
                note TEXT,
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
    interventi_attesa_count = 0
    
    username = session.get('username')
    is_admin = session.get('is_admin')
    puo_assegnare = session.get('puo_assegnare_promemoria')
    
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        cur.execute("SELECT * FROM prodotti ORDER BY nome ASC;")
        tutti = cur.fetchall()
        
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
                           promemoria_urgenti=promemoria_urgenti,
                           interventi_aperti_count=interventi_aperti_count,
                           interventi_in_lavoro_count=interventi_in_lavoro_count,
                           interventi_attesa_count=interventi_attesa_count)

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

# --- MODULO NASTRI ---
@app.route("/nastri")
@app.route("/nastri.html")
def nastri():
    if not (session.get('is_admin') or session.get('puo_vedere_magazzino', 1)):
        flash("Accesso al modulo Nastri non autorizzato.", "error")
        return redirect(url_for('index'))
    lista_nastri = []
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT * FROM nastri ORDER BY nome ASC;")
        lista_nastri = cur.fetchall()
        cur.close()
        conn.close()
    except Exception as e:
        print(f"Errore caricamento nastri: {e}")
    return render_template("nastri.html", nastri=lista_nastri)

@app.route("/aggiungi_nastro", methods=["POST"])
def aggiungi_nastro():
    if not (session.get('is_admin') or session.get('puo_aggiungere_prodotti', 1)):
        flash("Permesso negato.", "error")
        return redirect(url_for("nastri"))
    codice = request.form.get("codice", "")
    nome = request.form.get("nome")
    posizione = request.form.get("posizione", "")
    stato = request.form.get("stato", "In Uso")
    note = request.form.get("note", "")
    if nome:
        try:
            conn = get_db_connection()
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO nastri (codice, nome, posizione, stato, note)
                VALUES (%s, %s, %s, %s, %s);
            """, (codice, nome, posizione, stato, note))
            conn.commit()
            cur.close()
            conn.close()
            registra_log(f"Aggiunto nastro: {nome}")
            flash("Nastro aggiunto con successo!", "success")
        except Exception as e:
            flash(f"Errore aggiunta nastro: {e}", "error")
    return redirect(url_for("nastri"))

@app.route("/elimina_nastro/<int:nastro_id>", methods=["POST"])
def elimina_nastro(nastro_id):
    if not (session.get('is_admin') or session.get('puo_eliminare', 0)):
        flash("Permesso negato per eliminare i nastri.", "error")
        return redirect(url_for("nastri"))
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("DELETE FROM nastri WHERE id = %s;", (nastro_id,))
        conn.commit()
        cur.close()
        conn.close()
        registra_log(f"Eliminato nastro ID {nastro_id}")
        flash("Nastro eliminato con successo.", "success")
    except Exception as e:
        flash(f"Errore eliminazione nastro: {e}", "error")
    return redirect(url_for("nastri"))

# --- PANNELLO PERMESSI ADMIN & LOGS ---
@app.route("/admin_utenti")
@app.route("/admin_utenti.html")
def admin_utenti():
    if not session.get('is_admin'):
        flash("Accesso riservato all'Amministratore.", "error")
        return redirect(url_for('index'))
    utenti = []
    logs = []
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT * FROM utenti ORDER BY username ASC;")
        utenti = cur.fetchall()
        
        cur.execute("DELETE FROM log_attivita WHERE data_ora < NOW() - INTERVAL '30 days';")
        conn.commit()
        cur.execute("SELECT * FROM log_attivita ORDER BY data_ora DESC LIMIT 100;")
        logs = cur.fetchall()
        
        cur.close()
        conn.close()
    except Exception as e:
        print(f"Errore admin: {e}")
    return render_template("admin_utenti.html", utenti=utenti, logs=logs)

@app.route("/log_attivita")
@app.route("/log_attivita.html")
def log_attivita():
    if not session.get('is_admin'):
        flash("Accesso riservato all'Amministratore.", "error")
        return redirect(url_for('index'))
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM log_attivita ORDER BY data_ora DESC LIMIT 100;")
    logs = cur.fetchall()
    cur.close()
    conn.close()
    return render_template("log_attivita.html", logs=logs)

@app.route("/toggle_permesso/<int:user_id>/<campo>", methods=["POST"])
def toggle_permesso(user_id, campo):
    if not session.get('is_admin'):
        return redirect(url_for('index'))
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        if campo.startswith("puo_"):
            cur.execute(f"UPDATE utenti SET {campo} = 1 - COALESCE({campo}, 0) WHERE id = %s;", (user_id,))
            conn.commit()
            registra_log(f"Modificato permesso {campo} per utente ID {user_id}")
        cur.close()
        conn.close()
    except Exception as e:
        flash(f"Errore aggiornamento permesso: {e}", "error")
    return redirect(url_for('admin_utenti'))

@app.route("/reset_password/<int:user_id>", methods=["POST"])
def reset_password(user_id):
    if not session.get('is_admin'):
        return redirect(url_for('index'))
    nuova_password = request.form.get("nuova_password")
    if nuova_password:
        try:
            conn = get_db_connection()
            cur = conn.cursor()
            hashed_pw = generate_password_hash(nuova_password)
            cur.execute("UPDATE utenti SET password = %s WHERE id = %s;", (hashed_pw, user_id))
            conn.commit()
            cur.close()
            conn.close()
            registra_log(f"Reset password per utente ID {user_id}")
            flash("Password aggiornata con successo!", "success")
        except Exception as e:
            flash(f"Errore reset password: {e}", "error")
    return redirect(url_for('admin_utenti'))

@app.route("/elimina_utente/<int:user_id>", methods=["POST"])
def elimina_utente(user_id):
    if not session.get('is_admin'):
        return redirect(url_for('index'))
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("DELETE FROM utenti WHERE id = %s AND username != 'admin';", (user_id,))
        conn.commit()
        cur.close()
        conn.close()
        registra_log(f"Eliminato utente ID {user_id}")
        flash("Utente eliminato con successo.", "success")
    except Exception as e:
        flash(f"Errore eliminazione utente: {e}", "error")
    return redirect(url_for('admin_utenti'))

# --- CAMBI SERIE ---
@app.route("/cambi_serie", methods=["GET", "POST"])
@app.route("/cambi_serie.html", methods=["GET", "POST"])
def cambi_serie():
    forno_filtro = request.args.get("forno", "Tutti")
    settimana_filtro = request.args.get("settimana", "")

    conn = get_db_connection()
    cur = conn.cursor()
    
    query = "SELECT * FROM cambi_serie WHERE 1=1"
    params = []

    if forno_filtro != "Tutti":
        query += " AND forno = %s"
        params.append(forno_filtro)
    
    if settimana_filtro:
        query += " AND TO_CHAR(data_cambio::DATE, 'IYYY-IW') = %s"
        params.append(settimana_filtro)

    query += " ORDER BY data_cambio DESC, id DESC;"
    cur.execute(query, tuple(params))
    record_serie = cur.fetchall()
    
    cur.close()
    conn.close()

    return render_template("cambi_serie.html", 
                           record_serie=record_serie, 
                           forno_filtro=forno_filtro, 
                           settimana_filtro=settimana_filtro)

@app.route("/aggiungi_cambio_serie", methods=["POST"])
def aggiungi_cambio_serie():
    forno = request.form.get("forno")
    linea = request.form.get("linea")
    data_cambio = request.form.get("data_cambio")
    nome_bottiglia = request.form.get("nome_bottiglia")
    tempo_cambio = request.form.get("tempo_cambio", "")
    altezza_paratie = request.form.get("altezza_paratie", "")
    num_bottiglie_tempera = int(request.form.get("num_bottiglie_tempera", 0) or 0)
    quantita_trattamento = request.form.get("quantita_trattamento", "")

    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO cambi_serie (forno, linea, data_cambio, nome_bottiglia, tempo_cambio, altezza_paratie, num_bottiglie_tempera, quantita_trattamento)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s);
        """, (forno, linea, data_cambio, nome_bottiglia, tempo_cambio, altezza_paratie, num_bottiglie_tempera, quantita_trattamento))
        
        conn.commit()
        cur.close()
        conn.close()
        
        registra_log(f"Registrato cambio serie per {forno} Linea {linea} - {nome_bottiglia}")
        flash("Cambio serie registrato con successo!", "success")
    except Exception as e:
        flash(f"Errore durante il salvataggio del cambio serie: {e}", "error")

    return redirect(url_for("cambi_serie"))

@app.route("/elimina_cambio_serie/<int:id_cambio>", methods=["POST"])
def elimina_cambio_serie(id_cambio):
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("DELETE FROM cambi_serie WHERE id = %s;", (id_cambio,))
        conn.commit()
        cur.close()
        conn.close()
        registra_log(f"Eliminato cambio serie ID {id_cambio}")
        flash("Cambio serie eliminato con successo.", "success")
    except Exception as e:
        flash(f"Errore durante l'eliminazione: {e}", "error")
    return redirect(url_for("cambi_serie"))

@app.route("/esporta_cambi_serie_csv", endpoint="esporta_cambi_serie_csv")
def esporta_cambi_serie_csv():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT data_cambio, forno, linea, nome_bottiglia, tempo_cambio, altezza_paratie, num_bottiglie_tempera, quantita_trattamento FROM cambi_serie ORDER BY data_cambio DESC;")
    righe = cur.fetchall()
    cur.close()
    conn.close()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['Data Cambio', 'Forno', 'Linea', 'Nome Bottiglia', 'Tempo Cambio', 'Altezza Paratie', 'N° Bottiglie Tempera', 'Quantità Trattamento'])
    for r in righe:
        writer.writerow([
            r.get('data_cambio', ''),
            r.get('forno', ''),
            r.get('linea', ''),
            r.get('nome_bottiglia', ''),
            r.get('tempo_cambio', ''),
            r.get('altezza_paratie', ''),
            r.get('num_bottiglie_tempera', 0),
            r.get('quantita_trattamento', '')
        ])
    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-disposition": "attachment; filename=Cambi_Serie_OMG.csv"}
    )

# --- MODULO: REPORT ORE & STATISTICHE MANUTENZIONI ---
@app.route("/report_ore")
@app.route("/report_ore.html")
def report_ore():
    if not (session.get('is_admin') or session.get('puo_vedere_report_ore', 1)):
        flash("Accesso al modulo Report Ore non autorizzato.", "error")
        return redirect(url_for('index'))

    filtro_tecnico = request.args.get("tecnico", "Tutti")
    data_inizio = request.args.get("data_inizio", "")
    data_fine = request.args.get("data_fine", "")
    periodo_predefinito = request.args.get("periodo", "mese")

    today = datetime.now().date()
    if periodo_predefinito == "oggi":
        data_inizio = today.strftime("%Y-%m-%d")
        data_fine = today.strftime("%Y-%m-%d")
    elif periodo_predefinito == "mese":
        data_inizio = today.replace(day=1).strftime("%Y-%m-%d")
        data_fine = today.strftime("%Y-%m-%d")
    elif periodo_predefinito == "anno":
        data_inizio = today.replace(month=1, day=1).strftime("%Y-%m-%d")
        data_fine = today.strftime("%Y-%m-%d")

    conn = get_db_connection()
    cur = conn.cursor()
    
    cur.execute("SELECT username FROM utenti ORDER BY username ASC;")
    utenti = cur.fetchall()

    query = """
        SELECT id, titolo, impianto_macchina, priorita, tipo_guasto, stato, assegnato_a, 
               creato_da, inizio_lavoro, fine_lavoro, COALESCE(tempo_lavorato_minuti, 0) as tempo_lavorato_minuti, creato_il 
        FROM richieste_manutenzione 
        WHERE 1=1
    """
    params = []

    if data_inizio:
        query += " AND DATE(COALESCE(fine_lavoro, creato_il)) >= %s"
        params.append(data_inizio)
    if data_fine:
        query += " AND DATE(COALESCE(fine_lavoro, creato_il)) <= %s"
        params.append(data_fine)

    query += " ORDER BY creato_il DESC;"
    cur.execute(query, tuple(params))
    interventi = cur.fetchall()

    ore_per_tecnico = {}
    ore_per_tipo = {}
    interventi_filtrati = []
    totale_minuti_generale = 0

    for u in utenti:
        ore_per_tecnico[u['username']] = 0

    for r in interventi:
        assegnati = [t.strip() for t in (r['assegnato_a'] or "").split(",") if t.strip()]
        
        if filtro_tecnico != "Tutti" and filtro_tecnico not in assegnati:
            continue

        interventi_filtrati.append(r)
        minuti = r['tempo_lavorato_minuti'] or 0
        totale_minuti_generale += minuti

        tipo = r['tipo_guasto'] or 'Meccanico'
        ore_per_tipo[tipo] = ore_per_tipo.get(tipo, 0) + (minuti / 60.0)

        if assegnati:
            quota_minuti = minuti
            for tec in assegnati:
                ore_per_tecnico[tec] = ore_per_tecnico.get(tec, 0) + (quota_minuti / 60.0)

    cur.close()
    conn.close()

    totale_ore_generale = round(totale_minuti_generale / 60.0, 1)

    chart_tecnici_labels = [k for k, v in ore_per_tecnico.items() if filtro_tecnico == "Tutti" or k == filtro_tecnico]
    chart_tecnici_values = [round(ore_per_tecnico[k], 1) for k in chart_tecnici_labels]

    chart_tipi_labels = list(ore_per_tipo.keys())
    chart_tipi_values = [round(v, 1) for v in ore_per_tipo.values()]

    return render_template("report_ore.html",
                           utenti=utenti,
                           interventi=interventi_filtrati,
                           filtro_tecnico=filtro_tecnico,
                           data_inizio=data_inizio,
                           data_fine=data_fine,
                           periodo_predefinito=periodo_predefinito,
                           totale_ore_generale=totale_ore_generale,
                           totale_interventi=len(interventi_filtrati),
                           chart_tecnici_labels=chart_tecnici_labels,
                           chart_tecnici_values=chart_tecnici_values,
                           chart_tipi_labels=chart_tipi_labels,
                           chart_tipi_values=chart_tipi_values)

# --- RICHIESTE INTERVENTO MANUTENZIONE OFFICINA ---
@app.route("/richieste_manutenzione", methods=["GET", "POST"])
@app.route("/richieste_manutenzione.html", methods=["GET", "POST"])
def richieste_manutenzione():
    if not (session.get('is_admin') or session.get('puo_vedere_manutenzione', 1)):
        flash("Accesso non autorizzato.", "error")
        return redirect(url_for('index'))

    username_corrente = session.get('username')
    is_admin = session.get('is_admin')
    puo_aprire = is_admin or session.get('puo_aprire_manutenzioni', 1)
    puo_assegnare = is_admin or session.get('puo_assegnare_manutenzioni', 1)
    puo_gestire = is_admin or session.get('puo_gestire_interventi', 1)
    puo_elimina_int = is_admin or session.get('puo_eliminare_interventi', 0)
    
    conn = get_db_connection()
    cur = conn.cursor()
    
    if request.method == "POST":
        if not puo_aprire:
            flash("Non hai i permessi per aprire nuove richieste di intervento.", "error")
            return redirect(url_for("richieste_manutenzione"))

        titolo = request.form.get("titolo")
        impianto_macchina = request.form.get("impianto_macchina", "")
        descrizione = request.form.get("descrizione", "")
        priorita = request.form.get("priorita", "Media")
        tipo_guasto = request.form.get("tipo_guasto", "Meccanico")
        
        tecnici_selezionati = []
        if puo_assegnare:
            tecnici_selezionati = request.form.getlist("assegnato_a[]")
            assegnato_a = ", ".join(tecnici_selezionati) if tecnici_selezionati else ""
        else:
            assegnato_a = username_corrente
            tecnici_selezionati = [username_corrente]
        
        allegato_nome = None
        allegato_dati = None
        file_allegato = request.files.get("allegato_foto")
        if file_allegato and file_allegato.filename:
            allegato_nome = file_allegato.filename
            allegato_dati = file_allegato.read()
        
        if titolo:
            cur.execute("""
                INSERT INTO richieste_manutenzione (titolo, impianto_macchina, descrizione, priorita, tipo_guasto, assegnato_a, creato_da, stato, allegato_nome, allegato_dati)
                VALUES (%s, %s, %s, %s, %s, %s, %s, 'Aperta', %s, %s);
            """, (titolo, impianto_macchina, descrizione, priorita, tipo_guasto, assegnato_a, username_corrente, allegato_nome, allegato_dati))
            conn.commit()
            
            for tec in tecnici_selezionati:
                tec_clean = tec.strip()
                if tec_clean:
                    crea_notifica(
                        destinatario=tec_clean,
                        titolo="🛠️ Nuova Manutenzione Assegnata",
                        messaggio=f"Ti è stato assegnato un intervento su {impianto_macchina}: {titolo}",
                        link="/richieste_manutenzione"
                    )

            registra_log(f"Creata richiesta intervento: {titolo} su {impianto_macchina}")
            flash("Richiesta di intervento creata e notifiche inviate!", "success")
        return redirect(url_for("richieste_manutenzione"))

    cur.execute("SELECT username FROM utenti ORDER BY username ASC;")
    lista_utenti = cur.fetchall()

    cur.execute("SELECT qr_code, nome, quantita FROM prodotti ORDER BY nome ASC;")
    lista_prodotti = cur.fetchall()

    cur.execute("""
        SELECT id, titolo, impianto_macchina, descrizione, priorita, stato, tipo_guasto, 
               assegnato_a, creato_da, inizio_lavoro, fine_lavoro, 
               COALESCE(tempo_lavorato_minuti, 0) AS tempo_lavorato_minuti, 
               note_lavoro, allegato_nome, creato_il 
        FROM richieste_manutenzione 
        ORDER BY CASE WHEN stato = 'Completata' THEN 2 ELSE 1 END, creato_il DESC;
    """)
    richieste = cur.fetchall()

    ricambi_per_intervento = {}
    for r in richieste:
        cur.execute("SELECT qr_code, nome_ricambio, quantita FROM intervento_ricambi WHERE intervento_id = %s;", (r['id'],))
        ricambi_per_intervento[r['id']] = cur.fetchall()

    cur.close()
    conn.close()
    
    return render_template("richieste_manutenzione.html", 
                           richieste=richieste, 
                           lista_utenti=lista_utenti, 
                           lista_prodotti=lista_prodotti,
                           ricambi_per_intervento=ricambi_per_intervento,
                           puo_aprire=puo_aprire,
                           puo_assegnare=puo_assegnare,
                           puo_gestire=puo_gestire,
                           puo_elimina_int=puo_elimina_int)

@app.route("/cambia_stato_intervento/<int:intervento_id>", methods=["POST"])
def cambia_stato_intervento(intervento_id):
    username_corrente = session.get('username')
    nuovo_stato = request.form.get("stato")
    note_lavoro = request.form.get("note_lavoro", "")
    
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM richieste_manutenzione WHERE id = %s;", (intervento_id,))
    req = cur.fetchone()
    
    if req:
        now = datetime.now()
        
        if nuovo_stato == 'In Lavoro':
            inizio_precedente = req.get('inizio_lavoro')
            if not inizio_precedente:
                cur.execute("""
                    UPDATE richieste_manutenzione 
                    SET stato = %s, 
                        assegnato_a = COALESCE(NULLIF(assegnato_a, ''), %s),
                        inizio_lavoro = %s
                    WHERE id = %s;
                """, (nuovo_stato, username_corrente, now, intervento_id))
            else:
                cur.execute("UPDATE richieste_manutenzione SET stato = %s WHERE id = %s;", (nuovo_stato, intervento_id))
            flash("Intervento avviato / ripreso!", "success")
            
        elif nuovo_stato == 'In Pausa':
            inizio = req.get('inizio_lavoro')
            minuti_aggiunti = 0
            if inizio and req.get('stato') == 'In Lavoro':
                minuti_aggiunti = int((now - inizio).total_seconds() / 60)
            
            cur.execute("""
                UPDATE richieste_manutenzione 
                SET stato = %s, 
                    tempo_lavorato_minuti = COALESCE(tempo_lavorato_minuti, 0) + %s,
                    inizio_lavoro = NULL
                WHERE id = %s;
            """, (nuovo_stato, minuti_aggiunti, intervento_id))
            flash("Intervento messo in pausa.", "warning")
            
        elif nuovo_stato == 'Attesa Ricambio':
            cur.execute("""
                UPDATE richieste_manutenzione 
                SET stato = %s, note_lavoro = COALESCE(NULLIF(%s, ''), note_lavoro) 
                WHERE id = %s;
            """, (nuovo_stato, note_lavoro, intervento_id))
            flash("Intervento messo in attesa ricambio.", "warning")
            
        elif nuovo_stato == 'Completata':
            inizio = req.get('inizio_lavoro')
            minuti_aggiunti = 0
            if inizio and req.get('stato') == 'In Lavoro':
                minuti_aggiunti = int((now - inizio).total_seconds() / 60)
            
            tempo_totale = req.get('tempo_lavorato_minuti', 0) + minuti_aggiunti

            ricambi_qr_list = request.form.getlist("ricambio_qr[]")
            ricambi_qta_list = request.form.getlist("ricambio_qta[]")
            
            for qr, qta_str in zip(ricambi_qr_list, ricambi_qta_list):
                if qr and qta_str and int(qta_str) > 0:
                    qta = int(qta_str)
                    cur.execute("SELECT * FROM prodotti WHERE qr_code = %s;", (qr,))
                    prod = cur.fetchone()
                    if prod:
                        cur.execute("UPDATE prodotti SET quantita = GREATEST(0, quantita - %s) WHERE qr_code = %s;", (qta, qr))
                        cur.execute("""
                            INSERT INTO intervento_ricambi (intervento_id, qr_code, nome_ricambio, quantita)
                            VALUES (%s, %s, %s, %s);
                        """, (intervento_id, qr, prod['nome'], qta))
                        registra_log(f"Utilizzato ricambio su intervento #{intervento_id}: {prod['nome']} (-{qta} pz)")

            cur.execute("""
                UPDATE richieste_manutenzione 
                SET stato = %s, 
                    fine_lavoro = %s, 
                    tempo_lavorato_minuti = %s,
                    note_lavoro = COALESCE(NULLIF(%s, ''), note_lavoro) 
                WHERE id = %s;
            """, (nuovo_stato, now, tempo_totale, note_lavoro, intervento_id))
            
            creato_da = req.get('creato_da')
            if creato_da and creato_da != username_corrente:
                crea_notifica(
                    destinatario=creato_da,
                    titolo="✅ Intervento Completato",
                    messaggio=f"L'intervento su {req.get('impianto_macchina')} è stato completato da {username_corrente}.",
                    link="/richieste_manutenzione"
                )
                
            flash("Intervento completato e chiuso con successo!", "success")
            
        elif nuovo_stato == 'Riassegna':
            if session.get('is_admin') or session.get('puo_assegnare_manutenzioni', 1):
                tecnici_nuovi = request.form.getlist("nuovi_assegnatari[]")
                nuova_lista = ", ".join(tecnici_nuovi) if tecnici_nuovi else ""
                cur.execute("UPDATE richieste_manutenzione SET assegnato_a = %s WHERE id = %s;", (nuova_lista, intervento_id))
                
                for tec in tecnici_nuovi:
                    tec_clean = tec.strip()
                    if tec_clean:
                        crea_notifica(
                            destinatario=tec_clean,
                            titolo="🔄 Intervento Riassegnato",
                            messaggio=f"Ti è stato riassegnato l'intervento su {req.get('impianto_macchina')}.",
                            link="/richieste_manutenzione"
                        )
                flash("Squadra / Tecnici aggiornati per l'intervento.", "success")

        conn.commit()
        registra_log(f"Aggiornato intervento ID {intervento_id} (Stato: {nuovo_stato})")
        
    cur.close()
    conn.close()
    return redirect(url_for("richieste_manutenzione"))

@app.route("/scarica_allegato_intervento/<int:intervento_id>")
def scarica_allegato_intervento(intervento_id):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT allegato_nome, allegato_dati FROM richieste_manutenzione WHERE id = %s;", (intervento_id,))
    res = cur.fetchone()
    cur.close()
    conn.close()
    if res and res['allegato_dati']:
        return send_file(
            io.BytesIO(res['allegato_dati']),
            download_name=res['allegato_nome'] or f"intervento_{intervento_id}.jpg",
            as_attachment=True
        )
    flash("Nessun allegato trovato.", "error")
    return redirect(url_for("richieste_manutenzione"))

@app.route("/stampa_intervento/<int:intervento_id>")
@app.route("/stampa_intervento.html/<int:intervento_id>")
def stampa_intervento(intervento_id):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT id, titolo, impianto_macchina, descrizione, priorita, stato, tipo_guasto, assegnato_a, creato_da, inizio_lavoro, fine_lavoro, tempo_lavorato_minuti, note_lavoro, creato_il FROM richieste_manutenzione WHERE id = %s;", (intervento_id,))
    intervento = cur.fetchone()
    cur.execute("SELECT * FROM intervento_ricambi WHERE intervento_id = %s;", (intervento_id,))
    ricambi = cur.fetchall()
    cur.close()
    conn.close()
    if not intervento:
        flash("Intervento non trovato.", "error")
        return redirect(url_for("richieste_manutenzione"))
    return render_template("stampa_intervento.html", r=intervento, ricambi=ricambi, intervento=intervento)

@app.route("/elimina_intervento/<int:intervento_id>", methods=["POST"])
def elimina_intervento(intervento_id):
    if not (session.get('is_admin') or session.get('puo_eliminare_interventi')):
        flash("Permesso negato per eliminare gli interventi.", "error")
        return redirect(url_for("richieste_manutenzione"))
        
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM richieste_manutenzione WHERE id = %s;", (intervento_id,))
    conn.commit()
    cur.close()
    conn.close()
    registra_log(f"Eliminato intervento ID {intervento_id}")
    flash("Intervento eliminato.", "success")
    return redirect(url_for("richieste_manutenzione"))

# --- GESTIONE PROMEMORIA ---
@app.route("/promemoria", methods=["GET", "POST"])
@app.route("/promemoria.html", methods=["GET", "POST"])
def promemoria():
    if not (session.get('is_admin') or session.get('puo_vedere_promemoria', 1)):
        flash("Accesso non autorizzato.", "error")
        return redirect(url_for('index'))

    username_corrente = session.get('username')
    is_admin = session.get('is_admin')
    puo_assegnare = session.get('puo_assegnare_promemoria')

    conn = get_db_connection()
    cur = conn.cursor()
    
    if request.method == "POST":
        titolo = request.form.get("titolo")
        descrizione = request.form.get("descrizione", "")
        data_scadenza = request.form.get("data_scadenza", "")
        priorita = request.form.get("priorita", "Media")
        ricorrenza = request.form.get("ricorrenza", "Nessuna")
        
        if is_admin or puo_assegnare:
            assegnato_a = request.form.get("assegnato_a")
            if not assegnato_a:
                assegnato_a = username_corrente
        else:
            assegnato_a = username_corrente
        
        if titolo:
            cur.execute("""
                INSERT INTO promemoria (titolo, descrizione, data_scadenza, priorita, ricorrenza, assegnato_a)
                VALUES (%s, %s, %s, %s, %s, %s);
            """, (titolo, descrizione, data_scadenza, priorita, ricorrenza, assegnato_a))
            conn.commit()
            
            if assegnato_a and assegnato_a != username_corrente:
                crea_notifica(
                    destinatario=assegnato_a,
                    titolo="📌 Nuovo Promemoria Assegnato",
                    messaggio=f"Ti è stato assegnato un promemoria: {titolo}",
                    link="/promemoria"
                )
                
            registra_log(f"Creato promemoria: {titolo} per utente {assegnato_a}")
            flash("Promemoria aggiunto con successo!", "success")
        return redirect(url_for("promemoria"))
        
    lista_utenti = []
    if is_admin or puo_assegnare:
        cur.execute("SELECT username FROM utenti ORDER BY username ASC;")
        lista_utenti = cur.fetchall()
        cur.execute("SELECT * FROM promemoria ORDER BY completato ASC, data_scadenza ASC;")
    else:
        cur.execute("""
            SELECT * FROM promemoria 
            WHERE assegnato_a = %s OR assegnato_a IS NULL OR assegnato_a = '' 
            ORDER BY completato ASC, data_scadenza ASC;
        """, (username_corrente,))

    lista_promemoria = cur.fetchall()
    cur.close()
    conn.close()
    
    return render_template("promemoria.html", 
                           promemoria=lista_promemoria, 
                           lista_utenti=lista_utenti, 
                           puo_assegnare=(is_admin or puo_assegnare))

@app.route("/completa_promemoria/<int:promemoria_id>", methods=["POST"])
def completa_promemoria(promemoria_id):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM promemoria WHERE id = %s;", (promemoria_id,))
    p = cur.fetchone()
    
    if p:
        ricorrenza = p.get('ricorrenza', 'Nessuna')
        data_attuale_str = p.get('data_scadenza')
        
        if ricorrenza and ricorrenza != 'Nessuna' and data_attuale_str:
            try:
                dt_scadenza = datetime.strptime(data_attuale_str, '%Y-%m-%d')
                
                if ricorrenza == 'Giorno':
                    nuova_dt = dt_scadenza + timedelta(days=1)
                elif ricorrenza == 'Settimana':
                    nuova_dt = dt_scadenza + timedelta(weeks=1)
                elif ricorrenza == 'Mese':
                    anno = dt_scadenza.year + (dt_scadenza.month // 12)
                    mese = (dt_scadenza.month % 12) + 1
                    giorno = min(dt_scadenza.day, 28)
                    nuova_dt = dt_scadenza.replace(year=anno, month=mese, day=giorno)
                elif ricorrenza == 'Anno':
                    nuova_dt = dt_scadenza.replace(year=dt_scadenza.year + 1)
                else:
                    nuova_dt = dt_scadenza
                
                nuova_data_str = nuova_dt.strftime('%Y-%m-%d')
                
                cur.execute("""
                    UPDATE promemoria 
                    SET data_scadenza = %s, completato = FALSE 
                    WHERE id = %s;
                """, (nuova_data_str, promemoria_id))
                
                registra_log(f"Avanzata scadenza promemoria '{p['titolo']}' al {nuova_data_str} ({ricorrenza})")
                flash(f"Promemoria completato! Prossima scadenza impostata al {nuova_data_str}.", "success")
                
            except Exception as e:
                cur.execute("UPDATE promemoria SET completato = NOT completato WHERE id = %s;", (promemoria_id,))
        else:
            cur.execute("UPDATE promemoria SET completato = NOT completato WHERE id = %s;", (promemoria_id,))
            
        conn.commit()
    
    cur.close()
    conn.close()
    return redirect(url_for("promemoria"))

@app.route("/elimina_promemoria/<int:promemoria_id>", methods=["POST"])
def elimina_promemoria(promemoria_id):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM promemoria WHERE id = %s;", (promemoria_id,))
    conn.commit()
    cur.close()
    conn.close()
    registra_log(f"Eliminato promemoria ID {promemoria_id}")
    flash("Promemoria eliminato.", "success")
    return redirect(url_for("promemoria"))

# --- GESTIONE FORNITORI E CONTATTI ---
@app.route("/fornitori", methods=["GET", "POST"])
@app.route("/fornitori.html", methods=["GET", "POST"])
def fornitori():
    if not (session.get('is_admin') or session.get('puo_gestire_fornitori', 1)):
        flash("Accesso non autorizzato.", "error")
        return redirect(url_for('index'))

    conn = get_db_connection()
    cur = conn.cursor()
    if request.method == "POST":
        nome_azienda = request.form.get("nome_azienda")
        settore_note = request.form.get("settore_note", "")
        indirizzo = request.form.get("indirizzo", "")
        p_iva = request.form.get("p_iva", "")
        telefono = request.form.get("telefono", "")
        email = request.form.get("email", "")
        if nome_azienda:
            cur.execute("""
                INSERT INTO fornitori (nome_azienda, settore_note, indirizzo, p_iva, telefono, email) 
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (nome_azienda) DO UPDATE SET
                    settore_note = EXCLUDED.settore_note,
                    indirizzo = EXCLUDED.indirizzo,
                    p_iva = EXCLUDED.p_iva,
                    telefono = EXCLUDED.telefono,
                    email = EXCLUDED.email;
            """, (nome_azienda, settore_note, indirizzo, p_iva, telefono, email))
            conn.commit()
            registra_log(f"Aggiunto/Aggiornato fornitore: {nome_azienda}")
            flash("Fornitore salvato con successo!", "success")
        return redirect(url_for("fornitori"))
    cur.execute("SELECT * FROM fornitori ORDER BY nome_azienda ASC;")
    lista_fornitori = cur.fetchall()
    cur.close()
    conn.close()
    return render_template("fornitori.html", fornitori=lista_fornitori)

@app.route("/modifica_fornitore/<int:fornitore_id>", methods=["POST"])
def modifica_fornitore(fornitore_id):
    if not (session.get('is_admin') or session.get('puo_gestire_fornitori', 1)):
        flash("Permesso negato.", "error")
        return redirect(url_for("fornitori"))

    nome_azienda = request.form.get("nome_azienda")
    settore_note = request.form.get("settore_note", "")
    indirizzo = request.form.get("indirizzo", "")
    p_iva = request.form.get("p_iva", "")
    telefono = request.form.get("telefono", "")
    email = request.form.get("email", "")
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("""
            UPDATE fornitori 
            SET nome_azienda = %s, settore_note = %s, indirizzo = %s, p_iva = %s, telefono = %s, email = %s
            WHERE id = %s;
        """, (nome_azienda, settore_note, indirizzo, p_iva, telefono, email, fornitore_id))
        conn.commit()
        cur.close()
        conn.close()
        registra_log(f"Modificato fornitore: {nome_azienda}")
        flash("Fornitore aggiornato con successo!", "success")
    except Exception as e:
        flash(f"Errore modifica fornitore: {e}", "error")
    return redirect(url_for("fornitori"))

@app.route("/fornitore/<int:fornitore_id>", methods=["GET", "POST"])
@app.route("/dettaglio_fornitore.html/<int:fornitore_id>", methods=["GET", "POST"])
def dettaglio_fornitore(fornitore_id):
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        if request.method == "POST":
            nome_tecnico = request.form.get("nome")
            telefono_tecnico = request.form.get("telefono")
            mansione = request.form.get("mansione", "")
            email_tecnico = request.form.get("email", "")
            if nome_tecnico and telefono_tecnico:
                cur.execute("""
                    INSERT INTO contatti_tecnici (fornitore_id, nome, telefono, mansione, email) 
                    VALUES (%s, %s, %s, %s, %s);
                """, (fornitore_id, nome_tecnico, telefono_tecnico, mansione, email_tecnico))
                conn.commit()
                registra_log(f"Aggiunto contatto tecnico {nome_tecnico} per fornitore ID {fornitore_id}")
                flash("Contatto tecnico aggiunto con successo!", "success")
            cur.close()
            conn.close()
            return redirect(url_for("dettaglio_fornitore", fornitore_id=fornitore_id))

        cur.execute("SELECT * FROM fornitori WHERE id = %s;", (fornitore_id,))
        fornitore = cur.fetchone()
        if not fornitore:
            flash("Fornitore non trovato.", "error")
            cur.close()
            conn.close()
            return redirect(url_for("fornitori"))

        cur.execute("SELECT * FROM contatti_tecnici WHERE fornitore_id = %s ORDER BY nome ASC;", (fornitore_id,))
        contatti = cur.fetchall()
        cur.close()
        conn.close()
        return render_template("dettaglio_fornitore.html", fornitore=fornitore, contatti=contatti)
    except Exception as e:
        flash(f"Errore caricamento dettaglio: {e}", "error")
        return redirect(url_for("fornitori"))

@app.route("/modifica_contatto_tecnico/<int:contatto_id>/<int:fornitore_id>", methods=["POST"])
def modifica_contatto_tecnico(contatto_id, fornitore_id):
    nome = request.form.get("nome")
    telefono = request.form.get("telefono")
    mansione = request.form.get("mansione", "")
    email = request.form.get("email", "")
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("""
            UPDATE contatti_tecnici 
            SET nome = %s, telefono = %s, mansione = %s, email = %s
            WHERE id = %s;
        """, (nome, telefono, mansione, email, contatto_id))
        conn.commit()
        cur.close()
        conn.close()
        registra_log(f"Modificato contatto tecnico ID {contatto_id}")
        flash("Contatto tecnico aggiornato con successo!", "success")
    except Exception as e:
        flash(f"Errore modifica contatto: {e}", "error")
    return redirect(url_for("dettaglio_fornitore", fornitore_id=fornitore_id))

@app.route("/elimina_contatto_tecnico/<int:contatto_id>/<int:fornitore_id>", methods=["POST"])
def elimina_contatto_tecnico(contatto_id, fornitore_id):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM contatti_tecnici WHERE id = %s;", (contatto_id,))
    conn.commit()
    cur.close()
    conn.close()
    registra_log(f"Eliminato contatto tecnico ID {contatto_id}")
    flash("Contatto tecnico eliminato.", "success")
    return redirect(url_for("dettaglio_fornitore", fornitore_id=fornitore_id))

@app.route("/elimina_fornitore/<int:fornitore_id>", methods=["POST"])
def elimina_fornitore(fornitore_id):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM fornitori WHERE id = %s;", (fornitore_id,))
    conn.commit()
    cur.close()
    conn.close()
    registra_log(f"Eliminato fornitore ID {fornitore_id}")
    flash("Fornitore eliminato con successo.", "success")
    return redirect(url_for("fornitori"))

@app.route("/importa_intelligente", methods=["GET", "POST"])
def importa_intelligente():
    if request.method == "GET":
        return redirect(url_for("fornitori"))
        
    if not (session.get('is_admin') or session.get('puo_importare_fornitori', 1)):
        flash("Permesso negato per l'importazione.", "error")
        return redirect(url_for("fornitori"))

    file_caricato = request.files.get("file_caricato")
    if not file_caricato or file_caricato.filename == '':
        flash("Nessun file selezionato.", "error")
        return redirect(url_for("fornitori"))
    filename = file_caricato.filename.lower()
    try:
        if filename.endswith(('.xlsx', '.xls')):
            df = pd.read_excel(file_caricato)
        elif filename.endswith(('.csv', '.txt')):
            try:
                stream = io.TextIOWrapper(file_caricato.stream, encoding="utf-8-sig")
                df = pd.read_csv(stream)
            except UnicodeDecodeError:
                file_caricato.stream.seek(0)
                stream = io.TextIOWrapper(file_caricato.stream, encoding="latin-1")
                df = pd.read_csv(stream)
        else:
            flash("Formato file non supportato.", "error")
            return redirect(url_for("fornitori"))
        
        conn = get_db_connection()
        cur = conn.cursor()
        count_fornitori = 0
        count_tecnici = 0
        current_fornitore_id = None
        
        for _, row in df.iterrows():
            valori = [str(val).strip() for val in row.values if pd.notna(val) and str(val).strip() != 'nan']
            if not valori:
                continue
            col1_raw = valori[0] if len(valori) > 0 else ''
            has_double_space = bool(re.search(r'\s{2,}', col1_raw))
            words = col1_raw.split()
            first_word = words[0] if words else ''
            
            is_company = False
            if has_double_space:
                is_company = True
            elif first_word.isupper() and len(first_word) > 1 and not any(c.islower() for c in first_word):
                is_company = True
            elif current_fornitore_id is None:
                is_company = True

            if is_company:
                if has_double_space:
                    parts = re.split(r'\s{2,}', col1_raw, maxsplit=1)
                    nome_azienda = parts[0].strip()
                    settore = parts[1].strip() if len(parts) > 1 else (valori[1] if len(valori) > 1 else '')
                else:
                    nome_azienda = col1_raw
                    settore = valori[1] if len(valori) > 1 else ''
                indirizzo = valori[2] if len(valori) > 2 else ''
                telefono = next((v for v in valori if re.search(r'\d{3}', v) and not '@' in v), '')
                email = next((v for v in valori if '@' in v), '')
                
                cur.execute("SELECT id FROM fornitori WHERE LOWER(nome_azienda) = LOWER(%s);", (nome_azienda,))
                f_res = cur.fetchone()
                if f_res:
                    current_fornitore_id = f_res['id']
                    cur.execute("""
                        UPDATE fornitori 
                        SET settore_note = COALESCE(NULLIF(%s, ''), settore_note),
                            indirizzo = COALESCE(NULLIF(%s, ''), indirizzo),
                            telefono = COALESCE(NULLIF(%s, ''), telefono),
                            email = COALESCE(NULLIF(%s, ''), email)
                        WHERE id = %s;
                    """, (settore, indirizzo, telefono, email, current_fornitore_id))
                else:
                    cur.execute("""
                        INSERT INTO fornitori (nome_azienda, settore_note, indirizzo, telefono, email)
                        VALUES (%s, %s, %s, %s, %s)
                        RETURNING id;
                    """, (nome_azienda, settore, indirizzo, telefono, email))
                    res = cur.fetchone()
                    current_fornitore_id = res['id'] if res else None
                    count_fornitori += 1
            else:
                if current_fornitore_id:
                    nome_tecnico = col1_raw
                    telefono = next((v for v in valori if re.search(r'\d{3}', v) and not '@' in v), '')
                    email = next((v for v in valori if '@' in v), '')
                    mansione = valori[1] if len(valori) > 1 and valori[1] != telefono and valori[1] != email else ''
                    
                    cur.execute("""
                        SELECT id FROM contatti_tecnici 
                        WHERE fornitore_id = %s AND LOWER(nome) = LOWER(%s);
                    """, (current_fornitore_id, nome_tecnico))
                    if not cur.fetchone():
                        cur.execute("""
                            INSERT INTO contatti_tecnici (fornitore_id, nome, telefono, mansione, email)
                            VALUES (%s, %s, %s, %s, %s);
                        """, (current_fornitore_id, nome_tecnico, telefono, mansione, email))
                        count_tecnici += 1
        conn.commit()
        cur.close()
        conn.close()
        registra_log(f"Importazione intelligente: {count_fornitori} fornitori e {count_tecnici} tecnici.")
        flash(f"Analisi completata! Importati {count_fornitori} fornitori e {count_tecnici} contatti tecnici.", "success")
    except Exception as e:
        flash(f"Errore importazione: {e}", "error")
    return redirect(url_for("fornitori"))

@app.route("/esporta_fornitori_intelligente", endpoint="esporta_fornitori_intelligente")
@app.route("/esporta_fornitori_csv", endpoint="esporta_fornitori_csv")
def esporta_fornitori_csv():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT nome_azienda, settore_note, indirizzo, p_iva, telefono, email FROM fornitori ORDER BY nome_azienda ASC;")
    fornitori_list = cur.fetchall()
    cur.close()
    conn.close()
    
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['Nome Azienda', 'Settore / Note', 'Indirizzo', 'P.IVA', 'Telefono', 'Email'])
    for f in fornitori_list:
        writer.writerow([
            f.get('nome_azienda', ''),
            f.get('settore_note', ''),
            f.get('indirizzo', ''),
            f.get('p_iva', ''),
            f.get('telefono', ''),
            f.get('email', '')
        ])
    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-disposition": "attachment; filename=Fornitori_Gestionale_OMG.csv"}
    )

# --- GESTIONE DOCUMENTI ---
@app.route("/documenti", defaults={"cartella_id": None}, methods=["GET", "POST"])
@app.route("/documenti/<int:cartella_id>", methods=["GET", "POST"])
@app.route("/documenti.html", defaults={"cartella_id": None}, methods=["GET", "POST"])
def documenti(cartella_id):
    if not (session.get('is_admin') or session.get('puo_gestire_documenti', 1)):
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
                registra_log(f"Creata cartella documenti: {nome_cartella}")
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
                registra_log(f"Caricato file: {nome_file}")
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
                           percorso_breadcrumb=percorso_breadcrumb,
                           puo_elimina_doc=(session.get('is_admin') or session.get('puo_eliminare_documenti', 0)))

@app.route("/scarica_file/<int:file_id>")
def scarica_file(file_id):
    if not (session.get('is_admin') or session.get('puo_gestire_documenti', 1)):
        flash("Accesso negato.", "error")
        return redirect(url_for('index'))

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT nome_file, tipo_file, dati_file FROM documenti WHERE id = %s;", (file_id,))
    file_data = cur.fetchone()
    cur.close()
    conn.close()

    if file_data:
        registra_log(f"Scaricato file: {file_data['nome_file']}")
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
    if not (session.get('is_admin') or session.get('puo_eliminare_documenti', 0)):
        flash("Permesso negato per eliminare cartelle.", "error")
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
    registra_log(f"Eliminata cartella documenti ID {cartella_id}")
    flash("Cartella eliminata con successo.", "success")
    
    if parent_id:
        return redirect(url_for("documenti", cartella_id=parent_id))
    return redirect(url_for("documenti"))

@app.route("/elimina_file/<int:file_id>", methods=["POST"])
def elimina_file(file_id):
    if not (session.get('is_admin') or session.get('puo_eliminare_documenti', 0)):
        flash("Permesso negato per eliminare i file.", "error")
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
    registra_log(f"Eliminato file ID {file_id}")
    flash("File eliminato con successo.", "success")
    
    if cartella_id:
        return redirect(url_for("documenti", cartella_id=cartella_id))
    return redirect(url_for("documenti"))

# --- ALTRE ROTTE GESTIONALE E ESPORTAZIONI CSV ---
@app.route("/esportazioni")
@app.route("/esportazioni.html")
def esportazioni():
    return render_template("esportazioni.html")

@app.route("/esporta_csv")
@app.route("/esportazione_csv")
def esporta_csv():
    return redirect(url_for("esporta_inventario"))

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
        writer.writerow([
            p.get('qr_code', ''), 
            p.get('nome', ''), 
            p.get('sap', ''), 
            p.get('quantita', 0), 
            p.get('posizione', ''), 
            p.get('peso', ''), 
            'Si' if p.get('magazzino_pesante') else 'No'
        ])
    
    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-disposition": "attachment; filename=Inventario_Gestionale_OMG.csv"}
    )

@app.route("/esporta_interventi")
def esporta_interventi():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT id, titolo, impianto_macchina, priorita, tipo_guasto, stato, assegnato_a, creato_da, inizio_lavoro, fine_lavoro, tempo_lavorato_minuti, note_lavoro, creato_il FROM richieste_manutenzione ORDER BY creato_il DESC;")
    richieste = cur.fetchall()
    cur.close()
    conn.close()
    
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['ID', 'Titolo', 'Macchina', 'Priorità', 'Tipo Guasto', 'Stato', 'Assegnato A', 'Creato Da', 'Inizio', 'Fine', 'Minuti Lavorati', 'Note', 'Data Creazione'])
    for r in richieste:
        writer.writerow([
            r.get('id', ''), 
            r.get('titolo', ''), 
            r.get('impianto_macchina', ''), 
            r.get('priorita', ''), 
            r.get('tipo_guasto', ''), 
            r.get('stato', ''), 
            r.get('assegnato_a', ''), 
            r.get('creato_da', ''), 
            r.get('inizio_lavoro', ''), 
            r.get('fine_lavoro', ''), 
            r.get('tempo_lavorato_minuti', 0), 
            r.get('note_lavoro', ''), 
            r.get('creato_il', '')
        ])
    
    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-disposition": "attachment; filename=Report_Interventi_Gestionale_OMG.csv"}
    )

@app.route("/upload", methods=["GET", "POST"])
@app.route("/upload.html", methods=["GET", "POST"])
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
                            DO UPDATE SET nome = EXCLUDED.nome, sap = EXCLUDED.sap, quantita = prodotti.quantita + EXCLUDED.quantita, posizione = EXCLUDED.posizione;
                        """, (qr_code, nome, sap, quantita, posizione))
                        count += 1
                conn.commit()
                cur.close()
                conn.close()
                flash(f"Importati/Aggiornati {count} articoli!", "success")
            except Exception as e:
                flash(f"Errore CSV: {e}", "error")
        return redirect(url_for("upload"))
    return render_template("upload.html")

@app.route("/stampa_tutti_qr")
@app.route("/stampa_tutti_qr.html")
def stampa_tutti_qr():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM prodotti ORDER BY nome ASC;")
    prodotti = cur.fetchall()
    cur.close()
    conn.close()
    return render_template("stampa_tutti_qr.html", prodotti=prodotti)

@app.route("/stampa_multipla_qr", endpoint="stampa_multipla_qr")
@app.route("/stampa_multipla_qr.html", endpoint="stampa_multipla_qr_html")
@app.route("/stampa_qr_multipli", endpoint="stampa_qr_multipli")
def stampa_multipla_qr():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM prodotti ORDER BY nome ASC;")
    prodotti = cur.fetchall()
    cur.close()
    conn.close()
    return render_template("stampa_multipla_qr.html", prodotti=prodotti)

@app.route("/stampa_singolo_qr/<qr_code>")
@app.route("/stampa_singolo_qr.html/<qr_code>")
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
@app.route("/magazzino_pesante.html")
def magazzino_pesante():
    if not (session.get('is_admin') or session.get('puo_vedere_pesante', 1)):
        flash("Accesso al Magazzino Pesante negato.", "error")
        return redirect(url_for('index'))
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
            if is_pesante:
                prodotti.append(p)
    except Exception:
        pass
    return render_template("magazzino_pesante.html", prodotti=prodotti)

@app.route("/esporta_pesante", endpoint="esporta_pesante")
def esporta_pesante():
    if not (session.get('is_admin') or session.get('puo_vedere_pesante', 1)):
        flash("Accesso negato.", "error")
        return redirect(url_for('index'))
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT qr_code, nome, sap, quantita, posizione, peso FROM prodotti WHERE magazzino_pesante IN (1, '1', true) ORDER BY nome ASC;")
        prodotti = cur.fetchall()
        cur.close()
        conn.close()
    except Exception:
        prodotti = []

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['QR Code', 'Nome Articolo', 'SAP', 'Quantita', 'Posizione', 'Peso'])
    for p in prodotti:
        writer.writerow([
            p.get('qr_code', ''), 
            p.get('nome', ''), 
            p.get('sap', ''), 
            p.get('quantita', 0), 
            p.get('posizione', ''), 
            p.get('peso', '')
        ])
    
    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-disposition": "attachment; filename=Magazzino_Pesante_OMG.csv"}
    )

@app.route("/manutenzioni")
@app.route("/manutenzioni.html")
def manutenzioni():
    if not (session.get('is_admin') or session.get('puo_vedere_manutenzioni_esterne', 1)):
        flash("Accesso negato.", "error")
        return redirect(url_for('index'))
    prodotti = []
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT * FROM prodotti ORDER BY nome ASC;")
        tutti = cur.fetchall()
        cur.close()
        conn.close()
        for p in tutti:
            if p.get('in_manutenzione') in [1, '1', True, 1.0]:
                prodotti.append(p)
    except Exception:
        pass
    return render_template("manutenzioni.html", prodotti=prodotti)

@app.route("/storico_manutenzioni")
@app.route("/storico_manutenzioni.html")
def storico_manutenzioni():
    if not (session.get('is_admin') or session.get('puo_vedere_storico_manutenzioni', 1)):
        flash("Accesso allo storico negato.", "error")
        return redirect(url_for('index'))
    storico = []
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT * FROM storico_manutenzioni ORDER BY registrato_il DESC;")
        storico = cur.fetchall()
        cur.close()
        conn.close()
    except Exception:
        pass
    return render_template("storico_manutenzioni.html", storico=storico)

@app.route("/esporta_storico_manutenzioni_csv", endpoint="esporta_storico_manutenzioni_csv")
def esporta_storico_manutenzioni_csv():
    if not (session.get('is_admin') or session.get('puo_vedere_storico_manutenzioni', 1)):
        flash("Accesso negato.", "error")
        return redirect(url_for('index'))
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT * FROM storico_manutenzioni ORDER BY registrato_il DESC;")
        storico = cur.fetchall()
        cur.close()
        conn.close()
    except Exception:
        storico = []

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['ID', 'Data Registrazione', 'Nome Prodotto', 'QR Code', 'SAP', 'Cliente', 'Quantita', 'Data Spedizione', 'Data Riconsegna', 'Vettore', 'Ordine Amministrativo', 'Note'])
    for s in storico:
        writer.writerow([
            s.get('id', ''),
            s.get('registrato_il', ''),
            s.get('nome_prodotto', ''),
            s.get('qr_code', ''),
            s.get('sap', ''),
            s.get('cliente', ''),
            s.get('quantita', 0),
            s.get('data_spedizione', ''),
            s.get('data_riconsegna', ''),
            s.get('vettore', ''),
            'Si' if s.get('ordine_amministrativo') else 'No',
            s.get('note', '')
        ])
    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-disposition": "attachment; filename=Storico_Manutenzioni_OMG.csv"}
    )

@app.route("/elimina_storico_manutenzione/<int:storico_id>", methods=["POST"])
def elimina_storico_manutenzione(storico_id):
    if not (session.get('is_admin') or session.get('puo_eliminare_storico', 0)):
        flash("Permesso negato.", "error")
        return redirect(url_for('storico_manutenzioni'))
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM storico_manutenzioni WHERE id = %s;", (storico_id,))
    conn.commit()
    cur.close()
    conn.close()
    registra_log(f"Eliminato record storico manutenzione ID {storico_id}")
    flash("Record eliminato dallo storico.", "success")
    return redirect(url_for('storico_manutenzioni'))

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

@app.route("/carico", methods=["GET", "POST"])
@app.route("/carico.html", methods=["GET", "POST"])
def carico():
    if not (session.get('is_admin') or session.get('puo_caricare_scaricare', 1)):
        flash("Permesso negato per il carico.", "error")
        return redirect(url_for('index'))

    if request.method == "POST":
        qr_code = request.form.get("qr_code")
        quantita = int(request.form.get("quantita", 1))
        if qr_code:
            conn = get_db_connection()
            cur = conn.cursor()
            cur.execute("UPDATE prodotti SET quantita = quantita + %s WHERE qr_code = %s;", (quantita, qr_code))
            conn.commit()
            cur.close()
            conn.close()
            registra_log(f"Carico di +{quantita} pz su QR: {qr_code}")
            flash(f"Carico di {quantita} pz effettuato con successo!", "success")
            return redirect(url_for("gestisci_prodotto", qr_code=qr_code))
    return render_template("carico.html")

@app.route("/scarico", methods=["GET", "POST"])
@app.route("/scarico.html", methods=["GET", "POST"])
def scarico():
    if not (session.get('is_admin') or session.get('puo_caricare_scaricare', 1)):
        flash("Permesso negato per lo scarico.", "error")
        return redirect(url_for('index'))

    if request.method == "POST":
        qr_code = request.form.get("qr_code")
        quantita_da_scaricare = int(request.form.get("quantita", 1))
        if qr_code:
            conn = get_db_connection()
            cur = conn.cursor()
            cur.execute("SELECT * FROM prodotti WHERE qr_code = %s;", (qr_code,))
            prodotto = cur.fetchone()
            if prodotto:
                qta_iniziale = prodotto['quantita']
                nuova_quantita = max(0, qta_iniziale - quantita_da_scaricare)
                cur.execute("UPDATE prodotti SET quantita = %s WHERE qr_code = %s;", (nuova_quantita, qr_code))
                conn.commit()
                registra_log(f"Scarico di -{quantita_da_scaricare} pz su QR: {qr_code}")
                flash(f"Scarico di {quantita_da_scaricare} pz effettuato con successo!", "success")
            cur.close()
            conn.close()
            return redirect(url_for("gestisci_prodotto", qr_code=qr_code))
    return render_template("scarico.html")

@app.route("/scanner_globale", methods=["GET", "POST"])
@app.route("/scanner_globale.html", methods=["GET", "POST"])
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
@app.route("/gestisci.html/<qr_code>")
def gestisci_prodotto(qr_code):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM prodotti WHERE qr_code = %s;", (qr_code,))
    prodotto = cur.fetchone()
    lista_fornitori = []
    try:
        cur.execute("SELECT * FROM fornitori ORDER BY nome_azienda ASC;")
        lista_fornitori = cur.fetchall()
    except Exception:
        pass
    cur.close()
    conn.close()
    if not prodotto:
        flash("Prodotto non trovato!", "error")
        return redirect(url_for("index"))
    return render_template("gestisci.html", prodotto=prodotto, fornitori=lista_fornitori)

@app.route("/aggiorna/<qr_code>", methods=["POST"])
@app.route("/aggiorna_prodotto/<qr_code>", methods=["POST"])
def aggiorna_prodotto(qr_code):
    if not (session.get('is_admin') or session.get('puo_modificare_prodotti', 1)):
        flash("Permesso negato per modificare gli articoli.", "error")
        return redirect(url_for("gestisci_prodotto", qr_code=qr_code))

    nome = request.form.get("nome")
    sap = request.form.get("sap", "")
    posizione = request.form.get("posizione", "")
    peso = request.form.get("peso", "")
    soglia_minima = int(request.form.get("soglia_minima", 3) or 3)
    flag_sezione = 1 if request.form.get("magazzino_pesante") else 0
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("""
            UPDATE prodotti 
            SET nome = %s, sap = %s, posizione = %s, peso = %s, magazzino_pesante = %s, soglia_minima = %s
            WHERE qr_code = %s;
        """, (nome, sap, posizione, peso, flag_sezione, soglia_minima, qr_code))
        conn.commit()
        cur.close()
        conn.close()
        registra_log(f"Aggiornato articolo: {nome} (QR: {qr_code})")
        flash("Articolo aggiornato con successo!", "success")
    except Exception as e:
        flash(f"Errore: {e}", "error")
    return redirect(url_for("gestisci_prodotto", qr_code=qr_code))

@app.route("/aggiungi", methods=["POST"])
@app.route("/aggiungi_prodotto", methods=["POST"])
def aggiungi_prodotto():
    if not (session.get('is_admin') or session.get('puo_aggiungere_prodotti', 1)):
        flash("Permesso negato per inserire nuovi prodotti.", "error")
        return redirect(url_for("index"))

    qr_code = request.form.get("qr_code", "").strip()
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
        
        if not qr_code:
            cur.execute("SELECT COUNT(*) + 1 as next_id FROM prodotti;")
            res_id = cur.fetchone()
            next_num = res_id['next_id'] if res_id else 1
            qr_code = f"OMG-{next_num:04d}"
            
            while True:
                cur.execute("SELECT id FROM prodotti WHERE qr_code = %s;", (qr_code,))
                if not cur.fetchone():
                    break
                next_num += 1
                qr_code = f"OMG-{next_num:04d}"

        cur.execute("""
            INSERT INTO prodotti (qr_code, nome, sap, peso, quantita, posizione, magazzino_pesante, soglia_minima)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (qr_code)
            DO UPDATE SET 
                quantita = prodotti.quantita + EXCLUDED.quantita,
                nome = EXCLUDED.nome,
                sap = EXCLUDED.sap,
                peso = EXCLUDED.peso,
                posizione = EXCLUDED.posizione,
                magazzino_pesante = EXCLUDED.magazzino_pesante,
                soglia_minima = EXCLUDED.soglia_minima;
        """, (qr_code, nome, sap, peso, quantita, posizione, flag_sezione, soglia_minima))
        conn.commit()
        cur.close()
        conn.close()
        registra_log(f"Aggiunto prodotto: {nome} (QR: {qr_code})")
        flash(f"Prodotto salvato con successo! (QR Code: {qr_code})", "success")
    except Exception as e:
        flash(f"Errore: {e}", "error")

    if flag_sezione == 1:
        return redirect(url_for("magazzino_pesante"))
    return redirect(url_for("index"))

@app.route("/manda_manutenzione/<qr_code>", methods=["POST"])
def manda_manutenzione(qr_code):
    cliente_manutenzione = request.form.get("cliente_manutenzione")
    quantita_manutenzione = int(request.form.get("quantita_manutenzione", 1))
    data_spedizione = request.form.get("data_spedizione", "").strip() or None
    data_riconsegna = request.form.get("data_riconsegna", "").strip() or None
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
        registra_log(f"Inviato in manutenzione: {qr_code}")
        flash("Articolo inviato in manutenzione e registrato nello storico!", "success")
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
        registra_log(f"Rientrato da manutenzione: {qr_code}")
        flash("Articolo rientrato in magazzino con successo!", "success")
    except Exception as e:
        flash(f"Errore: {e}", "error")
    return redirect(url_for("gestisci_prodotto", qr_code=qr_code))

@app.route("/elimina", methods=["POST"])
@app.route("/elimina_prodotto/<qr_code>", methods=["POST"])
def elimina_prodotto(qr_code=None):
    if not (session.get('is_admin') or session.get('puo_eliminare', 0)):
        flash("Permesso negato per eliminare prodotti.", "error")
        return redirect(url_for("index"))

    if not qr_code:
        qr_code = request.form.get("qr_code")

    if qr_code:
        try:
            conn = get_db_connection()
            cur = conn.cursor()
            cur.execute("DELETE FROM prodotti WHERE qr_code = %s;", (qr_code,))
            conn.commit()
            cur.close()
            conn.close()
            registra_log(f"Eliminato prodotto QR: {qr_code}")
            flash("Articolo eliminato dal magazzino con successo!", "success")
        except Exception as e:
            flash(f"Errore durante l'eliminazione: {e}", "error")
    return redirect(url_for("index"))

if __name__ == "__main__":
    app.run(debug=True)
