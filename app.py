import os
import json
import traceback
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, send_from_directory
from flask_wtf import FlaskForm
from flask_wtf.file import FileField, FileRequired, FileAllowed
from wtforms import StringField, SubmitField
from wtforms.validators import Optional
from werkzeug.utils import secure_filename
from pathlib import Path
from utils import logger

app = Flask(__name__)
BASE_DIR = Path(__file__).resolve().parent
app.config['SECRET_KEY'] = os.environ.get('PERSON_INFO_SECRET_KEY', 'person_info_search_secret_key')
app.config['UPLOAD_FOLDER'] = os.environ.get('PERSON_INFO_UPLOAD_DIR', str(BASE_DIR / 'uploads'))
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024
OUTPUT_DIR = BASE_DIR / 'output'

os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

from main import PersonInfoSearcher

searcher = PersonInfoSearcher()

ALLOWED_EXTENSIONS = {'docx', 'pdf', 'jpg', 'jpeg', 'png', 'bmp', 'txt'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

class UploadForm(FlaskForm):
    file = FileField('上传简历', validators=[
        FileRequired(),
        FileAllowed(ALLOWED_EXTENSIONS, '只支持 docx, pdf, jpg, png, bmp, txt 格式')
    ])
    name = StringField('姓名（可选，自动识别失败时使用）', validators=[Optional()])
    submit = SubmitField('开始搜索')

class ManualForm(FlaskForm):
    name = StringField('姓名', validators=[])
    company = StringField('过往任职企业', validators=[Optional()])
    position = StringField('岗位', validators=[Optional()])
    region = StringField('所在地域', validators=[Optional()])
    phone = StringField('电话号码', validators=[Optional()])
    submit = SubmitField('开始搜索')

def _friendly_error_message(error):
    message = str(error)
    if isinstance(error, ValueError):
        return f"输入或解析失败: {message}"
    if isinstance(error, FileNotFoundError):
        return "简历文件未找到，请重新上传。"
    if isinstance(error, ImportError):
        return f"解析依赖缺失: {message}"
    return "系统处理失败，请稍后重试。"

@app.route('/', methods=['GET', 'POST'])
def index():
    upload_form = UploadForm()
    manual_form = ManualForm()
    
    if request.method == 'POST':
        if 'file' in request.files and request.files['file'].filename != '':
            return handle_file_upload(upload_form)
        elif request.form.get('name') and request.form.get('submit_type') == 'manual':
            return handle_manual_input(manual_form)
        elif request.form.get('name'):
            person_info = {
                'name': request.form.get('name'),
                'company': request.form.get('company', ''),
                'position': request.form.get('position', ''),
                'region': request.form.get('region', ''),
                'phone': request.form.get('phone', '')
            }
            return do_search(person_info)
    
    return render_template('index.html', upload_form=upload_form, manual_form=manual_form)

def handle_file_upload(form):
    if form.validate_on_submit():
        file = form.file.data
        filename = secure_filename(file.filename)
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)
        
        try:
            person_info = searcher.parse_resume_file(filepath)
            
            if not person_info.get('name'):
                if form.name.data:
                    person_info['name'] = form.name.data
                else:
                    flash('无法从简历中识别姓名，请手动输入', 'warning')
                    os.remove(filepath)
                    return redirect(url_for('index'))
            
            person_info['source'] = 'file_upload'
            person_info['filename'] = filename
            
            os.remove(filepath)
            
            return do_search(person_info)
        except Exception as e:
            logger.exception("简历解析失败")
            flash(_friendly_error_message(e), 'danger')
            os.remove(filepath)
            return redirect(url_for('index'))
    else:
        for field, errors in form.errors.items():
            for error in errors:
                flash(f'{field}: {error}', 'danger')
        return render_template('index.html', upload_form=form, manual_form=ManualForm())

def handle_manual_input(form):
    if not request.form.get('name'):
        flash('请输入姓名', 'warning')
        return redirect(url_for('index'))
    
    person_info = {
        'name': request.form.get('name'),
        'company': request.form.get('company') or None,
        'position': request.form.get('position') or None,
        'region': request.form.get('region') or None,
        'phone': request.form.get('phone') or None,
        'source': 'manual_input'
    }
    
    return do_search(person_info)

def do_search(person_info):
    try:
        results = searcher.search(person_info)
        
        report_files = searcher.generate_report(person_info, results, formats=['excel', 'word'])
        download_files = {key: Path(value).name for key, value in report_files.items()}
        
        return render_template('results.html', 
                              person_info=person_info, 
                              results=results,
                              report_files=download_files)
    except Exception as e:
        logger.exception("搜索失败")
        flash(_friendly_error_message(e), 'danger')
        return redirect(url_for('index'))

@app.route('/download/<filename>')
def download_file(filename):
    safe_filename = os.path.basename(filename)
    return send_from_directory(OUTPUT_DIR, safe_filename, as_attachment=True)

@app.route('/api/search', methods=['POST'])
def api_search():
    data = request.get_json()
    
    if not data or not data.get('name'):
        return jsonify({'error': '缺少姓名参数'}), 400
    
    person_info = {
        'name': data.get('name'),
        'company': data.get('company') or None,
        'position': data.get('position') or None,
        'region': data.get('region') or None,
        'phone': data.get('phone') or None
    }
    
    try:
        results = searcher.search(person_info)
        return jsonify({
            'success': True,
            'person_info': person_info,
            'results': results
        })
    except Exception as e:
        logger.exception("API 搜索失败")
        return jsonify({'success': False, 'error': _friendly_error_message(e)}), 500

@app.errorhandler(413)
def handle_large_file(_error):
    flash('上传文件过大，请控制在 16MB 以内。', 'warning')
    return redirect(url_for('index'))

@app.errorhandler(500)
def handle_server_error(error):
    logger.exception("服务器内部错误")
    flash('系统异常，请稍后重试。', 'danger')
    return redirect(url_for('index'))

if __name__ == '__main__':
    debug_mode = os.environ.get('PERSON_INFO_DEBUG', '').lower() in ('1', 'true', 'yes')
    app.run(host='0.0.0.0', port=5000, debug=debug_mode)