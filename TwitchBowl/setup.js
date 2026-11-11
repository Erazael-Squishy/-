// Run by install.bat: saves your Twitch Client ID and makes the bowl start with Windows.
const { execFile, spawnSync } = require('child_process');
const fs = require('fs');
const path = require('path');
const readline = require('readline/promises');

const CONFIG_FILE = path.join(__dirname, 'config.json');
const BACKGROUND_FILE = path.join(__dirname, 'background.js');
const STARTUP_FILE = path.join(
  process.env.APPDATA,
  'Microsoft', 'Windows', 'Start Menu', 'Programs', 'Startup', 'Twitch Bowl.bat',
);

async function askForClientId() {
  const config = JSON.parse(fs.readFileSync(CONFIG_FILE));
  if (config.clientId) return;

  console.log(`Twitch needs a free app registration, once. A page is opening in your browser.
Fill it in like this, click Create, then Manage, and copy the Client ID:

  Name:                anything unique
  OAuth Redirect URL:  http://localhost
  Category:            any
  Client Type:         Public
`);
  execFile('rundll32', ['url.dll,FileProtocolHandler', 'https://dev.twitch.tv/console/apps/create']);

  const terminal = readline.createInterface({ input: process.stdin, output: process.stdout });
  while (!config.clientId) config.clientId = (await terminal.question('Paste the Client ID: ')).trim();
  terminal.close();
  fs.writeFileSync(CONFIG_FILE, JSON.stringify(config, null, 2));
}

async function main() {
  await askForClientId();

  // Stops a copy that's already running, so running this again applies new settings.
  await fetch('http://127.0.0.1:7373/quit').catch(() => {});
  await new Promise((done) => setTimeout(done, 1000));

  // chcp lets the file hold folder names with accented letters.
  fs.writeFileSync(STARTUP_FILE, `@chcp 65001 >nul\r\n@"${process.execPath}" "${BACKGROUND_FILE}"\r\n`);
  spawnSync(process.execPath, [BACKGROUND_FILE]);

  console.log(`
Done. The bowl is running in the background and will start with Windows.
If this is your first time, approve the Twitch page that just opened.

Keep this folder where it is. The bowl runs from here.

Last step, once only: in OBS, add a Browser source
  URL:     http://127.0.0.1:7373
  Width:   800
  Height:  800

To change the bowl, the balls or the physics, open "Bowl Editor" in this folder.
`);
}

main();
