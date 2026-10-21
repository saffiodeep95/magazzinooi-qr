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
            CREATE TABLE IF NOT EXISTS cambi_serie (
                id SERIAL PRIMARY KEY,
                forno VARCHAR(50) NOT NULL,
                linea VARCHAR(50),
                data_cambio VARCHAR(50),
                nome_bottiglia VARCHAR(255) NOT NULL,
                tempo_cambio VARCHAR(255),
                altezza_paratie VARCHAR(255),
                num_bottiglie_tempera INT DEFAULT 0,
                quantita_trattamento VARCHAR(255),
                creato_il TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        cur.execute("ALTER TABLE cambi_serie ADD COLUMN IF NOT EXISTS linea VARCHAR(50);")
        cur.execute("ALTER TABLE cambi_serie ADD COLUMN IF NOT EXISTS data_cambio VARCHAR(50);")

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
    prodotti_pesanti = []
    prodotti_sotto_soglia = []
    totale_pezzi_principale = 0
    totale_pezzi_pesante = 0
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
        
        if is_admin or puo_assegnare:
            cur.execute("SELECT COUNT(*) as count FROM promemoria WHERE completato = FALSE;")
        else:
            cur.execute("SELECT COUNT(*) as count FROM promemoria WHERE completato = FALSE AND (assegnato_a = %s OR assegnato_a IS NULL OR assegnato_a = '');", (username,))
        res_p = cur.fetchone()
        if res_p:
            promemoria_urgenti = res_p['count']
            
        cur.execute("SELECT COUNT(*) as count FROM richieste_manutenzione WHERE stato = 'Aperta';")
        res_i = cur.fetchone()
        if res_i:
            interventi_aperti_count = res_i['count']
        
        cur.close()
        conn.close()
        
        for p in tutti:
            val_pesante = p.get('magazzino_pesante')
            is_pesante = (val_pesante == 1 or val_pesante == '1' or val_pesante is True or val_pesante == 1.0)
            qta = p.get('quantita', 0) or 0
            
            if is_pesante:
                prodotti_pesanti.append(p)
                totale_pezzi_pesante += qta
            else:
                prodotti.append(p)
                totale_pezzi_principale += qta
                
            soglia = p.get('soglia_minima', 3) or 3
            if qta <= soglia:
                prodotti_sotto_soglia.append(p)
    except Exception as e:
        print(f"Errore index: {e}")
        
    return render_template("index.html", 
                           prodotti=prodotti, 
                           prodotti_pesanti=prodotti_pesanti,
                           prodotti_sotto_soglia=prodotti_sotto_soglia,
                           totale_pezzi_principale=totale_pezzi_principale,
                           totale_pezzi_pesante=totale_pezzi_pesante,
                           promemoria_urgenti=promemoria_urgenti,
                           interventi_aperti_count=interventi_aperti_count)

# --- ROTTA STAMPA QR MULTIPLI (Etichette Armadi) ---
def logica_stampa_qr_multipli():
    conn = get_db_connection()
    cur = conn.cursor()
    
    ids = request.form.getlist("prodotti_ids[]") or request.form.getlist("prodotti_ids") or request.form.getlist("ids[]") or request.args.getlist("ids[]")
    
    if ids:
        ids_int = [int(i) for i in ids if str(i).isdigit()]
        if ids_int:
            cur.execute("SELECT * FROM prodotti WHERE id IN %s ORDER BY nome ASC;", (tuple(ids_int),))
            prodotti = cur.fetchall()
        else:
            prodotti = []
    else:
        cur.execute("SELECT * FROM prodotti ORDER BY nome ASC;")
        prodotti = cur.fetchall()
        
    cur.close()
    conn.close()
    return render_template("stampa_multipla_qr.html", prodotti=prodotti)

@app.route("/stampa_qr_multipli", methods=["GET", "POST"])
def stampa_qr_multipli():
    return logica_stampa_qr_multipli()

@app.route("/stampa_multipla_qr", methods=["GET", "POST"])
def stampa_multipla_qr():
    return logica_stampa_qr_multipli()

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

# --- GESTIONE PRODOTTO SINGOLO (/gestisci/<qr_code>) ---
@app.route("/gestisci/<qr_code>")
def gestisci_prodotto(qr_code):
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT * FROM prodotti WHERE qr_code = %s;", (qr_code,))
        prodotto = cur.fetchone()
        cur.close()
        conn.close()
        if not prodotto:
            flash("Prodotto non trovato!", "error")
            return redirect(url_for("index"))
        return render_template("gestisci.html", prodotto=prodotto)
    except Exception as e:
        flash(f"Errore apertura prodotto: {e}", "error")
        return redirect(url_for("index"))

@app.route("/aggiorna/<qr_code>", methods=["POST"])
def aggiorna_prodotto(qr_code):
    if not (session.get('is_admin') or session.get('puo_modificare_prodotti', 1)):
        flash("Permesso negato.", "error")
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
        flash("Articolo aggiornato con successo!", "success")
    except Exception as e:
        flash(f"Errore: {e}", "error")
    return redirect(url_for("gestisci_prodotto", qr_code=qr_code))

@app.route("/aggiungi", methods=["POST"])
def aggiungi_prodotto():
    if not (session.get('is_admin') or session.get('puo_aggiungere_prodotti', 1)):
        flash("Permesso negato.", "error")
        return redirect(url_for("index"))
    qr_code = request.form.get("qr_code")
    nome = request.form.get("nome")
    sap = request.form.get("sap", "")
    peso = request.form.get("peso", "")
    quantita = int(request.form.get("quantita", 0))
    soglia_minima = int(request.form.get("soglia_minima", 3) or 3)
    posizione = request.form.get("posizione", "")
    flag_sezione = 1 if request.form.get("magazzino_pesante") else 0

    if qr_code and nome:
        try:
            conn = get_db_connection()
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO prodotti (qr_code, nome, sap, peso, quantita, posizione, magazzino_pesante, soglia_minima)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (qr_code)
                DO UPDATE SET quantita = prodotti.quantita + EXCLUDED.quantita, nome = EXCLUDED.nome;
            """, (qr_code, nome, sap, peso, quantita, posizione, flag_sezione, soglia_minima))
            conn.commit()
            cur.close()
            conn.close()
            flash("Prodotto salvato con successo!", "success")
        except Exception as e:
            flash(f"Errore: {e}", "error")
    return redirect(url_for("magazzino_pesante" if flag_sezione == 1 else "index"))

@app.route("/elimina", methods=["POST"])
def elimina_prodotto():
    if not (session.get('is_admin') or session.get('puo_eliminare', 0)):
        flash("Permesso negato.", "error")
        return redirect(url_for("index"))
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

# --- ALTRE ROTTE PRINCIPALI DEL GESTIONALE ---
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
        FROM richieste_manutenzione WHERE 1=1
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
    cur.close()
    conn.close()
    totale_ore_generale = round(totale_minuti_generale / 60.0, 1)
    chart_tecnici_labels = [k for k, v in ore_per_tecnico.items() if filtro_tecnico == "Tutti" or k == filtro_tecnico]
    chart_tecnici_values = [round(ore_per_tecnico[k], 1) for k in chart_tecnici_labels]
    chart_tipi_labels = list(ore_per_tipo.keys())
    chart_tipi_values = [round(v, 1) for v in ore_per_tipo.values()]
    return render_template("report_ore.html", utenti=utenti, interventi=interventi_filtrati, filtro_tecnico=filtro_tecnico, data_inizio=data_inizio, data_fine=data_fine, periodo_predefinito=periodo_predefinito, totale_ore_generale=totale_ore_generale, totale_interventi=len(interventi_filtrati), chart_tecnici_labels=chart_tecnici_labels, chart_tecnici_values=chart_tecnici_values, chart_tipi_labels=chart_tipi_labels, chart_tipi_values=chart_tipi_values)

@app.route("/cambi_serie")
def cambi_serie():
    forno_filtro = request.args.get("forno", "Tutti")
    settimana_filtro = request.args.get("settimana", "")
    conn = get_db_connection()
    cur = conn.cursor()
    query = "SELECT * FROM cambi_serie WHERE 1=1"
    params = []
    if forno_filtro and forno_filtro != "Tutti":
        query += " AND forno = %s"
        params.append(forno_filtro)
    if settimana_filtro and "-W" in settimana_filtro:
        try:
            anno, num_sett = settimana_filtro.split("-W")
            query += " AND EXTRACT(ISOYEAR FROM TO_DATE(data_cambio, 'YYYY-MM-DD')) = %s AND EXTRACT(WEEK FROM TO_DATE(data_cambio, 'YYYY-MM-DD')) = %s"
            params.extend([int(anno), int(num_sett)])
        except Exception:
            pass
    query += " ORDER BY data_cambio ASC, id DESC;"
    cur.execute(query, tuple(params))
    record_serie = cur.fetchall()
    cur.close()
    conn.close()
    return render_template("cambi_serie.html", forno_filtro=forno_filtro, settimana_filtro=settimana_filtro, record_serie=record_serie)

@app.route("/aggiungi_cambio_serie", methods=["POST"])
def aggiungi_cambio_serie():
    forno = request.form.get("forno", "Forno 1")
    linea = request.form.get("linea", "")
    data_cambio = request.form.get("data_cambio", "")
    nome_bottiglia = request.form.get("nome_bottiglia")
    tempo_cambio = request.form.get("tempo_cambio", "")
    altezza_paratie = request.form.get("altezza_paratie", "")
    num_bottiglie_tempera = int(request.form.get("num_bottiglie_tempera", 0) or 0)
    quantita_trattamento = request.form.get("quantita_trattamento", "")
    if nome_bottiglia:
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
            flash("Cambio serie registrato con successo!", "success")
        except Exception as e:
            flash(f"Errore salvataggio cambio serie: {e}", "error")
    return redirect(url_for("cambi_serie", forno=forno))

@app.route("/elimina_cambio_serie/<int:id_cambio>", methods=["POST"])
def elimina_cambio_serie(id_cambio):
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("DELETE FROM cambi_serie WHERE id = %s;", (id_cambio,))
        conn.commit()
        cur.close()
        conn.close()
        flash("Record eliminato con successo.", "success")
    except Exception as e:
        flash(f"Errore eliminazione: {e}", "error")
    return redirect(url_for("cambi_serie"))

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
            flash("Non hai i permessi.", "error")
            return redirect(url_for("richieste_manutenzione"))
        titolo = request.form.get("titolo")
        impianto_macchina = request.form.get("impianto_macchina", "")
        fornitore_id = request.form.get("fornitore_id")
        dati_fornitore_str = ""
        if fornitore_id:
            cur.execute("SELECT nome_azienda, telefono, email FROM fornitori WHERE id = %s;", (fornitore_id,))
            f_data = cur.fetchone()
            if f_data:
                dati_fornitore_str = f" [FORNITORE: {f_data['nome_azienda']} - Tel: {f_data['telefono']}]"
        descrizione = request.form.get("descrizione", "") + dati_fornitore_str
        priorita = request.form.get("priorita", "Media")
        tipo_guasto = request.form.get("tipo_guasto", "Meccanico")
        assegnato_a = ", ".join(request.form.getlist("assegnato_a[]")) if puo_assegnare else username_corrente
        file_allegato = request.files.get("allegato_foto")
        allegato_nome = file_allegato.filename if file_allegato and file_allegato.filename else None
        allegato_dati = file_allegato.read() if allegato_nome else None
        if titolo:
            cur.execute("""
                INSERT INTO richieste_manutenzione (titolo, impianto_macchina, descrizione, priorita, tipo_guasto, assegnato_a, creato_da, stato, allegato_nome, allegato_dati)
                VALUES (%s, %s, %s, %s, %s, %s, %s, 'Aperta', %s, %s);
            """, (titolo, impianto_macchina, descrizione, priorita, tipo_guasto, assegnato_a, username_corrente, allegato_nome, allegato_dati))
            conn.commit()
            flash("Richiesta creata!", "success")
        return redirect(url_for("richieste_manutenzione"))
    cur.execute("SELECT username FROM utenti ORDER BY username ASC;")
    lista_utenti = cur.fetchall()
    cur.execute("SELECT qr_code, nome, quantita FROM prodotti ORDER BY nome ASC;")
    lista_prodotti = cur.fetchall()
    cur.execute("SELECT id, nome_azienda FROM fornitori ORDER BY nome_azienda ASC;")
    lista_fornitori = cur.fetchall()
    cur.execute("SELECT * FROM richieste_manutenzione ORDER BY CASE WHEN stato = 'Completata' THEN 2 ELSE 1 END, creato_il DESC;")
    richieste = cur.fetchall()
    ricambi_per_intervento = {}
    for r in richieste:
        cur.execute("SELECT qr_code, nome_ricambio, quantita FROM intervento_ricambi WHERE intervento_id = %s;", (r['id'],))
        ricambi_per_intervento[r['id']] = cur.fetchall()
    cur.close()
    conn.close()
    return render_template("richieste_manutenzione.html", richieste=richieste, lista_utenti=lista_utenti, lista_prodotti=lista_prodotti, lista_fornitori=lista_fornitori, ricambi_per_intervento=ricambi_per_intervento, puo_aprire=puo_aprire, puo_assegnare=puo_assegnare, puo_gestire=puo_gestire, puo_elimina_int=puo_elimina_int)

@app.route("/cambia_stato_intervento/<int:intervento_id>", methods=["POST"])
def cambia_stato_intervento(intervento_id):
    username_corrente = session.get('username')
    nuovo_stato = request.form.get("stato")
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM richieste_manutenzione WHERE id = %s;", (intervento_id,))
    req = cur.fetchone()
    if req:
        now = datetime.now()
        if nuovo_stato == 'In Lavoro':
            cur.execute("UPDATE richieste_manutenzione SET stato = %s, inizio_lavoro = COALESCE(inizio_lavoro, %s) WHERE id = %s;", (nuovo_stato, now, intervento_id))
        elif nuovo_stato == 'Completata':
            cur.execute("UPDATE richieste_manutenzione SET stato = %s, fine_lavoro = %s WHERE id = %s;", (nuovo_stato, now, intervento_id))
        else:
            cur.execute("UPDATE richieste_manutenzione SET stato = %s WHERE id = %s;", (nuovo_stato, intervento_id))
        conn.commit()
    cur.close()
    conn.close()
    return redirect(url_for("richieste_manutenzione"))

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
    cur.execute("SELECT username FROM utenti ORDER BY username ASC;" if (is_admin or puo_assegnare) else "SELECT 1 WHERE 1=0;")
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
            cur.execute("INSERT INTO fornitori (nome_azienda, settore_note, indirizzo, p_iva, telefono, email) VALUES (%s, %s, %s, %s, %s, %s) ON CONFLICT (nome_azienda) DO NOTHING;", (nome_azienda, settore_note, indirizzo, p_iva, telefono, email))
            conn.commit()
            flash("Fornitore salvato!", "success")
        return redirect(url_for("fornitori"))
    cur.execute("SELECT * FROM fornitori ORDER BY nome_azienda ASC;")
    lista_fornitori = cur.fetchall()
    cur.close()
    conn.close()
    return render_template("fornitori.html", fornitori=lista_fornitori)

@app.route("/documenti", defaults={"cartella_id": None}, methods=["GET", "POST"])
@app.route("/documenti/<int:cartella_id>", methods=["GET", "POST"])
def documenti(cartella_id):
    if not (session.get('is_admin') or session.get('puo_gestire_documenti', 1)):
        flash("Accesso negato.", "error")
        return redirect(url_for('index'))
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM cartelle WHERE parent_id = %s ORDER BY nome ASC;" if cartella_id else "SELECT * FROM cartelle WHERE parent_id IS NULL ORDER BY nome ASC;", (cartella_id,) if cartella_id else ())
    sottocartelle = cur.fetchall()
    cur.execute("SELECT id, nome_file, tipo_file, caricato_il FROM documenti WHERE cartella_id = %s ORDER BY nome_file ASC;" if cartella_id else "SELECT id, nome_file, tipo_file, caricato_il FROM documenti WHERE cartella_id IS NULL ORDER BY nome_file ASC;", (cartella_id,) if cartella_id else ())
    lista_file = cur.fetchall()
    cur.close()
    conn.close()
    return render_template("documenti.html", sottocartelle=sottocartelle, lista_file=lista_file, cartella_corrente=None)

@app.route("/magazzino_pesante")
def magazzino_pesante():
    if not (session.get('is_admin') or session.get('puo_vedere_pesante', 1)):
        flash("Accesso negato.", "error")
        return redirect(url_for('index'))
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM prodotti WHERE magazzino_pesante = 1 ORDER BY nome ASC;")
    prodotti = cur.fetchall()
    cur.close()
    conn.close()
    return render_template("magazzino_pesante.html", prodotti=prodotti)

@app.route("/manutenzioni")
def manutenzioni():
    if not (session.get('is_admin') or session.get('puo_vedere_manutenzioni_esterne', 1)):
        flash("Accesso negato.", "error")
        return redirect(url_for('index'))
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM prodotti WHERE in_manutenzione = TRUE ORDER BY nome ASC;")
    prodotti = cur.fetchall()
    cur.close()
    conn.close()
    return render_template("manutenzioni.html", prodotti=prodotti)

@app.route("/carico", methods=["GET", "POST"])
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
def scarico():
    if request.method == "POST":
        qr_code = request.form.get("qr_code")
        quantita = int(request.form.get("quantita", 1))
        if qr_code:
            conn = get_db_connection()
            cur = conn.cursor()
            cur.execute("UPDATE prodotti SET quantita = GREATEST(0, quantita - %s) WHERE qr_code = %s;", (quantita, qr_code))
            conn.commit()
            cur.close()
            conn.close()
            flash("Scarico effettuato!", "success")
            return redirect(url_for("gestisci_prodotto", qr_code=qr_code))
    return render_template("scarico.html")

@app.route("/scanner_globale", methods=["GET", "POST"])
def scanner_globale():
    if request.method == "POST":
        qr_code = request.form.get("qr_code", "").strip()
        if qr_code:
            return redirect(url_for("gestisci_prodotto", qr_code=qr_code))
    return render_template("scanner_globale.html")

if __name__ == "__main__":
    app.run(debug=True)
