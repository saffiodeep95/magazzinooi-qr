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
                posizione VARCHAR(255),
                sap VARCHAR(255),
                stato VARCHAR(50) DEFAULT 'Disponibile',
                cliente_manutenzione VARCHAR(255)
            );
            CREATE TABLE IF NOT EXISTS clienti (
                id SERIAL PRIMARY KEY,
                nome_azienda VARCHAR(255) UNIQUE NOT NULL,
                indirizzo TEXT,
                p_iva VARCHAR(50),
                telefono VARCHAR(50),
                email VARCHAR(100)
            );
        """)
        conn.commit()
        cur.close()
        conn.close()
    except Exception as e:
        print(f"Errore DB: {e}")

init_db()

@app.route("/")
def index():
    prodotti = []
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT * FROM prodotti ORDER BY id DESC;")
        prodotti = cur.fetchall()
        cur.close()
        conn.close()
    except Exception as e:
        print(f"Errore index: {e}")
    return render_template("index.html", prodotti=prodotti)

@app.route("/gestisci/<qr_code>")
def gestisci_prodotto(qr_code):
    prodotto = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT * FROM prodotti WHERE qr_code = %s;", (qr_code,))
        prodotto = cur.fetchone()
        cur.close()
        conn.close()
    except Exception as e:
        print(f"Errore gestisci: {e}")

    if not prodotto:
        flash("Prodotto non trovato nel sistema!", "error")
        return redirect(url_for("index"))

    return render_template("gestisci.html", prodotto=prodotto)

@app.route("/aggiungi", methods=["POST"])
def aggiungi_prodotto():
    qr_code = request.form.get("qr_code")
    nome = request.form.get("nome")
    sap = request.form.get("sap", "")
    quantita = int(request.form.get("quantita", 0) or 0)
    posizione = request.form.get("posizione", "")

    if qr_code and nome:
        try:
            conn = get_db_connection()
            cur = conn.cursor()
            cur.execute(
                """
                INSERT INTO prodotti (qr_code, nome, sap, quantita, posizione, stato)
                VALUES (%s, %s, %s, %s, %s, 'Disponibile')
                ON CONFLICT (qr_code)
                DO UPDATE SET quantita = prodotti.quantita + EXCLUDED.quantita,
                              nome = EXCLUDED.nome,
                              sap = EXCLUDED.sap,
                              posizione = EXCLUDED.posizione;
                """,
                (qr_code, nome, sap, quantita, posizione)
            )
            conn.commit()
            cur.close()
            conn.close()
            flash("Prodotto aggiunto o aggiornato con successo!", "success")
        except Exception as e:
            flash(f"Errore nell'inserimento: {e}", "error")

    return redirect(url_for("index"))

@app.route("/carico", methods=["GET", "POST"])
def carico():
    if request.method == "POST":
        qr_code = request.form.get("qr_code")
        quantita = int(request.form.get("quantita", 1) or 1)
        if qr_code:
            try:
                conn = get_db_connection()
                cur = conn.cursor()
                cur.execute("UPDATE prodotti SET quantita = quantita + %s WHERE qr_code = %s;", (quantita, qr_code))
                conn.commit()
                cur.close()
                conn.close()
                flash(f"Carico di {quantita} pz effettuato con successo!", "success")
                return redirect(url_for("gestisci_prodotto", qr_code=qr_code))
            except Exception as e:
                flash(f"Errore durante il carico: {e}", "error")
    return render_template("carico.html")

@app.route("/scarico", methods=["GET", "POST"])
def scarico():
    if request.method == "POST":
        qr_code = request.form.get("qr_code")
        quantita = int(request.form.get("quantita", 1) or 1)
        if qr_code:
            try:
                conn = get_db_connection()
                cur = conn.cursor()
                cur.execute("UPDATE prodotti SET quantita = GREATEST(0, quantita - %s) WHERE qr_code = %s;", (quantita, qr_code))
                conn.commit()
                cur.close()
                conn.close()
                flash(f"Scarico di {quantita} pz effettuato con successo!", "success")
                return redirect(url_for("gestisci_prodotto", qr_code=qr_code))
            except Exception as e:
                flash(f"Errore durante lo scarico: {e}", "error")
    return render_template("scarico.html")

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
            flash("Articolo eliminato dal magazzino con successo!", "success")
        except Exception as e:
            flash(f"Errore durante l'eliminazione: {e}", "error")

    return redirect(url_for("index"))

@app.route("/stato_manutenzione/<qr_code>", methods=["POST"])
def stato_manutenzione(qr_code):
    nuovo_stato = request.form.get("stato", "In Manutenzione")
    cliente = request.form.get("cliente_manutenzione", "")
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("""
            UPDATE prodotti 
            SET stato = %s, cliente_manutenzione = %s 
            WHERE qr_code = %s;
        """, (nuovo_stato, cliente if cliente else None, qr_code))
        conn.commit()
        cur.close()
        conn.close()
        flash(f"Stato prodotto aggiornato a: {nuovo_stato}", "success")
    except Exception as e:
        flash(f"Errore aggiornamento stato: {e}", "error")
    return redirect(url_for("gestisci_prodotto", qr_code=qr_code))

@app.route("/clienti")
@app.route("/lista_clienti")
def clienti():
    clienti_list = []
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT * FROM clienti ORDER BY nome_azienda ASC;")
        clienti_list = cur.fetchall()
        cur.close()
        conn.close()
    except Exception as e:
        print(f"Errore clienti: {e}")
    return render_template("clienti.html", clienti=clienti_list)

@app.route("/aggiungi_cliente", methods=["POST"])
def aggiungi_cliente():
    nome_azienda = request.form.get("nome_azienda", "").strip()
    indirizzo = request.form.get("indirizzo", "")
    p_iva = request.form.get("p_iva", "")
    telefono = request.form.get("telefono", "")
    email = request.form.get("email", "")

    if nome_azienda:
        try:
            conn = get_db_connection()
            cur = conn.cursor()
            cur.execute(
                """
                INSERT INTO clienti (nome_azienda, indirizzo, p_iva, telefono, email)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (nome_azienda) DO UPDATE 
                SET indirizzo = EXCLUDED.indirizzo, 
                    p_iva = EXCLUDED.p_iva, 
                    telefono = EXCLUDED.telefono, 
                    email = EXCLUDED.email;
                """,
                (nome_azienda, indirizzo, p_iva, telefono, email)
            )
            conn.commit()
            cur.close()
            conn.close()
            flash("Cliente salvato con successo!", "success")
        except Exception as e:
            flash(f"Errore salvataggio cliente: {e}", "error")

    return redirect(url_for("clienti"))

@app.route("/manutenzioni")
@app.route("/lista_manutenzioni")
def lista_manutenzioni():
    prodotti_maint = []
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT * FROM prodotti WHERE stato = 'In Manutenzione' ORDER BY id DESC;")
        prodotti_maint = cur.fetchall()
        cur.close()
        conn.close()
    except Exception as e:
        print(f"Errore manutenzioni: {e}")
    return render_template("manutenzioni.html", prodotti=prodotti_maint)

if __name__ == "_main_":
    app.run(host="0.0.0.0", port=5000, debug=True)
