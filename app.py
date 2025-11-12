from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, session
from flask_socketio import SocketIO, emit, join_room, leave_room
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from models import db, User, Message, ChatRoom, chat_members
from datetime import datetime
from cryptography.fernet import Fernet
import pytz
import os
import uuid
from flask import send_file
import io
from flask_cors import CORS
from flask_mail import Mail, Message as MailMessage
from itsdangerous import URLSafeTimedSerializer, SignatureExpired, BadTimeSignature
import random
from dotenv import load_dotenv
from werkzeug.utils import secure_filename
from PIL import Image
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.backends import default_backend

# --- Load .env file ---
load_dotenv()

# --- Flask setup ---
app = Flask(__name__)
CORS(app, supports_credentials=True)

# --- Load from Environment Variables ---
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY')
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///chat.db'
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024 # 50 MB file limit
app.config['PROFILE_PIC_FOLDER'] = 'static/images/profile_pics'
app.config['ALLOWED_EXTENSIONS'] = {'png', 'jpg', 'jpeg', 'gif'}
socketio = SocketIO(app)

# --- Gmail Mail Config ---
app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 465
app.config['MAIL_USE_SSL'] = True
app.config['MAIL_USERNAME'] = os.getenv('MAIL_USERNAME') # From .env
app.config['MAIL_PASSWORD'] = os.getenv('MAIL_PASSWORD') # From .env
app.config['MAIL_DEFAULT_SENDER'] = ('FireTon', os.getenv('MAIL_USERNAME'))
mail = Mail(app)

# --- Serializer for tokens ---
s = URLSafeTimedSerializer(app.config['SECRET_KEY'])

# --- Login setup ---
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'
login_manager.login_message = "Please log in and complete 2FA to access this page."

# --- Database setup ---
db.init_app(app)

# --- (Fernet, Timezone, Folder Creation) ---
KEY_FILE = "secret.key"
if os.path.exists(KEY_FILE):
    with open(KEY_FILE, "rb") as f:
        key = f.read()
else:
    key = Fernet.generate_key()
    with open(KEY_FILE, "wb") as f:
        f.write(key)
fernet = Fernet(key)
IST = pytz.timezone('Asia/Kolkata')
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(app.config['PROFILE_PIC_FOLDER'], exist_ok=True)
user_rooms = {} 

@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))

# --- (OTP functions are the same) ---
def generate_otp():
    return str(random.randint(100000, 999999))

def send_otp_email(user, otp, subject="FireTon: Your Verification Code"):
    msg = MailMessage(subject, recipients=[user.email])
    msg.html = render_template('otp_email.html', username=user.username, otp=otp)
    try:
        mail.send(msg)
    except Exception as e:
        print(f"--- EMAIL SEND FAILED --- \n{e}\n-------------------------")

@app.route('/')
def index():
    if current_user.is_authenticated:
        return redirect(url_for('chat'))
    return redirect(url_for('login'))

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')
        
        if User.query.filter_by(username=username).first():
            flash('Username already exists')
            return redirect(url_for('register'))
        if User.query.filter_by(email=email).first():
            flash('Email address already in use')
            return redirect(url_for('register'))
        
        user = User(
            username=username, 
            email=email, 
            password=generate_password_hash(password),
            email_verified=False 
        )
        db.session.add(user)
        db.session.commit()
        
        otp = generate_otp()
        session['verification_otp'] = otp
        session['verification_user_id'] = user.id
        send_otp_email(user, otp, subject="Welcome to FireTon! Verify Your Email")
        
        flash('Account created! We sent a verification code to your email.')
        return redirect(url_for('verify_email'))
        
    return render_template('register.html')

@app.route('/verify-email', methods=['GET', 'POST'])
def verify_email():
    if 'verification_user_id' not in session:
        flash('No verification in progress. Please register or log in.')
        return redirect(url_for('register'))

    if request.method == 'POST':
        otp_entered = request.form.get('otp')
        if otp_entered == session.get('verification_otp'):
            user_id = session.get('verification_user_id')
            user = db.session.get(User, user_id)
            if user:
                user.email_verified = True
                db.session.commit()
                
                session.pop('verification_otp', None)
                session.pop('verification_user_id', None)
                
                flash('Email verified successfully! You can now log in.', 'success')
                return redirect(url_for('login'))
            else:
                flash('User not found. Please register again.')
                return redirect(url_for('register'))
        else:
            flash('Invalid code. Please try again.', 'danger')
            
    return render_template('verify_email.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        user = User.query.filter_by(username=username).first()
        
        if user and check_password_hash(user.password, password):
            
            if not user.email_verified:
                otp = generate_otp()
                session['verification_otp'] = otp
                session['verification_user_id'] = user.id
                send_otp_email(user, otp, subject="Verify Your Email to Log In")
                flash('Your email is not verified. We sent a new code to your email.')
                return redirect(url_for('verify_email'))

            otp = generate_otp()
            session['2fa_otp'] = otp
            session['2fa_user_id'] = user.id
            send_otp_email(user, otp, subject="FireTon: Your Login Code")
            
            return redirect(url_for('login_2fa'))
            
        flash('Invalid username or password')
    return render_template('login.html')

@app.route('/login-2fa', methods=['GET', 'POST'])
def login_2fa():
    if '2fa_user_id' not in session:
        flash('No 2FA login in progress. Please log in first.')
        return redirect(url_for('login'))

    if request.method == 'POST':
        otp_entered = request.form.get('otp')
        if otp_entered == session.get('2fa_otp'):
            user_id = session.get('2fa_user_id')
            user = db.session.get(User, user_id)
            
            if user:
                login_user(user)
                session.pop('2fa_otp', None)
                session.pop('2fa_user_id', None)
                return redirect(url_for('chat'))
            else:
                flash('User not found. Please log in again.')
                return redirect(url_for('login'))
        else:
            flash('Invalid code. Please try again.', 'danger')
            
    return render_template('login_2fa.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))
    
@app.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        email = request.form.get('email')
        user = User.query.filter_by(email=email).first()
        
        if user:
            # Generate a one-time OTP for password reset and email it
            otp = generate_otp()
            session['reset_otp'] = otp
            session['reset_user_id'] = user.id
            # Set an expiry timestamp in session (10 minutes)
            session['reset_otp_expiry'] = (datetime.now(IST).timestamp() + 10 * 60)
            send_otp_email(user, otp, subject="FireTon: Password Reset Code")
            
        # Keep response generic to avoid leaking account existence
        flash('If an account with that email exists, a password reset code has been sent.', 'info')
        return redirect(url_for('verify_reset'))
        
    return render_template('forgot_password.html')


@app.route('/verify-reset', methods=['GET', 'POST'])
def verify_reset():
    # Verify OTP sent for password reset
    if 'reset_user_id' not in session:
        flash('No password reset in progress. Please request a password reset.', 'warning')
        return redirect(url_for('forgot_password'))

    if request.method == 'POST':
        otp_entered = request.form.get('otp')

        # Check expiry
        expiry = session.get('reset_otp_expiry')
        if expiry and datetime.now(IST).timestamp() > expiry:
            # cleanup keys
            session.pop('reset_otp', None)
            session.pop('reset_user_id', None)
            session.pop('reset_otp_expiry', None)
            flash('The reset code has expired. Please request a new one.', 'danger')
            return redirect(url_for('forgot_password'))

        if otp_entered == session.get('reset_otp'):
            # OTP correct, allow user to set new password
            session.pop('reset_otp', None)
            session.pop('reset_otp_expiry', None)
            # Mark verified flag so reset-password view can allow change
            session['reset_verified_user_id'] = session.get('reset_user_id')
            session.pop('reset_user_id', None)
            return redirect(url_for('reset_password'))
        else:
            flash('Invalid code. Please try again.', 'danger')

    return render_template('verify_reset.html')

@app.route('/reset-password', methods=['GET', 'POST'])
@app.route('/reset-password/<token>', methods=['GET', 'POST'])
def reset_password(token=None):
    user = None

    # If token provided, validate token (legacy link flow)
    if token:
        try:
            email = s.loads(token, salt='password-reset-salt', max_age=3600) # 1 hour
        except SignatureExpired:
            flash('The password reset link has expired.', 'danger')
            return redirect(url_for('forgot_password'))
        except BadTimeSignature:
            flash('Invalid password reset link.', 'danger')
            return redirect(url_for('forgot_password'))
        user = User.query.filter_by(email=email).first()
        if not user:
            flash('Invalid user.', 'danger')
            return redirect(url_for('login'))
    else:
        # Session-based verification flow
        if 'reset_verified_user_id' not in session:
            flash('No verified password reset in progress. Please request a password reset.', 'warning')
            return redirect(url_for('forgot_password'))
        user_id = session.get('reset_verified_user_id')
        user = db.session.get(User, user_id)
        if not user:
            flash('Invalid user.', 'danger')
            return redirect(url_for('login'))

    if request.method == 'POST':
        password = request.form.get('password')
        password_confirm = request.form.get('password_confirm')

        if password != password_confirm:
            flash('Passwords do not match.', 'danger')
            return render_template('reset_password.html', token=token)

        user.password = generate_password_hash(password)
        db.session.commit()

        # Cleanup any session flags
        session.pop('reset_verified_user_id', None)

        flash('Your password has been reset successfully! You can now log in.', 'success')
        return redirect(url_for('login'))

    return render_template('reset_password.html', token=token)

def send_reset_email(user, token):
    reset_url = url_for('reset_password', token=token, _external=True)
    msg = MailMessage(
        'FireTon: Password Reset Request',
        recipients=[user.email]
    )
    msg.html = render_template('reset_email.html', username=user.username, reset_url=reset_url)
    
    try:
        mail.send(msg)
    except Exception as e:
        print(f"--- EMAIL SEND FAILED --- \n{e}\n-------------------------")
# --- End of auth routes ---

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

# --- NEW: Dedicated HTML Page Routes ---
@app.route('/new-group')
@login_required
def new_group():
    # Logic for getting contacts is moved into the route that renders the page
    blocked_ids = {u.id for u in current_user.blocked_users}
    blocked_by_ids = {u.id for u in current_user.blocked_by}
    all_blocked_user_ids = blocked_ids.union(blocked_by_ids)

    dm_rooms_query = ChatRoom.query.filter(
        ChatRoom.is_group == False,
        ChatRoom.members.contains(current_user)
    )
    dm_rooms = dm_rooms_query.all()
    contacts = []
    if dm_rooms:
        dm_room_ids = [room.id for room in dm_rooms]
        contacts_query = User.query.join(chat_members).join(ChatRoom).filter(
            ChatRoom.id.in_(dm_room_ids),
            User.id != current_user.id
        )
        contacts = contacts_query.filter(
            ~User.id.in_(all_blocked_user_ids)
        ).distinct().all()
        
    return render_template('new_group.html', contacts=contacts)

@app.route('/manage-blocked')
@login_required
def manage_blocked():
    # Logic for getting blocked list is moved into the route that renders the page
    all_users = User.query.filter(User.id != current_user.id).all()
    blocked_users_list = current_user.blocked_users
    blocked_user_ids = {u.id for u in blocked_users_list}
    blocked_by_user_ids = {u.id for u in current_user.blocked_by}
    
    unblocked_list = []
    blocked_list = []
    
    for user in all_users:
        if user.id in blocked_user_ids:
            blocked_list.append(user.to_dict())
        elif user.id not in blocked_by_user_ids:
            unblocked_list.append(user.to_dict())
            
    return render_template('manage_blocked.html', 
                           unblocked_contacts=unblocked_list, 
                           blocked_contacts=blocked_list)

@app.route('/profile', methods=['GET'])
@login_required
def profile():
    profile_pic_url = f'/static/images/profile_pics/{current_user.profile_pic}'
    return render_template('profile.html', profile_pic_url=profile_pic_url)

@app.route('/api/profile/upload', methods=['POST'])
@login_required
def upload_profile_pic():
    if 'profile_pic' not in request.files:
        flash('No file part', 'danger')
        return redirect(url_for('profile'))
        
    file = request.files['profile_pic']
    
    if file.filename == '':
        flash('No selected file', 'danger')
        return redirect(url_for('profile'))
        
    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        ext = filename.rsplit('.', 1)[1].lower()
        new_filename = f"{current_user.id}_{str(uuid.uuid4())[:8]}.{ext}"
        save_path = os.path.join(app.config['PROFILE_PIC_FOLDER'], new_filename)
        
        output_size = (300, 300)
        img = Image.open(file.stream)
        img.thumbnail(output_size)
        img.save(save_path)
        
        if current_user.profile_pic != 'default.png':
            old_path = os.path.join(app.config['PROFILE_PIC_FOLDER'], current_user.profile_pic)
            if os.path.exists(old_path):
                os.remove(old_path)
        
        current_user.profile_pic = new_filename
        db.session.commit()
        
        flash('Profile picture updated!', 'success')
    else:
        flash('Invalid file type. Please use png, jpg, or gif.', 'danger')
        
    return redirect(url_for('profile'))

# --- UPDATED: /chat route ---
@app.route('/chat')
@login_required
def chat():
    user_rooms = current_user.chat_rooms.order_by(ChatRoom.id).all()
    
    blocked_ids = {u.id for u in current_user.blocked_users}
    blocked_by_ids = {u.id for u in current_user.blocked_by}
    all_blocked_user_ids = blocked_ids.union(blocked_by_ids)
    
    dm_rooms_query = ChatRoom.query.filter(
        ChatRoom.is_group == False,
        ChatRoom.members.contains(current_user)
    )
    dm_rooms = dm_rooms_query.all()
    contacts = []
    if dm_rooms:
        dm_room_ids = [room.id for room in dm_rooms]
        contacts_query = User.query.join(chat_members).join(ChatRoom).filter(
            ChatRoom.id.in_(dm_room_ids),
            User.id != current_user.id
        )
        contacts = contacts_query.filter(
            ~User.id.in_(all_blocked_user_ids)
        ).distinct().all()

    # --- NEW: Build chat_rooms_data list ---
    chat_rooms_data = []
    for room in user_rooms:
        room_data = {
            "id": room.id,
            "is_group": room.is_group,
            "creator_id": room.creator_id
        }
        if room.is_group:
            room_data["name"] = room.name
            room_data["profile_pic_url"] = f'/static/images/profile_pics/{room.group_profile_pic}'
        else:
            other_member = None
            for member in room.members.all():
                if member.id != current_user.id:
                    other_member = member
                    break
            
            if other_member and other_member.id not in all_blocked_user_ids:
                room_data["name"] = other_member.username
                room_data["profile_pic_url"] = f'/static/images/profile_pics/{other_member.profile_pic}'
            else:
                continue 
                
        chat_rooms_data.append(room_data)
    # --- END NEW ---

    profile_pic_url = f'/static/images/profile_pics/{current_user.profile_pic}'
    return render_template('chat.html', 
                           chat_rooms_data=chat_rooms_data,
                           contacts=contacts, 
                           current_user_id=current_user.id,
                           profile_pic_url=profile_pic_url)
# --- END UPDATED ---

@app.route('/api/upload', methods=['POST'])
@login_required
def upload_file():
    if 'file' not in request.files:
        return jsonify({"error": "No file part"}), 400
    file = request.files['file']
    room_id = request.form.get('room_id')
    if file.filename == '' or not room_id:
        return jsonify({"error": "Missing file or room ID"}), 400
    room = db.session.get(ChatRoom, int(room_id))
    if not room or current_user not in room.members.all():
        return jsonify({"error": "Not authorized"}), 403
    try:
        file_bytes = file.read()
        encrypted_bytes = fernet.encrypt(file_bytes)
        secure_filename = str(uuid.uuid4()) + ".dat"
        file_path_on_disk = os.path.join(app.config['UPLOAD_FOLDER'], secure_filename)
        with open(file_path_on_disk, 'wb') as f:
            f.write(encrypted_bytes)
        mime = file.mimetype
        if mime.startswith('image/'): msg_type = 'image'
        elif mime.startswith('video/'): msg_type = 'video'
        else: msg_type = 'file'
        msg = Message(
            content=None, sender_id=current_user.id, chatroom_id=room_id,
            message_type=msg_type, file_path=secure_filename,
            original_filename=file.filename, mime_type=file.mimetype
        )
        db.session.add(msg)
        db.session.commit()
        
        socketio.emit('new_message', {
            'room_id': room_id, 'sender_id': current_user.id,
            'sender_name': current_user.username,
            'sender_profile_pic': f'/static/images/profile_pics/{current_user.profile_pic}',
            'timestamp': msg.timestamp.strftime('%H:%M'),
            'message_id': msg.id, 'message_type': msg.message_type,
            'original_filename': msg.original_filename,
            'mime_type': msg.mime_type, 'content': None
        }, to=f'room_{room_id}') 
        return jsonify({"success": True, "message_id": msg.id}), 201
    except Exception as e:
        print(f"File upload error: {e}")
        return jsonify({"error": "Internal server error"}), 500

@app.route('/api/file/<int:message_id>')
@login_required
def get_file(message_id):
    msg = db.session.get(Message, message_id)
    if not msg:
        return "File not found", 404
    room = db.session.get(ChatRoom, msg.chatroom_id)
    if not room or current_user not in room.members.all():
        return "Not authorized", 403
    try:
        file_path_on_disk = os.path.join(app.config['UPLOAD_FOLDER'], msg.file_path)
        with open(file_path_on_disk, 'rb') as f:
            encrypted_bytes = f.read()
        decrypted_bytes = fernet.decrypt(encrypted_bytes)
        return send_file(
            io.BytesIO(decrypted_bytes),
            mimetype=msg.mime_type,
            as_attachment=False,
            download_name=msg.original_filename
        )
    except Exception as e:
        print(f"Error serving file: {e}")
        return "Error processing file", 500

@app.route('/api/chat/start_dm_by_username', methods=['POST'])
@login_required
def start_dm_by_username():
    data = request.get_json()
    username = data.get('username')
    if not username:
        return jsonify({"error": "Username is required"}), 400
    other_user = User.query.filter_by(username=username).first()
    if not other_user:
        return jsonify({"error": "User not found"}), 404
    if other_user.id == current_user.id:
        return jsonify({"error": "You cannot start a chat with yourself"}), 400
    if other_user in current_user.blocked_by:
        return jsonify({"error": f"You cannot start a chat with {other_user.username}."}), 403
    if other_user in current_user.blocked_users:
        return jsonify({"error": f"You must unblock {other_user.username} to start a chat."}), 400
    chat = ChatRoom.query.filter(ChatRoom.is_group == False).filter(
        ChatRoom.members.contains(current_user)
    ).filter(
        ChatRoom.members.contains(other_user)
    ).first()

    if not chat:
        chat = ChatRoom(is_group=False)
        chat.members.append(current_user)
        chat.members.append(other_user)
        db.session.add(chat)
        db.session.commit()
        
        socketio.emit('new_chat_room', {
            'id': chat.id, 'name': current_user.username,
            'is_group': chat.is_group, 'creator_id': None,
            'contact_id': current_user.id,
            'profile_pic_url': f'/static/images/profile_pics/{current_user.profile_pic}'
        }, to=f'user_{other_user.id}')

    return jsonify({
        "id": chat.id, "name": other_user.username,
        "is_group": chat.is_group, "creator_id": None,
        "contact_id": other_user.id,
        'profile_pic_url': f'/static/images/profile_pics/{other_user.profile_pic}'
    })

@app.route('/api/chat/create_group', methods=['POST'])
@login_required
def create_group():
    data = request.get_json()
    group_name = data.get('group_name')
    user_ids = data.get('user_ids')
    if not group_name or not user_ids:
        return jsonify({"error": "Group name and members are required"}), 400
    new_room = ChatRoom(
        name=group_name, is_group=True, creator_id=current_user.id,
        group_profile_pic='default.png'
    )
    new_room.members.append(current_user)
    for user_id in user_ids:
        user = db.session.get(User, int(user_id))
        if user and user != current_user:
            new_room.members.append(user)
    db.session.add(new_room)
    db.session.commit()
    
    group_icon_url = f'/static/images/profile_pics/{new_room.group_profile_pic}'
    for user in new_room.members.all():
        if user.id != current_user.id:
            socketio.emit('new_chat_room', {
                'id': new_room.id, 'name': new_room.name,
                'is_group': new_room.is_group, 'creator_id': new_room.creator_id,
                'contact_id': None,
                'profile_pic_url': group_icon_url
            }, to=f'user_{user.id}')
    
    return jsonify({
        "id": new_room.id, "name": new_room.name,
        "is_group": new_room.is_group,
        "creator_id": new_room.creator_id,
        'profile_pic_url': group_icon_url
    }), 201

# --- NEW: API Route for Group Pic Upload ---
@app.route('/api/group/<int:room_id>/upload-pic', methods=['POST'])
@login_required
def upload_group_pic(room_id):
    room = db.session.get(ChatRoom, room_id)
    if not room or not room.is_group:
        return jsonify({"error": "Group not found"}), 404
    if room.creator_id != current_user.id:
        return jsonify({"error": "Not authorized"}), 403

    if 'group_pic' not in request.files:
        return jsonify({"error": "No file part"}), 400
        
    file = request.files['group_pic']
    
    if file.filename == '':
        return jsonify({"error": "No selected file"}), 400
        
    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        ext = filename.rsplit('.', 1)[1].lower()
        new_filename = f"group_{room.id}_{str(uuid.uuid4())[:8]}.{ext}"
        save_path = os.path.join(app.config['PROFILE_PIC_FOLDER'], new_filename)
        
        output_size = (300, 300)
        img = Image.open(file.stream)
        img.thumbnail(output_size)
        img.save(save_path)
        
        if room.group_profile_pic != 'default.png':
            old_path = os.path.join(app.config['PROFILE_PIC_FOLDER'], room.group_profile_pic)
            if os.path.exists(old_path):
                os.remove(old_path)
        
        room.group_profile_pic = new_filename
        db.session.commit()
        
        new_pic_url = f'/static/images/profile_pics/{new_filename}'
        
        socketio.emit('group_pic_updated', {
            'room_id': room_id,
            'new_pic_url': new_pic_url
        }, to=f'room_{room_id}')
        
        return jsonify({"success": True, "new_pic_url": new_pic_url})
    else:
        return jsonify({"error": "Invalid file type"}), 400
# --- END NEW ---

@app.route('/api/group/<int:room_id>/members')
@login_required
def get_group_members(room_id):
    room = db.session.get(ChatRoom, room_id)
    if not room or not room.is_group:
        return jsonify({"error": "Group not found"}), 404
    if room.creator_id != current_user.id:
        return jsonify({"error": "Not authorized"}), 403
    current_member_ids = {member.id for member in room.members.all()}
    blocked_ids = {u.id for u in current_user.blocked_users}
    blocked_by_ids = {u.id for u in current_user.blocked_by}
    all_blocked_user_ids = blocked_ids.union(blocked_by_ids)
    dm_rooms_query = ChatRoom.query.filter(
        ChatRoom.is_group == False,
        ChatRoom.members.contains(current_user)
    )
    dm_rooms = dm_rooms_query.all()
    if not dm_rooms:
        contacts = []
    else:
        dm_room_ids = [room.id for room in dm_rooms]
        contacts_query = User.query.join(chat_members).join(ChatRoom).filter(
            ChatRoom.id.in_(dm_room_ids),
            User.id != current_user.id
        )
        contacts = contacts_query.filter(
            ~User.id.in_(all_blocked_user_ids)
        ).distinct().all()
    addable_contacts = []
    current_members = []
    for user in contacts:
        if user.id in current_member_ids:
            if user.id != current_user.id: 
                current_members.append(user.to_dict())
        else:
            addable_contacts.append(user.to_dict())
    return jsonify({
        'current_members': current_members,
        'addable_contacts': addable_contacts
    })

@app.route('/api/group/<int:room_id>/add_member', methods=['POST'])
@login_required
def add_group_member(room_id):
    room = db.session.get(ChatRoom, room_id)
    if not room or not room.is_group:
        return jsonify({"error": "Group not found"}), 404
    if room.creator_id != current_user.id:
        return jsonify({"error": "Not authorized"}), 403
    data = request.get_json()
    user_id_to_add = data.get('user_id')
    user = db.session.get(User, user_id_to_add)
    if not user:
        return jsonify({"error": "User not found"}), 404
    if user in room.members.all():
        return jsonify({"error": "User is already in the group"}), 400
    room.members.append(user)
    db.session.commit()
    socketio.emit('new_chat_room', {
        'id': room.id, 'name': room.name,
        'is_group': room.is_group, 'creator_id': room.creator_id,
        'profile_pic_url': f'/static/images/profile_pics/{room.group_profile_pic}'
    }, to=f'user_{user.id}')
    return jsonify({"success": True, "user": user.to_dict()})

@app.route('/api/group/<int:room_id>/remove_member', methods=['POST'])
@login_required
def remove_group_member(room_id):
    room = db.session.get(ChatRoom, room_id)
    if not room or not room.is_group:
        return jsonify({"error": "Group not found"}), 404
    if room.creator_id != current_user.id:
        return jsonify({"error": "Not authorized"}), 403
    data = request.get_json()
    user_id_to_remove = data.get('user_id')
    if user_id_to_remove == current_user.id:
        return jsonify({"error": "You cannot remove yourself"}), 400
    user = db.session.get(User, user_id_to_remove)
    if not user:
        return jsonify({"error": "User not found"}), 404
    if user not in room.members.all():
        return jsonify({"error": "User is not in the group"}), 400
    room.members.remove(user)
    db.session.commit()
    socketio.emit('removed_from_group', {
        'room_id': room.id
    }, to=f'user_{user.id}')
    return jsonify({"success": True, "user": user.to_dict()})

@app.route('/api/group/<int:room_id>/leave', methods=['POST'])
@login_required
def leave_group(room_id):
    room = db.session.get(ChatRoom, room_id)
    if not room or not room.is_group:
        return jsonify({"error": "Group not found"}), 404
    if current_user not in room.members.all():
        return jsonify({"error": "You are not a member of this group"}), 400
    if current_user.id == room.creator_id:
        return jsonify({"error": "Creator cannot leave the group. You must delete it."}), 403
    room.members.remove(current_user)
    msg_content = f"{current_user.username} has left the group."
    msg = Message(
        content=msg_content, message_type='system',
        chatroom_id=room_id, sender_id=None
    )
    db.session.add(msg)
    db.session.commit()
    socketio.emit('new_message', {
        'room_id': room_id, 'sender_id': None,
        'sender_name': 'System', 'timestamp': msg.timestamp.strftime('%H:%M'),
        'message_id': msg.id, 'message_type': 'system',
        'original_filename': None, 'mime_type': 'text/plain',
        'content': msg_content,
        'sender_profile_pic': '/static/images/profile_pics/default.png' # System icon
    }, to=f'room_{room_id}')
    return jsonify({"success": True, "room_id": room_id})

# --- (SocketIO event handlers are unchanged) ---
@socketio.on('connect')
def handle_connect():
    if current_user.is_authenticated:
        join_room(f'user_{current_user.id}')
        emit('user_connected', {
            'user_id': current_user.id,
            'username': current_user.username
        }, broadcast=True)

@socketio.on('disconnect')
def handle_disconnect():
    if current_user.is_authenticated:
        leave_room(f'user_{current_user.id}')
        room_id = user_rooms.pop(request.sid, None)
        if room_id:
             leave_room(f'room_{room_id}')
        emit('user_disconnected', {
            'user_id': current_user.id,
            'username': current_user.username
        }, broadcast=True)

@socketio.on('join_room')
def handle_join_room(data):
    if not current_user.is_authenticated: return
    room_id = data['room_id']
    room = db.session.get(ChatRoom, int(room_id))
    if not room or current_user not in room.members.all():
        return
    prev_room_id = user_rooms.pop(request.sid, None)
    if prev_room_id:
        leave_room(f'room_{prev_room_id}')
    join_room(f'room_{room_id}')
    user_rooms[request.sid] = room_id 
    emit('room_joined', {'room_id': room_id, 'name': room.name if room.is_group else 'DM'})

@socketio.on('send_message')
def handle_message(data):
    if not current_user.is_authenticated: return
    room_id = data['room_id']
    content = data['message']
    room = db.session.get(ChatRoom, int(room_id))
    if not room or current_user not in room.members.all():
        return
    if not room.is_group:
        recipient = None
        for user in room.members.all():
            if user.id != current_user.id:
                recipient = user
                break
        if recipient:
            if current_user in recipient.blocked_users:
                emit('error', {'message': 'You cannot send messages to this user.'})
                return
            if recipient in current_user.blocked_users:
                emit('error', {'message': f'You must unblock {recipient.username} to send messages.'})
                return
    encrypted = fernet.encrypt(content.encode()).decode()
    msg = Message(
        content=encrypted, sender_id=current_user.id,
        chatroom_id=room_id, message_type='text'
    )
    db.session.add(msg)
    db.session.commit()
    socketio.emit('new_message', {
        'room_id': room_id, 'sender_id': current_user.id,
        'sender_name': current_user.username, 'content': content,
        'sender_profile_pic': f'/static/images/profile_pics/{current_user.profile_pic}',
        'timestamp': msg.timestamp.strftime('%H:%M'),
        'message_id': msg.id, 'message_type': 'text',
        'original_filename': None, 'mime_type': 'text/plain'
    }, to=f'room_{room_id}')

@socketio.on('delete_message')
def handle_delete_message(data):
    if not current_user.is_authenticated: return
    message_id = data.get('message_id')
    msg = db.session.get(Message, message_id)
    if not msg:
        return 
    if msg.sender_id != current_user.id:
        return 
    try:
        room_id = msg.chatroom_id
        if msg.file_path:
            file_path_on_disk = os.path.join(app.config['UPLOAD_FOLDER'], msg.file_path)
            if os.path.exists(file_path_on_disk):
                os.remove(file_path_on_disk)
        db.session.delete(msg)
        db.session.commit()
        emit('message_deleted', {
            'message_id': message_id
        }, to=f'room_{room_id}')
    except Exception as e:
        print(f"Error deleting message: {e}")
        db.session.rollback()

@app.route('/api/messages/<int:room_id>')
@login_required
def get_messages(room_id):
    room = db.session.get(ChatRoom, room_id)
    if not room or current_user not in room.members.all():
        return jsonify({"error": "Not authorized"}), 403
    try:
        messages = Message.query.filter_by(chatroom_id=room_id) \
                                .order_by(Message.timestamp).all()
        result = []
        for m in messages:
            content = None
            if m.message_type == 'text':
                content = fernet.decrypt(m.content.encode()).decode()
            elif m.message_type == 'system':
                content = m.content
                
            profile_pic = '/static/images/profile_pics/default.png' # System default
            if m.sender:
                profile_pic = f'/static/images/profile_pics/{m.sender.profile_pic}'

            ist_time = m.timestamp.astimezone(IST).strftime('%H:%M')
            result.append({
                'sender_id': m.sender_id,
                'sender_name': m.sender.username if m.sender else 'System',
                'sender_profile_pic': profile_pic,
                'content': content, 'timestamp': ist_time,
                'message_id': m.id, 'message_type': m.message_type,
                'original_filename': m.original_filename,
                'mime_type': m.mime_type
            })
        return jsonify(result)
    except Exception as e:
        print(f"Error retrieving messages: {e}")
        return jsonify([])

@app.route('/api/user/block_list')
@login_required
def get_block_list():
    all_users = User.query.filter(User.id != current_user.id).all()
    blocked_users_list = current_user.blocked_users
    blocked_user_ids = {u.id for u in blocked_users_list}
    blocked_by_user_ids = {u.id for u in current_user.blocked_by}
    unblocked_list = []
    blocked_list = []
    for user in all_users:
        if user.id in blocked_user_ids:
            blocked_list.append(user.to_dict())
        elif user.id not in blocked_by_user_ids:
            unblocked_list.append(user.to_dict())
    return jsonify({
        'unblocked_contacts': unblocked_list,
        'blocked_contacts': blocked_list
    })

@app.route('/api/user/block', methods=['POST'])
@login_required
def block_user():
    data = request.get_json()
    user_id_to_block = data.get('user_id')
    user = db.session.get(User, user_id_to_block)
    if not user:
        return jsonify({"error": "User not found"}), 404
    if user == current_user:
        return jsonify({"error": "You cannot block yourself"}), 400
    if user not in current_user.blocked_users:
        current_user.blocked_users.append(user)
        db.session.commit()
    return jsonify({"success": True, "user": user.to_dict()})

@app.route('/api/user/unblock', methods=['POST'])
@login_required
def unblock_user():
    data = request.get_json()
    user_id_to_unblock = data.get('user_id')
    user = db.session.get(User, user_id_to_unblock)
    if not user:
        return jsonify({"error": "User not found"}), 404
    if user in current_user.blocked_users:
        current_user.blocked_users.remove(user)
        db.session.commit()
    return jsonify({"success": True, "user": user.to_dict()})

def generate_and_exchange_public_key_fn() -> bytes:
    """
    f(n) - SIMULATION STEP 1: Generates an RSA key pair and returns the public key
    for a simulated secure exchange. This key is NOT used by Fernet.
    """
    # 1. Generate Private Key (The 'Recipient's' key)
    private_key_demonstration = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
        backend=default_backend()
    )

    # 2. Get Public Key (The part that is 'exchanged')
    public_key_demonstration = private_key_demonstration.public_key()
    
    # 3. Serialize and return the Public Key bytes
    public_key_bytes = public_key_demonstration.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo
    )
    
    # NOTE: In a real system, the private key would be saved securely 
    # to be used for decryption in the next step.
    
    return public_key_bytes


from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.backends import default_backend

# --- UNUSED HYBRID KEY EXCHANGE DEMONSTRATION FUNCTIONS ---

_DEMO_PRIVATE_KEY = None
_DEMO_PUBLIC_KEY_BYTES = None

def generate_and_exchange_asymmetric_key_fn() -> bytes:
    
    global _DEMO_PRIVATE_KEY
    global _DEMO_PUBLIC_KEY_BYTES
    
    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
        backend=default_backend()
    )
    _DEMO_PRIVATE_KEY = private_key
    
    public_key = private_key.public_key()
    public_key_bytes = public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo
    )
    _DEMO_PUBLIC_KEY_BYTES = public_key_bytes

    return public_key_bytes


def encrypt_session_key_with_asymmetric_key_fn(recipient_public_key_pem: bytes, session_symmetric_key: bytes) -> bytes:
    
    loaded_public_key = serialization.load_pem_public_key(
        recipient_public_key_pem,
        backend=default_backend()
    )

    encrypted_symmetric_key = loaded_public_key.encrypt(
        session_symmetric_key,
        padding.OAEP(
            mgf=padding.MGF1(algorithm=hashes.SHA256()),
            algorithm=hashes.SHA256(),
            label=None
        )
    )
    #The functions you added simulate a Hybrid Cryptography Key Exchange, which is the standard method used to secure communications like TLS/SSL or secure messaging:
    #   Asymmetric Phase (Key Transport): The recipient's RSA Public Key is used to encrypt a newly generated symmetric session key (like the Fernet key). Only the recipient's secret RSA Private Key can decrypt it.
    #   Symmetric Phase (Data Encryption): Once the session key is securely transmitted, both parties use that fast symmetric key (like Fernet) to encrypt and decrypt the bulk message data.
    
    return encrypted_symmetric_key


def decrypt_received_key_fn(encrypted_key: bytes) -> bytes:
    
    global _DEMO_PRIVATE_KEY
    if _DEMO_PRIVATE_KEY is None:
        raise ValueError("RSA private key not available for decryption simulation.")
        
    decrypted_session_key = _DEMO_PRIVATE_KEY.decrypt(
        encrypted_symmetric_key,
        padding.OAEP(
            mgf=padding.MGF1(algorithm=hashes.SHA256()),
            algorithm=hashes.SHA256(),
            label=None
        )
    )
    
    return decrypted_session_key
RSA_PUBLIC_KEY = generate_and_exchange_asymmetric_key_fn()
# --- END OF UNUSED ASYMMETRIC DEMONSTRATION ---
if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    socketio.run(app, debug=True)