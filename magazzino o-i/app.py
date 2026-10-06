import os
import psycopg2
from psycopg2.extras import RealDictCursor
from flask import Flask, render_template, request, redirect, url_for, flash

# Configurazione del percorso assoluto per la cartella templates all'interno di magazzino o-i
template_dir = os.path.abspath(os.path.join(os.path.dirname(_file_), 'magazzino o-i', 'templates'))
app = Flask(_name_, template_folder=template_dir)
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
        flash
