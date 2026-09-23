from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
import os
import shutil
import mysql.connector
import bcrypt
from functools import wraps
import jwt
from datetime import datetime, timedelta

app = Flask(__name__)
CORS(app)

app.config['SECRET_KEY'] = 'your-secret-key-here'
UPLOAD_FOLDER = "uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

DB_CONFIG = {
    "host": "localhost",
    "user": "admin",
    "password": "Admin@12345",
    "database": "document_collab"
}

def get_db():
    return mysql.connector.connect(**DB_CONFIG)

def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.headers.get('Authorization')
        if not token:
            return jsonify({'message': 'Token missing'}), 401
        try:
            token = token.split(" ")[1]
            data = jwt.decode(token, app.config['SECRET_KEY'], algorithms=["HS256"])
            user_id = data['user_id']
        except:
            return jsonify({'message': 'Invalid token'}), 401
        return f(user_id, *args, **kwargs)
    return decorated

# ==================== REGISTER ====================
@app.route('/api/register', methods=['POST'])
def register():
    data = request.json
    username = data.get('username', '').strip()
    email = data.get('email', '').strip()
    password = data.get('password', '')

    if not username or not email or not password:
        return jsonify({'message': 'All fields required'}), 400

    password_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    
    try:
        db = get_db()
        cursor = db.cursor()
        cursor.execute(
            "INSERT INTO users (username, email, password_hash) VALUES (%s, %s, %s)",
            (username, email, password_hash)
        )
        db.commit()
        cursor.close()
        db.close()
        return jsonify({'message': 'Registration successful'}), 201
    except mysql.connector.Error as e:
        return jsonify({'message': f'Registration failed: {str(e)}'}), 400

# ==================== LOGIN ====================
@app.route('/api/login', methods=['POST'])
def login():
    data = request.json
    email = data.get('email', '').strip()
    password = data.get('password', '')

    db = get_db()
    cursor = db.cursor(dictionary=True)
    cursor.execute("SELECT * FROM users WHERE email = %s", (email,))
    user = cursor.fetchone()
    cursor.close()
    db.close()

    if not user:
        return jsonify({'message': 'User not found'}), 401

    if not bcrypt.checkpw(password.encode(), user['password_hash'].encode()):
        return jsonify({'message': 'Incorrect password'}), 401

    token = jwt.encode({
        'user_id': user['id'],
        'exp': datetime.utcnow() + timedelta(days=7)
    }, app.config['SECRET_KEY'], algorithm="HS256")

    return jsonify({
        'token': token,
        'user': {
            'id': user['id'],
            'username': user['username'],
            'email': user['email']
        }
    }), 200

# ==================== CREATE DOCUMENT ====================
@app.route('/api/documents', methods=['POST'])
@token_required
def create_document(user_id):
    data = request.json
    name = data.get('name', '').strip()
    content = data.get('content', '')

    if not name:
        return jsonify({'message': 'Document name required'}), 400

    filename = f"{user_id}_{name}_{datetime.now().timestamp()}"
    filepath = os.path.join(UPLOAD_FOLDER, filename)

    with open(filepath, "w", encoding="utf-8") as file:
        file.write(content)

    db = get_db()
    cursor = db.cursor()
    cursor.execute(
        "INSERT INTO documents (owner_id, document_name, file_path, document_type) VALUES (%s, %s, %s, %s)",
        (user_id, name, filepath, "text")
    )
    document_id = cursor.lastrowid
    
    cursor.execute(
        "INSERT INTO document_versions (document_id, user_id, version_number, file_path) VALUES (%s, %s, %s, %s)",
        (document_id, user_id, 1, filepath)
    )
    db.commit()
    cursor.close()
    db.close()

    return jsonify({'message': 'Document created', 'document_id': document_id}), 201

# ==================== GET MY DOCUMENTS ====================
@app.route('/api/my-documents', methods=['GET'])
@token_required
def my_documents(user_id):
    db = get_db()
    cursor = db.cursor(dictionary=True)
    cursor.execute(
        "SELECT id, document_name, document_type, created_at, updated_at FROM documents WHERE owner_id = %s ORDER BY created_at DESC",
        (user_id,)
    )
    documents = cursor.fetchall()
    cursor.close()
    db.close()

    return jsonify(documents), 200

# ==================== GET SHARED DOCUMENTS ====================
@app.route('/api/shared-documents', methods=['GET'])
@token_required
def shared_documents(user_id):
    db = get_db()
    cursor = db.cursor(dictionary=True)
    cursor.execute("""
        SELECT d.id, d.document_name, u.username AS owner, p.permission
        FROM document_permissions p
        JOIN documents d ON p.document_id = d.id
        JOIN users u ON d.owner_id = u.id
        WHERE p.user_id = %s
    """, (user_id,))
    documents = cursor.fetchall()
    cursor.close()
    db.close()

    return jsonify(documents), 200

# ==================== VIEW DOCUMENT ====================
@app.route('/api/documents/<int:document_id>', methods=['GET'])
@token_required
def view_document(user_id, document_id):
    db = get_db()
    cursor = db.cursor(dictionary=True)
    
    # Check ownership or permission
    cursor.execute(
        "SELECT * FROM documents WHERE id = %s AND owner_id = %s",
        (document_id, user_id)
    )
    document = cursor.fetchone()
    
    if not document:
        cursor.execute("""
            SELECT d.*, p.permission FROM documents d
            JOIN document_permissions p ON d.id = p.document_id
            WHERE d.id = %s AND p.user_id = %s
        """, (document_id, user_id))
        document = cursor.fetchone()
    
    cursor.close()
    db.close()
    
    if not document:
        return jsonify({'message': 'Access denied'}), 403

    try:
        with open(document['file_path'], 'r', encoding='utf-8') as f:
            content = f.read()
        return jsonify({'content': content, 'permission': document.get('permission', 'owner')}), 200
    except:
        return jsonify({'message': 'File not found'}), 404

# ==================== EDIT DOCUMENT ====================
@app.route('/api/documents/<int:document_id>', methods=['PUT'])
@token_required
def edit_document(user_id, document_id):
    data = request.json
    content = data.get('content', '')

    db = get_db()
    cursor = db.cursor(dictionary=True)
    
    cursor.execute(
        "SELECT * FROM documents WHERE id = %s AND owner_id = %s",
        (document_id, user_id)
    )
    document = cursor.fetchone()
    
    if not document:
        cursor.execute("""
            SELECT * FROM document_permissions WHERE document_id = %s AND user_id = %s
        """, (document_id, user_id))
        perm = cursor.fetchone()
        if not perm or perm['permission'] != 'editor':
            cursor.close()
            db.close()
            return jsonify({'message': 'No edit permission'}), 403

    with open(document['file_path'], 'w', encoding='utf-8') as f:
        f.write(content)

    cursor.execute(
        "SELECT MAX(version_number) FROM document_versions WHERE document_id = %s",
        (document_id,)
    )
    result = cursor.fetchone()
    latest_version = (result[0] or 0) + 1

    cursor.execute(
        "INSERT INTO document_versions (document_id, user_id, version_number, file_path) VALUES (%s, %s, %s, %s)",
        (document_id, user_id, latest_version, document['file_path'])
    )
    db.commit()
    cursor.close()
    db.close()

    return jsonify({'message': 'Document updated', 'version': latest_version}), 200

# ==================== SHARE DOCUMENT ====================
@app.route('/api/documents/<int:document_id>/share', methods=['POST'])
@token_required
def share_document(user_id, document_id):
    data = request.json
    email = data.get('email', '').strip()
    permission = data.get('permission', 'viewer')

    if permission not in ['viewer', 'editor']:
        return jsonify({'message': 'Invalid permission'}), 400

    db = get_db()
    cursor = db.cursor()
    
    # Check ownership
    cursor.execute("SELECT id FROM documents WHERE id = %s AND owner_id = %s", (document_id, user_id))
    if not cursor.fetchone():
        cursor.close()
        db.close()
        return jsonify({'message': 'Not your document'}), 403

    # Get user
    cursor.execute("SELECT id FROM users WHERE email = %s", (email,))
    target_user = cursor.fetchone()
    if not target_user:
        cursor.close()
        db.close()
        return jsonify({'message': 'User not found'}), 404

    cursor.execute(
        "INSERT INTO document_permissions (document_id, user_id, permission) VALUES (%s, %s, %s)",
        (document_id, target_user[0], permission)
    )
    db.commit()
    cursor.close()
    db.close()

    return jsonify({'message': 'Document shared'}), 200

if __name__ == '__main__':
    app.run(debug=True, port=5000)