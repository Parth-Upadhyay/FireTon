from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from datetime import datetime
import pytz

db = SQLAlchemy()
IST = pytz.timezone('Asia/Kolkata')

# Association table for the many-to-many relationship
# between users and chat rooms
chat_members = db.Table('chat_members',
    db.Column('user_id', db.Integer, db.ForeignKey('user.id'), primary_key=True),
    db.Column('chatroom_id', db.Integer, db.ForeignKey('chat_room.id'), primary_key=True)
)

# Association table for the block list
block_list = db.Table('block_list',
    db.Column('blocker_id', db.Integer, db.ForeignKey('user.id'), primary_key=True),
    db.Column('blocked_id', db.Integer, db.ForeignKey('user.id'), primary_key=True)
)

class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    email_verified = db.Column(db.Boolean, default=False, nullable=False)
    profile_pic = db.Column(db.String(100), nullable=False, default='default.png')
    
    chat_rooms = db.relationship('ChatRoom', secondary=chat_members,
                                 back_populates='members', lazy='dynamic')
    
    created_groups = db.relationship('ChatRoom', 
                                     back_populates='creator', 
                                     foreign_keys='ChatRoom.creator_id')

    blocked_users = db.relationship('User', secondary=block_list,
                                    primaryjoin=(block_list.c.blocker_id == id),
                                    secondaryjoin=(block_list.c.blocked_id == id),
                                    back_populates='blocked_by')
    
    blocked_by = db.relationship('User', secondary=block_list,
                                 primaryjoin=(block_list.c.blocked_id == id),
                                 secondaryjoin=(block_list.c.blocker_id == id),
                                 back_populates='blocked_users')

    def to_dict(self):
        return {
            'id': self.id,
            'username': self.username,
            'profile_pic_url': f'/static/images/profile_pics/{self.profile_pic}'
        }

class ChatRoom(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=True) # Name for group chats, null for DMs
    is_group = db.Column(db.Boolean, default=False)
    
    # --- NEW: Group Profile Pic ---
    group_profile_pic = db.Column(db.String(100), nullable=False, default='default.png')
    # --- END NEW ---
    
    # Track group creator
    creator_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    creator = db.relationship('User', 
                              back_populates='created_groups', 
                              foreign_keys=[creator_id])
    
    members = db.relationship('User', secondary=chat_members,
                              back_populates='chat_rooms', lazy='dynamic')
    
    messages = db.relationship('Message', back_populates='room', lazy='dynamic')

class Message(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.Text, nullable=True) # Text content is now optional
    timestamp = db.Column(db.DateTime, default=lambda: datetime.now(IST))
    
    message_type = db.Column(db.String(20), nullable=False, default='text') # 'text', 'image', 'video', 'file', 'system'
    file_path = db.Column(db.String(300), nullable=True) # Path to the encrypted file on disk
    original_filename = db.Column(db.String(300), nullable=True) # e.g., 'vacation.jpg'
    mime_type = db.Column(db.String(100), nullable=True) # e.g., 'image/jpeg'

    sender_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    
    chatroom_id = db.Column(db.Integer, db.ForeignKey('chat_room.id'))
    
    sender = db.relationship('User')
    room = db.relationship('ChatRoom', back_populates='messages')