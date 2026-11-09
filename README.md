# MicroLab USB – prawdziwa płytka jak w Thonny

Dodatek do MicroLab 0.8.0 (wersja przeglądarkowa `MicroLab.html` i `MicroLab-B.html`):

- **Wykrywa podłączenie płytki** – Raspberry Pi Pico / Pico W / Pico 2, inne płytki z RP2040,
  ESP32 przez przejściówki CP210x, CH340, CH9102 i FTDI oraz ESP32-S2/S3/C3/C6 z własnym USB.
  Po podłączeniu łączy się sama i pokazuje „Wykryto: …”, a po odłączeniu „Odłączono płytkę …”.
- **▶ Na płytce** – uruchamia kod z edytora MicroLab na prawdziwej płytce bez zapisywania go
  (jak F5 w Thonny). Wyjście programu widać na żywo w konsoli, **■ Stop** przerywa program
  (Ctrl+C). Biblioteki z projektu (np. `ssd1306.py`), których brakuje na płytce, kopiuje się same.
- **⤒ Wgraj** – zapisuje wszystkie pliki projektu na płytce (`main.py` uruchamia się sam po każdym
  włączeniu) i ją restartuje.
- **Konsola REPL** – piszesz w niej jak w Thonny: Ctrl+C przerywa program, Ctrl+D robi miękki
  restart, działają strzałki i Tab.
- **Pliki na płytce** – lista plików z rozmiarami i wolnym miejscem, pobieranie i usuwanie.
- **MicroPython na Pico** – wgrywanie MicroPythona 1.29.0 (Pico, Pico W, Pico 2, Pico 2 W)
  na płytkę w trybie BOOTSEL. Pliki `.uf2` są już w MicroLab.html, więc działa to bez internetu.

Przyciski są w dwóch miejscach: **Płytka USB** na górnym pasku i obok Uruchom/Stop/Reset
nad edytorem kodu zaznaczonej płytki.

## Jak dodać to do swojego MicroLab

Najprościej: otwórz w Chrome lub Edge plik `dist/Dodaj-USB-do-MicroLab.html` z tego repozytorium,
wskaż swój `MicroLab.html` albo `MicroLab-B.html` i zastąp stary plik pobranym.
Strona działa bez internetu. Na już poprawionym pliku tylko aktualizuje dodatek.

Z wiersza poleceń (Node.js 18+):

```bash
node tools/build.mjs inject MicroLab.html MicroLab-z-USB.html
```

```bash
node tools/build.mjs patcher Dodaj-USB-do-MicroLab.html
```

## Pierwsze podłączenie

1. Otwórz MicroLab.html w **Google Chrome** albo **Microsoft Edge**. Firefox i Safari nie mają
   dostępu do portów szeregowych.
2. Podłącz płytkę i kliknij **Płytka USB → Połącz…**. Przeglądarka pokaże listę płytek: wybierz
   swoją. Za pierwszym razem przeglądarka zawsze pyta o zgodę i nie da się tego ominąć.
3. Potem MicroLab łączy się sam za każdym razem, gdy tę płytkę podłączysz.

Jeśli płytki nie ma na liście, użyj **Wszystkie porty…** albo sprawdź kabel. Część kabli
ma tylko zasilanie, bez przewodów danych. Starsze przejściówki CH340 na Windows potrzebują
sterownika WCH.

Port może mieć otwarty tylko jeden program. Jeśli Thonny, Arduino IDE albo druga karta
z MicroLab trzyma port, MicroLab o tym powie.

## Czego jeszcze nie ma

- **Android (APK)**: WebView Androida nie obsługuje Web Serial. Potrzebna jest wtyczka
  natywna (USB OTG) i ponowne zbudowanie aplikacji ze źródeł.
- **Windows (instalator)**: Electron pokazuje okno wyboru portu dopiero po dodaniu w procesie
  głównym obsługi zdarzenia `select-serial-port` i uprawnień `serial`, np.:

  ```js
  // main.js (Electron), po utworzeniu okna
  const ses = mainWindow.webContents.session;
  ses.on('select-serial-port', (event, portList, webContents, callback) => {
    event.preventDefault();
    callback(portList[0]?.portId ?? ''); // albo własne okno z listą portList
  });
  ses.setPermissionCheckHandler((wc, permission) => permission === 'serial' || null);
  ses.setDevicePermissionHandler((details) => details.deviceType === 'serial');
  ```

  Trzeba też dołączyć `src/microlab-usb.js` do kodu aplikacji, np. jako import w `main.tsx`.
- **Wgrywanie MicroPythona na ESP32**: z esptool albo z Thonny. Pliki `.bin` dla ESP32 są
  tylko w wersji na Windows.
- **Szkice Arduino na prawdziwym UNO**: wymagają kompilatora z wersji na Windows i avrdude.

## Jak to działa

`src/microlab-usb.js` to samodzielny skrypt doklejany na końcu `MicroLab.html`. Nie zmienia
kodu aplikacji:

- kod czyta z edytora (CodeMirror) i z autozapisu projektu (`microlab.autosave.v1`),
- przyciski wstawia do istniejącego interfejsu i pilnuje ich, gdy React przerysowuje panel,
- kolory bierze ze zmiennych CSS aktywnego motywu, więc pasuje do MicroLab i MicroLab B.

Z płytką rozmawia przez Web Serial, tym samym protokołem co Thonny i mpremote:

- Ctrl+C przerywa program, Ctrl+A włącza raw REPL,
- kod wysyła trybem raw-paste z kontrolą przepływu, a na starszych wersjach MicroPythona kawałkami,
- pliki zapisuje kawałkami w base64.

DTR i RTS ustawia razem, więc ESP32 z automatycznym resetem nie restartuje się
i nie przechodzi w tryb programowania.

Teksty są po polsku i po angielsku. Język wybiera się według języka MicroLab.

## Testy

```bash
node tools/build.mjs inject MicroLab.html /tmp/MicroLab-test.html
```

```bash
node test/e2e.mjs /tmp/MicroLab-test.html
```

Test uruchamia MicroLab w Chromium (Playwright) z udawaną płytką MicroPython (`test/mock-serial.js`:
REPL, raw REPL, raw-paste, system plików) i sprawdza:

- łączenie i samodzielne wykrywanie po podłączeniu,
- uruchamianie, Stop, wgrywanie i pliki na płytce,
- pobieranie `.uf2`,
- port zajęty przez inny program,
- starszą płytkę bez raw-paste i polskie znaki.
