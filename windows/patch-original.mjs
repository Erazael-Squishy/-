#!/usr/bin/env node
// Dodaje „Płytka USB” do oryginalnej aplikacji MicroLab na Windows (wypakowanej z instalatora).
//
//   node windows/patch-original.mjs <folder-aplikacji> [wersja]
//
// <folder-aplikacji> to zawartość app-64.7z z instalatora (MicroLab.exe, resources/app/…).
// Zmiany (można uruchomić drugi raz – nic się nie zdubluje):
//   resources/app/dist/assets/microlab-usb.js   dodatek (CSP aplikacji pozwala tylko na skrypty z plików)
//   resources/app/dist/index.html               <script> z dodatkiem
//   resources/app/electron/main.cjs             porty szeregowe: zgoda dla strony MicroLab, wybór portu bez okienka przeglądarki
//   resources/app/electron/preload.cjs          window.microlabUsbHost (dodatek wie, że port wybiera aplikacja)
//   resources/app/package.json                  wersja
import { copyFileSync, existsSync, readFileSync, writeFileSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const repo = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const [dirArg, version] = process.argv.slice(2);
if (!dirArg) { console.error('użycie: node windows/patch-original.mjs <folder-aplikacji> [wersja]'); process.exit(1); }
const appDir = join(resolve(dirArg), 'resources', 'app');
const must = (p) => { if (!existsSync(p)) { console.error(`brak ${p}: to nie wygląda na wypakowany MicroLab`); process.exit(1); } return p; };
const MARK = 'MicroLab USB';

// 1. dodatek jako osobny plik
copyFileSync(join(repo, 'src', 'microlab-usb.js'), join(must(join(appDir, 'dist', 'assets')), 'microlab-usb.js'));

// 2. index.html
const indexPath = must(join(appDir, 'dist', 'index.html'));
let index = readFileSync(indexPath, 'utf8');
if (!index.includes('microlab-usb.js')) {
  index = index.replace('</head>', '    <script type="module" src="./assets/microlab-usb.js"></script>\n  </head>');
  writeFileSync(indexPath, index);
}

// 3. main.cjs
const mainPath = must(join(appDir, 'electron', 'main.cjs'));
let main = readFileSync(mainPath, 'utf8');
if (!main.includes(MARK)) {
  const block = `
// ── ${MARK}: prawdziwe płytki przez port szeregowy (Web Serial), jak w Thonny ──
// Strona MicroLab ma zgodę na porty z góry, więc wykrywa płytkę sama po podłączeniu; przycisk
// „Połącz…” nie pokazuje okienka przeglądarki: port wybiera aplikacja (przy kilku płytkach pyta).
/** Płytki, które MicroLab rozpoznaje po VID USB: na liście są pierwsze. */
const USB_KNOWN_VIDS = new Set([0x2e8a, 0x303a, 0x239a, 0x2886, 0x1209, 0xf055, 0x10c4, 0x1a86, 0x0403, 0x2341, 0x2a03]);
function usbVid(port) {
  const v = String(port.vendorId ?? '');
  return /[a-f]/i.test(v) ? parseInt(v, 16) : Number(v);
}
function ourOrigin(origin) {
  const devOrigin = process.env.MICROLAB_DEV_URL ? new URL(process.env.MICROLAB_DEV_URL).origin : null;
  const o = String(origin ?? '');
  return o.startsWith('app://microlab') || (devOrigin !== null && o.startsWith(devOrigin));
}
async function chooseSerialPort(portList, webContents) {
  if (!portList.length) return '';
  const known = portList.filter((p) => USB_KNOWN_VIDS.has(usbVid(p)));
  const list = known.length ? [...known, ...portList.filter((p) => !known.includes(p))] : portList;
  if (list.length === 1) return list[0].portId;
  const pl = String(app.getLocale()).toLowerCase().startsWith('pl');
  const label = (p) => {
    const name = p.displayName || p.portName || 'Port';
    return p.portName && !name.includes(p.portName) ? \`\${name} (\${p.portName})\` : name;
  };
  const { response } = await dialog.showMessageBox(BrowserWindow.fromWebContents(webContents) || mainWindow, {
    type: 'question',
    title: APP_NAME,
    message: pl ? 'Którą płytkę połączyć?' : 'Which board should MicroLab connect to?',
    buttons: [...list.map(label), pl ? 'Anuluj' : 'Cancel'],
    cancelId: list.length,
    noLink: true,
  });
  return response < list.length ? list[response].portId : '';
}
function handleSerialPorts() {
  const ses = session.defaultSession;
  // Bez tej obsługi Electron zgadza się na wszystko; zostaje tak, tylko porty są wyłącznie dla strony MicroLab.
  ses.setPermissionCheckHandler((_webContents, permission, origin) => (permission === 'serial' ? ourOrigin(origin) : true));
  ses.setDevicePermissionHandler((details) => details.deviceType === 'serial' && ourOrigin(details.origin));
  ses.on('select-serial-port', (event, portList, webContents, callback) => {
    event.preventDefault();
    chooseSerialPort(portList, webContents).then(callback, () => callback(''));
  });
}
// ── koniec ${MARK} ──

`;
  const anchor = '// One MicroLab at a time';
  if (!main.includes(anchor) || !main.includes('  handleProjectFiles();\n')) { console.error('main.cjs wygląda inaczej niż w 0.8.0: nie wiem, gdzie dopisać obsługę portów'); process.exit(1); }
  main = main.replace(anchor, block + anchor).replace('  handleProjectFiles();\n', '  handleProjectFiles();\n  handleSerialPorts();\n');
  writeFileSync(mainPath, main);
}

// 4. preload.cjs
const preloadPath = must(join(appDir, 'electron', 'preload.cjs'));
let preload = readFileSync(preloadPath, 'utf8');
if (!preload.includes('microlabUsbHost')) {
  preload += `\n// ${MARK}: port szeregowy wybiera aplikacja (main.cjs), nie okienko przeglądarki.\ncontextBridge.exposeInMainWorld('microlabUsbHost', { serialChooser: true });\n`;
  writeFileSync(preloadPath, preload);
}

// 5. wersja
const pkgPath = must(join(appDir, 'package.json'));
const pkg = JSON.parse(readFileSync(pkgPath, 'utf8'));
if (version) pkg.version = version;
writeFileSync(pkgPath, JSON.stringify(pkg, null, 2) + '\n');

console.log(`gotowe: ${pkg.productName} ${pkg.version} (edycja ${pkg.microlabEdition ?? 'a'}) z dodatkiem MicroLab USB`);
