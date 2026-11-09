// Test aplikacji Electron (na Linuksie, pod Xvfb): mostek microlabNative, otwieranie .mlab, dodatek USB.
//   xvfb-run -a node test/smoke.mjs [plik.mlab] [katalog-na-zrzuty]
import { createRequire } from 'node:module';
import { readFileSync, existsSync, rmSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
const require = createRequire(import.meta.url);
const { _electron: electron } = require('playwright');
const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const mlab = process.argv[2] ? resolve(process.argv[2]) : null;
const shots = process.argv[3];
let failures = 0;
const check = (c, m) => { console.log(`${c ? 'ok  ' : 'FAIL'} ${m}`); if (!c) failures++; };

const env = { ...process.env }; delete env.NODE_OPTIONS;
const app = await electron.launch({ env, timeout: 60000, args: ['--no-sandbox', root, ...(mlab ? [mlab] : [])], executablePath: require(join(root, 'node_modules/electron')) });
try {
  const page = await app.firstWindow();
  page.on('pageerror', (e) => { console.log('PAGEERROR', e.message); failures++; });
  await page.waitForSelector('.topbar .mlu-top', { timeout: 30000 });
  const bridge = await page.evaluate(() => Object.keys(window.microlabNative || {}).sort().join(','));
  check(bridge.includes('saveProject') && bridge.includes('takeOpenedProject'), `mostek microlabNative: ${bridge}`);
  check(await page.evaluate(() => !!window.microlabUsbHost?.serialChooser), 'dodatek wie, że port wybiera aplikacja');
  await page.locator('.topbar .mlu-top').click();
  const note = await page.locator('.mlu-note').textContent();
  check(!/okno wyboru portu może nie działać|port chooser may not work/.test(note), `bez ostrzeżenia o Electron: „${note}”`);
  // requestPort bez płytek: handler w procesie głównym odpowiada od razu, nic nie wisi
  const res = await page.evaluate(() => Promise.race([
    navigator.serial.requestPort({ filters: [{ usbVendorId: 0x2e8a }] }).then(() => 'port', (e) => e.name),
    new Promise((r) => setTimeout(() => r('timeout'), 5000)),
  ]));
  check(res === 'NotFoundError', `„Połącz…” bez podłączonej płytki kończy się od razu, bez okienka (${res})`);
  const all = await page.evaluate(() => navigator.serial.requestPort({}).then((p) => JSON.stringify(p.getInfo()), (e) => e.name));
  console.log('     porty systemowe tego komputera:', all);
  check(await page.evaluate(() => !window.__microlabUsb.api.state.link), 'nieznany port systemowy nie jest łączony automatycznie');
  check(await page.evaluate(async () => Array.isArray(await navigator.serial.getPorts())), 'getPorts działa');
  if (mlab) {
    await page.waitForFunction(() => document.title.includes('.mlab') || document.title.length > 8, null, { timeout: 15000 }).catch(() => {});
    const parts = await page.locator('.statusbar, footer, .status-bar').first().textContent().catch(() => '');
    const title = await page.title();
    check(/test-pwm/.test(title), `plik .mlab z wiersza poleceń otwarty: tytuł „${title}”`);
  }
  // Zapisz jako… przez natywne okno (podmienione na stałą ścieżkę)
  const out = '/tmp/microlab-smoke.mlab';
  if (existsSync(out)) rmSync(out);
  await app.evaluate(({ dialog }, out) => { dialog.showSaveDialog = async () => ({ canceled: false, filePath: out }); }, out);
  await page.keyboard.press('Escape');
  if (shots) await page.screenshot({ path: join(shots, 'electron-przed-zapisem.png') });
  await page.locator('.mlu-panel .mlu-x').click();
  await page.mouse.click(700, 120);
  await page.keyboard.press('Control+Shift+S');
  for (let i = 0; i < 50 && !existsSync(out); i++) await new Promise((r) => setTimeout(r, 100));
  check(existsSync(out) && JSON.parse(readFileSync(out, 'utf8')).format === 'microlab.project', 'Zapisz jako… zapisuje .mlab natywnym oknem');
  // ESP32 na stole: ta wersja nie ma emulatora, ale nic nie może się wysypać
  await page.locator('.palette-item', { hasText: 'ESP32-DevKitC' }).first().click();
  await page.mouse.click(500, 250);
  await page.waitForTimeout(2500);
  check(await page.locator('.topbar').isVisible(), 'ESP32 na stole nie wysypuje aplikacji');
  if (shots) await page.screenshot({ path: join(shots, 'electron.png') });
} finally {
  await app.close();
}
console.log(failures ? `\n${failures} błędów` : '\nwszystko działa');
process.exit(failures ? 1 : 0);
