import os
import sqlite3
import re
import io
import urllib.parse
import pandas as pd
from flask import Flask, render_template, request, jsonify, redirect, url_for
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication
from email.mime.image import MIMEImage

app = Flask(__name__)
DB_NAME = 'crm_clientes.db'

# --- CONFIGURACIÓN DE CORREO ---
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 465 
SMTP_USER = "castillojuan01277@gmail.com"  # <--- TU GMAIL
SMTP_PASS = "znuh scgl kaaq fzal"  # <--- TU CLAVE DE 16 LETRAS
DESTINATARIO = "avillalba@neb.com.ve"

# --- MENSAJES AUTOMÁTICOS ---
MSG_VENTAS = "Buen dia!, Quisieramos consultar como estan de inventario, deseamos montar pedido para {nombre}."
MSG_COBRANZA = "Buen dia!, Quisieramos consultarle por el pago de la factura {factura}, ya que la misma se encuentra vencida por un monto de ${monto}."

def init_db():
    with sqlite3.connect(DB_NAME) as conn:
        conn.execute('''CREATE TABLE IF NOT EXISTS clientes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT NOT NULL, telefono TEXT NOT NULL, estatus TEXT DEFAULT 'Por vender')''')
        conn.execute('''CREATE TABLE IF NOT EXISTS cobranza (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT NOT NULL, telefono TEXT NOT NULL, factura TEXT, monto TEXT,
            estatus TEXT DEFAULT 'En espera de pago')''')
        conn.commit()

init_db()

@app.route('/')
def index():
    tab = request.args.get('tab', 'ventas')
    with sqlite3.connect(DB_NAME) as conn:
        conn.row_factory = sqlite3.Row
        ventas = conn.execute('SELECT * FROM clientes ORDER BY id DESC').fetchall()
        cobros = conn.execute('SELECT * FROM cobranza ORDER BY id DESC').fetchall()
    return render_template('index.html', ventas=ventas, cobros=cobros, active_tab=tab)

@app.route('/enviar_correo', methods=['POST'])
def enviar_correo():
    nombre = request.form.get('nombre')
    factura = request.form.get('factura')
    archivos = request.files.getlist('adjuntos')
    try:
        msg = MIMEMultipart('related')
        msg['From'] = SMTP_USER
        msg['To'] = DESTINATARIO
        msg['Subject'] = f"Soporte de pago {nombre} Factura {factura}"
        html = f"""<html><body style='font-family: Arial, sans-serif;'>
                   <p>Buen día,</p>
                   <p>Adjunto soporte de pago del cliente <b>{nombre}</b> perteneciente a la factura Nro. <b>{factura}</b>.</p>
                   <p>Cualquier información adicional estamos a la orden.</p><br>
                   <p>Saludos cordiales,</p>
                   <p>Telef: 04123056920</p>
                   <img src="cid:firma_img" width="300"></body></html>"""
        msg.attach(MIMEText(html, 'html'))
        ruta_firma = os.path.join(app.root_path, 'static', 'firma.png')
        if os.path.exists(ruta_firma):
            with open(ruta_firma, 'rb') as f:
                img = MIMEImage(f.read())
                img.add_header('Content-ID', '<firma_img>')
                img.add_header('Content-Disposition', 'inline', filename='firma.png')
                msg.attach(img)
        for f in archivos:
            if f.filename:
                part = MIMEApplication(f.read(), Name=f.filename)
                part['Content-Disposition'] = f'attachment; filename="{f.filename}"'
                msg.attach(part)
        import ssl
        context = ssl.create_default_context()
        with smtplib.SMTP_SSL(SMTP_SERVER, SMTP_PORT, context=context) as server:
            server.login(SMTP_USER, SMTP_PASS)
            server.send_message(msg)
        return jsonify({"success": True, "message": "Correo enviado con firma"})
    except Exception as e: return jsonify({"success": False, "message": str(e)})

@app.route('/wa/<tabla>/<int:id>')
def ir_whatsapp(tabla, id):
    with sqlite3.connect(DB_NAME) as conn:
        conn.row_factory = sqlite3.Row
        target = 'clientes' if tabla == 'ventas' else 'cobranza'
        c = conn.execute(f'SELECT * FROM {target} WHERE id = ?', (id,)).fetchone()
        if c:
            msg = MSG_VENTAS.format(nombre=c['nombre']) if tabla == 'ventas' else MSG_COBRANZA.format(nombre=c['nombre'], factura=c['factura'], monto=c['monto'])
            return redirect(f"https://wa.me/{c['telefono']}?text={urllib.parse.quote(msg)}")
    return redirect('/')

@app.route('/importar/<tipo>', methods=['POST'])
def importar(tipo):
    file = request.files.get('file')
    if file:
        try:
            df = pd.read_excel(file) if not file.filename.endswith('.csv') else pd.read_csv(io.StringIO(file.read().decode("utf-8-sig")), sep=None, engine='python')
            df.columns = [str(c).strip().lower().replace('é','e').replace('ó','o').replace('á','a') for c in df.columns]
            with sqlite3.connect(DB_NAME) as conn:
                for _, row in df.iterrows():
                    nombre = row.get('razon social') or row.get('cliente') or row.get('nombre')
                    tel = re.sub(r'[^\d+]', '', str(row.get('telefono') or ""))
                    if nombre and not pd.isna(nombre):
                        if tipo == 'ventas': conn.execute('INSERT INTO clientes (nombre, telefono) VALUES (?, ?)', (str(nombre), tel))
                        else:
                            f = row.get('factura') or "S/N"
                            m = row.get('monto') or "0.00"
                            conn.execute('INSERT INTO cobranza (nombre, telefono, factura, monto) VALUES (?, ?, ?, ?)', (str(nombre), tel, str(f), str(m)))
        except Exception as e: print(e)
    return redirect(url_for('index', tab=tipo))

@app.route('/cambiar_estatus/<tabla>/<int:id>')
def cambiar_estatus(tabla, id):
    t = 'clientes' if tabla == 'ventas' else 'cobranza'
    with sqlite3.connect(DB_NAME) as conn:
        curr = conn.execute(f'SELECT estatus FROM {t} WHERE id=?', (id,)).fetchone()[0]
        nuevo = ('Vendido' if curr == 'Por vender' else 'Por vender') if tabla == 'ventas' else ('Pedido pagado' if 'espera' in curr.lower() else 'En espera de pago')
        conn.execute(f'UPDATE {t} SET estatus=? WHERE id=?', (nuevo, id))
    return jsonify({"nuevo_estatus": nuevo})

@app.route('/eliminar/<tabla>/<int:id>', methods=['DELETE'])
def eliminar(tabla, id):
    t = 'clientes' if tabla == 'ventas' else 'cobranza'
    with sqlite3.connect(DB_NAME) as conn:
        conn.execute(f"DELETE FROM {t} WHERE id=?", (id,))
    return jsonify({"success": True})

@app.route('/borrar_todo/<tabla>', methods=['POST'])
def borrar_todo(tabla):
    t = 'clientes' if tabla == 'ventas' else 'cobranza'
    with sqlite3.connect(DB_NAME) as conn:
        conn.execute(f"DELETE FROM {t}")
    return redirect(url_for('index', tab=tabla))

if __name__ == '__main__':
    app.run(debug=True, port=5000)
