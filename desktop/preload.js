// Mostek między MicroLab.html a procesem głównym (contextIsolation, sandbox).
'use strict';
const { contextBridge, ipcRenderer } = require('electron');

const compileMessage = {
  pl: 'Ta wersja MicroLab (z obsługą płytek USB) nie ma kompilatora Arduino. Szkic skompilujesz w MicroLab 0.8.0 na Windows albo w Arduino IDE; gotowy plik .hex możesz zaimportować przyciskiem Importuj.',
  en: 'This MicroLab build (with USB boards) has no Arduino compiler. Compile the sketch in MicroLab 0.8.0 for Windows or in Arduino IDE; you can import a ready .hex file with Import.',
};

contextBridge.exposeInMainWorld('microlabNative', {
  saveProject: (text, name, existingPath, labels) => ipcRenderer.invoke('save-project', text, name, existingPath, labels),
  openProject: (labels) => ipcRenderer.invoke('open-project', labels),
  saveExport: (data, name, ext, labels) => ipcRenderer.invoke('save-export', data, name, ext, labels),
  takeOpenedProject: () => ipcRenderer.invoke('take-opened-project'),
  onOpenProject: (fn) => { ipcRenderer.on('open-project', (_e, project) => fn(project)); },
  compileArduino: async () => ({
    ok: false,
    log: (String(document.documentElement.lang || navigator.language).toLowerCase().startsWith('pl') ? compileMessage.pl : compileMessage.en),
    diagnostics: [],
  }),
  esp32Dir: null,
});

// dodatek „Płytka USB”: port wybiera aplikacja, nie okienko przeglądarki
contextBridge.exposeInMainWorld('microlabUsbHost', { serialChooser: true, platform: process.platform });
