import sqlite3
from flask import Flask, render_template, request, redirect, url_for, session, flash

app = Flask(__name__)
app.secret_key = 'tua_chiave_segreta_molto_sicura'

def get_db_connection():
    conn = sqlite3.connect('magazzino.db')
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Tabella prodotti (con peso e is_pesante per i motori/riduttori/nastri)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS prodotti (
            qr_code TEXT PRIMARY KEY,
            nome TEXT NOT NULL,
            sap TEXT,
            peso TEXT,
            quantita INTEGER DEFAULT 0,
            posizione TEXT,
            is_pesante INTEGER DEFAULT 0,
            in_manutenzione INTEGER DEFAULT 0,
            cliente_manutenzione TEXT,
            quantita_manutenzione INTEGER DEFAULT 0,
            data_spedizione TEXT,
            data_riconsegna TEXT,
            vettore TEXT,
            ordine_amministrativo INTEGER DEFAULT 0,
            note_manutenzione TEXT
        )
    ''')
    
    # Tabella utenti (con permessi granulari)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS utenti (
            username TEXT PRIMARY KEY,
            password TEXT NOT NULL,
            is_admin INTEGER DEFAULT 0,
            puo_vedere_manutenzione INTEGER DEFAULT 0,
            puo_eliminare INTEGER DEFAULT 0,
            puo_vedere_pesanti INTEGER DEFAULT 0
        )
    ''')

    # Tabella clienti / rubrica
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS clienti (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome_azienda TEXT NOT NULL,
            referente TEXT,
            telefono TEXT,
            email TEXT
        )
    ''')
    
    # Aggiornamenti sicuri delle colonne se il DB esiste già
    cursor.execute("PRAGMA table_info(utenti)")
    colonne_utenti = [col[1] for col in cursor.fetchall()]
    if 'puo_vedere_pesanti' not in colonne_utenti:
        cursor.execute('ALTER TABLE utenti ADD COLUMN puo_vedere_pesanti INTEGER DEFAULT 0')

    cursor.execute("PRAGMA table_info(prodotti)")
    colonne_prodotti = [col[1] for col in cursor.fetchall()]
    if 'is_pesante' not in colonne_prodotti:
        cursor.execute('ALTER TABLE prodotti ADD COLUMN is_pesante INTEGER DEFAULT 0')
    if 'peso' not in colonne_prodotti:
        cursor.execute('ALTER TABLE prodotti ADD COLUMN peso TEXT')

    # Admin di default
    cursor.execute('SELECT * FROM utenti WHERE username = "admin"')
    if not cursor.fetchone():
        cursor.execute('''
            INSERT INTO utenti (username, password, is_admin, puo_vedere_manutenzione, puo_eliminare, puo_vedere_pesanti)
            VALUES ("admin", "admin123", 1, 1, 1, 1)
        ''')
        
    conn.commit()
    conn.close()

init_db()

# --- AUTENTICAZIONE & REGISTRAZIONE ---

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        conn = get_db_connection()
        user = conn.execute('SELECT * FROM utenti WHERE username = ? AND password = ?', (username, password)).fetchone()
        conn.close()
        
        if user:
            session['username'] = user['username']
            session['is_admin'] = user['is_admin']
            session['puo_vedere_manutenzione'] = user['puo_vedere_manutenzione']
            session['puo_eliminare'] = user['puo_eliminare']
            session['puo_vedere_pesanti'] = user['puo_vedere_pesanti']
            return redirect(url_for('index'))
        else:
            flash('Credenziali non valide.', 'error')
            
    return render_template('login.html')

@app.route('/registra', methods=['GET', 'POST'])
def registra():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        conn = get_db_connection()
        try:
            conn.execute('''
                INSERT INTO utenti (username, password, is_admin, puo_vedere_manutenzione, puo_eliminare, puo_vedere_pesanti)
                VALUES (?, ?, 0, 0, 0, 0)
            ''', (username, password))
            conn.commit()
            flash('Registrazione completata! Ora puoi effettuare il login.', 'success')
            conn.close()
            return redirect(url_for('login'))
        except sqlite3.IntegrityError:
            flash('Nome utente già esistente.', 'error')
            conn.close()
            
    return render_template('registra.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

# --- HOME E SEZIONE MOTORI/RIDUTTORI ---

@app.route('/')
def index():
    if 'username' not in session:
        return redirect(url_for('login'))
    conn = get_db_connection()
    prodotti = conn.execute('SELECT * FROM prodotti WHERE is_pesante = 0 OR is_pesante IS NULL').fetchall()
    conn.close()
    return render_template('index.html', prodotti=prodotti)

@app.route('/motori_riduttori')
def sezione_pesanti():
    if 'username' not in session:
        return redirect(url_for('login'))
    
    if not session.get('is_admin') and not session.get('puo_vedere_pesanti'):
        flash('Accesso non autorizzato alla sezione motori e riduttori.', 'error')
        return redirect(url_for('index'))
        
    conn = get_db_connection()
    prodotti = conn.execute('SELECT * FROM prodotti WHERE is_pesante = 1').fetchall()
    conn.close()
    return render_template('sezione_pesanti.html', prodotti=prodotti)

# --- GESTIONE PRODOTTI ---

@app.route('/aggiungi', methods=['POST'])
def aggiungi_prodotto():
    if 'username' not in session:
        return redirect(url_for('login'))
    
    qr_code = request.form.get('qr_code')
    nome = request.form.get('nome')
    sap = request.form.get('sap', '')
    peso = request.form.get('peso', '')
    quantita = int(request.form.get('quantita', 0))
    posizione = request.form.get('posizione', '')
    is_pesante = int(request.form.get('is_pesante', 0))

    conn = get_db_connection()
    try:
        conn.execute('''
            INSERT INTO prodotti (qr_code, nome, sap, peso, quantita, posizione, is_pesante)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (qr_code, nome, sap, peso, quantita, posizione, is_pesante))
        conn.commit()
        flash('Articolo aggiunto con successo!', 'success')
    except sqlite3.IntegrityError:
        flash('Errore: Un articolo con questo QR code esiste già.', 'error')
    finally:
        conn.close()

    if is_pesante:
        return redirect(url_for('sezione_pesanti'))
    return redirect(url_for('index'))

@app.route('/gestisci/<qr_code>')
def gestisci_prodotto(qr_code):
    if 'username' not in session:
        return redirect(url_for('login'))
    conn = get_db_connection()
    prodotto = conn.execute('SELECT * FROM prodotti WHERE qr_code = ?', (qr_code,)).fetchone()
    clienti = conn.execute('SELECT * FROM clienti').fetchall()
    conn.close()
    if not prodotto:
        flash('Articolo non trovato.', 'error')
        return redirect(url_for('index'))
    return render_template('gestisci.html', prodotto=prodotto, clienti=clienti)

@app.route('/elimina', methods=['POST'])
def elimina_prodotto():
    if 'username' not in session:
        return redirect(url_for('login'))
    if not session.get('is_admin') and not session.get('puo_eliminare'):
        flash('Non hai i permessi per eliminare gli articoli.', 'error')
        return redirect(url_for('index'))
        
    qr_code = request.form.get('qr_code')
    conn = get_db_connection()
    conn.execute('DELETE FROM prodotti WHERE qr_code = ?', (qr_code,))
    conn.commit()
    conn.close()
    flash('Articolo eliminato con successo.', 'success')
    return redirect(url_for('index'))

# --- CARICO, SCARICO E STAMPA ---

@app.route('/carico', methods=['GET', 'POST'])
def carico():
    if 'username' not in session:
        return redirect(url_for('login'))
    if request.method == 'POST':
        qr_code = request.form.get('qr_code')
        quantita = int(request.form.get('quantita', 1))
        conn = get_db_connection()
        conn.execute('UPDATE prodotti SET quantita = quantita + ? WHERE qr_code = ?', (quantita, qr_code))
        conn.commit()
        conn.close()
        flash('Carico registrato con successo!', 'success')
        return redirect(url_for('carico'))
    return render_template('carico.html')

@app.route('/scarico', methods=['GET', 'POST'])
def scarico():
    if 'username' not in session:
        return redirect(url_for('login'))
    if request.method == 'POST':
        qr_code = request.form.get('qr_code')
        quantita = int(request.form.get('quantita', 1))
        conn = get_db_connection()
        p = conn.execute('SELECT * FROM prodotti WHERE qr_code = ?', (qr_code,)).fetchone()
        if p and p['quantita'] >= quantita:
            conn.execute('UPDATE prodotti SET quantita = quantita - ? WHERE qr_code = ?', (quantita, qr_code))
            conn.commit()
            flash('Scarico registrato con successo!', 'success')
        else:
            flash('Quantità insufficiente in magazzino.', 'error')
        conn.close()
        return redirect(url_for('scarico'))
    return render_template('scarico.html')

@app.route('/stampa_tutti_qr')
def stampa_tutti_qr():
    if 'username' not in session:
        return redirect(url_for('login'))
    conn = get_db_connection()
    prodotti = conn.execute('SELECT * FROM prodotti').fetchall()
    conn.close()
    return render_template('stampa_tutti_qr.html', prodotti=prodotti)

@app.route('/upload', methods=['GET', 'POST'])
def pagina_upload():
    if 'username' not in session:
        return redirect(url_for('login'))
    if request.method == 'POST':
        flash('File caricato correttamente.', 'success')
        return redirect(url_for('index'))
    return render_template('upload.html')

# --- MANUTENZIONE, STORICO E BOLLA ---

@app.route('/manda_manutenzione/<qr_code>', methods=['POST'])
def manda_manutenzione(qr_code):
    if 'username' not in session:
        return redirect(url_for('login'))
    if not session.get('is_admin') and not session.get('puo_vedere_manutenzione'):
        flash('Non hai i permessi per gestire le manutenzioni.', 'error')
        return redirect(url_for('gestisci_prodotto', qr_code=qr_code))
        
    cliente = request.form.get('cliente_manutenzione')
    q_manutenzione = int(request.form.get('quantita_manutenzione', 1))
    data_spedizione = request.form.get('data_spedizione')
    data_riconsegna = request.form.get('data_riconsegna')
    vettore = request.form.get('vettore')
    ordine_amministrativo = 1 if request.form.get('ordine_amministrativo') else 0
    note = request.form.get('note_manutenzione')

    conn = get_db_connection()
    p = conn.execute('SELECT * FROM prodotti WHERE qr_code = ?', (qr_code,)).fetchone()
    
    if p and p['quantita'] >= q_manutenzione:
        nuova_q_disp = p['quantita'] - q_manutenzione
        conn.execute('''
            UPDATE prodotti SET 
                quantita = ?, 
                in_manutenzione = 1, 
                cliente_manutenzione = ?, 
                quantita_manutenzione = ?, 
                data_spedizione = ?, 
                data_riconsegna = ?, 
                vettore = ?, 
                ordine_amministrativo = ?, 
                note_manutenzione = ? 
            WHERE qr_code = ?
        ''', (nuova_q_disp, cliente, q_manutenzione, data_spedizione, data_riconsegna, vettore, ordine_amministrativo, note, qr_code))
        conn.commit()
        flash('Articolo inviato in manutenzione con successo!', 'success')
    else:
        flash('Quantità disponibile in magazzino insufficiente.', 'error')
        
    conn.close()
    return redirect(url_for('gestisci_prodotto', qr_code=qr_code))

@app.route('/ripristina_magazzino/<qr_code>', methods=['POST'])
def ripristina_magazzino(qr_code):
    if 'username' not in session:
        return redirect(url_for('login'))
    
    conn = get_db_connection()
    p = conn.execute('SELECT * FROM prodotti WHERE qr_code = ?', (qr_code,)).fetchone()
    if p and p['in_manutenzione']:
        reintegro = p['quantita_manutenzione']
        conn.execute('''
            UPDATE prodotti SET 
                quantita = quantita + ?, 
                in_manutenzione = 0, 
                cliente_manutenzione = NULL, 
                quantita_manutenzione = 0, 
                data_spedizione = NULL, 
                data_riconsegna = NULL, 
                vettore = NULL, 
                ordine_amministrativo = 0, 
                note_manutenzione = NULL 
            WHERE qr_code = ?
        ''', (reintegro, qr_code))
        conn.commit()
        flash('Articolo rientrato in magazzino!', 'success')
    conn.close()
    return redirect(url_for('gestisci_prodotto', qr_code=qr_code))

@app.route('/lista_manutenzioni')
def lista_manutenzioni():
    if 'username' not in session:
        return redirect(url_for('login'))
    conn = get_db_connection()
    prodotti = conn.execute('SELECT * FROM prodotti WHERE in_manutenzione = 1').fetchall()
    conn.close()
    return render_template('lista_manutenzioni.html', prodotti=prodotti)

@app.route('/manutenzioni')
def manutenzioni():
    if 'username' not in session:
        return redirect(url_for('login'))
    conn = get_db_connection()
    prodotti = conn.execute('SELECT * FROM prodotti WHERE in_manutenzione = 1').fetchall()
    conn.close()
    return render_template('manutenzioni.html', prodotti=prodotti)

@app.route('/storico_manutenzioni')
def storico_manutenzioni():
    if 'username' not in session:
        return redirect(url_for('login'))
    conn = get_db_connection()
    prodotti = conn.execute('SELECT * FROM prodotti').fetchall()
    conn.close()
    return render_template('storico_manutenzioni.html', prodotti=prodotti)

@app.route('/stampa_bolla/<qr_code>')
def stampa_bolla(qr_code):
    if 'username' not in session:
        return redirect(url_for('login'))
    conn = get_db_connection()
    prodotto = conn.execute('SELECT * FROM prodotti WHERE qr_code = ?', (qr_code,)).fetchone()
    conn.close()
    if not prodotto:
        flash('Articolo non trovato.', 'error')
        return redirect(url_for('index'))
    return render_template('stampa_bolla.html', prodotto=prodotto)

@app.route('/bolla/<qr_code>')
def bolla(qr_code):
    if 'username' not in session:
        return redirect(url_for('login'))
    conn = get_db_connection()
    prodotto = conn.execute('SELECT * FROM prodotti WHERE qr_code = ?', (qr_code,)).fetchone()
    conn.close()
    if not prodotto:
        flash('Articolo non trovato.', 'error')
        return redirect(url_for('index'))
    return render_template('bolla.html', prodotto=prodotto)

# --- RUBRICA CLIENTI E ADMIN UTENTI ---

@app.route('/clienti', methods=['GET', 'POST'])
def clienti():
    if 'username' not in session:
        return redirect(url_for('login'))
    conn = get_db_connection()
    if request.method == 'POST':
        nome_azienda = request.form.get('nome_azienda')
        referente = request.form.get('referente')
        telefono = request.form.get('telefono')
        email = request.form.get('email')
        conn.execute('INSERT INTO clienti (nome_azienda, referente, telefono, email) VALUES (?, ?, ?, ?)',
                     (nome_azienda, referente, telefono, email))
        conn.commit()
        flash('Cliente aggiunto alla rubrica!', 'success')
    clienti_list = conn.execute('SELECT * FROM clienti').fetchall()
    conn.close()
    return render_template('clienti.html', clienti=clienti_list)

@app.route('/lista_clienti')
def lista_clienti():
    if 'username' not in session:
        return redirect(url_for('login'))
    conn = get_db_connection()
    clienti_list = conn.execute('SELECT * FROM clienti').fetchall()
    conn.close()
    return render_template('lista_clienti.html', clienti=clienti_list)

@app.route('/admin/utenti', methods=['GET', 'POST'])
def admin_utenti():
    if 'username' not in session or not session.get('is_admin'):
        return redirect(url_for('index'))
    
    conn = get_db_connection()
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        puo_vedere_manutenzione = 1 if request.form.get('puo_vedere_manutenzione') else 0
        puo_eliminare = 1 if request.form.get('puo_eliminare') else 0
        puo_vedere_pesanti = 1 if request.form.get('puo_vedere_pesanti') else 0
        
        try:
            conn.execute('''
                INSERT INTO utenti (username, password, puo_vedere_manutenzione, puo_eliminare, puo_vedere_pesanti)
                VALUES (?, ?, ?, ?, ?)
            ''', (username, password, puo_vedere_manutenzione, puo_eliminare, puo_vedere_pesanti))
            conn.commit()
            flash('Utente creato con successo!', 'success')
        except sqlite3.IntegrityError:
            flash('Nome utente già esistente.', 'error')

    utenti = conn.execute('SELECT * FROM utenti').fetchall()
    conn.close()
    return render_template('admin_utenti.html', utenti=utenti)

if __name__ == '_main_':
    app.run(debug=True)
