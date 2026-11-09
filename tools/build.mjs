#!/usr/bin/env node
// Dokleja dodatek MicroLab USB do zbudowanego MicroLab.html (albo MicroLab-B.html)
// i buduje stronę „Dodaj-USB-do-MicroLab.html”, która robi to samo w przeglądarce.
//
//   node tools/build.mjs inject <MicroLab.html> <wynik.html>
//   node tools/build.mjs patcher <wynik.html>
import { readFileSync, writeFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = join(dirname(fileURLToPath(import.meta.url)), '..');
const addon = readFileSync(join(root, 'src/microlab-usb.js'), 'utf8');
if (/<\/script/i.test(addon)) throw new Error('dodatek nie może zawierać </script');

const START = '<!-- microlab-usb:start -->';
const END = '<!-- microlab-usb:end -->';
const block = (code) => `${START}<script type="module" id="microlab-usb">\n${code}\n</script>${END}`;

export function inject(html, code = addon) {
  const s = html.indexOf(START);
  if (s >= 0) {
    const e = html.indexOf(END, s);
    if (e < 0) throw new Error('uszkodzony blok microlab-usb');
    return html.slice(0, s) + block(code) + html.slice(e + END.length);
  }
  const at = html.lastIndexOf('</body>');
  if (at < 0) throw new Error('to nie wygląda na MicroLab.html (brak </body>)');
  return html.slice(0, at) + block(code) + '\n  ' + html.slice(at);
}

const [cmd, a, b] = process.argv.slice(2);
if (cmd === 'inject') {
  const html = readFileSync(a, 'utf8');
  if (!html.includes('__MICROLAB_FILES__') && !html.includes('MicroLab')) throw new Error('to nie wygląda na MicroLab.html');
  writeFileSync(b, inject(html));
  console.log(`zapisano ${b}`);
} else if (cmd === 'patcher') {
  const tpl = readFileSync(join(root, 'tools/patcher-template.html'), 'utf8');
  const out = tpl
    .replace('/*ADDON*/', () => addon)
    .replace('/*START*/', () => JSON.stringify(START))
    .replace('/*END*/', () => JSON.stringify(END));
  writeFileSync(a, out);
  console.log(`zapisano ${a}`);
} else if (cmd) {
  console.error('użycie: node tools/build.mjs inject <MicroLab.html> <wynik.html> | patcher <wynik.html>');
  process.exit(1);
}
