# app.py
import os
import json
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from werkzeug.utils import secure_filename
import fitz  # PyMuPDF
from pypdf import PdfReader
from io import BytesIO
import traceback

# --- Configuração Inicial ---
UPLOAD_FOLDER = 'uploads'
STATIC_FOLDER = 'static'
ALLOWED_EXTENSIONS = {'pdf'}

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['STATIC_FOLDER'] = STATIC_FOLDER
app.secret_key = "uma-chave-secreta-muito-segura"

os.makedirs(os.path.join(UPLOAD_FOLDER), exist_ok=True)
os.makedirs(os.path.join(STATIC_FOLDER, 'images'), exist_ok=True)

# --- Funções Auxiliares ---
def allowed_file(filename):
    """Verifica se a extensão do arquivo é permitida."""
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# --- ROTAS DA APLICAÇÃO ---

@app.route('/', methods=['GET', 'POST'])
def upload_file():
    """Página inicial para fazer o upload do arquivo PDF."""
    if request.method == 'POST':
        if 'file' not in request.files:
            flash('Nenhum arquivo enviado')
            return redirect(request.url)
        file = request.files['file']
        if file.filename == '':
            flash('Nenhum arquivo selecionado')
            return redirect(request.url)
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            pdf_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(pdf_path)
            
            # Redireciona para a página de configuração do template
            return redirect(url_for('setup_template', filename=filename))
            
    return render_template('index.html')

@app.route('/setup/<filename>')
def setup_template(filename):
    """Exibe o PDF como imagem para o usuário clicar e definir os campos."""
    pdf_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    image_filename = filename.replace('.pdf', '.png')
    image_path_static = os.path.join(app.config['STATIC_FOLDER'], 'images', image_filename)
    image_url = url_for('static', filename=f'images/{image_filename}')

    try:
        # Converte a primeira página do PDF para uma imagem PNG
        if not os.path.exists(image_path_static):
            doc = fitz.open(pdf_path)
            page = doc.load_page(0)
            pix = page.get_pixmap(dpi=150)
            pix.save(image_path_static)
            doc.close()

        # Obtém as dimensões do PDF para passar ao template
        reader = PdfReader(pdf_path)
        page = reader.pages[0]
        pdf_height = float(page.mediabox.height)
        
        return render_template('setup.html', 
                               image_url=image_url, 
                               pdf_filename=filename, 
                               pdf_height=pdf_height)

    except Exception as e:
        traceback.print_exc()
        flash(f"Ocorreu um erro ao processar o PDF: {e}")
        return redirect(url_for('upload_file'))

@app.route('/save_template/<pdf_filename>', methods=['POST'])
def save_template(pdf_filename):
    """Salva as coordenadas dos campos em um arquivo JSON."""
    data = request.get_json()
    fields = data.get('fields')
    template_name = pdf_filename.replace('.pdf', '_template.json')
    template_path = os.path.join(app.config['UPLOAD_FOLDER'], template_name)

    try:
        with open(template_path, 'w', encoding='utf-8') as f:
            json.dump(fields, f, indent=4)
        flash(f"Template '{template_name}' salvo com sucesso!")
        return jsonify({'status': 'success', 'message': 'Template salvo!'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True)
