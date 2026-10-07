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
            cur.execute("""
                CREATE TABLE IF NOT EXISTS prodotti (
                    id SERIAL PRIMARY KEY,
                    qr_code VARCHAR(255) UNIQUE NOT NULL,
                    nome VARCHAR(255) NOT NULL,
                    quantita INT DEFAULT 0,
                    posizione VARCHAR(255),
                    foto TEXT
                );
            """)
            conn.commit()
            cur.close()
            conn.close()
            print("Inizializzazione database completata con successo.")
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
def aggiungi_prodotto():
    qr_code = request.form.get('qr_code')
    nome = request.form.get('nome')
    try:
        quantita = int(request.form.get('quantita', 0))
    except ValueError:
        quantita = 0
    posizione = request.form.get('posizione', '')

    foto_file = request.files.get('foto')
    foto_base64 = None
    if foto_file and foto_file.filename != '':
        foto_bytes = foto_file.read()
        foto_base64 = base64.b64encode(foto_bytes).decode('utf-8')

    if not qr_code or not nome:
        flash("QR Code e Nome sono obbligatori!", "error")
        return redirect(url_for('index'))

    conn = get_db_connection()
    if not conn:
        flash("Errore di connessione al database", "error")
        return redirect(url_for('index'))
    try:
        cur = conn.cursor()
        if foto_base64:
            cur.execute("""
                INSERT INTO prodotti (qr_code, nome, quantita, posizione, foto)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (qr_code) DO UPDATE SET
                    nome = EXCLUDED.nome,
                    quantita = EXCLUDED.quantita,
                    posizione = EXCLUDED.posizione,
                    foto = EXCLUDED.foto;
            """, (qr_code, nome, quantita, posizione, foto_base64))
        else:
            cur.execute("""
                INSERT INTO prodotti (qr_code, nome, quantita, posizione)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (qr_code) DO UPDATE SET
                    nome = EXCLUDED.nome,
                    quantita = EXCLUDED.quantita,
                    posizione = EXCLUDED.posizione;
            """, (qr_code, nome, quantita, posizione))
            
        conn.commit()
        cur.close()
        conn.close()
        flash("Prodotto aggiunto o aggiornato con successo!", "success")
    except Exception as e:
        flash(f"Errore nell'inserimento: {e}", "error")
    return redirect(url_for('index'))

@app.route('/cancella/<qr_code>', methods=['POST'])
def cancella_prodotto(qr_code):
    conn = get_db_connection()
    if not conn:
        flash("Errore di connessione al database", "error")
        return redirect(url_for('index'))
    try:
        cur = conn.cursor()
        cur.execute("DELETE FROM prodotti WHERE qr_code = %s;", (qr_code,))
        conn.commit()
        cur.close()
        conn.close()
        flash("Prodotto eliminato con successo!", "success")
    except Exception as e:
        flash(f"Errore durante l'eliminazione: {e}", "error")
    return redirect(url_for('index'))

@app.route('/carico', methods=['POST'])
def carico():
    qr_code = request.form.get('qr_code')
    try:
        quantita = int(request.form.get('quantita', 1))
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

@app.route('/scarico', methods=['POST'])
def scarico():
    qr_code = request.form.get('qr_code')
    try:
        quantita = int(request.form.get('quantita', 1))
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

if __name__ == '_main_':
    app.run(host='0.0.0.0', port=5000, debug=True)
