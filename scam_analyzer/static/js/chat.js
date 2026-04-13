// ── SEND, ANALYZE, RENDER MESSAGES, EDIT ─────────────────────────────────────

async function sendMessage() {
    const input = document.getElementById('textInput'), text = input.value.trim();
    if (!text && !currentFile) return;
    document.getElementById('welcomeScreen')?.remove();
    const displayText = currentFile ? `📷 ${currentFile.name}` : text;
    if (editingMsgIndex !== null) { await submitEdit(text, displayText); return; }
    input.value = '';
    appendUserMsg(displayText, currentMessages.length);
    await doAnalyze(text, displayText, null);
    clearFile();
}

async function doAnalyze(text, displayText, replaceAtBotIdx) {
    const thinkingId = appendThinking();
    const form = new FormData();
    form.append('text', text);
    form.append('type', currentMode);
    if (currentFile) form.append('image', currentFile);
    try {
        const res = await fetch('/analyze', {
            method: 'POST',
            headers: { 'X-CSRFToken': CSRF_TOKEN },
            body: form
        });
        const data = await res.json();
        removeThinking(thinkingId);
        if (data.error) { appendErrorMsg(data.error); return; }
        const shown = data.results
            ? (data.results[currentLang] || data.results.kz || data.results.ru)
            : data.result;
        if (replaceAtBotIdx !== null) {
            replaceBotInDom(replaceAtBotIdx, shown, data.score, data.level, data.results);
            if (currentMessages[replaceAtBotIdx])
                currentMessages[replaceAtBotIdx] = {
                    type: 'bot', result: data.result,
                    score: data.score, level: data.level, results: data.results
                };
            const chat = chatHistory.find(c => c.id === currentChatId);
            if (chat) { chat.messages = currentMessages; persist(); }
        } else {
            appendBotMsg(shown, data.score, data.level, true, data.results);
            saveChat(displayText, data.result, data.score, data.level, data.results);
        }
    } catch (e) {
        removeThinking(thinkingId);
        appendErrorMsg('❌ Network error');
    }
}

function newChat() {
    currentChatId = null; currentMessages = []; editingMsgIndex = null;
    document.getElementById('chatMessages').innerHTML =
        `<div class="welcome-screen" id="welcomeScreen">
            <div class="welcome-icon">⬡</div>
            <h1 class="welcome-title">ScamShield AI</h1>
            <p class="welcome-sub">${T('subtitle')}</p>
            <div class="quick-actions">
                <button class="quick-btn" onclick="quickCheck('phone')">📱 ${T('phone_check')}</button>
                <button class="quick-btn" onclick="quickCheck('link')">🔗 ${T('link_check')}</button>
                <button class="quick-btn" onclick="quickCheck('text')">💬 ${T('new_chat')}</button>
            </div>
        </div>`;
    loadHistory();
}

function loadChat(chatId) {
    const chat = chatHistory.find(c => c.id === chatId);
    if (!chat) return;
    currentChatId = chatId;
    currentMessages = chat.messages ? JSON.parse(JSON.stringify(chat.messages)) : [];
    editingMsgIndex = null;
    document.getElementById('chatMessages').innerHTML = '';
    currentMessages.forEach((msg, idx) => {
        if (msg.type === 'user') appendUserMsg(msg.text, idx);
        else {
            const shown = msg.results
                ? (msg.results[currentLang] || msg.results.kz || msg.results.ru)
                : msg.result;
            appendBotMsg(shown, msg.score, msg.level, false, msg.results);
        }
    });
    loadHistory();
}

// ── EDIT ──────────────────────────────────────────────────────────────────────

function startEdit(userMsgIdx) {
    const msg = currentMessages[userMsgIdx];
    if (!msg || msg.type !== 'user') return;
    editingMsgIndex = userMsgIdx;
    const domEl = getUserMsgDom(userMsgIdx);
    if (!domEl) return;
    const bubble = domEl.querySelector('.msg-bubble');
    const editArea = domEl.querySelector('.edit-area');
    const editInp = domEl.querySelector('.edit-input');
    const actions = domEl.querySelector('.msg-actions');
    editInp.value = msg.text;
    if (bubble) bubble.style.display = 'none';
    if (actions) actions.style.display = 'none';
    if (editArea) editArea.classList.add('active');
    editInp.focus(); editInp.select();
}

function cancelEdit(userMsgIdx) {
    editingMsgIndex = null;
    const domEl = getUserMsgDom(userMsgIdx);
    if (!domEl) return;
    domEl.querySelector('.msg-bubble').style.display = '';
    domEl.querySelector('.msg-actions').style.display = '';
    domEl.querySelector('.edit-area').classList.remove('active');
}

async function submitEdit(text, displayText) {
    const idx = editingMsgIndex;
    editingMsgIndex = null;
    if (currentMessages[idx]) currentMessages[idx].text = displayText;
    const domEl = getUserMsgDom(idx);
    if (domEl) {
        const bubble = domEl.querySelector('.msg-bubble');
        const editArea = domEl.querySelector('.edit-area');
        const actions = domEl.querySelector('.msg-actions');
        if (bubble) { bubble.innerHTML = escHtml(displayText); bubble.style.display = ''; }
        if (actions) actions.style.display = '';
        if (editArea) editArea.classList.remove('active');
    }
    document.getElementById('textInput').value = '';
    await doAnalyze(text, displayText, idx + 1);
    clearFile();
}

function getUserMsgDom(idx) {
    let n = 0;
    for (let i = 0; i < idx; i++) {
        if (currentMessages[i] && currentMessages[i].type === 'user') n++;
    }
    return document.querySelectorAll('.user-msg')[n] || null;
}

// ── RENDER ────────────────────────────────────────────────────────────────────

function appendUserMsg(text, msgIdx) {
    const msgs = document.getElementById('chatMessages');
    const div = document.createElement('div');
    div.className = 'msg user-msg';
    div.innerHTML =
        `<div class="msg-bubble">${escHtml(text)}</div>
        <div class="msg-actions">
            <button class="msg-action-btn" onclick="startEdit(${msgIdx})">✏️ ${T('edit')}</button>
        </div>
        <div class="edit-area">
            <textarea class="edit-input"
                onkeydown="if(event.key==='Enter'&&!event.shiftKey){event.preventDefault();document.getElementById('textInput').value=this.value;sendMessage();}
                           if(event.key==='Escape')cancelEdit(${msgIdx})"></textarea>
            <div class="edit-btns">
                <button class="edit-cancel" onclick="cancelEdit(${msgIdx})">${T('cancel')}</button>
                <button class="edit-save"
                    onclick="document.getElementById('textInput').value=this.closest('.edit-area').querySelector('.edit-input').value;sendMessage()">${T('save')}</button>
            </div>
        </div>`;
    msgs.appendChild(div);
    msgs.scrollTop = msgs.scrollHeight;
}

function appendThinking() {
    const msgs = document.getElementById('chatMessages');
    const id = 'think_' + Date.now();
    const div = document.createElement('div');
    div.className = 'msg bot-msg'; div.id = id;
    div.innerHTML =
        `<div class="bot-avatar">⬡</div>
        <div class="msg-bubble thinking"><span></span><span></span><span></span></div>`;
    msgs.appendChild(div);
    msgs.scrollTop = msgs.scrollHeight;
    return id;
}

function removeThinking(id) { document.getElementById(id)?.remove(); }

function appendBotMsg(result, score, level, animate, results) {
    const msgs = document.getElementById('chatMessages');
    const div = document.createElement('div');
    div.className = 'msg bot-msg' + (animate ? ' fade-in' : '');
    if (results) div.dataset.results = JSON.stringify(results);
    const rl = { low: T('risk_low'), medium: T('risk_medium'), high: T('risk_high') };
    div.innerHTML =
        `<div class="bot-avatar">⬡</div>
        <div class="msg-content">
            <div class="msg-bubble bot-bubble"><div class="result-text">${result}</div></div>
            <div class="risk-bar-wrap">
                <div class="risk-info">
                    <span class="risk-label risk-${level}">${rl[level] || ''}</span>
                    <span class="risk-score">${score}%</span>
                </div>
                <div class="risk-bar">
                    <div class="risk-fill risk-fill-${level}" style="width:0%" data-target="${score}"></div>
                </div>
            </div>
        </div>`;
    msgs.appendChild(div);
    msgs.scrollTop = msgs.scrollHeight;
    setTimeout(() => {
        const f = div.querySelector('.risk-fill');
        if (f) f.style.width = f.dataset.target + '%';
    }, animate ? 100 : 0);
}

function appendErrorMsg(text) {
    const msgs = document.getElementById('chatMessages');
    const div = document.createElement('div');
    div.className = 'msg bot-msg';
    div.innerHTML =
        `<div class="bot-avatar">⬡</div>
        <div class="msg-bubble error-bubble">${text}</div>`;
    msgs.appendChild(div);
    msgs.scrollTop = msgs.scrollHeight;
}

function replaceBotInDom(botMsgIdx, result, score, level, results) {
    let n = 0;
    for (let i = 0; i < botMsgIdx; i++) {
        if (currentMessages[i] && currentMessages[i].type === 'bot') n++;
    }
    const domBot = Array.from(document.querySelectorAll('.bot-msg:not([id])'))[n];
    if (!domBot) { appendBotMsg(result, score, level, true, results); return; }
    const rl = { low: T('risk_low'), medium: T('risk_medium'), high: T('risk_high') };
    if (results) domBot.dataset.results = JSON.stringify(results);
    const te = domBot.querySelector('.result-text');
    const le = domBot.querySelector('.risk-label');
    const se = domBot.querySelector('.risk-score');
    const fi = domBot.querySelector('.risk-fill');
    if (te) te.innerHTML = result;
    if (le) { le.className = `risk-label risk-${level}`; le.textContent = rl[level] || ''; }
    if (se) se.textContent = score + '%';
    if (fi) {
        fi.className = `risk-fill risk-fill-${level}`;
        fi.dataset.target = score;
        fi.style.width = '0%';
        setTimeout(() => fi.style.width = score + '%', 100);
    }
}

// ── FILE ──────────────────────────────────────────────────────────────────────

function handleFile(input) {
    if (input.files[0]) {
        currentFile = input.files[0];
        document.getElementById('filePreview').style.display = 'flex';
        document.getElementById('fileName').textContent = currentFile.name;
    }
}

function clearFile() {
    currentFile = null;
    document.getElementById('fileInput').value = '';
    document.getElementById('filePreview').style.display = 'none';
}

function escHtml(s) {
    return String(s)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;');
}