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
        cur.execute("""
            CREATE TABLE IF NOT EXISTS prodotti (
                id SERIAL PRIMARY KEY,
                qr_code VARCHAR(255) UNIQUE NOT NULL,
                nome VARCHAR(255) NOT NULL,
                sap VARCHAR(255),
                peso VARCHAR(255),
                quantita INT DEFAULT 0,
                posizione VARCHAR(255),
                is_pesante INT DEFAULT 0,
                in_manutenzione INT DEFAULT 0,
                cliente_manutenzione VARCHAR(255),
                quantita_manutenzione INT DEFAULT 0,
                data_spedizione VARCHAR(255),
                data_riconsegna VARCHAR(255),
                vettore VARCHAR(255),
                ordine_amministrativo INT DEFAULT 0,
                note_manutenzione TEXT
            );
        """)
        conn.commit()
        cur.close()
        conn.close()
        print("Inizializzazione tabella prodotti completata con successo.")
    except Exception as e:
        print(f"Errore durante l'inizializzazione del database: {e}")

init_db()

@app.route("/")
def index():
    conn = get_db_connection()
    cur = conn.cursor()
    # Mostra i prodotti normali (esclusi quelli di composizione e motori)
    cur.execute("SELECT * FROM prodotti WHERE is_pesante = 0 OR is_pesante IS NULL ORDER BY nome ASC;")
    prodotti = cur.fetchall()
    cur.close()
    conn.close()
    return render_template("index.html", prodotti=prodotti)

# Nuova Sezione: Magazzino Composizione e Motori
@app.route("/magazzino_composizione_motori")
def magazzino_composizione_motori():
    conn = get_db_connection()
    cur = conn.cursor()
    # Mostra solo i prodotti con il flag attivo
    cur.execute("SELECT * FROM prodotti WHERE is_pesante = 1 ORDER BY nome ASC;")
    prodotti = cur.fetchall()
    cur.close()
    conn.close()
    return render_template("magazzino_composizione_motori.html", prodotti=prodotti)

@app.route("/gestisci/<qr_code>")
def gestisci_prodotto(qr_code):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM prodotti WHERE qr_code = %s;", (qr_code,))
    prodotto = cur.fetchone()
    
    clienti = []
    try:
        cur.execute("SELECT * FROM clienti ORDER BY nome_azienda ASC;")
        clienti = cur.fetchall()
    except Exception:
        pass

    cur.close()
    conn.close()

    if not prodotto:
        flash("Prodotto non trovato nel sistema!", "error")
        return redirect(url_for("index"))

    return render_template("gestisci.html", prodotto=prodotto, clienti=clienti)

@app.route("/aggiungi", methods=["POST"])
def aggiungi_prodotto():
    qr_code = request.form.get("qr_code")
    nome = request.form.get("nome")
    sap = request.form.get("sap", "")
    peso = request.form.get("peso", "")
    quantita = int(request.form.get("quantita", 0))
    posizione = request.form.get("posizione", "")
    is_pesante = 1 if request.form.get("magazzino_composizione_motori") else 0

    if not qr_code or not nome:
        flash("QR Code e Nome sono obbligatori!", "error")
        return redirect(url_for("index"))

    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO prodotti (qr_code, nome, sap, peso, quantita, posizione, is_pesante)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (qr_code)
            DO UPDATE SET 
                quantita = prodotti.quantita + EXCLUDED.quantita,
                nome = EXCLUDED.nome,
                sap = EXCLUDED.sap,
                peso = EXCLUDED.peso,
                posizione = EXCLUDED.posizione,
                is_pesante = EXCLUDED.is_pesante;
            """,
            (qr_code, nome, sap, peso, quantita, posizione, is_pesante)
        )
        conn.commit()
        cur.close()
        conn.close()
        flash("Prodotto aggiunto o aggiornato con successo!", "success")
    except Exception as e:
        flash(f"Errore nell'inserimento: {e}", "error")

    if is_pesante:
        return redirect(url_for("magazzino_composizione_motori"))
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

@app.route("/manutenzione/<qr_code>", methods=["POST"])
def manutenzione(qr_code):
    azione = request.form.get("azione")
    conn = get_db_connection()
    cur = conn.cursor()

    try:
        if azione == "invia":
            cliente = request.form.get("cliente")
            q_maint = int(request.form.get("quantita_manutenzione", 1))
            data_sped = request.form.get("data_spedizione")
            data_ric = request.form.get("data_riconsegna")
            vettore = request.form.get("vettore")
            ordine_amm = 1 if request.form.get("ordine_amministrativo") else 0
            note = request.form.get("note_manutenzione")

            prod = cur.execute("SELECT quantita FROM prodotti WHERE qr_code = %s;", (qr_code,)).fetchone()
            if prod and prod["quantita"] >= q_maint:
                cur.execute("""
                    UPDATE prodotti SET 
                        quantita = quantita - %s,
                        in_manutenzione = 1,
                        cliente_manutenzione = %s,
                        quantita_manutenzione = %s,
                        data_spedizione = %s,
                        data_riconsegna = %s,
                        vettore = %s,
                        ordine_amministrativo = %s,
                        note_manutenzione = %s
                    WHERE qr_code = %s;
                """, (q_maint, cliente, q_maint, data_sped, data_ric, vettore, ordine_amm, note, qr_code))
                conn.commit()
                flash("Articolo inviato in manutenzione con successo!", "success")
            else:
                flash("Quantità insufficiente per mandare in manutenzione.", "error")

        elif azione == "rientra":
            prod = cur.execute("SELECT quantita_manutenzione FROM prodotti WHERE qr_code = %s;", (qr_code,)).fetchone()
            if prod:
                q_rientro = prod["quantita_manutenzione"] or 0
                cur.execute("""
                    UPDATE prodotti SET 
                        quantita = quantita + %s,
                        in_manutenzione = 0,
                        cliente_manutenzione = NULL,
                        quantita_manutenzione = 0,
                        data_spedizione = NULL,
                        data_riconsegna = NULL,
                        vettore = NULL,
                        ordine_amministrativo = 0,
                        note_manutenzione = NULL
                    WHERE qr_code = %s;
                """, (q_rientro, qr_code))
                conn.commit()
                flash("Articolo rientrato dalla manutenzione con successo!", "success")
    except Exception as e:
        flash(f"Errore nella gestione manutenzione: {e}", "error")
    finally:
        cur.close()
        conn.close()

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
