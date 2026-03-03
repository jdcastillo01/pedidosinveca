import os
import sqlite3
import re
import io
import pandas as pd
from flask import Flask, render_template, request, jsonify, redirect, url_for

app = Flask(__name__)
DB_NAME = 'crm_clientes.db'

def init_db():
    with sqlite3.connect(DB_NAME) as conn:
        conn.execute('''CREATE TABLE IF NOT EXISTS clientes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT NOT NULL, 
            telefono TEXT NOT NULL, 
            estatus TEXT DEFAULT 'Por vender')''')
        conn.execute('''CREATE TABLE IF NOT EXISTS cobranza (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT NOT NULL, 
            telefono TEXT NOT NULL, 
            factura TEXT, 
            monto TEXT,
            estatus TEXT DEFAULT 'En espera de pago')''')
        conn.commit()

init_db()

def limpiar_telefono(tel):
    if pd.isna(tel) or str(tel).strip() == "": return ""
    return re.sub(r'[^\d+]', '', str(tel))

@app.route('/')
def index():
    tab = request.args.get('tab', 'ventas')
    with sqlite3.connect(DB_NAME) as conn:
        conn.row_factory = sqlite3.Row
        ventas = conn.execute('SELECT * FROM clientes ORDER BY id DESC').fetchall()
        cobros = conn.execute('SELECT * FROM cobranza ORDER BY id DESC').fetchall()
    return render_template('index.html', ventas=ventas, cobros=cobros, active_tab=tab)

@app.route('/importar/<tipo>', methods=['POST'])
def importar(tipo):
    file = request.files.get('file')
    if file:
        try:
            # Lectura flexible de CSV o Excel
            if file.filename.endswith('.csv'):
                content = file.read().decode("utf-8-sig")
                df = pd.read_csv(io.StringIO(content), sep=None, engine='python')
            else:
                df = pd.read_excel(file)
            
            # Normalizamos encabezados: minúsculas, sin espacios, sin tildes
            df.columns = [str(c).strip().lower().replace('é','e').replace('ó','o').replace('á','a') for c in df.columns]
            
            with sqlite3.connect(DB_NAME) as conn:
                for _, row in df.iterrows():
                    # MAPEADO CLAVE: Busca "razon social" (tu archivo de ventas) o "cliente" (tu archivo de cobros)
                    nombre = row.get('razon social') or row.get('cliente') or row.get('nombre')
                    
                    # Busca "telefono" o "telefono" con/sin tilde
                    telefono = row.get('telefono') or row.get('tel')
                    
                    if nombre and not pd.isna(nombre):
                        tel_limpio = limpiar_telefono(telefono)
                        
                        if tipo == 'ventas':
                            conn.execute('INSERT INTO clientes (nombre, telefono) VALUES (?, ?)',
                                       (str(nombre).strip(), tel_limpio))
                        
                        elif tipo == 'cobranza':
                            factura = row.get('factura') or row.get('nro. factura') or "S/N"
                            monto = row.get('monto') or row.get('total factura') or "0.00"
                            est = row.get('estatus') or 'En espera de pago'
                            
                            conn.execute('INSERT INTO cobranza (nombre, telefono, factura, monto, estatus) VALUES (?, ?, ?, ?, ?)',
                                       (str(nombre).strip(), tel_limpio, str(factura), str(monto), str(est)))
                conn.commit()
        except Exception as e:
            print(f"Error en importación: {e}")
            
    return redirect(url_for('index', tab=tipo))

@app.route('/borrar_todo/<tabla>', methods=['POST'])
def borrar_todo(tabla):
    target = 'clientes' if tabla == 'ventas' else 'cobranza'
    with sqlite3.connect(DB_NAME) as conn:
        conn.execute(f'DELETE FROM {target}')
        conn.commit()
    return redirect(url_for('index', tab=tabla))

@app.route('/cambiar_estatus/<tabla>/<int:id>')
def cambiar_estatus(tabla, id):
    target = 'clientes' if tabla == 'ventas' else 'cobranza'
    with sqlite3.connect(DB_NAME) as conn:
        res = conn.execute(f'SELECT estatus FROM {target} WHERE id = ?', (id,)).fetchone()
        if res:
            actual = res[0]
            if tabla == 'ventas':
                nuevo = 'Vendido' if actual == 'Por vender' else 'Por vender'
            else:
                nuevo = 'Pedido pagado' if 'espera' in actual.lower() else 'En espera de pago'
            conn.execute(f'UPDATE {target} SET estatus = ? WHERE id = ?', (nuevo, id))
            conn.commit()
            return jsonify({"nuevo_estatus": nuevo})
    return jsonify({"error": "No encontrado"}), 404

@app.route('/eliminar/<tabla>/<int:id>', methods=['DELETE'])
def eliminar(tabla, id):
    target = 'clientes' if tabla == 'ventas' else 'cobranza'
    with sqlite3.connect(DB_NAME) as conn:
        conn.execute(f'DELETE FROM {target} WHERE id = ?', (id,))
        conn.commit()
    return jsonify({"success": True})

if __name__ == '__main__':
    app.run(debug=True, port=5000)
