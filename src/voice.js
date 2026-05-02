// voice.js — Voice command console
// Connects to the shared WebSocket and displays voice messages only.
// Does NOT touch EOG logic.

(function () {
    // ── Theme ─────────────────────────────────────────────────────────────────
    const savedTheme = localStorage.getItem('theme');
    if (savedTheme === 'dark') {
        document.documentElement.setAttribute('data-theme', 'dark');
    }

    const themeBtn = document.getElementById('theme-toggle');
    const icon     = document.getElementById('mode');
    const orb = document.getElementById('voice-orb');

    function setState(state) {
        orb.classList.remove('listening', 'thinking', 'speaking');
        if (state) orb.classList.add(state);
        }
    // Set correct icon on load
    icon.src = savedTheme === 'dark' ? '../Icons/sun.png' : '../Icons/moon.png';

    themeBtn.addEventListener('click', () => {
        const isDark = document.documentElement.getAttribute('data-theme') === 'dark';
        if (isDark) {
            document.documentElement.removeAttribute('data-theme');
            localStorage.setItem('theme', 'light');
            icon.src = '../Icons/moon.png';
        } else {
            document.documentElement.setAttribute('data-theme', 'dark');
            localStorage.setItem('theme', 'dark');
            icon.src = '../Icons/sun.png';
        }
    });

    // ── Back button ───────────────────────────────────────────────────────────
    document.getElementById('back-btn').addEventListener('click', () => {
        window.location.href = 'index.html';
    });

    // ── DOM refs ──────────────────────────────────────────────────────────────
    const log      = document.getElementById('voice-log');
    const empty    = document.getElementById('voice-empty');
    const badge    = document.getElementById('ws-status');

    // ── WebSocket ─────────────────────────────────────────────────────────────
    const WS_URL           = 'ws://localhost:8765';
    const RECONNECT_DELAY  = 3000;
    let ws                 = null;
    let messageCount       = 0;

    function connect() {
        // Detach old listeners before creating a new connection
        if (ws) {
            ws.onopen    = null;
            ws.onclose   = null;
            ws.onerror   = null;
            ws.onmessage = null;
            ws.close();
        }

        ws = new WebSocket(WS_URL);

        ws.addEventListener('open', () => {
            badge.textContent = 'Connected';
            badge.className   = 'ws-badge ws-connected';
        });

        ws.addEventListener('close', () => {
            badge.textContent = 'Reconnecting...';
            badge.className   = 'ws-badge ws-connecting';
            setTimeout(connect, RECONNECT_DELAY);
        });

        ws.addEventListener('error', () => {
            badge.textContent = 'Error';
            badge.className   = 'ws-badge ws-error';
            // close will fire after error and handle the reconnect
        });

        ws.addEventListener('message', (event) => {
            let msg;
            try { msg = JSON.parse(event.data); } catch { return; }

            if (msg.type === 'user_transcript') {
                addMessage(msg.text, 'user');
                setState('thinking');
            }
            else if (msg.type === 'assistant_reply') {
                addMessage(msg.text, 'system');
                setState('speaking');
            }
            else if (msg.type === 'voice_status') {
                addMessage(msg.text, 'system');
            }
            else if (msg.type === 'voice_state') {
                setState(msg.state);
            }
        });
    }

    connect();

    // ── Message renderer ──────────────────────────────────────────────────────
    function addMessage(text, type) {
        if (!text || !text.trim()) return;

        // Hide the empty state once first message arrives
        if (messageCount === 0) {
            empty.style.display = 'none';
        }
        messageCount++;

        const div = document.createElement('div');
        div.classList.add('voice-msg');

        if (type === 'user') {
            div.classList.add('voice-user');
            div.textContent = '🗣️  ' + text;
        } else {
            div.classList.add('voice-system');
            div.textContent =  text;
        }

        log.appendChild(div);
        log.scrollTop = log.scrollHeight;
    }

})();