# Live Translator &middot; one language pair

Live speech subtitles and translation for OBS. Everything runs on your own PC: no cloud, no API, no account.

**This version: one language pair at a time.** You pick one spoken language and one subtitle language (Swedish &rarr;
English by default) and press **Load this pair**. Only what that pair needs is loaded, with the models that fit it
best, so it is the lightest and quickest of the four versions. Loading another pair takes a few seconds (the first
time for a pair, a download).

The four versions (`LiveTranslator_translation`, `LiveTranslator_conversation`, `LiveTranslator_both`,
`LiveTranslator_single_pair`) share one engine and differ only in what the Languages module offers. Run one at a
time: they all use port 5050.

## Start

Double-click **Start Live Translator.bat** (it finds Python 3.11 &ndash; 3.13, or offers to install it), or run
`Create shortcuts.bat` once to get a desktop / Start menu shortcut called "Live Translator (one pair)". The first start installs
what is missing and downloads the speech model; after that it starts in a few seconds and works offline.

- **Control page:** `http://127.0.0.1:5050/control` (opens by itself)
- **OBS overlay:** `http://127.0.0.1:5050/overlay`

If another program already uses port 5050, the translator picks the next free port by itself (5051, 5052 …),
remembers it, and shows the right links on the control page.

## Showing the subtitles on stream (Twitch, YouTube, TikTok)

In OBS add a **Browser Source** with the URL `http://127.0.0.1:5050/overlay`.

- **Twitch / YouTube (landscape):** width 1920, height 1080.
- **TikTok (vertical):** width 1080, height 1920, and the link `http://127.0.0.1:5050/overlay?font_size=44&margin=520`.
  The overlay lays itself out for whatever size the source has; the two numbers in the link give this overlay bigger
  text and lift it above TikTok's own buttons, without changing your landscape overlay. Change them to taste
  (`max_lines`, `max_width`, `position` and `align` work the same way). If you stream to both shapes at once, add one
  Browser Source to each canvas or scene. Any number of overlays can be open at the same time. The control page lists
  both links under **OBS links & docks**.
- Tick **Shutdown source when not visible** so a hidden scene costs nothing.
- The subtitles are part of the picture OBS sends, so they appear on every platform you stream or restream to.

Position, size, colours, the number of lines and the font are set on the control page (modules *Subtitles* and
*Font & colours*) and apply to every overlay at once.

## Languages

Pick **Spoken** and **Subtitles in**, then press **Load this pair**. What gets loaded:

| Pair | Speech model | Translation |
|---|---|---|
| **Swedish &rarr; English** (the default) | `KBLab/kb-whisper-small`, a speech model trained for Swedish | the Nordic &rarr; English text model (OPUS-MT `tc-big-gmq-en`) |
| another language &rarr; English | `medium` (Whisper translates to English itself, in one step) | none |
| English &rarr; another language | `large-v3-turbo` | a small model made for just that pair (OPUS-MT) |
| another language &rarr; another language | `large-v3-turbo` (Swedish: KB-Whisper) | the general model (`m2m100-1.2b`) |
| same language (plain subtitles) | `large-v3-turbo` (Swedish: KB-Whisper) | none |

With the default pair nothing else is ever loaded: only the Swedish speech model and the Swedish &rarr; English text
model, about 1.0 GB of downloads the first time and 1.3 GB of video memory while it runs.

For English &rarr; Polish, Norwegian, Croatian, Serbian and Slovenian the small model only writes the live drafts
(it is an older language-family model), and the finished line comes from the general model. On a PC without an NVIDIA
card the speech model is `small` (`small.en` for English, KB-Whisper for Swedish).

Text is translated on this PC by a small model made for one pair (OPUS-MT), wherever one exists with English on one
side: it writes the live drafts and the finished line, and answers in under 0.1 s. Pairs without one (and the finished
lines of a few older language-family models) use the general model (`m2m100-1.2b` on a graphics card with 6 GB or
more), which takes about half a second a sentence.

A model is downloaded the first time a language needs it (a one-pair model is converted once, into the `models` folder
next to the program; that takes a minute or two). **Until it is ready the subtitles wait**, or show the words in the
language they were spoken in &mdash; the Microphone module says what is being prepared. Do the first start before a
stream, not during it.

## Swedish &rarr; English: how it is done, and how good it is

Whisper can translate speech to English by itself, and that is what this program used to do for Swedish (with the
`medium` model). Measured on 148 real Swedish recordings (26 minutes, two speakers, the FLEURS set, which comes with
a human English translation of every sentence), two specialised models in a row are clearly better and quicker:

| Swedish speech &rarr; English text | translation score (BLEU, higher is better) | one draft / one finished line (10 s sentences) | video memory |
|---|---|---|---|
| Whisper `medium` translating by itself (before) | 31.1 | 407 ms / 599 ms | 0.93 GB |
| KB-Whisper small + Nordic &rarr; English text model (now) | **41.7** | **285 ms / 404 ms** | 1.26 GB |

- **KB-Whisper** (National Library of Sweden, Apache 2.0) is Whisper trained further on Swedish speech. Its small
  model got 7.7 % of the Swedish words wrong on these recordings, where `large-v3-turbo` got 9.4 &ndash; 9.9 %, with
  about half the video memory.
- **OPUS-MT `tc-big-gmq-en`** (University of Helsinki, CC BY 4.0) only translates the Nordic languages to English. On
  the written Swedish sentences it scored 49.6, the big general model `m2m100-1.2b` 44.2 &mdash; and it answers in
  85 ms instead of 520 ms.
- Both run with 16-bit weights on the graphics card, which made each pass another 21 &ndash; 27 % quicker than 8-bit.
- KB-Whisper writes `<|nospeech|>` when nobody is talking and guesses "Tack!" for clicks and beeps; both are caught
  (nine kinds of noise, 18 passes: text on screen in 16 before, in none now).

Set `ENGLISH_BY = "whisper"` to go back to Whisper translating by itself, or `LANGUAGE_MODELS = {}` to write Swedish
down with `large-v3-turbo`. `"KBLab/kb-whisper-medium"` in `LANGUAGE_MODELS` gets a few more Swedish words right
(7.5 % wrong in the first test, where small had 8.3 %) but every pass takes twice as long.

## What makes it quick

Measured on a laptop with a Quadro RTX 3000 (6 GB), which is slower than an RTX 4050; the same speech, the same
35 % GPU limit, compared with the version this one was built from.

**Swedish &rarr; English, real Swedish speech** (eight sentences of 6 &ndash; 9 seconds from the FLEURS recordings,
80 seconds, played into the program as the microphone):

| | first words on screen | finished line after the last word | live updates | GPU time used |
|---|---|---|---|---|
| before | 2.45 s | 1.10 s | 43 | 25 % |
| now | **1.05 s** | **0.74 s** | **114** | **19 %** |

(Now = the average of three of the versions, which share this path; GPU time is what `nvidia-smi` showed for the
whole card. These speakers start slowly and the recordings begin with a breath, so "first words" is later here than
with the short sentences below. The version before garbled two of the eight lines (one of them also said "bought"
for built) and got details wrong in two more; now all eight come through, the weakest being a Japanese place name
it couldn't spell and one clumsy verb.)

**Other pairs** (computer voices, six short sentences of 3 &ndash; 5 seconds in 35 seconds):

| | first words on screen | finished line after the last word | live updates |
|---|---|---|---|
| English &rarr; Polish subtitles | 2.41 s &rarr; **0.46 s** | 1.76 s &rarr; **0.83 s** | 9 &rarr; **51** |
| English &rarr; English subtitles | 0.59 s &rarr; **0.46 s** | 0.98 s &rarr; **0.63 s** | 30 &rarr; **53** |
| Polish &rarr; English (Whisper translates by itself) | 0.74 s &rarr; **0.65 s** | 0.95 s &rarr; **0.86 s** | 24 &rarr; **43** |
| Conversation, Polish &harr; English | 2.39 s &rarr; **0.86 s** | 1.47 s &rarr; **1.00 s** | 9 &rarr; **32** |
| Conversation, Swedish &harr; English (real Swedish, 63 s) | **1.03 s** | **0.91 s** | **81** |
| No graphics card (CPU), English &rarr; English* | 3.84 s &rarr; **1.11 s** | 2.39 s &rarr; **1.27 s** | 3 &rarr; **17** |

(before &rarr; now; the whole card was 19 &ndash; 22 % busy in each of these. The first line after a start often takes
about 0.4 s longer to lock in than the rest. *Measured before the last changes, not repeated.)

Single steps: one draft pass of the speech model 315 ms &rarr; 107 ms (`large-v3-turbo`); one translated draft
sentence about 50 ms with a one-pair model (135 ms with `m2m100-418m`, 230 ms with `m2m100-1.2b`); the word filter
0.24 ms &rarr; 0.03 ms a line, with identical results on 27,845 test lines.

- **Short listening window.** Whisper always looks at 30 seconds of audio, most of it empty here. Drafts now look at
  10 seconds and finished lines at 15, which makes each pass 2 &ndash; 3x quicker and that much lighter on the GPU. A
  pass that comes out odd on the short window (a loop, far too many words, time marks past the end) is redone on the
  full 30 seconds at once. A finished line of more than 7 seconds of speech always gets the full window: on long
  real sentences that was measurably more accurate (9.4 % of the words wrong instead of 10.3 %).
- **Drafts keep the words they agreed on.** What two drafts in a row have in common is kept, so words that are
  already on screen stop jumping (44 % fewer changed words in the test) while the newest words can still change.
- **No guesses at the start of a Swedish sentence.** From a fraction of a second of speech the model often just
  guesses ("Thanks.", "Yeah."), and that flashed on screen before the real words. With the Swedish speech model a
  draft from the first second is now only shown when the model is sure of it.
- **One listening pass, shared.** The expensive half of the speech model runs once per stretch of audio; finding the
  language (conversation), the text and a retry all use the same result.
- **The careful pass starts early.** It runs 0.35 s into a pause instead of after it, so when the pause turns out to be
  the end of the sentence the line locks in straight away.
- **Translation on CTranslate2** (the engine the speech model uses) instead of PyTorch, sentence by sentence, with
  every sentence remembered: in a growing draft only the last, unfinished sentence is translated again.
- **PyTorch is no longer loaded** while it runs (only its GPU libraries are used): a quicker start and a few hundred MB
  less memory.

## Graphics card and memory

| Setup | Video memory used (measured) |
|---|---|
| **Swedish &rarr; English** (KB-Whisper small + the Nordic &rarr; English model) | 1.26 GB |
| another language &rarr; English (`medium`) | 0.93 GB |
| English subtitles from English speech (`large-v3-turbo`) | 1.0 GB |
| English &rarr; a language with its own one-pair model (turbo + that model; measured: Swedish) | 1.55 GB |
| a pair that also needs the general model (measured: English &rarr; Polish, turbo + both text models) | 2.4 GB |
| conversation Swedish &harr; English (turbo + two one-pair models) | 2.13 GB |

`TRANSLATION_MODEL = "m2m100-418m"` saves about 0.8 GB against `m2m100-1.2b`, for less exact lines.

- **RTX 4050 (6 GB):** everything above fits; Swedish &rarr; English leaves 4.7 GB for the game. `nvidia-smi` showed
  the whole card about 20 % busy on average while it translated non-stop speech (with the 35 % limit).
- **RTX 4070 (8 / 12 GB):** room to spare. You can raise `GPU_LIMIT` (e.g. 60) for more updates a second.
- **No NVIDIA card, or the card taken away by a game:** it runs on the CPU (Swedish: KB-Whisper small, finished lines
  with one candidate instead of three). That is a fallback, not a way to stream: with 8-second Swedish sentences the
  finished line came 2.7 s after the last word and the drafts only every few seconds.

If the GPU runs out of memory or keeps failing while you play, the translator moves itself to the CPU and keeps
going. Restart it to use the GPU again.

## Settings at the top of `translator_http.py`

| Setting | What it does |
|---|---|
| `GPU_LIMIT = 35` | Share of GPU time the translator may use. Lower = smoother game, fewer updates. |
| `"responsiveness"` | `snappy` (default), `balanced`, `light` (heavy games). |
| `"model_size"` | `auto`, or one speech model for everything (`small`, `medium`, `large-v3-turbo` …). |
| `TRANSLATION_MODEL` | `auto`, `m2m100-418m` (small), `m2m100-1.2b` (accurate), `nllb-600m` / `nllb-1.3b` (most accurate, but licensed for **non-commercial** use only). |
| `PAIR_MODELS` | `auto` (default: a model made for the pair writes everything), `drafts`, `all`, `off`. |
| `ENGLISH_BY` | `auto` (default: Swedish is written down and translated as text, other languages are translated by Whisper itself), `whisper`, `text`. |
| `TEXT_TO_ENGLISH`, `LANGUAGE_MODELS` | The spoken languages `auto` treats as text (`["sv"]`), and the speech models trained for one language (`{"sv": "KBLab/kb-whisper-small"}`). |
| `"draft_window"`, `"final_window"` | The short listening window in seconds (`0` = always the full 30). |
| `"first_draft_sure"`, `"short_line_sure"` | How sure the model must be before a first draft / a one- or two-word line is shown. |
| `"custom_words"` | Names to spell right, e.g. `["Valorant"]`. |
| `GPU_SLIDER`, `APP_WINDOW` | A "Max GPU use" slider on the control page / the control page as its own window. |
| `START_LISTENING`, `GAME_FIRST`, `LOG_TRANSCRIPT` | Start with the mic off / let the game have the CPU first / write finished lines to the log. |

Settings made on the control page are saved in `translator_settings.json` next to the program.

## Control page: move, pop out and dock the modules

The control page is made of modules: Microphone, Languages, Subtitles, Water waves, Live preview, Transcript,
Font & colours, Mix It Up and OBS links. Each one has a title bar: **⠿** drags it (or use the arrow keys),
**▾ / ▸** folds it, **↔** makes it wide, **↗** pops it out into its own window. **Reset layout** puts everything back.

Every module also has its own link (e.g. `http://127.0.0.1:5050/dock/status`), listed in **OBS links & docks**. In
OBS open **Docks → Custom Browser Docks**, paste the link, and the module becomes a panel inside OBS.

Looks: **Dark**, **Glass**, **Light**, **Neon**, **Sakura**, **Midnight**. The look and layout are saved, and every
open page follows straight away.

**Stop listening** closes the microphone until you press **Start listening**. **Turn off** closes the translator.

## Word filter

Hate words and other very bad words are replaced with `@#$%&!` before anything is shown, in every language.

1. **Word lists in the `blocked_words` folder:** about 2,500 words and phrases in 21 languages (credits in
   `blocked_words/README.md`). Add your own to `blocked_words/my_words.txt`; changes apply within seconds.
2. **A built-in list of slurs** (English and Swedish), hidden *before* translation.
3. **A check through English:** a line shown in another language is translated back to English on this PC and checked
   there. With `CENSOR_CHECK = "auto"` (the default) this is skipped when the speech itself was English, because the
   English words were already checked before translating; `"always"` checks every such line, `"off"` uses the lists
   only.

Ordinary swearing in `ALLOWED_WORDS` stays visible. `CENSOR_STYLE = "stars"` shows `*****`, `CENSOR = False` turns the
filter off. No word list is ever complete: add what is missing to `my_words.txt`.

## Mix It Up (channel point redeems)

The **Mix It Up / stream bot** module has three private links: start listening, stop listening, switch on / off. In
Mix It Up add a **Web Request** action (GET) with the link; for "translate for 10 minutes" use start, a 600 second
**Wait**, then stop. While stopped the mic is closed and nothing runs, but the models stay loaded, so it starts again
instantly. The links contain a secret key; **Make new links** replaces them.

## Privacy and safety

- **No trackers, webhooks or telemetry.** The pages load nothing from the internet and only talk to `127.0.0.1`.
- **Nothing outside your PC can connect**, and other websites open in your browser can't read the subtitles or change
  settings (a fresh secret key every start, requests from other sites are refused).
- **What you say isn't saved** unless you set `LOG_TRANSCRIPT = True`.
- **Internet is only used the first time**, for Python packages (PyPI / pytorch.org) and models (Hugging Face). The
  translation models are fetched at one fixed revision, so the files can't change later. After that everything loads
  from disk.
- Original model files in PyTorch format are only opened with PyTorch 2.6 or newer (CVE-2025-32434), and only once,
  in a separate program, to convert them.

## For developers

`translator_http.py` in each version folder is built from `source/translator_http.py` by `python make_versions.py`
(one folder up). Lines like `#@if conv` … `#@end` in the source mark the parts only some versions get. Edit the source,
run the script, and all four folders and their zip files are rebuilt.
