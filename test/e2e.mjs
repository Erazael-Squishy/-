#!/usr/bin/env node
// Test całości w Chromium: MicroLab.html z dodatkiem + udawana płytka MicroPython.
//   node test/e2e.mjs <MicroLab-z-dodatkiem.html> [katalog-na-zrzuty]
import { createRequire } from 'node:module';
import { readFileSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const require = createRequire(import.meta.url);
const { chromium } = require('playwright');
const here = dirname(fileURLToPath(import.meta.url));
const mock = readFileSync(join(here, 'mock-serial.js'), 'utf8');
const html = resolve(process.argv[2]);
const shots = process.argv[3];

let failures = 0;
const check = (cond, msg) => { console.log(`${cond ? 'ok  ' : 'FAIL'} ${msg}`); if (!cond) failures++; };

async function page(browser, cfg = {}, lang = 'pl') {
  const ctx = await browser.newContext({ viewport: { width: 1500, height: 950 } });
  const p = await ctx.newPage();
  p.on('pageerror', (e) => { console.log('PAGEERROR', e.message); failures++; });
  await p.addInitScript(({ cfg, lang }) => { window.__MOCK_CFG__ = cfg; try { localStorage.setItem('microlab.language', lang); } catch {} }, { cfg, lang });
  await p.addInitScript(mock);
  await p.goto('file://' + html);
  await p.waitForSelector('.topbar .mlu-top', { timeout: 15000 });
  return p;
}
const placePico = async (p) => {
  await p.locator('.palette-item', { hasText: 'Raspberry Pi Pico / Pico H' }).first().click();
  await p.mouse.click(700, 380);
  await p.waitForSelector('section.code-panel .mlu-group', { timeout: 10000 });
};
const statusText = (p) => p.locator('.mlu-panel .mlu-status').textContent();
const termText = (p) => p.locator('.mlu-term-out').textContent();
const fs = (p) => p.evaluate(() => Object.fromEntries([...window.__mockSerial.port.device.fs].map(([k, v]) => [k, new TextDecoder().decode(v)])));
const waitIdle = (p) => p.waitForFunction(() => !window.__microlabUsb.api.state.busy, null, { timeout: 15000 });

const browser = await chromium.launch();
try {
  // 1. pierwsze uruchomienie: brak zgody na port, łączenie przyciskiem
  {
    const p = await page(browser);
    check(await p.locator('.topbar .mlu-top').textContent() === 'Płytka USB', 'przycisk „Płytka USB” na górnym pasku (po polsku)');
    await placePico(p);
    check(await p.locator('.mlu-group .mlu-g-run').isHidden(), 'bez płytki nie ma przycisku „Na płytce”');
    await p.locator('.mlu-group .mlu-g-usb').click();
    check(await p.locator('.mlu-panel').isVisible(), 'panel się otwiera');
    check((await p.locator('.mlu-note').textContent()).includes('Połącz'), 'podpowiedź o pierwszym połączeniu');
    await p.locator('.mlu-panel button', { hasText: 'Połącz…' }).click();
    await p.waitForFunction(() => window.__microlabUsb.api.state.info, null, { timeout: 10000 });
    await waitIdle(p);
    const req = await p.evaluate(() => window.__mockSerial.requests[0]);
    check(req.filters.some((f) => f.usbVendorId === 0x2e8a) && req.filters.some((f) => f.usbVendorId === 0x10c4), 'okno wyboru filtruje Pico i ESP32');
    const st = await statusText(p);
    check(st.includes('Raspberry Pi Pico') && st.includes('1.29.0'), `status po połączeniu: ${st}`);
    check(await p.locator('.mlu-group .mlu-g-run').isVisible(), 'po połączeniu przycisk „Na płytce” w pasku kodu');
    const sig = await p.evaluate(() => window.__mockSerial.port.signals);
    check(sig.dataTerminalReady && sig.requestToSend, 'DTR i RTS ustawione razem');
    if (shots) await p.screenshot({ path: join(shots, '1-polaczono.png') });

    // 2. uruchomienie kodu z edytora (domyślny program Pico: while True)
    await p.locator('.mlu-group .mlu-g-run').click();
    await p.waitForFunction(() => window.__microlabUsb.api.state.running, null, { timeout: 10000 });
    await p.waitForFunction(() => document.querySelector('.mlu-term-out').textContent.includes('tick 3'), null, { timeout: 10000 });
    check(true, 'program działa na płytce, wyjście płynie do konsoli');
    check(await p.locator('.mlu-group .mlu-g-stop').isVisible(), 'przycisk Stop w trakcie działania');
    if (shots) await p.screenshot({ path: join(shots, '2-dziala.png') });
    await p.locator('.mlu-group .mlu-g-stop').click();
    await waitIdle(p);
    const t2 = await termText(p);
    check(t2.includes('KeyboardInterrupt') && t2.includes('Program przerwany'), 'Stop przerywa program');

    // 3. biblioteka w projekcie + wgrywanie
    await p.evaluate(() => {
      const v = window.__microlabUsb.api.app.editorView();
      v.dispatch({ changes: { from: 0, to: v.state.doc.length, insert: 'print("czesc z main")\n' } });
    });
    await p.waitForTimeout(700); // autozapis
    await p.locator('.mlu-group .mlu-g-upload').click();
    await p.waitForFunction(() => window.__mockSerial.port.device.log.includes('soft-reboot'), null, { timeout: 15000 });
    await p.waitForFunction(() => document.querySelector('.mlu-term-out').textContent.includes('czesc z main'), null, { timeout: 5000 });
    const files = await fs(p);
    check(files['main.py'] === 'print("czesc z main")\n', 'main.py zapisany na płytce z treścią z edytora');
    check((await termText(p)).includes('Zapisano na płytce: main.py'), 'komunikat o wgraniu');

    // 4. pliki na płytce
    await p.locator('.mlu-tabs button', { hasText: 'Pliki na płytce' }).click();
    await p.waitForSelector('.mlu-files td.n:text("main.py")');
    check(await p.locator('.mlu-files td.n', { hasText: 'boot.py' }).count() === 1, 'lista plików pokazuje boot.py i main.py');
    if (shots) await p.screenshot({ path: join(shots, '3-pliki.png') });
    const [dl] = await Promise.all([p.waitForEvent('download'), p.locator('.mlu-files tr', { hasText: 'boot.py' }).locator('button', { hasText: 'Pobierz' }).click()]);
    check(readFileSync(await dl.path(), 'utf8') === '# boot.py\n', 'pobieranie pliku z płytki');
    p.once('dialog', (d) => d.accept());
    await p.locator('.mlu-files tr', { hasText: 'boot.py' }).locator('button', { hasText: 'Usuń' }).click();
    await p.waitForFunction(() => !window.__mockSerial.port.device.fs.has('boot.py'), null, { timeout: 5000 });
    await waitIdle(p);
    check(await p.locator('.mlu-files td.n', { hasText: 'boot.py' }).count() === 0, 'usuwanie pliku z płytki');

    // 5. odłączenie i ponowne podłączenie: wykrywa samo
    await p.locator('.mlu-tabs button', { hasText: 'Konsola' }).click();
    await p.evaluate(() => window.__mockSerial.unplug());
    await p.waitForFunction(() => !window.__microlabUsb.api.state.link, null, { timeout: 5000 });
    check((await statusText(p)) === 'Brak płytki', 'po odłączeniu: „Brak płytki”');
    check(await p.locator('.mlu-group .mlu-g-run').isHidden(), 'po odłączeniu znika „Na płytce”');
    await p.evaluate(() => window.__mockSerial.plug());
    await p.waitForFunction(() => window.__microlabUsb.api.state.info && !window.__microlabUsb.api.state.busy, null, { timeout: 10000 });
    check(true, 'po ponownym podłączeniu łączy się sama');
    check(await p.locator('.mlu-toast', { hasText: 'Wykryto' }).count() >= 1, 'powiadomienie „Wykryto: …”');
    if (shots) await p.screenshot({ path: join(shots, '4-wykryto.png') });

    // 6. konsola REPL: wpisywanie
    await p.locator('.mlu-term').click();
    await p.keyboard.type('1+1');
    await p.keyboard.press('Enter');
    await p.waitForFunction(() => window.__mockSerial.port.device.log.includes('line:1+1'), null, { timeout: 5000 });
    check(true, 'wpisywanie w konsoli trafia do REPL płytki');
    const parts = await p.evaluate(() => document.querySelectorAll('.bench-part, [data-part-id]').length);
    check(parts <= 1, 'litery wpisane w konsoli nie wstawiają części na stół');

    // 7. zakładka MicroPython (BOOTSEL)
    await p.locator('.mlu-tabs button', { hasText: 'MicroPython' }).click();
    check(await p.locator('.mlu-fw select option').count() === 4, 'cztery wersje MicroPythona dla Pico');
    const [fw] = await Promise.all([p.waitForEvent('download'), p.locator('.mlu-fw button', { hasText: 'Pobierz plik .uf2' }).click()]);
    const uf2 = readFileSync(await fw.path());
    check(uf2.slice(0, 4).toString() === 'UF2\n' && fw.suggestedFilename() === 'mp-1.29.0-pico.uf2', `pobrany plik ${fw.suggestedFilename()} to UF2 (${uf2.length} B)`);
    if (shots) await p.screenshot({ path: join(shots, '5-micropython.png') });
    await p.context().close();
  }

  // 8. zgoda już jest: łączy się samo przy starcie; stara płytka bez raw-paste
  {
    const p = await page(browser, { granted: true, rawPaste: false, info: { usbVendorId: 0x10c4, usbProductId: 0xea60 } }, 'en');
    await p.waitForFunction(() => window.__microlabUsb.api.state.info && !window.__microlabUsb.api.state.busy, null, { timeout: 10000 });
    check((await statusText(p)).startsWith('ESP32 (CP210x)'), 'samodzielne połączenie przy starcie (ESP32 przez CP210x), po angielsku');
    await placePico(p);
    await p.evaluate(() => {
      const v = window.__microlabUsb.api.app.editorView();
      v.dispatch({ changes: { from: 0, to: v.state.doc.length, insert: 'x = "' + 'ż'.repeat(3000) + '"\n' } });
    });
    await p.waitForTimeout(700);
    await p.locator('.mlu-group .mlu-g-upload').click();
    await p.waitForFunction(() => window.__mockSerial.port.device.log.includes('soft-reboot'), null, { timeout: 20000 });
    const files = await fs(p);
    check(files['main.py'] === 'x = "' + 'ż'.repeat(3000) + '"\n', 'duży plik z polskimi znakami wgrany bez raw-paste');
    await p.context().close();
  }

  // 9. port zajęty przez inny program
  {
    const p = await page(browser, {}, 'pl');
    await p.evaluate(() => { window.__MOCK_BUSY__ = true; });
    await p.locator('.topbar .mlu-top').click();
    await p.locator('.mlu-panel button', { hasText: 'Połącz…' }).click();
    await p.waitForSelector('.mlu-toast:has-text("zajęty")', { timeout: 5000 });
    check(true, 'komunikat o porcie zajętym przez inny program');
    await p.context().close();
  }

  // 10. motyw jasny (MicroLab B / Retro) – panel bierze kolory z motywu
  {
    const p = await page(browser, { granted: true }, 'pl');
    await p.waitForFunction(() => window.__microlabUsb.api.state.info, null, { timeout: 10000 });
    await p.evaluate(() => { document.documentElement.dataset.theme = 'retro2'; });
    if (shots) await p.screenshot({ path: join(shots, '6-motyw-retro.png') });
    await p.context().close();
  }
} finally {
  await browser.close();
}
console.log(failures ? `\n${failures} błędów` : '\nwszystko działa');
process.exit(failures ? 1 : 0);
