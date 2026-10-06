import os
import io
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.image import MIMEImage

import psycopg2
import qrcode
from PIL import Image, ImageDraw, ImageFont
from flask import Flask, render_template, request, jsonify, send_file, redirect, url_for

app = Flask(_name_)

DATABASE_URL = os.environ.get('DATABASE_URL')

# Configurazione Email SMTP (impostabili dalle variabili d'ambiente di Render)
SMTP_SERVER = os.environ.get('SMTP_SERVER', 'smtp.gmail.com')
SMTP_PORT = int(os.environ.get('SMTP_PORT', 587))
SMTP_EMAIL = os.environ.get('SMTP_EMAIL', '')
SMTP_PASSWORD = os.environ.get('SMTP_PASSWORD', '')

def get_db_connection():
    if DATABASE_URL:
        conn = psycopg2.connect(DATABASE_URL, sslmode='require')
        return conn
    else:
        import sqlite3
        conn = sqlite3.connect('magazzino.db')
        return conn

def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    if DATABASE_URL:
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS prodotti (
                id SERIAL PRIMARY KEY,
                qr_code VARCHAR(100) UNIQUE NOT NULL,
                nome VARCHAR(255) NOT NULL,
                quantita INTEGER NOT NULL DEFAULT 0,
                posizione VARCHAR(100)
            );
        ''')
    else:
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS prodotti (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                qr_code TEXT UNIQUE NOT NULL,
                nome TEXT NOT NULL,
                quantita INTEGER NOT NULL DEFAULT 0,
                posizione TEXT
            );
        ''')
    
    conn.commit()
    cursor.close()
    conn.close()

# Genera l'immagine dell'etichetta (Descrizione in alto + QR Code sotto)
def crea_immagine_etichetta(codice, nome_prodotto, posizione=""):
    qr = qrcode.QRCode(box_size=8, border=2)
    qr.add_data(codice)
    qr.make(fit=True)
    qr_img = qr.make_image(fill_color="black", back_color="white").convert('RGB')
    
    qr_w, qr_h = qr_img.size
    padding = 20
    header_h = 60
    
    label_w = qr_w + (padding * 2)
    label_h = qr_h + header_h + padding
    label_img = Image.new('RGB', (label_w, label_h), color='white')
    
    draw = ImageDraw.Draw(label_img)
    font = ImageFont.load_default()
    
    draw.text((padding, 10), f"PRODOTTO: {nome_prodotto[:28]}", fill="black", font=font)
    draw.text((padding, 28), f"CODICE: {codice}", fill="black", font=font)
    if posizione:
        draw.text((padding, 44), f"POSIZIONE: {posizione}", fill="black", font=font)
        
    label_img.paste(qr_img, (padding, header_h))
    return label_img

@app.route('/')
def index():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, qr_code, nome, quantita, posizione FROM prodotti ORDER BY nome ASC;")
    prodotti = cursor.fetchall()
    cursor.close()
    conn.close()
    return render_template('index.html', prodotti=prodotti)

@app.route('/carico')
def carico():
    return render_template('carico.html')

@app.route('/scarico')
def scarico():
    return render_template('scarico.html')

# Rotta per visualizzare/scaricare l'etichetta PNG
@app.route('/qr_label/<string:codice>')
def qr_label(codice):
    conn = get_db_connection()
    cursor = conn.cursor()
    sql = "SELECT nome, posizione FROM prodotti WHERE qr_code = %s;" if DATABASE_URL else "SELECT nome, posizione FROM prodotti WHERE qr_code = ?;"
    cursor.execute(sql, (codice,))
    prod = cursor.fetchone()
    cursor.close()
    conn.close()

    nome = prod[0] if prod else codice
    pos = prod[1] if prod and prod[1] else ""

    label_img = crea_immagine_etichetta(codice, nome, pos)
    buf = io.BytesIO()
    label_img.save(buf, 'PNG')
    buf.seek(0)
    return send_file(buf, mimetype='image/png')

# Funzione ausiliaria invio email
def invia_email_etichetta(destinatario, qr_code, nome, posizione=""):
    if not SMTP_EMAIL or not SMTP_PASSWORD:
        return False, "Credenziali SMTP non configurate"

    label_img = crea_immagine_etichetta(qr_code, nome, posizione)
    img_bytes = io.BytesIO()
    label_img.save(img_bytes, format='PNG')
    img_data = img_bytes.getvalue()

    msg = MIMEMultipart()
    msg['Subject'] = f"Etichetta QR Code: {nome}"
    msg['From'] = SMTP_EMAIL
    msg['To'] = destinatario

    body = f"In allegato trovi l'etichetta generata per il prodotto '{nome}' (Codice: {qr_code})."
    msg.attach(MIMEText(body, 'plain'))

    image_attachment = MIMEImage(img_data, name=f"etichetta_{qr_code}.png")
    msg.attach(image_attachment)

    server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
    server.starttls()
    server.login(SMTP_EMAIL, SMTP_PASSWORD)
    server.send_message(msg)
    server.quit()
    return True, f"Etichetta inviata a {destinatario}"

# API CARICO / INSERIMENTO (+1)
@app.route('/api/carica', methods=['POST'])
def api_carica():
    data = request.get_json()
    qr_code = data.get('qr_code', '').strip()
    nome = data.get('nome', '').strip()
    posizione = data.get('posizione', '').strip()
    email = data.get('email', '').strip()

    if not qr_code:
        return jsonify({'success': False, 'message': 'QR code vuoto'}), 400

    conn = get_db_connection()
    cursor = conn.cursor()

    sql_select = "SELECT id, nome, quantita FROM prodotti WHERE qr_code = %s;" if DATABASE_URL else "SELECT id, nome, quantita FROM prodotti WHERE qr_code = ?;"
    cursor.execute(sql_select, (qr_code,))
    prodotto = cursor.fetchone()

    # Se esiste -> +1 giacenza
    if prodotto:
        prod_id, prod_nome, quantita = prodotto
        nuova_quantita = quantita + 1
        sql_update = "UPDATE prodotti SET quantita = %s WHERE id = %s;" if DATABASE_URL else "UPDATE prodotti SET quantita = ? WHERE id = ?;"
        cursor.execute(sql_update, (nuova_quantita, prod_id))
        conn.commit()
        cursor.close()
        conn.close()

        email_status = ""
        if email:
            ok, msg_mail = invia_email_etichetta(email, qr_code, prod_nome, posizione)
            email_status = f" | {msg_mail}" if ok else f" | Error mail: {msg_mail}"

        return jsonify({
            'success': True,
            'is_new': False,
            'message': f'Caricato 1x "{prod_nome}". Nuova giacenza: {nuova_quantita}{email_status}'
        })
    
    # Se non esiste ed è stato specificato il nome -> Crea il prodotto
    elif nome:
        sql_insert = "INSERT INTO prodotti (qr_code, nome, quantita, posizione) VALUES (%s, %s, 1, %s);" if DATABASE_URL else "INSERT INTO prodotti (qr_code, nome, quantita, posizione) VALUES (?, ?, 1, ?);"
        cursor.execute(sql_insert, (qr_code, nome, posizione))
        conn.commit()
        cursor.close()
        conn.close()

        email_status = ""
        if email:
            ok, msg_mail = invia_email_etichetta(email, qr_code, nome, posizione)
            email_status = f" | {msg_mail}" if ok else f" | Error mail: {msg_mail}"

        return jsonify({
            'success': True,
            'is_new': False,
            'message': f'Creato nuovo prodotto "{nome}" (Giacenza: 1){email_status}'
        })
    
    # Se non esiste e manca il nome -> Chiedi i dettagli all'utente
    else:
        cursor.close()
        conn.close()
        return jsonify({
            'success': False,
            'is_new': True,
            'message': f'Codice QR {qr_code} non censito. Inserisci i dati per crearne uno nuovo.'
        })

# API SCARICO (-1)
@app.route('/api/scarica', methods=['POST'])
def api_scarica():
    data = request.get_json()
    qr_code = data.get('qr_code', '').strip()

    if not qr_code:
        return jsonify({'success': False, 'message': 'QR code vuoto'}), 400

    conn = get_db_connection()
    cursor = conn.cursor()

    sql_select = "SELECT id, nome, quantita FROM prodotti WHERE qr_code = %s;" if DATABASE_URL else "SELECT id, nome, quantita FROM prodotti WHERE qr_code = ?;"
    cursor.execute(sql_select, (qr_code,))
    prodotto = cursor.fetchone()

    if not prodotto:
        cursor.close()
        conn.close()
        return jsonify({'success': False, 'message': f'QR non trovato: {qr_code}'}), 404

    prod_id, nome, quantita = prodotto

    if quantita <= 0:
        cursor.close()
        conn.close()
        return jsonify({'success': False, 'message': f'"{nome}" esaurito (Giacenza: 0)'}), 400

    nuova_quantita = quantita - 1
    sql_update = "UPDATE prodotti SET quantita = %s WHERE id = %s;" if DATABASE_URL else "UPDATE prodotti SET quantita = ? WHERE id = ?;"
    cursor.execute(sql_update, (nuova_quantita, prod_id))
    
    conn.commit()
    cursor.close()
    conn.close()

    return jsonify({
        'success': True,
        'message': f'Scaricato 1x "{nome}". Nuova giacenza: {nuova_quantita}'
    })

if _name_ == '_main_':
    init_db()
    app.run(host='0.0.0.0', port=5000, debug=True)
