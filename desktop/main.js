// MicroLab USB – aplikacja na Windows: MicroLab.html z dodatkiem „Płytka USB” w oknie Electron.
// Proces główny: okno, porty szeregowe bez okienka zgody, natywne okna Zapisz/Otwórz, pliki .mlab.
'use strict';
const { app, BrowserWindow, dialog, ipcMain, session, shell, Menu } = require('electron');
const fs = require('node:fs/promises');
const path = require('node:path');

const APP_TITLE = 'MicroLab';
const HTML = path.join(__dirname, 'app', 'MicroLab.html');

// Płytki, które dodatek rozpoznaje (VID USB); okno wyboru pokazuje je pierwsze.
const KNOWN_VIDS = new Set([0x2e8a, 0x303a, 0x239a, 0x2886, 0x1209, 0xf055, 0x10c4, 0x1a86, 0x0403, 0x2341, 0x2a03]);
const vidOf = (p) => {
  const v = String(p.vendorId ?? '');
  if (!v) return NaN;
  return /^[0-9a-f]{4}$/i.test(v) && /[a-f]/i.test(v) ? parseInt(v, 16) : Number(v);
};

let win = null;
let pendingFile = fileFromArgs(process.argv);

if (!app.requestSingleInstanceLock()) {
  app.quit();
} else {
  app.on('second-instance', (_e, argv) => {
    const file = fileFromArgs(argv);
    if (win) {
      if (win.isMinimized()) win.restore();
      win.focus();
      if (file) readProject(file).then((p) => p && win.webContents.send('open-project', p));
    }
  });
  app.whenReady().then(start);
  app.on('window-all-closed', () => app.quit());
}

function fileFromArgs(argv) {
  const args = argv.slice(app.isPackaged ? 1 : 2);
  return args.find((a) => /\.mlab$/i.test(a) && !a.startsWith('-')) || null;
}

async function readProject(file) {
  try {
    const text = await fs.readFile(file, 'utf8');
    return { name: path.basename(file), text, path: file };
  } catch (err) {
    // bez blokowania programu (showErrorBox zatrzymałby wszystko do kliknięcia OK)
    const opts = { type: 'error', title: APP_TITLE, message: path.basename(file), detail: err.message };
    (win ? dialog.showMessageBox(win, opts) : dialog.showMessageBox(opts)).catch(() => {});
    return null;
  }
}

function start() {
  Menu.setApplicationMenu(null);
  const ses = session.defaultSession;

  // Web Serial: zgoda na porty z góry (MicroLab sam wykrywa płytkę po podłączeniu, jak Thonny)…
  ses.setPermissionCheckHandler(() => true);
  ses.setDevicePermissionHandler((details) => details.deviceType === 'serial');
  // …a przycisk „Połącz…” wybiera port sam, a przy kilku płytkach pyta, którą.
  ses.on('select-serial-port', (event, portList, webContents, callback) => {
    event.preventDefault();
    choosePort(portList, webContents).then(callback, () => callback(''));
  });

  win = new BrowserWindow({
    width: 1440,
    height: 900,
    minWidth: 800,
    minHeight: 500,
    title: APP_TITLE,
    backgroundColor: '#0d1117',
    show: false,
    icon: path.join(__dirname, 'build', 'icon.png'),
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      sandbox: true,
      nodeIntegration: false,
      spellcheck: false,
    },
  });
  win.once('ready-to-show', () => { win.maximize(); win.show(); });
  win.webContents.setWindowOpenHandler(({ url }) => {
    if (/^https?:\/\//i.test(url)) shell.openExternal(url);
    return { action: 'deny' };
  });
  win.webContents.on('will-navigate', (e, url) => {
    if (!url.startsWith('file:')) { e.preventDefault(); if (/^https?:\/\//i.test(url)) shell.openExternal(url); }
  });
  // F11 pełny ekran, Ctrl+Shift+I narzędzia (bez menu nie ma ich inaczej); F12 zostaje dla MicroLab
  win.webContents.on('before-input-event', (e, input) => {
    if (input.type !== 'keyDown') return;
    if (input.key === 'F11') { win.setFullScreen(!win.isFullScreen()); e.preventDefault(); }
    if (input.control && input.shift && input.key.toLowerCase() === 'i') { win.webContents.toggleDevTools(); e.preventDefault(); }
    if (input.control && (input.key === '=' || input.key === '+')) { win.webContents.setZoomLevel(win.webContents.getZoomLevel() + 0.5); e.preventDefault(); }
    if (input.control && input.key === '-') { win.webContents.setZoomLevel(win.webContents.getZoomLevel() - 0.5); e.preventDefault(); }
    if (input.control && input.key === '0') { win.webContents.setZoomLevel(0); e.preventDefault(); }
  });
  win.loadFile(HTML);
}

async function choosePort(portList, webContents) {
  if (!portList.length) return '';
  const known = portList.filter((p) => KNOWN_VIDS.has(vidOf(p)));
  const list = known.length ? [...known, ...portList.filter((p) => !known.includes(p))] : portList;
  if (list.length === 1) return list[0].portId;
  const pl = String(app.getLocale()).startsWith('pl');
  const label = (p) => `${p.displayName || p.portName || 'Port'}${p.portName && p.displayName && !p.displayName.includes(p.portName) ? ` (${p.portName})` : ''}`;
  const parent = BrowserWindow.fromWebContents(webContents) || win;
  const { response } = await dialog.showMessageBox(parent, {
    type: 'question',
    title: APP_TITLE,
    message: pl ? 'Którą płytkę połączyć?' : 'Which board should MicroLab connect to?',
    buttons: [...list.map(label), pl ? 'Anuluj' : 'Cancel'],
    cancelId: list.length,
    noLink: true,
  });
  return response < list.length ? list[response].portId : '';
}

// ───────── mostek window.microlabNative (to samo, czego MicroLab oczekuje od wersji na Windows) ─────────
const filters = (labels, ext, name) => [
  { name: labels?.filter || name || ext.toUpperCase(), extensions: [ext] },
  { name: labels?.allFiles || 'All files', extensions: ['*'] },
];

ipcMain.handle('save-project', async (e, text, name, existingPath, labels) => {
  try {
    let file = existingPath;
    if (!file) {
      const r = await dialog.showSaveDialog(BrowserWindow.fromWebContents(e.sender), {
        title: labels?.title, defaultPath: name || 'projekt.mlab', filters: filters(labels, 'mlab', 'MicroLab'),
      });
      if (r.canceled || !r.filePath) return null;
      file = /\.mlab$/i.test(r.filePath) ? r.filePath : `${r.filePath}.mlab`;
    }
    await fs.writeFile(file, text, 'utf8');
    return { name: path.basename(file), path: file };
  } catch (err) {
    return { error: err.message };
  }
});

ipcMain.handle('open-project', async (e, labels) => {
  try {
    const r = await dialog.showOpenDialog(BrowserWindow.fromWebContents(e.sender), {
      title: labels?.title, properties: ['openFile'], filters: filters(labels, 'mlab', 'MicroLab'),
    });
    if (r.canceled || !r.filePaths[0]) return null;
    const file = r.filePaths[0];
    return { name: path.basename(file), text: await fs.readFile(file, 'utf8'), path: file };
  } catch (err) {
    return { error: err.message };
  }
});

ipcMain.handle('save-export', async (e, data, name, ext, labels) => {
  try {
    const r = await dialog.showSaveDialog(BrowserWindow.fromWebContents(e.sender), {
      title: labels?.title, defaultPath: name, filters: filters(labels, ext, ext),
    });
    if (r.canceled || !r.filePath) return null;
    await fs.writeFile(r.filePath, typeof data === 'string' ? data : Buffer.from(data));
    return { name: path.basename(r.filePath), path: r.filePath };
  } catch (err) {
    return { error: err.message };
  }
});

ipcMain.handle('take-opened-project', async () => {
  const file = pendingFile;
  pendingFile = null;
  return file ? readProject(file) : null;
});
