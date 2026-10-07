import os
import io
import base64
import qrcode
import psycopg2
from psycopg2.extras import RealDictCursor
from flask import Flask, render_template, request, redirect, url_for, flash

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "chiave-segreta-magazzino")

DATABASE_URL = os.environ.get("DATABASE_URL")

def get_db_connection():
    if not DATABASE_URL:
        print("DATABASE_URL non impostata!")
        return None
    try:
        conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
        return conn
    except Exception as e:
        print(f"Errore di connessione al database: {e}")
        return None

def init_db():
    conn = get_db_connection()
    if conn:
        try:
            cur = conn.cursor()
            # Crea la tabella se non esiste
            cur.execute("""
                CREATE TABLE IF NOT EXISTS prodotti (
                    id SERIAL PRIMARY KEY,
                    qr_code VARCHAR(255) UNIQUE NOT NULL,
                    nome VARCHAR(255) NOT NULL,
                    quantita INT DEFAULT 0,
                    posizione VARCHAR(255)
                );
            """)
            # Aggiunge la colonna foto se manca nei database esistenti
            cur.execute("""
                ALTER TABLE prodotti ADD COLUMN IF NOT EXISTS foto TEXT;
            """)
            conn.commit()
            cur.close()
            conn.close()
            print("Inizializzazione e aggiornamento database completati con successo.")
        except Exception as e:
            print(f"Errore durante l'inizializzazione del database: {e}")

init_db()

def genera_qr_base64(testo):
    qr = qrcode.QRCode(version=1, box_size=5, border=2)
    qr.add_data(testo)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buffered = io.BytesIO()
    img.save(buffered, format="PNG")
    return base64.b64encode(buffered.getvalue()).decode("utf-8")

@app.route('/')
def index():
    search_query = request.args.get('q', '').strip()
    conn = get_db_connection()
    if not conn:
        return render_template("index.html", prodotti=[], search_query=search_query)
    try:
        cur = conn.cursor()
        if search_query:
            cur.execute("""
                SELECT id, qr_code, nome, quantita, posizione, foto 
                FROM prodotti 
                WHERE qr_code ILIKE %s OR nome ILIKE %s 
                ORDER BY nome ASC;
            """, (f"%{search_query}%", f"%{search_query}%"))
        else:
            cur.execute("SELECT id, qr_code, nome, quantita, posizione, foto FROM prodotti ORDER BY nome ASC;")
        
        prodotti_db = cur.fetchall()
        cur.close()
        conn.close()
        
        prodotti = []
        for p in prodotti_db:
            p_dict = dict(p)
            url_azione = url_for('gestisci_prodotto', qr_code=p['qr_code'], _external=True)
            p_dict['qr_img'] = genera_qr_base64(url_azione)
            prodotti.append(p_dict)

        return render_template("index.html", prodotti=prodotti, search_query=search_query)
    except Exception as e:
        print(f"Errore nella rotta index: {e}")
        return render_template("index.html", prodotti=[], search_query=search_query)

@app.route('/gestisci/<qr_code>')
def gestisci_prodotto(qr_code):
    conn = get_db_connection()
    if not conn:
        flash("Errore di connessione al database", "error")
        return redirect(url_for('index'))
    try:
        cur = conn.cursor()
        cur.execute("SELECT id, qr_code, nome, quantita, posizione, foto FROM prodotti WHERE qr_code = %s;", (qr_code,))
        prodotto = cur.fetchone()
        cur.close()
        conn.close()
        if not prodotto:
            flash("Prodotto non trovato nel sistema!", "error")
            return redirect(url_for('index'))
        
        prodotto_dict = dict(prodotto)
        url_azione = url_for('gestisci_prodotto', qr_code=qr_code, _external=True)
        prodotto_dict['qr_img'] = genera_qr_base64(url_azione)

        return render_template("gestisci.html", prodotto=prodotto_dict)
    except Exception as e:
        flash(f"Errore: {e}", "error")
        return redirect(url_for('index'))

@app.route('/aggiungi', methods=['POST'])
def aggiungi
