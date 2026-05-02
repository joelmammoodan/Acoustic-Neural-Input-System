const { app, BrowserWindow, ipcMain, screen } = require('electron');
const path = require('path');
const { spawn } = require('child_process');

let pyProcesses = [];
let mainWindow;
let panelMode = false;

// ── Python launcher ───────────────────────────────────────────────────────────
function startPython(script) {
    const proc = spawn('python', ['-u', script]);

    proc.stdout.on('data', (data) => {
        console.log(`[PY ${path.basename(script)}]`, data.toString().trim());
    });
    proc.stderr.on('data', (data) => {
        console.error(`[PY ERR ${path.basename(script)}]`, data.toString().trim());
    });
    proc.on('exit', (code) => {
        console.log(`[PY ${path.basename(script)}] exited with code ${code}`);
    });

    pyProcesses.push(proc);
    return proc;
}

function startAllPython() {
    const py = (script) => path.join(__dirname, '..', 'Python_files', script);
    startPython(py('EOG_control.py'));
    startPython(py('voice_pipeline.py'));
}

function killAllPython() {
    pyProcesses.forEach(p => {
        try { p.kill(); } catch (_) {}
    });
    pyProcesses = [];
}

// ── Restart Python (called from Save Settings button) ────────────────────────
ipcMain.on('restart-python', () => {
    console.log('[SYSTEM] Restarting Python processes...');
    killAllPython();
    setTimeout(startAllPython, 500);
});
ipcMain.on('load-page', (event, page) => {
    mainWindow.loadFile(path.join(__dirname, '..', 'public', page));
});
// ── Panel toggle ──────────────────────────────────────────────────────────────
ipcMain.handle('toggle-panel', () => {
    const { width, height } = screen.getPrimaryDisplay().workArea;

    if (!panelMode) {
        mainWindow.setBounds({ x: 0, y: 0, width: 400, height });
        mainWindow.setAlwaysOnTop(true);
    } else {
        mainWindow.setBounds({ x: 0, y: 0, width: 1000, height: 1000 });
        mainWindow.setAlwaysOnTop(false);
    }
    panelMode = !panelMode;
});

// ── Settings window ───────────────────────────────────────────────────────────
// Settings are inline in index.html — nothing to open. Handler kept to avoid crash.
ipcMain.handle('open-settings', () => {
    console.log('[SYSTEM] Settings are inline in the main window.');
});

// ── Main window ───────────────────────────────────────────────────────────────
function createWindow() {
    mainWindow = new BrowserWindow({
        width: 800,
        height: 600,
        frame: true,
        webPreferences: {
            nodeIntegration: true,
            contextIsolation: false,
        }
    });

    mainWindow.loadFile(path.join(__dirname, '..', 'public', 'index.html'));
    mainWindow.webContents.openDevTools(); // ← add this
}

// ── App lifecycle ─────────────────────────────────────────────────────────────
app.whenReady().then(() => {
    startAllPython();
    createWindow();

    app.on('activate', () => {
        if (BrowserWindow.getAllWindows().length === 0) createWindow();
    });
});

app.on('window-all-closed', () => {
    killAllPython();
    if (process.platform !== 'darwin') app.quit();
});