import subprocess
import sys
import os
import sqlite3
import bcrypt
import jwt
import time
import logging
from datetime import datetime, timedelta
from flask import Flask, request, jsonify
from flask_cors import CORS
from functools import wraps

class Config:
    # Server Settings
    PORT = int(os.environ.get('APP_PORT', 5000))
    HOST = os.environ.get('APP_HOST', '0.0.0.0')
    DEBUG = os.environ.get('APP_DEBUG', 'False').lower() == 'true'
    
    # Security
    JWT_SECRET = os.environ.get('APP_JWT_SECRET')
    ALLOWED_ORIGINS = os.environ.get('APP_ALLOWED_ORIGINS', 'http://0.0.0.0:3000,http://localhost:3000,http://127.0.0.1:3000').split(',')
    
    # Database
    DB_PATH = os.environ.get('APP_DB_PATH', 'users.db')
    
    # Logging
    LOG_LEVEL = os.environ.get('APP_LOG_LEVEL', 'INFO')
    MAX_LOG_LINES = int(os.environ.get('APP_MAX_LOG_LINES', 1000))
    
    # Frontend Settings
    FRONTEND_PORT = int(os.environ.get('APP_FRONTEND_PORT', 3000))
    FRONTEND_HOST = os.environ.get('APP_FRONTEND_HOST', '0.0.0.0')
    
    # Retry Settings
    COMMAND_TIMEOUT = int(os.environ.get('APP_COMMAND_TIMEOUT', 30))
    MAX_RETRIES = int(os.environ.get('APP_MAX_RETRIES', 3))
    RETRY_DELAY = int(os.environ.get('APP_RETRY_DELAY', 1))

    @classmethod
    def setup_logging(cls):
        logging.basicConfig(
            level=getattr(logging, cls.LOG_LEVEL.upper()),
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            handlers=[
                logging.StreamHandler(),
                logging.FileHandler('app.log')
            ]
        )

    @classmethod
    def validate(cls):
        if not cls.JWT_SECRET:
            raise ValueError("APP_JWT_SECRET environment variable must be set")

    @classmethod
    def get_frontend_url(cls):
        return f'http://{cls.FRONTEND_HOST}:{cls.FRONTEND_PORT}'

def start_frontend():
    frontend_url = Config.get_frontend_url()
    os.environ['REACT_APP_API_URL'] = f'http://{Config.HOST}:{Config.PORT}'
    retries = 0
    
    while retries < Config.MAX_RETRIES:
        try:
            process = subprocess.Popen(
                ['npm', 'run', 'dev'], 
                cwd='../frontend',
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=os.environ.copy()
            )
            
            try:
                process.wait(timeout=Config.COMMAND_TIMEOUT)
                logging.info(f"Frontend started successfully at {frontend_url}")
                return
            except subprocess.TimeoutExpired:
                process.kill()
                
            retries += 1
            if retries < Config.MAX_RETRIES:
                logging.warning(f"Frontend start attempt {retries} failed, retrying in {Config.RETRY_DELAY} seconds...")
                time.sleep(Config.RETRY_DELAY)
                
        except Exception as e:
            logging.error(f"Failed to start frontend: {e}")
            retries += 1
            if retries < Config.MAX_RETRIES:
                time.sleep(Config.RETRY_DELAY)
            else:
                raise RuntimeError(f"Failed to start frontend after {Config.MAX_RETRIES} attempts")

def create_app():
    Config.setup_logging()
    try:
        Config.validate()
        start_frontend()
    except ValueError as e:
        logging.error(f"Configuration Error: {e}")
        sys.exit(1)

    app = Flask(__name__)
    CORS(app, origins=Config.ALLOWED_ORIGINS)
    return app

app = create_app()

def init_db():
    conn = sqlite3.connect(Config.DB_PATH)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS users
        (id INTEGER PRIMARY KEY AUTOINCREMENT,
         username TEXT UNIQUE NOT NULL,
         password TEXT NOT NULL,
         created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
         last_login TIMESTAMP)
    ''')
    conn.commit()
    conn.close()

def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.headers.get('Authorization')
        if not token:
            return jsonify({'error': 'Token is missing'}), 401
        
        try:
            token = token.split(' ')[1]
            data = jwt.decode(token, Config.JWT_SECRET, algorithms=["HS256"])
            conn = sqlite3.connect(Config.DB_PATH)
            c = conn.cursor()
            c.execute('SELECT * FROM users WHERE id = ?', (data['user_id'],))
            current_user = c.fetchone()
            conn.close()
            
            if not current_user:
                return jsonify({'error': 'Invalid token'}), 401
            return f(current_user, *args, **kwargs)
        except Exception as e:
            logging.error(f"Token validation error: {e}")
            return jsonify({'error': 'Invalid token'}), 401
    return decorated

@app.route('/api/register', methods=['POST'])
def register():
    data = request.json
    username = data.get('username')
    password = data.get('password')
    
    if not username or not password:
        return jsonify({'error': 'Missing credentials'}), 400
    
    hashed = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())
    
    try:
        conn = sqlite3.connect(Config.DB_PATH)
        c = conn.cursor()
        c.execute('INSERT INTO users (username, password) VALUES (?, ?)',
                 (username, hashed))
        conn.commit()
        conn.close()
        logging.info(f"User registered successfully: {username}")
        return jsonify({'message': 'User registered successfully'}), 201
    except sqlite3.IntegrityError:
        logging.warning(f"Registration failed - username exists: {username}")
        return jsonify({'error': 'Username already exists'}), 409
    except Exception as e:
        logging.error(f"Registration error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/login', methods=['POST'])
def login():
    data = request.json
    username = data.get('username')
    password = data.get('password')
    
    if not username or not password:
        return jsonify({'error': 'Missing credentials'}), 400
    
    try:
        conn = sqlite3.connect(Config.DB_PATH)
        c = conn.cursor()
        c.execute('SELECT id, password FROM users WHERE username = ?', (username,))
        result = c.fetchone()
        
        if result and bcrypt.checkpw(password.encode('utf-8'), result[1]):
            c.execute('UPDATE users SET last_login = CURRENT_TIMESTAMP WHERE id = ?', (result[0],))
            conn.commit()
            
            token = jwt.encode({
                'user_id': result[0],
                'exp': datetime.utcnow() + timedelta(days=1)
            }, Config.JWT_SECRET)
            
            conn.close()
            logging.info(f"User logged in successfully: {username}")
            return jsonify({'token': token}), 200
            
        conn.close()
        logging.warning(f"Login failed for user: {username}")
        return jsonify({'error': 'Invalid credentials'}), 401
    except Exception as e:
        logging.error(f"Login error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/user', methods=['GET'])
@token_required
def get_user(current_user):
    try:
        conn = sqlite3.connect(Config.DB_PATH)
        c = conn.cursor()
        c.execute('''
            SELECT id, username, created_at, last_login 
            FROM users WHERE id = ?
        ''', (current_user[0],))
        user = c.fetchone()
        conn.close()
        
        if user:
            return jsonify({
                'id': user[0],
                'username': user[1],
                'createdAt': user[2],
                'lastLogin': user[3]
            })
        return jsonify({'error': 'User not found'}), 404
    except Exception as e:
        logging.error(f"Error fetching user data: {e}")
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    init_db()
    app.run(
        host=Config.HOST,
        port=Config.PORT,
        debug=Config.DEBUG
    )