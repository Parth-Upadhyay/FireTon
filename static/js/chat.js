document.addEventListener('DOMContentLoaded', () => {
    const socket = io();
    
    const isTouchDevice = ('ontouchstart' in window) || (navigator.maxTouchPoints > 0);
    
    let selectedRoomId = null; 

    // --- Core Chat Elements ---
    const messageForm = document.getElementById('message-form');
    const messageInput = document.getElementById('message');
    const messagesDiv = document.getElementById('messages');
    const sendButton = document.getElementById('send-btn');
    const selectedUserSpan = document.getElementById('selected-user');
    const chatRoomList = document.getElementById('chat-rooms-list');
    const selectedChatPic = document.getElementById('selected-chat-pic');

    // --- View-Switching Elements ---
    const chatContainer = document.querySelector('.chat-container');
    const backToChatsBtn = document.getElementById('back-to-chats-btn');

    // --- "Add User" Elements ---
    const addUserForm = document.getElementById('add-user-form');
    const addUserInput = document.getElementById('add-user-input');

    // --- File Upload Elements ---
    const uploadBtn = document.getElementById('upload-btn');
    const fileInput = document.getElementById('file-input');

    // --- TOP CONTROL TARGETS (From base.html) ---
    const openModalBtn = document.getElementById('nav-open-group-btn'); 
    const openBlockModalBtn = document.getElementById('nav-open-block-btn'); 
    // --- END TOP CONTROL TARGETS ---

    // --- Create Group Modal Elements ---
    const createGroupModal = document.getElementById('create-group-modal');
    const closeModalBtn = document.getElementById('close-modal-btn');
    const createGroupBtn = document.getElementById('create-group-btn');
    const groupNameInput = document.getElementById('group-name-input');
    const groupMembersList = document.getElementById('group-members-list');

    // --- Manage Group Modal Elements ---
    const manageGroupBtn = document.getElementById('manage-group-btn');
    const manageGroupModal = document.getElementById('manage-group-modal');
    const closeManageModalBtn = document.getElementById('close-manage-modal-btn');
    const manageRemoveList = document.getElementById('manage-remove-list');
    const manageAddList = document.getElementById('manage-add-list');
    const groupPicInput = document.getElementById('group-pic-input');
    const groupPicUploadBtn = document.getElementById('group-pic-upload-btn');
    
    const leaveGroupBtn = document.getElementById('leave-group-btn');
    
    // --- Manage Blocked Modal Elements ---
    const manageBlockModal = document.getElementById('manage-block-modal');
    const closeBlockModalBtn = document.getElementById('close-block-modal-btn');
    const manageUnblockedList = document.getElementById('manage-unblocked-list');
    const manageBlockedList = document.getElementById('manage-blocked-list');

    // --- 1. Event Listener: Add User by Username ---
    if (addUserForm) {
        addUserForm.addEventListener('submit', async (e) => {
            e.preventDefault();
            const username = addUserInput.value.trim();
            if (!username) return;

            try {
                const response = await fetch('/api/chat/start_dm_by_username', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ 'username': username }),
                    credentials: 'include'
                });

                if (response.ok) {
                    const room = await response.json(); 
                    const newRoomEl = addChatToList(room); 
                    if (room.contact_id) {
                        addContactToCreateModal(room.name, room.contact_id);
                    }
                    newRoomEl.click();
                    addUserInput.value = '';
                } else {
                    const err = await response.json();
                    alert(`Error: ${err.error}`);
                }
            } catch (err) {
                console.error("Failed to start DM:", err);
                alert("An error occurred.");
            }
        });
    }

    // --- 2. TOP BUTTONS: Attach Modals ---
    // These buttons now open the modals directly from the navbar
    if (openModalBtn) {
        openModalBtn.addEventListener('click', () => {
            createGroupModal.style.display = 'block';
        });
    }
    if (openBlockModalBtn) {
        openBlockModalBtn.addEventListener('click', () => {
            openManageBlockModal();
        });
    }
    // --- END TOP BUTTONS ---


    // --- 3. Event Listener: Create Group Modal ---
    if (closeModalBtn) { closeModalBtn.addEventListener('click', () => { createGroupModal.style.display = 'none'; }); }
    window.addEventListener('click', (event) => { if (event.target == createGroupModal) { createGroupModal.style.display = 'none'; } });
    
    if (createGroupBtn) {
        createGroupBtn.addEventListener('click', async () => {
            const groupName = groupNameInput.value.trim();
            const selectedUserIds = [];
            groupMembersList.querySelectorAll('.group-user-select:checked').forEach(cb => {
                selectedUserIds.push(cb.dataset.id);
            });

            if (!groupName) { alert('Please enter a group name.'); return; }
            if (selectedUserIds.length === 0) { alert('Please select at least one member.'); return; }

            try {
                const response = await fetch('/api/chat/create_group', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        'group_name': groupName,
                        'user_ids': selectedUserIds
                    }),
                    credentials: 'include'
                });

                if (response.ok) {
                    const newRoom = await response.json();
                    const newRoomEl = addChatToList(newRoom); 
                    
                    groupNameInput.value = '';
                    groupMembersList.querySelectorAll('.group-user-select:checked').forEach(cb => cb.checked = false);
                    createGroupModal.style.display = 'none';
                    
                    newRoomEl.click();
                } else {
                    const err = await response.json();
                    alert(`Error: ${err.error}`);
                }
            } catch (err) {
                console.error('Failed to create group:', err);
                alert('An error occurred.');
            }
        });
    }

    // --- 4. Event Listener: Select a Chat Room ---
    chatRoomList.querySelectorAll('.chat-room').forEach(roomElement => {
        roomElement.addEventListener('click', () => selectChatRoom(roomElement));
    });

    // --- 5. Event Listener: Send Message (Text) ---
    messageForm.addEventListener('submit', (e) => {
        e.preventDefault();
        if (!selectedRoomId) return;
        const content = messageInput.value.trim();
        if (!content) return;
        socket.emit('send_message', { 'room_id': selectedRoomId, 'message': content });
        messageInput.value = '';
    });

    // --- 6. Socket Listener: Receive New Message ---
    socket.on('new_message', (data) => {
        if (selectedRoomId && data.room_id.toString() === selectedRoomId.toString()) {
            addMessageToUI(data); 
        }
    });

    // --- 7. Event Listener: File Upload ---
    if (uploadBtn) { uploadBtn.addEventListener('click', () => { if (!selectedRoomId) { alert("Please select a chat first."); return; } fileInput.click(); }); }
    if (fileInput) { fileInput.addEventListener('change', async (e) => {
            const file = e.target.files[0]; if (!file || !selectedRoomId) return;
            const tempId = `temp_${Date.now()}`;
            // Use the image from the user's current profile bar
            addMessageToUI({ sender_name: 'You', content: `Uploading ${file.name}...`, timestamp: '', isSent: true, message_type: 'text', temp_id: tempId, sender_profile_pic: document.querySelector('#current-user-bar img').src });
            const formData = new FormData(); formData.append('file', file); formData.append('room_id', selectedRoomId);
            try {
                const response = await fetch('/api/upload', { method: 'POST', body: formData, credentials: 'include' });
                const tempMsg = document.getElementById(tempId);
                if (response.ok) { if (tempMsg) tempMsg.remove(); } else {
                    const err = await response.json(); alert(`Upload failed: ${err.error}`);
                    if (tempMsg) tempMsg.querySelector('.message-content').textContent = `Upload failed: ${file.name}`;
                }
            } catch (err) {
                console.error("Upload error:", err); alert("Upload failed.");
                const tempMsg = document.getElementById(tempId);
                if (tempMsg) tempMsg.querySelector('.message-content').textContent = `Upload failed: ${file.name}`;
            }
            fileInput.value = '';
        });
    }
    
    // --- 8. Mobile "Back" Button Logic ---
    if (backToChatsBtn) {
        backToChatsBtn.addEventListener('click', () => {
            chatContainer.classList.remove('mobile-chat-view');
            // --- Mobile Chat View Trigger ---
            chatRoomList.querySelectorAll('.chat-room').forEach(room => {
            room.addEventListener('click', () => {
                if (window.innerWidth <= 768) {
            chatContainer.classList.add('mobile-chat-view');
        }
    });
});

        });
    }

    // --- 9. Socket Listener: New Chat Room Added ---
    socket.on('new_chat_room', (room) => {
        addChatToList(room); 
        if (room.contact_id && !room.is_group) {
            addContactToCreateModal(room.name, room.contact_id);
        }
    });

    // --- 10. Socket Listener: Message Deleted ---
    socket.on('message_deleted', (data) => {
        const msgEl = document.querySelector(`div[data-message-id="${data.message_id}"]`);
        if (msgEl) {
            msgEl.remove();
        }
    });

    // --- 11. Socket Listener: Removed from Group ---
    socket.on('removed_from_group', (data) => {
        const roomEl = chatRoomList.querySelector(`li[data-room-id="${data.room_id}"]`);
        if (roomEl) {
            roomEl.remove();
        }
        if (selectedRoomId === data.room_id.toString()) {
            chatContainer.classList.remove('mobile-chat-view');
            selectedRoomId = null;
            selectedUserSpan.textContent = 'Select a chat to begin';
            selectedChatPic.style.display = 'none'; 
            messageInput.disabled = true;
            sendButton.disabled = true;
            manageGroupBtn.style.display = 'none';
            leaveGroupBtn.style.display = 'none'; 
            messagesDiv.innerHTML = '';
            alert("You have been removed from this group.");
        }
    });

    // --- 12. Socket Listener: Group Pic Updated ---
    socket.on('group_pic_updated', (data) => {
        const { room_id, new_pic_url } = data;
        
        // 1. Update sidebar
        const roomEl = chatRoomList.querySelector(`li[data-room-id="${room_id}"]`);
        if (roomEl) {
            roomEl.querySelector('img').src = new_pic_url;
        }
        
        // 2. Update header (if it's the selected chat)
        if (selectedRoomId === room_id.toString()) {
            selectedChatPic.src = new_pic_url;
        }
    });

    // --- 13. Manage Group Modal Logic ---
    if (manageGroupBtn) { manageGroupBtn.addEventListener('click', () => { if (selectedRoomId) { openManageGroupModal(selectedRoomId); } }); }
    if (closeManageModalBtn) { closeManageModalBtn.addEventListener('click', () => { manageGroupModal.style.display = 'none'; }); }
    window.addEventListener('click', (event) => { if (event.target == manageGroupModal) { manageGroupModal.style.display = 'none'; } });
    
    // --- 14. Group Pic Upload Logic ---
    if (groupPicUploadBtn) {
        groupPicUploadBtn.addEventListener('click', async () => {
            const file = groupPicInput.files[0];
            if (!file) {
                alert('Please select a file first.');
                return;
            }
            if (!selectedRoomId) return;

            const formData = new FormData();
            formData.append('group_pic', file);

            try {
                const response = await fetch(`/api/group/${selectedRoomId}/upload-pic`, {
                    method: 'POST',
                    body: formData,
                    credentials: 'include'
                });
                
                if (response.ok) {
                    alert('Group icon updated!');
                    groupPicInput.value = ''; 
                } else {
                    const err = await response.json();
                    alert(`Upload failed: ${err.error}`);
                }
            } catch (err) {
                console.error('Group pic upload error:', err);
                alert('An error occurred.');
            }
        });
    }
    // --- 15. Leave Group Button Logic ---
    if (leaveGroupBtn) {
        leaveGroupBtn.addEventListener('click', async () => {
            if (!selectedRoomId) return;
            if (!confirm('Are you sure you want to leave this group?')) return;
            try {
                const response = await fetch(`/api/group/${selectedRoomId}/leave`, { method: 'POST', credentials: 'include' });
                const data = await response.json();
                if (response.ok) {
                    const roomEl = chatRoomList.querySelector(`li[data-room-id="${data.room_id}"]`);
                    if (roomEl) { roomEl.remove(); }
                    backToChatsBtn.click();
                } else {
                    alert(`Error: ${data.error}`);
                }
            } catch (err) {
                console.error('Failed to leave group:', err);
                alert('An error occurred.');
            }
        });
    }

    // --- 16. Manage Blocked Modal Logic ---
    if (openBlockModalBtn) {
        openBlockModalBtn.addEventListener('click', () => {
            openManageBlockModal();
        });
    }
    if (closeBlockModalBtn) { closeBlockModalBtn.addEventListener('click', () => { manageBlockModal.style.display = 'none'; }); }
    window.addEventListener('click', (event) => { if (event.target == manageBlockModal) { manageBlockModal.style.display = 'none'; } });

    // --- 17. Socket Error Listener ---
    socket.on('error', (data) => {
        alert(data.message);
    });

    // --- HELPER FUNCTIONS ---

    function addContactToCreateModal(username, userId) {
        const existingEntry = groupMembersList.querySelector(`input[data-id="${userId}"]`);
        if (existingEntry) { return; }
        const li = document.createElement('li');
        li.innerHTML = `<label><input type="checkbox" class="group-user-select" data-id="${userId}"> ${username}</label>`;
        groupMembersList.appendChild(li);
    }

    function addChatToList(room) {
        let existingRoomEl = chatRoomList.querySelector(`.chat-room[data-room-id="${room.id}"]`);
        
        const img = document.createElement('img');
        img.src = room.profile_pic_url;
        img.alt = room.name;
        img.className = 'profile-pic-small';
        
        const nameSpan = document.createElement('span');
        nameSpan.className = 'chat-room-name';
        nameSpan.textContent = room.name;

        if (existingRoomEl) {
            existingRoomEl.querySelector('img').src = room.profile_pic_url;
            existingRoomEl.querySelector('.chat-room-name').textContent = room.name;
            existingRoomEl.dataset.creatorId = room.creator_id || 0;
            return existingRoomEl;
        }
        
        const newRoomEl = document.createElement('li');
        newRoomEl.className = 'chat-room';
        newRoomEl.dataset.roomId = room.id;
        newRoomEl.dataset.isGroup = room.is_group;
        newRoomEl.dataset.creatorId = room.creator_id || 0;
        
        newRoomEl.appendChild(img);
        newRoomEl.appendChild(nameSpan);
        
        newRoomEl.addEventListener('click', () => selectChatRoom(newRoomEl));
        
        chatRoomList.appendChild(newRoomEl);
        return newRoomEl;
    }

    function selectChatRoom(roomElement) {
        chatRoomList.querySelectorAll('.chat-room').forEach(el => el.classList.remove('active'));
        roomElement.classList.add('active');
        
        messageInput.disabled = false;
        sendButton.disabled = false;
        
        const newRoomId = roomElement.dataset.roomId;
        const roomName = roomElement.querySelector('.chat-room-name').textContent.trim();
        
        const picSrc = roomElement.querySelector('img').src;
        selectedChatPic.src = picSrc;
        selectedChatPic.style.display = 'inline-block';
        
        const isGroup = roomElement.dataset.isGroup === 'true';
        const creatorId = roomElement.dataset.creatorId;

        manageGroupBtn.style.display = 'none';
        leaveGroupBtn.style.display = 'none';

        if (isGroup) {
            if (creatorId == currentUserId) {
                manageGroupBtn.style.display = 'inline-block';
            } else {
                leaveGroupBtn.style.display = 'inline-block';
            }
        }
        
        if (newRoomId === selectedRoomId) {
            chatContainer.classList.add('mobile-chat-view');
            return;
        }

        selectedRoomId = newRoomId;
        selectedUserSpan.textContent = `${roomName}`;
        
        socket.emit('join_room', { 'room_id': selectedRoomId });
        
        loadMessages(selectedRoomId);

        chatContainer.classList.add('mobile-chat-view');
    }

    function loadMessages(roomId) {
        fetch(`/api/messages/${roomId}`, { credentials: 'include' })
            .then(response => response.json())
            .then(messages => {
                messagesDiv.innerHTML = '';
                messages.forEach(msg => {
                    addMessageToUI(msg);
                });
                scrollToBottom();
            })
            .catch(err => console.error("Error loading messages:", err));
    }

    function addMessageToUI(msg) {
        
        if (msg.message_type === 'system') {
            const systemMsgEl = document.createElement('div');
            systemMsgEl.className = 'system-message';
            systemMsgEl.textContent = msg.content;
            messagesDiv.appendChild(systemMsgEl);
            scrollToBottom();
            return;
        }
        
        const isSent = msg.sender_id === currentUserId;
        const messageElement = document.createElement('div');
        messageElement.className = `message ${isSent ? 'sent' : 'received'}`;
        messageElement.dataset.messageId = msg.message_id;

        if (msg.temp_id) {
            messageElement.id = msg.temp_id;
        }

        const messageRow = document.createElement('div');
        messageRow.className = 'message-row';

        const pic = document.createElement('img');
        pic.src = msg.sender_profile_pic;
        pic.className = 'profile-pic-small';
        messageRow.appendChild(pic);
        
        const messageContainer = document.createElement('div');
        messageContainer.className = 'message-container';

        const messageContent = document.createElement('div');
        messageContent.className = 'message-content';
        
        const fileUrl = `/api/file/${msg.message_id}`;

        switch (msg.message_type) {
            case 'text':
                messageContent.textContent = msg.content;
                break;
            case 'image':
                const img = document.createElement('img');
                img.src = fileUrl;
                img.alt = msg.original_filename;
                img.onload = () => scrollToBottom();
                messageContent.appendChild(img);
                break;
            case 'video':
                const video = document.createElement('video');
                video.src = fileUrl;
                video.controls = true;
                video.onloadeddata = () => scrollToBottom();
                messageContent.appendChild(video);
                break;
            case 'file':
            default:
                const link = document.createElement('a');
                link.href = fileUrl;
                link.textContent = `Download: ${msg.original_filename}`;
                link.className = 'file-link';
                messageContent.appendChild(link);
                break;
        }
        
        const chatRoom = chatRoomList.querySelector(`.chat-room.active`); 
        if (chatRoom && !isSent && chatRoom.dataset.isGroup === 'true') {
            const senderName = document.createElement('span');
            senderName.className = 'message-sender';
            senderName.textContent = msg.sender_name;
            messageContainer.appendChild(senderName);
        }

        const messageMeta = document.createElement('div');
        messageMeta.className = 'message-meta';
        messageMeta.innerHTML = `<span class="message-time">${msg.timestamp}</span>`;
        
        messageContainer.appendChild(messageContent);
        messageContainer.appendChild(messageMeta);

        if (isSent && msg.message_id) { 
            
            const deleteBtn = document.createElement('button');
            deleteBtn.className = 'delete-msg-btn';
            deleteBtn.innerHTML = '&times;';
            deleteBtn.title = 'Delete message';
            deleteBtn.addEventListener('click', (e) => {
                e.stopPropagation(); 
                if (confirm('Are you sure you want to delete this message?')) {
                    socket.emit('delete_message', { 'message_id': msg.message_id });
                }
            });
            messageContainer.appendChild(deleteBtn);
            
            if (isTouchDevice) {
                let pressTimer;
                messageContainer.addEventListener('touchstart', (e) => {
                    pressTimer = window.setTimeout(() => {
                        e.preventDefault(); 
                        if (confirm('Are you sure you want to delete this message?')) {
                            socket.emit('delete_message', { 'message_id': msg.message_id });
                        }
                    }, 500); 
                });
                const onTouchEnd = () => { clearTimeout(pressTimer); };
                const onTouchMove = () => { clearTimeout(pressTimer); };
                messageContainer.addEventListener('touchstart', onTouchStart);
                messageContainer.addEventListener('touchend', onTouchEnd);
                messageContainer.addEventListener('touchcancel', onTouchEnd);
                messageContainer.addEventListener('touchmove', onTouchMove);
            }
        }
        
        messageRow.appendChild(messageContainer);
        messageElement.appendChild(messageRow);
        
        messagesDiv.appendChild(messageElement);
        scrollToBottom();
    }

    async function openManageGroupModal(roomId) {
        try {
            const response = await fetch(`/api/group/${roomId}/members`, { credentials: 'include' });
            if (!response.ok) { const err = await response.json(); alert(`Error: ${err.error}`); return; }
            const data = await response.json(); 
            manageRemoveList.innerHTML = '';
            manageAddList.innerHTML = '';
            data.current_members.forEach(user => { addUserToManageLists(user, 'remove'); });
            data.addable_contacts.forEach(user => { addUserToManageLists(user, 'add'); });
            manageGroupModal.style.display = 'block';
        } catch (err) { console.error('Failed to open manage modal:', err); alert('An error occurred.'); }
    }
    function addUserToManageLists(user, listType) {
        const li = document.createElement('li');
        li.className = 'manage-user-item';
        li.dataset.userId = user.id; li.dataset.username = user.username;
        const span = document.createElement('span');
        span.textContent = user.username;
        const btn = document.createElement('button');
        if (listType === 'remove') {
            btn.textContent = 'Remove';
            btn.dataset.userId = user.id;
            btn.addEventListener('click', () => handleRemoveMember(user.id));
            manageRemoveList.appendChild(li);
        } else {
            btn.textContent = 'Add';
            btn.className = 'add-btn';
            btn.dataset.userId = user.id;
            btn.addEventListener('click', () => handleAddMember(user.id));
            manageAddList.appendChild(li);
        }
        li.appendChild(span);
        li.appendChild(btn);
    }
    function removeUserFromManageLists(userId) {
        const removeRow = manageRemoveList.querySelector(`li[data-user-id="${userId}"]`);
        if (removeRow) removeRow.remove();
        const addRow = manageAddList.querySelector(`li[data-user-id="${userId}"]`);
        if (addRow) addRow.remove();
    }
    async function handleRemoveMember(userId) {
        if (!confirm('Are you sure you want to remove this member?')) return;
        try {
            const response = await fetch(`/api/group/${selectedRoomId}/remove_member`, {
                method: 'POST', headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ 'user_id': userId }), credentials: 'include'
            });
            const data = await response.json();
            if (response.ok) {
                removeUserFromManageLists(data.user.id);
                addUserToManageLists(data.user, 'add');
            } else { alert(`Error: ${data.error}`); }
        } catch (err) { alert('An error occurred.'); }
    }
    async function handleAddMember(userId) {
        try {
            const response = await fetch(`/api/group/${selectedRoomId}/add_member`, {
                method: 'POST', headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ 'user_id': userId }), credentials: 'include'
            });
            const data = await response.json();
            if (response.ok) {
                removeUserFromManageLists(data.user.id);
                addUserToManageLists(data.user, 'remove');
            } else { alert(`Error: ${data.error}`); }
        } catch (err) { alert('An error occurred.'); }
    }
    async function openManageBlockModal() {
        try {
            const response = await fetch('/api/user/block_list', { credentials: 'include' }); 
            if (!response.ok) { const err = await response.json(); alert(`Error: ${err.error}`); return; }
            const data = await response.json(); 
            manageUnblockedList.innerHTML = '';
            manageBlockedList.innerHTML = '';
            data.unblocked_contacts.forEach(user => { addUserToBlockLists(user, 'unblocked'); });
            data.blocked_contacts.forEach(user => { addUserToBlockLists(user, 'blocked'); });
            manageBlockModal.style.display = 'block';
        } catch (err) { console.error('Failed to open block modal:', err); alert('An error occurred.'); }
    }
    function addUserToBlockLists(user, listType) {
        const li = document.createElement('li');
        li.className = 'manage-user-item';
        li.dataset.userId = user.id; li.dataset.username = user.username;
        const span = document.createElement('span');
        span.textContent = user.username;
        const btn = document.createElement('button');
        if (listType === 'blocked') {
            btn.textContent = 'Unblock';
            btn.className = 'unblock-btn';
            btn.dataset.userId = user.id;
            btn.addEventListener('click', () => handleUnblockUser(user.id));
            manageBlockedList.appendChild(li);
        } else {
            btn.textContent = 'Block';
            btn.className = 'block-btn';
            btn.dataset.userId = user.id;
            btn.addEventListener('click', () => handleBlockUser(user.id));
            manageUnblockedList.appendChild(li);
        }
        li.appendChild(span);
        li.appendChild(btn);
    }
    
    function removeUserFromBlockLists(userId) { 
        const unblockedRow = manageUnblockedList.querySelector(`li[data-user-id="${userId}"]`);
        if (unblockedRow) unblockedRow.remove();
        
        const blockedRow = manageBlockedList.querySelector(`li[data-user-id="${userId}"]`);
        if (blockedRow) blockedRow.remove();
    }

    async function handleBlockUser(userId) {
        if (!confirm('Are you sure you want to block this user? They will not be able to message you, and you will not be able to message them.')) return;
        try {
            const response = await fetch('/api/user/block', {
                method: 'POST', headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ 'user_id': userId }), credentials: 'include'
            });
            const data = await response.json();
            if (response.ok) {
                removeUserFromBlockLists(data.user.id);
                addUserToBlockLists(data.user, 'blocked');
                const chatRoomEl = findDmChatElementByUsername(data.user.username);
                if (chatRoomEl) {
                    if (chatRoomEl.dataset.roomId === selectedRoomId) { backToChatsBtn.click(); }
                    chatRoomEl.remove();
                }
            } else { alert(`Error: ${data.error}`); }
        } catch (err) { alert('An error occurred.'); }
    }
    async function handleUnblockUser(userId) {
        try {
            const response = await fetch('/api/user/unblock', {
                method: 'POST', headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ 'user_id': userId }), credentials: 'include'
            });
            const data = await response.json();
            if (response.ok) {
                removeUserFromBlockLists(data.user.id);
                addUserToBlockLists(data.user, 'unblocked');
                addChatToList({
                    id: `dm-user-${data.user.id}`, 
                    name: data.user.username, 
                    is_group: false, creator_id: 0,
                    profile_pic_url: data.user.profile_pic_url 
                });
            } else { alert(`Error: ${data.error}`); }
        } catch (err) { alert('An error occurred.'); }
    }
    function findDmChatElementByUsername(username) {
        const chatRooms = chatRoomList.querySelectorAll('.chat-room');
        for (const roomEl of chatRooms) {
            if (roomEl.dataset.isGroup === 'false' && roomEl.querySelector('.chat-room-name').textContent.trim() === username) {
                return roomEl;
            }
        }
        return null;
    }
    function scrollToBottom() {
        messagesDiv.scrollTop = messagesDiv.scrollHeight;
    }
});