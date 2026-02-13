import os
from flask import Flask, render_template, request, jsonify, redirect
import pandas as pd
import sqlite3
import re
import io

app = Flask(__name__)
DB_NAME = 'crm_clientes.db'

def init_db():
    with sqlite3.connect(DB_NAME) as conn:
        conn.execute('''
            CREATE TABLE IF NOT EXISTS clientes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nombre TEXT NOT NULL,
                telefono TEXT NOT NULL,
                estatus TEXT DEFAULT 'Por vender'
            )
        ''')
        conn.commit()

def limpiar_telefono(tel):
    if pd.isna(tel): return ""
    return re.sub(r'\D', '', str(tel))

@app.route('/')
def index():
    init_db()
    with sqlite3.connect(DB_NAME) as conn:
        conn.row_factory = sqlite3.Row
        clientes = conn.execute('SELECT * FROM clientes ORDER BY id DESC').fetchall()
    return render_template('index.html', clientes=clientes)

@app.route('/importar', methods=['POST'])
def importar():
    file = request.files.get('file')
    if file:
        try:
            if file.filename.endswith('.csv'):
                content = file.read().decode("utf-8-sig")
                df = pd.read_csv(io.StringIO(content))
            else:
                df = pd.read_excel(file)
            
            df.columns = [str(c).strip() for c in df.columns]
            with sqlite3.connect(DB_NAME) as conn:
                for _, row in df.iterrows():
                    nombre = row.get('Razón social') or row.get('Razon social')
                    telefono = row.get('Teléfono') or row.get('Telefono')
                    if nombre and telefono:
                        conn.execute('INSERT INTO clientes (nombre, telefono) VALUES (?, ?)',
                                   (str(nombre).strip(), limpiar_telefono(telefono)))
                conn.commit()
        except Exception as e:
            print(f"Error de importacion: {e}")
    return redirect('/')

@app.route('/cambiar_estatus/<int:id>')
def cambiar_estatus(id):
    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.execute('SELECT estatus FROM clientes WHERE id = ?', (id,))
        res = cursor.fetchone()
        if res:
            nuevo = 'Vendido' if res[0] == 'Por vender' else 'Por vender'
            conn.execute('UPDATE clientes SET estatus = ? WHERE id = ?', (nuevo, id))
            conn.commit()
            return jsonify({"nuevo_estatus": nuevo})
    return jsonify({"error": "No encontrado"}), 404

@app.route('/eliminar/<int:id>', methods=['DELETE'])
def eliminar(id):
    with sqlite3.connect(DB_NAME) as conn:
        conn.execute('DELETE FROM clientes WHERE id = ?', (id,))
        conn.commit()
    return jsonify({"success": True})

@app.route('/limpiar')
def limpiar():
    with sqlite3.connect(DB_NAME) as conn:
        conn.execute('DELETE FROM clientes')
        conn.commit()
    return redirect('/')

if __name__ == '__main__':
    init_db()
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)