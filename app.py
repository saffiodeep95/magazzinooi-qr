import os
import psycopg2
from psycopg2.extras import RealDictCursor
from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify

app = Flask(_name_)
app.secret_key = os.environ.get("SECRET_KEY", "super_segreto_omg_2026")

def get_db_connection():
    db_url = os.environ.get("DATABASE_URL")
    conn = psycopg2.connect(db_url, cursor_factory=RealDictCursor)
    return conn

def registra_log(messaggio):
    print(f"[LOG OMG]: {messaggio}")

# --- INIZIALIZZAZIONE COMPLETA DEL DATABASE ---
def init_db():
    conn = get_db_connection()
    cur = conn.cursor()
    
    # 1. Tabella Prodotti & Magazzino Pesante (con Matricola, Stato Pezzo e Riparazioni)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS prodotti (
            qr_code VARCHAR(100) PRIMARY KEY,
            nome VARCHAR(255) NOT NULL,
            sap VARCHAR(100),
            quantita INT DEFAULT 0,
            posizione VARCHAR(100),
            peso VARCHAR(50),
            soglia_minima INT DEFAULT 3,
            magazzino_pesante BOOLEAN DEFAULT FALSE,
            matricola VARCHAR(100),
            stato_pezzo VARCHAR(100) DEFAULT 'Nuovo ✨',
            volte_riparato INT DEFAULT 0,
            in_manutenzione BOOLEAN DEFAULT FALSE,
            cliente_manutenzione VARCHAR(255),
            quantita_manutenzione INT DEFAULT 0,
            data_spedizione DATE,
            data_riconsegna DATE,
            vettore VARCHAR(100),
            ordine_amministrativo BOOLEAN DEFAULT FALSE,
            note_manutenzione TEXT
        );
    """)

    # 2. Tabella Storico Manutenzioni Esterne (con Esito e Rientro)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS storico_manutenzioni (
            id SERIAL PRIMARY KEY,
            nome_prodotto VARCHAR(255),
            qr_code VARCHAR(100),
            sap VARCHAR(100),
            cliente VARCHAR(255),
            quantita INT DEFAULT 1,
            data_riconsegna DATE,
            note TEXT,
            esito VARCHAR(100),
            registrato_il TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)

    # 3. Tabella Richieste Interventi Officina Interna
    cur.execute("""
        CREATE TABLE IF NOT EXISTS richieste_manutenzione (
            id SERIAL PRIMARY KEY,
            impianto_macchina VARCHAR(255),
            titolo VARCHAR(255) NOT NULL,
            tipo_guasto VARCHAR(100) DEFAULT 'Meccanico',
            priorita VARCHAR(50) DEFAULT 'Media',
            stato VARCHAR(50) DEFAULT 'Aperto',
            creato_da VARCHAR(100),
            assegnato_a VARCHAR(100),
            descrizione TEXT,
            inizio_lavoro TIMESTAMP,
            fine_lavoro TIMESTAMP,
            tempo_lavorato_minuti INT DEFAULT 0,
            note_lavoro TEXT,
            creato_il TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)

    # 4. Tabella Fornitori
    cur.execute("""
        CREATE TABLE IF NOT EXISTS fornitori (
            id SERIAL PRIMARY KEY,
            nome_azienda VARCHAR(255) NOT NULL,
            contatto VARCHAR(255),
            telefono VARCHAR(100),
            email VARCHAR(255),
            settore_note TEXT
        );
    """)

    # 5. Tabella Notifiche di Sistema
    cur.execute("""
        CREATE TABLE IF NOT EXISTS notifiche (
            id SERIAL PRIMARY KEY,
            titolo VARCHAR(255),
            messaggio TEXT,
            letta BOOLEAN DEFAULT FALSE,
            creata_il TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)

    conn.commit()
    cur.close()
    conn.close()

try:
    init_db()
except Exception as e:
    print(f"Errore inizializzazione DB: {e}")


# --- GESTIONE AUTENTICAZIONE E ADMIN ---
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "").strip()
        
        admin_password = os.environ.get("ADMIN_PASSWORD", "omg2026admin")
        
        if username == "admin" and password == admin_password:
            session['is_admin'] = True
            session['username'] = username
            session['puo_modificare_prodotti'] = True
            session['puo_eliminare'] = True
            flash("Login effettuato con successo come Amministratore!", "success")
            return redirect(url_for("index"))
        else:
            flash("Credenziali non valide. Riprova.", "error")
            
    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    flash("Logout effettuato con successo.", "success")
    return redirect(url_for("index"))


# --- DASHBOARD PRINCIPALE ---
@app.route("/")
def index():
    conn = get_db_connection()
    cur = conn.cursor()
    
    cur.execute("SELECT * FROM prodotti ORDER BY nome ASC;")
    prodotti = cur.fetchall()
    
    prodotti_sotto_soglia = [p for p in prodotti if p['quantita'] <= (p.get('soglia_minima') or 3)]

    try:
        cur.execute("SELECT COUNT(*) FROM richieste_manutenzione WHERE stato = 'Aperto';")
        interventi_aperti_count = cur.fetchone()['count']
        cur.execute("SELECT COUNT(*) FROM richieste_manutenzione WHERE stato = 'In Lavoro';")
        interventi_in_lavoro_count = cur.fetchone()['count']
    except Exception:
        interventi_aperti_count = 0
        interventi_in_lavoro_count = 0

    cur.execute("SELECT * FROM fornitori ORDER BY nome_azienda ASC;")
    fornitori = cur.fetchall()

    cur.close()
    conn.close()
    
    return render_template("index.html", 
                           prodotti=prodotti, 
                           prodotti_sotto_soglia=prodotti_sotto_soglia,
                           interventi_aperti_count=interventi_aperti_count,
                           interventi_in_lavoro_count=interventi_in_lavoro_count,
                           fornitori=fornitori)


# --- INSERIMENTO E MODIFICA PRODOTTI ---
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
    stato_pezzo = request.form.get("stato_pezzo", "Nuovo ✨")

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
        flash(f"Errore durante il salvataggio (Codice o Matricola duplicati?): {e}", "error")

    return redirect(url_for("index"))


# --- SCHEDA DETTAGLIO ARTICOLO ---
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
    except Exception as e:
        print(f"Errore recupero fornitori: {e}")

    cur.execute("""
        SELECT * FROM storico_manutenzioni 
        WHERE qr_code = %s 
        ORDER BY id DESC;
    """, (qr_code,))
    storico_prodotto = cur.fetchall()

    cur.close()
    conn.close()
    
    if not prodotto:
        flash("Prodotto non trovato!", "error")
        return redirect(url_for("index"))
        
    return render_template("gestisci.html", 
                           prodotto=prodotto, 
                           fornitori=lista_fornitori, 
                           storico_prodotto=storico_prodotto)


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
        flash("Dati articolo aggiornati con successo!", "success")
    except Exception as e:
        flash(f"Errore aggiornamento articolo: {e}", "error")

    return redirect(url_for("gestisci_prodotto", qr_code=qr_code))


# --- INVIO IN MANUTENZIONE ESTERNA ---
@app.route("/manda_manutenzione/<qr_code>", methods=["POST"])
def manda_manutenzione(qr_code):
    cliente = request.form.get("cliente_manutenzione", "").strip()
    quantita = int(request.form.get("quantita_manutenzione", 1))
    data_sp = request.form.get("data_spedizione") or None
    data_ric = request.form.get("data_riconsegna") or None
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
        """, (cliente, quantita, data_sp, data_ric, vettore, note, quantita, qr_code))
        
        cur.execute("""
            INSERT INTO notifiche (titolo, messaggio)
            VALUES (%s, %s);
        """, ("Invio in Manutenzione", f"Articolo {qr_code} spedito a {cliente}"))

        conn.commit()
        cur.close()
        conn.close()
        flash(f"Articolo inviato in manutenzione a {cliente}!", "success")
    except Exception as e:
        flash(f"Errore registrazione invio: {e}", "error")

    return redirect(url_for("gestisci_prodotto", qr_code=qr_code))


# --- RIENTRO DA MANUTENZIONE CON ESITO E CONTEGGIO ---
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
                    note_manutenzione = NULL
                WHERE qr_code = %s;
            """, (qta_rientro, esito, qr_code))

            cur.execute("""
                INSERT INTO storico_manutenzioni (nome_prodotto, qr_code, sap, cliente, quantita, data_riconsegna, note, esito)
                VALUES (%s, %s, %s, %s, %s, CURRENT_DATE, %s, %s);
            """, (prod['nome'], qr_code, prod['sap'], prod.get('cliente_manutenzione', 'Terzista'), qta_rientro, note_rientro, esito))

            cur.execute("""
                INSERT INTO notifiche (titolo, messaggio)
                VALUES (%s, %s);
            """, ("Rientro da Manutenzione", f"Articolo {prod['nome']} rientrato con esito: {esito}"))

            conn.commit()
            flash(f"✅ Articolo rientrato in magazzino! Esito registrato: {esito}", "success")
            
        cur.close()
        conn.close()
    except Exception as e:
        flash(f"Errore durante il rientro in magazzino: {e}", "error")
        
    return redirect(url_for("gestisci_prodotto", qr_code=qr_code))


# --- INTERVENTI OFFICINA INTERNA ---
@app.route("/richieste_manutenzione")
def richieste_manutenzione():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM richieste_manutenzione ORDER BY id DESC;")
    richieste = cur.fetchall()
    cur.close()
    conn.close()
    return render_template("richieste_manutenzione.html", richieste=richieste)

@app.route("/nuova_richiesta_manutenzione", methods=["POST"])
def nuova_richiesta_manutenzione():
    impianto = request.form.get("impianto_macchina", "").strip()
    titolo = request.form.get("titolo", "").strip()
    tipo_guasto = request.form.get("tipo_guasto", "Meccanico")
    priorita = request.form.get("priorita", "Media")
    assegnato_a = request.form.get("assegnato_a", "").strip()
    descrizione = request.form.get("descrizione", "").strip()
    creato_da = session.get("username", "Operatore Officina")

    if not titolo:
        flash("Il titolo dell'intervento è obbligatorio!", "error")
        return redirect(url_for("richieste_manutenzione"))

    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO richieste_manutenzione (impianto_macchina, titolo, tipo_guasto, priorita, assegnato_a, descrizione, creato_da, stato)
            VALUES (%s, %s, %s, %s, %s, %s, %s, 'Aperto');
        """, (impianto, titolo, tipo_guasto, priorita, assegnato_a, descrizione, creato_da))
        conn.commit()
        cur.close()
        conn.close()
        flash("Richiesta di intervento creata con successo!", "success")
    except Exception as e:
        flash(f"Errore creazione richiesta: {e}", "error")

    return redirect(url_for("richieste_manutenzione"))

@app.route("/stampa_intervento/<int:intervento_id>")
def stampa_intervento(intervento_id):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM richieste_manutenzione WHERE id = %s;", (intervento_id,))
    r = cur.fetchone()
    
    ricambi = []
    try:
        cur.execute("SELECT * FROM ricambi_intervento WHERE intervento_id = %s;", (intervento_id,))
        ricambi = cur.fetchall()
    except Exception:
        pass

    cur.close()
    conn.close()

    if not r:
        flash("Intervento non trovato.", "error")
        return redirect(url_for("richieste_manutenzione"))

    return render_template("stampa_intervento.html", r=r, ricambi=ricambi)


# --- STORICO MANUTENZIONI ESTERNE GLOBALE ---
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
    if not (session.get('is_admin') or session.get('puo_eliminare', True)):
        flash("Non hai i permessi amministrativi per eliminare dallo storico.", "error")
        return redirect(url_for("storico_manutenzioni"))

    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("DELETE FROM storico_manutenzioni WHERE id = %s;", (id,))
        conn.commit()
        cur.close()
        conn.close()
        flash("Voce eliminata dallo storico con successo.", "success")
    except Exception as e:
        flash(f"Errore eliminazione: {e}", "error")
    return redirect(url_for("storico_manutenzioni"))


# --- GESTIONE FORNITORI ---
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
        flash(f"Fornitore {nome_azienda} aggiunto!", "success")
    except Exception as e:
        flash(f"Errore salvataggio fornitore: {e}", "error")

    return redirect(url_for("index"))


# --- STAMPE E BOLLA ---
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


# --- ELIMINAZIONE PRODOTTO ---
@app.route("/elimina_prodotto", methods=["POST"])
def elimina_prodotto():
    if not (session.get('is_admin') or session.get('puo_eliminare', True)):
        flash("Non hai i permessi amministrativi per eliminare prodotti.", "error")
        return redirect(url_for("index"))

    qr_code = request.form.get("qr_code")
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("DELETE FROM prodotti WHERE qr_code = %s;", (qr_code,))
        conn.commit()
        cur.close()
        conn.close()
        flash("Articolo eliminato dal database.", "success")
    except Exception as e:
        flash(f"Errore eliminazione: {e}", "error")

    return redirect(url_for("index"))


# --- API NOTIFICHE COMPLETE ---
@app.route("/api/notifiche")
def api_notifiche():
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT * FROM notifiche WHERE letta = FALSE ORDER BY creata_il DESC;")
        notifiche = cur.fetchall()
        cur.close()
        conn.close()
        return jsonify(notifiche)
    except Exception:
        return jsonify([])

@app.route("/api/notifiche/segna_lette", methods=["POST"])
def api_segna_lette():
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("UPDATE notifiche SET letta = TRUE WHERE letta = FALSE;")
        conn.commit()
        cur.close()
        conn.close()
        return jsonify({"status": "ok"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


if _name_ == "_main_":
    app.run(debug=True, host="0.0.0.0", port=5000)
