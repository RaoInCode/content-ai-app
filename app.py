# app.py
# This is the main application file. It handles web requests, user authentication,
# and connects the frontend to the backend logic.

import os
from flask import Flask, request, jsonify, render_template, redirect, url_for
from dotenv import load_dotenv
from models import db, User
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from cryptography.fernet import Fernet
# existing imports...
from main_logic import (
    run_full_analysis,
    generate_groq_recommendations,
    get_threads_profile,
    fetch_user_threads,
    fetch_replies,
    analyze_replies_sentiment
)

# Load environment variables from .env file for local development
load_dotenv()

# Initialize the main Flask application
app = Flask(__name__)

# --- App Configuration ---
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY')
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# --- Initialize Extensions (Database & Login Manager) ---
db.init_app(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

@login_manager.user_loader
def load_user(user_id):
    """This function is used by Flask-Login to load the current user from the database."""
    return User.query.get(int(user_id))

# --- Security Functions for Token Encryption ---
def get_cipher():
    """Gets the encryption cipher using the key from the environment."""
    key_string = os.environ.get('ENCRYPTION_KEY')
    if not key_string:
        raise ValueError("ENCRYPTION_KEY is not set in the environment!")
    
    # --- THIS IS THE CRITICAL FIX ---
    # The key is read as a plain string from .env. We must convert it to bytes.
    key_bytes = key_string.encode('utf-8')
    return Fernet(key_bytes)

def encrypt_token(token):
    """Encrypts a token."""
    cipher = get_cipher()
    return cipher.encrypt(token.encode('utf-8')).decode('utf-8')

def decrypt_token(encrypted_token):
    """Decrypts a token."""
    if not encrypted_token:
        return None
    cipher = get_cipher()
    return cipher.decrypt(encrypted_token.encode('utf-8')).decode('utf-8')

# ==============================================================================
# SECTION 1: HTML SERVING ROUTES (The Pages Users See)
# ==============================================================================

# ==============================================================================
# SECTION 1: PAGE ROUTES (Frontend templates)
# ==============================================================================

@app.route('/')
def index():
    """Landing/home page describing the product and options."""
    return render_template('landing.html')

@app.route('/login')
def login():
    """Serves the login page."""
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    return render_template('login.html')

@app.route('/register')
def register():
    """Serves the registration page."""
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    return render_template('register.html')

@app.route('/dashboard')
@login_required
def dashboard():
    """Serves the main application dashboard (keyword recommendations)."""
    return render_template('dashboard.html')

@app.route('/account')
@login_required
def account():
    """Serves the user's account page."""
    return render_template('account.html')

@app.route('/threads')
@login_required
def threads_page():
    """Page where the user can analyze their Threads posts (requires login)."""
    return render_template('threads.html')


# ==============================================================================
# SECTION 2: API ENDPOINTS (The Logic Behind the Forms)
# ==============================================================================

@app.route('/api/register', methods=['POST'])
def api_register():
    """Handles the registration form submission."""
    data = request.get_json()
    username = data.get('username')
    password = data.get('password')

    if not username or not password:
        return jsonify({"error": "Username and password are required."}), 400

    if User.query.filter_by(username=username).first():
        return jsonify({"error": "Username already taken."}), 409

    new_user = User(username=username)
    new_user.set_password(password)
    db.session.add(new_user)
    db.session.commit()
    return jsonify({"message": "Account created successfully. Please log in."}), 201

@app.route('/api/login', methods=['POST'])
def api_login():
    """Handles the login form submission."""
    data = request.get_json()
    username = data.get('username')
    password = data.get('password')
    user = User.query.filter_by(username=username).first()

    if user and user.check_password(password):
        login_user(user, remember=True)
        return jsonify({"message": "Logged in successfully."}), 200
    
    return jsonify({"error": "Invalid username or password."}), 401

@app.route('/api/logout', methods=['POST'])
@login_required
def api_logout():
    """Logs the current user out."""
    logout_user()
    return jsonify({"message": "Logged out successfully."}), 200

@app.route('/api/update_token', methods=['POST'])
@login_required
def api_update_token():
    """Updates the Threads token for the current user."""
    data = request.get_json()
    token = data.get('token')
    if not token:
        return jsonify({"error": "Token is required."}), 400

    try:
        current_user.encrypted_threads_token = encrypt_token(token)
        db.session.commit()
        return jsonify({"message": "Token updated successfully."}), 200
    except Exception as e:
        print(f"ERROR in api_update_token: {e}") 
        return jsonify({"error": "An internal error occurred while saving the token."}), 500

@app.route('/api/analyze', methods=['POST'])
@login_required
def api_analyze():
    """The main endpoint to run the keyword-based analysis for the logged-in user."""
    keyword = request.json.get('keyword')
    if not keyword:
        return jsonify({"error": "Keyword is required"}), 400

    user_threads_token = decrypt_token(current_user.encrypted_threads_token)
    if not user_threads_token:
        return jsonify({"error": "Please add your Threads Access Token in the Account page first."}), 400

    analysis_data = run_full_analysis(user_threads_token, keyword)
    if "error" in analysis_data:
        return jsonify(analysis_data), 500

    ai_recommendation = generate_groq_recommendations(analysis_data, keyword)
    analysis_data['ai_recommendation'] = ai_recommendation
    
    return jsonify(analysis_data)


# ----- NEW THREADS ANALYSIS API ENDPOINTS -----

@app.route('/api/account_info', methods=['GET'])
@login_required
def api_account_info():
    """Return whether the current user has a token and (if present) some profile info."""
    if not current_user.encrypted_threads_token:
        return jsonify({"has_token": False, "message": "No token saved."}), 200
    try:
        token = decrypt_token(current_user.encrypted_threads_token)
        profile = get_threads_profile(token)
        return jsonify({"has_token": True, "profile": profile})
    except Exception as e:
        return jsonify({"has_token": False, "error": str(e)}), 500


@app.route('/api/fetch_threads', methods=['POST'])
@login_required
def api_fetch_threads():
    """Fetch the current user's threads using saved token."""
    data = request.get_json() or {}
    limit = int(data.get("limit", 3))
    since = data.get("since") or None
    until = data.get("until", "now")

    if not current_user.encrypted_threads_token:
        return jsonify({"error": "Please add your Threads Access Token in the Account page first."}), 400
    try:
        token = decrypt_token(current_user.encrypted_threads_token)
        threads_json = fetch_user_threads(token, limit=limit, since=since, until=until)
        return jsonify(threads_json)
    except Exception as e:
        print(f"ERROR in api_fetch_threads: {e}")
        return jsonify({"error": "An internal error occurred while fetching threads."}), 500


@app.route('/api/analyze_post', methods=['POST'])
@login_required
def api_analyze_post():
    """Fetch replies for a post and run sentiment analysis."""
    data = request.get_json() or {}
    post_id = data.get("post_id")
    if not post_id:
        return jsonify({"error": "post_id is required"}), 400
    if not current_user.encrypted_threads_token:
        return jsonify({"error": "Please add your Threads Access Token in the Account page first."}), 400
    try:
        token = decrypt_token(current_user.encrypted_threads_token)
        replies_json = fetch_replies(token, post_id)
        if "error" in replies_json:
            return jsonify(replies_json), 500
        replies_list = replies_json.get("data", [])
        analysis = analyze_replies_sentiment(replies_list)
        return jsonify({"replies": replies_list, "analysis": analysis})
    except Exception as e:
        print(f"ERROR in api_analyze_post: {e}")
        return jsonify({"error": "An internal error occurred during sentiment analysis."}), 500

# This block allows you to run the app directly using 'python app.py'
if __name__ == '__main__':
    # Creates the database tables from your models if they don't exist yet
    with app.app_context():
        db.create_all()
    app.run(debug=True)