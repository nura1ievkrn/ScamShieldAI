// ── SCROLL TO BOTTOM BUTTON ───────────────────────────────────────────────────

(function () {
    const chatArea  = document.getElementById('chatArea');
    const btn       = document.getElementById('scrollDownBtn');
    const inputWrap = document.querySelector('.input-wrapper');
    const THRESHOLD = 120;

    function positionBtn() {
        const rect = inputWrap.getBoundingClientRect();
        btn.style.bottom = (window.innerHeight - rect.top + 16) + 'px';
    }

    function updateBtn() {
        const dist = chatArea.scrollHeight - chatArea.scrollTop - chatArea.clientHeight;
        btn.classList.toggle('visible', dist > THRESHOLD);
    }

    chatArea.addEventListener('scroll', updateBtn, { passive: true });
    window.addEventListener('resize', positionBtn, { passive: true });
    new MutationObserver(updateBtn).observe(
        document.getElementById('chatMessages'), { childList: true });

    positionBtn();
    updateBtn();
})();

function scrollToBottom() {
    document.getElementById('chatArea').scrollTo({ top: Infinity, behavior: 'smooth' });
}