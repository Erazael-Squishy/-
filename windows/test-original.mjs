#!/usr/bin/env node
// Test poprawionej aplikacji MicroLab (Windows) uruchomionej Electronem na Linuksie, pod Xvfb.
//   xvfb-run -a -s "-screen 0 1600x1000x24" node windows/test-original.mjs <folder-aplikacji> [katalog-na-zrzuty]
import { createRequire } from 'node:module';
import { readFileSync, existsSync, rmSync, statSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const repo = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const require = createRequire(join(repo, 'desktop', 'package.json'));
const { _electron: electron } = require('playwright');
const appDir = join(resolve(process.argv[2]), 'resources', 'app');
const shots = process.argv[3];
const mock = readFileSync(join(repo, 'test', 'mock-serial.js'), 'utf8');
let failures = 0;
const check = (c, m) => { console.log(`${c ? 'ok  ' : 'FAIL'} ${m}`); if (!c) failures++; };

const env = { ...process.env, MICROLAB_SMOKE: '' };
delete env.NODE_OPTIONS;
const app = await electron.launch({ env, timeout: 60000, args: ['--no-sandbox', appDir], executablePath: require('electron') });
try {
  const page = await app.firstWindow();
  page.on('pageerror', (e) => { console.log('PAGEERROR', e.message); failures++; });
  const cspErrors = [];
  page.on('console', (m) => { if (/Content Security Policy|Refused to/i.test(m.text())) cspErrors.push(m.text()); });
  await page.waitForSelector('.topbar .mlu-top', { timeout: 30000 });
  check(true, 'dodatek załadowany w oryginalnej aplikacji (przycisk na górnym pasku)');
  check(await page.evaluate(() => typeof window.microlabNative?.compileArduino === 'function' && !!window.microlabUsbHost?.serialChooser), 'oryginalny mostek (Arduino, ESP32) jest, a dodatek wie, że port wybiera aplikacja');

  // prawdziwy Web Serial w Electronie: zgoda i wybór portu przez main.cjs
  const res = await page.evaluate(() => Promise.race([
    navigator.serial.requestPort({ filters: [{ usbVendorId: 0x2e8a }] }).then(() => 'port', (e) => e.name),
    new Promise((r) => setTimeout(() => r('timeout'), 5000)),
  ]));
  check(res === 'NotFoundError', `„Połącz…” bez płytki kończy się od razu, bez okienka przeglądarki (${res})`);
  check(await page.evaluate(async () => Array.isArray(await navigator.serial.getPorts())), 'getPorts działa (zgoda dla strony MicroLab)');

  // MicroPython .uf2 z folderu firmware/ (aplikacja nie ma ich w HTML)
  const out = '/tmp/microlab-fw-test.uf2';
  if (existsSync(out)) rmSync(out);
  await app.evaluate(({ session }, out) => { session.defaultSession.once('will-download', (_e, item) => item.setSavePath(out)); }, out);
  await page.locator('.topbar .mlu-top').click();
  await page.locator('.mlu-tabs button', { hasText: /MicroPython/ }).click();
  check(await page.locator('.mlu-fw select option').count() === 4, 'zakładka MicroPython: cztery płytki');
  await page.locator('.mlu-fw button', { hasText: /\.uf2/ }).click();
  for (let i = 0; i < 50 && !(existsSync(out) && statSync(out).size > 500000); i++) await new Promise((r) => setTimeout(r, 100));
  check(existsSync(out) && readFileSync(out).subarray(0, 4).toString() === 'UF2\n', `plik .uf2 wczytany z firmware/ i zapisany (${existsSync(out) ? statSync(out).size : 0} B)`);

  // udawana płytka: połączenie, uruchomienie, Stop, wgranie
  await app.context().addInitScript({ content: mock });
  await page.reload();
  await page.waitForSelector('.topbar .mlu-top', { timeout: 30000 });
  await page.locator('.palette-item', { hasText: 'Raspberry Pi Pico / Pico H' }).first().click();
  await page.mouse.click(650, 300);
  await page.waitForSelector('section.code-panel .mlu-group', { timeout: 15000 });
  await page.locator('.mlu-group .mlu-g-usb').click();
  await page.locator('.mlu-panel button', { hasText: /Połącz|Connect/ }).first().click();
  await page.waitForFunction(() => window.__microlabUsb.api.state.info && !window.__microlabUsb.api.state.busy, null, { timeout: 15000 });
  check(true, 'połączenie z płytką (udawaną) w aplikacji');
  await page.locator('.mlu-group .mlu-g-run').click();
  await page.waitForFunction(() => document.querySelector('.mlu-term-out').textContent.includes('tick 2'), null, { timeout: 15000 });
  check(true, 'kod z edytora działa na płytce, wyjście w konsoli');
  if (shots) await page.screenshot({ path: join(shots, 'oryginal-0.8.1.png') });
  await page.locator('.mlu-group .mlu-g-stop').click();
  await page.waitForFunction(() => !window.__microlabUsb.api.state.busy, null, { timeout: 15000 });
  await page.locator('.mlu-group .mlu-g-upload').click();
  await page.waitForFunction(() => window.__mockSerial.port.device.log.includes('soft-reboot'), null, { timeout: 20000 });
  const main = await page.evaluate(() => new TextDecoder().decode(window.__mockSerial.port.device.fs.get('main.py') || new Uint8Array()));
  check(main.includes('led.toggle()'), 'main.py wgrany na płytkę');
  check(cspErrors.length === 0, `bez błędów CSP${cspErrors.length ? ': ' + cspErrors[0] : ''}`);
} finally {
  await app.close();
}
console.log(failures ? `\n${failures} błędów` : '\nwszystko działa');
process.exit(failures ? 1 : 0);
