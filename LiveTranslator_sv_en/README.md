# Live Translator &middot; Swedish &rarr; English

Live speech subtitles and translation for OBS. Everything runs on your own PC: no cloud, no API, no account.

**This version: Swedish &rarr; English only.** Swedish speech, English subtitles; there is no language to pick.
The *Swedish &rarr; English* module on the control page chooses the size of the speech model: **Small**, **Medium**
or **Large**.

It is the `LiveTranslator_translation` version with the languages fixed to Swedish &rarr; English. All the versions
(`LiveTranslator_translation`, `LiveTranslator_conversation`, `LiveTranslator_both`, `LiveTranslator_single_pair`,
`LiveTranslator_sv_en`) share one engine. Run one at a time: they all use port 5050.

## Start

Double-click **Start Live Translator.bat** (it finds Python 3.11 &ndash; 3.13, or offers to install it), or run
`Create shortcuts.bat` once to get a desktop / Start menu shortcut called "Live Translator (Swedish to English)". The first start installs
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

## Swedish &rarr; English and the speech model

The Swedish words are written down by **KB-Whisper**, a speech model trained for Swedish, and the Nordic &rarr;
English text model (OPUS-MT `tc-big-gmq-en`) translates them. Nothing else is loaded.

Under **Speech model** you pick the size of KB-Whisper. The choice is remembered and switches straight away (a few
seconds; the first time, the model is downloaded, so try a new size before a stream, not during it).

| Button | Speech model | Download | Video memory (speech model) | Each pass |
|---|---|---|---|---|
| **Small** (the default) | `KBLab/kb-whisper-small` | 0.5 GB | about 0.5 GB | the quickest; 7.7 % of the Swedish words wrong in the test below |
| **Medium** | `KBLab/kb-whisper-medium` | 1.5 GB | about 1 GB (1.6 GB on a card with 8 GB or more) | about twice as long; 7.5 % wrong where Small had 8.3 % (first test) |
| **Large** | `KBLab/kb-whisper-large` | 3 GB | about 2 GB (3.5 GB on a card with 8 GB or more) | about twice as long again; the fewest wrong words in its makers' tests (not measured here) |

On a card with 8 GB or more the medium and large models run with 16-bit weights, which is quicker but takes more
memory. The text model comes on top (about 0.7 GB). Only Small was measured in this program; the memory for Medium
and Large is an estimate from the size of the models.

The model that is running is shown under the buttons. If a size doesn't fit on the graphics card (or can't be
downloaded), the translator keeps the model it had (at start: Small) and says why under the buttons. Without a
graphics card Medium and Large are slow, and the subtitles lag behind. If the GPU keeps failing and the translator
moves to the CPU, it uses Small there until the next start.

The first time, the models are downloaded (the text model is converted once, into the `models` folder next to the
program; that takes a minute or two). **Until they are ready the subtitles wait**, or show the Swedish words &mdash;
the Microphone module says what is being prepared. Do the first start before a stream, not during it.

Which model each button uses is set in `SPEECH_SIZES` at the top of `translator_http.py`. Setting `"model_size"` to
one model by hand switches the buttons off.

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

Set `ENGLISH_BY = "whisper"` to go back to Whisper translating by itself (the buttons then pick `small`, `medium`
and `large-v3`), or `"model_size": "large-v3-turbo"` to write Swedish down with `large-v3-turbo`.

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
whole card. These speakers start slowly and the recordings begin with a breath, so "first words" comes later than
with short, crisp sentences. The version before garbled two of the eight lines (one of them also said "bought"
for built) and got details wrong in two more; now all eight come through, the weakest being a Japanese place name
it couldn't spell and one clumsy verb.)

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
- **One listening pass, shared.** The expensive half of the speech model runs once per stretch of audio; the text and
  a retry both use the same result.
- **The careful pass starts early.** It runs 0.35 s into a pause instead of after it, so when the pause turns out to be
  the end of the sentence the line locks in straight away.
- **Translation on CTranslate2** (the engine the speech model uses) instead of PyTorch, sentence by sentence, with
  every sentence remembered: in a growing draft only the last, unfinished sentence is translated again.
- **PyTorch is no longer loaded** while it runs (only its GPU libraries are used): a quicker start and a few hundred MB
  less memory.

## Graphics card and memory

| Speech model + the Nordic &rarr; English text model | Video memory used |
|---|---|
| **Small** (KB-Whisper small) | 1.26 GB (measured) |
| **Medium** (KB-Whisper medium) | about 1.7 GB (2.3 GB on a card with 8 GB or more), estimated |
| **Large** (KB-Whisper large) | about 2.7 GB (4.2 GB on a card with 8 GB or more), estimated |

- **RTX 4050 (6 GB):** all three fit; Small leaves 4.7 GB for the game, Large about 3.3 GB. `nvidia-smi` showed
  the whole card about 20 % busy on average while it translated non-stop speech (with the 35 % limit).
- **RTX 4070 (8 / 12 GB):** room to spare. You can raise `GPU_LIMIT` (e.g. 60) for more updates a second.
- **No NVIDIA card, or the card taken away by a game:** it runs on the CPU (use Small there; finished lines with one
  candidate instead of three). That is a fallback, not a way to stream: with 8-second Swedish sentences the
  finished line came 2.7 s after the last word and the drafts only every few seconds.

If the GPU runs out of memory or keeps failing while you play, the translator moves itself to the CPU and keeps
going. Restart it to use the GPU again.

## Settings at the top of `translator_http.py`

| Setting | What it does |
|---|---|
| `GPU_LIMIT = 35` | Share of GPU time the translator may use. Lower = smoother game, fewer updates. |
| `"responsiveness"` | `snappy` (default), `balanced`, `light` (heavy games). |
| `"model_size"` | `auto` (the **Small / Medium / Large** buttons decide), or one speech model for everything (`KBLab/kb-whisper-small`, `large-v3-turbo` …; the buttons are switched off then). |
| `SPEECH_SIZES` | The models behind the Small / Medium / Large buttons: KB-Whisper for writing the Swedish words down (`"sv"`), and the models used when Whisper translates to English by itself (`"translate"`). |
| `ENGLISH_BY` | `auto` (default: the Swedish is written down and translated as text), `whisper` (Whisper translates by itself), `text`. |
| `PAIR_MODELS` | `auto` (default: the Nordic &rarr; English model writes everything), `drafts`, `all`, `off` (then the general `TRANSLATION_MODEL` translates). |
| `"draft_window"`, `"final_window"` | The short listening window in seconds (`0` = always the full 30). |
| `"first_draft_sure"`, `"short_line_sure"` | How sure the model must be before a first draft / a one- or two-word line is shown. |
| `"custom_words"` | Names to spell right, e.g. `["Valorant"]`. |
| `GPU_SLIDER`, `APP_WINDOW` | A "Max GPU use" slider on the control page / the control page as its own window. |
| `START_LISTENING`, `GAME_FIRST`, `LOG_TRANSCRIPT` | Start with the mic off / let the game have the CPU first / write finished lines to the log. |

Settings made on the control page are saved in `translator_settings.json` next to the program.

## Control page: move, pop out and dock the modules

The control page is made of modules: Microphone, Swedish &rarr; English, Subtitles, Water waves, Live preview, Transcript,
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

`translator_http.py` in the other four version folders is built from `source/translator_http.py` by
`python make_versions.py` (one folder up). This version is not built by that script: it was made by hand from the
`translation` version, with the languages fixed (`clean_languages`), the language dial taken off the control page and
the speech model buttons set to the three KB-Whisper sizes. A change to the engine has to be made here as well.
