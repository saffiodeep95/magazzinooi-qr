# ========================================================================
# Magazzino OMG Application
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
from flask import Flask, render_template, request, redirect, url_for, flash, session, send_file, Response
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "chiave-segreta-magazzino")

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
                puo_vedere_manutenzione INT DEFAULT 1,
                puo_eliminare INT DEFAULT 0,
                puo_eliminare_storico INT DEFAULT 0,
                puo_gestire_documenti INT DEFAULT 1,
                puo_assegnare_promemoria INT DEFAULT 0,
                puo_aprire_manutenzioni INT DEFAULT 1,
                puo_assegnare_manutenzioni INT DEFAULT 1
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
        
        # Migrazione automatica colonne esistenti
        colonne_migrazione = [
            ("fornitori", "settore_note", "VARCHAR(255)"),
            ("contatti_tecnici", "email", "VARCHAR(255)"),
            ("promemoria", "ricorrenza", "VARCHAR(50) DEFAULT 'Nessuna'"),
            ("promemoria", "assegnato_a", "VARCHAR(255)"),
            ("utenti", "puo_assegnare_promemoria", "INT DEFAULT 0"),
            ("utenti", "puo_aprire_manutenzioni", "INT DEFAULT 1"),
            ("utenti", "puo_assegnare_manutenzioni", "INT DEFAULT 1"),
            ("prodotti", "soglia_minima", "INT DEFAULT 3"),
            ("richieste_manutenzione", "tipo_guasto", "VARCHAR(50) DEFAULT 'Meccanico'"),
            ("richieste_manutenzione", "tempo_lavorato_minuti", "INT DEFAULT 0"),
            ("richieste_manutenzione", "allegato_nome", "VARCHAR(255)"),
            ("richieste_manutenzione", "allegato_dati", "BYTEA")
        ]
        
        for tabella, colonna, tipo in colonne_migrazione:
            cur.execute(f"ALTER TABLE {tabella} ADD COLUMN IF NOT EXISTS {colonna} {tipo};")
        
        cur.execute("SELECT * FROM utenti WHERE username = 'admin';")
        if not cur.fetchone():
            hashed_pw = generate_password_hash("admin")
            cur.execute("INSERT INTO utenti (username, password, is_admin, puo_vedere_manutenzione, puo_eliminare, puo_eliminare_storico, puo_gestire_documenti, puo_assegnare_promemoria, puo_aprire_manutenzioni, puo_assegnare_manutenzioni) VALUES (%s, %s, 1, 1, 1, 1, 1, 1, 1, 1);", ('admin', hashed_pw))

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
                session['puo_vedere_manutenzione'] = user.get('puo_vedere_manutenzione', 1)
                session['puo_eliminare'] = user.get('puo_eliminare', 0)
                session['puo_eliminare_storico'] = user.get('puo_eliminare_storico', 0)
                session['puo_gestire_documenti'] = user.get('puo_gestire_documenti', 1)
                session['puo_assegnare_promemoria'] = user.get('puo_assegnare_promemoria', 0)
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
                cur.execute("INSERT INTO utenti (username, password, is_admin, puo_vedere_manutenzione, puo_eliminare, puo_eliminare_storico, puo_gestire_documenti, puo_assegnare_promemoria, puo_aprire_manutenzioni, puo_assegnare_manutenzioni) VALUES (%s, %s, 0, 1, 0, 0, 1, 0, 1, 1);", (username, hashed_pw))
                conn.commit()
                cur.close()
                conn.close()
                registra_log(f"Registrato nuovo utente: {username}")
                flash("Registrazione completata! Ora puoi effettuare il login.", "success")
                return redirect(url_for('login'))
            except Exception as e:
                flash("Username già esistente o errore di registrazione.", "error")
    return render_template("registra.html")

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
        writer.writerow([r['id'], r['titolo'], r['impianto_macchina'], r['priorita'], r['tipo_guasto'], r['stato'], r['assegnato_a'], r['creato_da'], r['inizio_lavoro'], r['fine_lavoro'], r['tempo_lavorato_minuti'], r['note_lavoro'], r['creato_il']])
    
    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-disposition": "attachment; filename=Report_Interventi_Officina.csv"}
    )

# --- RICHIESTE INTERVENTO MANUTENZIONE OFFICINA ---
@app.route("/richieste_manutenzione", methods=["GET", "POST"])
def richieste_manutenzione():
    username_corrente = session.get('username')
    is_admin = session.get('is_admin')
    puo_aprire_global = session.get('is_admin') or session.get('puo_aprire_manutenzioni', 1)
    puo_assegnare_global = session.get('is_admin') or session.get('puo_assegnare_manutenzioni', 1)
    
    conn = get_db_connection()
    cur = conn.cursor()
    
    if request.method == "POST":
        if not puo_aprire_global:
            flash("Non hai i permessi per aprire nuove richieste di intervento.", "error")
            return redirect(url_for("richieste_manutenzione"))

        titolo = request.form.get("titolo")
        impianto_macchina = request.form.get("impianto_macchina", "")
        descrizione = request.form.get("descrizione", "")
        priorita = request.form.get("priorita", "Media")
        tipo_guasto = request.form.get("tipo_guasto", "Meccanico")
        
        # Se l'utente può assegnare sceglie dal form, altrimenti si assegna a se stesso o resta vuoto
        if puo_assegnare_global:
            assegnato_a = request.form.get("assegnato_a", "")
        else:
            assegnato_a = username_corrente
        
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
            registra_log(f"Creata richiesta intervento: {titolo} su {impianto_macchina}")
            flash("Richiesta di intervento creata con successo!", "success")
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
                           puo_aprire=puo_aprire_global,
                           puo_assegnare_manut=puo_assegnare_global)

@app.route("/cambia_stato_intervento/<int:intervento_id>", methods=["POST"])
def cambia_stato_intervento(intervento_id):
    username_corrente = session.get('username')
    nuovo_stato = request.form.get("stato")
    note_lavoro = request.form.get("note_lavoro", "")
    nuovo_assegnatario = request.form.get("nuovo_assegnatario", "").strip()
    
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
            flash("Intervento completato e chiuso con successo!", "success")
            
        elif nuovo_stato == 'Riassegna':
            if session.get('is_admin') or session.get('puo_assegnare_manutenzioni', 1):
                if nuovo_assegnatario:
                    cur.execute("UPDATE richieste_manutenzione SET assegnato_a = %s WHERE id = %s;", (nuovo_assegnatario, intervento_id))
                    flash(f"Intervento riassegnato a {nuovo_assegnatario}.", "success")

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

@app.route("/elimina_intervento/<int:intervento_id>", methods=["POST"])
def elimina_intervento(intervento_id):
    if not session.get('is_admin'):
        flash("Permesso negato.", "error")
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

# --- GESTIONE UTENTI E LOG ---
@app.route("/admin_utenti")
def admin_utenti():
    if not session.get('is_admin'):
        flash("Accesso negato.", "error")
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

@app.route("/toggle_permesso/<int:user_id>/<tipo>", methods=["POST"])
def toggle_permesso(user_id, tipo):
    if not session.get('is_admin'):
        return redirect(url_for('index'))
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        if tipo == 'manutenzione':
            cur.execute("UPDATE utenti SET puo_vedere_manutenzione = 1 - puo_vedere_manutenzione WHERE id = %s;", (user_id,))
        elif tipo == 'eliminazione':
            cur.execute("UPDATE utenti SET puo_eliminare = 1 - puo_eliminare WHERE id = %s;", (user_id,))
        elif tipo == 'eliminazione_storico':
            cur.execute("UPDATE utenti SET puo_eliminare_storico = 1 - puo_eliminare_storico WHERE id = %s;", (user_id,))
        elif tipo == 'documenti':
            cur.execute("UPDATE utenti SET puo_gestire_documenti = 1 - puo_gestire_documenti WHERE id = %s;", (user_id,))
        elif tipo == 'assegnare_promemoria':
            cur.execute("UPDATE utenti SET puo_assegnare_promemoria = 1 - puo_assegnare_promemoria WHERE id = %s;", (user_id,))
        elif tipo == 'aprire_manutenzioni':
            cur.execute("UPDATE utenti SET puo_aprire_manutenzioni = 1 - puo_aprire_manutenzioni WHERE id = %s;", (user_id,))
        elif tipo == 'assegnare_manutenzioni':
            cur.execute("UPDATE utenti SET puo_assegnare_manutenzioni = 1 - puo_assegnare_manutenzioni WHERE id = %s;", (user_id,))
        conn.commit()
        cur.close()
        conn.close()
        registra_log(f"Modificati permessi utente ID {user_id} ({tipo})")
    except Exception as e:
        flash(f"Errore aggiornamento permessi: {e}", "error")
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

@app.route("/log_attivita")
def visualizza_log():
    return redirect(url_for('admin_utenti'))

# --- GESTIONE PROMEMORIA ---
@app.route("/promemoria", methods=["GET", "POST"])
def promemoria():
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
def fornitori():
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

@app.route("/importa_intelligente", methods=["POST"])
def importa_intelligente():
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

# --- GESTIONE DOCUMENTI ---
@app.route("/documenti", defaults={"cartella_id": None}, methods=["GET", "POST"])
@app.route("/documenti/<int:cartella_id>", methods=["GET", "POST"])
def documenti(cartella_id):
    if not (session.get('is_admin') or session.get('puo_gestire_documenti')):
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
                           percorso_breadcrumb=percorso_breadcrumb)

@app.route("/scarica_file/<int:file_id>")
def scarica_file(file_id):
    if not (session.get('is_admin') or session.get('puo_gestire_documenti')):
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
    if not session.get('is_admin'):
        flash("Solo l'amministratore può eliminare le cartelle.", "error")
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
    if not session.get('is_admin'):
        flash("Solo l'amministratore può eliminare i documenti.", "error")
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

# --- ALTRE ROTTE MAGAZZINO ---
@app.route("/upload", methods=["GET", "POST"])
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
def stampa_tutti_qr():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM prodotti ORDER BY nome ASC;")
    prodotti = cur.fetchall()
    cur.close()
    conn.close()
    return render_template("stampa_tutti_qr.html", prodotti=prodotti)

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

@app.route("/magazzino_pesante")
def magazzino_pesante():
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
    except Exception:
        pass
    return render_template("magazzino_pesante.html", prodotti=prodotti)

@app.route("/manutenzioni")
def manutenzioni():
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
def storico_manutenzioni():
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

@app.route("/elimina_storico_manutenzione/<int:storico_id>", methods=["POST"])
def elimina_storico_manutenzione(storico_id):
    if not (session.get('is_admin') or session.get('puo_eliminare_storico')):
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
            registra_log(f"Carico di +{quantita} pz su QR: {qr_code}")
            flash(f"Carico di {quantita} pz effettuato con successo!", "success")
            return redirect(url_for("gestisci_prodotto", qr_code=qr_code))
    return render_template("carico.html")

@app.route("/scarico", methods=["GET", "POST"])
def scarico():
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
def aggiorna_prodotto(qr_code):
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
def aggiungi_prodotto():
    qr_code = request.form.get("qr_code")
    nome = request.form.get("nome")
    sap = request.form.get("sap", "")
    peso = request.form.get("peso", "")
    quantita = int(request.form.get("quantita", 0))
    soglia_minima = int(request.form.get("soglia_minima", 3) or 3)
    posizione = request.form.get("posizione", "")
    flag_sezione = 1 if request.form.get("magazzino_pesante") else 0

    if not qr_code or not nome:
        flash("QR Code e Nome sono obbligatori!", "error")
        return redirect(url_for("index"))

    try:
        conn = get_db_connection()
        cur = conn.cursor()
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
        flash("Prodotto salvato con successo!", "success")
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
def elimina_prodotto():
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


Il lun 19 ott 2026, 22:32 marco pavan <marco.pavan1995@gmail.com> ha scritto:
# ========================================================================
# Magazzino OMG Application
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
from flask import Flask, render_template, request, redirect, url_for, flash, session, send_file, Response
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "chiave-segreta-magazzino")

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
                puo_vedere_manutenzione INT DEFAULT 1,
                puo_eliminare INT DEFAULT 0,
                puo_eliminare_storico INT DEFAULT 0,
                puo_gestire_documenti INT DEFAULT 1,
                puo_assegnare_promemoria INT DEFAULT 0,
                puo_aprire_manutenzioni INT DEFAULT 1,
                puo_assegnare_manutenzioni INT DEFAULT 1
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
        
        # Migrazione automatica colonne esistenti
        colonne_migrazione = [
            ("fornitori", "settore_note", "VARCHAR(255)"),
            ("contatti_tecnici", "email", "VARCHAR(255)"),
            ("promemoria", "ricorrenza", "VARCHAR(50) DEFAULT 'Nessuna'"),
            ("promemoria", "assegnato_a", "VARCHAR(255)"),
            ("utenti", "puo_assegnare_promemoria", "INT DEFAULT 0"),
            ("utenti", "puo_aprire_manutenzioni", "INT DEFAULT 1"),
            ("utenti", "puo_assegnare_manutenzioni", "INT DEFAULT 1"),
            ("prodotti", "soglia_minima", "INT DEFAULT 3"),
            ("richieste_manutenzione", "tipo_guasto", "VARCHAR(50) DEFAULT 'Meccanico'"),
            ("richieste_manutenzione", "tempo_lavorato_minuti", "INT DEFAULT 0"),
            ("richieste_manutenzione", "allegato_nome", "VARCHAR(255)"),
            ("richieste_manutenzione", "allegato_dati", "BYTEA")
        ]
        
        for tabella, colonna, tipo in colonne_migrazione:
            cur.execute(f"ALTER TABLE {tabella} ADD COLUMN IF NOT EXISTS {colonna} {tipo};")
        
        cur.execute("SELECT * FROM utenti WHERE username = 'admin';")
        if not cur.fetchone():
            hashed_pw = generate_password_hash("admin")
            cur.execute("INSERT INTO utenti (username, password, is_admin, puo_vedere_manutenzione, puo_eliminare, puo_eliminare_storico, puo_gestire_documenti, puo_assegnare_promemoria, puo_aprire_manutenzioni, puo_assegnare_manutenzioni) VALUES (%s, %s, 1, 1, 1, 1, 1, 1, 1, 1);", ('admin', hashed_pw))

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
                session['puo_vedere_manutenzione'] = user.get('puo_vedere_manutenzione', 1)
                session['puo_eliminare'] = user.get('puo_eliminare', 0)
                session['puo_eliminare_storico'] = user.get('puo_eliminare_storico', 0)
                session['puo_gestire_documenti'] = user.get('puo_gestire_documenti', 1)
                session['puo_assegnare_promemoria'] = user.get('puo_assegnare_promemoria', 0)
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
                cur.execute("INSERT INTO utenti (username, password, is_admin, puo_vedere_manutenzione, puo_eliminare, puo_eliminare_storico, puo_gestire_documenti, puo_assegnare_promemoria, puo_aprire_manutenzioni, puo_assegnare_manutenzioni) VALUES (%s, %s, 0, 1, 0, 0, 1, 0, 1, 1);", (username, hashed_pw))
                conn.commit()
                cur.close()
                conn.close()
                registra_log(f"Registrato nuovo utente: {username}")
                flash("Registrazione completata! Ora puoi effettuare il login.", "success")
                return redirect(url_for('login'))
            except Exception as e:
                flash("Username già esistente o errore di registrazione.", "error")
    return render_template("registra.html")

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
        writer.writerow([r['id'], r['titolo'], r['impianto_macchina'], r['priorita'], r['tipo_guasto'], r['stato'], r['assegnato_a'], r['creato_da'], r['inizio_lavoro'], r['fine_lavoro'], r['tempo_lavorato_minuti'], r['note_lavoro'], r['creato_il']])
    
    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-disposition": "attachment; filename=Report_Interventi_Officina.csv"}
    )

# --- RICHIESTE INTERVENTO MANUTENZIONE OFFICINA ---
@app.route("/richieste_manutenzione", methods=["GET", "POST"])
def richieste_manutenzione():
    username_corrente = session.get('username')
    is_admin = session.get('is_admin')
    puo_aprire_global = session.get('is_admin') or session.get('puo_aprire_manutenzioni', 1)
    puo_assegnare_global = session.get('is_admin') or session.get('puo_assegnare_manutenzioni', 1)
    
    conn = get_db_connection()
    cur = conn.cursor()
    
    if request.method == "POST":
        if not puo_aprire_global:
            flash("Non hai i permessi per aprire nuove richieste di intervento.", "error")
            return redirect(url_for("richieste_manutenzione"))

        titolo = request.form.get("titolo")
        impianto_macchina = request.form.get("impianto_macchina", "")
        descrizione = request.form.get("descrizione", "")
        priorita = request.form.get("priorita", "Media")
        tipo_guasto = request.form.get("tipo_guasto", "Meccanico")
        
        # Se l'utente può assegnare sceglie dal form, altrimenti si assegna a se stesso o resta vuoto
        if puo_assegnare_global:
            assegnato_a = request.form.get("assegnato_a", "")
        else:
            assegnato_a = username_corrente
        
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
            registra_log(f"Creata richiesta intervento: {titolo} su {impianto_macchina}")
            flash("Richiesta di intervento creata con successo!", "success")
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
                           puo_aprire=puo_aprire_global,
                           puo_assegnare_manut=puo_assegnare_global)

@app.route("/cambia_stato_intervento/<int:intervento_id>", methods=["POST"])
def cambia_stato_intervento(intervento_id):
    username_corrente = session.get('username')
    nuovo_stato = request.form.get("stato")
    note_lavoro = request.form.get("note_lavoro", "")
    nuovo_assegnatario = request.form.get("nuovo_assegnatario", "").strip()
    
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
            flash("Intervento completato e chiuso con successo!", "success")
            
        elif nuovo_stato == 'Riassegna':
            if session.get('is_admin') or session.get('puo_assegnare_manutenzioni', 1):
                if nuovo_assegnatario:
                    cur.execute("UPDATE richieste_manutenzione SET assegnato_a = %s WHERE id = %s;", (nuovo_assegnatario, intervento_id))
                    flash(f"Intervento riassegnato a {nuovo_assegnatario}.", "success")

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

@app.route("/elimina_intervento/<int:intervento_id>", methods=["POST"])
def elimina_intervento(intervento_id):
    if not session.get('is_admin'):
        flash("Permesso negato.", "error")
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

# --- GESTIONE UTENTI E LOG ---
@app.route("/admin_utenti")
def admin_utenti():
    if not session.get('is_admin'):
        flash("Accesso negato.", "error")
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

@app.route("/toggle_permesso/<int:user_id>/<tipo>", methods=["POST"])
def toggle_permesso(user_id, tipo):
    if not session.get('is_admin'):
        return redirect(url_for('index'))
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        if tipo == 'manutenzione':
            cur.execute("UPDATE utenti SET puo_vedere_manutenzione = 1 - puo_vedere_manutenzione WHERE id = %s;", (user_id,))
        elif tipo == 'eliminazione':
            cur.execute("UPDATE utenti SET puo_eliminare = 1 - puo_eliminare WHERE id = %s;", (user_id,))
        elif tipo == 'eliminazione_storico':
            cur.execute("UPDATE utenti SET puo_eliminare_storico = 1 - puo_eliminare_storico WHERE id = %s;", (user_id,))
        elif tipo == 'documenti':
            cur.execute("UPDATE utenti SET puo_gestire_documenti = 1 - puo_gestire_documenti WHERE id = %s;", (user_id,))
        elif tipo == 'assegnare_promemoria':
            cur.execute("UPDATE utenti SET puo_assegnare_promemoria = 1 - puo_assegnare_promemoria WHERE id = %s;", (user_id,))
        elif tipo == 'aprire_manutenzioni':
            cur.execute("UPDATE utenti SET puo_aprire_manutenzioni = 1 - puo_aprire_manutenzioni WHERE id = %s;", (user_id,))
        elif tipo == 'assegnare_manutenzioni':
            cur.execute("UPDATE utenti SET puo_assegnare_manutenzioni = 1 - puo_assegnare_manutenzioni WHERE id = %s;", (user_id,))
        conn.commit()
        cur.close()
        conn.close()
        registra_log(f"Modificati permessi utente ID {user_id} ({tipo})")
    except Exception as e:
        flash(f"Errore aggiornamento permessi: {e}", "error")
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

@app.route("/log_attivita")
def visualizza_log():
    return redirect(url_for('admin_utenti'))

# --- GESTIONE PROMEMORIA ---
@app.route("/promemoria", methods=["GET", "POST"])
def promemoria():
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
def fornitori():
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

@app.route("/importa_intelligente", methods=["POST"])
def importa_intelligente():
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

# --- GESTIONE DOCUMENTI ---
@app.route("/documenti", defaults={"cartella_id": None}, methods=["GET", "POST"])
@app.route("/documenti/<int:cartella_id>", methods=["GET", "POST"])
def documenti(cartella_id):
    if not (session.get('is_admin') or session.get('puo_gestire_documenti')):
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
                           percorso_breadcrumb=percorso_breadcrumb)

@app.route("/scarica_file/<int:file_id>")
def scarica_file(file_id):
    if not (session.get('is_admin') or session.get('puo_gestire_documenti')):
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
    if not session.get('is_admin'):
        flash("Solo l'amministratore può eliminare le cartelle.", "error")
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
    if not session.get('is_admin'):
        flash("Solo l'amministratore può eliminare i documenti.", "error")
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

# --- ALTRE ROTTE MAGAZZINO ---
@app.route("/upload", methods=["GET", "POST"])
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
def stampa_tutti_qr():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM prodotti ORDER BY nome ASC;")
    prodotti = cur.fetchall()
    cur.close()
    conn.close()
    return render_template("stampa_tutti_qr.html", prodotti=prodotti)

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

@app.route("/magazzino_pesante")
def magazzino_pesante():
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
    except Exception:
        pass
    return render_template("magazzino_pesante.html", prodotti=prodotti)

@app.route("/manutenzioni")
def manutenzioni():
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
def storico_manutenzioni():
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

@app.route("/elimina_storico_manutenzione/<int:storico_id>", methods=["POST"])
def elimina_storico_manutenzione(storico_id):
    if not (session.get('is_admin') or session.get('puo_eliminare_storico')):
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
            registra_log(f"Carico di +{quantita} pz su QR: {qr_code}")
            flash(f"Carico di {quantita} pz effettuato con successo!", "success")
            return redirect(url_for("gestisci_prodotto", qr_code=qr_code))
    return render_template("carico.html")

@app.route("/scarico", methods=["GET", "POST"])
def scarico():
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
def aggiorna_prodotto(qr_code):
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
def aggiungi_prodotto():
    qr_code = request.form.get("qr_code")
    nome = request.form.get("nome")
    sap = request.form.get("sap", "")
    peso = request.form.get("peso", "")
    quantita = int(request.form.get("quantita", 0))
    soglia_minima = int(request.form.get("soglia_minima", 3) or 3)
    posizione = request.form.get("posizione", "")
    flag_sezione = 1 if request.form.get("magazzino_pesante") else 0

    if not qr_code or not nome:
        flash("QR Code e Nome sono obbligatori!", "error")
        return redirect(url_for("index"))

    try:
        conn = get_db_connection()
        cur = conn.cursor()
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
        flash("Prodotto salvato con successo!", "success")
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
def elimina_prodotto():
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


Il lun 19 ott 2026, 22:22 marco pavan <marco.pavan1995@gmail.com> ha scritto:
# ========================================================================
# Magazzino OMG Application
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
from flask import Flask, render_template, request, redirect, url_for, flash, session, send_file, Response
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "chiave-segreta-magazzino")

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
                puo_vedere_manutenzione INT DEFAULT 1,
                puo_eliminare INT DEFAULT 0,
                puo_eliminare_storico INT DEFAULT 0,
                puo_gestire_documenti INT DEFAULT 1,
                puo_assegnare_promemoria INT DEFAULT 0
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
        
        cur.execute("ALTER TABLE fornitori ADD COLUMN IF NOT EXISTS settore_note VARCHAR(255);")
        cur.execute("ALTER TABLE contatti_tecnici ADD COLUMN IF NOT EXISTS email VARCHAR(255);")
        cur.execute("ALTER TABLE promemoria ADD COLUMN IF NOT EXISTS ricorrenza VARCHAR(50) DEFAULT 'Nessuna';")
        cur.execute("ALTER TABLE promemoria ADD COLUMN IF NOT EXISTS assegnato_a VARCHAR(255);")
        cur.execute("ALTER TABLE utenti ADD COLUMN IF NOT EXISTS puo_assegnare_promemoria INT DEFAULT 0;")
        cur.execute("ALTER TABLE richieste_manutenzione ADD COLUMN IF NOT EXISTS tipo_guasto VARCHAR(50) DEFAULT 'Meccanico';")
        cur.execute("ALTER TABLE richieste_manutenzione ADD COLUMN IF NOT EXISTS tempo_lavorato_minuti INT DEFAULT 0;")
        cur.execute("ALTER TABLE richieste_manutenzione ADD COLUMN IF NOT EXISTS allegato_nome VARCHAR(255);")
        cur.execute("ALTER TABLE richieste_manutenzione ADD COLUMN IF NOT EXISTS allegato_dati BYTEA;")
        
        cur.execute("SELECT * FROM utenti WHERE username = 'admin';")
        if not cur.fetchone():
            hashed_pw = generate_password_hash("admin")
            cur.execute("INSERT INTO utenti (username, password, is_admin, puo_vedere_manutenzione, puo_eliminare, puo_eliminare_storico, puo_gestire_documenti, puo_assegnare_promemoria) VALUES (%s, %s, 1, 1, 1, 1, 1, 1);", ('admin', hashed_pw))

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
                session['puo_vedere_manutenzione'] = user.get('puo_vedere_manutenzione', 1)
                session['puo_eliminare'] = user.get('puo_eliminare', 0)
                session['puo_eliminare_storico'] = user.get('puo_eliminare_storico', 0)
                session['puo_gestire_documenti'] = user.get('puo_gestire_documenti', 1)
                session['puo_assegnare_promemoria'] = user.get('puo_assegnare_promemoria', 0)
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
                cur.execute("INSERT INTO utenti (username, password, is_admin, puo_vedere_manutenzione, puo_eliminare, puo_eliminare_storico, puo_gestire_documenti, puo_assegnare_promemoria) VALUES (%s, %s, 0, 1, 0, 0, 1, 0);", (username, hashed_pw))
                conn.commit()
                cur.close()
                conn.close()
                registra_log(f"Registrato nuovo utente: {username}")
                flash("Registrazione completata! Ora puoi effettuare il login.", "success")
                return redirect(url_for('login'))
            except Exception as e:
                flash("Username già esistente o errore di registrazione.", "error")
    return render_template("registra.html")

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
        writer.writerow([r['id'], r['titolo'], r['impianto_macchina'], r['priorita'], r['tipo_guasto'], r['stato'], r['assegnato_a'], r['creato_da'], r['inizio_lavoro'], r['fine_lavoro'], r['tempo_lavorato_minuti'], r['note_lavoro'], r['creato_il']])
    
    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-disposition": "attachment; filename=Report_Interventi_Officina.csv"}
    )

# --- RICHIESTE INTERVENTO MANUTENZIONE OFFICINA ---
@app.route("/richieste_manutenzione", methods=["GET", "POST"])
def richieste_manutenzione():
    username_corrente = session.get('username')
    is_admin = session.get('is_admin')
    puo_assegnare = session.get('puo_assegnare_promemoria')
    
    conn = get_db_connection()
    cur = conn.cursor()
    
    if request.method == "POST":
        titolo = request.form.get("titolo")
        impianto_macchina = request.form.get("impianto_macchina", "")
        descrizione = request.form.get("descrizione", "")
        priorita = request.form.get("priorita", "Media")
        tipo_guasto = request.form.get("tipo_guasto", "Meccanico")
        assegnato_a = request.form.get("assegnato_a", "")
        
        # Gestione allegato foto opzionale
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
            registra_log(f"Creata richiesta intervento: {titolo} su {impianto_macchina}")
            flash("Richiesta di intervento creata con successo!", "success")
        return redirect(url_for("richieste_manutenzione"))

    cur.execute("SELECT username FROM utenti ORDER BY username ASC;")
    lista_utenti = cur.fetchall()

    cur.execute("SELECT * FROM prodotti ORDER BY nome ASC;")
    lista_prodotti = cur.fetchall()

    cur.execute("SELECT * FROM richieste_manutenzione ORDER BY CASE WHEN stato = 'Completata' THEN 2 ELSE 1 END, creato_il DESC;")
    richieste = cur.fetchall()

    # Recupera i ricambi associati a ciascun intervento
    ricambi_per_intervento = {}
    for r in richieste:
        cur.execute("SELECT * FROM intervento_ricambi WHERE intervento_id = %s;", (r['id'],))
        ricambi_per_intervento[r['id']] = cur.fetchall()

    cur.close()
    conn.close()
    
    return render_template("richieste_manutenzione.html", 
                           richieste=richieste, 
                           lista_utenti=lista_utenti, 
                           lista_prodotti=lista_prodotti,
                           ricambi_per_intervento=ricambi_per_intervento,
                           puo_assegnare=(is_admin or puo_assegnare))

@app.route("/cambia_stato_intervento/<int:intervento_id>", methods=["POST"])
def cambia_stato_intervento(intervento_id):
    username_corrente = session.get('username')
    nuovo_stato = request.form.get("stato")
    note_lavoro = request.form.get("note_lavoro", "")
    nuovo_assegnatario = request.form.get("nuovo_assegnatario", "").strip()
    
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM richieste_manutenzione WHERE id = %s;", (intervento_id,))
    req = cur.fetchone()
    
    if req:
        now = datetime.now()
        
        if nuovo_stato == 'In Lavoro':
            # Se riprende da pausa o inizia per la prima volta
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
            # Calcola i minuti trascorsi e li aggiunge al totale lavorato
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
            # Calcola minuti finali se era in corso
            inizio = req.get('inizio_lavoro')
            minuti_aggiunti = 0
            if inizio and req.get('stato') == 'In Lavoro':
                minuti_aggiunti = int((now - inizio).total_seconds() / 60)
            
            tempo_totale = req.get('tempo_lavorato_minuti', 0) + minuti_aggiunti

            # Gestione ricambi multipli dal form (riceve liste o singoli)
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
            flash("Intervento completato e chiuso con successo!", "success")
            
        elif nuovo_stato == 'Riassegna':
            if nuovo_assegnatario:
                cur.execute("UPDATE richieste_manutenzione SET assegnato_a = %s WHERE id = %s;", (nuovo_assegnatario, intervento_id))
                flash(f"Intervento riassegnato a {nuovo_assegnatario}.", "success")

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

@app.route("/elimina_intervento/<int:intervento_id>", methods=["POST"])
def elimina_intervento(intervento_id):
    if not session.get('is_admin'):
        flash("Permesso negato.", "error")
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

# --- GESTIONE UTENTI E LOG ---
@app.route("/admin_utenti")
def admin_utenti():
    if not session.get('is_admin'):
        flash("Accesso negato.", "error")
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

@app.route("/toggle_permesso/<int:user_id>/<tipo>", methods=["POST"])
def toggle_permesso(user_id, tipo):
    if not session.get('is_admin'):
        return redirect(url_for('index'))
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        if tipo == 'manutenzione':
            cur.execute("UPDATE utenti SET puo_vedere_manutenzione = 1 - puo_vedere_manutenzione WHERE id = %s;", (user_id,))
        elif tipo == 'eliminazione':
            cur.execute("UPDATE utenti SET puo_eliminare = 1 - puo_eliminare WHERE id = %s;", (user_id,))
        elif tipo == 'eliminazione_storico':
            cur.execute("UPDATE utenti SET puo_eliminare_storico = 1 - puo_eliminare_storico WHERE id = %s;", (user_id,))
        elif tipo == 'documenti':
            cur.execute("UPDATE utenti SET puo_gestire_documenti = 1 - puo_gestire_documenti WHERE id = %s;", (user_id,))
        elif tipo == 'assegnare_promemoria':
            cur.execute("UPDATE utenti SET puo_assegnare_promemoria = 1 - puo_assegnare_promemoria WHERE id = %s;", (user_id,))
        conn.commit()
        cur.close()
        conn.close()
        registra_log(f"Modificati permessi utente ID {user_id} ({tipo})")
    except Exception as e:
        flash(f"Errore aggiornamento permessi: {e}", "error")
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

@app.route("/log_attivita")
def visualizza_log():
    return redirect(url_for('admin_utenti'))

# --- GESTIONE PROMEMORIA ---
@app.route("/promemoria", methods=["GET", "POST"])
def promemoria():
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
def fornitori():
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

@app.route("/importa_intelligente", methods=["POST"])
def importa_intelligente():
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

# --- GESTIONE DOCUMENTI ---
@app.route("/documenti", defaults={"cartella_id": None}, methods=["GET", "POST"])
@app.route("/documenti/<int:cartella_id>", methods=["GET", "POST"])
def documenti(cartella_id):
    if not (session.get('is_admin') or session.get('puo_gestire_documenti')):
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
                           percorso_breadcrumb=percorso_breadcrumb)

@app.route("/scarica_file/<int:file_id>")
def scarica_file(file_id):
    if not (session.get('is_admin') or session.get('puo_gestire_documenti')):
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
    if not session.get('is_admin'):
        flash("Solo l'amministratore può eliminare le cartelle.", "error")
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
    if not session.get('is_admin'):
        flash("Solo l'amministratore può eliminare i documenti.", "error")
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

# --- ALTRE ROTTE MAGAZZINO ---
@app.route("/upload", methods=["GET", "POST"])
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
def stampa_tutti_qr():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM prodotti ORDER BY nome ASC;")
    prodotti = cur.fetchall()
    cur.close()
    conn.close()
    return render_template("stampa_tutti_qr.html", prodotti=prodotti)

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

@app.route("/magazzino_pesante")
def magazzino_pesante():
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
    except Exception:
        pass
    return render_template("magazzino_pesante.html", prodotti=prodotti)

@app.route("/manutenzioni")
def manutenzioni():
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
def storico_manutenzioni():
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

@app.route("/elimina_storico_manutenzione/<int:storico_id>", methods=["POST"])
def elimina_storico_manutenzione(storico_id):
    if not (session.get('is_admin') or session.get('puo_eliminare_storico')):
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
            registra_log(f"Carico di +{quantita} pz su QR: {qr_code}")
            flash(f"Carico di {quantita} pz effettuato con successo!", "success")
            return redirect(url_for("gestisci_prodotto", qr_code=qr_code))
    return render_template("carico.html")

@app.route("/scarico", methods=["GET", "POST"])
def scarico():
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
def aggiorna_prodotto(qr_code):
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
def aggiungi_prodotto():
    qr_code = request.form.get("qr_code")
    nome = request.form.get("nome")
    sap = request.form.get("sap", "")
    peso = request.form.get("peso", "")
    quantita = int(request.form.get("quantita", 0))
    soglia_minima = int(request.form.get("soglia_minima", 3) or 3)
    posizione = request.form.get("posizione", "")
    flag_sezione = 1 if request.form.get("magazzino_pesante") else 0

    if not qr_code or not nome:
        flash("QR Code e Nome sono obbligatori!", "error")
        return redirect(url_for("index"))

    try:
        conn = get_db_connection()
        cur = conn.cursor()
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
        flash("Prodotto salvato con successo!", "success")
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
def elimina_prodotto():
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
