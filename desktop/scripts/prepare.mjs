// Przygotowuje app/MicroLab.html: oryginalny MicroLab.html + najnowszy dodatek „Płytka USB”.
//   MICROLAB_HTML=ścieżka/do/MicroLab.html node scripts/prepare.mjs
import { existsSync, mkdirSync } from 'node:fs';
import { execFileSync } from 'node:child_process';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const root = resolve(here, '..');
const candidates = [
  process.env.MICROLAB_HTML,
  join(root, '..', '..', 'MicroLab', 'MicroLab', 'MicroLab.html'), // układ repozytorium Squish
  join(root, 'MicroLab.html'),
].filter(Boolean);
const input = candidates.find((p) => existsSync(p));
if (!input) {
  console.error('Nie znalazłem MicroLab.html. Podaj go: MICROLAB_HTML=ścieżka node scripts/prepare.mjs');
  process.exit(1);
}
mkdirSync(join(root, 'app'), { recursive: true });
execFileSync(process.execPath, [join(root, '..', 'tools', 'build.mjs'), 'inject', input, join(root, 'app', 'MicroLab.html')], { stdio: 'inherit' });
