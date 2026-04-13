// ── CHAT HISTORY, LOCALSTORAGE, CONTEXT MENU, RENAME, ARCHIVE ────────────────

function renderList(id, chats) {
    const el = document.getElementById(id);
    if (!chats.length) { el.innerHTML = `<div class="no-history">${T('no_history')}</div>`; return; }
    el.innerHTML = chats.map(c =>
        `<div class="history-item ${c.id === currentChatId ? 'active' : ''}" onclick="loadChat('${c.id}')">
            <div class="history-item-left">
                <span class="history-title">${escHtml(c.title)}</span>
                <span class="history-date">${c.date || ''}</span>
            </div>
            <button class="history-menu-btn" onclick="openCtxMenu(event,'${c.id}')">⋯</button>
        </div>`
    ).join('');
}

function loadHistory() {
    renderList('historyList', chatHistory.filter(c => !c.archived));
    const arch = chatHistory.filter(c => c.archived);
    const btn = document.getElementById('archiveToggleBtn');
    document.getElementById('archiveToggleLabel').textContent = T('archive_label');
    if (arch.length) {
        btn.style.display = 'flex';
        document.getElementById('archiveCount').textContent = `(${arch.length})`;
        renderList('archiveList', arch);
    } else {
        btn.style.display = 'none';
        document.getElementById('archiveList').innerHTML = '';
        document.getElementById('archiveSection').classList.remove('open');
    }
}

function toggleArchiveSection() {
    document.getElementById('archiveSection').classList.toggle('open');
}

function persist() {
    localStorage.setItem('chatHistory', JSON.stringify(chatHistory.slice(0, 100)));
}

function saveChat(userText, result, score, level, results) {
    const today = new Date().toLocaleDateString(
        currentLang === 'kz' ? 'kk-KZ' : currentLang === 'ru' ? 'ru-RU' : 'en-US');
    if (!currentChatId) {
        currentChatId = Date.now().toString();
        chatHistory.unshift({
            id: currentChatId,
            title: userText.slice(0, 32) + (userText.length > 32 ? '…' : ''),
            date: today, messages: []
        });
    }
    const chat = chatHistory.find(c => c.id === currentChatId);
    if (chat) {
        chat.messages = chat.messages || [];
        chat.messages.push({ type: 'user', text: userText });
        chat.messages.push({ type: 'bot', result, score, level, results });
        currentMessages = JSON.parse(JSON.stringify(chat.messages));
    }
    persist();
    loadHistory();
}

// ── CONTEXT MENU ──────────────────────────────────────────────────────────────

function openCtxMenu(e, chatId) {
    e.stopPropagation();
    ctxTargetId = chatId;
    const menu = document.getElementById('ctxMenu');
    const chat = chatHistory.find(c => c.id === chatId);
    document.getElementById('ctxLabelRename').textContent = T('rename');
    document.getElementById('ctxLabelArchive').textContent =
        (chat && chat.archived) ? T('unarchive') : T('archive');
    document.getElementById('ctxLabelDelete').textContent = T('delete_chat');
    menu.classList.add('open');
    let x = e.clientX, y = e.clientY;
    if (x + 175 > window.innerWidth) x = window.innerWidth - 185;
    if (y + 130 > window.innerHeight) y = window.innerHeight - 140;
    menu.style.left = x + 'px';
    menu.style.top = y + 'px';
}

function closeCtxMenu() {
    document.getElementById('ctxMenu').classList.remove('open');
}

function ctxRename() {
    const id = ctxTargetId;
    closeCtxMenu();
    const chat = chatHistory.find(c => c.id === id);
    if (!chat) return;
    ctxTargetId = id;
    document.getElementById('renameTitleLabel').textContent = T('rename_title');
    document.getElementById('renameCancelBtn').textContent = T('cancel');
    document.getElementById('renameSaveBtn').textContent = T('save_rename');
    document.getElementById('renameInput').value = chat.title;
    document.getElementById('renameModal').classList.add('open');
    setTimeout(() => {
        const inp = document.getElementById('renameInput');
        inp.focus(); inp.select();
    }, 60);
}

function closeRenameModal() {
    document.getElementById('renameModal').classList.remove('open');
}

function confirmRename() {
    const v = document.getElementById('renameInput').value.trim();
    if (!v) return;
    const chat = chatHistory.find(c => c.id === ctxTargetId);
    if (chat) { chat.title = v; persist(); loadHistory(); }
    closeRenameModal();
}

function ctxArchive() {
    const id = ctxTargetId;
    closeCtxMenu();
    const chat = chatHistory.find(c => c.id === id);
    if (!chat) return;
    chat.archived = !chat.archived;
    if (chat.archived && currentChatId === id) newChat();
    persist();
    loadHistory();
}

function ctxDelete() {
    const id = ctxTargetId;
    closeCtxMenu();
    if (!confirm(T('confirm_delete'))) return;
    chatHistory = chatHistory.filter(c => c.id !== id);
    if (currentChatId === id) newChat();
    persist();
    loadHistory();
}