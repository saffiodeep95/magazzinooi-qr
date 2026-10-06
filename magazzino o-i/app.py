import os
import psycopg2
from psycopg2.extras import RealDictCursor
from flask import Flask, render_template, request, redirect, url_for, flash

app = Flask(_name_)
app.secret_key = os.environ.get("SECRET_KEY", "chiave-segreta-magazzino")

# Recupera l'URL del database dalle variabili d'ambiente
DATABASE_URL = os.environ.get("DATABASE_URL")

def get_db_connection():
    """Crea una connessione al database PostgreSQL."""
    conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
    return conn

def init_db():
    """Crea la tabella 'prodotti' se non esiste già."""
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

# Inizializza il database all'avvio dell'applicazione
init_db()


@app.route("/")
def index():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT id, qr_code, nome, quantita, posizione FROM prodotti ORDER BY nome ASC;")
    prodotti = cur.fetchall()
    cur.close()
    conn.close()
    return render_template("index.html", prodotti=prodotti)


@app.route("/aggiungi", methods=["POST"])
def aggiungi_prodotto():
    qr_code = request.form.get("qr_code")
    nome = request.form.get("nome")
    quantita = request.form.get("quantita", 0)
    posizione = request.form.get("posizione", "")

    if not qr_code or not nome:
        flash("QR Code e Nome sono obbligatori!", "error")
        return redirect(url_for("index"))

    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO prodotti (qr_code, nome, quantita, posizione) VALUES (%s, %s, %s, %s);",
            (qr_code, nome, quantita, posizione)
        )
        conn.commit()
        cur.close()
        conn.close()
        flash("Prodotto aggiunto con successo!", "success")
    except Exception as e:
        flash(f"Errore nell'inserimento: {e}", "error")

    return redirect(url_for("index"))


if _name_ == "_main_":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
