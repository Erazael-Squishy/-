// Runs server.js with no window and restarts it if it crashes.
const { spawn } = require('child_process');
const fs = require('fs');

// Started by Windows: hand over to a hidden copy of this script, so the window can close.
if (process.argv[2] !== 'hidden') {
  spawn(process.execPath, [__filename, 'hidden'], {
    detached: true,
    stdio: 'ignore',
    windowsHide: true,
  }).unref();
  process.exit();
}

const log = fs.openSync(`${__dirname}/bowl.log`, 'w');

function run() {
  const server = spawn(process.execPath, ['server.js'], {
    cwd: __dirname,
    stdio: ['ignore', log, log],
    windowsHide: true,
  });
  // A clean exit means it was asked to stop.
  server.on('exit', (code) => {
    if (code !== 0) setTimeout(run, 5000);
  });
}

run();
