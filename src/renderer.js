// renderer.js — EOG dashboard
// Handles: EOG signal charts, direction display, settings, theme, voice log.

const { ipcRenderer } = require('electron');
const fs              = require('fs');
let audioLevel = 0;
// ── Theme ─────────────────────────────────────────────────────────────────────
const themeBtn     = document.getElementById('theme-toggle');
const icon         = document.getElementById('mode');
const currentTheme = localStorage.getItem('theme');

if (currentTheme === 'dark') {
    document.documentElement.setAttribute('data-theme', 'dark');
    icon.src = '../Icons/sun.png';
} else {
    document.documentElement.removeAttribute('data-theme');
    icon.src = '../Icons/moon.png';
}

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

// ── WebSocket ─────────────────────────────────────────────────────────────────
let eogCount = 0;
const ws = new WebSocket('ws://localhost:8765');

ws.addEventListener('open',  () => console.log('[WS] Connected'));
ws.addEventListener('close', () => console.log('[WS] Disconnected'));
ws.addEventListener('error', (e) => console.error('[WS] Error', e));

// ── EOG charts + voice log ────────────────────────────────────────────────────
window.addEventListener('DOMContentLoaded', () => {

    // Charts
    const canvas1 = document.getElementById('eegChart1');
    const canvas2 = document.getElementById('eegChart2');
    if (!canvas1 || !canvas2) return;

    const chartOpts = {
        millisPerPixel: 20,
        grid:           { strokeStyle: '#555', lineWidth: 1 },
        labels:         { fillStyle: '#AAA' },
        maxValue:        1,
        minValue:       -1,
        interpolation:  'linear',
        maxDataSetLength: 500,
    };

    const eogChart1 = new SmoothieChart(chartOpts);
    const eogChart2 = new SmoothieChart(chartOpts);

    eogChart1.streamTo(canvas1, 1000);
    eogChart2.streamTo(canvas2, 1000);

    const verticalSeries   = new TimeSeries();
    const horizontalSeries = new TimeSeries();

    eogChart1.addTimeSeries(verticalSeries,   { strokeStyle: '#00fd98', lineWidth: 2 });
    eogChart2.addTimeSeries(horizontalSeries, { strokeStyle: '#00fd98', lineWidth: 2 });

    // WebSocket message handler
    ws.onmessage = (event) => {
        let msg;
        try {
            msg = JSON.parse(event.data);
        } catch {
            return;
        }

        // EOG messages
        if (msg.stat !== 'ACTIVE') return;

        eogCount++;
        const now = Date.now();
        verticalSeries.append(now, msg.v);
        horizontalSeries.append(now, msg.h);
        showDirection(msg.dir_x, msg.dir_y);

        if (msg.type === "audio_level") {
            audioLevel = msg.level;
            updateOrb();
            return;
        }``
    };

    // Settings save
    document.getElementById('save-settings').addEventListener('click', () => {
        saveSettings(getSettings());
        ipcRenderer.send('restart-python');
    });
});


// ── D-pad direction display ───────────────────────────────────────────────────
function showDirection(dir_x, dir_y) {
    document.querySelectorAll('.arrow').forEach(a => a.classList.remove('active'));
    if (dir_y === 'UP')    document.getElementById('up').classList.add('active');
    if (dir_y === 'DOWN')  document.getElementById('down').classList.add('active');
    if (dir_x === 'LEFT')  document.getElementById('left').classList.add('active');
    if (dir_x === 'RIGHT') document.getElementById('right').classList.add('active');
}


let smoothedLevel = 0;

function updateOrb() {
    const orb = document.getElementById("orb");
    if (!orb) return;

    smoothedLevel = smoothedLevel * 0.8 + audioLevel * 0.2;

    const intensity = Math.min(smoothedLevel * 20, 1);

    const scale = 1 + intensity * 0.6;
    const glow  = 20 + intensity * 80;

    orb.style.transform = `scale(${scale})`;
    orb.style.boxShadow = `0 0 ${glow}px rgba(0, 150, 255, 0.8)`;
}

// ── Settings ──────────────────────────────────────────────────────────────────
function getSettings() {
    return {
        moveAmount:      parseFloat(document.getElementById('move-amount').value),
        slopeThreshold:  parseFloat(document.getElementById('slope-threshold').value),
        neutralZone:     parseFloat(document.getElementById('neutral-zone').value),
    };
}

function saveSettings(settings) {
    const settingsPath = require('path').join(__dirname, '..', 'settings.json');
    fs.writeFileSync(settingsPath, JSON.stringify(settings, null, 4));
    console.log('[SETTINGS] Saved to', settingsPath);
}

// ── Navigation ────────────────────────────────────────────────────────────────
document.getElementById('voice-btn').addEventListener('click', () => {
    require('electron').ipcRenderer.send('load-page', 'voice.html');
});