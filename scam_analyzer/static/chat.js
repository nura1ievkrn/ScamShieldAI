// ── SCROLL TO BOTTOM ─────────────────────────────────────────────────────────
(function initScrollBtn() {
    const chatArea  = document.getElementById('chatArea');
    const btn       = document.getElementById('scrollDownBtn');
    const inputWrap = document.querySelector('.input-wrapper');
    const THRESHOLD = 120; // px from bottom before button appears

    function positionBtn() {
        const rect = inputWrap.getBoundingClientRect();
        btn.style.bottom = (window.innerHeight - rect.top + 16) + 'px';
    }

    function updateBtn() {
        const distFromBottom = chatArea.scrollHeight - chatArea.scrollTop - chatArea.clientHeight;
        btn.classList.toggle('visible', distFromBottom > THRESHOLD);
    }

    chatArea.addEventListener('scroll', updateBtn, { passive: true });
    window.addEventListener('resize', positionBtn, { passive: true });

    // Re-check whenever new messages are appended
    new MutationObserver(updateBtn).observe(
        document.getElementById('chatMessages'),
        { childList: true }
    );

    positionBtn();
    updateBtn();
})();

function scrollToBottom() {
    const chatArea = document.getElementById('chatArea');
    chatArea.scrollTo({ top: chatArea.scrollHeight, behavior: 'smooth' });
}