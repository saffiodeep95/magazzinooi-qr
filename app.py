import os
import psycopg2
from psycopg2.extras import RealDictCursor
from flask import Flask, render_template, request, redirect, url_for, flash

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "chiave-segreta-magazzino")

DATABASE_URL = os.environ.get("DATABASE_URL")

def get_db_connection():
    return psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)

def init_db():
    if not DATABASE_URL:
        print("DATABASE_URL non impostata!")
        return
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Creazione tabella con supporto per peso e magazzino composizione motori
        cur.execute("""
            CREATE TABLE IF NOT EXISTS prodotti (
                id SERIAL PRIMARY KEY,
                qr_code VARCHAR(255) UNIQUE NOT NULL,
                nome VARCHAR(255) NOT NULL,
                sap VARCHAR(255),
                peso VARCHAR(255),
                quantita INT DEFAULT 0,
                posizione VARCHAR(255),
                magazzino_composizione_motori INT DEFAULT 0
            );
        """)
        
        # Aggiunta sicura delle colonne se la tabella esisteva già senza di esse
        cur.execute("ALTER TABLE prodotti ADD COLUMN IF NOT EXISTS peso VARCHAR(255);")
        cur.execute("ALTER TABLE prodotti ADD COLUMN IF NOT EXISTS magazzino_composizione_motori INT DEFAULT 0;")

        conn.commit()
        cur.close()
        conn.close()
        print("Inizializzazione database completata con successo.")
    except Exception as e:
        print(f"Errore durante l'inizializzazione del database: {e}")

init_db()

@app.route("/")
def index():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT id, qr_code, nome, sap, peso, quantita, posizione FROM prodotti WHERE magazzino_composizione_motori = 0 OR magazzino_composizione_motori IS NULL ORDER BY nome ASC;")
    prodotti = cur.fetchall()
    cur.close()
    conn.close()
    return render_template("index.html", prodotti=prodotti)

@app.route("/magazzino_composizione_motori")
def magazzino_composizione_motori_view():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT id, qr_code, nome, sap, peso, quantita, posizione FROM prodotti WHERE magazzino_composizione_motori = 1 ORDER BY nome ASC;")
    prodotti = cur.fetchall()
    cur.close()
    conn.close()
    return render_template("magazzino_composizione.html", prodotti=prodotti)

@app.route("/gestisci/<qr_code>")
def gestisci_prodotto(qr_code):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT id, qr_code, nome, sap, peso, quantita, posizione FROM prodotti WHERE qr_code = %s;", (qr_code,))
    prodotto = cur.fetchone()
    cur.close()
    conn.close()

    if not prodotto:
        flash("Prodotto non trovato nel sistema!", "error")
        return redirect(url_for("index"))

    return render_template("gestisci.html", prodotto=prodotto)

@app.route("/aggiungi", methods=["POST"])
def aggiungi_prodotto():
    qr_code = request.form.get("qr_code")
    nome = request.form.get("nome")
    sap = request.form.get("sap", "")
    peso = request.form.get("peso", "")
    quantita = int(request.form.get("quantita", 0))
    posizione = request.form.get("posizione", "")
    magazzino_composizione_motori = 1 if request.form.get("magazzino_composizione_motori") else 0

    if not qr_code or not nome:
        flash("QR Code e Nome sono obbligatori!", "error")
        return redirect(url_for("index"))

    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO prodotti (qr_code, nome, sap, peso, quantita, posizione, magazzino_composizione_motori)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (qr_code)
            DO UPDATE SET 
                quantita = prodotti.quantita + EXCLUDED.quantita,
                nome = EXCLUDED.nome,
                sap = EXCLUDED.sap,
                peso = EXCLUDED.peso,
                posizione = EXCLUDED.posizione,
                magazzino_composizione_motori = EXCLUDED.magazzino_composizione_motori;
            """,
            (qr_code, nome, sap, peso, quantita, posizione, magazzino_composizione_motori)
        )
        conn.commit()
        cur.close()
        conn.close()
        flash("Prodotto aggiunto o aggiornato con successo!", "success")
    except Exception as e:
        flash(f"Errore nell'inserimento: {e}", "error")

    if magazzino_composizione_motori:
        return redirect(url_for("magazzino_composizione_motori_view"))
    return redirect(url_for("index"))

@app.route("/carico", methods=["GET", "POST"])
def carico():
    if request.method == "POST":
        qr_code = request.form.get("qr_code")
        quantita = int(request.form.get("quantita", 1))
    else:
        qr_code = request.args.get("qr_code")
        quantita = int(request.args.get("quantita", 1))

    if not qr_code:
        flash("QR Code non valido o mancante!", "error")
        return redirect(url_for("index"))

    try:
        conn = get_db_connection()
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

    return redirect(url_for("gestisci_prodotto", qr_code=qr_code))

@app.route("/scarico", methods=["GET", "POST"])
def scarico():
    if request.method == "POST":
        qr_code = request.form.get("qr_code")
        quantita = int(request.form.get("quantita", 1))
    else:
        qr_code = request.args.get("qr_code")
        quantita = int(request.args.get("quantita", 1))

    if not qr_code:
        flash("QR Code non valido o mancante!", "error")
        return redirect(url_for("index"))

    try:
        conn = get_db_connection()
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

    return redirect(url_for("gestisci_prodotto", qr_code=qr_code))

@app.route("/elimina", methods=["POST"])
def elimina_prodotto():
    qr_code = request.form.get("qr_code")
    if not qr_code:
        flash("QR Code non valido per l'eliminazione!", "error")
        return redirect(url_for("index"))

    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("DELETE FROM prodotti WHERE qr_code = %s;", (qr_code,))
        conn.commit()
        cur.close()
        conn.close()
        flash("Articolo eliminato dal magazzino con successo!", "success")
    except Exception as e:
        flash(f"Errore durante l'eliminazione: {e}", "error")

    return redirect(url_for("index"))

if __name__ == "_main_":
    app.run(debug=True)
