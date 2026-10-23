# ========================================================================
# Gestionale OMG Application - Complete System
# Copyright (c) 2026 Marco Pavan. All Rights Reserved.
# ========================================================================

import os
import csv
import io
from datetime import datetime, timedelta
import pandas as pd
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
                nome VARCHAR(255) NOT NULL
            );
        """)
        
        cur.execute("""
            CREATE TABLE IF NOT EXISTS fornitori (
                id SERIAL PRIMARY KEY,
                nome_azienda VARCHAR(255) UNIQUE NOT NULL
            );
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS contatti_tecnici (
                id SERIAL PRIMARY KEY,
                fornitore_id INT REFERENCES fornitori(id) ON DELETE CASCADE,
                nome VARCHAR(255) NOT NULL,
                telefono VARCHAR(255) NOT NULL
            );
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS promemoria (
                id SERIAL PRIMARY KEY,
                titolo VARCHAR(255) NOT NULL
            );
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS richieste_manutenzione (
                id SERIAL PRIMARY KEY,
                titolo VARCHAR(255) NOT NULL
            );
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS utenti (
                id SERIAL PRIMARY KEY,
                username VARCHAR(255) UNIQUE NOT NULL,
                password VARCHAR(255) NOT NULL
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
                data_cambio VARCHAR(255),
                forno_macchina VARCHAR(255),
                bottiglia_nuova VARCHAR(255),
                numero_bottiglie INT DEFAULT 0,
                numero_bottiglie_tempera INT DEFAULT 0,
                piastrina_stacker VARCHAR(255),
                operatore VARCHAR(255),
                note TEXT,
                creato_il TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)

        # Colonne aggiuntive per prodotti
        colonne_prodotti = [
            ("sap", "VARCHAR(255)"), ("peso", "VARCHAR(255)"), ("quantita", "INT DEFAULT 0"),
            ("posizione", "VARCHAR(255)"), ("magazzino_pesante", "INT DEFAULT 0"),
            ("in_manutenzione", "BOOLEAN DEFAULT FALSE"), ("cliente_manutenzione", "VARCHAR(255)"),
            ("quantita_manutenzione", "INT DEFAULT 0"), ("data_spedizione", "VARCHAR(255)"),
            ("data_riconsegna", "VARCHAR(255)"), ("vettore", "VARCHAR(255)"),
            ("ordine_amministrativo", "BOOLEAN DEFAULT FALSE"), ("note_manutenzione", "TEXT"),
            ("soglia_minima", "INT DEFAULT 3")
        ]
        for col, ctype in colonne_prodotti:
            cur.execute(f"ALTER TABLE prodotti ADD COLUMN IF NOT EXISTS {col} {ctype};")

        # Colonne promemoria
        colonne_promemoria = [
            ("descrizione", "TEXT"), ("data_scadenza", "VARCHAR(255)"),
            ("priorita", "VARCHAR(50) DEFAULT 'Media'"), ("ricorrenza", "VARCHAR(50) DEFAULT 'Nessuna'"),
            ("assegnato_a", "VARCHAR(255)"), ("completato", "BOOLEAN DEFAULT FALSE"),
            ("creato_il", "TIMESTAMP DEFAULT CURRENT_TIMESTAMP")
        ]
        for col, ctype in colonne_promemoria:
            cur.execute(f"ALTER TABLE promemoria ADD COLUMN IF NOT EXISTS {col} {ctype};")

        # Colonne manutenzione
        colonne_manutenzione = [
            ("impianto_macchina", "VARCHAR(255)"), ("descrizione", "TEXT"),
            ("priorita", "VARCHAR(50) DEFAULT 'Media'"), ("stato", "VARCHAR(50) DEFAULT 'Aperta'"),
            ("tipo_guasto", "VARCHAR(50) DEFAULT 'Meccanico'"), ("assegnato_a", "TEXT"),
            ("creato_da", "VARCHAR(255)"), ("inizio_lavoro", "TIMESTAMP"), ("fine_lavoro", "TIMESTAMP"),
            ("tempo_lavorato_minuti", "INT DEFAULT 0"), ("note_lavoro", "TEXT"),
            ("allegato_nome", "VARCHAR(255)"), ("allegato_dati", "BYTEA"),
            ("creato_il", "TIMESTAMP DEFAULT CURRENT_TIMESTAMP")
        ]
        for col, ctype in colonne_manutenzione:
            cur.execute(f"ALTER TABLE richieste_manutenzione ADD COLUMN IF NOT EXISTS {col} {ctype};")

        # Permessi utente
        permessi_lista = [
            ("is_admin", "INT DEFAULT 0"),
            ("puo_vedere_magazzino", "INT DEFAULT 1"), ("puo_aggiungere_prodotti", "INT DEFAULT 1"),
            ("puo_modificare_prodotti", "INT DEFAULT 1"), ("puo_caricare_scaricare", "INT DEFAULT 1"),
            ("puo_eliminare", "INT DEFAULT 0"), ("puo_vedere_pesante", "INT DEFAULT 1"),
            ("puo_vedere_manutenzione", "INT DEFAULT 1"), ("puo_aprire_manutenzioni", "INT DEFAULT 1"),
            ("puo_gestire_interventi", "INT DEFAULT 1"), ("puo_assegnare_manutenzioni", "INT DEFAULT 1"),
            ("puo_eliminare_interventi", "INT DEFAULT 0"), ("puo_vedere_manutenzioni_esterne", "INT DEFAULT 1"),
            ("puo_vedere_storico_manutenzioni", "INT DEFAULT 1"), ("puo_eliminare_storico", "INT DEFAULT 0"),
            ("puo_gestire_fornitori", "INT DEFAULT 1"), ("puo_importare_fornitori", "INT DEFAULT 1"),
            ("puo_gestire_documenti", "INT DEFAULT 1"), ("puo_eliminare_documenti", "INT DEFAULT 0"),
            ("puo_vedere_promemoria", "INT DEFAULT 1"), ("puo_assegnare_promemoria", "INT DEFAULT 1"),
            ("puo_vedere_report_ore", "INT DEFAULT 1")
        ]
        for p_col, p_type in permessi_lista:
            cur.execute(f"ALTER TABLE utenti ADD COLUMN IF NOT EXISTS {p_col} {p_type};")
        
        # Admin di default
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
                           interventi_aperti_count=interventi_aperti_count)

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
                    VALUES (%s, %s, 0, 1, 1, 1, 1, 0, 1, 1, 1, 1, 1, 0, 1, 1, 0, 1, 1, 1, 0, 1, 1, 1);
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

@app.route("/admin_utenti", methods=["GET", "POST"])
def admin_utenti():
    if not session.get('is_admin'):
        flash("Accesso riservato all'Amministratore.", "error")
        return redirect(url_for('index'))
    
    conn = None
    cur = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        if request.method == "POST":
            user_id = request.form.get("user_id")
            is_admin_val = 1 if request.form.get("is_admin") else 0
            
            permessi_possibili = [
                "puo_vedere_magazzino", "puo_aggiungere_prodotti", "puo_modificare_prodotti",
                "puo_caricare_scaricare", "puo_eliminare", "puo_vedere_pesante",
                "puo_vedere_manutenzione", "puo_aprire_manutenzioni", "puo_gestire_interventi",
                "puo_assegnare_manutenzioni", "puo_eliminare_interventi", "puo_vedere_manutenzioni_esterne",
                "puo_vedere_storico_manutenzioni", "puo_eliminare_storico", "puo_gestire_fornitori",
                "puo_importare_fornitori", "puo_gestire_documenti", "puo_eliminare_documenti",
                "puo_vedere_promemoria", "puo_assegnare_promemoria", "puo_vedere_report_ore"
            ]
            
            set_clauses = ["is_admin = %s"]
            values = [is_admin_val]
            
            for p in permessi_possibili:
                val = 1 if request.form.get(p) else 0
                set_clauses.append(f"{p} = %s")
                values.append(val)
                
            values.append(user_id)
            query = f"UPDATE utenti SET {', '.join(set_clauses)} WHERE id = %s;"
            cur.execute(query, tuple(values))
            conn.commit()
            
            registra_log(f"Aggiornati permessi per l'utente ID {user_id}")
            flash("Permessi utente aggiornati con successo!", "success")
            return redirect(url_for('admin_utenti'))

        cur.execute("SELECT * FROM utenti ORDER BY username ASC;")
        utenti = cur.fetchall()
        
        logs = []
        try:
            cur.execute("SELECT * FROM log_attivita ORDER BY data_ora DESC LIMIT 100;")
            logs = cur.fetchall()
        except Exception:
            if conn:
                conn.rollback()
            logs = []
            
        cur.close()
        conn.close()
    except Exception as e:
        if cur:
            try: cur.close()
            except: pass
        if conn:
            try: conn.rollback(); conn.close()
            except: pass
        flash(f"Errore critico pannello admin: {e}", "error")
        utenti = []
        logs = []

    return render_template("admin_utenti.html", utenti=utenti, logs=logs)

@app.route("/admin_reset_password/<int:user_id>", methods=["POST"])
def admin_reset_password(user_id):
    if not session.get('is_admin'):
        flash("Accesso riservato all'Amministratore.", "error")
        return redirect(url_for('index'))
    
    nuova_password = request.form.get("nuova_password")
    if nuova_password:
        try:
            hashed_pw = generate_password_hash(nuova_password)
            conn = get_db_connection()
            cur = conn.cursor()
            cur.execute("UPDATE utenti SET password = %s WHERE id = %s;", (hashed_pw, user_id))
            conn.commit()
            cur.close()
            conn.close()
            
            registra_log(f"Password reimpostata per l'utente ID {user_id} dall'amministratore")
            flash("Password reimpostata con successo!", "success")
        except Exception as e:
            flash(f"Errore durante il reset della password: {e}", "error")
    else:
        flash("La nuova password non può essere vuota.", "error")
        
    return redirect(url_for('admin_utenti'))

@app.route("/admin_elimina_utente/<int:user_id>", methods=["POST"])
def admin_elimina_utente(user_id):
    if not session.get('is_admin'):
        flash("Accesso riservato all'Amministratore.", "error")
        return redirect(url_for('index'))
    
    conn = get_db_connection()
    cur = conn.cursor()
    
    cur.execute("SELECT username FROM utenti WHERE id = %s;", (user_id,))
    u = cur.fetchone()
    
    if u and u['username'] == 'admin':
        flash("Non è possibile eliminare l'utente amministratore principale di sistema ('admin').", "error")
    elif u and u['username'] == session.get('username'):
        flash("Non puoi eliminare il tuo stesso account mentre sei loggato.", "error")
    else:
        cur.execute("DELETE FROM utenti WHERE id = %s;", (user_id,))
        conn.commit()
        registra_log(f"Eliminato utente ID {user_id} ({u['username'] if u else ''})")
        flash("Utente eliminato con successo.", "success")
        
    cur.close()
    conn.close()
    return redirect(url_for('admin_utenti'))

# --- MODULO FORNITORI ---
@app.route("/fornitori", methods=["GET", "POST"])
def fornitori():
    if not (session.get('is_admin') or session.get('puo_gestire_fornitori', 1)):
        return redirect(url_for('index'))
        
    conn = get_db_connection()
    cur = conn.cursor()
    
    if request.method == "POST":
        nome_azienda = request.form.get("nome_azienda")
        if nome_azienda:
            try:
                cur.execute("INSERT INTO fornitori (nome_azienda) VALUES (%s) RETURNING id;", (nome_azienda,))
                fornitore_id = cur.fetchone()['id']
                
                nomi_contatto = request.form.getlist("contatto_nome[]")
                telefoni_contatto = request.form.getlist("contatto_telefono[]")
                for n, t in zip(nomi_contatto, telefoni_contatto):
                    if n.strip() and t.strip():
                        cur.execute("INSERT INTO contatti_tecnici (fornitore_id, nome, telefono) VALUES (%s, %s, %s);", (fornitore_id, n.strip(), t.strip()))
                
                conn.commit()
                registra_log(f"Aggiunto fornitore: {nome_azienda}")
                flash("Fornitore aggiunto con successo!", "success")
            except Exception as e:
                conn.rollback()
                flash(f"Errore inserimento fornitore (possibile nome duplicato): {e}", "error")
        cur.close()
        conn.close()
        return redirect(url_for('fornitori'))
        
    cur.execute("SELECT * FROM fornitori ORDER BY nome_azienda ASC;")
    lista_fornitori = cur.fetchall()
    
    fornitori_con_contatti = []
    for f in lista_fornitori:
        cur.execute("SELECT * FROM contatti_tecnici WHERE fornitore_id = %s;", (f['id'],))
        contatti = cur.fetchall()
        f_dict = dict(f)
        f_dict['contatti'] = contatti
        fornitori_con_contatti.append(f_dict)
        
    cur.close()
    conn.close()
    return render_template("fornitori.html", fornitori=fornitori_con_contatti)

@app.route("/elimina_fornitore/<int:fornitore_id>", methods=["POST"])
def elimina_fornitore(fornitore_id):
    if not session.get('username'):
        return redirect(url_for('login'))
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM fornitori WHERE id = %s;", (fornitore_id,))
    conn.commit()
    cur.close()
    conn.close()
    flash("Fornitore eliminato.", "success")
    return redirect(url_for('fornitori'))

# --- MODULO DOCUMENTI ---
@app.route("/documenti", defaults={"cartella_id": None}, methods=["GET", "POST"])
@app.route("/documenti/<int:cartella_id>", methods=["GET", "POST"])
def documenti(cartella_id):
    if not (session.get('is_admin') or session.get('puo_gestire_documenti', 1)):
        return redirect(url_for('index'))
        
    conn = get_db_connection()
    cur = conn.cursor()
    
    if request.method == "POST":
        azione = request.form.get("azione")
        if azione == "crea_cartella":
            nome_cartella = request.form.get("nome_cartella")
            if nome_cartella:
                cur.execute("INSERT INTO cartelle (nome, parent_id) VALUES (%s, %s);", (nome_cartella, cartella_id))
                conn.commit()
                flash("Cartella creata con successo!", "success")
        elif azione == "carica_file":
            file = request.files.get("file")
            if file and file.filename:
                filename = file.filename
                filedata = file.read()
                mimetype = file.content_type
                cur.execute("""
                    INSERT INTO documenti (cartella_id, nome_file, tipo_file, dati_file)
                    VALUES (%s, %s, %s, %s);
                """, (cartella_id, filename, mimetype, psycopg2.Binary(filedata)))
                conn.commit()
                flash("File caricato con successo!", "success")
        cur.close()
        conn.close()
        return redirect(url_for('documenti', cartella_id=cartella_id) if cartella_id else url_for('documenti'))

    percorso = []
    curr = cartella_id
    while curr is not None:
        cur.execute("SELECT id, nome, parent_id FROM cartelle WHERE id = %s;", (curr,))
        c = cur.fetchone()
        if c:
            percorso.insert(0, c)
            curr = c['parent_id']
        else:
            break

    if cartella_id is None:
        cur.execute("SELECT * FROM cartelle WHERE parent_id IS NULL ORDER BY nome ASC;")
    else:
        cur.execute("SELECT * FROM cartelle WHERE parent_id = %s ORDER BY nome ASC;", (cartella_id,))
    sottocartelle = cur.fetchall()

    if cartella_id is None:
        cur.execute("SELECT id, nome_file, tipo_file, caricato_il FROM documenti WHERE cartella_id IS NULL ORDER BY nome_file ASC;")
    else:
        cur.execute("SELECT id, nome_file, tipo_file, caricato_il FROM documenti WHERE cartella_id = %s ORDER BY nome_file ASC;", (cartella_id,))
    lista_file = cur.fetchall()

    cartella_corrente = None
    if cartella_id:
        cur.execute("SELECT * FROM cartelle WHERE id = %s;", (cartella_id,))
        cartella_corrente = cur.fetchone()

    cur.close()
    conn.close()
    
    return render_template("documenti.html", 
                           cartella_corrente=cartella_corrente, 
                           sottocartelle=sottocartelle, 
                           lista_file=lista_file, 
                           percorso_breadcrumb=percorso)

@app.route("/scarica_documento/<int:doc_id>")
def scarica_documento(doc_id):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT nome_file, tipo_file, dati_file FROM documenti WHERE id = %s;", (doc_id,))
    doc = cur.fetchone()
    cur.close()
    conn.close()
    if doc:
        return Response(
            doc['dati_file'],
            mimetype=doc['tipo_file'] or 'application/octet-stream',
            headers={"Content-disposition": f"attachment; filename={doc['nome_file']}"}
        )
    flash("Documento non trovato.", "error")
    return redirect(url_for('documenti'))

@app.route("/elimina_documento/<int:doc_id>", methods=["POST"])
def elimina_documento(doc_id):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM documenti WHERE id = %s;", (doc_id,))
    conn.commit()
    cur.close()
    conn.close()
    flash("Documento eliminato.", "success")
    return redirect(url_for('documenti'))

@app.route("/elimina_cartella/<int:cartella_id>", methods=["POST"])
def elimina_cartella(cartella_id):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT parent_id FROM cartelle WHERE id = %s;", (cartella_id,))
    c = cur.fetchone()
    parent_id = c['parent_id'] if c else None
    
    cur.execute("DELETE FROM cartelle WHERE id = %s;", (cartella_id,))
    conn.commit()
    cur.close()
    conn.close()
    flash("Cartella eliminata.", "success")
    if parent_id:
        return redirect(url_for('documenti', cartella_id=parent_id))
    return redirect(url_for('documenti'))

# --- MODULO CAMBI SERIE ---
@app.route("/cambi_serie", methods=["GET", "POST"])
def cambi_serie():
    if not session.get('username'):
        return redirect(url_for('login'))
    
    conn = get_db_connection()
    cur = conn.cursor()
    
    if request.method == "POST":
        data_cambio = request.form.get("data_cambio", datetime.now().strftime("%Y-%m-%d"))
        forno_macchina = request.form.get("forno_macchina", "")
        bottiglia_nuova = request.form.get("bottiglia_nuova", "")
        numero_bottiglie = int(request.form.get("numero_bottiglie", 0) or 0)
        numero_bottiglie_tempera = int(request.form.get("numero_bottiglie_tempera", 0) or 0)
        piastrina_stacker = request.form.get("piastrina_stacker", "")
        operatore = session.get('username', '')
        note = request.form.get("note", "")
        
        cur.execute("""
            INSERT INTO cambi_serie (data_cambio, forno_macchina, bottiglia_nuova, numero_bottiglie, numero_bottiglie_tempera, piastrina_stacker, operatore, note)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s);
        """, (data_cambio, forno_macchina, bottiglia_nuova, numero_bottiglie, numero_bottiglie_tempera, piastrina_stacker, operatore, note))
        conn.commit()
        registra_log(f"Registrato cambio serie su {forno_macchina}: '{bottiglia_nuova}' ({numero_bottiglie} btg)")
        flash("Cambio serie registrato con successo!", "success")
        cur.close()
        conn.close()
        return redirect(url_for('cambi_serie'))
        
    cur.execute("SELECT * FROM cambi_serie ORDER BY data_cambio DESC, id DESC;")
    lista_cambi = cur.fetchall()
    cur.close()
    conn.close()
    
    return render_template("cambi_serie.html", cambi=lista_cambi)

@app.route("/elimina_cambio_serie/<int:id>", methods=["POST"])
def elimina_cambio_serie(id):
    if not session.get('username'):
        return redirect(url_for('login'))
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM cambi_serie WHERE id = %s;", (id,))
    conn.commit()
    cur.close()
    conn.close()
    registra_log(f"Eliminato cambio serie ID {id}")
    flash("Cambio serie eliminato.", "success")
    return redirect(url_for('cambi_serie'))

# --- ALTRE ROTTE DI SUPPORTO ---
@app.route("/esporta")
def esporta():
    return render_template("esportazioni.html")

@app.route("/esporta_inventario")
def esporta_inventario():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT qr_code, nome, sap, quantita, posizione, peso FROM prodotti WHERE COALESCE(magazzino_pesante, 0) = 0 ORDER BY nome ASC;")
    prodotti = cur.fetchall()
    cur.close()
    conn.close()
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['QR Code', 'Nome Articolo', 'SAP', 'Quantita', 'Posizione', 'Peso'])
    for p in prodotti:
        writer.writerow([p['qr_code'], p['nome'], p['sap'], p['quantita'], p['posizione'], p['peso']])
    return Response(output.getvalue(), mimetype="text/csv", headers={"Content-disposition": "attachment; filename=Inventario_Principale_OMG.csv"})

@app.route("/esporta_pesante")
def esporta_pesante():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT qr_code, nome, sap, quantita, posizione, peso FROM prodotti WHERE magazzino_pesante = 1 OR magazzino_pesante = TRUE ORDER BY nome ASC;")
    prodotti = cur.fetchall()
    cur.close()
    conn.close()
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['QR Code', 'Nome Articolo', 'SAP', 'Quantita', 'Posizione', 'Peso'])
    for p in prodotti:
        writer.writerow([p['qr_code'], p['nome'], p['sap'], p['quantita'], p['posizione'], p['peso']])
    return Response(output.getvalue(), mimetype="text/csv", headers={"Content-disposition": "attachment; filename=Magazzino_Pesante_OMG.csv"})

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

@app.route("/aggiorna/<qr_code>", methods=["POST"])
def aggiorna_prodotto(qr_code):
    nome = request.form.get("nome")
    sap = request.form.get("sap", "")
    posizione = request.form.get("posizione", "")
    peso = request.form.get("peso", "")
    soglia = int(request.form.get("soglia_minima", 3) or 3)
    pesante = 1 if request.form.get("magazzino_pesante") else 0
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        UPDATE prodotti SET nome = %s, sap = %s, posizione = %s, peso = %s, magazzino_pesante = %s, soglia_minima = %s WHERE qr_code = %s;
    """, (nome, sap, posizione, peso, pesante, soglia, qr_code))
    conn.commit()
    cur.close()
    conn.close()
    flash("Aggiornato!", "success")
    return redirect(url_for("gestisci_prodotto", qr_code=qr_code))

@app.route("/aggiungi", methods=["POST"])
def aggiungi_prodotto():
    qr = request.form.get("qr_code")
    nome = request.form.get("nome")
    sap = request.form.get("sap", "")
    peso = request.form.get("peso", "")
    qta = int(request.form.get("quantita", 0))
    soglia = int(request.form.get("soglia_minima", 3) or 3)
    pos = request.form.get("posizione", "")
    pesante = 1 if request.form.get("magazzino_pesante") else 0
    if qr and nome:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO prodotti (qr_code, nome, sap, peso, quantita, posizione, magazzino_pesante, soglia_minima)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (qr_code) DO UPDATE SET quantita = prodotti.quantita + EXCLUDED.quantita, nome = EXCLUDED.nome;
        """, (qr, nome, sap, peso, qta, pos, pesante, soglia))
        conn.commit()
        cur.close()
        conn.close()
        flash("Salvato!", "success")
    return redirect(url_for("magazzino_pesante" if pesante == 1 else "index"))

@app.route("/magazzino_pesante")
def magazzino_pesante():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM prodotti ORDER BY nome ASC;")
    tutti = cur.fetchall()
    cur.close()
    conn.close()
    prodotti = [p for p in tutti if p.get('magazzino_pesante') in [1, '1', True, 1.0]]
    return render_template("magazzino_pesante.html", prodotti=prodotti)

@app.route("/manutenzioni")
def manutenzioni():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM prodotti ORDER BY nome ASC;")
    tutti = cur.fetchall()
    cur.close()
    conn.close()
    prodotti = [p for p in tutti if p.get('in_manutenzione') in [1, '1', True, 1.0]]
    return render_template("manutenzioni.html", prodotti=prodotti)

@app.route("/stampa_tutti_qr")
def stampa_tutti_qr():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM prodotti ORDER BY nome ASC;")
    prodotti = cur.fetchall()
    cur.close()
    conn.close()
    return render_template("stampa_tutti_qr.html", prodotti=prodotti)

if __name__ == "_main_":
    app.run(debug=True)
