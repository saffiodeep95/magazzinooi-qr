from flask import Flask, render_template, request, redirect, url_for, flash
from flask_login import LoginManager, UserMixin, login_required, current_user, login_user, logout_user
import sqlite3
import os

app = Flask(__name__)
app.secret_key = 'chiave_segreta_magazzino'

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

DATABASE = 'magazzino.db'

def get_db_connection():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    
    # Tabella Utenti (aggiunto flag o permesso specifico per i pesanti, es. puo_vedere_pesanti)
    conn.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'user',
            puo_vedere_pesanti INTEGER NOT NULL DEFAULT 0
        )
    ''')
    
    # Tabella Magazzino Standard e Pesante (con campo peso e flag is_pesante)
    conn.execute('''
        CREATE TABLE IF NOT EXISTS rulli (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            codice_articolo TEXT UNIQUE NOT NULL,
            descrizione TEXT NOT NULL,
            giacenza INTEGER NOT NULL DEFAULT 0,
            soglia_minima INTEGER NOT NULL DEFAULT 0,
            is_pesante INTEGER NOT NULL DEFAULT 0,
            peso REAL DEFAULT 0.0
        )
    ''')
    
    # Tabella Manutenzioni
    conn.execute('''
        CREATE TABLE IF NOT EXISTS manutenzioni (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            macchinario TEXT NOT NULL,
            descrizione TEXT NOT NULL,
            articolo_id INTEGER,
            quantita_usata INTEGER,
            utente_id INTEGER,
            data TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (articolo_id) REFERENCES rulli (id),
            FOREIGN KEY (utente_id) REFERENCES users (id)
        )
    ''')
    
    # Assicura che l'admin esista e abbia accesso completo ai pesanti
    conn.execute('''
        INSERT INTO users (id, username, password, role, puo_vedere_pesanti) 
        VALUES (1, 'admin', 'admin123', 'admin', 1)
        ON CONFLICT(id) DO UPDATE SET username='admin', password='admin123', role='admin', puo_vedere_pesanti=1
    ''')
    
    conn.commit()
    conn.close()

class User(UserMixin):
    def _init_(self, id, username, role, puo_vedere_pesanti):
        self.id = id
        self.username = username
        self.role = role
        self.puo_vedere_pesanti = puo_vedere_pesanti

@login_manager.user_loader
def load_user(user_id):
    conn = get_db_connection()
    user = conn.execute('SELECT * FROM users WHERE id = ?', (user_id,)).fetchone()
    conn.close()
    if user:
        return User(user['id'], user['username'], user['role'], user['puo_vedere_pesanti'])
    return None

@app.route('/')
@login_required
def index():
    return render_template('index.html')

# --- GESTIONE UTENTI E CONCESSIONI (Admin) ---
@app.route('/users', methods=['GET', 'POST'])
@login_required
def manage_users():
    if current_user.role != 'admin':
        flash("Accesso negato: sezione riservata agli amministratori.", "danger")
        return redirect(url_for('index'))
    
    conn = get_db_connection()
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        role = request.form['role']
        puo_vedere_pesanti = 1 if 'puo_vedere_pesanti' in request.form else 0
        try:
            conn.execute('''
                INSERT INTO users (username, password, role, puo_vedere_pesanti) 
                VALUES (?, ?, ?, ?)
            ''', (username, password, role, puo_vedere_pesanti))
            conn.commit()
            flash("Utente e permessi aggiornati con successo!", "success")
        except sqlite3.IntegrityError:
            flash("Nome utente già esistente.", "danger")
        return redirect(url_for('manage_users'))
        
    users = conn.execute('SELECT * FROM users').fetchall()
    conn.close()
    return render_template('users.html', users=users)

@app.route('/users/delete/<int:id>', methods=['POST'])
@login_required
def delete_user(id):
    if current_user.role != 'admin':
        flash("Accesso negato.", "danger")
        return redirect(url_for('index'))
    
    conn = get_db_connection()
    conn.execute('DELETE FROM users WHERE id = ?', (id,))
    conn.commit()
    conn.close()
    flash("Utente eliminato.", "success")
    return redirect(url_for('manage_users'))

# --- GESTIONE MAGAZZINO STANDARD E SEZIONE PESANTE (Rulli, Riduttori, Motori con Peso) ---
@app.route('/rulli', methods=['GET', 'POST'])
@login_required
def gestione_rulli():
    conn = get_db_connection()
    if request.method == 'POST':
        codice_articolo = request.form['codice_articolo']
        descrizione = request.form['descrizione']
        giacenza = int(request.form['giacenza'])
        soglia_minima = int(request.form['soglia_minima'])
        is_pesante = 1 if 'is_pesante' in request.form else 0
        
        # Se prova ad aggiungere un articolo pesante senza averne i permessi (e non è admin)
        if is_pesante == 1 and current_user.role != 'admin' and current_user.puo_vedere_pesanti == 0:
            flash("Non hai i permessi per aggiungere componenti nella sezione pesante.", "danger")
            return redirect(url_for('gestione_rulli'))

        peso = float(request.form.get('peso', 0.0)) if is_pesante == 1 else 0.0
        
        try:
            conn.execute('''
                INSERT INTO rulli (codice_articolo, descrizione, giacenza, soglia_minima, is_pesante, peso)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (codice_articolo, descrizione, giacenza, soglia_minima, is_pesante, peso))
            conn.commit()
            flash("Articolo inserito correttamente.", "success")
        except sqlite3.IntegrityError:
            flash("Codice articolo già esistente.", "danger")
        return redirect(url_for('gestione_rulli'))
        
    rulli = conn.execute('SELECT * FROM rulli WHERE is_pesante = 0').fetchall()
    
    # Protezione visualizzazione sezione pesante in base alle concessioni dell'utente
    pesanti = []
    if current_user.role == 'admin' or current_user.puo_vedere_pesanti == 1:
        pesanti = conn.execute('SELECT * FROM rulli WHERE is_pesante = 1').fetchall()
        
    conn.close()
    return render_template('rulli.html', rulli=rulli, pesanti=pesanti, puo_vedere_pesanti=(current_user.role == 'admin' or current_user.puo_vedere_pesanti == 1))

# --- REGISTRO MANUTENZIONI (Invariato e integrato con QR code / scansione) ---
@app.route('/manutenzioni', methods=['GET', 'POST'])
@login_required
def manutenzioni():
    conn = get_db_connection()
    if request.method == 'POST':
        macchinario = request.form['macchinario']
        descrizione = request.form['descrizione']
        articolo_id = request.form.get('articolo_id')
        quantita = int(request.form.get('quantita', 0))
        
        conn.execute('''
            INSERT INTO manutenzioni (macchinario, descrizione, articolo_id, quantita_usata, utente_id)
            VALUES (?, ?, ?, ?, ?)
        ''', (macchinario, descrizione, articolo_id if articolo_id else None, quantita if articolo_id else 0, current_user.id))
        
        if articolo_id and quantita > 0:
            conn.execute('''
                UPDATE rulli 
                SET giacenza = giacenza - ? 
                WHERE id = ?
            ''', (quantita, articolo_id))
            
        conn.commit()
        conn.close()
        flash("Intervento di manutenzione registrato.", "success")
        return redirect(url_for('manutenzioni'))
        
    storico = conn.execute('''
        SELECT m.*, r.descrizione as rullo_nome, u.username 
        FROM manutenzioni m 
        LEFT JOIN rulli r ON m.articolo_id = r.id 
        LEFT JOIN users u ON m.utente_id = u.id 
        ORDER BY m.data DESC
    ''').fetchall()
    
    # Mostra nel select dei ricambi solo quelli accessibili all'utente
    if current_user.role == 'admin' or current_user.puo_vedere_pesanti == 1:
        rulli_totali = conn.execute('SELECT * FROM rulli').fetchall()
    else:
        rulli_totali = conn.execute('SELECT * FROM rulli WHERE is_pesante = 0').fetchall()
        
    conn.close()
    return render_template('manutenzioni.html', storico=storico, rulli=rulli_totali)

# --- LOGIN / LOGOUT ---
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        conn = get_db_connection()
        user_data = conn.execute('SELECT * FROM users WHERE username = ? AND password = ?', (username, password)).fetchone()
        conn.close()
        
        if user_data:
            user = User(user_data['id'], user_data['username'], user_data['role'], user_data['puo_vedere_pesanti'])
            login_user(user)
            return redirect(url_for('index'))
        flash("Credenziali non valide.", "danger")
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

if __name__ == '_main_':
    init_db()
    app.run(debug=True)
