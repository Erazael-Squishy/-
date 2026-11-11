// Listens for Twitch events and tells overlay.html how many balls belong in the bowl.
const { execFile } = require('child_process');
const fs = require('fs');
const http = require('http');

const PORT = 7373;
const EVENTSUB_URL = 'wss://eventsub.wss.twitch.tv/ws?keepalive_timeout_seconds=30';
const CHAT_URL = 'wss://irc-ws.chat.twitch.tv:443';
const SCOPES = 'moderator:read:followers channel:read:subscriptions bits:read chat:read';
const ONE_HOUR = 60 * 60 * 1000;

// Only these files are served, so data.json (your Twitch login) stays private.
const FILES = {
  '/': 'overlay.html',
  '/editor': 'editor.html',
  '/matter.min.js': 'matter.min.js',
  '/config.json': 'config.json',
  '/bowl.png': 'images/bowl.png',
  '/ball.png': 'images/ball.png',
  '/log': 'bowl.log',
};
const IMAGES = { '/image/bowl': 'images/bowl.png', '/image/ball': 'images/ball.png' };

const CONFIG_FILE = `${__dirname}/config.json`;
const DATA_FILE = `${__dirname}/data.json`;
const config = JSON.parse(fs.readFileSync(CONFIG_FILE));
const state = fs.existsSync(DATA_FILE)
  ? JSON.parse(fs.readFileSync(DATA_FILE))
  : { balls: 0, followers: [], token: null };

const overlays = new Set();
const seenMessages = new Set();
let user; // The connected Twitch account: { login, user_id }
let refreshing = null; // The login refresh in progress, if any

// Written to the side first, so a power cut can't leave a half-written file.
function writeJson(file, value) {
  fs.writeFileSync(`${file}.tmp`, JSON.stringify(value, null, 2));
  fs.renameSync(`${file}.tmp`, file);
}

function save() {
  writeJson(DATA_FILE, state);
}

function tellOverlays(message) {
  for (const overlay of overlays) overlay.write(message);
}

function setBalls(balls) {
  state.balls = balls;
  save();
  tellOverlays(`data: ${balls}\n\n`);
}

function addBalls(count, reason) {
  setBalls(state.balls + count);
  console.log(`+${count} ${reason} (total ${state.balls})`);
}

// --- Overlay and editor ---

// Saves settings or a picture from the editor page, then reloads every overlay.
function saveFromEditor(req, res, route) {
  if (req.headers['sec-fetch-site'] !== 'same-origin') return res.writeHead(403).end();

  const chunks = [];
  req.on('data', (chunk) => chunks.push(chunk));
  req.on('end', () => {
    const body = Buffer.concat(chunks);
    if (route === '/config') {
      Object.assign(config, JSON.parse(body));
      writeJson(CONFIG_FILE, config);
    } else if (IMAGES[route]) {
      fs.writeFileSync(`${__dirname}/${IMAGES[route]}`, body);
    } else {
      return res.writeHead(404).end();
    }
    tellOverlays('event: reload\ndata: 1\n\n');
    res.end('Saved.');
  });
}

http.createServer((req, res) => {
  const route = req.url.split('?')[0];

  // Stops other websites from adding balls or emptying the bowl.
  if (req.headers['sec-fetch-site'] === 'cross-site') return res.writeHead(403).end();

  if (req.method === 'POST') {
    saveFromEditor(req, res, route);
  } else if (route === '/events') {
    res.writeHead(200, { 'Content-Type': 'text/event-stream', 'Cache-Control': 'no-store' });
    res.write(`data: ${state.balls}\n\n`);
    overlays.add(res);
    req.on('close', () => overlays.delete(res));
  } else if (route === '/test') {
    addBalls(1, 'test');
    res.end('Added one ball.');
  } else if (route === '/reset') {
    setBalls(0);
    res.end('Bowl emptied.');
  } else if (route === '/quit') {
    res.end('Stopped.', () => process.exit(0));
  } else if (FILES[route]) {
    fs.readFile(`${__dirname}/${FILES[route]}`, (error, file) => {
      if (error) return res.writeHead(404).end();
      res.writeHead(200, { 'Cache-Control': 'no-store' }).end(file);
    });
  } else {
    res.writeHead(404).end();
  }
}).listen(PORT, '127.0.0.1', () => {
  console.log(`Overlay running at http://127.0.0.1:${PORT}`);
  // Only once the port is ours, so a second copy can't use up the saved login.
  startTwitch();
});

// --- Twitch login ---

async function oauth(endpoint, params) {
  const response = await fetch(`https://id.twitch.tv/oauth2/${endpoint}`, {
    method: 'POST',
    body: new URLSearchParams({ client_id: config.clientId, ...params }),
  });
  return response.json();
}

function saveToken(token) {
  state.token = token;
  save();
}

async function login() {
  const device = await oauth('device', { scopes: SCOPES });
  if (!device.device_code) throw new Error(device.message);
  console.log(`\nConnect your Twitch account: open ${device.verification_uri}`);
  console.log(`Code: ${device.user_code}\n`);
  execFile('rundll32', ['url.dll,FileProtocolHandler', device.verification_uri]);

  while (true) {
    await new Promise((done) => setTimeout(done, device.interval * 1000));
    const token = await oauth('token', {
      scopes: SCOPES,
      device_code: device.device_code,
      grant_type: 'urn:ietf:params:oauth:grant-type:device_code',
    });
    if (token.access_token) return saveToken(token);
    if (token.message !== 'authorization_pending') throw new Error(token.message);
  }
}

async function renewToken() {
  const token = await oauth('token', {
    grant_type: 'refresh_token',
    refresh_token: state.token.refresh_token,
  });
  if (token.access_token) saveToken(token);
  // A Twitch outage shouldn't pop open a login page in the middle of a stream.
  else if (token.status >= 500) throw new Error(token.message);
  else await login();
}

// A refresh token works once, so overlapping calls have to share one request.
function refreshLogin() {
  refreshing ??= renewToken().finally(() => {
    refreshing = null;
  });
  return refreshing;
}

// --- Twitch connections ---

// Reconnects once if the socket closes or stays silent too long.
// Returns a function to call whenever the socket receives a message.
function watchSocket(ws, silenceLimit, reconnect) {
  let timer;
  const fail = () => {
    clearTimeout(timer);
    if (ws.retired) return;
    ws.retired = true;
    ws.close();
    setTimeout(reconnect, 5000);
  };
  const heard = () => {
    clearTimeout(timer);
    timer = setTimeout(fail, silenceLimit);
  };
  ws.onclose = fail;
  heard();
  return heard;
}

async function subscribe(sessionId) {
  await refreshLogin(); // The login may have run out while the PC was asleep.
  const channel = { broadcaster_user_id: user.user_id };
  const subscriptions = [
    ['channel.follow', '2', { ...channel, moderator_user_id: user.user_id }],
    ['channel.subscribe', '1', channel], // New subs and each gifted sub
    ['channel.subscription.message', '1', channel], // Resubs shared in chat
    ['channel.bits.use', '1', channel], // Cheers, Power-ups and combos
  ];

  for (const [type, version, condition] of subscriptions) {
    const response = await fetch('https://api.twitch.tv/helix/eventsub/subscriptions', {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${state.token.access_token}`,
        'Client-Id': config.clientId,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        type,
        version,
        condition,
        transport: { method: 'websocket', session_id: sessionId },
      }),
    });
    if (response.ok) console.log(`Listening for ${type}`);
    else console.log(`Could not listen for ${type}: ${await response.text()}`);
  }
}

function handleEvent(type, event) {
  if (type === 'channel.follow') {
    // Someone who unfollows and follows again only counts once.
    if (state.followers.includes(event.user_id)) return;
    state.followers.push(event.user_id);
    addBalls(1, `new follower: ${event.user_name}`);
  } else if (type === 'channel.bits.use') {
    const count = Math.max(1, Math.floor(event.bits / config.bitsPerBall));
    addBalls(count, `${event.bits} bits from ${event.user_name}`);
  } else {
    addBalls(1, `sub: ${event.user_name}`);
  }
}

// `previous` is set when Twitch moves us to a new server: the old socket stays
// open until the new one is ready, and the subscriptions move across by themselves.
function connectEventSub(url = EVENTSUB_URL, previous) {
  const ws = new WebSocket(url);
  const heard = watchSocket(ws, 40_000, connectEventSub);

  ws.onmessage = ({ data }) => {
    heard();
    const { metadata, payload } = JSON.parse(data);
    const type = metadata.message_type;

    if (type === 'session_welcome' && previous) {
      previous.retired = true;
      previous.close();
    } else if (type === 'session_welcome') {
      subscribe(payload.session.id).catch((error) => console.log(error.message));
    } else if (type === 'session_reconnect') {
      connectEventSub(payload.session.reconnect_url, ws);
    } else if (type === 'revocation') {
      console.log(`Twitch stopped ${payload.subscription.type}: ${payload.subscription.status}`);
    } else if (type === 'notification' && !seenMessages.has(metadata.message_id)) {
      seenMessages.add(metadata.message_id);
      handleEvent(metadata.subscription_type, payload.event);
    }
  };
}

// EventSub has no first-time chatter event, so this comes from Twitch chat instead.
function connectChat() {
  const ws = new WebSocket(CHAT_URL);
  const heard = watchSocket(ws, 7 * 60_000, connectChat);

  ws.onopen = () => {
    ws.send('CAP REQ :twitch.tv/tags twitch.tv/commands');
    ws.send(`PASS oauth:${state.token.access_token}`);
    ws.send(`NICK ${user.login}`);
    ws.send(`JOIN #${user.login}`);
  };

  ws.onmessage = ({ data }) => {
    heard();
    for (const line of data.split('\r\n')) {
      const [tags, , command] = line.split(' ');
      if (line.startsWith('PING')) {
        ws.send(line.replace('PING', 'PONG'));
      } else if (command === 'PRIVMSG' && tags.includes(';first-msg=1;')) {
        // Only the tags are checked, so typing "first-msg=1" in chat does nothing.
        addBalls(1, `first-time chatter: ${tags.match(/display-name=([^;]*)/)[1]}`);
      } else if (command === 'ROOMSTATE') {
        console.log('Listening for first-time chatters');
      } else if (line.startsWith(':tmi.twitch.tv NOTICE')) {
        console.log(line);
      }
    }
  };
}

async function connectTwitch() {
  if (!config.clientId) {
    console.log('No clientId in config.json, so Twitch is not connected. See README.md.');
    return;
  }

  if (state.token) await refreshLogin();
  else await login();

  const response = await fetch('https://id.twitch.tv/oauth2/validate', {
    headers: { Authorization: `OAuth ${state.token.access_token}` },
  });
  if (!response.ok) throw new Error('Twitch rejected the login');
  user = await response.json();
  console.log(`Connected to Twitch as ${user.login}`);

  connectEventSub();
  connectChat();
  // Login tokens last 4 hours, so this keeps a valid one ready for reconnects.
  setInterval(() => refreshLogin().catch((error) => console.log(error.message)), ONE_HOUR);
}

// Keeps trying, because the internet may not be up yet when Windows starts.
function startTwitch() {
  connectTwitch().catch((error) => {
    console.log(`Could not connect to Twitch: ${error.message}`);
    setTimeout(startTwitch, 60_000);
  });
}
