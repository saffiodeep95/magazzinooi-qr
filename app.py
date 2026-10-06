import os
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
            cur.execute("""
                CREATE TABLE IF NOT EXISTS prodotti (
                    id SERIAL PRIMARY KEY,
                    qr_code VARCHAR(255) UNIQUE NOT NULL,
                    nome VARCHAR(255) NOT NULL,
                    quantita INT DEFAULT 0,
                    posizione VARCHAR(255)
                );
            """)
            conn.commit()
            cur.close()
            conn.close()
            print("Inizializzazione tabella prodotti completata con successo.")
        except Exception as e:
            print(f"Errore durante l'inizializzazione del database: {e}")

# Inizializza il database all'avvio
init_db()

@app.route('/')
def index():
    conn = get_db_connection()
    if not conn:
        return render_template("index.html", prodotti=[])
    try:
        cur = conn.cursor()
        cur.execute("SELECT id, qr_code, nome, quantita, posizione FROM prodotti ORDER BY nome ASC;")
        prodotti = cur.fetchall()
        cur.close()
        conn.close()
        return render_template("index.html", prodotti=prodotti if prodotti else [])
    except Exception as e:
        print(f"Errore nella rotta index: {e}")
        return render_template("index.html", prodotti=[])

@app.route('/gestisci/<qr_code>')
def gestisci_prodotto(qr_code):
    conn = get_db_connection()
    if not conn:
        flash("Errore di connessione al database", "error")
        return redirect(url_for('index'))
    try:
        cur = conn.cursor()
        cur.execute("SELECT id, qr_code, nome, quantita, posizione FROM prodotti WHERE qr_code = %s;", (qr_code,))
        prodotto = cur.fetchone()
        cur.close()
        conn.close()
        if not prodotto:
            flash("Prodotto non trovato nel sistema!", "error")
            return redirect(url_for('index'))
        return render_template("gestisci.html", prodotto=prodotto)
    except Exception as e:
        flash(f"Errore: {e}", "error")
        return redirect(url_for('index'))

@app.route('/aggiungi', methods=['POST'])
def aggiungi_prodotto():
    qr_code = request.form.get('qr_code')
    nome = request.form.get('nome')
    try:
        quantita = int(request.form.get('quantita', 0))
    except ValueError:
        quantita = 0
    posizione = request.form.get('posizione', '')

    if not qr_code or not nome:
        flash("QR Code e Nome sono obbligatori!", "error")
        return redirect(url_for('index'))

    conn = get_db_connection()
    if not conn:
        flash("Errore di connessione al database", "error")
        return redirect(url_for('index'))
    try:
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO prodotti (qr_code, nome, quantita, posizione)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (qr_code) DO UPDATE SET
                nome = EXCLUDED.nome,
                posizione = EXCLUDED.posizione;
        """, (qr_code, nome, quantita, posizione))
        conn.commit()
        cur.close()
        conn.close()
        flash("Prodotto aggiunto o aggiornato con successo!", "success")
    except Exception as e:
        flash(f"Errore nell'inserimento: {e}", "error")
    return redirect(url_for('index'))

@app.route('/carico', methods=['GET', 'POST'])
def carico():
    if request.method == 'POST':
        qr_code = request.form.get('qr_code')
        try:
            quantita = int(request.form.get('quantita', 1))
        except ValueError:
            quantita = 1
    else:
        qr_code = request.args.get('qr_code')
        try:
            quantita = int(request.args.get('quantita', 1))
        except ValueError:
            quantita = 1

    if not qr_code:
        flash("QR Code non valido o mancante!", "error")
        return redirect(url_for('index'))

    conn = get_db_connection()
    if not conn:
        flash("Errore di connessione al database", "error")
        return redirect(url_for('index'))
    try:
        cur = conn.cursor()
        cur.execute("UPDATE prodotti SET quantita = quantita + %s WHERE qr_code = %s;", (quantita, qr_code))
        if cur.rowcount == 0:
            flash("Prodotto non trovato!", "error")
        else:
            conn.commit()
            flash(f"Carico di {quantita} pz effettuato con successo!", "success")
        cur.close()
        conn.close()
    except Exception as e:
        flash(f"Errore durante il carico: {e}", "error")
    
    return redirect(url_for('gestisci_prodotto', qr_code=qr_code))

@app.route('/scarico', methods=['GET', 'POST'])
def scarico():
    if request.method == 'POST':
        qr_code = request.form.get('qr_code')
        try:
            quantita = int(request.form.get('quantita', 1))
        except ValueError:
            quantita = 1
    else:
        qr_code = request.args.get('qr_code')
        try:
            quantita = int(request.args.get('quantita', 1))
        except ValueError:
            quantita = 1

    if not qr_code:
        flash("QR Code non valido o mancante!", "error")
        return redirect(url_for('index'))

    conn = get_db_connection()
    if not conn:
        flash("Errore di connessione al database", "error")
        return redirect(url_for('index'))
    try:
        cur = conn.cursor()
        cur.execute("UPDATE prodotti SET quantita = GREATEST(0, quantita - %s) WHERE qr_code = %s;", (quantita, qr_code))
        if cur.rowcount == 0:
            flash("Prodotto non trovato!", "error")
        else:
            conn.commit()
            flash(f"Scarico di {quantita} pz effettuato con successo!", "success")
        cur.close()
        conn.close()
    except Exception as e:
        flash(f"Errore durante lo scarico: {e}", "error")

    return redirect(url_for('gestisci_prodotto', qr_code=qr_code))

if _name_ == '_main_':
    app.run(host='0.0.0.0', port=5000, debug=True)
