# ========================================================================
# Gestionale OMG Application - Complete System with Notifications & All Modules
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
        if not destinatario:
            return
        destinatario_clean = str(destinatario).strip()
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO notifiche (destinatario, titolo, messaggio, link, letta)
            VALUES (%s, %s, %s, %s, FALSE);
        """, (destinatario_clean, titolo, messaggio, link))
        conn.commit()
        cur.close()
        conn.close()
    except Exception as e:
        print(f"Errore inserimento notifica: {e}")

def parse_data_flessibile(data_str):
    if not data_str:
        return None
    for fmt in ('%Y-%m-%d', '%d/%m/%Y', '%Y/%m/%d', '%d-%m-%Y'):
        try:
            return datetime.strptime(str(data_str).strip(), fmt).date()
        except ValueError:
            continue
    return None

@app.context_processor
def utility_processor():
    return dict(parse_data_flessibile=parse_data_flessibile)

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
                puo_vedere_report_ore INT DEFAULT 1,
                puo_vedere_omd INT DEFAULT 1,
                puo_vedere_lavori_interni INT DEFAULT 1,
                puo_gestire_agenda INT DEFAULT 1
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
                bottiglia_precedente VARCHAR(255),
                bottiglia_nuova VARCHAR(255),
                tempo_cambio VARCHAR(50),
                num_bottiglie_tempera INT DEFAULT 0,
                num_bottiglie_tempera_vecchia INT DEFAULT 0,
                num_bottiglie_tempera_nuova INT DEFAULT 0,
                quantita_trattamento VARCHAR(50),
                misura_piastrina VARCHAR(50),
                misura_piastrina_nuova VARCHAR(50),
                creato_il TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS nastri (
                id SERIAL PRIMARY KEY,
                codice_sap VARCHAR(255),
                numero VARCHAR(255),
                nome VARCHAR(255),
                sezione_impianto VARCHAR(255),
                misura VARCHAR(255),
                tipo VARCHAR(255),
                utilizzo VARCHAR(255),
                misura_nastro_finito VARCHAR(255),
                tipo_di_riduttore VARCHAR(255),
                tipo_di_motore VARCHAR(255),
                tappeto_presente BOOLEAN DEFAULT TRUE,
                note TEXT,
                creato_il TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS agenda (
                id SERIAL PRIMARY KEY,
                titolo VARCHAR(255) NOT NULL,
                descrizione TEXT,
                data_scadenza VARCHAR(50),
                nome_azienda VARCHAR(255),
                utenti_visibili VARCHAR(255) DEFAULT '',
                sezione VARCHAR(50) DEFAULT 'agenda',
                creato_da VARCHAR(255),
                richiesto_da VARCHAR(255),
                data_inizio VARCHAR(50),
                data_fine VARCHAR(50),
                completato BOOLEAN DEFAULT FALSE,
                creato_il TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        
        cur.execute("ALTER TABLE agenda ADD COLUMN IF NOT EXISTS sezione VARCHAR(50) DEFAULT 'agenda';")
        cur.execute("ALTER TABLE agenda ADD COLUMN IF NOT EXISTS richiesto_da VARCHAR(255);")
        cur.execute("ALTER TABLE agenda ADD COLUMN IF NOT EXISTS data_inizio VARCHAR(50);")
        cur.execute("ALTER TABLE agenda ADD COLUMN IF NOT EXISTS data_fine VARCHAR(50);")
        cur.execute("ALTER TABLE agenda ADD COLUMN IF NOT EXISTS completato BOOLEAN DEFAULT FALSE;")
        cur.execute("ALTER TABLE cambi_serie ADD COLUMN IF NOT EXISTS misura_piastrina_nuova VARCHAR(50);")

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
            ("puo_vedere_report_ore", "INT DEFAULT 1"),
            ("puo_vedere_omd", "INT DEFAULT 1"),
            ("puo_vedere_lavori_interni", "INT DEFAULT 1"),
            ("puo_gestire_agenda", "INT DEFAULT 1")
        ]
        
        for p_col, p_type in permessi_lista:
            cur.execute(f"ALTER TABLE utenti ADD COLUMN IF NOT EXISTS {p_col} {p_type};")
        
        cur.execute("SELECT * FROM utenti WHERE username = 'admin';")
        if not cur.fetchone():
            hashed_pw = generate_password_hash("admin")
            cur.execute("""
                INSERT INTO utenti (username, password, is_admin, puo_vedere_magazzino, puo_aggiungere_prodotti, puo_modificare_prodotti, puo_caricare_scaricare, puo_eliminare, puo_vedere_pesante, puo_vedere_manutenzione, puo_aprire_manutenzioni, puo_gestire_interventi, puo_assegnare_manutenzioni, puo_eliminare_interventi, puo_vedere_manutenzioni_esterne, puo_vedere_storico_manutenzioni, puo_eliminare_storico, puo_gestire_fornitori, puo_importare_fornitori, puo_gestire_documenti, puo_eliminare_documenti, puo_vedere_promemoria, puo_assegnare_promemoria, puo_vedere_report_ore, puo_vedere_omd, puo_vedere_lavori_interni, puo_gestire_agenda)
                VALUES (%s, %s, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1);
            """, ('admin', hashed_pw))

        conn.commit()
        cur.close()
        conn.close()
        print("Database e permessi inizializzati con successo.")
    except Exception as e:
        print(f"Errore init_db: {e}")

init_db()

@app.before_request
def require_login():
    allowed_routes = ['login', 'registra', 'static']
    if request.endpoint and request.endpoint not in allowed_routes and 'username' not in session:
        return redirect(url_for('login'))

# --- API NOTIFICHE CORRETTE E ROBUSTE ---
@app.route("/api/notifiche")
def api_notifiche():
    username = session.get('username')
    if not username:
        return jsonify([])
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("""
            SELECT id, titolo, messaggio, link, letta, creato_il 
            FROM notifiche 
            WHERE LOWER(TRIM(destinatario)) = LOWER(TRIM(%s)) 
               OR LOWER(TRIM(destinatario)) = 'tutti'
            ORDER BY creato_il DESC LIMIT 20;
        """, (str(username).strip(),))
        rows = cur.fetchall()
        cur.close()
        conn.close()
        
        notifiche = []
        for r in rows:
            notifiche.append({
                "id": r['id'],
                "titolo": r['titolo'],
                "messaggio": r['messaggio'],
                "link": r['link'] or '#',
                "letta": r['letta'],
                "creato_il": r['creato_il'].isoformat() if r['creato_il'] else ""
            })
        return jsonify(notifiche)
    except Exception as e:
        print(f"Errore API notifiche: {e}")
        return jsonify([])

@app.route("/api/notifiche/segna_lette", methods=["POST"])
def api_segna_lette():
    username = session.get('username')
    if username:
        try:
            conn = get_db_connection()
            cur = conn.cursor()
            cur.execute(
                "UPDATE notifiche SET letta = TRUE WHERE LOWER(TRIM(destinatario)) = LOWER(TRIM(%s)) OR LOWER(TRIM(destinatario)) = 'tutti';",
                (str(username).strip(),)
            )
            conn.commit()
            cur.close()
            conn.close()
        except Exception as e:
            print(f"Errore segna lette: {e}")
    return jsonify({"status": "ok"})

@app.route("/api/notifiche/elimina/<int:notifica_id>", methods=["POST"])
def api_elimina_notifica(notifica_id):
    username = session.get('username')
    if username:
        try:
            conn = get_db_connection()
            cur = conn.cursor()
            cur.execute("DELETE FROM notifiche WHERE id = %s;", (notifica_id,))
            conn.commit()
            cur.close()
            conn.close()
        except Exception as e:
            print(f"Errore elimina notifica: {e}")
    return jsonify({"status": "ok"})

# --- HOME ---
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

# --- AUTENTICAZIONE ---
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
                    INSERT INTO utenti (username, password, is_admin, puo_vedere_magazzino, puo_aggiungere_prodotti, puo_modificare_prodotti, puo_caricare_scaricare, puo_eliminare, puo_vedere_pesante, puo_vedere_manutenzione, puo_aprire_manutenzioni, puo_gestire_interventi, puo_assegnare_manutenzioni, puo_eliminare_interventi, puo_vedere_manutenzioni_esterne, puo_vedere_storico_manutenzioni, puo_eliminare_storico, puo_gestire_fornitori, puo_importare_fornitori, puo_gestire_documenti, puo_eliminare_documenti, puo_vedere_promemoria, puo_assegnare_promemoria, puo_vedere_report_ore, puo_vedere_omd, puo_vedere_lavori_interni, puo_gestire_agenda)
                    VALUES (%s, %s, 0, 1, 1, 1, 1, 0, 1, 1, 1, 1, 1, 0, 1, 1, 0, 1, 1, 1, 0, 1, 0, 1, 1, 1, 1);
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

# --- ADMIN & UTENTI ---
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

# --- NASTRI ---
@app.route("/nastri", methods=["GET", "POST"])
@app.route("/nastri.html", methods=["GET", "POST"])
def nastri():
    if not (session.get('is_admin') or session.get('puo_vedere_magazzino', 1)):
        flash("Accesso al modulo Nastri non autorizzato.", "error")
        return redirect(url_for('index'))

    conn = get_db_connection()
    cur = conn.cursor()

    if request.method == "POST":
        codice_sap = request.form.get("codice_sap", "").strip()
        numero = request.form.get("numero", "").strip()
        sezione_impianto = request.form.get("sezione_impianto", "COMPOSIZIONE").strip()
        misura = request.form.get("misura", "").strip()
        tipo = request.form.get("tipo", "").strip()
        utilizzo = request.form.get("utilizzo", "").strip()
        misura_nastro_finito = request.form.get("misura_nastro_finito", "").strip()
        tipo_di_riduttore = request.form.get("tipo_di_riduttore", "").strip()
        tipo_di_motore = request.form.get("tipo_di_motore", "").strip()
        tappeto_presente = True if request.form.get("tappeto_presente", "1") == "1" else False
        note = request.form.get("note", "").strip()
        nome = f"Nastro {numero} - {sezione_impianto}"

        try:
            cur.execute("""
                INSERT INTO nastri (codice_sap, numero, nome, sezione_impianto, misura, tipo, utilizzo, misura_nastro_finito, tipo_di_riduttore, tipo_di_motore, tappeto_presente, note)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s);
            """, (codice_sap, numero, nome, sezione_impianto, misura, tipo, utilizzo, misura_nastro_finito, tipo_di_riduttore, tipo_di_motore, tappeto_presente, note))
            conn.commit()
            registra_log(f"Aggiunto nuovo nastro: {numero} ({sezione_impianto})")
            flash("Nastro aggiunto con successo!", "success")
        except Exception as e:
            flash(f"Errore inserimento nastro: {e}", "error")
        
        cur.close()
        conn.close()
        return redirect(url_for("nastri"))

    sezione_filtro = request.args.get("sezione", "Tutte")
    cur.execute("SELECT DISTINCT sezione_impianto FROM nastri WHERE sezione_impianto IS NOT NULL AND sezione_impianto != '' ORDER BY sezione_impianto ASC;")
    sezioni_disponibili = [r['sezione_impianto'] for r in cur.fetchall()]

    if sezione_filtro != "Tutte":
        cur.execute("SELECT * FROM nastri WHERE sezione_impianto = %s ORDER BY numero ASC, id DESC;", (sezione_filtro,))
    else:
        cur.execute("SELECT * FROM nastri ORDER BY sezione_impianto ASC, numero ASC;")
    
    lista_nastri = cur.fetchall()
    cur.close()
    conn.close()

    return render_template("nastri.html", nastri=lista_nastri, sezioni_disponibili=sezioni_disponibili, sezione_filtro=sezione_filtro)

@app.route("/toggle_tappeto/<int:nastro_id>", methods=["POST"])
def toggle_tappeto(nastro_id):
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT tappeto_presente FROM nastri WHERE id = %s;", (nastro_id,))
        res = cur.fetchone()
        if res:
            nuovo_stato = not (res.get('tappeto_presente') if res.get('tappeto_presente') is not None else True)
            cur.execute("UPDATE nastri SET tappeto_presente = %s WHERE id = %s;", (nuovo_stato, nastro_id))
            conn.commit()
            registra_log(f"Aggiornato stato tappeto ID {nastro_id} a {nuovo_stato}")
        cur.close()
        conn.close()
    except Exception as e:
        flash(f"Errore cambio stato tappeto: {e}", "error")
    return redirect(url_for("nastri"))

@app.route("/modifica_nastro/<int:nastro_id>", methods=["POST"])
def modifica_nastro(nastro_id):
    codice_sap = request.form.get("codice_sap", "").strip()
    numero = request.form.get("numero", "").strip()
    sezione_impianto = request.form.get("sezione_impianto", "").strip()
    misura = request.form.get("misura", "").strip()
    tipo = request.form.get("tipo", "").strip()
    utilizzo = request.form.get("utilizzo", "").strip()
    misura_nastro_finito = request.form.get("misura_nastro_finito", "").strip()
    tipo_di_riduttore = request.form.get("tipo_di_riduttore", "").strip()
    tipo_di_motore = request.form.get("tipo_di_motore", "").strip()
    note = request.form.get("note", "").strip()

    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("""
            UPDATE nastri 
            SET codice_sap = %s, numero = %s, sezione_impianto = %s, misura = %s, tipo = %s, utilizzo = %s, misura_nastro_finito = %s, tipo_di_riduttore = %s, tipo_di_motore = %s, note = %s
            WHERE id = %s;
        """, (codice_sap, numero, sezione_impianto, misura, tipo, utilizzo, misura_nastro_finito, tipo_di_riduttore, tipo_di_motore, note, nastro_id))
        conn.commit()
        cur.close()
        conn.close()
        registra_log(f"Modificato nastro ID {nastro_id}")
        flash("Nastro aggiornato con successo!", "success")
    except Exception as e:
        flash(f"Errore aggiornamento nastro: {e}", "error")
    return redirect(url_for("nastri"))

@app.route("/elimina_nastro/<int:nastro_id>", methods=["POST"])
def elimina_nastro(nastro_id):
    if not (session.get('is_admin') or session.get('puo_eliminare', 0)):
        flash("Permesso negato.", "error")
        return redirect(url_for("nastri"))
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("DELETE FROM nastri WHERE id = %s;", (nastro_id,))
        conn.commit()
        cur.close()
        conn.close()
        registra_log(f"Eliminato nastro ID {nastro_id}")
        flash("Nastro eliminato.", "success")
    except Exception as e:
        flash(f"Errore eliminazione nastro: {e}", "error")
    return redirect(url_for("nastri"))

@app.route("/esporta_nastri_csv")
def esporta_nastri_csv():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT codice_sap, numero, sezione_impianto, misura, tipo, utilizzo, misura_nastro_finito, tipo_di_riduttore, tipo_di_motore, tappeto_presente, note FROM nastri ORDER BY sezione_impianto ASC, numero ASC;")
    nastri_list = cur.fetchall()
    cur.close()
    conn.close()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['Codice SAP', 'Numero', 'Sezione Impianto', 'Misura', 'Tipo', 'Utilizzo', 'Misura Finito', 'Riduttore', 'Motore', 'Tappeto Presente', 'Note'])
    for n in nastri_list:
        writer.writerow([
            n.get('codice_sap', ''), n.get('numero', ''), n.get('sezione_impianto', ''),
            n.get('misura', ''), n.get('tipo', ''), n.get('utilizzo', ''),
            n.get('misura_nastro_finito', ''), n.get('tipo_di_riduttore', ''),
            n.get('tipo_di_motore', ''), 'Presente' if n.get('tappeto_presente', True) else 'Assente', n.get('note', '')
        ])
    return Response(output.getvalue(), mimetype="text/csv", headers={"Content-disposition": "attachment; filename=Magazzino_Nastri_OMG.csv"})

@app.route("/stampa_nastri")
def stampa_nastri():
    sezione = request.args.get("sezione", "Tutte")
    conn = get_db_connection()
    cur = conn.cursor()
    if sezione != "Tutte":
        cur.execute("SELECT * FROM nastri WHERE sezione_impianto = %s ORDER BY numero ASC;", (sezione,))
    else:
        cur.execute("SELECT * FROM nastri ORDER BY sezione_impianto ASC, numero ASC;")
    lista = cur.fetchall()
    cur.close()
    conn.close()
    return render_template("stampa_nastri.html", nastri=lista, sezione=sezione)

# --- AGENDA / OMD / LAVORI INTERNI ---
@app.route("/agenda", methods=["GET", "POST"])
@app.route("/agenda.html", methods=["GET", "POST"])
def agenda():
    if not session.get('username'):
        return redirect(url_for('login'))
    
    username_corrente = session.get('username')
    is_admin = session.get('is_admin')
    sezione_corrente = request.form.get("sezione_target") or request.args.get("sezione", "agenda")
    filtro_stato = request.args.get("stato", "attive")
    
    conn = get_db_connection()
    cur = conn.cursor()
    
    titoli_mappa = {"agenda": "Agenda", "omd": "OMD", "lavori_interni": "Lavori Interni"}
    titolo_sezione = titoli_mappa.get(sezione_corrente, "Agenda")
    
    if request.method == "POST":
        titolo = request.form.get("titolo")
        descrizione = request.form.get("descrizione", "")
        data_scadenza = request.form.get("data_scadenza", "")
        richiesto_da = request.form.get("richiesto_da", "").strip()
        data_inizio = request.form.get("data_inizio", "").strip()
        data_fine = request.form.get("data_fine", "").strip()
        nome_azienda = request.form.get("fornitore_input", "")
        utenti_selezionati = request.form.getlist("utenti_visibili[]")
        sezione_form = request.form.get("sezione_target") or sezione_corrente
        utenti_visibili = ", ".join(utenti_selezionati) if utenti_selezionati else ""
        
        if titolo:
            cur.execute("""
                INSERT INTO agenda (titolo, descrizione, data_scadenza, richiesto_da, data_inizio, data_fine, nome_azienda, utenti_visibili, sezione, creato_da, completato)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, FALSE);
            """, (titolo, descrizione, data_scadenza, richiesto_da, data_inizio, data_fine, nome_azienda, utenti_visibili, sezione_form, username_corrente))
            conn.commit()
            
            if utenti_selezionati:
                if "Tutti" in utenti_selezionati:
                    cur.execute("SELECT username FROM utenti;")
                    for u_dict in cur.fetchall():
                        crea_notifica(u_dict['username'], f"📅 Nuova Attività ({titoli_mappa.get(sezione_form, 'Agenda')})", f"Nuova attività: {titolo}", f"/agenda?sezione={sezione_form}")
                else:
                    for tec in utenti_selezionati:
                        if tec.strip():
                            crea_notifica(tec.strip(), f"📅 Nuova Attività Assegnata", f"Ti è stata assegnata: {titolo}", f"/agenda?sezione={sezione_form}")
            
            registra_log(f"Creata attività in {sezione_form}: {titolo}")
            flash("Attività aggiunta con successo!", "success")
            
        cur.close()
        conn.close()
        return redirect(url_for('agenda', sezione=sezione_form, stato=filtro_stato))

    bool_completato = True if filtro_stato == "completate" else False
    try:
        if is_admin:
            cur.execute("SELECT * FROM agenda WHERE sezione = %s AND completato = %s ORDER BY data_scadenza ASC NULLS LAST, id DESC;", (sezione_corrente, bool_completato))
        else:
            cur.execute("""
                SELECT * FROM agenda 
                WHERE sezione = %s AND completato = %s 
                  AND (utenti_visibili LIKE %s OR utenti_visibili = 'Tutti' OR utenti_visibili = '' OR utenti_visibili IS NULL)
                ORDER BY data_scadenza ASC NULLS LAST, id DESC;
            """, (sezione_corrente, bool_completato, f"%{username_corrente}%"))
        attivita = cur.fetchall()
    except Exception:
        cur.execute("SELECT * FROM agenda WHERE sezione = %s AND completato = %s ORDER BY id DESC;", (sezione_corrente, bool_completato))
        attivita = cur.fetchall()

    cur.execute("SELECT username FROM utenti ORDER BY username ASC;")
    utenti = cur.fetchall()
    cur.execute("SELECT nome_azienda FROM fornitori ORDER BY nome_azienda ASC;")
    fornitori = cur.fetchall()
    cur.close()
    conn.close()
    
    return render_template("agenda.html", attivita=attivita, utenti=utenti, fornitori=fornitori, titolo_sezione=titolo_sezione, sezione_corrente=sezione_corrente, filtro_stato=filtro_stato)

@app.route("/omd")
@app.route("/omd.html")
def omd():
    return redirect(url_for('agenda', sezione='omd'))

@app.route("/lavori_interni")
@app.route("/lavori_interni.html")
def lavori_interni():
    return redirect(url_for('agenda', sezione='lavori_interni'))

@app.route("/completa_agenda/<int:agenda_id>", methods=["POST"])
def completa_agenda(agenda_id):
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT sezione, completato FROM agenda WHERE id = %s;", (agenda_id,))
        res = cur.fetchone()
        sezione = res['sezione'] if res and 'sezione' in res else 'agenda'
        stato_attuale = res['completato'] if res and 'completato' in res else False
        nuovo_stato = not stato_attuale
        
        if nuovo_stato:
            data_oggi = datetime.now().strftime('%Y-%m-%d')
            cur.execute("UPDATE agenda SET completato = TRUE, data_fine = COALESCE(NULLIF(data_fine, ''), %s) WHERE id = %s;", (data_oggi, agenda_id))
        else:
            cur.execute("UPDATE agenda SET completato = FALSE WHERE id = %s;", (agenda_id,))
            
        conn.commit()
        cur.close()
        conn.close()
        flash("Stato attività aggiornato!", "success")
        return redirect(url_for('agenda', sezione=sezione, stato=('completate' if nuovo_stato else 'attive')))
    except Exception as e:
        flash(f"Errore: {e}", "error")
        return redirect(url_for('agenda'))

@app.route("/modifica_agenda/<int:agenda_id>", methods=["POST"])
def modifica_agenda(agenda_id):
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT sezione FROM agenda WHERE id = %s;", (agenda_id,))
        res = cur.fetchone()
        sezione = res['sezione'] if res and 'sezione' in res else 'agenda'
        
        titolo = request.form.get("titolo")
        descrizione = request.form.get("descrizione", "")
        richiesto_da = request.form.get("richiesto_da", "").strip()
        data_inizio = request.form.get("data_inizio", "").strip()
        data_fine = request.form.get("data_fine", "").strip()
        nome_azienda = request.form.get("fornitore_input", "")
        utenti_selezionati = request.form.getlist("utenti_visibili[]")
        utenti_visibili = ", ".join(utenti_selezionati) if utenti_selezionati else ""
        
        cur.execute("""
            UPDATE agenda 
            SET titolo = %s, descrizione = %s, richiesto_da = %s, data_inizio = %s, data_fine = %s, data_scadenza = %s, nome_azienda = %s, utenti_visibili = %s
            WHERE id = %s;
        """, (titolo, descrizione, richiesto_da, data_inizio, data_fine, data_fine, nome_azienda, utenti_visibili, agenda_id))
        conn.commit()
        cur.close()
        conn.close()
        flash("Attività modificata con successo!", "success")
        return redirect(url_for('agenda', sezione=sezione))
    except Exception as e:
        flash(f"Errore: {e}", "error")
        return redirect(url_for('agenda'))

@app.route("/stampa_archivio_agenda")
def stampa_archivio_agenda():
    sezione = request.args.get("sezione", "omd")
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM agenda WHERE sezione = %s AND completato = TRUE ORDER BY data_fine DESC NULLS LAST, id DESC;", (sezione,))
    lista = cur.fetchall()
    cur.close()
    conn.close()
    titoli_mappa = {"omd": "OMD", "lavori_interni": "Lavori Interni", "agenda": "Agenda"}
    return render_template("stampa_archivio_agenda.html", attivita=lista, nome_sezione=titoli_mappa.get(sezione, sezione.upper()))

@app.route("/elimina_agenda/<int:agenda_id>", methods=["POST"])
def elimina_agenda(agenda_id):
    if not session.get('is_admin'):
        flash("Accesso non autorizzato.", "error")
        return redirect(url_for("agenda"))
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT sezione FROM agenda WHERE id = %s;", (agenda_id,))
        res = cur.fetchone()
        sezione = res['sezione'] if res and 'sezione' in res else 'agenda'
        cur.execute("DELETE FROM agenda WHERE id = %s;", (agenda_id,))
        conn.commit()
        cur.close()
        conn.close()
        flash("Attività eliminata.", "success")
        return redirect(url_for('agenda', sezione=sezione))
    except Exception as e:
        flash(f"Errore: {e}", "error")
        return redirect(url_for("agenda"))

# --- CAMBI SERIE & API ---
@app.route("/api/ultima_bottiglia/<forno>/<linea>")
def ultima_bottiglia(forno, linea):
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("""
            SELECT bottiglia_nuova, nome_bottiglia, num_bottiglie_tempera_nuova, num_bottiglie_tempera, misura_piastrina_nuova, misura_piastrina
            FROM cambi_serie WHERE forno = %s AND linea = %s ORDER BY id DESC LIMIT 1;
        """, (forno, linea))
        ultimo = cur.fetchone()
        cur.close()
        conn.close()
        if ultimo:
            return jsonify({
                "bottiglia": ultimo.get('bottiglia_nuova') or ultimo.get('nome_bottiglia') or "",
                "tempera": ultimo.get('num_bottiglie_tempera_nuova') if ultimo.get('num_bottiglie_tempera_nuova') is not None else (ultimo.get('num_bottiglie_tempera') or 0),
                "piastrina": ultimo.get('misura_piastrina_nuova') or ultimo.get('misura_piastrina') or ""
            })
        return jsonify({"bottiglia": "", "tempera": 0, "piastrina": ""})
    except Exception:
        return jsonify({"bottiglia": "", "tempera": 0, "piastrina": ""})

@app.route("/cambi_serie", methods=["GET", "POST"])
@app.route("/cambi_serie.html", methods=["GET", "POST"])
def cambi_serie():
    forno_filtro = request.args.get("forno", "Tutti")
    settimana_filtro = request.args.get("settimana", "").strip()
    conn = get_db_connection()
    cur = conn.cursor()
    query = "SELECT * FROM cambi_serie WHERE 1=1"
    params = []
    if forno_filtro != "Tutti":
        query += " AND forno = %s"
        params.append(forno_filtro)
    query += " ORDER BY data_cambio ASC, id ASC;"
    cur.execute(query, tuple(params))
    tutti_record = cur.fetchall()
    cur.close()
    conn.close()

    record_serie = []
    dt_lunedì, dt_domenica = None, None
    if settimana_filtro:
        try:
            parts = settimana_filtro.split('-W')
            if len(parts) == 2:
                anno, settimana = int(parts[0]), int(parts[1])
                dt_lunedì = datetime.fromisocalendar(anno, settimana, 1).date()
                dt_domenica = datetime.fromisocalendar(anno, settimana, 7).date()
        except Exception:
            pass

    for r in tutti_record:
        aggiungi = True
        if settimana_filtro and dt_lunedì and dt_domenica:
            dt_cambio = parse_data_flessibile(r.get('data_cambio', ''))
            if dt_cambio and not (dt_lunedì <= dt_cambio <= dt_domenica):
                aggiungi = False
            elif not dt_cambio:
                aggiungi = False
        if aggiungi:
            record_serie.append(r)

    return render_template("cambi_serie.html", record_serie=record_serie, forno_filtro=forno_filtro, settimana_filtro=settimana_filtro)

@app.route("/aggiungi_cambio_serie", methods=["POST"])
def aggiungi_cambio_serie():
    forno = request.form.get("forno")
    linea = request.form.get("linea")
    data_cambio = request.form.get("data_cambio")
    bottiglia_precedente = request.form.get("bottiglia_precedente", "")
    bottiglia_nuova = request.form.get("bottiglia_nuova", "")
    tempo_cambio = request.form.get("tempo_cambio", "")
    num_bottiglie_tempera_vecchia = int(request.form.get("num_bottiglie_tempera_vecchia", 0) or 0)
    num_bottiglie_tempera_nuova = int(request.form.get("num_bottiglie_tempera_nuova", 0) or 0)
    misura_piastrina = request.form.get("misura_piastrina", "").strip()

    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO cambi_serie (forno, linea, data_cambio, bottiglia_precedente, bottiglia_nuova, nome_bottiglia, tempo_cambio, num_bottiglie_tempera_vecchia, num_bottiglie_tempera_nuova, num_bottiglie_tempera, misura_piastrina, misura_piastrina_nuova)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s);
        """, (forno, linea, data_cambio, bottiglia_precedente, bottiglia_nuova, bottiglia_nuova, tempo_cambio, num_bottiglie_tempera_vecchia, num_bottiglie_tempera_nuova, num_bottiglie_tempera_nuova, misura_piastrina, misura_piastrina))
        conn.commit()
        cur.close()
        conn.close()
        flash("Cambio serie registrato!", "success")
    except Exception as e:
        flash(f"Errore: {e}", "error")
    return redirect(url_for("cambi_serie"))

@app.route("/modifica_cambio_serie/<int:id_cambio>", methods=["POST"])
def modifica_cambio_serie(id_cambio):
    forno = request.form.get("forno")
    linea = request.form.get("linea")
    data_cambio = request.form.get("data_cambio")
    bottiglia_precedente = request.form.get("bottiglia_precedente", "")
    bottiglia_nuova = request.form.get("bottiglia_nuova", "")
    tempo_cambio = request.form.get("tempo_cambio", "")
    num_bottiglie_tempera_vecchia = int(request.form.get("num_bottiglie_tempera_vecchia", 0) or 0)
    num_bottiglie_tempera_nuova = int(request.form.get("num_bottiglie_tempera_nuova", 0) or 0)
    misura_piastrina = request.form.get("misura_piastrina", "").strip()

    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("""
            UPDATE cambi_serie 
            SET forno = %s, linea = %s, data_cambio = %s, bottiglia_precedente = %s, bottiglia_nuova = %s, nome_bottiglia = %s, tempo_cambio = %s, num_bottiglie_tempera_vecchia = %s, num_bottiglie_tempera_nuova = %s, num_bottiglie_tempera = %s, misura_piastrina = %s, misura_piastrina_nuova = %s
            WHERE id = %s;
        """, (forno, linea, data_cambio, bottiglia_precedente, bottiglia_nuova, bottiglia_nuova, tempo_cambio, num_bottiglie_tempera_vecchia, num_bottiglie_tempera_nuova, num_bottiglie_tempera_nuova, misura_piastrina, misura_piastrina, id_cambio))
        conn.commit()
        cur.close()
        conn.close()
        flash("Cambio serie aggiornato!", "success")
    except Exception as e:
        flash(f"Errore: {e}", "error")
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
        flash("Eliminato.", "success")
    except Exception as e:
        flash(f"Errore: {e}", "error")
    return redirect(url_for("cambi_serie"))

@app.route("/esporta_cambi_serie_csv")
def esporta_cambi_serie_csv():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT data_cambio, forno, linea, bottiglia_precedente, bottiglia_nuova, nome_bottiglia, tempo_cambio, num_bottiglie_tempera_vecchia, num_bottiglie_tempera_nuova, num_bottiglie_tempera, misura_piastrina, misura_piastrina_nuova FROM cambi_serie ORDER BY data_cambio ASC;")
    righe = cur.fetchall()
    cur.close()
    conn.close()
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['Data Cambio', 'Forno', 'Linea', 'Smontante', 'Montante', 'Tempo', 'Tempera Vecchia', 'Tempera Nuova', 'Piastrina'])
    for r in righe:
        writer.writerow([
            r.get('data_cambio', ''), r.get('forno', ''), r.get('linea', ''),
            r.get('bottiglia_precedente') or r.get('nome_bottiglia', ''), r.get('bottiglia_nuova', ''), r.get('tempo_cambio', ''),
            r.get('num_bottiglie_tempera_vecchia', 0), r.get('num_bottiglie_tempera_nuova') if r.get('num_bottiglie_tempera_nuova') is not None else r.get('num_bottiglie_tempera', 0),
            r.get('misura_piastrina_nuova') or r.get('misura_piastrina', '')
        ])
    return Response(output.getvalue(), mimetype="text/csv", headers={"Content-disposition": "attachment; filename=Cambi_Serie_OMG.csv"})

# --- REPORT ORE ---
@app.route("/report_ore")
@app.route("/report_ore.html")
def report_ore():
    if not (session.get('is_admin') or session.get('puo_vedere_report_ore', 1)):
        flash("Accesso non autorizzato.", "error")
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

    query = "SELECT id, titolo, impianto_macchina, priorita, tipo_guasto, stato, assegnato_a, creato_da, inizio_lavoro, fine_lavoro, COALESCE(tempo_lavorato_minuti, 0) as tempo_lavorato_minuti, creato_il FROM richieste_manutenzione WHERE 1=1"
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
        for tec in assegnati:
            if tec in ore_per_tecnico:
                ore_per_tecnico[tec] += (minuti / 60.0)

    cur.close()
    conn.close()

    totale_ore_generale = round(totale_minuti_generale / 60.0, 1)
    chart_tecnici_labels = [k for k, v in ore_per_tecnico.items() if filtro_tecnico == "Tutti" or k == filtro_tecnico]
    chart_tecnici_values = [round(ore_per_tecnico[k], 1) for k in chart_tecnici_labels]
    chart_tipi_labels = list(ore_per_tipo.keys())
    chart_tipi_values = [round(v, 1) for v in ore_per_tipo.values()]

    return render_template("report_ore.html", utenti=utenti, interventi=interventi_filtrati, filtro_tecnico=filtro_tecnico, data_inizio=data_inizio, data_fine=data_fine, periodo_predefinito=periodo_predefinito, totale_ore_generale=totale_ore_generale, totale_interventi=len(interventi_filtrati), chart_tecnici_labels=chart_tecnici_labels, chart_tecnici_values=chart_tecnici_values, chart_tipi_labels=chart_tipi_labels, chart_tipi_values=chart_tipi_values)

# --- RICHIESTE MANUTENZIONE (OFFICINA) ---
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
            flash("Permesso negato.", "error")
            return redirect(url_for("richieste_manutenzione"))

        titolo = request.form.get("titolo")
        impianto_macchina = request.form.get("impianto_macchina", "")
        descrizione = request.form.get("descrizione", "")
        priorita = request.form.get("priorita", "Media")
        tipo_guasto = request.form.get("tipo_guasto", "Meccanico")
        
        tecnici_selezionati = request.form.getlist("assegnato_a[]") if puo_assegnare else [username_corrente]
        assegnato_a = ", ".join(tecnici_selezionati) if tecnici_selezionati else username_corrente
        
        allegato_nome, allegato_dati = None, None
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
                if tec.strip():
                    crea_notifica(tec.strip(), "🛠️ Nuova Manutenzione Assegnata", f"Intervento su {impianto_macchina}: {titolo}", "/richieste_manutenzione")

            flash("Richiesta creata con successo!", "success")
        cur.close()
        conn.close()
        return redirect(url_for("richieste_manutenzione"))

    cur.execute("SELECT username FROM utenti ORDER BY username ASC;")
    lista_utenti = cur.fetchall()
    cur.execute("SELECT qr_code, nome, quantita FROM prodotti ORDER BY nome ASC;")
    lista_prodotti = cur.fetchall()
    cur.execute("""
        SELECT id, titolo, impianto_macchina, descrizione, priorita, stato, tipo_guasto, assegnato_a, creato_da, inizio_lavoro, fine_lavoro, COALESCE(tempo_lavorato_minuti, 0) AS tempo_lavorato_minuti, note_lavoro, allegato_nome, creato_il 
        FROM richieste_manutenzione ORDER BY CASE WHEN stato = 'Completata' THEN 2 ELSE 1 END, creato_il DESC;
    """)
    richieste = cur.fetchall()
    ricambi_per_intervento = {}
    for r in richieste:
        cur.execute("SELECT qr_code, nome_ricambio, quantita FROM intervento_ricambi WHERE intervento_id = %s;", (r['id'],))
        ricambi_per_intervento[r['id']] = cur.fetchall()

    cur.close()
    conn.close()
    return render_template("richieste_manutenzione.html", richieste=richieste, lista_utenti=lista_utenti, lista_prodotti=lista_prodotti, ricambi_per_intervento=ricambi_per_intervento, puo_aprire=puo_aprire, puo_assegnare=puo_assegnare, puo_gestire=puo_gestire, puo_elimina_int=puo_elimina_int)

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
            flash("Intervento avviato!", "success")
        elif nuovo_stato == 'In Pausa':
            inizio = req.get('inizio_lavoro')
            minuti = int((now - inizio).total_seconds() / 60) if (inizio and req.get('stato') == 'In Lavoro') else 0
            cur.execute("UPDATE richieste_manutenzione SET stato = %s, tempo_lavorato_minuti = COALESCE(tempo_lavorato_minuti, 0) + %s, inizio_lavoro = NULL WHERE id = %s;", (nuovo_stato, minuti, intervento_id))
            flash("Intervento in pausa.", "warning")
        elif nuovo_stato == 'Attesa Ricambio':
            cur.execute("UPDATE richieste_manutenzione SET stato = %s, note_lavoro = COALESCE(NULLIF(%s, ''), note_lavoro) WHERE id = %s;", (nuovo_stato, note_lavoro, intervento_id))
            flash("In attesa ricambio.", "warning")
        elif nuovo_stato == 'Completata':
            inizio = req.get('inizio_lavoro')
            minuti = int((now - inizio).total_seconds() / 60) if (inizio and req.get('stato') == 'In Lavoro') else 0
            tempo_totale = req.get('tempo_lavorato_minuti', 0) + minuti

            for qr, qta_str in zip(request.form.getlist("ricambio_qr[]"), request.form.getlist("ricambio_qta[]")):
                if qr and qta_str and int(qta_str) > 0:
                    qta = int(qta_str)
                    cur.execute("SELECT * FROM prodotti WHERE qr_code = %s;", (qr,))
                    prod = cur.fetchone()
                    if prod:
                        cur.execute("UPDATE prodotti SET quantita = GREATEST(0, quantita - %s) WHERE qr_code = %s;", (qta, qr))
                        cur.execute("INSERT INTO intervento_ricambi (intervento_id, qr_code, nome_ricambio, quantita) VALUES (%s, %s, %s, %s);", (intervento_id, qr, prod['nome'], qta))

            cur.execute("UPDATE richieste_manutenzione SET stato = %s, fine_lavoro = %s, tempo_lavorato_minuti = %s, note_lavoro = COALESCE(NULLIF(%s, ''), note_lavoro) WHERE id = %s;", (nuovo_stato, now, tempo_totale, note_lavoro, intervento_id))
            if req.get('creato_da') and req.get('creato_da') != username_corrente:
                crea_notifica(req.get('creato_da'), "✅ Intervento Completato", f"Completato intervento su {req.get('impianto_macchina')}", "/richieste_manutenzione")
            flash("Intervento completato!", "success")
        elif nuovo_stato == 'Riassegna':
            tecnici_nuovi = request.form.getlist("nuovi_assegnatari[]")
            nuova_lista = ", ".join(tecnici_nuovi) if tecnici_nuovi else ""
            cur.execute("UPDATE richieste_manutenzione SET assegnato_a = %s WHERE id = %s;", (nuova_lista, intervento_id))
            for tec in tecnici_nuovi:
                if tec.strip():
                    crea_notifica(tec.strip(), "🔄 Intervento Riassegnato", f"Ti è stato riassegnato l'intervento su {req.get('impianto_macchina')}", "/richieste_manutenzione")
            flash("Riassegnato con successo.", "success")
        conn.commit()
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
        return send_file(io.BytesIO(res['allegato_dati']), download_name=res['allegato_nome'] or f"intervento_{intervento_id}.jpg", as_attachment=True)
    flash("Allegato non trovato.", "error")
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
    return render_template("stampa_intervento.html", r=intervento, ricambi=ricambi, intervento=intervento)

@app.route("/elimina_intervento/<int:intervento_id>", methods=["POST"])
def elimina_intervento(intervento_id):
    if not (session.get('is_admin') or session.get('puo_eliminare_interventi')):
        flash("Permesso negato.", "error")
        return redirect(url_for("richieste_manutenzione"))
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM richieste_manutenzione WHERE id = %s;", (intervento_id,))
    conn.commit()
    cur.close()
    conn.close()
    flash("Intervento eliminato.", "success")
    return redirect(url_for("richieste_manutenzione"))

# --- PROMEMORIA ---
@app.route("/promemoria", methods=["GET", "POST"])
@app.route("/promemoria.html", methods=["GET", "POST"])
def promemoria():
    if not (session.get('is_admin') or session.get('puo_vedere_promemoria', 1)):
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
        assegnato_a = request.form.get("assegnato_a", "").strip() or username_corrente
        
        if titolo:
            cur.execute("""
                INSERT INTO promemoria (titolo, descrizione, data_scadenza, priorita, ricorrenza, assegnato_a)
                VALUES (%s, %s, %s, %s, %s, %s);
            """, (titolo, descrizione, data_scadenza, priorita, ricorrenza, assegnato_a))
            conn.commit()
            crea_notifica(assegnato_a, "📌 Nuovo Promemoria Assegnato", f"Promemoria: {titolo}", "/promemoria")
            flash("Promemoria aggiunto!", "success")
        cur.close()
        conn.close()
        return redirect(url_for("promemoria"))
        
    cur.execute("SELECT username FROM utenti ORDER BY username ASC;")
    lista_utenti = cur.fetchall()
    if is_admin or puo_assegnare:
        cur.execute("SELECT * FROM promemoria ORDER BY completato ASC, data_scadenza ASC;")
    else:
        cur.execute("SELECT * FROM promemoria WHERE assegnato_a = %s OR assegnato_a IS NULL OR assegnato_a = '' ORDER BY completato ASC, data_scadenza ASC;", (username_corrente,))
    lista_promemoria = cur.fetchall()
    cur.close()
    conn.close()
    return render_template("promemoria.html", promemoria=lista_promemoria, lista_utenti=lista_utenti, puo_assegnare=True)

@app.route("/completa_promemoria/<int:promemoria_id>", methods=["POST"])
def completa_promemoria(promemoria_id):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM promemoria WHERE id = %s;", (promemoria_id,))
    p = cur.fetchone()
    if p:
        ricorrenza = p.get('ricorrenza', 'Nessuna')
        data_str = p.get('data_scadenza')
        if ricorrenza and ricorrenza != 'Nessuna' and data_str:
            try:
                dt = datetime.strptime(data_str, '%Y-%m-%d')
                if ricorrenza == 'Giorno': dt += timedelta(days=1)
                elif ricorrenza == 'Settimana': dt += timedelta(weeks=1)
                elif ricorrenza == 'Mese': dt = dt.replace(year=dt.year + (dt.month // 12), month=(dt.month % 12) + 1)
                elif ricorrenza == 'Anno': dt = dt.replace(year=dt.year + 1)
                cur.execute("UPDATE promemoria SET data_scadenza = %s, completato = FALSE WHERE id = %s;", (dt.strftime('%Y-%m-%d'), promemoria_id))
            except Exception:
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
    flash("Promemoria eliminato.", "success")
    return redirect(url_for("promemoria"))

# --- FORNITORI & CONTATTI ---
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
                ON CONFLICT (nome_azienda) DO UPDATE SET settore_note = EXCLUDED.settore_note, indirizzo = EXCLUDED.indirizzo, p_iva = EXCLUDED.p_iva, telefono = EXCLUDED.telefono, email = EXCLUDED.email;
            """, (nome_azienda, settore_note, indirizzo, p_iva, telefono, email))
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
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("UPDATE fornitori SET nome_azienda = %s, settore_note = %s, indirizzo = %s, p_iva = %s, telefono = %s, email = %s WHERE id = %s;",
                (request.form.get("nome_azienda"), request.form.get("settore_note", ""), request.form.get("indirizzo", ""), request.form.get("p_iva", ""), request.form.get("telefono", ""), request.form.get("email", ""), fornitore_id))
    conn.commit()
    cur.close()
    conn.close()
    flash("Fornitore aggiornato.", "success")
    return redirect(url_for("fornitori"))

@app.route("/fornitore/<int:fornitore_id>", methods=["GET", "POST"])
@app.route("/dettaglio_fornitore.html/<int:fornitore_id>", methods=["GET", "POST"])
def dettaglio_fornitore(fornitore_id):
    conn = get_db_connection()
    cur = conn.cursor()
    if request.method == "POST":
        cur.execute("INSERT INTO contatti_tecnici (fornitore_id, nome, telefono, mansione, email) VALUES (%s, %s, %s, %s, %s);",
                    (fornitore_id, request.form.get("nome"), request.form.get("telefono"), request.form.get("mansione", ""), request.form.get("email", "")))
        conn.commit()
        flash("Contatto aggiunto.", "success")
        cur.close()
        conn.close()
        return redirect(url_for("dettaglio_fornitore", fornitore_id=fornitore_id))
    cur.execute("SELECT * FROM fornitori WHERE id = %s;", (fornitore_id,))
    fornitore = cur.fetchone()
    cur.execute("SELECT * FROM contatti_tecnici WHERE fornitore_id = %s ORDER BY nome ASC;", (fornitore_id,))
    contatti = cur.fetchall()
    cur.close()
    conn.close()
    return render_template("dettaglio_fornitore.html", fornitore=fornitore, contatti=contatti)

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

@app.route("/esporta_fornitori_csv")
def esporta_fornitori_csv():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT nome_azienda, settore_note, indirizzo, p_iva, telefono, email FROM fornitori ORDER BY nome_azienda ASC;")
    fornitori_list = cur.fetchall()
    cur.close()
    conn.close()
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['Azienda', 'Settore', 'Indirizzo', 'P.IVA', 'Telefono', 'Email'])
    for f in fornitori_list:
        writer.writerow([f.get('nome_azienda', ''), f.get('settore_note', ''), f.get('indirizzo', ''), f.get('p_iva', ''), f.get('telefono', ''), f.get('email', '')])
    return Response(output.getvalue(), mimetype="text/csv", headers={"Content-disposition": "attachment; filename=Fornitori_OMG.csv"})

# --- DOCUMENTI & CARTELLE ---
@app.route("/documenti", defaults={"cartella_id": None}, methods=["GET", "POST"])
@app.route("/documenti/<int:cartella_id>", methods=["GET", "POST"])
@app.route("/documenti.html", defaults={"cartella_id": None}, methods=["GET", "POST"])
def documenti(cartella_id):
    if not (session.get('is_admin') or session.get('puo_gestire_documenti', 1)):
        flash("Accesso negato.", "error")
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
            nome = request.form.get("nome_cartella")
            if nome:
                cur.execute("INSERT INTO cartelle (nome, parent_id) VALUES (%s, %s);", (nome, cartella_id))
                conn.commit()
                flash("Cartella creata.", "success")
        elif azione == "carica_file":
            file_caricato = request.files.get("file_caricato")
            if file_caricato and file_caricato.filename:
                cur.execute("INSERT INTO documenti (cartella_id, nome_file, tipo_file, dati_file) VALUES (%s, %s, %s, %s);",
                            (cartella_id, file_caricato.filename, file_caricato.mimetype, file_caricato.read()))
                conn.commit()
                flash("File caricato.", "success")
        cur.close()
        conn.close()
        return redirect(url_for("documenti", cartella_id=cartella_id) if cartella_id else url_for("documenti"))

    cur.execute("SELECT * FROM cartelle WHERE parent_id " + ("= %s" if cartella_id else "IS NULL") + " ORDER BY nome ASC;", (cartella_id,) if cartella_id else ())
    sottocartelle = cur.fetchall()
    cur.execute("SELECT id, nome_file, tipo_file, caricato_il FROM documenti WHERE cartella_id " + ("= %s" if cartella_id else "IS NULL") + " ORDER BY nome_file ASC;", (cartella_id,) if cartella_id else ())
    lista_file = cur.fetchall()
    cur.close()
    conn.close()
    return render_template("documenti.html", cartella_corrente=cartella_corrente, sottocartelle=sottocartelle, lista_file=lista_file, percorso_breadcrumb=percorso_breadcrumb, puo_elimina_doc=(session.get('is_admin') or session.get('puo_eliminare_documenti', 0)))

@app.route("/scarica_file/<int:file_id>")
def scarica_file(file_id):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT nome_file, tipo_file, dati_file FROM documenti WHERE id = %s;", (file_id,))
    f = cur.fetchone()
    cur.close()
    conn.close()
    if f:
        return send_file(io.BytesIO(f['dati_file']), mimetype=f['tipo_file'], as_attachment=True, download_name=f['nome_file'])
    flash("File non trovato.", "error")
    return redirect(url_for("documenti"))

@app.route("/elimina_file/<int:file_id>", methods=["POST"])
def elimina_file(file_id):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT cartella_id FROM documenti WHERE id = %s;", (file_id,))
    res = cur.fetchone()
    cartella_id = res['cartella_id'] if res else None
    cur.execute("DELETE FROM documenti WHERE id = %s;", (file_id,))
    conn.commit()
    cur.close()
    conn.close()
    flash("File eliminato.", "success")
    return redirect(url_for("documenti", cartella_id=cartella_id) if cartella_id else url_for("documenti"))

@app.route("/elimina_cartella/<int:cartella_id>", methods=["POST"])
def elimina_cartella(cartella_id):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT parent_id FROM cartelle WHERE id = %s;", (cartella_id,))
    res = cur.fetchone()
    parent_id = res['parent_id'] if res else None
    cur.execute("DELETE FROM cartelle WHERE id = %s;", (cartella_id,))
    conn.commit()
    cur.close()
    conn.close()
    flash("Cartella eliminata.", "success")
    return redirect(url_for("documenti", cartella_id=parent_id) if parent_id else url_for("documenti"))

# --- ESPORTAZIONI & UTILITY ---
@app.route("/esportazioni")
@app.route("/esportazioni.html")
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
    writer.writerow(['QR Code', 'Nome', 'SAP', 'Quantita', 'Posizione', 'Peso', 'Pesante'])
    for p in prodotti:
        writer.writerow([p.get('qr_code', ''), p.get('nome', ''), p.get('sap', ''), p.get('quantita', 0), p.get('posizione', ''), p.get('peso', ''), 'Si' if p.get('magazzino_pesante') else 'No'])
    return Response(output.getvalue(), mimetype="text/csv", headers={"Content-disposition": "attachment; filename=Inventario_OMG.csv"})

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
    writer.writerow(['ID', 'Titolo', 'Macchina', 'Priorità', 'Tipo Guasto', 'Stato', 'Assegnato A', 'Creato Da', 'Inizio', 'Fine', 'Minuti', 'Note', 'Creato Il'])
    for r in richieste:
        writer.writerow([r.get('id', ''), r.get('titolo', ''), r.get('impianto_macchina', ''), r.get('priorita', ''), r.get('tipo_guasto', ''), r.get('stato', ''), r.get('assegnato_a', ''), r.get('creato_da', ''), r.get('inizio_lavoro', ''), r.get('fine_lavoro', ''), r.get('tempo_lavorato_minuti', 0), r.get('note_lavoro', ''), r.get('creato_il', '')])
    return Response(output.getvalue(), mimetype="text/csv", headers={"Content-disposition": "attachment; filename=Report_Interventi_OMG.csv"})

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
                        cur.execute("INSERT INTO prodotti (qr_code, nome, sap, quantita, posizione) VALUES (%s, %s, %s, %s, %s) ON CONFLICT (qr_code) DO UPDATE SET nome = EXCLUDED.nome, sap = EXCLUDED.sap, quantita = prodotti.quantita + EXCLUDED.quantita, posizione = EXCLUDED.posizione;",
                                    (row[0].strip(), row[1].strip(), row[2].strip() if len(row) > 2 else "", int(row[3].strip()) if len(row) > 3 and row[3].strip().isdigit() else 0, row[4].strip() if len(row) > 4 else ""))
                        count += 1
                conn.commit()
                cur.close()
                conn.close()
                flash(f"Importati {count} articoli!", "success")
            except Exception as e:
                flash(f"Errore CSV: {e}", "error")
        return redirect(url_for("upload"))
    return render_template("upload.html")

@app.route("/stampa_tutti_qr")
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
def stampa_singolo_qr(qr_code):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM prodotti WHERE qr_code = %s;", (qr_code,))
    prodotto = cur.fetchone()
    cur.close()
    conn.close()
    return render_template("stampa_singolo_qr.html", prodotto=prodotto)

@app.route("/qr_scaffale", methods=["GET"])
def qr_scaffale():
    ubicazione = request.args.get("ubicazione", "")
    conn = get_db_connection()
    cur = conn.cursor()
    prodotti = []
    if ubicazione:
        cur.execute("SELECT * FROM prodotti WHERE posizione ILIKE %s ORDER BY nome ASC;", (f"%{ubicazione}%",))
        prodotti = cur.fetchall()
    cur.close()
    conn.close()
    return render_template("qr_scaffale.html", prodotti=prodotti, ubicazione=ubicazione)

# --- MAGAZZINO PESANTE & MANUTENZIONI ESTERNE ---
@app.route("/magazzino_pesante")
@app.route("/magazzino_pesante.html")
def magazzino_pesante():
    if not (session.get('is_admin') or session.get('puo_vedere_pesante', 1)):
        return redirect(url_for('index'))
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM prodotti ORDER BY nome ASC;")
    tutti = cur.fetchall()
    cur.close()
    conn.close()
    prodotti = [p for p in tutti if p.get('magazzino_pesante') in [1, '1', True, 1.0]]
    return render_template("magazzino_pesante.html", prodotti=prodotti)

@app.route("/esporta_pesante")
def esporta_pesante():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT qr_code, nome, sap, quantita, posizione, peso FROM prodotti WHERE magazzino_pesante IN (1, '1', true) ORDER BY nome ASC;")
    prodotti = cur.fetchall()
    cur.close()
    conn.close()
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['QR Code', 'Nome', 'SAP', 'Quantita', 'Posizione', 'Peso'])
    for p in prodotti:
        writer.writerow([p.get('qr_code', ''), p.get('nome', ''), p.get('sap', ''), p.get('quantita', 0), p.get('posizione', ''), p.get('peso', '')])
    return Response(output.getvalue(), mimetype="text/csv", headers={"Content-disposition": "attachment; filename=Magazzino_Pesante_OMG.csv"})

@app.route("/manutenzioni")
@app.route("/manutenzioni.html")
def manutenzioni():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM prodotti ORDER BY nome ASC;")
    tutti = cur.fetchall()
    cur.close()
    conn.close()
    prodotti = [p for p in tutti if p.get('in_manutenzione') in [1, '1', True, 1.0]]
    return render_template("manutenzioni.html", prodotti=prodotti)

@app.route("/storico_manutenzioni")
@app.route("/storico_manutenzioni.html")
def storico_manutenzioni():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM storico_manutenzioni ORDER BY registrato_il DESC;")
    storico = cur.fetchall()
    cur.close()
    conn.close()
    return render_template("storico_manutenzioni.html", storico=storico)

@app.route("/esporta_storico_manutenzioni_csv")
def esporta_storico_manutenzioni_csv():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM storico_manutenzioni ORDER BY registrato_il DESC;")
    storico = cur.fetchall()
    cur.close()
    conn.close()
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['ID', 'Data', 'Prodotto', 'QR', 'SAP', 'Cliente', 'Qta', 'Spedizione', 'Riconsegna', 'Vettore', 'Ordine Amm.', 'Note'])
    for s in storico:
        writer.writerow([s.get('id', ''), s.get('registrato_il', ''), s.get('nome_prodotto', ''), s.get('qr_code', ''), s.get('sap', ''), s.get('cliente', ''), s.get('quantita', 0), s.get('data_spedizione', ''), s.get('data_riconsegna', ''), s.get('vettore', ''), 'Si' if s.get('ordine_amministrativo') else 'No', s.get('note', '')])
    return Response(output.getvalue(), mimetype="text/csv", headers={"Content-disposition": "attachment; filename=Storico_Manutenzioni_OMG.csv"})

@app.route("/elimina_storico_manutenzione/<int:storico_id>", methods=["POST"])
def elimina_storico_manutenzione(storico_id):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM storico_manutenzioni WHERE id = %s;", (storico_id,))
    conn.commit()
    cur.close()
    conn.close()
    flash("Eliminato dallo storico.", "success")
    return redirect(url_for('storico_manutenzioni'))

@app.route("/stampa_bolla/<qr_code>")
def stampa_bolla(qr_code):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM prodotti WHERE qr_code = %s;", (qr_code,))
    prodotto = cur.fetchone()
    cur.close()
    conn.close()
    return render_template("bolla.html", prodotto=prodotto)

# --- CARICO, SCARICO & GESTIONE PRODOTTI ---
@app.route("/carico", methods=["GET", "POST"])
@app.route("/carico.html", methods=["GET", "POST"])
def carico():
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
            flash("Carico effettuato!", "success")
            return redirect(url_for("gestisci_prodotto", qr_code=qr_code))
    return render_template("carico.html")

@app.route("/scarico", methods=["GET", "POST"])
@app.route("/scarico.html", methods=["GET", "POST"])
def scarico():
    if request.method == "POST":
        qr_code = request.form.get("qr_code")
        qta = int(request.form.get("quantita", 1))
        if qr_code:
            conn = get_db_connection()
            cur = conn.cursor()
            cur.execute("SELECT quantita FROM prodotti WHERE qr_code = %s;", (qr_code,))
            p = cur.fetchone()
            if p:
                nuova = max(0, p['quantita'] - qta)
                cur.execute("UPDATE prodotti SET quantita = %s WHERE qr_code = %s;", (nuova, qr_code))
                conn.commit()
            cur.close()
            conn.close()
            flash("Scarico effettuato!", "success")
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
            p = cur.fetchone()
            cur.close()
            conn.close()
            if p:
                return redirect(url_for("gestisci_prodotto", qr_code=qr_code))
            flash("Articolo non trovato.", "error")
    return render_template("scanner_globale.html")

@app.route("/gestisci/<qr_code>")
@app.route("/gestisci.html/<qr_code>")
def gestisci_prodotto(qr_code):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM prodotti WHERE qr_code = %s;", (qr_code,))
    prodotto = cur.fetchone()
    cur.execute("SELECT * FROM fornitori ORDER BY nome_azienda ASC;")
    fornitori = cur.fetchall()
    cur.close()
    conn.close()
    return render_template("gestisci.html", prodotto=prodotto, fornitori=fornitori)

@app.route("/aggiorna/<qr_code>", methods=["POST"])
@app.route("/aggiorna_prodotto/<qr_code>", methods=["POST"])
def aggiorna_prodotto(qr_code):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("UPDATE prodotti SET nome = %s, sap = %s, posizione = %s, peso = %s, magazzino_pesante = %s, soglia_minima = %s WHERE qr_code = %s;",
                (request.form.get("nome"), request.form.get("sap", ""), request.form.get("posizione", ""), request.form.get("peso", ""), 1 if request.form.get("magazzino_pesante") else 0, int(request.form.get("soglia_minima", 3) or 3), qr_code))
    conn.commit()
    cur.close()
    conn.close()
    flash("Articolo aggiornato.", "success")
    return redirect(url_for("gestisci_prodotto", qr_code=qr_code))

@app.route("/aggiungi", methods=["POST"])
@app.route("/aggiungi_prodotto", methods=["POST"])
def aggiungi_prodotto():
    qr_code = request.form.get("qr_code", "").strip()
    nome = request.form.get("nome")
    sap = request.form.get("sap", "")
    peso = request.form.get("peso", "")
    quantita = int(request.form.get("quantita", 0) or 0)
    soglia_minima = int(request.form.get("soglia_minima", 3) or 3)
    posizione = request.form.get("posizione", "")
    flag_sezione = 1 if request.form.get("magazzino_pesante") else 0

    if not nome:
        flash("Nome obbligatorio.", "error")
        return redirect(url_for("index"))

    conn = get_db_connection()
    cur = conn.cursor()
    if not qr_code:
        cur.execute("SELECT COUNT(*) + 1 as next_id FROM prodotti;")
        res = cur.fetchone()
        next_num = res['next_id'] if res else 1
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
        ON CONFLICT (qr_code) DO UPDATE SET quantita = prodotti.quantita + EXCLUDED.quantita, nome = EXCLUDED.nome, sap = EXCLUDED.sap, peso = EXCLUDED.peso, posizione = EXCLUDED.posizione, magazzino_pesante = EXCLUDED.magazzino_pesante, soglia_minima = EXCLUDED.soglia_minima;
    """, (qr_code, nome, sap, peso, quantita, posizione, flag_sezione, soglia_minima))
    conn.commit()
    cur.close()
    conn.close()
    flash(f"Prodotto salvato (QR: {qr_code})", "success")
    return redirect(url_for("magazzino_pesante") if flag_sezione == 1 else url_for("index"))

@app.route("/manda_manutenzione/<qr_code>", methods=["POST"])
def manda_manutenzione(qr_code):
    cliente = request.form.get("cliente_manutenzione")
    qta = int(request.form.get("quantita_manutenzione", 1))
    spedizione = request.form.get("data_spedizione", "").strip() or None
    riconsegna = request.form.get("data_riconsegna", "").strip() or None
    vettore = request.form.get("vettore", "").strip()
    ordine_amm = True if request.form.get("ordine_amministrativo") else False
    note = request.form.get("note_manutenzione", "").strip()

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM prodotti WHERE qr_code = %s;", (qr_code,))
    prod = cur.fetchone()
    cur.execute("""
        UPDATE prodotti SET quantita = GREATEST(0, quantita - %s), in_manutenzione = TRUE, cliente_manutenzione = %s, quantita_manutenzione = %s, data_spedizione = %s, data_riconsegna = %s, vettore = %s, ordine_amministrativo = %s, note_manutenzione = %s WHERE qr_code = %s;
    """, (qta, cliente, qta, spedizione, riconsegna, vettore, ordine_amm, note, qr_code))
    if prod:
        cur.execute("""
            INSERT INTO storico_manutenzioni (nome_prodotto, qr_code, sap, cliente, quantita, data_spedizione, data_riconsegna, vettore, ordine_amministrativo, note)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s);
        """, (prod['nome'], qr_code, prod['sap'], cliente, qta, spedizione, riconsegna, vettore, ordine_amm, note))
    conn.commit()
    cur.close()
    conn.close()
    flash("Inviato in manutenzione.", "success")
    return redirect(url_for("gestisci_prodotto", qr_code=qr_code))

@app.route("/ripristina_magazzino/<qr_code>", methods=["POST"])
def ripristina_magazzino(qr_code):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        UPDATE prodotti SET quantita = quantita + quantita_manutenzione, in_manutenzione = FALSE, cliente_manutenzione = NULL, quantita_manutenzione = 0, data_spedizione = NULL, data_riconsegna = NULL, vettore = NULL, ordine_amministrativo = FALSE, note_manutenzione = NULL WHERE qr_code = %s;
    """, (qr_code,))
    conn.commit()
    cur.close()
    conn.close()
    flash("Rientrato in magazzino.", "success")
    return redirect(url_for("gestisci_prodotto", qr_code=qr_code))

@app.route("/elimina", methods=["POST"])
@app.route("/elimina_prodotto/<qr_code>", methods=["POST"])
def elimina_prodotto(qr_code=None):
    if not (session.get('is_admin') or session.get('puo_eliminare', 0)):
        flash("Permesso negato.", "error")
        return redirect(url_for("index"))
    if not qr_code:
        qr_code = request.form.get("qr_code")
    if qr_code:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("DELETE FROM prodotti WHERE qr_code = %s;", (qr_code,))
        conn.commit()
        cur.close()
        conn.close()
        flash("Articolo eliminato.", "success")
    return redirect(url_for("index"))

if __name__ == "__main__":
    app.run(debug=True)
