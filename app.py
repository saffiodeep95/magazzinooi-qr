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
                soglia_minima INT DEFAULT 3,
                matricola VARCHAR(255),
                stato_pezzo VARCHAR(255) DEFAULT 'Nuovo',
                volte_riparato INT DEFAULT 0
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
                note TEXT,
                esito VARCHAR(255)
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
        
        migrazioni = [
            ("prodotti", "matricola", "VARCHAR(255)"),
            ("prodotti", "stato_pezzo", "VARCHAR(255) DEFAULT 'Nuovo'"),
            ("prodotti", "volte_riparato", "INT DEFAULT 0"),
            ("storico_manutenzioni", "esito", "VARCHAR(255)")
        ]
        for tab, col, tipo in migrazioni:
            cur.execute(f"ALTER TABLE {tab} ADD COLUMN IF NOT EXISTS {col} {tipo};")

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

@app.route("/report_ore")
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
    cur.close()
    conn.close()

    ore_per_tecnico = {u['username']: 0 for u in utenti}
    ore_per_tipo = {}
    interventi_filtrati = []
    totale_minuti_generale = 0

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
            for tec in assegnati:
                if tec in ore_per_tecnico:
                    ore_per_tecnico[tec] += (minuti / 60.0)

    totale_ore_generale = round(totale_minuti_generale / 60.0, 1)
    chart_tecnici_labels = [k for k in ore_per_tecnico.keys() if filtro_tecnico == "Tutti" or k == filtro_tecnico]
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

@app.route("/richieste_manutenzione", methods=["GET", "POST"])
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
            flash("Non hai i permessi per aprire nuove richieste.", "error")
            return redirect(url_for("richieste_manutenzione"))

        titolo = request.form.get("titolo")
        impianto_macchina = request.form.get("impianto_macchina", "")
        descrizione = request.form.get("descrizione", "")
        priorita = request.form.get("priorita", "Media")
        tipo_guasto = request.form.get("tipo_guasto", "Meccanico")
        
        tecnici_selezionati = request.form.getlist("assegnato_a[]") if puo_assegnare else [username_corrente]
        assegnato_a = ", ".join(tecnici_selezionati) if tecnici_selezionati else ""
        
        file_allegato = request.files.get("allegato_foto")
        allegato_nome = file_allegato.filename if file_allegato and file_allegato.filename else None
        allegato_dati = file_allegato.read() if file_allegato and file_allegato.filename else None
        
        if titolo:
            cur.execute("""
                INSERT INTO richieste_manutenzione (titolo, impianto_macchina, descrizione, priorita, tipo_guasto, assegnato_a, creato_da, stato, allegato_nome, allegato_dati)
                VALUES (%s, %s, %s, %s, %s, %s, %s, 'Aperta', %s, %s);
            """, (titolo, impianto_macchina, descrizione, priorita, tipo_guasto, assegnato_a, username_corrente, allegato_nome, allegato_dati))
            conn.commit()
            
            for tec in tecnici_selezionati:
                if tec.strip():
                    crea_notifica(tec.strip(), "🛠️ Nuova Manutenzione", f"Intervento su {impianto_macchina}: {titolo}", "/richieste_manutenzione")

            registra_log(f"Creata richiesta intervento: {titolo}")
            flash("Richiesta creata con successo!", "success")
        return redirect(url_for("richieste_manutenzione"))

    cur.execute("SELECT username FROM utenti ORDER BY username ASC;")
    lista_utenti = cur.fetchall()
    cur.execute("SELECT qr_code, nome, quantita FROM prodotti ORDER BY nome ASC;")
    lista_prodotti = cur.fetchall()
    cur.execute("SELECT * FROM richieste_manutenzione ORDER BY CASE WHEN stato = 'Completata' THEN 2 ELSE 1 END, creato_il DESC;")
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
            if not req.get('inizio_lavoro'):
                cur.execute("UPDATE richieste_manutenzione SET stato = %s, assegnato_a = COALESCE(NULLIF(assegnato_a, ''), %s), inizio_lavoro = %s WHERE id = %s;", (nuovo_stato, username_corrente, now, intervento_id))
            else:
                cur.execute("UPDATE richieste_manutenzione SET stato = %s WHERE id = %s;", (nuovo_stato, intervento_id))
        elif nuovo_stato == 'In Pausa':
            minuti = int((now - req['inizio_lavoro']).total_seconds() / 60) if req.get('inizio_lavoro') and req.get('stato') == 'In Lavoro' else 0
            cur.execute("UPDATE richieste_manutenzione SET stato = %s, tempo_lavorato_minuti = COALESCE(tempo_lavorato_minuti, 0) + %s, inizio_lavoro = NULL WHERE id = %s;", (nuovo_stato, minuti, intervento_id))
        elif nuovo_stato == 'Completata':
            minuti = int((now - req['inizio_lavoro']).total_seconds() / 60) if req.get('inizio_lavoro') and req.get('stato') == 'In Lavoro' else 0
            tempo_totale = req.get('tempo_lavorato_minuti', 0) + minuti
            cur.execute("UPDATE richieste_manutenzione SET stato = %s, fine_lavoro = %s, tempo_lavorato_minuti = %s, note_lavoro = COALESCE(NULLIF(%s, ''), note_lavoro) WHERE id = %s;", (nuovo_stato, now, tempo_totale, note_lavoro, intervento_id))
        elif nuovo_stato == 'Attesa Ricambio':
            cur.execute("UPDATE richieste_manutenzione SET stato = %s WHERE id = %s;", (nuovo_stato, intervento_id))

        conn.commit()
    cur.close()
    conn.close()
    return redirect(url_for("richieste_manutenzione"))

@app.route("/elimina_intervento/<int:intervento_id>", methods=["POST"])
def elimina_intervento(intervento_id):
    if not (session.get('is_admin') or session.get('puo_eliminare_interventi', 0)):
        flash("Permesso negato per eliminare gli interventi.", "error")
        return redirect(url_for("richieste_manutenzione"))
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("DELETE FROM richieste_manutenzione WHERE id = %s;", (intervento_id,))
        conn.commit()
        cur.close()
        conn.close()
        flash("Intervento eliminato con successo.", "success")
    except Exception as e:
        flash(f"Errore durante l'eliminazione: {e}", "error")
    return redirect(url_for("richieste_manutenzione"))

@app.route("/aggiungi_ricambio_intervento/<int:intervento_id>", methods=["POST"])
def aggiungi_ricambio_intervento(intervento_id):
    qr_code = request.form.get("qr_code")
    quantita = int(request.form.get("quantita", 1))

    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT * FROM prodotti WHERE qr_code = %s;", (qr_code,))
        prod = cur.fetchone()

        if prod:
            if prod['quantita'] >= quantita:
                cur.execute("UPDATE prodotti SET quantita = quantita - %s WHERE qr_code = %s;", (quantita, qr_code))
                cur.execute("INSERT INTO intervento_ricambi (intervento_id, qr_code, nome_ricambio, quantita) VALUES (%s, %s, %s, %s);", (intervento_id, qr_code, prod['nome'], quantita))
                conn.commit()
                flash(f"Scaricati {quantita} pezzi di {prod['nome']} per l'intervento.", "success")
            else:
                flash(f"Quantità insufficiente in magazzino per {prod['nome']}!", "error")
        else:
            flash("Articolo non trovato!", "error")

        cur.close()
        conn.close()
    except Exception as e:
        flash(f"Errore scarico ricambio: {e}", "error")

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
def stampa_intervento(intervento_id):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM richieste_manutenzione WHERE id = %s;", (intervento_id,))
    intervento = cur.fetchone()
    cur.execute("SELECT * FROM intervento_ricambi WHERE intervento_id = %s;", (intervento_id,))
    ricambi = cur.fetchall()
    cur.close()
    conn.close()
    if not intervento:
        flash("Intervento non trovato.", "error")
        return redirect(url_for("richieste_manutenzione"))
    return render_template("stampa_intervento.html", r=intervento, ricambi=ricambi)

@app.route("/promemoria", methods=["GET", "POST"])
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
        assegnato_a = request.form.get("assegnato_a") if (is_admin or puo_assegnare) else username_corrente
        
        if titolo:
            cur.execute("INSERT INTO promemoria (titolo, descrizione, data_scadenza, priorita, ricorrenza, assegnato_a) VALUES (%s, %s, %s, %s, %s, %s);", (titolo, descrizione, data_scadenza, priorita, ricorrenza, assegnato_a))
            conn.commit()
            flash("Promemoria aggiunto!", "success")
        return redirect(url_for("promemoria"))

    cur.execute("SELECT username FROM utenti ORDER BY username ASC;")
    lista_utenti = cur.fetchall()
    cur.execute("SELECT * FROM promemoria ORDER BY completato ASC, data_scadenza ASC;")
    lista_promemoria = cur.fetchall()
    cur.close()
    conn.close()
    return render_template("promemoria.html", promemoria=lista_promemoria, lista_utenti=lista_utenti, puo_assegnare=(is_admin or puo_assegnare))

@app.route("/completa_promemoria/<int:promemoria_id>", methods=["POST"])
def completa_promemoria(promemoria_id):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM promemoria WHERE id = %s;", (promemoria_id,))
    p = cur.fetchone()
    if p:
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
    flash("Promemoria eliminato.", "success")
    return redirect(url_for("promemoria"))

@app.route("/fornitori", methods=["GET", "POST"])
def fornitori():
    if not (session.get('is_admin') or session.get('puo_gestire_fornitori', 1)):
        flash("Accesso non autorizzato.", "error")
        return redirect(url_for('index'))
    conn = get_db_connection()
    cur = conn.cursor()
    if request.method == "POST":
        nome = request.form.get("nome_azienda")
        if nome:
            cur.execute("INSERT INTO fornitori (nome_azienda, settore_note, indirizzo, p_iva, telefono, email) VALUES (%s, %s, %s, %s, %s, %s) ON CONFLICT (nome_azienda) DO NOTHING;", (nome, request.form.get("settore_note"), request.form.get("indirizzo"), request.form.get("p_iva"), request.form.get("telefono"), request.form.get("email")))
            conn.commit()
            flash("Fornitore salvato!", "success")
        return redirect(url_for("fornitori"))
    cur.execute("SELECT * FROM fornitori ORDER BY nome_azienda ASC;")
    lista = cur.fetchall()
    cur.close()
    conn.close()
    return render_template("fornitori.html", fornitori=lista)

@app.route("/modifica_fornitore/<int:fornitore_id>", methods=["POST"])
def modifica_fornitore(fornitore_id):
    if not (session.get('is_admin') or session.get('puo_gestire_fornitori', 1)):
        flash("Permesso negato.", "error")
        return redirect(url_for("fornitori"))
    nome = request.form.get("nome_azienda")
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("UPDATE fornitori SET nome_azienda = %s, settore_note = %s, indirizzo = %s, p_iva = %s, telefono = %s, email = %s WHERE id = %s;", 
                    (nome, request.form.get("settore_note"), request.form.get("indirizzo"), request.form.get("p_iva"), request.form.get("telefono"), request.form.get("email"), fornitore_id))
        conn.commit()
        cur.close()
        conn.close()
        flash("Fornitore aggiornato!", "success")
    except Exception as e:
        flash(f"Errore: {e}", "error")
    return redirect(url_for("fornitori"))

@app.route("/elimina_fornitore/<int:fornitore_id>", methods=["POST"])
def elimina_fornitore(fornitore_id):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM fornitori WHERE id = %s;", (fornitore_id,))
    conn.commit()
    cur.close()
    conn.close()
    flash("Fornitore eliminato.", "success")
    return redirect(url_for("fornitori"))

@app.route("/fornitore/<int:fornitore_id>", methods=["GET", "POST"])
def dettaglio_fornitore(fornitore_id):
    conn = get_db_connection()
    cur = conn.cursor()
    if request.method == "POST":
        nome = request.form.get("nome")
        tel = request.form.get("telefono")
        if nome and tel:
            cur.execute("INSERT INTO contatti_tecnici (fornitore_id, nome, telefono, mansione, email) VALUES (%s, %s, %s, %s, %s);", 
                        (fornitore_id, nome, tel, request.form.get("mansione"), request.form.get("email")))
            conn.commit()
            flash("Contatto aggiunto!", "success")
        cur.close()
        conn.close()
        return redirect(url_for("dettaglio_fornitore", fornitore_id=fornitore_id))
    cur.execute("SELECT * FROM fornitori WHERE id = %s;", (fornitore_id,))
    fornitore = cur.fetchone()
    cur.execute("SELECT * FROM contatti_tecnici WHERE fornitore_id = %s;", (fornitore_id,))
    contatti = cur.fetchall()
    cur.close()
    conn.close()
    return render_template("dettaglio_fornitore.html", fornitore=fornitore, contatti=contatti)

@app.route("/elimina_contatto_tecnico/<int:contatto_id>/<int:fornitore_id>", methods=["POST"])
def elimina_contatto_tecnico(contatto_id, fornitore_id):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM contatti_tecnici WHERE id = %s;", (contatto_id,))
    conn.commit()
    cur.close()
    conn.close()
    flash("Contatto eliminato.", "success")
    return redirect(url_for("dettaglio_fornitore", fornitore_id=fornitore_id))

@app.route("/documenti", defaults={"cartella_id": None}, methods=["GET", "POST"])
@app.route("/documenti/<int:cartella_id>", methods=["GET", "POST"])
def documenti(cartella_id):
    if not (session.get('is_admin') or session.get('puo_gestire_documenti', 1)):
        flash("Accesso negato.", "error")
        return redirect(url_for('index'))
    conn = get_db_connection()
    cur = conn.cursor()
    if request.method == "POST":
        azione = request.form.get("azione")
        if azione == "crea_cartella":
            cur.execute("INSERT INTO cartelle (nome, parent_id) VALUES (%s, %s);", (request.form.get("nome_cartella"), cartella_id))
            conn.commit()
        elif azione == "carica_file":
            f = request.files.get("file_caricato")
            if f and f.filename:
                cur.execute("INSERT INTO documenti (cartella_id, nome_file, tipo_file, dati_file) VALUES (%s, %s, %s, %s);", (cartella_id, f.filename, f.mimetype, f.read()))
                conn.commit()
        cur.close()
        conn.close()
        return redirect(url_for("documenti", cartella_id=cartella_id) if cartella_id else url_for("documenti"))

    cur.execute("SELECT * FROM cartelle WHERE parent_id " + ("= %s" if cartella_id else "IS NULL") + " ORDER BY nome ASC;", (cartella_id,) if cartella_id else ())
    sottocartelle = cur.fetchall()
    cur.execute("SELECT id, nome_file, tipo_file, caricato_il FROM documenti WHERE cartella_id " + ("= %s" if cartella_id else "IS NULL") + " ORDER BY nome_file ASC;", (cartella_id,) if cartella_id else ())
    lista_file = cur.fetchall()
    cur.close()
    conn.close()
    return render_template("documenti.html", sottocartelle=sottocartelle, lista_file=lista_file, cartella_corrente=None)

@app.route("/scarica_file/<int:file_id>")
def scarica_file(file_id):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT nome_file, tipo_file, dati_file FROM documenti WHERE id = %s;", (file_id,))
    doc = cur.fetchone()
    cur.close()
    conn.close()
    if doc:
        return send_file(io.BytesIO(doc['dati_file']), download_name=doc['nome_file'], mimetype=doc['tipo_file'] or 'application/octet-stream', as_attachment=True)
    flash("File non trovato.", "error")
    return redirect(url_for("documenti"))

@app.route("/elimina_file/<int:file_id>", methods=["POST"])
def elimina_file(file_id):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM documenti WHERE id = %s;", (file_id,))
    conn.commit()
    cur.close()
    conn.close()
    flash("File eliminato.", "success")
    return redirect(url_for("documenti"))

@app.route("/elimina_cartella/<int:cartella_id>", methods=["POST"])
def elimina_cartella(cartella_id):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM cartelle WHERE id = %s;", (cartella_id,))
    conn.commit()
    cur.close()
    conn.close()
    flash("Cartella eliminata.", "success")
    return redirect(url_for("documenti"))

@app.route("/aggiungi", methods=["POST"])
def aggiungi_prodotto():
    qr_code = request.form.get("qr_code")
    nome = request.form.get("nome")
    sap = request.form.get("sap", "")
    peso = request.form.get("peso", "")
    quantita = int(request.form.get("quantita", 0))
    soglia_minima = int(request.form.get("soglia_minima", 3) or 3)
    posizione = request.form.get("posizione", "")
    flag_sezione = 1 if request.form.get("magazzino_pesante") else 0
    matricola = request.form.get("matricola", "").strip()
    stato_pezzo = request.form.get("stato_pezzo", "Nuovo")

    if not qr_code or not nome:
        flash("QR Code e Nome sono obbligatori!", "error")
        return redirect(url_for("index"))

    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO prodotti (qr_code, nome, sap, peso, quantita, posizione, magazzino_pesante, soglia_minima, matricola, stato_pezzo)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (qr_code)
            DO UPDATE SET 
                quantita = prodotti.quantita + EXCLUDED.quantita,
                nome = EXCLUDED.nome,
                sap = EXCLUDED.sap,
                peso = EXCLUDED.peso,
                posizione = EXCLUDED.posizione,
                magazzino_pesante = EXCLUDED.magazzino_pesante,
                soglia_minima = EXCLUDED.soglia_minima,
                matricola = EXCLUDED.matricola,
                stato_pezzo = EXCLUDED.stato_pezzo;
        """, (qr_code, nome, sap, peso, quantita, posizione, flag_sezione, soglia_minima, matricola, stato_pezzo))
        conn.commit()
        cur.close()
        conn.close()
        flash("Prodotto salvato con successo!", "success")
    except Exception as e:
        flash(f"Errore: {e}", "error")

    return redirect(url_for("magazzino_pesante") if flag_sezione == 1 else url_for("index"))

@app.route("/aggiorna/<qr_code>", methods=["POST"])
def aggiorna_prodotto(qr_code):
    nome = request.form.get("nome")
    sap = request.form.get("sap", "")
    posizione = request.form.get("posizione", "")
    peso = request.form.get("peso", "")
    soglia_minima = int(request.form.get("soglia_minima", 3) or 3)
    matricola = request.form.get("matricola", "").strip()
    flag_sezione = 1 if request.form.get("magazzino_pesante") else 0

    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("""
            UPDATE prodotti 
            SET nome = %s, sap = %s, posizione = %s, peso = %s, soglia_minima = %s, matricola = %s, magazzino_pesante = %s
            WHERE qr_code = %s;
        """, (nome, sap, posizione, peso, soglia_minima, matricola, flag_sezione, qr_code))
        conn.commit()
        cur.close()
        conn.close()
        flash("Articolo aggiornato con successo!", "success")
    except Exception as e:
        flash(f"Errore: {e}", "error")
    return redirect(url_for("gestisci_prodotto", qr_code=qr_code))

@app.route("/gestisci/<qr_code>")
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

    storico_prodotto = []
    try:
        cur.execute("SELECT * FROM storico_manutenzioni WHERE qr_code = %s ORDER BY id DESC;", (qr_code,))
        storico_prodotto = cur.fetchall()
    except Exception:
        pass

    cur.close()
    conn.close()
    if not prodotto:
        flash("Prodotto non trovato!", "error")
        return redirect(url_for("index"))
    return render_template("gestisci.html", prodotto=prodotto, fornitori=lista_fornitori, storico_prodotto=storico_prodotto)

@app.route("/storico_manutenzioni")
def storico_manutenzioni():
    if not (session.get('is_admin') or session.get('puo_vedere_storico_manutenzioni', 1)):
        flash("Accesso allo storico negato.", "error")
        return redirect(url_for('index'))
    storico = []
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT * FROM storico_manutenzioni ORDER BY registrato_il DESC, id DESC;")
        storico = cur.fetchall()
        cur.close()
        conn.close()
    except Exception as e:
        print(f"Errore caricamento storico: {e}")
    return render_template("storico_manutenzioni.html", storico=storico)

@app.route("/elimina_storico_manutenzione/<int:storico_id>", methods=["POST"])
def elimina_storico_manutenzione(storico_id):
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("DELETE FROM storico_manutenzioni WHERE id = %s;", (storico_id,))
        conn.commit()
        cur.close()
        conn.close()
        flash("Record eliminato dallo storico.", "success")
    except Exception as e:
        flash(f"Errore eliminazione: {e}", "error")
    return redirect(url_for('storico_manutenzioni'))

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

@app.route("/stampa_tutti_qr")
def stampa_tutti_qr():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM prodotti ORDER BY nome ASC;")
    prodotti = cur.fetchall()
    cur.close()
    conn.close()
    return render_template("stampa_tutti_qr.html", prodotti=prodotti)

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
        flash("Articolo inviato in manutenzione e registrato nello storico!", "success")
    except Exception as e:
        flash(f"Errore: {e}", "error")
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
            cur.execute("""
                UPDATE storico_manutenzioni 
                SET esito = %s, data_riconsegna = CURRENT_DATE, note = COALESCE(NULLIF(%s, ''), note)
                WHERE qr_code = %s AND (data_riconsegna IS NULL OR data_riconsegna = '');
            """, (esito, note_rientro, qr_code))

            cur.execute("""
                UPDATE prodotti 
                SET quantita = quantita + %s,
                    volte_riparato = COALESCE(volte_riparato, 0) + 1,
                    stato_pezzo = %s,
                    in_manutenzione = FALSE,
                    cliente_manutenzione = NULL,
                    quantita_manutenzione = 0,
                    data_spedizione = NULL,
                    data_riconsegna = NULL,
                    vettore = NULL,
                    ordine_amministrativo = FALSE,
                    note_manutenzione = NULL
                WHERE qr_code = %s;
            """, (qta_rientro, esito, qr_code))

        conn.commit()
        cur.close()
        conn.close()
        flash(f"Articolo rientrato in magazzino con esito: {esito}!", "success")
    except Exception as e:
        flash(f"Errore: {e}", "error")
    return redirect(url_for("gestisci_prodotto", qr_code=qr_code))

@app.route("/elimina/<qr_code>", methods=["POST"])
def elimina_prodotto(qr_code):
    if not (session.get('is_admin') or session.get('puo_eliminare', 0)):
        flash("Permesso negato per eliminare gli articoli.", "error")
        return redirect(url_for("index"))
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("DELETE FROM prodotti WHERE qr_code = %s;", (qr_code,))
        conn.commit()
        cur.close()
        conn.close()
        flash("Prodotto eliminato con successo.", "success")
    except Exception as e:
        flash(f"Errore eliminazione: {e}", "error")
    return redirect(url_for("index"))

@app.route("/carica_scarica/<qr_code>/<azione>", methods=["POST"])
def carica_scarica(qr_code, azione):
    quantita = int(request.form.get("quantita_movimento", 1))
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        if azione == 'carica':
            cur.execute("UPDATE prodotti SET quantita = quantita + %s WHERE qr_code = %s;", (quantita, qr_code))
        elif azione == 'scarica':
            cur.execute("UPDATE prodotti SET quantita = GREATEST(0, quantita - %s) WHERE qr_code = %s;", (quantita, qr_code))
        conn.commit()
        cur.close()
        conn.close()
        flash(f"Operazione di {azione} eseguita!", "success")
    except Exception as e:
        flash(f"Errore movimento: {e}", "error")
    return redirect(url_for("gestisci_prodotto", qr_code=qr_code))

@app.route("/magazzino_pesante")
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
            if p.get('magazzino_pesante') in [1, '1', True, 1.0]:
                prodotti.append(p)
    except Exception as e:
        print(f"Errore magazzino pesante: {e}")
    return render_template("magazzino_pesante.html", prodotti=prodotti)

@app.route("/manutenzioni")
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
        headers={"Content-disposition": "attachment; filename=Inventario_Gestionale_OMG.csv"}
    )

if __name__ == "__main__":
    app.run(debug=True)
