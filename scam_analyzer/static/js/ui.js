// ── SIDEBAR, DROPDOWNS, LANG, MODE ───────────────────────────────────────────

function toggleSidebar() {
    document.getElementById('sidebar').classList.toggle('collapsed');
    document.getElementById('main').classList.toggle('sidebar-collapsed');
}

function toggleUserMenu() {
    document.getElementById('userDropdown').classList.toggle('show');
}

function toggleExportMenu() {
    document.getElementById('exportDropdown').classList.toggle('show');
}

document.addEventListener('click', e => {
    if (!e.target.closest('.user-menu'))
        document.getElementById('userDropdown')?.classList.remove('show');
    if (!e.target.closest('.ctx-menu') && !e.target.closest('.history-menu-btn'))
        closeCtxMenu();
    if (!e.target.closest('.export-menu'))
        document.getElementById('exportDropdown')?.classList.remove('show');
});

function setMode(mode) {
    currentMode = mode;
    document.querySelectorAll('.mode-tab').forEach(b =>
        b.classList.toggle('active', b.dataset.mode === mode));
    document.getElementById('modeLabel').textContent =
        { text: '💬', phone: '📱', link: '🔗' }[mode] + ' ' +
        { text: T('new_chat'), phone: T('phone_check'), link: T('link_check') }[mode];
    document.getElementById('textInput').placeholder =
        { text: T('placeholder'), phone: '+7 (___) ___-__-__', link: 'https://...' }[mode];
}

function quickCheck(mode) {
    setMode(mode);
    document.getElementById('textInput').focus();
}

async function switchLang(lang) {
    fetch('/set_language/' + lang, { redirect: 'manual' });
    currentLang = lang;
    Object.assign(t, uiTexts[lang] || uiTexts.kz);
    document.querySelectorAll('.lang-btn').forEach(b =>
        b.classList.toggle('active', b.dataset.lang === lang));
    document.querySelectorAll('.bot-msg[data-results]').forEach(div => {
        try {
            const r = JSON.parse(div.dataset.results);
            const txt = r[lang] || r.kz || r.ru;
            if (txt) { const el = div.querySelector('.result-text'); if (el) el.innerHTML = txt; }
        } catch (e) {}
    });
    const rl = { low: T('risk_low'), medium: T('risk_medium'), high: T('risk_high') };
    document.querySelectorAll('.risk-label').forEach(el => {
        const lv = ['low', 'medium', 'high'].find(l => el.classList.contains('risk-' + l));
        if (lv) el.textContent = rl[lv];
    });
    document.querySelectorAll('.msg-action-btn').forEach(b => {
        if (b.textContent.includes('✏')) b.innerHTML = `✏️ ${T('edit')}`;
    });
    document.querySelectorAll('.edit-save').forEach(b => b.textContent = T('save'));
    document.querySelectorAll('.edit-cancel').forEach(b => b.textContent = T('cancel'));
    document.getElementById('textInput').placeholder = T('placeholder');
    const sub = document.querySelector('.welcome-sub');
    if (sub) sub.textContent = T('subtitle');
    const me = document.getElementById('modeLabel');
    if (me) me.textContent = {
        text: '💬 ' + T('new_chat'),
        phone: '📱 ' + T('phone_check'),
        link: '🔗 ' + T('link_check')
    }[currentMode] || me.textContent;
    loadHistory();
}