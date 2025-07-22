# app.py
import os
import json
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, send_file
from werkzeug.utils import secure_filename
import fitz  # PyMuPDF
from pypdf import PdfReader, PdfWriter
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from io import BytesIO
import traceback

# --- Configuração Inicial ---
UPLOAD_FOLDER = 'uploads'
STATIC_FOLDER = 'static'
TEMPLATES_FOLDER = 'templates' # Definir a pasta de templates
ALLOWED_EXTENSIONS = {'pdf'}

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['STATIC_FOLDER'] = STATIC_FOLDER
app.secret_key = "uma-chave-secreta-muito-segura"

# Garante que as pastas de upload e de imagens estáticas existem
os.makedirs(os.path.join(UPLOAD_FOLDER), exist_ok=True)
os.makedirs(os.path.join(STATIC_FOLDER, 'images'), exist_ok=True)

# --- Funções Auxiliares ---
def allowed_file(filename):
    """Verifica se a extensão do ficheiro é permitida."""
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def get_available_templates():
    """Busca e retorna uma lista de templates JSON disponíveis."""
    templates = []
    files = os.listdir(UPLOAD_FOLDER)
    for f in files:
        if f.endswith('_template.json'):
            pdf_name = f.replace('_template.json', '.pdf')
            if pdf_name in files:
                templates.append({
                    'name': pdf_name.replace('.pdf', ''),
                    'pdf_filename': pdf_name,
                    'template_filename': f
                })
    return templates

def get_available_forms():
    """Busca e retorna uma lista de formulários HTML gerados."""
    forms = []
    # Nomes dos ficheiros base da aplicação que não devem ser listados
    core_files = ['index.html', 'setup.html', 'cria_form.html', 'form.html']
    for f in os.listdir(TEMPLATES_FOLDER):
        if f.endswith('.html') and f not in core_files:
            forms.append({'name': f.replace('.html', ''), 'filename': f})
    return forms

# --- ROTAS PRINCIPAIS E DE GESTÃO DE TEMPLATES ---

@app.route('/', methods=['GET'])
def list_templates():
    """Página inicial que lista os templates e os formulários criados."""
    templates = get_available_templates()
    forms = get_available_forms()
    return render_template('index.html', templates=templates, forms=forms)

# --- NOVA ROTA PÚBLICA PARA FORMULÁRIOS ---
@app.route('/form/<form_html_file>')
def serve_public_form(form_html_file):
    """Serve um formulário HTML para qualquer pessoa com o link."""
    try:
        # A rota vai renderizar o ficheiro HTML com o nome correspondente
        return render_template(form_html_file)
    except Exception:
        # Se o ficheiro não for encontrado, mostra um erro 404
        return "Formulário não encontrado.", 404

@app.route('/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        flash('Nenhum ficheiro enviado')
        return redirect(url_for('list_templates'))
    file = request.files['file']
    if file.filename == '':
        flash('Nenhum ficheiro selecionado')
        return redirect(url_for('list_templates'))
    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        pdf_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(pdf_path)
        flash(f'"{filename}" enviado com sucesso! Agora configure os campos.')
        return redirect(url_for('setup_template', filename=filename))
    else:
        flash('Extensão de ficheiro não permitida. Por favor, envie um PDF.')
        return redirect(url_for('list_templates'))

@app.route('/setup/<filename>')
def setup_template(filename):
    pdf_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    image_filename = filename.replace('.pdf', '.png')
    image_path_static = os.path.join(app.config['STATIC_FOLDER'], 'images', image_filename)
    image_url = url_for('static', filename=f'images/{image_filename}')
    try:
        if not os.path.exists(image_path_static):
            doc = fitz.open(pdf_path)
            page = doc.load_page(0)
            pix = page.get_pixmap(dpi=150)
            pix.save(image_path_static)
            doc.close()
            
        reader = PdfReader(pdf_path)
        page = reader.pages[0]
        # *** AJUSTE AQUI: Obtém a largura e a altura do PDF ***
        pdf_height = float(page.mediabox.height)
        pdf_width = float(page.mediabox.width)
        
        return render_template('setup.html', 
                               image_url=image_url, 
                               pdf_filename=filename, 
                               pdf_height=pdf_height,
                               pdf_width=pdf_width) # Passa a largura para o template
    except Exception as e:
        traceback.print_exc()
        flash(f"Ocorreu um erro ao processar o ficheiro PDF: {e}")
        return redirect(url_for('list_templates'))

@app.route('/save_template/<pdf_filename>', methods=['POST'])
def save_template(pdf_filename):
    data = request.get_json()
    fields = data.get('fields')
    template_name = pdf_filename.replace('.pdf', '_template.json')
    template_path = os.path.join(app.config['UPLOAD_FOLDER'], template_name)
    try:
        with open(template_path, 'w', encoding='utf-8') as f:
            json.dump(fields, f, indent=4)
        flash(f"Template para '{pdf_filename}' salvo com sucesso!")
        return jsonify({'status': 'success', 'message': 'Template salvo!'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/delete/<pdf_name>', methods=['POST'])
def delete_template(pdf_name):
    try:
        pdf_filename = f"{pdf_name}.pdf"
        template_filename = f"{pdf_name}_template.json"
        image_filename = f"{pdf_name}.png"
        pdf_path = os.path.join(app.config['UPLOAD_FOLDER'], pdf_filename)
        template_path = os.path.join(app.config['UPLOAD_FOLDER'], template_filename)
        image_path = os.path.join(app.config['STATIC_FOLDER'], 'images', image_filename)
        if os.path.exists(pdf_path): os.remove(pdf_path)
        if os.path.exists(template_path): os.remove(template_path)
        if os.path.exists(image_path): os.remove(image_path)
        flash(f'Template "{pdf_name}" e todos os seus ficheiros foram excluídos com sucesso.')
    except Exception as e:
        traceback.print_exc()
        flash(f'Ocorreu um erro ao excluir o template: {e}')
    return redirect(url_for('list_templates'))

@app.route('/fill/<pdf_name>')
def fill_form(pdf_name):
    template_name = f"{pdf_name}_template.json"
    template_path = os.path.join(app.config['UPLOAD_FOLDER'], template_name)
    try:
        with open(template_path, 'r', encoding='utf-8') as f:
            fields = json.load(f)
        return render_template('form.html', fields=fields, pdf_name=pdf_name)
    except FileNotFoundError:
        flash(f"Template para '{pdf_name}' não encontrado.")
        return redirect(url_for('list_templates'))

@app.route('/generate/<pdf_name>', methods=['POST'])
def generate_pdf(pdf_name):
    form_data = request.form
    pdf_path = os.path.join(app.config['UPLOAD_FOLDER'], f"{pdf_name}.pdf")
    template_path = os.path.join(app.config['UPLOAD_FOLDER'], f"{pdf_name}_template.json")
    try:
        with open(template_path, 'r', encoding='utf-8') as f:
            template_fields = json.load(f)
        packet = BytesIO()
        reader = PdfReader(pdf_path)
        page_size = reader.pages[0].mediabox
        c = canvas.Canvas(packet, pagesize=(page_size.width, page_size.height))
        
        c.setFont("Helvetica", 10)

        for field in template_fields:
            field_name = field['name']
            if field_name in form_data:
                x = float(field['x'])
                y = float(field['y'])
                value = form_data[field_name]
                c.drawString(x, y, value)
        
        c.save()
        packet.seek(0)
        new_pdf = PdfReader(packet)
        existing_pdf = PdfReader(open(pdf_path, "rb"))
        output = PdfWriter()
        page = existing_pdf.pages[0]
        page.merge_page(new_pdf.pages[0])
        output.add_page(page)
        for i in range(1, len(existing_pdf.pages)):
            output.add_page(existing_pdf.pages[i])
        final_buffer = BytesIO()
        output.write(final_buffer)
        final_buffer.seek(0)
        return send_file(final_buffer, as_attachment=True, download_name=f"{pdf_name}_preenchido.pdf", mimetype='application/pdf')
    except Exception as e:
        traceback.print_exc()
        flash(f"Erro ao gerar o PDF: {e}")
        return redirect(url_for('fill_form', pdf_name=pdf_name))

@app.route('/form-builder')
def form_builder():
    templates = get_available_templates()
    return render_template('cria_form.html', templates=templates)

@app.route('/get-fields/<pdf_name>')
def get_template_fields(pdf_name):
    template_name = f"{pdf_name}_template.json"
    template_path = os.path.join(app.config['UPLOAD_FOLDER'], template_name)
    try:
        with open(template_path, 'r', encoding='utf-8') as f:
            fields = json.load(f)
        return jsonify(fields)
    except FileNotFoundError:
        return jsonify({"error": "Template não encontrado."}), 404

@app.route('/save-form', methods=['POST'])
def save_html_form():
    data = request.get_json()
    form_name = data.get('form_name')
    html_content = data.get('html_content')
    if not form_name or not html_content:
        return jsonify({"status": "error", "message": "Dados incompletos."}), 400
    full_html = f"""<!DOCTYPE html>
<html lang="pt-br">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{form_name}</title>
    <script src="https://cdn.tailwindcss.com"></script>
</head>
<body class="bg-gray-100 flex items-center justify-center min-h-screen p-6">
    {html_content}
</body>
</html>"""
    safe_filename = secure_filename(form_name) + '.html'
    file_path = os.path.join('templates', safe_filename)
    try:
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(full_html)
        return jsonify({"status": "success", "message": f"Formulário '{safe_filename}' salvo com sucesso!"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True)
