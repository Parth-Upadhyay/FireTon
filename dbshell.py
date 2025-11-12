import os
from flask import Flask
# Fernet is no longer needed since we aren't decrypting
from models import db, User, Message, ChatRoom

# --- App Setup ---
app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///chat.db'
app.config['SECRET_KEY'] = 'temp_key_for_shell' 
db.init_app(app)

# --- Menu Functions ---

def list_users():
    """Queries and prints all users and their block lists."""
    print("\n" + "="*30)
    print("         👥 All Users")
    print("="*30)
    
    users = User.query.all()
    if not users:
        print("No users found in the database.")
        return

    for user in users:
        print(f"\n[ID: {user.id}] {user.username}")
        print(f"  Email: {user.email}")
        print(f"  Verified: {user.email_verified}")
        
        # Note: blocked_users is a list (not dynamic), so no .all() needed
        blocked = [u.username for u in user.blocked_users]
        if blocked:
            print(f"  Blocking: {', '.join(blocked)}")
        else:
            print("  Blocking: None")

def view_chat_rooms():
    """Queries and prints all chat rooms and their members."""
    print("\n" + "="*30)
    print("       💬 All Chat Rooms")
    print("="*30)
    
    rooms = ChatRoom.query.all()
    if not rooms:
        print("No chat rooms found.")
        return

    for room in rooms:
        if room.is_group:
            creator = room.creator.username if room.creator else "N/A"
            print(f"\n[Group ID: {room.id}] Name: {room.name} (Creator: {creator})")
        else:
            print(f"\n[DM ID: {room.id}]")
        
        # Note: members is dynamic, so .all() is required
        members = [m.username for m in room.members.all()]
        print(f"  Members: {', '.join(members)}")

def view_messages_encrypted():
    """Asks for a Room ID and prints its raw, ENCRYPTED messages."""
    # Show rooms first so the user can pick one
    view_chat_rooms()
    
    try:
        room_id = int(input("\nWhich Room ID do you want to view? "))
    except ValueError:
        print("Invalid ID. Please enter a number.")
        return

    room = db.session.get(ChatRoom, room_id)
    if not room:
        print(f"Error: Room ID {room_id} not found.")
        return

    room_name = f"'{room.name}'" if room.is_group else "DM"
    print("\n" + "="*30)
    print(f" 🔒 Encrypted Messages for {room_name} (ID: {room.id})")
    print("="*30)

    # Note: messages is dynamic, so .all() is required
    messages = room.messages.order_by(Message.timestamp).all()
    
    if not messages:
        print("... No messages in this room ...")
        return

    for msg in messages:
        sender = "System"
        if msg.sender: # Sender is None for system messages
            sender = msg.sender.username
        
        print(f"\n[{msg.timestamp.strftime('%Y-%m-%d %H:%M')}] From: {sender}")
        
        # --- Show ENCRYPTED Content ---
        if msg.message_type == 'text':
            if msg.content:
                print(f"  ENCRYPTED: {msg.content}")
            else:
                print("  [Empty Message]")
        elif msg.message_type == 'system':
            print(f"  ... {msg.content} ...") # System messages are not encrypted
        else: # image, video, file
            print(f"  [{msg.message_type.upper()}]: {msg.original_filename}")
            print(f"  File Path (Encrypted Name): {msg.file_path}")
        # --- End ---

def main_menu():
    """The main REPL (Read-Evaluate-Print-Loop) for the shell."""
    while True:
        print("\n" + "="*30)
        print("       FireTon Admin Shell")
        print("="*30)
        print("1. List All Users")
        print("2. List All Chat Rooms")
        print("3. View Messages")
        print("4. Exit")
        choice = input("\n> ")

        if choice == '1':
            list_users()
        elif choice == '2':
            view_chat_rooms()
        elif choice == '3':
            view_messages_encrypted()
        elif choice == '4':
            print("Exiting.")
            break
        else:
            print("Invalid choice. Please enter 1, 2, 3, or 4.")


# --- Run the Shell ---
if __name__ == "__main__":
    # We must run our queries inside an app_context
    with app.app_context():
        main_menu() # Run the main menu loop