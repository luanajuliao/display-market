from flask import Flask, render_template, request, redirect, url_for, flash, session
from pymongo import MongoClient
from bson.objectid import ObjectId
import os
from werkzeug.utils import secure_filename
import uuid
from flask_socketio import SocketIO, emit
from dotenv import load_dotenv
from functools import wraps
import datetime
from werkzeug.security import generate_password_hash, check_password_hash
from PIL import Image # Para manipulação de imagens


# Configuração inicial

load_dotenv()
app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "sua_chave_secreta_aqui")
socketio = SocketIO(app, cors_allowed_origins="*")

# MongoDB
MONGO_URI = "mongodb+srv://<usuario>:<senha>@cluster0.xxxxx.mongodb.net/display_market?retryWrites=true&w=majority"
client = MongoClient(MONGO_URI)
db = client["display_market"]
layouts_collection = db["layouts"]
stores_collection = db["stores"]
tvs_collection = db["tvs"]
users_collection = db["users"]

# Uploads
UPLOAD_FOLDER = "static/uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('logged_in'):
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def process_image(filepath):
    """Redimensiona a imagem mantendo proporções para melhor performance"""
    try:
        img = Image.open(filepath)
        img.thumbnail((1920, 1080))  # Máximo Full HD
        img.save(filepath, optimize=True, quality=85)
    except Exception as e:
        print(f"Erro ao processar imagem: {e}")

# --- Rotas Públicas ---

@app.route('/')
def root():
    if session.get('logged_in'):
        return redirect(url_for('stores'))
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        user = users_collection.find_one({"username": username})
        
        if user and check_password_hash(user['password'], password):
            session['logged_in'] = True
            session['user_id'] = str(user['_id'])
            return redirect(url_for('stores'))
        flash('Usuário ou senha incorretos', 'error')
    return render_template('login.html')

# --- Rotas Protegidas ---

@app.route('/stores')
@login_required
def stores():
    stores_list = list(stores_collection.find())
    return render_template('stores.html', stores=stores_list)

@app.route('/settings')
@login_required
def settings():
    users = list(users_collection.find({}, {"password": 0}))
    return render_template('settings.html', users=users)

@app.route('/store/<store_id>/tvs')
@login_required
def store_tvs(store_id):
    try:
        if not ObjectId.is_valid(store_id):
            flash("ID da loja inválido", "error")
            return redirect(url_for('stores'))
        
        store = stores_collection.find_one({"_id": ObjectId(store_id)})
        if not store:
            flash("Loja não encontrada", "error")
            return redirect(url_for('stores'))
        
        tvs_list = list(tvs_collection.find({"store_id": ObjectId(store_id)}))
        
        return render_template('store_tvs.html', 
                            tvs=tvs_list, 
                            store_id=store_id,
                            store_name=store.get('name', 'Sem nome'))
    
    except Exception as e:
        flash(f"Erro ao carregar TVs: {str(e)}", "error")
        return redirect(url_for('stores'))

@app.route('/dashboard/<tv_id>')
@login_required
def dashboard(tv_id):
    try:
        tv = tvs_collection.find_one({"_id": ObjectId(tv_id)})
        if not tv:
            flash("TV não encontrada", "error")
            return redirect(url_for('stores'))
        
        # Busca todos os layouts para esta TV
        layouts = list(layouts_collection.find({"tv_id": ObjectId(tv_id)}).sort("created_at", 1))
        
        return render_template('dashboard.html', 
                            layouts=layouts, 
                            tv_id=tv_id,
                            store_id=str(tv['store_id']))
    except Exception as e:
        flash(f"Erro ao acessar dashboard: {str(e)}", "error")
        return redirect(url_for('stores'))


# --- CRUD Lojas ---

@app.route('/add_store', methods=['POST'])
@login_required
def add_store():
    name = request.form.get('name')
    if not name:
        flash('Nome da loja é obrigatório', 'error')
        return redirect(url_for('stores'))
    
    stores_collection.insert_one({"name": name})
    flash('Loja adicionada com sucesso', 'success')
    return redirect(url_for('stores'))

@app.route('/edit_store/<store_id>', methods=['POST'])
@login_required
def edit_store(store_id):
    try:
        new_name = request.form.get('name')
        if not new_name:
            flash('Nome da loja é obrigatório', 'error')
            return redirect(url_for('stores'))
            
        stores_collection.update_one(
            {"_id": ObjectId(store_id)},
            {"$set": {"name": new_name}}
        )
        flash('Loja atualizada com sucesso', 'success')
    except:
        flash('Erro ao atualizar loja', 'error')
    return redirect(url_for('stores'))

@app.route('/delete_store/<store_id>', methods=['POST'])
@login_required
def delete_store(store_id):
    try:
        tvs = list(tvs_collection.find({"store_id": ObjectId(store_id)}))
        for tv in tvs:
            layouts_collection.delete_many({"tv_id": tv["_id"]})
        
        tvs_collection.delete_many({"store_id": ObjectId(store_id)})
        stores_collection.delete_one({"_id": ObjectId(store_id)})
        
        flash('Loja removida com sucesso', 'success')
    except:
        flash('Erro ao remover loja', 'error')
    return redirect(url_for('stores'))

# --- CRUD TVs ---

@app.route('/store/<store_id>/add_tv', methods=['POST'])
@login_required
def add_tv(store_id):
    try:
        name = request.form.get('name')
        if not name:
            flash('Nome da TV é obrigatório', 'error')
            return redirect(url_for('store_tvs', store_id=store_id))
            
        tvs_collection.insert_one({
            "name": name,
            "store_id": ObjectId(store_id)
        })
        flash('TV adicionada com sucesso', 'success')
    except:
        flash('Erro ao adicionar TV', 'error')
    return redirect(url_for('store_tvs', store_id=store_id))

@app.route('/edit_tv/<tv_id>', methods=['POST'])
@login_required
def edit_tv(tv_id):
    try:
        tv = tvs_collection.find_one({"_id": ObjectId(tv_id)})
        if not tv:
            flash('TV não encontrada', 'error')
            return redirect(url_for('stores'))
            
        new_name = request.form.get('name')
        if not new_name:
            flash('Nome da TV é obrigatório', 'error')
            return redirect(url_for('store_tvs', store_id=tv["store_id"]))
            
        tvs_collection.update_one(
            {"_id": ObjectId(tv_id)},
            {"$set": {"name": new_name}}
        )
        flash('TV atualizada com sucesso', 'success')
        return redirect(url_for('store_tvs', store_id=tv["store_id"]))
    except:
        flash('Erro ao atualizar TV', 'error')
        return redirect(url_for('stores'))

@app.route('/delete_tv/<tv_id>', methods=['POST'])
@login_required
def delete_tv(tv_id):
    try:
        tv = tvs_collection.find_one({"_id": ObjectId(tv_id)})
        if not tv:
            flash('TV não encontrada', 'error')
            return redirect(url_for('stores'))
            
        layouts_collection.delete_many({"tv_id": ObjectId(tv_id)})
        tvs_collection.delete_one({"_id": ObjectId(tv_id)})
        
        flash('TV removida com sucesso', 'success')
        return redirect(url_for('store_tvs', store_id=tv["store_id"]))
    except:
        flash('Erro ao remover TV', 'error')
        return redirect(url_for('stores'))

# --- CRUD Layouts ---

@app.route('/upload/<tv_id>', methods=['POST'])
@login_required
def upload(tv_id):
    if 'image' not in request.files:
        flash('Nenhum arquivo enviado', 'error')
        return redirect(url_for('dashboard', tv_id=tv_id))

    file = request.files['image']
    layout_name = request.form.get('layout_name', '').strip()
    
    if file.filename == '':
        flash('Nenhum arquivo selecionado', 'error')
        return redirect(url_for('dashboard', tv_id=tv_id))

    if not layout_name:
        flash('Nome do layout é obrigatório', 'error')
        return redirect(url_for('dashboard', tv_id=tv_id))

    if file and allowed_file(file.filename):
        try:
            # Gera nome único para o arquivo
            filename = secure_filename(file.filename)
            unique_filename = f"{uuid.uuid4()}_{filename}"
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], unique_filename)
            file.save(filepath)
            process_image(filepath)  # Processa a imagem

            new_layout = {
                "name": layout_name,
                "image": unique_filename,
                "tv_id": ObjectId(tv_id),
                "products": [],
                "created_at": datetime.datetime.now()
            }
            layouts_collection.insert_one(new_layout)
            
            flash('Novo layout adicionado com sucesso!', 'success')
        except Exception as e:
            flash(f'Erro ao fazer upload: {str(e)}', 'error')
    else:
        flash('Tipo de arquivo não permitido (use apenas PNG, JPG, JPEG)', 'error')

    return redirect(url_for('dashboard', tv_id=tv_id))

@app.route('/rename_layout/<layout_id>', methods=['GET', 'POST'])
@login_required
def rename_layout(layout_id):
    if request.method == 'POST':
        new_name = request.form.get('nome_layout')
        tv_id = request.form.get('tv_id')
        
        if new_name:
            layouts_collection.update_one(
                {"_id": ObjectId(layout_id)},
                {"$set": {"name": new_name}}
            )
            flash('Nome do layout atualizado com sucesso!', 'success')
        return redirect(url_for('dashboard', tv_id=tv_id))
    
    layout = layouts_collection.find_one({"_id": ObjectId(layout_id)})
    tv_id = request.args.get('tv_id')
    return render_template('rename_layout.html', 
                         layout_id=layout_id, 
                         current_name=layout.get('name', ''),
                         tv_id=tv_id)

@app.route('/delete_layout/<layout_id>', methods=['POST'])
@login_required
def delete_layout(layout_id):
    try:
        layout = layouts_collection.find_one({"_id": ObjectId(layout_id)})
        if layout:
            if 'image' in layout:
                os.remove(os.path.join(app.config['UPLOAD_FOLDER'], layout['image']))
            layouts_collection.delete_one({"_id": ObjectId(layout_id)})
            flash('Layout removido com sucesso!', 'success')
        return redirect(url_for('dashboard', tv_id=str(layout['tv_id'])))
    except Exception as e:
        flash(f'Erro ao remover layout: {str(e)}', 'error')
        return redirect(url_for('stores'))
    
@app.route("/get_layout_data")
def get_layout_data():
    try:
        layout_id = request.args.get('layout_id')
        if not layout_id or not ObjectId.is_valid(layout_id):
            return {"error": "ID inválido"}, 400
        
        layout = layouts_collection.find_one({"_id": ObjectId(layout_id)})
        if not layout:
            return {"error": "Layout não encontrado"}, 404
        
        return {
            "image": layout.get("image", ""),
            "products": layout.get("products", [])
        }
    
    except Exception as e:
        print(f"Erro em get_layout_data: {str(e)}")
        return {"error": "Erro interno"}, 500

# --- CRUD Produtos ---
@app.route("/add_produto/<layout_id>", methods=["POST"])
@login_required
def add_produto(layout_id):
    try:
        layout = layouts_collection.find_one({"_id": ObjectId(layout_id)})
        if not layout:
            flash('Layout não encontrado', 'error')
            return redirect(url_for('stores'))
        
        tv_id = str(layout['tv_id'])

        # Cria um novo produto com os dados do formulário
        novo_produto = {
            "nome": request.form["nome"],
            "preco": float(request.form["preco"].replace(",", ".")),
            "cor_fundo": request.form["cor_fundo"],
            "cor_fonte": request.form["cor_fonte"],
            "tamanho": int(request.form["tamanho"]),
            "sem_fundo": "sem_fundo" in request.form
        }

        # Adiciona o produto apenas ao layout específico
        layouts_collection.update_one(
            {"_id": ObjectId(layout_id)},
            {"$push": {"products": novo_produto}}
        )
        
        socketio.emit("refresh", {"layout_id": layout_id})
        return redirect(url_for('dashboard', tv_id=tv_id))
    
    except Exception as e:
        flash(f"Erro ao adicionar produto: {str(e)}", "error")
        return redirect(url_for('stores'))

@app.route("/edit_produto/<layout_id>/<int:index>", methods=["GET", "POST"])
@login_required
def edit_produto(layout_id, index):
    try:
        layout = layouts_collection.find_one({"_id": ObjectId(layout_id)})
        if not layout:
            flash('Layout não encontrado', 'error')
            return redirect(url_for('stores'))
        
        produtos = layout.get("products", [])
        if index >= len(produtos):
            flash('Índice do produto inválido', 'error')
            return redirect(url_for('stores'))

        if request.method == 'POST':
            # Processar o formulário de edição
            produtos[index] = {
                "nome": request.form["nome"],
                "preco": float(request.form["preco"].replace(",", ".")),
                "cor_fundo": request.form["cor_fundo"],
                "cor_fonte": request.form["cor_fonte"],
                "tamanho": int(request.form["tamanho"]),
                "sem_fundo": "sem_fundo" in request.form
            }

            layouts_collection.update_one(
                {"_id": ObjectId(layout_id)},
                {"$set": {"products": produtos}}
            )
            
            flash('Produto atualizado com sucesso!', 'success')
            return redirect(url_for('dashboard', tv_id=request.form.get('tv_id')))
        
        # GET - Mostrar formulário de edição
        produto = produtos[index]
        tv_id = request.args.get('tv_id')
        return render_template('edit_produto.html',
                            produto=produto,
                            layout_id=layout_id,
                            index=index,
                            tv_id=tv_id)
    
    except Exception as e:
        flash(f"Erro ao editar produto: {str(e)}", "error")
        return redirect(url_for('stores'))
    

@app.route("/delete_produto/<layout_id>/<int:index>", methods=["POST"])
@login_required
def delete_produto(layout_id, index):
    try:
        layout = layouts_collection.find_one({"_id": ObjectId(layout_id)})
        if not layout:
            flash('Layout não encontrado', 'error')
            return redirect(url_for('stores'))
        
        produtos = layout.get("products", [])
        if index >= len(produtos):
            flash('Índice do produto inválido', 'error')
            return redirect(url_for('dashboard', tv_id=str(layout['tv_id'])))

        # Remove apenas o produto específico deste layout
        produtos.pop(index)
        
        layouts_collection.update_one(
            {"_id": ObjectId(layout_id)},
            {"$set": {"products": produtos}}
        )
        
        socketio.emit("refresh", {"layout_id": layout_id})
        return redirect(url_for('dashboard', tv_id=str(layout['tv_id'])))
    
    except Exception as e:
        flash(f"Erro ao excluir produto: {str(e)}", "error")
        return redirect(url_for('stores'))
    
# --- TV Display ---
@app.route("/tv")
def tv():
    tv_id = request.args.get('tv_id')
    preview = request.args.get('preview', '').lower() == 'true'
    
    if not tv_id or not ObjectId.is_valid(tv_id):
        return redirect(url_for('stores'))
    
    try:
        tv = tvs_collection.find_one({"_id": ObjectId(tv_id)})
        if not tv:
            return redirect(url_for('stores'))
        
        layouts = list(layouts_collection.find({"tv_id": ObjectId(tv_id)}).sort("created_at", 1))
        
        if not layouts:
            return render_template("tv.html", 
                                tv_name=tv.get("name", ""),
                                layouts=[],
                                current_layout=None,
                                preview=preview)
        
        # Calcula o índice do layout atual baseado no tempo
        seconds = int(datetime.datetime.now().timestamp())
        layout_index = (seconds // 10) % len(layouts)
        current_layout = layouts[layout_index]
        
        # Prepara os dados para o template
        serializable_layouts = []
        for layout in layouts:
            serializable_layout = {
                "id": str(layout["_id"]),
                "image": layout.get("image", ""),
                "products": layout.get("products", [])
            }
            serializable_layouts.append(serializable_layout)
        
        return render_template("tv.html", 
                            tv_name=tv.get("name", ""),
                            layouts=serializable_layouts,
                            current_layout_index=layout_index,
                            preview=preview)
    
    except Exception as e:
        print(f"Erro na rota /tv: {str(e)}")
        return redirect(url_for('stores'))
    
# --- User Management ---
@app.route('/add_user', methods=['POST'])
@login_required
def add_user():
    try:
        username = request.form.get('username')
        password = request.form.get('password')
        
        if not username or not password:
            flash('Usuário e senha são obrigatórios', 'error')
            return redirect(url_for('settings'))
            
        if users_collection.find_one({"username": username}):
            flash('Usuário já existe', 'error')
            return redirect(url_for('settings'))
            
        users_collection.insert_one({
            "username": username,
            "password": generate_password_hash(password)
        })
        flash('Usuário adicionado com sucesso', 'success')
    except Exception as e:
        flash(f'Erro ao adicionar usuário: {str(e)}', 'error')
    return redirect(url_for('settings'))

@app.route('/edit_user/<user_id>', methods=['POST'])
@login_required
def edit_user(user_id):
    try:
        new_username = request.form.get('username')
        new_password = request.form.get('password')
        
        if not new_username:
            flash('Nome de usuário é obrigatório', 'error')
            return redirect(url_for('settings'))
            
        update_data = {"username": new_username}
        if new_password:
            update_data["password"] = generate_password_hash(new_password)
            
        users_collection.update_one(
            {"_id": ObjectId(user_id)},
            {"$set": update_data}
        )
        flash('Usuário atualizado com sucesso', 'success')
    except Exception as e:
        flash(f'Erro ao atualizar usuário: {str(e)}', 'error')
    return redirect(url_for('settings'))

@app.route('/delete_user/<user_id>', methods=['POST'])
@login_required
def delete_user(user_id):
    try:
        if str(session.get('user_id')) == user_id:
            flash('Você não pode excluir seu próprio usuário', 'error')
            return redirect(url_for('settings'))
            
        users_collection.delete_one({"_id": ObjectId(user_id)})
        flash('Usuário removido com sucesso', 'success')
    except Exception as e:
        flash(f'Erro ao remover usuário: {str(e)}', 'error')
    return redirect(url_for('settings'))

@app.route('/change_password', methods=['POST'])
@login_required
def change_password():
    try:
        current_password = request.form.get('current_password')
        new_password = request.form.get('new_password')
        
        user = users_collection.find_one({"_id": ObjectId(session.get('user_id'))})
        if not user or not check_password_hash(user['password'], current_password):
            flash('Senha atual incorreta', 'error')
            return redirect(url_for('settings'))
            
        users_collection.update_one(
            {"_id": ObjectId(session.get('user_id'))},
            {"$set": {"password": generate_password_hash(new_password)}}
        )
        flash('Senha alterada com sucesso', 'success')
    except Exception as e:
        flash(f'Erro ao alterar senha: {str(e)}', 'error')
    return redirect(url_for('settings'))

@app.route('/logout')
def logout():
    session.pop('logged_in', None)
    session.pop('user_id', None)
    return redirect(url_for('login'))

# --- WebSockets e API ---
@socketio.on("connect")
def handle_connect():
    print("Cliente conectado à TV:", request.sid)

@app.route("/api/layouts", methods=["GET"])
def get_layouts():
    layouts = list(layouts_collection.find({}, {"_id": 0}))
    return {"layouts": layouts}

if __name__ == '__main__':
    # Criar usuário admin padrão se não existir
    if not users_collection.find_one({"username": "admin"}):
        users_collection.insert_one({
            "username": "admin",
            "password": generate_password_hash("admin")
        })
    
    socketio.run(app, host='0.0.0.0', port=5000, debug=True)