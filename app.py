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
                bottiglia_precedente VARCHAR(255),
                bottiglia_nuova VARCHAR(255),
                tempo_cambio VARCHAR(50),
                num_bottiglie_tempera INT DEFAULT 0,
                num_bottiglie_tempera_vecchia INT DEFAULT 0,
                num_bottiglie_tempera_nuova INT DEFAULT 0,
                quantita_trattamento VARCHAR(50),
                misura_piastrina VARCHAR(50),
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
                utenti_visibili VARCHAR(255) DEFAULT 'Tutti',
                creato_da VARCHAR(255),
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
    ubicazioni_disponibili = []
    promemoria_urgenti = 0
    interventi_aperti_count = 0
    
    username = session.get('username')
    is_admin = session.get('is_admin')
    puo_assegnare = session.get('puo_assegnare_promemoria')
    
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        cur.execute("SELECT * FROM prodotti ORDER BY nome ASC;")
        tutti = cur.fetchall()

        # Estrae le ubicazioni uniche dal database per la tendina autocompilante
        cur.execute("SELECT DISTINCT posizione FROM prodotti WHERE posizione IS NOT NULL AND posizione != '' ORDER BY posizione ASC;")
        ubicazioni_disponibili = [r['posizione'] for r in cur.fetchall()]
        
        if is_admin or puo_assegnare:
            cur.execute("SELECT COUNT(*) as count FROM promemoria WHERE completato = FALSE;")
        else:
            cur.execute("SELECT COUNT(*) as count FROM promemoria WHERE completato = FALSE AND (assegnato_a = %s OR assegnato_a IS NULL OR assegnato_a = '');", (username,))
        res_p = cur.fetchone()
        if res_p:
            promemoria_urgenti = res_p['count']
            
        cur.execute("SELECT COUNT(*) as count FROM richieste_manutenzione WHERE stato = 'Aperta';")
        interventi_aperti_count = cur.fetchone()['count']
        
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
                           ubicazioni_disponibili=ubicazioni_disponibili,
                           promemoria_urgenti=promemoria_urgenti,
                           interventi_aperti_count=interventi_aperti_count)

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
            registra_log(f"Aggiunto nuovo nastro: {numero}")
            flash("Nastro aggiunto con successo!", "success")
        except Exception as e:
            flash(f"Errore inserimento nastro: {e}", "error")
        cur.close()
        conn.close()
        return redirect(url_for("nastri"))

    sezione_filtro = request.args.get("sezione", "Tutte")
    cur.execute("SELECT DISTINCT sezione_impianto FROM nastri WHERE sezione_impianto IS NOT NULL ORDER BY sezione_impianto ASC;")
    sezioni_disponibili = [r['sezione_impianto'] for r in cur.fetchall()]
    if sezione_filtro != "Tutte":
        cur.execute("SELECT * FROM nastri WHERE sezione_impianto = %s ORDER BY numero ASC;", (sezione_filtro,))
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
            registra_log(f"Aggiornato stato tappeto ID {nastro_id}")
        cur.close()
        conn.close()
    except Exception as e:
        flash(f"Errore stato tappeto: {e}", "error")
    return redirect(url_for("nastri"))

@app.route("/modifica_nastro/<int:nastro_id>", methods=["POST"])
def modifica_nastro(nastro_id):
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("""
            UPDATE nastri 
            SET codice_sap = %s, numero = %s, sezione_impianto = %s, misura = %s, tipo = %s, utilizzo = %s, misura_nastro_finito = %s, tipo_di_riduttore = %s, tipo_di_motore = %s, note = %s
            WHERE id = %s;
        """, (request.form.get("codice_sap"), request.form.get("numero"), request.form.get("sezione_impianto"), request.form.get("misura"), request.form.get("tipo"), request.form.get("utilizzo"), request.form.get("misura_nastro_finito"), request.form.get("tipo_di_riduttore"), request.form.get("tipo_di_motore"), request.form.get("note"), nastro_id))
        conn.commit()
        cur.close()
        conn.close()
        flash("Nastro aggiornato!", "success")
    except Exception as e:
        flash(f"Errore: {e}", "error")
    return redirect(url_for("nastri"))

@app.route("/elimina_nastro/<int:nastro_id>", methods=["POST"])
def elimina_nastro(nastro_id):
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("DELETE FROM nastri WHERE id = %s;", (nastro_id,))
        conn.commit()
        cur.close()
        conn.close()
        flash("Nastro eliminato.", "success")
    except Exception as e:
        flash(f"Errore: {e}", "error")
    return redirect(url_for("nastri"))

@app.route("/esporta_nastri_csv")
def esporta_nastri_csv():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM nastri ORDER BY sezione_impianto ASC, numero ASC;")
    nastri_list = cur.fetchall()
    cur.close()
    conn.close()
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['Codice SAP', 'Numero', 'Sezione', 'Misura', 'Tipo', 'Utilizzo', 'Misura Finito', 'Riduttore', 'Motore', 'Tappeto', 'Note'])
    for n in nastri_list:
        writer.writerow([n.get('codice_sap'), n.get('numero'), n.get('sezione_impianto'), n.get('misura'), n.get('tipo'), n.get('utilizzo'), n.get('misura_nastro_finito'), n.get('tipo_di_riduttore'), n.get('tipo_di_motore'), 'Presente' if n.get('tappeto_presente') else 'Assente', n.get('note')])
    return Response(output.getvalue(), mimetype="text/csv", headers={"Content-disposition": "attachment; filename=Nastri_OMG.csv"})

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

@app.route("/agenda", methods=["GET", "POST"])
@app.route("/agenda.html", methods=["GET", "POST"])
def agenda():
    if not session.get('username'):
        return redirect(url_for('login'))
    conn = get_db_connection()
    cur = conn.cursor()
    if request.method == "POST":
        titolo = request.form.get("titolo")
        if titolo:
            cur.execute("INSERT INTO agenda (titolo, descrizione, data_scadenza, nome_azienda, utenti_visibili, creato_da) VALUES (%s, %s, %s, %s, %s, %s);",
                        (titolo, request.form.get("descrizione"), request.form.get("data_scadenza"), request.form.get("fornitore_input"), ", ".join(request.form.getlist("utenti_visibili[]")) or "Tutti", session.get('username')))
            conn.commit()
            flash("Attività aggiunta in agenda!", "success")
        cur.close()
        conn.close()
        return redirect(url_for("agenda"))
    cur.execute("SELECT * FROM agenda ORDER BY data_scadenza ASC NULLS LAST, id DESC;")
    attivita = cur.fetchall()
    cur.execute("SELECT username FROM utenti ORDER BY username ASC;")
    utenti = cur.fetchall()
    cur.execute("SELECT nome_azienda FROM fornitori ORDER BY nome_azienda ASC;")
    fornitori = cur.fetchall()
    cur.close()
    conn.close()
    return render_template("agenda.html", attivita=attivita, utenti=utenti, fornitori=fornitori)

@app.route("/completa_agenda/<int:agenda_id>", methods=["POST"])
def completa_agenda(agenda_id):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM agenda WHERE id = %s;", (agenda_id,))
    conn.commit()
    cur.close()
    conn.close()
    flash("Attività completata e rimossa.", "success")
    return redirect(url_for("agenda"))

@app.route("/elimina_agenda/<int:agenda_id>", methods=["POST"])
def elimina_agenda(agenda_id):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM agenda WHERE id = %s;", (agenda_id,))
    conn.commit()
    cur.close()
    conn.close()
    flash("Attività eliminata.", "success")
    return redirect(url_for("agenda"))

@app.route("/api/ultima_bottiglia/<forno>/<linea>")
def ultima_bottiglia(forno, linea):
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT bottiglia_nuova, nome_bottiglia, num_bottiglie_tempera_nuova, num_bottiglie_tempera FROM cambi_serie WHERE forno = %s AND linea = %s ORDER BY id DESC LIMIT 1;", (forno, linea))
        ultimo = cur.fetchone()
        cur.close()
        conn.close()
        if ultimo:
            return jsonify({"bottiglia": ultimo.get('bottiglia_nuova') or ultimo.get('nome_bottiglia') or "", "tempera": ultimo.get('num_bottiglie_tempera_nuova') or ultimo.get('num_bottiglie_tempera') or 0})
        return jsonify({"bottiglia": "", "tempera": 0})
    except Exception:
        return jsonify({"bottiglia": "", "tempera": 0})

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
    return render_template("cambi_serie.html", record_serie=record_serie, forno_filtro=forno_filtro, settimana_filtro=settimana_filtro)

@app.route("/aggiungi_cambio_serie", methods=["POST"])
def aggiungi_cambio_serie():
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO cambi_serie (forno, linea, data_cambio, bottiglia_precedente, bottiglia_nuova, nome_bottiglia, tempo_cambio, num_bottiglie_tempera_vecchia, num_bottiglie_tempera_nuova, num_bottiglie_tempera, misura_piastrina)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s);
        """, (request.form.get("forno"), request.form.get("linea"), request.form.get("data_cambio"), request.form.get("bottiglia_precedente"), request.form.get("bottiglia_nuova"), request.form.get("bottiglia_nuova"), request.form.get("tempo_cambio"), int(request.form.get("num_bottiglie_tempera_vecchia", 0) or 0), int(request.form.get("num_bottiglie_tempera_nuova", 0) or 0), int(request.form.get("num_bottiglie_tempera_nuova", 0) or 0), request.form.get("misura_piastrina", "").strip()))
        conn.commit()
        cur.close()
        conn.close()
        flash("Cambio serie registrato!", "success")
    except Exception as e:
        flash(f"Errore: {e}", "error")
    return redirect(url_for("cambi_serie"))

@app.route("/modifica_cambio_serie/<int:id_cambio>", methods=["POST"])
def modifica_cambio_serie(id_cambio):
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("""
            UPDATE cambi_serie 
            SET forno = %s, linea = %s, data_cambio = %s, bottiglia_precedente = %s, bottiglia_nuova = %s, nome_bottiglia = %s, tempo_cambio = %s, num_bottiglie_tempera_vecchia = %s, num_bottiglie_tempera_nuova = %s, num_bottiglie_tempera = %s, misura_piastrina = %s
            WHERE id = %s;
        """, (request.form.get("forno"), request.form.get("linea"), request.form.get("data_cambio"), request.form.get("bottiglia_precedente"), request.form.get("bottiglia_nuova"), request.form.get("bottiglia_nuova"), request.form.get("tempo_cambio"), int(request.form.get("num_bottiglie_tempera_vecchia", 0) or 0), int(request.form.get("num_bottiglie_tempera_nuova", 0) or 0), int(request.form.get("num_bottiglie_tempera_nuova", 0) or 0), request.form.get("misura_piastrina", "").strip(), id_cambio))
        conn.commit()
        cur.close()
        conn.close()
        flash("Aggiornato con successo!", "success")
    except Exception as e:
        flash(f"Errore: {e}", "error")
    return redirect(url_for("cambi_serie"))

@app.route("/elimina_cambio_serie/<int:id_cambio>", methods=["POST"])
def elimina_cambio_serie(id_cambio):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM cambi_serie WHERE id = %s;", (id_cambio,))
    conn.commit()
    cur.close()
    conn.close()
    flash("Eliminato.", "success")
    return redirect(url_for("cambi_serie"))

@app.route("/esporta_cambi_serie_csv")
def esporta_cambi_serie_csv():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM cambi_serie ORDER BY data_cambio DESC;")
    righe = cur.fetchall()
    cur.close()
    conn.close()
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['Data', 'Forno', 'Linea', 'Smontante', 'Montante', 'Tempo', 'Tempera Vecchia', 'Tempera Nuova', 'Piastrina'])
    for r in righe:
        writer.writerow([r.get('data_cambio'), r.get('forno'), r.get('linea'), r.get('bottiglia_precedente'), r.get('bottiglia_nuova'), r.get('tempo_cambio'), r.get('num_bottiglie_tempera_vecchia'), r.get('num_bottiglie_tempera_nuova'), r.get('misura_piastrina')])
    return Response(output.getvalue(), mimetype="text/csv", headers={"Content-disposition": "attachment; filename=Cambi_Serie.csv"})

@app.route("/report_ore")
@app.route("/report_ore.html")
def report_ore():
    if not (session.get('is_admin') or session.get('puo_vedere_report_ore', 1)):
        flash("Accesso negato.", "error")
        return redirect(url_for('index'))
    return render_template("report_ore.html", utenti=[], interventi=[], chart_tecnici_labels=[], chart_tecnici_values=[], chart_tipi_labels=[], chart_tipi_values=[])

@app.route("/richieste_manutenzione", methods=["GET", "POST"])
@app.route("/richieste_manutenzione.html", methods=["GET", "POST"])
def richieste_manutenzione():
    if not (session.get('is_admin') or session.get('puo_vedere_manutenzione', 1)):
        flash("Accesso non autorizzato.", "error")
        return redirect(url_for('index'))
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM richieste_manutenzione ORDER BY id DESC;")
    richieste = cur.fetchall()
    cur.close()
    conn.close()
    return render_template("richieste_manutenzione.html", richieste=richieste, puo_aprire=True, puo_assegnare=True, puo_gestire=True, puo_elimina_int=True)

@app.route("/cambia_stato_intervento/<int:intervento_id>", methods=["POST"])
def cambia_stato_intervento(intervento_id):
    return redirect(url_for("richieste_manutenzione"))

@app.route("/scarica_allegato_intervento/<int:intervento_id>")
def scarica_allegato_intervento(intervento_id):
    return redirect(url_for("richieste_manutenzione"))

@app.route("/stampa_intervento/<int:intervento_id>")
def stampa_intervento(intervento_id):
    return redirect(url_for("richieste_manutenzione"))

@app.route("/elimina_intervento/<int:intervento_id>", methods=["POST"])
def elimina_intervento(intervento_id):
    return redirect(url_for("richieste_manutenzione"))

@app.route("/promemoria", methods=["GET", "POST"])
@app.route("/promemoria.html", methods=["GET", "POST"])
def promemoria():
    conn = get_db_connection()
    cur = conn.cursor()
    if request.method == "POST":
        cur.execute("INSERT INTO promemoria (titolo, descrizione, data_scadenza, assegnato_a) VALUES (%s, %s, %s, %s);",
                    (request.form.get("titolo"), request.form.get("descrizione"), request.form.get("data_scadenza"), request.form.get("assegnato_a")))
        conn.commit()
        flash("Promemoria aggiunto!", "success")
    cur.execute("SELECT * FROM promemoria ORDER BY completato ASC, data_scadenza ASC;")
    lista = cur.fetchall()
    cur.close()
    conn.close()
    return render_template("promemoria.html", promemoria=lista, puo_assegnare=True)

@app.route("/completa_promemoria/<int:promemoria_id>", methods=["POST"])
def completa_promemoria(promemoria_id):
    conn = get_db_connection()
    cur = conn.cursor()
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
    return redirect(url_for("promemoria"))

@app.route("/fornitori", methods=["GET", "POST"])
@app.route("/fornitori.html", methods=["GET", "POST"])
def fornitori():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM fornitori ORDER BY nome_azienda ASC;")
    lista = cur.fetchall()
    cur.close()
    conn.close()
    return render_template("fornitori.html", fornitori=lista)

@app.route("/modifica_fornitore/<int:fornitore_id>", methods=["POST"])
def modifica_fornitore(fornitore_id):
    return redirect(url_for("fornitori"))

@app.route("/fornitore/<int:fornitore_id>")
def dettaglio_fornitore(fornitore_id):
    return redirect(url_for("fornitori"))

@app.route("/modifica_contatto_tecnico/<int:contatto_id>/<int:fornitore_id>", methods=["POST"])
def modifica_contatto_tecnico(contatto_id, fornitore_id):
    return redirect(url_for("dettaglio_fornitore", fornitore_id=fornitore_id))

@app.route("/elimina_contatto_tecnico/<int:contatto_id>/<int:fornitore_id>", methods=["POST"])
def elimina_contatto_tecnico(contatto_id, fornitore_id):
    return redirect(url_for("dettaglio_fornitore", fornitore_id=fornitore_id))

@app.route("/elimina_fornitore/<int:fornitore_id>", methods=["POST"])
def elimina_fornitore(fornitore_id):
    return redirect(url_for("fornitori"))

@app.route("/importa_intelligente", methods=["POST"])
def importa_intelligente():
    return redirect(url_for("fornitori"))

@app.route("/esporta_fornitori_csv")
def esporta_fornitori_csv():
    return redirect(url_for("fornitori"))

@app.route("/documenti", defaults={"cartella_id": None})
@app.route("/documenti/<int:cartella_id>")
def documenti(cartella_id):
    return render_template("documenti.html", cartella_corrente=None, sottocartelle=[], lista_file=[], percorso_breadcrumb=[], puo_elimina_doc=True)

@app.route("/scarica_file/<int:file_id>")
def scarica_file(file_id):
    return redirect(url_for("documenti"))

@app.route("/elimina_cartella/<int:cartella_id>", methods=["POST"])
def elimina_cartella(cartella_id):
    return redirect(url_for("documenti"))

@app.route("/elimina_file/<int:file_id>", methods=["POST"])
def elimina_file(file_id):
    return redirect(url_for("documenti"))

@app.route("/esportazioni")
def esportazioni():
    return render_template("esportazioni.html")

@app.route("/esporta_inventario")
def esporta_inventario():
    return redirect(url_for("index"))

@app.route("/esporta_interventi")
def esporta_interventi():
    return redirect(url_for("index"))

@app.route("/upload", methods=["GET", "POST"])
def upload():
    return render_template("upload.html")

@app.route("/stampa_tutti_qr")
def stampa_tutti_qr():
    return redirect(url_for("index"))

@app.route("/stampa_multipla_qr", endpoint="stampa_multipla_qr")
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

@app.route("/qr_scaffale/<path:ubicazione>")
def qr_scaffale(ubicazione):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM prodotti WHERE UPPER(posizione) = UPPER(%s) ORDER BY nome ASC;", (ubicazione,))
    prodotti = cur.fetchall()
    cur.close()
    conn.close()
    return render_template("qr_scaffale.html", prodotti=prodotti, ubicazione=ubicazione)

@app.route("/magazzino_pesante")
def magazzino_pesante():
    return render_template("magazzino_pesante.html", prodotti=[])

@app.route("/esporta_pesante")
def esporta_pesante():
    return redirect(url_for("magazzino_pesante"))

@app.route("/manutenzioni")
def manutenzioni():
    return render_template("manutenzioni.html", prodotti=[])

@app.route("/storico_manutenzioni")
def storico_manutenzioni():
    return render_template("storico_manutenzioni.html", storico=[])

@app.route("/esporta_storico_manutenzioni_csv")
def esporta_storico_manutenzioni_csv():
    return redirect(url_for("storico_manutenzioni"))

@app.route("/elimina_storico_manutenzione/<int:storico_id>", methods=["POST"])
def elimina_storico_manutenzione(storico_id):
    return redirect(url_for("storico_manutenzioni"))

@app.route("/stampa_bolla/<qr_code>")
def stampa_bolla(qr_code):
    return redirect(url_for("index"))

@app.route("/carico", methods=["GET", "POST"])
def carico():
    return render_template("carico.html")

@app.route("/scarico", methods=["GET", "POST"])
def scarico():
    return render_template("scarico.html")

@app.route("/scanner_globale")
def scanner_globale():
    return render_template("scanner_globale.html")

@app.route("/gestisci/<qr_code>")
def gestisci_prodotto(qr_code):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM prodotti WHERE qr_code = %s;", (qr_code,))
    prodotto = cur.fetchone()
    cur.execute("SELECT DISTINCT posizione FROM prodotti WHERE posizione IS NOT NULL AND posizione != '' ORDER BY posizione ASC;")
    ubicazioni_disponibili = [r['posizione'] for r in cur.fetchall()]
    cur.execute("SELECT * FROM fornitori ORDER BY nome_azienda ASC;")
    lista_fornitori = cur.fetchall()
    cur.close()
    conn.close()
    return render_template("gestisci.html", prodotto=prodotto, ubicazioni_disponibili=ubicazioni_disponibili, fornitori=lista_fornitori)

@app.route("/aggiorna/<qr_code>", methods=["POST"])
def aggiorna_prodotto(qr_code):
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("""
            UPDATE prodotti 
            SET nome = %s, sap = %s, posizione = %s, peso = %s, quantita = %s, magazzino_pesante = %s, soglia_minima = %s
            WHERE qr_code = %s;
        """, (request.form.get("nome"), request.form.get("sap"), request.form.get("posizione"), request.form.get("peso"), int(request.form.get("quantita", 0) or 0), 1 if request.form.get("magazzino_pesante") else 0, int(request.form.get("soglia_minima", 3) or 3), qr_code))
        conn.commit()
        cur.close()
        conn.close()
        flash("Articolo aggiornato!", "success")
    except Exception as e:
        flash(f"Errore: {e}", "error")
    return redirect(url_for("gestisci_prodotto", qr_code=qr_code))

@app.route("/aggiungi", methods=["POST"])
def aggiungi_prodotto():
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        qr_code = request.form.get("qr_code", "").strip()
        if not qr_code:
            cur.execute("SELECT COUNT(*) + 1 as next_id FROM prodotti;")
            res_id = cur.fetchone()
            qr_code = f"OMG-{(res_id['next_id'] if res_id else 1):04d}"
        cur.execute("""
            INSERT INTO prodotti (qr_code, nome, sap, peso, quantita, posizione, magazzino_pesante, soglia_minima)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (qr_code) DO UPDATE SET 
                quantita = prodotti.quantita + EXCLUDED.quantita,
                nome = EXCLUDED.nome,
                sap = EXCLUDED.sap,
                posizione = EXCLUDED.posizione;
        """, (qr_code, request.form.get("nome"), request.form.get("sap"), request.form.get("peso"), int(request.form.get("quantita", 0) or 0), request.form.get("posizione"), 1 if request.form.get("magazzino_pesante") else 0, int(request.form.get("soglia_minima", 3) or 3)))
        conn.commit()
        cur.close()
        conn.close()
        flash("Prodotto salvato con successo!", "success")
    except Exception as e:
        flash(f"Errore: {e}", "error")
    return redirect(url_for("index"))

@app.route("/manda_manutenzione/<qr_code>", methods=["POST"])
def manda_manutenzione(qr_code):
    return redirect(url_for("gestisci_prodotto", qr_code=qr_code))

@app.route("/ripristina_magazzino/<qr_code>", methods=["POST"])
def ripristina_magazzino(qr_code):
    return redirect(url_for("gestisci_prodotto", qr_code=qr_code))

@app.route("/elimina/<qr_code>", methods=["POST"])
def elimina_prodotto(qr_code=None):
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
