// Udawany navigator.serial z płytką MicroPython (friendly REPL, raw REPL, raw-paste, mały system plików).
// Wstrzykiwany przez Playwright (addInitScript) przed załadowaniem MicroLab.
(() => {
  const enc = new TextEncoder();
  const dec = new TextDecoder();
  const cfg = Object.assign({ rawPaste: true, window: 32, info: { usbVendorId: 0x2e8a, usbProductId: 0x0005 }, granted: false, plugged: true }, window.__MOCK_CFG__ || {});

  class Device {
    constructor(port) {
      this.port = port;
      this.mode = 'friendly';
      this.fs = new Map([['boot.py', enc.encode('# boot.py\n')]]);
      this.line = '';
      this.code = [];
      this.loop = null;
      this.log = [];
    }
    emit(s) { this.port._emit(typeof s === 'string' ? enc.encode(s) : s); }
    input(bytes) { for (const b of bytes) this.byte(b); }
    byte(b) {
      const ch = String.fromCharCode(b);
      if (this.loop) { // program działa
        if (b === 3) this.stopLoop();
        return;
      }
      switch (this.mode) {
        case 'friendly':
          if (b === 1) { this.mode = 'raw'; this.code = []; this.emit('\r\nraw REPL; CTRL-B to exit\r\n>'); }
          else if (b === 3) { this.line = ''; this.emit('\r\n>>> '); }
          else if (b === 4) { this.emit('MPY: soft reboot\r\n'); this.log.push('soft-reboot'); this.runMain(); }
          else if (b === 13) { this.emit('\r\n'); this.log.push('line:' + this.line); this.line = ''; this.emit('>>> '); }
          else if (b === 2) this.emit('\r\nMicroPython v1.29.0 on 2026-08-24; Raspberry Pi Pico with RP2040\r\nType "help()" for more information.\r\n>>> ');
          else if (b >= 32) { this.line += ch; this.emit(ch); }
          break;
        case 'raw':
          if (b === 2) { this.mode = 'friendly'; this.emit('\r\nMicroPython v1.29.0 on 2026-08-24; Raspberry Pi Pico with RP2040\r\nType "help()" for more information.\r\n>>> '); }
          else if (b === 1) { this.code = []; this.emit('\r\nraw REPL; CTRL-B to exit\r\n>'); }
          else if (b === 3) { this.code = []; }
          else if (b === 5) { this.mode = 'paste?'; }
          else if (b === 4) {
            if (!this.code.length) { this.emit('OK'); this.emit('\x04\x04>'); return; }
            this.emit('OK'); const code = dec.decode(new Uint8Array(this.code)); this.code = []; this.exec(code);
          } else this.code.push(b);
          break;
        case 'paste?':
          if (b === 0x41) this.mode = 'paste?A';
          else this.mode = 'raw';
          break;
        case 'paste?A':
          if (b === 1) {
            if (!cfg.rawPaste) { this.mode = 'raw'; this.emit('R\x00'); return; }
            this.mode = 'paste'; this.code = []; this.recv = 0;
            this.emit(new Uint8Array([0x52, 0x01, cfg.window & 0xff, cfg.window >> 8]));
          } else this.mode = 'raw';
          break;
        case 'paste':
          if (b === 4) { this.mode = 'raw'; this.emit('\x04'); const code = dec.decode(new Uint8Array(this.code)); this.code = []; this.exec(code); return; }
          this.code.push(b); this.recv++;
          if (this.recv % cfg.window === 0) this.emit('\x01');
          break;
      }
    }
    done(out = '', err = '') { this.emit(out.replace(/\n/g, '\r\n') + '\x04' + err.replace(/\n/g, '\r\n') + '\x04>'); }
    exec(code) {
      this.log.push('exec:' + code.slice(0, 40));
      setTimeout(() => this.execNow(code), 2);
    }
    execNow(code) {
      if (code.includes('_machine')) return this.done(JSON.stringify(['Raspberry Pi Pico with RP2040', '1.29.0', 'rp2']) + '\n');
      if (code.includes('ilistdir')) {
        const list = [...this.fs].map(([p, d]) => ['/' + p, d.length]);
        return this.done(JSON.stringify([list, [1441792, 1400000]]) + '\n');
      }
      let out = '', err = '';
      const open = /_f=open\("([^"]+)","wb"\)/.exec(code);
      if (open) { this.cur = open[1]; this.fs.set(this.cur, new Uint8Array(0)); }
      for (const m of code.matchAll(/_w\(_B\.a2b_base64\("([^"]*)"\)\)/g)) {
        const bin = atob(m[1]); const add = Uint8Array.from(bin, (c) => c.charCodeAt(0));
        const old = this.fs.get(this.cur); const n = new Uint8Array(old.length + add.length); n.set(old); n.set(add, old.length); this.fs.set(this.cur, n);
      }
      if (/_f\.close\(\)/.test(code)) this.log.push('closed:' + this.cur);
      const rm = /os\.remove\("([^"]+)"\)/.exec(code);
      if (rm) { const p = rm[1].replace(/^\//, ''); if (this.fs.has(p)) this.fs.delete(p); else err = 'Traceback (most recent call last):\n  File "<stdin>", line 2, in <module>\nOSError: [Errno 2] ENOENT\n'; }
      const rd = /with open\("([^"]+)","rb"\)/.exec(code);
      if (rd) { const d = this.fs.get(rd[1].replace(/^\//, '')) || new Uint8Array(0); for (let i = 0; i < d.length; i += 1536) out += btoa(String.fromCharCode(...d.subarray(i, i + 1536))) + '\n'; }
      if (open || rm || rd || /^import os|^try:|_f\.close|_w\(/.test(code.trim())) return this.done(out, err);
      return this.userCode(code, () => this.done(out, err));
    }
    userCode(code, finish) {
      for (const m of code.matchAll(/print\("([^"]*)"\)/g)) this.emit(m[1] + '\r\n');
      if (/raise /.test(code)) return this.done('', 'Traceback (most recent call last):\n  File "<stdin>", line 1, in <module>\nValueError: test\n');
      if (/while True/.test(code)) {
        let n = 0;
        this.finishLoop = finish;
        this.loop = setInterval(() => this.emit(`tick ${n++}\r\n`), 100);
        return;
      }
      finish();
    }
    stopLoop() {
      clearInterval(this.loop); this.loop = null;
      if (this.mode === 'friendly') { this.emit('Traceback (most recent call last):\r\n  File "main.py", line 9, in <module>\r\nKeyboardInterrupt: \r\nMicroPython v1.29.0\r\n>>> '); return; }
      this.done('', 'Traceback (most recent call last):\n  File "<stdin>", line 9, in <module>\nKeyboardInterrupt: \n');
    }
    runMain() {
      const main = this.fs.get('main.py');
      if (!main) { this.emit('MicroPython v1.29.0\r\n>>> '); return; }
      this.userCode(dec.decode(main), () => this.emit('MicroPython v1.29.0\r\n>>> '));
    }
  }

  class FakePort extends EventTarget {
    constructor(info) { super(); this.info = info; this.device = new Device(this); this.isOpen = false; }
    getInfo() { return this.info; }
    async open() {
      if (this.isOpen) throw new DOMException('The port is already open.', 'InvalidStateError');
      if (window.__MOCK_BUSY__) throw new DOMException('Failed to open serial port.', 'NetworkError');
      this.isOpen = true;
      this.readable = new ReadableStream({ start: (c) => { this.ctrl = c; } });
      this.writable = new WritableStream({ write: (chunk) => { setTimeout(() => this.device.input(chunk), 1); } });
    }
    async setSignals(s) { this.signals = s; }
    _emit(bytes) { if (this.isOpen && this.ctrl) try { this.ctrl.enqueue(new Uint8Array(bytes)); } catch { /* zamknięty */ } }
    async close() { this.isOpen = false; try { this.ctrl?.close(); } catch { /* ignore */ } this.readable = null; this.writable = null; }
    _unplug() { if (this.isOpen) { try { this.ctrl.error(new DOMException('The device has been lost.', 'NetworkError')); } catch { /* ignore */ } this.isOpen = false; this.readable = null; } }
  }

  class FakeSerial extends EventTarget {
    constructor() { super(); this.port = new FakePort(cfg.info); this.granted = cfg.granted; this.plugged = cfg.plugged; this.requests = []; }
    async getPorts() { return this.granted && this.plugged ? [this.port] : []; }
    async requestPort(opts) {
      this.requests.push(opts);
      if (!this.plugged) throw new DOMException('No port selected by the user.', 'NotFoundError');
      this.granted = true; return this.port;
    }
    unplug() { this.plugged = false; this.port._unplug(); const e = new Event('disconnect', { bubbles: true }); Object.defineProperty(e, 'target', { value: this.port }); this.dispatchEvent(e); }
    plug() { this.plugged = true; if (!this.granted) return; const e = new Event('connect', { bubbles: true }); Object.defineProperty(e, 'target', { value: this.port }); this.dispatchEvent(e); }
  }

  const serial = new FakeSerial();
  Object.defineProperty(Navigator.prototype, 'serial', { configurable: true, get: () => serial });
  window.__mockSerial = serial;
})();
