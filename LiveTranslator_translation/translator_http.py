"""
translator_http.py  -  live subtitles and translation for OBS, web control page, all in one file
================================================================================================
Version: TRANSLATION  (speech in one language -> subtitles in another)

Run:   python translator_http.py      (or use the Live Translator shortcut)
  Control page:  http://127.0.0.1:5050/control   (opens by itself)
  OBS overlay:   http://127.0.0.1:5050/overlay   (Browser Source, 1920 x 1080; for a vertical TikTok canvas 1080 x 1920)

Speech is turned into subtitles while it's spoken: drafts first, with words fixed as more context
arrives, then a careful pass locks each line in after a pause.
The speech model is picked by itself, or with the Small / Medium / Large buttons on the control page.
The language dial picks the spoken language and the subtitle language. Swedish -> English is the default.

Everything runs on this PC. Internet is used only the first time: to install missing packages (from
PyPI / pytorch.org) and to download the speech model (and, for non-English subtitles, a translation
model). After that the models are loaded from disk without contacting anyone, and the pages use no
outside scripts, fonts or trackers: they only talk to this PC (127.0.0.1). Other devices, and other
websites open in your browser, can't connect. What you say is NOT written to disk unless you turn on
LOG_TRANSCRIPT below. Settings are saved in translator_settings.json next to this file.
"""
import codecs, glob, importlib, importlib.metadata, importlib.util, json, logging, math, os, queue, random, re, secrets, shutil, subprocess, sys, threading, time, traceback, zlib
import webbrowser
from collections import OrderedDict, deque

# ============================== SETTINGS ==================================
CONFIG = {
    "model_size": "auto",         # auto (the speech model is picked with the "Speech model" buttons on the control
                                  # page: Auto / Small / Medium / Large, see SPEECH_SIZES) / or always one model, and
                                  # the buttons are switched off: small / medium / large-v2 / large-v3-turbo /
                                  # distil-large-v3 ...
    "device": "auto",             # auto (NVIDIA GPU if there is one) / cpu (keeps the GPU free for games and streaming)
    "engine": "auto",             # auto (faster-whisper: ~4x lighter on the GPU, falls back to openai-whisper) /
                                  # faster-whisper / openai-whisper
    "responsiveness": "snappy",   # snappy / balanced / light (light = heavy games, slower subtitles)
    "custom_words": [],           # names to spell right, e.g. ["Stanislaw", "Valorant"]
}
TRANSLATION_MODEL = "auto"        # text translation, used for subtitles in languages other than English:
                                  #   auto        = m2m100-1.2b on an NVIDIA card with 6 GB or more, else m2m100-418m
                                  #   m2m100-418m = smallest and fastest (0.5 GB download), MIT licence
                                  #   m2m100-1.2b = clearly more accurate (1.3 GB download), MIT licence
                                  #   nllb-600m / nllb-1.3b = Meta's NLLB-200, the most accurate of these (0.6 / 1.4 GB),
                                  #                 but its licence (CC BY-NC 4.0) allows NON-COMMERCIAL use only
PAIR_MODELS = "auto"              # small, quick translation models made for one pair with English on one side
                                  # (OPUS-MT, got ready once on this PC: a 300 - 470 MB download becomes a 75 - 230 MB
                                  # model). Measured on 120 - 200 sentences a pair against the big TRANSLATION_MODEL
                                  # (m2m100-1.2b), BLEU, higher is better: Swedish -> English 49.6 / 44.2, English ->
                                  # Swedish 46.5 / 42.4, -> German 39.9 / 35.5, -> Spanish 28.6 / 24.7, -> French 53.1 /
                                  # 46.1 - and they answer in ~85 ms where the big model takes ~550 ms. Only the old
                                  # language-family model for Polish was a little behind (17.6 / 18.3).
                                  #   auto   = a model trained for the pair writes everything, drafts and finished
                                  #            lines, and the big model isn't loaded at all (about 1.3 GB less video
                                  #            memory); the old language-family models (English -> Polish, Croatian,
                                  #            Serbian, Slovenian, Norwegian) only write the drafts, and their
                                  #            finished lines come from the TRANSLATION_MODEL
                                  #   drafts = they only write the live drafts, every finished line comes from the
                                  #            TRANSLATION_MODEL
                                  #   all    = they write everything / off = never used
ENGLISH_BY = "auto"               # how speech in another language becomes ENGLISH subtitles:
                                  #   auto    = "text" for the languages in TEXT_TO_ENGLISH, "whisper" for all others
                                  #   whisper = the speech model writes the English itself (Whisper's own translation,
                                  #             with the "medium" model): one step, no translation model needed
                                  #   text    = the words are written down in the spoken language, then translated as
                                  #             text by a model made for that language -> English
TEXT_TO_ENGLISH = ["sv"]          # spoken languages where "text" was measured to be clearly better than "whisper".
                                  # Swedish, 148 real recordings (26 minutes, FLEURS): Whisper's own translation scored
                                  # BLEU 31, the Swedish speech model below + the Nordic -> English text model BLEU 41,
                                  # with each pass 1.3 - 4x quicker and less video memory
LANGUAGE_MODELS = {"sv": "KBLab/kb-whisper-small"}
                                  # speech models trained for ONE language, used when that's the only language spoken
                                  # and its words are written down (not for Whisper's own translation to English).
                                  # KB-Whisper (National Library of Sweden, Apache 2.0, 0.5 GB download): on the same
                                  # recordings it got 8.3 % of the Swedish words wrong where large-v3-turbo got 9.9 %,
                                  # with 0.4 GB of video memory instead of 1.0. {} = always the general models;
                                  # "KBLab/kb-whisper-medium" = 7.5 % wrong, but each pass takes twice as long
SPEECH_SIZES = {                  # the "Speech model" buttons on the control page. Auto (the default) picks by itself
                                  # (see auto_speech_model and LANGUAGE_MODELS); the other three always use one size:
                                  #   write     writes the words down in the spoken language (they're translated as
                                  #             text afterwards when the subtitles are in another language)
                                  #   translate Whisper turns the speech into English by itself (see ENGLISH_BY;
                                  #             turbo models can't do that, so Large uses the full large-v3 there)
                                  #   "sv" ...  a model made for just that language, used when it's the only
                                  #             language spoken and its words are written down (KB-Whisper for
                                  #             Swedish; for English the English-only models, a little more
                                  #             accurate at the same speed)
    "small":  {"write": "small",          "translate": "small",    "sv": "KBLab/kb-whisper-small",  "en": "small.en"},
    "medium": {"write": "medium",         "translate": "medium",   "sv": "KBLab/kb-whisper-medium", "en": "medium.en"},
    "large":  {"write": "large-v3-turbo", "translate": "large-v3", "sv": "KBLab/kb-whisper-large"},
}
GPU_LIMIT = 35                    # % of GPU time the translator may use (lower = smoother game, slower subtitles).
GPU_SLIDER = False                # True = a "Max GPU use" slider on the control page (its value is remembered)
HOST, PORT = "127.0.0.1", 5050   # keep 127.0.0.1: "0.0.0.0" would let other devices on your network connect
OPEN_BROWSER = True
APP_WINDOW = False                # True = the control page opens as its own app window (Edge / Chrome, no tabs or
                                  # address bar), and closing that window turns the translator off
LOG_TRANSCRIPT = False            # True = also write every finished subtitle line to translator_log.txt
START_LISTENING = True            # False = start with the mic off, e.g. when Mix It Up switches it on with a redeem
GAME_FIRST = False                # True = Windows gives the game and OBS the CPU first when they're all busy
                                  # (smoother game on a maxed-out CPU, but slower subtitles then)
CENSOR = True                     # hide racial slurs and similar hate words in the subtitles (normal swearing stays)
CENSOR_STYLE = "grawlix"          # grawlix = @#$%&! / stars = *****
CENSOR_CHECK = "auto"             # the extra check through English for subtitles in other languages:
                                  #   auto   = always, except when the speech itself was English (then the English
                                  #            words were already checked before translating, so it's skipped: faster)
                                  #   always = every line in another language / off = word lists only
BLOCKED_WORDS = []                # your own extra words to hide, e.g. ["badword", "prefix*"] (* = any ending)
                                  # (more: put word lists, one word per line, in the blocked_words folder)
ALLOWED_WORDS = ["fuck*", "motherfuck*", "shit*", "bullshit*", "damn*", "goddamn*", "hell", "heck", "crap*", "ass",
                 "asses", "asshole*", "bitch*", "bastard*", "piss*", "dick", "dicks", "wtf"]
                                  # normal swearing that stays visible even when a word list contains it
# ==========================================================================

VERSION = "translation"
HERE = os.path.dirname(os.path.abspath(__file__))

# ---------------------------------------------------------------- packages
os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")      # Hugging Face libraries: no usage statistics
os.environ.setdefault("DO_NOT_TRACK", "1")
os.environ.setdefault("TRANSFORMERS_NO_ADVISORY_WARNINGS", "1")
os.environ.setdefault("HF_HUB_DISABLE_IMPLICIT_TOKEN", "1")  # never send a saved Hugging Face login along
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
os.environ.setdefault("HF_HUB_DOWNLOAD_TIMEOUT", "60")       # slow internet: wait longer before giving up
os.environ.setdefault("HF_HUB_ETAG_TIMEOUT", "30")
TORCH_CUDA = "https://download.pytorch.org/whl/cu126"   # PyPI torch is CPU-only on Windows


LOG_FILE = os.path.join(HERE, "translator_log.txt")
try:                                     # a fresh log each start once it gets big (stays on this PC, never sent anywhere)
    if os.path.getsize(LOG_FILE) > 1_000_000:
        os.remove(LOG_FILE)
except OSError:
    pass


def log(msg, error=False):
    try:
        print(msg, file=sys.stderr if error else sys.stdout, flush=True)
    except Exception:                    # no console (e.g. started without one)
        pass
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(time.strftime("%Y-%m-%d %H:%M:%S ") + ("ERROR " if error else "") + str(msg) + "\n")
    except OSError:
        pass


def pip(*args):
    subprocess.check_call([sys.executable, "-m", "pip", "install", *args])


_GPU = []


def nvidia_gpu():
    """(is there an NVIDIA graphics card, its video memory in MB). Asked once."""
    if not _GPU:
        try:
            r = subprocess.run(["nvidia-smi", "--query-gpu=memory.total", "--format=csv,noheader,nounits"],
                               capture_output=True, text=True, timeout=10,
                               creationflags=0x08000000 if sys.platform == "win32" else 0)   # no console flash
            mb = [int(x) for x in r.stdout.split() if x.isdigit()]
            _GPU.append((r.returncode == 0 and bool(mb), max(mb, default=0)))
        except Exception:
            _GPU.append((False, 0))
    return _GPU[0]


def has_nvidia_gpu():
    return nvidia_gpu()[0]


def install_missing():
    """Installs what's missing. PyTorch is only fetched on a PC with an NVIDIA card (its CUDA build carries the GPU
    libraries the speech and translation engine use); without one, nothing here needs it."""
    try:
        torch_version = importlib.metadata.version("torch")
    except importlib.metadata.PackageNotFoundError:
        torch_version = None
    gpu = has_nvidia_gpu() and CONFIG.get("device") != "cpu"
    try:
        if gpu and torch_version is None and not cuda_folders():
            log("Installing PyTorch with CUDA (about 2.5 GB, one time)...")
            pip("torch", "--index-url", TORCH_CUDA)
        elif gpu and torch_version and "+cu" not in torch_version and not cuda_folders(nvidia_only=True):
            log(f"Replacing CPU-only PyTorch {torch_version} with the CUDA build (about 2.5 GB, one time)...")
            pip("--force-reinstall", "torch", "--index-url", TORCH_CUDA)
    except subprocess.CalledProcessError:
        sys.exit(f"Could not install PyTorch. Try:  python -m pip install torch --index-url {TORCH_CUDA}")
    importlib.invalidate_caches()
    need = {"numpy": "numpy", "pyaudio": "PyAudio", "flask": "Flask>=2.2", "sentencepiece": "sentencepiece"}
    if CONFIG.get("engine") == "openai-whisper":
        need["whisper"] = "openai-whisper"
        need["ctranslate2"] = "ctranslate2>=4.5,<5"      # still runs the text translation
    else:                                # faster-whisper; openai-whisper is installed later only if it's needed
        need["faster_whisper"] = "faster-whisper>=1.1,<2"
    missing = [p for m, p in need.items() if importlib.util.find_spec(m) is None]
    if missing:
        log(f"Installing {', '.join(missing)} ...")
        try:
            pip(*missing)
        except subprocess.CalledProcessError:
            sys.exit(f"Could not install. Try:  python -m pip install {' '.join(missing)}\n"
                     "(Use Python 3.11-3.13; PyAudio has no installer for newer versions yet.)")
        importlib.invalidate_caches()


def cuda_folders(nvidia_only=False):
    """Folders with NVIDIA's CUDA libraries (cuBLAS, cuDNN) that pip put on this PC: inside PyTorch's CUDA build, or
    the separate nvidia-* packages."""
    out = []
    try:
        spec = importlib.util.find_spec("nvidia")
        for root in (spec.submodule_search_locations or []) if spec else []:
            out += glob.glob(os.path.join(root, "*", "bin")) + glob.glob(os.path.join(root, "*", "lib"))
    except Exception:
        pass
    if not nvidia_only:
        try:
            spec = importlib.util.find_spec("torch")           # found, not loaded
            if spec and spec.origin:
                out.append(os.path.join(os.path.dirname(spec.origin), "lib"))
        except Exception:
            pass
    return [f for f in out if glob.glob(os.path.join(f, "*cublas*")) or glob.glob(os.path.join(f, "*cudnn*"))]


def use_cuda_folders():
    """Points Windows at those folders, so the speech and translation engine (CTranslate2) finds the GPU libraries
    without loading PyTorch itself: a couple of seconds quicker at start and a few hundred MB less memory."""
    if sys.platform != "win32":
        return
    folders = cuda_folders()
    if folders:
        os.environ["PATH"] = os.pathsep.join(folders + [os.environ.get("PATH", "")])
        for folder in folders:
            try:
                os.add_dll_directory(folder)
            except (OSError, AttributeError):
                pass


install_missing()
use_cuda_folders()
import numpy as np  # noqa: E402
import pyaudio  # noqa: E402
from flask import Flask, Response, abort, g, jsonify, request, send_from_directory  # noqa: E402
from werkzeug.serving import make_server  # noqa: E402

# ---------------------------------------------------------------- defaults
RATE = 16000   # Whisper wants 16 kHz mono
SETTINGS_FILE = os.path.join(HERE, "translator_settings.json")
FONT_DIR = os.path.join(HERE, "fonts")   # drop .ttf / .otf files here
FONT_TYPES = {".ttf": "font/ttf", ".otf": "font/otf", ".woff": "font/woff", ".woff2": "font/woff2"}


def font_files():
    """{font name: file} for every font file in the fonts folder. The name is the file name, e.g. Taakeferd.ttf -> Taakeferd."""
    try:
        os.makedirs(FONT_DIR, exist_ok=True)
        names = sorted(os.listdir(FONT_DIR))
    except OSError:                  # read-only folder etc.: just no custom fonts
        return {}
    out = {}
    for f in names:
        stem, ext = os.path.splitext(f)
        name = re.sub(r"[^\w \-]", "", stem).strip()[:60]
        if ext.lower() in FONT_TYPES and name:
            out[name] = f
    return out

# Languages for the language dial: speech recognition (Whisper) and text translation (M2M100 / NLLB) both know these.
LANGUAGES = {
    "ar": "Arabic", "bg": "Bulgarian", "zh": "Chinese", "hr": "Croatian", "cs": "Czech", "nl": "Dutch",
    "en": "English", "et": "Estonian", "fi": "Finnish", "fr": "French", "de": "German", "el": "Greek", "he": "Hebrew",
    "hi": "Hindi", "hu": "Hungarian", "id": "Indonesian", "it": "Italian", "ja": "Japanese", "ko": "Korean",
    "lv": "Latvian", "lt": "Lithuanian", "no": "Norwegian", "pl": "Polish", "pt": "Portuguese", "ro": "Romanian",
    "ru": "Russian", "sr": "Serbian", "sk": "Slovak", "sl": "Slovenian", "es": "Spanish", "sv": "Swedish",
    "th": "Thai", "tr": "Turkish", "uk": "Ukrainian", "vi": "Vietnamese",
}
# Speech in "a" -> subtitles in "b".
DEFAULT_LANGUAGES = {"mode": "one_way", "a": "sv", "b": "en"}


def clean_languages(data, base=DEFAULT_LANGUAGES):
    out = dict(base)
    if isinstance(data, dict):
        for k in ("a", "b"):
            if isinstance(data.get(k), str) and data[k] in LANGUAGES:
                out[k] = data[k]
    out["mode"] = "one_way"
    return out


def ways(langs):
    """The (spoken, shown) directions this language setting has."""
    return [(langs["a"], langs["b"])]


def clean_speech_size(value, base="auto"):
    """The "Speech model" choice: "auto" or one of SPEECH_SIZES (small / medium / large)."""
    return value if isinstance(value, str) and (value == "auto" or value in SPEECH_SIZES) else base


ENGINE = {
    "model_size": "auto", "custom_words": [], "device": "auto", "model_dir": "",
    "max_segment": 10.0,       # lock in after this many seconds of non-stop talking (shorter = lighter passes)
    "min_speech": 0.3,         # ignore sounds shorter than this
    "vad_sensitivity": 3.0,    # speech must be this many times louder than the background
    "min_level": 0.004,        # absolute minimum loudness that counts as speech
    "use_context": True,       # give Whisper the previous sentence
    "boost_quiet_mic": True,
    # Whisper always looks at a 30-second window, and here most of it is empty: the audio handed over is a few
    # seconds long. Looking at a shorter window makes every pass 1.5 - 3x quicker (and that much lighter on the GPU).
    # A pass that comes out odd on a short window (a loop, far too many words, time marks past the end) is redone
    # on the full 30 seconds straight away, so the result is never worse than before. 0 = always the full window.
    "draft_window": 10.0,      # seconds the model looks at for a draft (at least; longer audio gets more)
    "final_window": 15.0,      # the same for the careful pass that writes the finished line. Only used when the words
                               # are written in the spoken language; Whisper's own translation to English always
                               # gets the full 30 seconds for the finished line
    # The quiet the model has to see after the audio, in seconds. Measured on 148 real recordings of 4 - 22 s with
    # large-v3-turbo: careful passes with only 3 s of quiet lost the thread in 49 of them (the text looped or the
    # time marks ran off the end; each was redone on the full window), and even with 8 s they got 10.3 % of the
    # words wrong where the full window gets 9.4 %. So a finished line is only written on the short window when the
    # audio leaves final_quiet seconds of quiet in it (up to 7 s of speech); longer speech gets the full 30 seconds.
    # Drafts are as right with 2 s of quiet as on the full window (10.2 % / 10.0 %) and twice as quick, so their
    # window just grows with the audio.
    "draft_quiet": 2.0, "final_quiet": 8.0,
    # Drafts keep the words they agreed on (see Whisper._kept): what two drafts in a row have in common stays, except
    # the last draft_hold pieces of words; every draft_refresh seconds of new sound a draft is written from nothing
    # again. draft_refresh 0 = every draft writes everything, as before.
    "draft_hold": 3, "draft_refresh": 3.0,
    "cpu_final_beam": 1,       # candidates compared for a finished line when it runs on the CPU (see Whisper._beam)
    # The first drafts of a sentence. From a fraction of a second of speech the model often just guesses ("Tack.",
    # "Ja."), and the guess flashed on screen before the real words. Measured on the starts of 148 Swedish sentences,
    # drafts from up to 1 s of speech: half were guesses, and the model's own sureness (average log-probability)
    # tells them apart fairly well - right ones were around -0.27, guesses around -0.55. So a draft from less than
    # first_draft_seconds of audio (that includes the 0.4 s kept from before the voice) is only shown when the
    # sureness is at least first_draft_sure; otherwise the next draft, a quarter of a second later, gets its turn.
    # That keeps 85 % of the right early drafts and drops the least sure half of the guesses. 0 seconds = show all.
    # Only used with KB-Whisper, the model it was measured on: Whisper translating to English by itself is less sure
    # of every first draft, and there the same line held back good ones (first words after 1.3 s instead of 0.6 s).
    "first_draft_seconds": 1.5, "first_draft_sure": -0.5,
    "short_line_sure": -0.6,   # KB-Whisper only: a line of one or two words isn't shown below this sureness (see
                               # Whisper._quick_segments; it is how that model's guesses from noise are caught)
}
# updates/s = max live re-translations (GPU_LIMIT can make it fewer),
# end/long_silence = pause that ends a sentence / longer wait if it looks unfinished,
# early_silence = a pause this short already starts the careful pass, so the line can lock in the moment the pause
#                 turns out to be the end of the sentence (0 = wait for end_silence first: fewer passes)
RESPONSIVENESS = {
    "snappy":   dict(updates_per_second=5.0, end_silence=0.6, long_silence=1.1, final_beam=3, early_silence=0.35),
    "balanced": dict(updates_per_second=2.5, end_silence=0.7, long_silence=1.6, final_beam=5, early_silence=0.4),
    "light":    dict(updates_per_second=1.5, end_silence=0.8, long_silence=1.8, final_beam=5, early_silence=0),
}

# state: (label, encouraging hints, colour)
STATES = {
    "loading":    ("Warming up", ["Getting everything ready for you..."], "#fbbf24"),
    "no_mic":     ("Mic missing", ["Plug in a mic whenever you're ready"], "#94a3b8"),
    "ready":      ("Ready when you are", ["You've got this :3", "Take your time, no rush",
                                          "Whenever you're ready", "Go get 'em :3"], "#34d399"),
    "recording":  ("Listening", ["Sounding great, keep going", "You're doing great", "Mhm, keep going"], "#fb7185"),
    "processing": ("Got it", ["Polishing your words...", "Tidying up that line..."], "#60a5fa"),
    "error":      ("Small hiccup", ["Nothing scary - details below"], "#f87171"),
    "paused":     ("Paused", ["Mic is off - press Start listening"], "#94a3b8"),
}

SYSTEM_FONTS = ["Taakeferd", "Arial", "Arial Black", "Verdana", "Tahoma", "Segoe UI", "Calibri", "Trebuchet MS",
                "Georgia", "Times New Roman", "Courier New", "Consolas", "Impact", "Comic Sans MS"]
# (No web fonts: loading them would contact Google from OBS. Any other font: drop its .ttf/.otf into the fonts folder.)

DEFAULT_STYLE = {
    "font_family": "Consolas", "font_size": 25, "font_weight": 700,
    "color": "#94b1ff", "partial_color": "#a9b4c6", "fix_color": "#ff9f40", "italic_partial": True,
    "progress": "full",            # full (drafts + fixes) / drafts / final (finished lines only)
    "outline_color": "#000000", "outline_width": 2, "bg_color": "#000000", "bg_opacity": 0.55,
    "max_lines": 3, "position": "bottom", "align": "center", "margin": 40, "max_width": 85,
    "hide_after": 6,               # seconds of silence before the box fades (0 = never)
    "show_indicator": False,       # "Speak now / Recording" badge in OBS
    "wave_mode": "blue", "wave_area": "subtitles", "wave_color": "#0096ff", "wave_strength": 0.5,
}


def _hex(v):
    v = str(v).strip().lower()
    if not re.fullmatch(r"#[0-9a-f]{6}", v):
        raise ValueError(v)
    return v


def _font(v):
    v = re.sub(r"[^\w \-]", "", str(v)).strip()[:60]
    if not v:
        raise ValueError(v)
    return v


def _num(lo, hi, kind=float, step=None):
    def check(v):
        f = float(v)
        if not math.isfinite(f):         # "nan" / "inf" from a hand-edited file or a bad request
            raise ValueError(v)
        x = min(hi, max(lo, kind(f)))
        return x // step * step if step else round(x, 2) if kind is float else x
    return check


def _pick(*options):
    def check(v):
        if str(v).lower() not in options:
            raise ValueError(v)
        return str(v).lower()
    return check


def _bool(v):
    return v if isinstance(v, bool) else str(v).lower() in ("1", "true", "yes", "on")


STYLE_RULES = {
    "font_family": _font, "font_size": _num(8, 200, int), "font_weight": _num(100, 900, int, 100),
    "color": _hex, "partial_color": _hex, "fix_color": _hex, "italic_partial": _bool,
    "progress": _pick("full", "drafts", "final"), "outline_color": _hex, "outline_width": _num(0, 10, int),
    "bg_color": _hex, "bg_opacity": _num(0, 1), "max_lines": _num(1, 3, int),
    "position": _pick("bottom", "middle", "top"), "align": _pick("left", "center", "right"),
    "margin": _num(0, 600, int), "max_width": _num(20, 100, int), "hide_after": _num(0, 300),
    "show_indicator": _bool, "wave_mode": _pick("off", "blue", "clear"), "wave_area": _pick("subtitles", "screen"),
    "wave_color": _hex, "wave_strength": _num(0, 3),
}


def clean_style(data, base):
    out = dict(base)
    for key, rule in STYLE_RULES.items():
        if isinstance(data, dict) and key in data:
            try:
                out[key] = rule(data[key])
            except (TypeError, ValueError, OverflowError):
                pass
    return out


def load_settings():
    try:
        with open(SETTINGS_FILE, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


# Control page look: themes and the modules that can be moved around, popped out or added to OBS as docks.
UI_THEMES = {"dark": "Dark", "glass": "Glass", "light": "Light", "neon": "Neon", "sakura": "Sakura", "midnight": "Midnight"}
UI_MODULES = {"status": "Microphone", "languages": "Languages", "subtitles": "Subtitles", "waves": "Water waves",
              "preview": "Live preview", "transcript": "Transcript", "look": "Font & colours", "bot": "Mix It Up / stream bot",
              "links": "OBS links & docks"}


def clean_ui(data):
    """Theme, module order, wide modules and folded-up modules, with anything unknown dropped."""
    data = data if isinstance(data, dict) else {}
    def modules(key, default=()):
        value = data.get(key)
        if not isinstance(value, list):
            return list(default)
        return list(dict.fromkeys(m for m in value if isinstance(m, str) and m in UI_MODULES))
    order = modules("order")
    order += [m for m in UI_MODULES if m not in order]
    theme = data.get("theme")
    return {"theme": theme if isinstance(theme, str) and theme in UI_THEMES else "dark", "order": order,
            "wide": modules("wide", ["preview", "transcript"]), "collapsed": modules("collapsed", ["bot"])}


def save_settings(data):
    try:
        with open(SETTINGS_FILE + ".tmp", "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        os.replace(SETTINGS_FILE + ".tmp", SETTINGS_FILE)
    except OSError as err:
        log(f"Could not save settings: {err}", error=True)


# ---------------------------------------------------------------- microphone
class Mic:
    """Keeps one input stream open and collects 16 kHz mono float audio."""

    def __init__(self):
        self.pa = pyaudio.PyAudio()
        self.lock = threading.RLock()
        self.chunks = deque(maxlen=2400)     # ~75 s safety cap
        self.fresh = threading.Event()       # set whenever new audio arrived: the translator wakes up at once
        self.stream = None
        self.rate, self.channels = RATE, 1
        self.device = None
        self.generation = 0                  # +1 on every device change
        self.level = 0.0
        self.error = None
        self.suspended = None                # the mic to reopen after "Stop listening" (None = listening)

    @property
    def chosen(self):
        """The mic in use, or the one that comes back when listening starts again."""
        return self.device or self.suspended

    def suspend(self):
        """Stop listening: the input stream is closed for real (Windows' mic icon goes away)."""
        with self.lock:
            self.suspended = self.device or self.suspended or {}
            self._close()
            self.device, self.level = None, 0.0
            self.generation += 1

    def resume(self):
        with self.lock:
            saved, self.suspended = self.suspended, None
            if not saved:                    # there was no mic when it stopped: the translator looks for one itself
                return False, "No microphone"
            dev = find_device(self.devices(), saved["name"], saved.get("hostapi"))   # indexes change after a rescan
            if dev is None:
                self.error = f"Device disappeared: {saved['name']}"
                return False, self.error
            return self._open(dev)

    def devices(self, rescan=False):
        with self.lock:
            if rescan:                       # restart PortAudio to see newly plugged-in mics
                current = self.device
                self._close()
                self.pa.terminate()
                self.pa = pyaudio.PyAudio()
            out = []
            for i in range(self.pa.get_device_count()):
                try:
                    info = self.pa.get_device_info_by_index(i)
                    api = self.pa.get_host_api_info_by_index(info["hostApi"])["name"]
                except Exception:
                    continue
                if int(info.get("maxInputChannels", 0)) < 1 or "WDM-KS" in api:
                    continue
                out.append({"index": i, "name": info["name"], "hostapi": api, "rate": int(info["defaultSampleRate"]),
                            "channels": int(info["maxInputChannels"]), "label": f"[{i}] {info['name']}  ({api})"})
            if rescan and current:
                match = find_device(out, current["name"], current["hostapi"])
                if match:
                    self._open(match)
                else:
                    self.device, self.error = None, f"Device disappeared: {current['name']}"
                    self.generation += 1
            return out

    def default(self):
        devices = self.devices()
        try:
            idx = self.pa.get_default_input_device_info()["index"]
        except (IOError, OSError):
            idx = None
        return next((d for d in devices if d["index"] == idx), devices[0] if devices else None)

    def use(self, device):
        """device = dict from devices() or an index number."""
        with self.lock:
            if not isinstance(device, dict):
                device = next((d for d in self.devices() if d["index"] == int(device)), None)
                if device is None:
                    self.error = "No such input device"
                    return False, self.error
            if self.suspended is not None:   # not listening right now: this mic is used when listening starts again
                self.suspended = device
                return True, "ok"
            self._close()
            return self._open(device)

    def _open(self, dev):
        err = None
        for ch in dict.fromkeys([1, min(2, dev["channels"]), dev["channels"]]):
            for rate in dict.fromkeys([dev["rate"], 48000, 44100, 16000, 32000]):
                try:
                    self.channels, self.rate = ch, rate
                    stream = self.pa.open(format=pyaudio.paInt16, channels=ch, rate=rate, input=True,
                                          input_device_index=dev["index"], frames_per_buffer=max(256, rate // 32),
                                          stream_callback=self._callback, start=False)   # ~30 ms pieces
                    self.chunks.clear()
                    stream.start_stream()
                    self.stream, self.device, self.error = stream, dev, None
                    self.generation += 1
                    log(f"Microphone: {dev['name']} ({dev['hostapi']}, {rate} Hz, {ch} ch)")
                    return True, "ok"
                except Exception as e:      # unsupported rate/channels: try the next combination
                    err = e
        self.device, self.error = None, f"Could not open '{dev['name']}': {err}"
        self.generation += 1
        log(self.error, error=True)
        return False, self.error

    def _close(self):
        if self.stream is not None:
            try:
                self.stream.stop_stream()
                self.stream.close()
            except Exception:
                pass
            self.stream = None

    def _callback(self, data, frames, info, status):
        a = np.frombuffer(data, dtype=np.int16).astype(np.float32) / 32768.0
        if self.channels > 1:
            a = a[: a.size // self.channels * self.channels].reshape(-1, self.channels).mean(axis=1)
        if self.rate != RATE and a.size:
            if self.rate % RATE == 0:        # 48k/32k: block average doubles as a low-pass filter
                k = self.rate // RATE
                a = a[: a.size // k * k].reshape(-1, k).mean(axis=1)
            else:
                n = int(round(a.size * RATE / self.rate))
                a = np.interp(np.linspace(0, a.size - 1, n), np.arange(a.size), a)
        a = a.astype(np.float32, copy=False)
        if a.size:
            self.level = float(np.sqrt(np.mean(a * a)))
            self.chunks.append(a)
            self.fresh.set()
        return None, pyaudio.paContinue

    def read(self):
        """All audio since the last call, plus the device generation."""
        chunks = [self.chunks.popleft() for _ in range(len(self.chunks))]
        return (np.concatenate(chunks) if chunks else np.zeros(0, np.float32)), self.generation

    def check(self):
        with self.lock:
            try:
                ok = self.stream is None or self.stream.is_active()
            except Exception:
                ok = False
            if not ok:
                name = self.device["name"] if self.device else "?"
                self._close()
                self.device, self.level = None, 0.0
                self.generation += 1
                self.error = f"Microphone stopped (unplugged?): {name}"
                log(self.error, error=True)

    def close(self):
        with self.lock:
            self._close()
            try:
                self.pa.terminate()
            except Exception:
                pass


def find_device(devices, name, hostapi=None):
    return (next((d for d in devices if d["name"] == name and d["hostapi"] == hostapi), None)
            or next((d for d in devices if d["name"] == name), None))


# ---------------------------------------------------------------- local server (OBS overlay + control)
def _int_setting(value, default, lo, hi):
    """A number from the settings file, or the default if it's missing or broken."""
    try:
        f = float(value)
        return int(min(hi, max(lo, f))) if math.isfinite(f) else default
    except (TypeError, ValueError, OverflowError):
        return default


def port_is_free(host, port):
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind((host, port))
            return True
        except OSError:
            return False


class Hub:
    """Holds the subtitles, style, languages and status, and serves the OBS overlay on this PC only.
    Pages get live updates over one plain HTTP stream (Server-Sent Events): no outside scripts needed."""

    LEVEL_HZ = 15                         # mic loudness updates per second for the waves and the meter

    def __init__(self, mic, remote_control=False):
        self.mic = mic
        self.settings = load_settings()
        self.style = clean_style(self.settings.get("style", {}), DEFAULT_STYLE)
        version = self.settings.get("style_version", 1)
        version = version if isinstance(version, int) else 1
        if self.settings.get("style") and version < 4:      # newer default looks, applied once, then her choices stay
            if version < 2:
                self.style.update(max_lines=3, partial_color="#a9b4c6")
            if version < 3:
                self.style.update(font_size=25, font_family="Consolas", color="#94b1ff")
            self.style["italic_partial"] = True
            if self.style["fix_color"] == "#ffd166":
                self.style["fix_color"] = "#ff9f40"
            self.settings.update(style=self.style, style_version=4)
            save_settings(self.settings)
        self.languages = clean_languages(self.settings.get("languages"))
        self.speech_size = clean_speech_size(self.settings.get("speech_size"))   # the "Speech model" buttons
        self.lang_version = 0                 # +1 whenever the language dial or the speech model size changes
        self.ui = clean_ui(self.settings.get("ui"))
        self.lock = threading.Lock()
        self.status_lock = threading.Lock()
        self.settings_lock = threading.Lock()
        self.clients, self.clients_lock = set(), threading.Lock()   # one queue per open page
        self.server = None
        self.lines = deque(maxlen=30)         # (id, text)
        self.next_id = 1
        self.version = 0                      # +1 on every text change
        self.partial, self.stage = "", "draft"   # stage: draft = quick guess, check = careful pass about to lock in
        self.gpu_limit = _int_setting(self.settings.get("gpu_limit", GPU_LIMIT), GPU_LIMIT, 10, 100) if GPU_SLIDER else GPU_LIMIT
        self.paused = False                   # "Stop listening" pressed: the mic is closed until it's pressed again
        self.resumed = threading.Event()      # wakes the translator the moment listening starts again
        self.pause_lock = threading.Lock()
        key = self.settings.get("remote_key")  # secret part of the Mix It Up links; stays the same between starts
        if not (isinstance(key, str) and re.fullmatch(r"[A-Za-z0-9_-]{24,64}", key)):
            key = secrets.token_urlsafe(24)
            self._save(remote_key=key)
        self.remote_key = key
        self.status = {"mic": None, "listening": False, "model": "loading...", "updates_per_sec": 0.0, "error": None,
                       "notice": None, "mt": "off", "gpu_limit": self.gpu_limit, "languages": self.languages,
                       "speech_size": self.speech_size, "speech_problem": None, "paused": False, "speed": None,
                       "mt_model": None}
        self.set_state("loading")

        # Only pages served by this PC may connect: the Host check blocks DNS-rebinding tricks, and changes need
        # the control page's secret token (made fresh every start), so other websites open in a browser can't
        # read the subtitles or change anything.
        hosts = {f"{h}:{PORT}" for h in {HOST, "127.0.0.1", "localhost"}}
        origins = {f"http://{h}" for h in hosts}
        self.token = secrets.token_urlsafe(32)
        logging.getLogger("werkzeug").setLevel(logging.ERROR)
        self.app = app = Flask(__name__)
        app.config["MAX_CONTENT_LENGTH"] = 64 * 1024
        self.pages = {}                       # the page templates, compiled once instead of on every page load

        @app.before_request
        def only_this_pc():
            if request.host not in hosts:
                abort(403)
            if request.method != "GET":
                if (request.headers.get("Origin") not in origins or not request.is_json
                        or not secrets.compare_digest(request.headers.get("X-Token", ""), self.token)):
                    abort(403)
            g.nonce = secrets.token_urlsafe(16)

        @app.after_request
        def safe_headers(resp):
            resp.headers["Content-Security-Policy"] = (
                f"default-src 'none'; script-src 'nonce-{g.get('nonce', 'none')}'; style-src 'self' 'unsafe-inline'; "
                "font-src 'self'; connect-src 'self'; img-src 'self' data:; frame-src 'self'; "
                "frame-ancestors 'self'; base-uri 'none'; form-action 'none'")
            resp.headers["X-Content-Type-Options"] = "nosniff"
            resp.headers["Referrer-Policy"] = "no-referrer"
            resp.headers["Cache-Control"] = "no-store"
            resp.headers["Cross-Origin-Resource-Policy"] = "same-origin"
            return resp

        overlay = lambda: self.render("overlay", OVERLAY_HTML, nonce=g.nonce, local_fonts=font_files())
        app.add_url_rule("/", "overlay", overlay)
        app.add_url_rule("/overlay", "overlay2", overlay)

        @app.route("/fonts/<name>")
        def fonts(name):
            if name not in font_files().values():         # only the font files themselves, nothing else in the folder
                abort(404)
            return send_from_directory(FONT_DIR, name, mimetype=FONT_TYPES[os.path.splitext(name)[1].lower()])

        @app.route("/ping")
        def ping():                       # lets a second start tell this translator apart from other programs
            return Response("live-translator", mimetype="text/plain")

        @app.route("/events")
        def events():
            return Response(self._stream(), mimetype="text/event-stream", headers={"X-Accel-Buffering": "no"})

        @app.route("/remote/<key>/<action>")
        def remote(key, action):
            """For Mix It Up and other stream bots (a "Web Request" action): start / stop / toggle / status.
            Only works with the secret key, so other websites open in a browser can't use it."""
            if not secrets.compare_digest(key.encode(), self.remote_key.encode()):
                abort(403)
            if action not in ("start", "stop", "toggle", "status"):
                abort(404)
            if action != "status":
                with self.pause_lock:
                    paused = {"start": False, "stop": True}.get(action, not self.paused)
                log(f"Stream bot: {action}")
                self.set_paused(paused)
            return Response("stopped" if self.paused else "listening", mimetype="text/plain")

        if remote_control:
            self._add_control_page()

    def render(self, name, source, **values):
        page = self.pages.get(name)
        if page is None:
            page = self.pages[name] = self.app.jinja_env.from_string(source)
        return Response(page.render(**values), mimetype="text/html")

    def _add_control_page(self):
        app, mic = self.app, self.mic
        def page(dock=None):
            return self.render(
                "control", CONTROL_HTML, nonce=g.nonce, token=self.token, overlay_url=self.overlay_url,
                remote_urls=self.remote_urls,
                remote_actions=[("start", "Start listening"), ("stop", "Stop listening"), ("toggle", "Switch on / off")],
                system_fonts=SYSTEM_FONTS, local_fonts=list(font_files()), languages=LANGUAGES,
                dock=dock, ui=self.ui, themes=UI_THEMES, modules=UI_MODULES, dock_urls=self.dock_urls, gpu_slider=GPU_SLIDER,
                text_to_english=sorted(code for code in LANGUAGES if code != "en" and english_by(code) == "text"),
                tuned_speech=sorted(code for code in LANGUAGE_MODELS if code in LANGUAGES) if CONFIG["model_size"] == "auto" else [],
                speech_sizes=[k for k in SPEECH_SIZES if isinstance(SPEECH_SIZES[k], dict)],
                speech_fixed=None if CONFIG["model_size"] == "auto" else str(CONFIG["model_size"]),
                app_window=APP_WINDOW and dock is None)

        app.add_url_rule("/control", "control", page)

        @app.route("/dock/<name>")
        def dock(name):
            """One module on its own page: for pop-out windows and OBS custom browser docks."""
            if name not in UI_MODULES:
                abort(404)
            return page(name)

        def action(name):
            def wrap(fn):
                app.add_url_rule(f"/api/{name}", f"api_{name}", lambda: jsonify(fn(request.get_json(silent=True))),
                                 methods=["POST"])
            return wrap

        @action("style")
        def on_style(data):
            self.update_style(data)
            return {"ok": True}

        @action("ui")
        def on_ui(data):
            self.update_ui(data)
            return {"ok": True}

        @action("clear")
        def on_clear(_):
            self.clear()
            return {"ok": True}

        @action("devices")
        def on_devices(data):
            devices = mic.devices(rescan=bool(isinstance(data, dict) and data.get("rescan")))
            current = next((d["index"] for d in devices if mic.chosen and d["name"] == mic.chosen.get("name")), None)
            return {"devices": devices, "current": current}

        @action("mic")
        def on_mic(data):
            try:
                ok, msg = mic.use(int(data["index"]))
            except (KeyError, TypeError, ValueError, OverflowError):
                return {"ok": False}
            if ok:
                self.remember_mic(mic.chosen)
            self.set_status(mic=mic.chosen["label"] if mic.chosen else None, error=None if ok else msg)
            return {"ok": ok}

        @action("listening")
        def on_listening(data):
            self.set_paused(isinstance(data, dict) and data.get("paused"))
            return {"ok": True, "paused": self.paused}

        @action("gpu_limit")
        def on_gpu_limit(data):
            self.set_gpu_limit(data.get("value") if isinstance(data, dict) else None)
            return {"ok": True}

        @action("remote_key")
        def on_remote_key(_):
            return {"urls": self.new_remote_key()}

        @action("quit")
        def on_quit(_):
            log("Turned off from the control page.")
            threading.Timer(0.3, self.quit).start()      # answer the page first, then close
            return {"ok": True}

        @action("languages")
        def on_languages(data):
            self.set_languages(data)
            return {"ok": True}

        @action("speech_size")
        def on_speech_size(data):
            self.set_speech_size(data.get("value") if isinstance(data, dict) else None)
            return {"ok": True, "value": self.speech_size}

    @property
    def overlay_url(self):
        return f"http://{HOST}:{PORT}/overlay"

    @property
    def dock_urls(self):
        return {m: f"http://{HOST}:{PORT}/dock/{m}" for m in UI_MODULES}

    @property
    def remote_urls(self):
        return {a: f"http://127.0.0.1:{PORT}/remote/{self.remote_key}/{a}" for a in ("start", "stop", "toggle")}

    def new_remote_key(self):
        """Makes new Mix It Up links; the old ones stop working."""
        self.remote_key = secrets.token_urlsafe(24)
        self._save(remote_key=self.remote_key)
        return self.remote_urls

    def run(self):
        self.server = make_server(HOST, PORT, self.app, threaded=True)
        self.server.daemon_threads = True
        self.server.serve_forever()

    # ---- live updates to the open pages ----
    @staticmethod
    def _event(name, data):
        return f"event: {name}\ndata: {json.dumps(data, separators=(',', ':'))}\n\n"

    def broadcast(self, name, data):
        msg = self._event(name, data)
        with self.clients_lock:
            clients = list(self.clients)
        for q in clients:
            try:
                q.put_nowait(msg)
            except queue.Full:                # a page that stopped reading: it gets everything fresh on reconnect
                pass

    def _stream(self):
        q = queue.Queue(maxsize=256)
        with self.clients_lock:
            self.clients.add(q)
        try:
            yield "retry: 1000\n\n"
            yield self._event("style", self.style)
            yield self._event("ui", self.ui)
            yield self._event("subtitle", self.payload())
            yield self._event("status", self.status_copy())
            level, next_level, last_beat = None, 0.0, time.monotonic()
            while True:
                try:
                    yield q.get(timeout=max(0.0, next_level - time.monotonic()))
                except queue.Empty:
                    pass
                now = time.monotonic()
                if now >= next_level:
                    next_level = now + 1.0 / self.LEVEL_HZ
                    new = round(self.mic.level if self.mic.device else 0.0, 3)
                    if new != level:
                        level = new
                        yield f"event: level\ndata: {level}\n\n"
                    elif now - last_beat > 10:   # keeps the connection alive and notices closed pages
                        last_beat = now
                        yield ": ping\n\n"
        finally:
            with self.clients_lock:
                self.clients.discard(q)

    # ---- text ----
    def payload(self):
        with self.lock:
            return {"lines": [list(x) for x in self.lines], "partial": self.partial, "stage": self.stage}

    def snapshot(self):
        with self.lock:
            return self.version, [t for _, t in self.lines], self.partial

    def send_text(self):
        self.broadcast("subtitle", self.payload())

    def commit(self, text):
        text = censor(text.strip())
        with self.lock:
            if text:
                self.lines.append((self.next_id, text))
                self.next_id += 1
            self.partial, self.stage = "", "draft"
            self.version += 1
        if text and LOG_TRANSCRIPT:
            log(f"  >> {text}")
        self.send_text()

    def set_partial(self, text, stage="draft"):
        text = censor(text.strip())
        with self.lock:
            if (text, stage) == (self.partial, self.stage):
                return
            self.partial, self.stage = text, stage
            self.version += 1
        self.send_text()

    def clear(self):
        with self.lock:
            self.lines.clear()
            self.partial = ""
            self.version += 1
        self.send_text()

    # ---- settings (all remembered in translator_settings.json) ----
    def _save(self, **changes):
        with self.settings_lock:              # pages and the window can change settings at the same moment
            self.settings.update(changes)
            save_settings(self.settings)

    def update_style(self, data):
        style = clean_style(data, self.style)
        if style == self.style:
            return
        self.style = style
        self._save(style=style)
        self.broadcast("style", style)

    def update_ui(self, data):
        ui = clean_ui(data)
        if ui == self.ui:
            return
        self.ui = ui
        self._save(ui=ui)
        self.broadcast("ui", ui)          # every open control page, pop-out and OBS dock follows along

    def remember_mic(self, dev):
        self._save(mic={"name": dev["name"], "hostapi": dev["hostapi"]})

    def set_paused(self, paused):
        """Stop listening (closes the mic) or start again with the same mic."""
        paused = bool(paused)
        with self.pause_lock:                 # the buttons and Mix It Up can press at the same moment
            if paused == self.paused:
                return
            self.paused = paused
            if paused:
                self.resumed.clear()
                self.mic.suspend()
            else:
                ok, msg = self.mic.resume()
                self.resumed.set()
        if paused:
            log("Stopped listening (microphone closed; the models stay loaded, so starting again is instant).")
            self.set_status(paused=True, listening=False)
            self.set_state("paused")
        else:
            log("Listening again." if ok else f"Listening again, but: {msg}")
            self.set_status(paused=False, listening=ok, error=None if ok else msg)

    def set_languages(self, data):
        new = clean_languages(data, self.languages)
        if new != self.languages:
            self.languages = new
            self.lang_version += 1
            self._save(languages=new)
        self.set_status(languages=self.languages)

    def set_speech_size(self, value, reload=True):
        """Auto / Small / Medium / Large: the translator loads the speech model of that size within a few seconds.
        reload=False: only remember it (the translator went back to the size that's loaded)."""
        new = clean_speech_size(value, self.speech_size)
        if new != self.speech_size:
            log(f"Speech model size: {new}.")
            self.speech_size = new
            if reload:
                self.lang_version += 1        # the translator loop switches the model, as for a new language setting
            self._save(speech_size=new)
        self.set_status(speech_size=self.speech_size)

    # ---- status (updated from several threads, so always sent as a copy) ----
    def status_copy(self):
        with self.status_lock:
            return dict(self.status)

    def set_status(self, **kw):
        with self.status_lock:
            if all(self.status.get(k) == v for k, v in kw.items()):
                return                        # nothing new: don't wake every page up
            self.status.update(kw)
            snapshot = dict(self.status)
        self.broadcast("status", snapshot)

    def set_state(self, state):
        with self.status_lock:
            same = self.status.get("state") == state
        if not same:
            label, hints, color = STATES[state]
            self.set_status(state=state, state_label=label, state_hint=random.choice(hints), state_color=color)

    def shutdown(self):
        if self.server is not None:
            threading.Thread(target=self.server.shutdown, daemon=True).start()

    def set_gpu_limit(self, value):
        if not GPU_SLIDER:
            return
        self.gpu_limit = _int_setting(value, self.gpu_limit, 10, 100)
        self._save(gpu_limit=self.gpu_limit)
        self.set_status(gpu_limit=self.gpu_limit)

    def quit(self):
        """The "Turn off" button: close the mic and end the program."""
        try:
            self.mic.close()
        finally:
            log("Stopped.")
            os._exit(0)


# ---------------------------------------------------------------- text clean-up
HALLUCINATIONS = ("thanks for watching", "thank you for watching", "subscribe", "amara.org", "translated by",
                  "subtitles by", "subtitled by", "transcribed by", "textning", "svensktextning", "like and share",
                  "see you in the next", "www.", ".com",
                  "tack för att ni tittade", "tack för att du tittade", "tack för att ni har tittat", "undertexter av",
                  "undertexter från", "textat av")      # the same made-up lines as Swedish text (speech written down first)
MADE_UP = ("tack till elever och person", "som hjälpte med videon", "textning stina hedin", "btistudios")
# (what large-v3-turbo wrote for hiss, clicks and silence when told the language is Swedish, sure of itself)
SWEDISH = set("och det att jag är inte som en ett på med för har den till av men vi du så om kan vad nu "
              "också eller där här bara mycket skulle måste hon han".split())
REPEAT = re.compile(r"\b((?:[\w']+[\s,.!?-]+){1,6}?)\1{2,}", re.IGNORECASE)
NO_SPEECH = re.compile(r"<\|?\s*no\s?speech\s*\|?>", re.IGNORECASE)   # what KB-Whisper writes when nobody is talking


def collapse_repeats(text):          # "go go go go go" -> "go" (Whisper sometimes loops)
    prev = None
    while prev != text:
        prev, text = text, REPEAT.sub(r"\1", text)
    return re.sub(r"\s+", " ", text).strip()


# Slurs to hide (English and Swedish). Stored scrambled with ROT13 (every letter moved 13 places) so they don't
# sit readable in this file; to read the list: codecs.decode(word, "rot13"). A * at the end means "and any
# ending" (e.g. plurals); other words also match common endings like -s, -es, -ed, -ing.
SLURS_ROT13 = ["avttre*", "avttn*", "avttnu*", "pbba", "xvxr", "fcvp", "jrgonpx*", "ornare*", "puvax", "tbbx*",
               "enturnq*", "gbjryurnq*", "cnxv", "snttbg*", "snt", "snttl", "qlxr", "genaal", "genaavrf", "furznyr*",
               "ergneq", "wvtnobb*", "cbepu zbaxrl", "whatyr ohaal", "mvccreurnq*", "tbyyvjbt*", "erqfxva*",
               "artre*", "artere*", "oynggr*", "finegfxnyyr*"]
GRAWLIX = "@#$%&!"
CENSOR_LANGS = ("en",)            # every line in another language is also translated back to English and checked
                                  # there (see Pipeline.shield), on top of the word lists


BLOCKLIST_DIR = os.path.join(HERE, "blocked_words")
# Scripts written without spaces between words: their entries match anywhere inside the text.
NO_SPACES = re.compile(r"[฀-๿぀-ヿ㐀-䶿一-鿿豈-﫿]")


def list_files():
    try:
        return sorted(os.path.join(BLOCKLIST_DIR, f) for f in os.listdir(BLOCKLIST_DIR) if f.lower().endswith(".txt"))
    except OSError:
        return []


def _list_words():
    """Every word to hide: the built-in list, BLOCKED_WORDS and the files in the blocked_words folder."""
    words = [codecs.decode(w, "rot13") for w in SLURS_ROT13] + [str(w) for w in BLOCKED_WORDS]
    for path in list_files():
        try:
            with open(path, encoding="utf-8-sig", errors="ignore") as f:
                words += [line.split("#")[0] for line in f]
        except OSError:
            pass
    allowed = [re.escape(str(w).strip().lower().rstrip("*")) + (r".*" if str(w).strip().endswith("*") else "")
               for w in ALLOWED_WORDS if str(w).strip()]
    allowed = re.compile("|".join(allowed)) if allowed else None
    out = set()
    for word in words:
        word = " ".join(word.split()).lower()
        if word.strip("*") and not (allowed and allowed.fullmatch(word.rstrip("*"))):
            out.add(word)
    return out


def _word_tree(patterns):
    """One pattern for many words, branching letter by letter ("cat", "car", "dog" -> (?:ca(?:t|r)|dog)), so a text
    is checked against thousands of words in one walk instead of trying them one after another. `patterns` holds
    (letters, ending) pairs: the letters as a list of ready-made regex pieces, the ending as regex."""
    tree = {}
    for letters, ending in patterns:
        node = tree
        for piece in letters:
            node = node.setdefault(piece, {})
        node.setdefault("", set()).add(ending)

    def build(node):
        options = []
        if "" in node:                                   # a word ends here (longest ending first)
            options += sorted(node[""], key=len, reverse=True)
        longer = [piece + build(child) for piece, child in node.items() if piece != ""]
        options = longer + options                       # try the longer words first
        return options[0] if len(options) == 1 else "(?:" + "|".join(options) + ")"
    return build(tree)


def _censor_pattern(words):
    spaced, unspaced = [], []
    for word in words:
        if NO_SPACES.search(word):
            unspaced.append(([re.escape(c) for c in word.rstrip("*")], ""))
        else:
            ending = r"\w*" if word.endswith("*") else r"(?:s|es|z|ed|ing|ers?)?"
            letters = [r"[\s-]+" if c == " " else re.escape(c) for c in word.rstrip("*")]   # "two words" = "two-words"
            spaced.append((letters, ending))
    alternatives = []
    if spaced:
        alternatives.append(r"(?<!\w)" + _word_tree(spaced) + r"(?!\w)")
    if unspaced:
        alternatives.append(_word_tree(unspaced))
    return re.compile("|".join(alternatives), re.IGNORECASE) if alternatives else None


def _lists_stamp():
    stamp = []
    for path in list_files():
        try:
            stamp.append((path, os.path.getmtime(path), os.path.getsize(path)))
        except OSError:
            pass
    return tuple(stamp)


CENSORED, _LISTS, _CENSOR_SEEN = None, {"stamp": None, "checked": 0.0}, OrderedDict()


def refresh_word_lists(force=False):
    """(Re)loads the word lists; edits to the files are picked up within a few seconds, even while running."""
    global CENSORED
    now = time.monotonic()
    if not force and now - _LISTS["checked"] < 5.0:
        return
    _LISTS["checked"] = now
    stamp = _lists_stamp()
    if force or stamp != _LISTS["stamp"]:
        _LISTS["stamp"] = stamp
        words = _list_words()
        CENSORED = _censor_pattern(words)
        _CENSOR_SEEN.clear()
        log(f"Word filter: {len(words)} words and phrases from the built-in list and {len(stamp)} file(s) "
            f"in the blocked_words folder.")


def _mask(n):
    return "*" * n if CENSOR_STYLE == "stars" else (GRAWLIX * n)[:n]


def censor(text):
    """Replaces hate words with @#$%&! (or *****) of the same length; everything else stays as it is.
    Drafts repeat the same text many times while someone talks, so recent answers are remembered."""
    if not (CENSOR and text):
        return text
    refresh_word_lists()
    if CENSORED is None:
        return text
    seen = _CENSOR_SEEN.get(text)
    if seen is None:
        seen = _CENSOR_SEEN[text] = CENSORED.sub(lambda m: _mask(len(m.group(0))), text)
        if len(_CENSOR_SEEN) > 1000:
            _CENSOR_SEEN.popitem(last=False)
    return seen


def mask_all(text):
    """Every word hidden, punctuation and spaces kept."""
    return re.sub(r"\w+", lambda m: _mask(len(m.group(0))), text)


def english_by(src):
    """"whisper" or "text": how speech in src becomes English subtitles (see ENGLISH_BY)."""
    mode = str(ENGLISH_BY).strip().lower()
    if mode == "auto":
        return "text" if src in TEXT_TO_ENGLISH else "whisper"
    return "text" if mode == "text" else "whisper"


def text_pairs(langs, speech_translates=True):
    """Every (from, to) text translation this language setting can ask for, the word check through English included.
    speech_translates: does the speech model write English itself for speech in this language? (then "-> English"
    needs no text translation). True / False for every language, or a function of the spoken language."""
    by_speech = speech_translates if callable(speech_translates) else (lambda src: speech_translates)
    pairs = set()
    for src, dst in ways(langs):
        if src != dst and not (dst == "en" and by_speech(src)):
            pairs.add((src, dst))
        if needs_check(src, dst):
            pairs.add((dst, "en"))
    return pairs


def needs_check(src, dst):
    """Is a line spoken in src and shown in dst also checked through English? (see CENSOR_CHECK)"""
    if not CENSOR or CENSOR_CHECK == "off" or dst in CENSOR_LANGS:
        return False
    return not (CENSOR_CHECK == "auto" and src in CENSOR_LANGS)


def is_hallucination(text):
    """Whisper's made-up lines ("Thanks for watching!", "Subtitles by ...") come on their own, so only short lines
    are checked: a real sentence that happens to say "subscribe" or a website stays."""
    low = text.lower().strip(" .!?,")
    if any(h in low for h in MADE_UP):          # nobody says these on a stream, whatever the length of the line
        return True
    return low in ("", "you", "bye", "...") or (len(low.split()) <= 8 and any(h in low for h in HALLUCINATIONS))


def looks_swedish(text):
    words = re.findall(r"[a-zåäö]+", text.lower())
    if len(words) < 3:
        return False
    return sum(w in SWEDISH for w in words) / len(words) > 0.25 or sum(any(c in w for c in "åäö") for w in words) >= 2


def ends_sentence(text):
    return bool(re.search(r"[.!?…。！？][\"')\]]*$", text.strip()))


def join(segs):
    return collapse_repeats(" ".join(s["text"] for s in segs))


def as_context(before, text):
    """The last ~200 characters of what was said, as the hint Whisper gets for the next sentence. Whisper copies the
    hint's style: after a hint without a full stop it leaves the full stops out too (measured: 1 of 8 sentences
    ended with one, against 8 of 8 after a hint that ends like a sentence) - and a line that doesn't end like a
    sentence is held back half a second longer before it locks in. So the hint always ends like a sentence."""
    text = text.strip()
    if text and not ends_sentence(text):
        text += "."
    return (before + " " + text).strip()[-200:]


SENTENCE_END = re.compile(r"([.!?…]+[\"'”’)\]]*)\s+|([。！？]+)")
NOT_AN_END = {"mr", "mrs", "ms", "dr", "st", "vs", "etc", "prof", "inc", "ltd", "jr", "sr", "nr", "ca", "bl", "tel"}


def split_sentences(text):
    """Cuts text into sentences. Translation models are trained on single sentences and tend to drop one when given
    several at once; sentence by sentence they stay accurate, and a sentence seen before costs nothing."""
    out, start = [], 0
    for m in SENTENCE_END.finditer(text):
        if m.group(1) and m.group(1).startswith(".") and "." not in m.group(1)[1:]:
            word = re.search(r"(\w+)$", text[start:m.start()])          # "Mr." / "e.g." / "3." don't end a sentence
            if word and (len(word.group(1)) == 1 or word.group(1).isdigit() or word.group(1).lower() in NOT_AN_END):
                continue
        piece = text[start:m.end()].strip()
        if piece:
            out.append(piece)
        start = m.end()
    rest = text[start:].strip()
    if rest:
        out.append(rest)
    return out


def sentence_groups(segs, must_cut=False):
    """Whisper's timed phrases joined into whole sentences (each keeps its start and end time), so the translation
    model gets sentences instead of fragments. must_cut: this is non-stop talking that has to be cut somewhere, so
    without any sentence end the last phrase stays on its own."""
    groups, cur = [], []
    for s in segs:
        cur.append(s)
        if ends_sentence(s["text"]):
            groups.append(cur)
            cur = []
    if cur:
        groups.append(cur)
    if must_cut and len(groups) == 1 and len(segs) > 1:
        groups = [segs[:-1], segs[-1:]]
    return [dict(g[0], end=g[-1]["end"], text=" ".join(x["text"].strip() for x in g)) for g in groups]


# ---------------------------------------------------------------- Whisper
def is_gpu_error(err):
    """Out of video memory or a GPU driver hiccup (common when a game, OBS and Discord all want the GPU)."""
    msg = f"{type(err).__name__} {err}".lower()
    return any(k in msg for k in ("out of memory", "outofmemory", "cuda", "cublas", "cudnn", "device-side"))


def auto_speech_model(device, to_english, spoken=None):
    """model_size "auto": the speech model for what the language setting needs.
      to_english  the speech is turned straight into English text by Whisper itself (its own "translate" mode: one
                  pass). Needs a full multilingual model - turbo and distil models can't translate.
      otherwise   the words are written down in the spoken language (and translated as text afterwards if the
                  subtitles are in another language). large-v3-turbo does this faster AND more accurately than
                  medium: large-v3's ears with a 4-layer instead of a 24/32-layer text writer."""
    if device != "cuda":
        return "small"
    if to_english:
        return "medium"
    return "large-v3-turbo"


class Whisper:
    """Speech -> text. Uses faster-whisper when it works: the same Whisper models run by CTranslate2, about 4x less
    GPU time and half the video memory of openai-whisper. If it can't start, openai-whisper is used instead."""

    def __init__(self, cfg):
        self.cfg, self.model, self.fp16, self.device = cfg, None, False, "cpu"
        self.kind = None                       # "faster" or "openai"
        self.name = None                       # the model that's loaded
        self.quick = False                     # the quick path of faster-whisper is in use (see _quick_segments)
        self.short_windows = False             # this CTranslate2 accepts a window shorter than 30 seconds
        self.redone = 0                        # passes redone on the full window because they came out odd
        self.cpu_only = False                  # the GPU kept failing: stay on the CPU until the next start
        self._heard, self._tokenizers, self._tools = None, {}, None
        self._draft, self._word_starts = None, {}   # see _kept: what the last draft wrote, and what the next can keep
        self._shown = 0                        # samples of audio in the last draft that was handed out (see first_draft_sure)
        self.text_silence = False              # this model writes silence as text (see short_line_sure)
        self.size = "auto"                     # the "Speech model" buttons: auto or one of SPEECH_SIZES

    def model_for(self, langs, device=None, general=False):
        """The model name to use for this language setting. general: only OpenAI's own models, and Whisper's own
        translation to English for every language (what the openai-whisper engine can run)."""
        name = self.cfg["model_size"]
        if name != "auto":
            return name
        device = "cpu" if self.cpu_only else (device or self.device)
        pairs = ways(langs)
        spoken = {src for src, _ in pairs}
        to_english = any(dst == "en" != src and (general or english_by(src) == "whisper") for src, dst in pairs)
        one = next(iter(spoken)) if len(spoken) == 1 and not general else None
        size = SPEECH_SIZES.get(self.size) if self.size != "auto" and not self.cpu_only else None
        if isinstance(size, dict):             # Small / Medium / Large picked on the control page (after the GPU
                                               # kept failing, the CPU gets Auto's light model instead)
            if one in size and not to_english:
                return size[one]               # one language spoken, and there's a speech model of this size for it
            picked = size.get("translate" if to_english else "write")
            if picked:
                return picked
        tuned = LANGUAGE_MODELS.get(one)
        if tuned and not to_english:
            return tuned                       # one language spoken, and there's a speech model trained for it
        return auto_speech_model(device, to_english, langs["a"])

    @property
    def can_translate(self):
        """Can this model turn speech straight into English? (turbo, distil, English-only and one-language models
        can't.)"""
        name = os.path.basename(str(self.name or "")).lower()
        tuned = {os.path.basename(str(n)).lower() for n in LANGUAGE_MODELS.values()}
        tuned |= {os.path.basename(str(n)).lower() for size in SPEECH_SIZES.values() if isinstance(size, dict)
                  for k, n in size.items() if k not in ("write", "translate")}
        return not ("turbo" in name or "distil" in name or name.endswith(".en") or name in tuned or "kb-whisper" in name)

    def writes_english(self, src):
        """Does speech in src become English in the speech model itself? (see ENGLISH_BY. The openai-whisper engine,
        only used when faster-whisper can't start, has no one-language models: there Whisper translates itself.)"""
        return self.can_translate and (english_by(src) == "whisper" or self.kind == "openai")

    def load(self, hub, langs=None, device=None, name=None):
        """device/name: override the settings (used to move to the CPU when the GPU keeps failing)."""
        self.unload()
        device = device or ("cpu" if self.cpu_only else self.cfg["device"])
        langs = langs or hub.languages
        engine = self.cfg.get("engine", "auto")
        if engine != "openai-whisper":
            try:
                return self._load_faster(hub, device, langs, name)
            except Exception as err:
                self.unload()
                if engine == "faster-whisper":
                    raise
                log(f"faster-whisper could not start ({err}) - using openai-whisper instead.", error=True)
        return self._load_openai(hub, device, langs, name)

    def unload(self):
        self._heard, self._tokenizers = None, {}
        self._draft, self._word_starts, self._shown = None, {}, 0
        if self.model is None:
            return
        self.model = None
        try:
            import gc
            gc.collect()
            if self.kind == "openai":
                import torch
                torch.cuda.empty_cache()
        except Exception:
            pass

    def _load_faster(self, hub, device, langs, name):
        import ctranslate2
        from faster_whisper import WhisperModel
        from faster_whisper.utils import download_model
        if sys.platform != "win32":           # Windows finds the GPU libraries by folder (use_cuda_folders)
            try:
                import torch  # noqa: F401  (makes PyTorch's CUDA libraries available to faster-whisper)
            except Exception:
                pass
        picked = device == "auto"
        if picked:
            device = "cuda" if ctranslate2.get_cuda_device_count() > 0 else "cpu"
        if picked and device == "cpu" and has_nvidia_gpu():
            log("NOTE: NVIDIA GPU found but it can't be used - running on CPU.", error=True)
        name = name or self.model_for(langs, device)
        root = self.cfg["model_dir"] or None
        if os.path.isdir(name):
            path = name
        else:
            try:                              # already downloaded: load it without going online at all
                path = download_model(name, local_files_only=True, cache_dir=root)
                if not os.path.isfile(os.path.join(path, "model.bin")):
                    raise FileNotFoundError(path)
            except Exception:
                hub.set_status(model=f"downloading '{name}' (one time)...")
                log(f"Downloading speech model '{name}' (one time) ...")
                path = download_model(name, cache_dir=root)
        supported = ctranslate2.get_supported_compute_types(device)
        wanted = ("int8_float16", "float16", "float32") if device == "cuda" else ("int8", "float32")
        deep = not any(k in os.path.basename(name).lower() for k in ("turbo", "distil"))
        try:
            megabytes = os.path.getsize(os.path.join(path, "model.bin")) / 1e6
        except OSError:
            megabytes = 0
        if device == "cuda" and deep and (nvidia_gpu()[1] >= 7500 or 0 < megabytes < 700):
            # 16-bit weights instead of 8-bit: the text writer is quicker, for more video memory. Measured on
            # "medium": ~23 % quicker for 0.65 GB more, so only on a card with 8 GB or more. On a small model
            # (KB-Whisper small, turn by turn on 60 recordings): a draft 283 -> 207 ms, a finished line 370 -> 292 ms,
            # the same words, for 0.17 GB more - so always. (turbo's short text writer gains nothing from it.)
            wanted = ("float16", "int8_float16", "float32")
        computes = [c for c in wanted if c in supported]
        if device == "cuda":
            compute, needs_torch = self._gpu_check(hub, path, computes)
            if not compute:
                raise RuntimeError("faster-whisper can't use this GPU (see the check above)")
            if needs_torch:
                import torch  # noqa: F401  (loading it makes its CUDA libraries visible)
            computes = [compute]
        hub.set_status(model=f"loading '{name}' on {device}...")
        log(f"Loading Whisper '{name}' on {device} (faster-whisper) ...")
        started, err = time.monotonic(), None
        for compute in computes:
            try:
                self.model = WhisperModel(path, device=device, compute_type=compute,
                                          cpu_threads=2 if device == "cuda" else max(2, (os.cpu_count() or 4) // 2))
                break
            except Exception as e:            # e.g. an older GPU without int8: try the next type
                err = e
        if self.model is None:
            raise err or RuntimeError(f"no usable compute type on {device}")
        self.kind, self.device, self.fp16, self.name = "faster", device, False, name
        self.text_silence = "kb-whisper" in os.path.basename(name).lower()
        self.quick = self._quick_ready()
        self._warm_up()
        log(f"Model ready ({time.monotonic() - started:.1f} s{'' if self.quick else ', standard path'}).")
        return f"{os.path.basename(name)} on {device}"

    def _gpu_check(self, hub, path, computes):
        """A missing GPU library can make faster-whisper crash the whole program instead of reporting an error, so
        it is tried once in a separate program first. The answer is remembered until the packages change.
        Returns (the compute type that works or None, PyTorch has to be loaded for it)."""
        def version(package):
            try:
                return importlib.metadata.version(package)
            except Exception:
                return "-"
        key = f"{version('ctranslate2')}|{version('faster-whisper')}|{version('torch')}|{','.join(computes)}"
        checks = hub.settings.get("gpu_checks")
        checks = dict(checks) if isinstance(checks, dict) else {}
        saved = checks.get(key)                # one answer per set of packages: it doesn't depend on the model
        if isinstance(saved, dict):
            return saved.get("compute"), bool(saved.get("torch"))
        hub.set_status(model="checking that the GPU works with faster-whisper (one time)...")
        log("Checking that faster-whisper works on this GPU (one time) ...")
        compute, output, how = None, "", "folders"
        for how in ("folders", "torch"):      # first with just the library folders, then with PyTorch loaded
            try:
                r = subprocess.run([sys.executable, "-c", GPU_CHECK, path, how, *computes], capture_output=True,
                                   text=True, timeout=300)
                output += (r.stdout or "") + (r.stderr or "")
                found = re.search(r"^GPU-OK (\S+)$", r.stdout or "", re.M)
                compute = found.group(1) if r.returncode == 0 and found else None
            except Exception as err:
                output += str(err)
            if compute:
                break
        if compute:
            log(f"GPU check passed ({compute}{', with PyTorch loaded' if how == 'torch' else ''}).")
        else:
            log("faster-whisper can't use the GPU here, so openai-whisper will be used:\n" + output[-1500:], error=True)
        if compute or "out of memory" not in output.lower():   # a GPU that's just busy right now: ask again next time
            save = getattr(hub, "_save", None)
            if save:
                checks[key] = {"compute": compute, "torch": how == "torch"}
                save(gpu_checks=checks)
        return compute, how == "torch"

    def _load_openai(self, hub, device, langs, name):
        if importlib.util.find_spec("whisper") is None:
            hub.set_status(model="installing openai-whisper (one time)...")
            log("Installing openai-whisper ...")
            pip("openai-whisper")
            importlib.invalidate_caches()
        import torch
        import whisper
        picked = device == "auto"
        if picked:
            device = "cuda" if torch.cuda.is_available() else "cpu"
        if picked and device == "cpu" and has_nvidia_gpu():
            log("NOTE: NVIDIA GPU found but PyTorch can't use it - running on CPU (slow).\n"
                f"      Fix: python -m pip install --force-reinstall torch --index-url {TORCH_CUDA}", error=True)
        if not name or "/" in name or name in LANGUAGE_MODELS.values():
            name = self.model_for(langs, device, general=True)   # (a one-language model is faster-whisper only)
        if "/" in name:                       # set by hand in model_size: the closest of OpenAI's own models
            name = "medium" if device == "cuda" else "small"
        if name.startswith("distil"):         # faster-whisper only: the closest openai-whisper model instead
            name = "turbo"
        if device == "cuda":
            torch.backends.cuda.matmul.allow_tf32 = torch.backends.cudnn.allow_tf32 = True
            torch.set_num_threads(2)     # leave CPU cores for the game
        else:
            torch.set_num_threads(max(2, (os.cpu_count() or 4) // 2))
        hub.set_status(model=f"loading '{name}' on {device} (first run downloads it)...")
        log(f"Loading Whisper '{name}' on {device} (openai-whisper) ...")
        self.model = whisper.load_model(name, device=device, download_root=self.cfg["model_dir"] or None)
        self.kind, self.device, self.fp16, self.name, self.quick = "openai", device, device == "cuda", name, False
        self._warm_up()
        log("Model ready.")
        return f"{name} on {device}"

    def _warm_up(self):                       # both kinds of pass once, so a problem shows up now, not mid-sentence
        quiet = np.zeros(RATE, np.float32)
        self.transcribe(quiet, final=False, language="en", task="transcribe")
        self.transcribe(np.zeros(RATE, np.float32), final=True, language="en", task="transcribe")

    def _quick_ready(self):
        """Tries the quick path once on silence; if this faster-whisper version doesn't have what it needs, the
        standard path (faster-whisper's own transcribe) is used instead."""
        try:
            from faster_whisper.audio import pad_or_trim
            from faster_whisper.tokenizer import Tokenizer
            from faster_whisper.transcribe import get_suppressed_tokens
            self._tools = (pad_or_trim, Tokenizer, get_suppressed_tokens)
            self.short_windows = False
            quiet = np.zeros(RATE, np.float32)
            self._quick_segments(quiet, False, "Hello.", "en", "transcribe")
            self._quick_segments(quiet, True, None, "en", "transcribe")
            if self.model.model.is_multilingual:
                self.model.model.detect_language(self._hear(quiet)[0])
        except Exception as err:
            log(f"The quick path isn't available with this faster-whisper ({type(err).__name__}: {err}) - "
                "using the standard one.", error=True)
            self._heard = None
            return False
        try:                                  # a window shorter than 30 seconds: needs a CTranslate2 that takes one
            self._heard = None
            self.short_windows = True
            self._hear(quiet, 10.0)
        except Exception as err:
            self.short_windows = False
            log(f"Short windows aren't available with this CTranslate2 ({type(err).__name__}: {err}) - every pass "
                "looks at the full 30 seconds.", error=True)
        self._heard = None
        return True

    def window(self, final, task="transcribe"):
        """(seconds of audio the encoder looks at for this kind of pass, 0 = the standard 30; the seconds of quiet it
        needs after the audio; whether the window grows with longer audio - otherwise that gets the full 30)."""
        if final:
            return (float(self.cfg.get("final_window") or 0) if task == "transcribe" else 0.0,
                    float(self.cfg.get("final_quiet") or 0), False)
        return float(self.cfg.get("draft_window") or 0), float(self.cfg.get("draft_quiet") or 0), True

    def detect(self, audio, choices, final=True):
        """Which of `choices` (language codes) is being spoken - used in conversation mode."""
        if self.kind == "faster":
            if self.quick:                    # shares the encoder pass with the text that's written right after
                heard = self._hear(audio, *self.window(final, "translate"))[0]
                probs = {token[2:-2]: p for token, p in self.model.model.detect_language(heard)[0]}
            else:
                audio = self._prepare(audio)
                if hasattr(self.model, "detect_language"):
                    probs = dict(self.model.detect_language(audio=audio)[2])
                else:
                    _, info = self.model.transcribe(audio, beam_size=1, without_timestamps=True)
                    probs = dict(info.all_language_probs or [])
        else:
            import whisper
            mel = whisper.log_mel_spectrogram(whisper.pad_or_trim(self._prepare(audio)), n_mels=self.model.dims.n_mels)
            mel = mel.to(self.model.device)
            _, probs = self.model.detect_language(mel.half() if self.fp16 else mel)
        scores = {code: float(probs.get(code, 0.0)) for code in choices}
        best = max(choices, key=scores.get)
        total = sum(scores.values())
        return best, (scores[best] / total if total > 0 else 0.0)

    def _prepare(self, audio):
        audio = audio.astype(np.float32, copy=False)
        peak = float(np.max(np.abs(audio))) if audio.size else 0.0
        if self.cfg["boost_quiet_mic"] and 0.001 < peak < 0.3:
            audio = audio * min(8.0, 0.5 / peak)
        return audio

    # ---- quick path: talk to the model directly ----
    # The audio handed in is always one stretch under 30 seconds, so faster-whisper's machinery for long files isn't
    # needed. Doing the steps here means the encoder (the expensive half) runs ONCE per stretch of audio and its
    # result is shared by the language check, the text and a retry; faster-whisper's own calls run it once each.
    def _hear(self, audio, window=0.0, quiet=0.0, grow=True):
        """(encoder output, seconds of audio, short window used?) for one stretch of audio. window = the seconds the
        encoder looks at (0 = the standard 30), quiet = the seconds it needs after the audio; audio too long for
        that gets a longer window (grow) or the full one. Remembered while the same audio is asked about: an answer
        on a window at least as long as the one asked for is used again."""
        extractor = self.model.feature_extractor
        full = extractor.nb_max_frames
        size = full
        if window and self.short_windows:
            per_second = int(round(1 / extractor.time_per_frame))
            margin = self.cfg.get("window_margin")                          # (only set by the tests)
            needed = audio.size // extractor.hop_length + int(float(margin or quiet or window / 5) * per_second)
            if needed <= int(window * per_second):
                size = int(window * per_second)
            elif grow or margin:
                size = min(full, needed)
            size += size % 2
        if self._heard is not None and self._heard[0] is audio and self._heard[3] >= size:
            return self._heard[1], self._heard[2], self._heard[3] < full
        features = extractor(self._prepare(audio))
        frames = max(1, min(features.shape[-1] - 1, full))
        encoded = self.model.encode(self._tools[0](features[:, :frames], max(size, frames + frames % 2)))
        self._heard = (audio, encoded, frames * extractor.time_per_frame, size)
        return encoded, self._heard[2], size < full

    def _tokenizer(self, language, task):
        key = (language, task)
        if key not in self._tokenizers:
            tokenizer = self._tools[1](self.model.hf_tokenizer, self.model.model.is_multilingual, task=task, language=language)
            self._tokenizers[key] = (tokenizer, self._tools[2](tokenizer, [-1]))
        return self._tokenizers[key]

    def _quick_segments(self, audio, final, prompt, language, task, window=None):
        encoded, seconds, short = self._hear(audio, *(self.window(final, task) if window is None else (window,)))
        tokenizer, suppress = self._tokenizer(language, task)
        start = self.model.get_prompt(tokenizer, tokenizer.encode(" " + prompt.strip()) if prompt else [],
                                      without_timestamps=not final)
        key = (language, task, prompt)
        keeps = not final and task == "transcribe"      # (only measured for words written in the spoken language)
        kept = self._kept(audio, key) if keeps else []
        result = self.model.model.generate(
            encoded, [start + kept], beam_size=self._beam(final), patience=1.0,
            max_length=min(self.model.max_length, len(start) + 160), return_scores=True, return_no_speech_prob=True,
            suppress_blank=not kept, suppress_tokens=suppress, max_initial_timestamp_index=50)[0]
        new = list(result.sequences_ids[0])
        if kept and new[:len(kept)] == kept:  # CTranslate2 hands the kept words back in front of the new ones
            tokens, new = new, new[len(kept):]
        else:
            tokens = kept + new
        logprob = result.scores[0] * len(new) / (len(new) + 1)
        whole = tokenizer.decode(tokens).strip()
        if NO_SPEECH.search(whole):           # KB-Whisper writes "nobody is talking" out as text: <|nospeech|>
            self.text_silence, self._draft = True, None
            whole = NO_SPEECH.sub(" ", whole).strip()
        data = whole.encode("utf-8")
        ratio = len(data) / len(zlib.compress(data)) if data else 0.0
        phrases = self._phrases(tokens, tokenizer.timestamp_begin, seconds) if final else []
        odd = self._odd(whole, ratio, len(tokens), max((b for _, b, _ in phrases), default=0.0), seconds)
        if odd and (short or kept):
            self.redone += 1                  # came out odd on the short window (or after the words kept from the
            self._draft = None                # drafts before): once more from nothing on the full 30 seconds
            return self._quick_segments(audio, final, prompt, language, task, window=0.0)
        if keeps:
            self._agree(audio, key, tokens, bool(kept), tokenizer)
        if not re.search(r"\w", whole) or (not kept and result.no_speech_prob > 0.6 and logprob <= -1.0):
            return []                         # silence or noise
        if (self.text_silence and not kept and len(whole.split()) <= 2
                and logprob < float(self.cfg.get("short_line_sure") or -99)):
            # A model that marks silence in its text never reports a "no speech" probability, so the rule above can't
            # catch its guesses: keyboard clicks, a beep or a chord came out as "Tack!" (sureness -0.65 ... -1.2), and
            # so did the first fraction of a second of many sentences. A real "Tack!" or "Ja!" is said with more
            # sureness than that (-0.25 in the recordings), so a line of one or two words below the mark isn't shown.
            return []
        if not final:
            if audio.size < self._shown:      # shorter audio: another sentence, nothing of it is on screen yet
                self._shown = 0
            if (self.text_silence and not self._shown and not kept
                    and seconds < float(self.cfg.get("first_draft_seconds") or 0)
                    and logprob < float(self.cfg.get("first_draft_sure") or -99)):
                return []                     # the first second of a sentence, and the model is guessing: not shown yet
            self._shown = audio.size          # (once a draft is on screen, the ones after it are never held back)
        facts = dict(compression_ratio=ratio, no_speech_prob=result.no_speech_prob, avg_logprob=logprob)
        if not final:
            return [dict(start=0.0, end=seconds, text=whole, **facts)]
        phrases = [(a, b, tokenizer.decode(part)) for a, b, part in phrases]
        return [dict(start=a, end=b, text=text, **facts) for a, b, text in phrases if b > a and text.strip()]

    def _beam(self, final):
        """How many candidates a pass compares. Drafts: 1. Finished lines: final_beam on the GPU, where it costs
        little (Swedish, 148 recordings: 3 candidates got 7.7 % of the words wrong in 319 ms, 1 candidate 8.1 % in
        259 ms). On the CPU every candidate is paid for in full - a careful pass on 10 s of speech took 2.1 s with 3
        and half that with 1, too slow to keep up with someone talking - so there it is cpu_final_beam."""
        if not final:
            return 1
        return int(self.cfg["final_beam"] if self.device == "cuda" else self.cfg.get("cpu_final_beam") or self.cfg["final_beam"])

    # ---- drafts that keep the words they agreed on ----
    # While someone talks, a draft pass hears the same sentence again every fraction of a second, a little longer
    # each time, and writes all of it again - and now and then it words the start differently than the draft before,
    # so words that were already on screen jump. The words that two drafts in a row agreed on (except the last few,
    # which the next second of sound may still change) are therefore handed to the model as the start of its
    # answer, and it writes on from there. Measured on real Swedish speech, a draft every 0.4 s: 44 % fewer words
    # change on screen, the drafts are as right as before (words wrong in the last draft 7.5 % either way) and take
    # the same time (CTranslate2 still goes through the kept words one by one). Every draft_refresh seconds of new
    # sound a draft is written from nothing again, so a word that was kept wrongly can't stay; and the careful pass
    # that writes the finished line never uses any of this.
    def _kept(self, audio, key):
        """The tokens this draft doesn't have to write again ([] = write everything)."""
        d = self._draft
        if d is None or d["key"] != key or audio.size < d["size"]:      # another sentence, language or hint
            self._draft = None
            return []
        if audio.size - d["fresh"] >= float(self.cfg.get("draft_refresh") or 0) * RATE:
            return []
        return d["kept"]

    def _agree(self, audio, key, tokens, used, tokenizer):
        """Remembers this draft, and works out what the next one can keep: what it shares with the draft before,
        less the last draft_hold tokens, cut back to the start of a word."""
        hold = int(self.cfg.get("draft_hold") or 0)
        d = self._draft
        if not hold or self.cfg.get("draft_refresh") in (0, None):       # switched off
            self._draft = None
            return
        if d is None or d["key"] != key or audio.size < d["size"]:
            d = self._draft = {"key": key, "tokens": [], "kept": [], "fresh": audio.size, "size": 0}
        same = 0
        for a, b in zip(tokens, d["tokens"]):
            if a != b:
                break
            same += 1
        keep = max(0, same - hold)
        words = self._word_starts.setdefault(id(tokenizer), {})
        while keep:                           # the token after the kept ones has to start a new word
            token = tokens[keep]
            if token not in words:
                words[token] = tokenizer.decode([token]).startswith(" ")
            if words[token]:
                break
            keep -= 1
        d.update(tokens=tokens, kept=tokens[:keep] if keep >= 3 else [], size=audio.size)
        if not used:
            d["fresh"] = audio.size           # this one was written from nothing

    @staticmethod
    def _odd(text, ratio, tokens, last_mark, seconds):
        """The signs of a pass gone wrong on a short window: the text loops (it squeezes too well, runs to the length
        limit or repeats a run of three words), it has far more words than fit in the time, or its time marks run
        past the end of the audio. A false alarm only costs one pass on the full window."""
        if ratio > 2.0 or tokens >= 150 or last_mark > seconds + 1.0:
            return True
        words = re.sub(r"[^\w\s]", "", text.lower()).split()
        runs = [tuple(words[i:i + 3]) for i in range(len(words) - 2)]
        return len(runs) != len(set(runs)) or len(words) > 4.5 * seconds + 6

    @staticmethod
    def _phrases(tokens, first_mark, seconds):
        """A careful pass comes with time marks: <|0.00|> words <|1.20|><|1.20|> more words <|2.50|>.
        Returns the phrases between them as (start, end, tokens)."""
        out, last, begin = [], 0, 0.0
        cuts = [i for i in range(1, len(tokens)) if tokens[i] >= first_mark and tokens[i - 1] >= first_mark]
        for cut in cuts + [len(tokens)]:
            part = tokens[last:cut]
            last = cut
            if not any(t < first_mark for t in part):
                continue                      # only time marks, no words
            if part[0] >= first_mark:
                begin = (part[0] - first_mark) * 0.02
            end = (part[-1] - first_mark) * 0.02 if part[-1] >= first_mark else seconds   # no closing mark: to the end
            out.append((begin, max(end, begin), part))
            begin = end
        return out

    def _segments(self, audio, final, prompt, language, task):
        """Raw segments as dicts: start, end, text and the model's own confidence numbers."""
        if self.kind == "faster" and self.quick:
            return self._quick_segments(audio, final, prompt, language, task)
        audio = self._prepare(audio)
        common = dict(language=language, task=task, temperature=0.0, condition_on_previous_text=False,
                      initial_prompt=prompt or None, compression_ratio_threshold=2.4, no_speech_threshold=0.6,
                      without_timestamps=not final)
        beam = dict(beam_size=self._beam(True), patience=1.0) if final else {}
        if self.kind == "faster":
            segments, _ = self.model.transcribe(audio, log_prob_threshold=-1.0, max_new_tokens=160,
                                                beam_size=beam.get("beam_size", 1), patience=1.0, **common)
            return [dict(start=s.start, end=s.end, text=s.text, compression_ratio=s.compression_ratio,
                         no_speech_prob=s.no_speech_prob, avg_logprob=s.avg_logprob) for s in segments]
        return self.model.transcribe(audio, fp16=self.fp16, logprob_threshold=-1.0, sample_len=160, verbose=None,
                                     **beam, **common).get("segments", [])

    def _run(self, audio, final, prompt, language, task):
        segs = []
        for s in self._segments(audio, final, prompt, language, task):
            text = collapse_repeats(NO_SPEECH.sub(" ", s.get("text", "")))
            if not text or is_hallucination(text) or s.get("compression_ratio", 0) > 2.4:
                continue
            if s.get("no_speech_prob", 0) > 0.6 and s.get("avg_logprob", 0) < -1.0:
                continue
            segs.append({"start": float(s["start"]), "end": float(s["end"]), "text": text})
        return segs

    def transcribe(self, audio, final, prompt=None, language="sv", task="translate"):
        """task "translate" = speech in `language` -> English text; "transcribe" = text in `language` itself."""
        segs = self._run(audio, final, prompt, language, task)
        if final and task == "translate" and language == "sv" and segs and looks_swedish(join(segs)):
            retry = self._run(audio, final, None, language, task)   # sometimes it doesn't translate: retry without context
            if retry and not looks_swedish(join(retry)):
                segs = retry
        return segs


# Run in a separate program by Whisper._gpu_check: loads the model on the GPU and runs one pass.
GPU_CHECK = r"""
import sys
path, how, computes = sys.argv[1], sys.argv[2], sys.argv[3:]
if how == "torch":
    try:
        import torch  # noqa: F401  (loading it makes PyTorch's CUDA libraries available)
    except Exception:
        pass
import numpy as np
from faster_whisper import WhisperModel
for compute in computes:
    try:
        model = WhisperModel(path, device="cuda", compute_type=compute)
        segments, _ = model.transcribe(np.zeros(16000, np.float32), language="en", beam_size=1)
        list(segments)
        print("GPU-OK " + compute, flush=True)
        break
    except Exception as err:
        print(f"{compute}: {err}", file=sys.stderr, flush=True)
"""


# ---------------------------------------------------------------- text translation
# Ready-to-run CTranslate2 conversions on the Hugging Face hub, pinned to one exact revision so the files can never
# change under this program: key -> (repo, revision, family, MB to download).
MT_MODELS = {
    "m2m100-418m": ("jncraton/m2m100_418M-ct2-int8", "7c1b2620a4e58dacecbd8bf89cfd6da7eb9eb7b0", "m2m100", 500),
    "m2m100-1.2b": ("jncraton/m2m100_1.2B-ct2-int8", "e50078df6be13a88592b70ea42f4d74c2082e448", "m2m100", 1260),
    "nllb-600m": ("JustFrederik/nllb-200-distilled-600M-ct2-int8", "302d78f00e6fdb50a1064059df7c392b735e9d05", "nllb", 650),
    "nllb-1.3b": ("JustFrederik/nllb-200-distilled-1.3B-ct2-int8", "30c36268408177b0fce2bfcfa205d877accd327d", "nllb", 1400),
}
MT_FILES = ["model.bin", "config.json", "shared_vocabulary.*", "sentencepiece.bpe.model"]
MT_BEAM = 4                       # finished lines: this many candidates are compared (drafts: 1, the quickest)
NLLB_CODES = {
    "ar": "arb_Arab", "bg": "bul_Cyrl", "zh": "zho_Hans", "hr": "hrv_Latn", "cs": "ces_Latn", "nl": "nld_Latn",
    "en": "eng_Latn", "et": "est_Latn", "fi": "fin_Latn", "fr": "fra_Latn", "de": "deu_Latn", "el": "ell_Grek",
    "he": "heb_Hebr", "hi": "hin_Deva", "hu": "hun_Latn", "id": "ind_Latn", "it": "ita_Latn", "ja": "jpn_Jpan",
    "ko": "kor_Hang", "lv": "lvs_Latn", "lt": "lit_Latn", "no": "nob_Latn", "pl": "pol_Latn", "pt": "por_Latn",
    "ro": "ron_Latn", "ru": "rus_Cyrl", "sr": "srp_Cyrl", "sk": "slk_Latn", "sl": "slv_Latn", "es": "spa_Latn",
    "sv": "swe_Latn", "th": "tha_Thai", "tr": "tur_Latn", "uk": "ukr_Cyrl", "vi": "vie_Latn",
}
# One-pair models (OPUS-MT by the University of Helsinki, Apache 2.0 / CC BY 4.0), English -> X. They only know
# their own pair, which makes them small (75 - 230 million weights instead of 1200) and 3 - 5x quicker: measured
# ~50 ms a sentence where m2m100-418m takes ~135 ms and m2m100-1.2b ~230 ms. See PAIR_MODELS for how they're used.
# (spoken, shown) -> (official repo, the target-language token the model wants in front of the text, or None).
# English -> Japanese / Thai have no good one, and neither has any pair without English on one side: those only use
# the TRANSLATION_MODEL. The X -> English models at the end are used for the spoken languages that become English
# as text (see ENGLISH_BY), and for the word check through English.
OPUS_FAMILY = {("en", "pl"), ("en", "no"), ("en", "hr"), ("en", "sr"), ("en", "sl"),      # these pairs come from a
               ("no", "en"), ("hr", "en"), ("sr", "en"), ("sl", "en"), ("pt", "en"), ("ro", "en")}   # language-family
               # model (West / South Slavic, North Germanic, Romance): fine for drafts, less exact than a model of their own
OPUS_MODELS = {
    ("en", "pl"): ("Helsinki-NLP/opus-mt-en-zlw", ">>pol<<"), ("en", "no"): ("Helsinki-NLP/opus-mt-tc-big-en-gmq", ">>nob<<"),
    ("en", "hr"): ("Helsinki-NLP/opus-mt-en-zls", ">>hrv<<"), ("en", "sr"): ("Helsinki-NLP/opus-mt-en-zls", ">>srp_Cyrl<<"),
    ("en", "sl"): ("Helsinki-NLP/opus-mt-en-zls", ">>slv<<"),
    ("en", "ar"): ("Helsinki-NLP/opus-mt-tc-big-en-ar", ">>ara<<"), ("en", "bg"): ("Helsinki-NLP/opus-mt-tc-big-en-bg", None),
    ("en", "zh"): ("Helsinki-NLP/opus-mt-en-zh", ">>cmn_Hans<<"), ("en", "cs"): ("Helsinki-NLP/opus-mt-en-cs", None),
    ("en", "nl"): ("Helsinki-NLP/opus-mt-tc-big-gmw-gmw", ">>nld<<"), ("en", "et"): ("Helsinki-NLP/opus-mt-en-et", None),
    ("en", "fi"): ("Helsinki-NLP/opus-mt-tc-big-en-fi", None), ("en", "fr"): ("Helsinki-NLP/opus-mt-tc-big-en-fr", None),
    ("en", "de"): ("Helsinki-NLP/opus-mt-tc-big-gmw-gmw", ">>deu<<"), ("en", "el"): ("Helsinki-NLP/opus-mt-tc-big-en-el", None),
    ("en", "he"): ("Helsinki-NLP/opus-mt-en-he", None), ("en", "hi"): ("Helsinki-NLP/opus-mt-en-hi", None),
    ("en", "hu"): ("Helsinki-NLP/opus-mt-tc-big-en-hu", None), ("en", "id"): ("Helsinki-NLP/opus-mt-en-id", None),
    ("en", "it"): ("Helsinki-NLP/opus-mt-tc-big-en-it", None), ("en", "ko"): ("Helsinki-NLP/opus-mt-tc-big-en-ko", None),
    ("en", "lv"): ("Helsinki-NLP/opus-mt-tc-big-en-lv", ">>lav<<"), ("en", "lt"): ("Helsinki-NLP/opus-mt-tc-big-en-lt", None),
    ("en", "pt"): ("Helsinki-NLP/opus-mt-tc-big-en-pt", ">>por<<"), ("en", "ro"): ("Helsinki-NLP/opus-mt-tc-big-en-ro", ">>ron<<"),
    ("en", "ru"): ("Helsinki-NLP/opus-mt-tc-big-en-zle", ">>rus<<"), ("en", "sk"): ("Helsinki-NLP/opus-mt-en-sk", None),
    ("en", "es"): ("Helsinki-NLP/opus-mt-tc-big-en-es", None), ("en", "sv"): ("Helsinki-NLP/opus-mt-tc-big-en-gmq", ">>swe<<"),
    ("en", "tr"): ("Helsinki-NLP/opus-mt-tc-big-en-tr", None), ("en", "uk"): ("Helsinki-NLP/opus-mt-en-uk", None),
    ("en", "vi"): ("Helsinki-NLP/opus-mt-en-vi", ">>vie<<"),
}
OPUS_MODELS.update({(code, "en"): (f"Helsinki-NLP/opus-mt-{name}-en", None) for code, name in {
    "ar": "tc-big-ar", "bg": "tc-big-bg", "zh": "zh", "hr": "tc-big-zls", "cs": "cs", "nl": "nl", "et": "tc-big-et",
    "fi": "tc-big-fi", "fr": "tc-big-fr", "de": "de", "el": "tc-big-el", "he": "tc-big-he", "hi": "hi", "hu": "tc-big-hu",
    "id": "id", "it": "tc-big-it", "ja": "ja", "ko": "tc-big-ko", "lv": "tc-big-lv", "lt": "tc-big-lt", "no": "tc-big-gmq",
    "pl": "tc-big-zlw", "pt": "ROMANCE", "ro": "roa", "ru": "ru", "sr": "tc-big-zls", "sk": "sk", "sl": "tc-big-zls", "es": "es",
    "sv": "tc-big-gmq", "th": "th", "tr": "tc-big-tr", "uk": "uk", "vi": "vi"}.items()})
# Where both exist, the newer "tc-big" model is used: measured against the older one of the same pair (BLEU, 120 - 200
# sentences), Swedish -> English 49.6 / 44.2, English -> Swedish 46.5 / 43.8, -> German 39.9 / 37.4, -> Russian 32.8 /
# 25.8, -> Dutch 25.7 / 24.7, Polish -> English 30.6 / 26.2, at the same speed.
# OPUS_EXACT: pairs whose model writes the finished lines whatever PAIR_MODELS says (except "off").
OPUS_EXACT = {("sv", "en")}
MODEL_DIR = os.path.join(HERE, "models")      # the converted one-pair models are kept here (about 75 - 230 MB each)

# Run in a separate program by TextTranslator._pair_model, so PyTorch and transformers (only needed for this one-time
# conversion) never stay in the translator's memory: downloads the official model and converts it to CTranslate2.
CONVERT = r"""
import os, shutil, sys
repo, out = sys.argv[1], sys.argv[2]
from ctranslate2.converters import TransformersConverter
TransformersConverter(repo, copy_files=["source.spm", "target.spm"]).convert(out, quantization="int8", force=True)
try:                                     # the downloaded original isn't needed any more (300 - 600 MB)
    from huggingface_hub import constants
    shutil.rmtree(os.path.join(constants.HF_HUB_CACHE, "models--" + repo.replace("/", "--")), ignore_errors=True)
except Exception:
    pass
print("CONVERTED", flush=True)
"""


def general_model(device):
    """The TRANSLATION_MODEL to use. "auto": the accurate 1.2B model on a graphics card with 6 GB or more (it takes
    ~1.3 GB of video memory there), the small one on a smaller card or on the CPU, where the big one would be slow."""
    key = str(TRANSLATION_MODEL).strip().lower()
    if key in MT_MODELS:
        return key
    if key != "auto":
        log(f"TRANSLATION_MODEL '{TRANSLATION_MODEL}' isn't one of {', '.join(MT_MODELS)} - using auto.", error=True)
    return "m2m100-1.2b" if device == "cuda" and nvidia_gpu()[1] >= 5500 else "m2m100-418m"


class MTModel:
    """One CTranslate2 translation model with its SentencePiece tokenizer."""

    def __init__(self, folder, family, token, device):
        import ctranslate2
        import sentencepiece
        self.family, self.token, self.device = family, token, device
        pieces = lambda name: sentencepiece.SentencePieceProcessor(model_file=os.path.join(folder, name))
        if family == "opus":
            self.sp_in, self.sp_out = pieces("source.spm"), pieces("target.spm")
        else:
            self.sp_in = self.sp_out = pieces("sentencepiece.bpe.model")
        supported = ctranslate2.get_supported_compute_types(device)
        wanted = ("int8_float16", "int8", "float16", "float32") if device == "cuda" else ("int8", "float32")
        if device == "cuda" and family == "opus":
            # The small one-pair models run with 16-bit weights on the GPU: measured on Swedish -> English, turn by
            # turn on 148 sentences, 105 -> 78 ms a sentence for 0.13 GB more video memory, the translations as good.
            wanted = ("float16", "int8_float16", "int8", "float32")
        self.model, err = None, None
        for compute in [c for c in wanted if c in supported]:
            try:
                self.model = ctranslate2.Translator(
                    folder, device=device, compute_type=compute, inter_threads=1,
                    intra_threads=2 if device == "cuda" else max(2, (os.cpu_count() or 4) // 2))   # cores left for the game
                self.compute = compute
                break
            except Exception as e:
                err = e
        if self.model is None:
            raise err or RuntimeError(f"no usable compute type on {device}")

    def translate(self, texts, src, dst, beam):
        pieces = [p[:300] for p in self.sp_in.encode(list(texts), out_type=str)]
        if self.family == "opus":
            source = [([self.token] if self.token else []) + p + ["</s>"] for p in pieces]
            prefix = None
        else:
            code = NLLB_CODES.__getitem__ if self.family == "nllb" else "__{}__".format
            source = [[code(src)] + p + ["</s>"] for p in pieces]
            prefix = [[code(dst)]] * len(source)
        longest = max(len(s) for s in source)
        results = self.model.translate_batch(source, target_prefix=prefix, beam_size=beam, disable_unk=True,
                                             max_decoding_length=min(256, 3 * longest + 16))   # never runs away
        # (disable_unk: the model may not answer with its "unknown word" sign, which showed up as "⁇" in a line)
        out = []
        for r in results:
            tokens = r.hypotheses[0]
            out.append(self.sp_out.decode(tokens[1:] if prefix else tokens).strip())
        return out


class TextTranslator:
    """Translates text between the LANGUAGES, fully offline after a one-time download. Runs on CTranslate2 - the
    engine faster-whisper uses - with 8-bit models: several times faster than the same model in PyTorch and a
    third of the memory. Models load in the background the first time they're needed, so subtitles keep running."""

    CACHE_SIZE = 2000

    def __init__(self, hub, device):
        self.hub, self.device = hub, device
        self.general = general_model(device)
        self.models, self.loading, self.failed = {}, set(), {}     # by model key
        self.lock = threading.Lock()
        self.cache, self.cache_lock = OrderedDict(), threading.Lock()   # (src, dst, sentence) -> (translation, careful?)
        self.seconds = 0.0                     # what the last translate() spent in the model
        self.gpu_errors = 0

    def routes(self, src, dst):
        """(the model that writes the drafts, the model that writes the finished lines) for src -> dst."""
        key, mode = f"opus-{src}-{dst}", str(PAIR_MODELS).lower()
        if (src, dst) not in OPUS_MODELS or mode == "off" or key in self.failed:
            return self.general, self.general
        whole = mode == "all" or (src, dst) in OPUS_EXACT or (mode == "auto" and (src, dst) not in OPUS_FAMILY)
        return key, (key if whole else self.general)

    def ready(self, src, dst):
        """Can src -> dst be translated now? (One of its two models is enough to start with.)"""
        return any(key in self.models for key in self.routes(src, dst))

    def gave_up(self, src, dst):
        return all(key in self.failed for key in self.routes(src, dst))

    def retry(self):
        self.failed.clear()

    def prepare(self, langs, speech_translates=True):
        """Starts loading everything this language setting needs (first time: the download)."""
        pairs = sorted(text_pairs(langs, speech_translates))
        self.hub.set_status(mt_needed=bool(pairs))
        for src, dst in pairs:
            self.ensure(src, dst)

    def ensure(self, src, dst):
        for key in dict.fromkeys(self.routes(src, dst)):
            with self.lock:
                if key in self.models or key in self.loading or key in self.failed:
                    continue
                self.loading.add(key)
            threading.Thread(target=self._load, args=(key, src, dst), daemon=True).start()

    def _state(self, mt, notice):
        self.hub.set_status(mt=mt, notice=notice)

    def _load(self, key, src, dst):
        try:
            folder, family, token = self._files(key)
            try:
                model = MTModel(folder, family, token, self.device)
            except Exception as err:
                if self.device != "cuda" or not is_gpu_error(err):
                    raise
                log(f"The translation model doesn't fit on the GPU ({err}) - running it on the CPU.", error=True)
                self.device = "cpu"
                model = MTModel(folder, family, token, "cpu")
            result = self._self_test(model, *((src, dst) if family == "opus" else ("en", "pl")))
            if not result:
                raise RuntimeError("the model loaded but its test translation came out wrong")
            self.models[key] = model
            log(f"Translation model {key} ready on {model.device}, {model.compute} "
                f"(test: 'Hello, how are you?' -> '{result}').")
            with self.lock:
                self.loading.discard(key)
                waiting = bool(self.loading)
            names = " + ".join(sorted(self.models))
            if waiting:                        # the other model of this pair is still on its way
                self.hub.set_status(mt_model=f"{names} on {model.device}")
            else:
                self.hub.set_status(mt="ready", notice=None, mt_model=f"{names} on {model.device}")
        except Exception as err:
            self.failed[key] = str(err) or type(err).__name__
            log(f"Could not load the translation model {key}:\n" + traceback.format_exc(), error=True)
            self.loading.discard(key)
            if key != self.general:            # the one-pair model didn't work out: the general model does its work
                log(f"Using {self.general} for {src} -> {dst} instead.", error=True)
                self.ensure(src, dst)
            elif self.ready(src, dst):
                self._state("ready", f"The translation model {key} failed to load ({self.failed[key]}), so the quick "
                                     "one-pair model writes the finished lines too. Details: translator_log.txt")
            else:
                self._state("failed", f"Translation model failed to load: {self.failed[key]}. Lines stay in the "
                                      "language they were spoken in. Details: translator_log.txt")
        finally:
            self.loading.discard(key)

    def _files(self, key):
        """(folder with the model, family, target token): from disk, or downloaded the first time."""
        if key.startswith("opus-"):
            return self._pair_model(key)
        from huggingface_hub import snapshot_download
        repo, revision, family, mb = MT_MODELS[key]
        complete = lambda folder: all(os.path.isfile(os.path.join(folder, f)) for f in ("model.bin", "sentencepiece.bpe.model"))
        try:                               # already downloaded: load it without going online at all
            folder = snapshot_download(repo, revision=revision, allow_patterns=MT_FILES, local_files_only=True)
            if complete(folder):
                return folder, family, None
        except Exception:
            pass
        self._state("downloading", f"Downloading the translation model ({key}, about {mb} MB, one time)...")
        log(f"Downloading translation model {key} from {repo} (about {mb} MB, one time) ...")
        threading.Thread(target=self._show_download, args=(key, repo, mb), daemon=True).start()
        for attempt in range(1, 4):        # an interrupted download carries on where it stopped
            try:
                folder = snapshot_download(repo, revision=revision, allow_patterns=MT_FILES)
                if not complete(folder):
                    raise OSError("the download is incomplete")
                return folder, family, None
            except Exception as err:
                if attempt == 3:
                    raise
                log(f"Download interrupted ({err}), trying again ({attempt}/3) ...", error=True)
                time.sleep(3)

    @staticmethod
    def _check_torch():
        """PyTorch older than 2.6 can be tricked into running code hidden in a model file (CVE-2025-32434), so the
        original model files are only opened with 2.6 or newer."""
        try:
            major, minor = (int(x) for x in re.findall(r"\d+", importlib.metadata.version("torch"))[:2])
        except Exception:
            major, minor = 0, 0
        if (major, minor) < (2, 6):
            raise RuntimeError("this needs PyTorch 2.6 or newer (older versions can't open model files safely). "
                               f"Update torch: python -m pip install --upgrade torch --index-url {TORCH_CUDA}")

    def _pair_model(self, key):
        """A one-pair OPUS-MT model. The official files are in PyTorch format; the first time they are converted to
        CTranslate2 (8-bit, ~75 - 230 MB) into the models folder next to this file - in a separate program, so
        PyTorch never stays in this one's memory - and from then on they load straight from there, offline."""
        src, dst = key.split("-")[1:]
        repo, token = OPUS_MODELS[(src, dst)]
        folder = os.path.join(MODEL_DIR, repo.split("/")[1] + "-ct2-int8")
        if all(os.path.isfile(os.path.join(folder, f)) for f in ("model.bin", "source.spm", "target.spm")):
            return folder, "opus", token
        pair = f"{LANGUAGES[src]} → {LANGUAGES[dst]}"
        missing = [p for m, p in (("torch", "torch"), ("transformers", "transformers>=4.50"))
                   if importlib.util.find_spec(m) is None]
        if missing:
            self._state("installing", "Installing the model converter (one time)...")
            log(f"Installing {', '.join(missing)} to convert the {pair} model (one time) ...")
            pip("--prefer-binary", *missing)
            importlib.invalidate_caches()
        self._check_torch()
        self._state("downloading", f"Getting the quick {pair} translation model ready (one time, a few hundred MB)...")
        log(f"Downloading {repo} and converting it for CTranslate2 (one time) ...")
        os.makedirs(MODEL_DIR, exist_ok=True)
        shutil.rmtree(folder + ".part", ignore_errors=True)
        done = subprocess.run([sys.executable, "-c", CONVERT, repo, folder + ".part"], capture_output=True, text=True,
                              timeout=3600, creationflags=0x08000000 if sys.platform == "win32" else 0)
        if done.returncode != 0 or "CONVERTED" not in (done.stdout or ""):
            shutil.rmtree(folder + ".part", ignore_errors=True)
            raise RuntimeError("the conversion didn't work: " + ((done.stderr or done.stdout or "").strip()[-600:] or "no output"))
        shutil.rmtree(folder, ignore_errors=True)
        os.replace(folder + ".part", folder)
        return folder, "opus", token

    @staticmethod
    def _self_test(model, src, dst):
        """Translates one sentence and checks it came out as real, different text."""
        try:
            out = model.translate(["Hello, how are you?"], src, dst, 2)[0]
        except Exception as err:
            log(f"Translation self-test failed: {err}", error=True)
            return None
        ok = len(out) >= 2 and sum(c.isalpha() for c in out) >= 2 and (src != "en" or out.lower() != "hello, how are you?")
        return out if ok else None                   # (a model that translates INTO English may well leave it as it is)

    def _show_download(self, key, repo, total_mb):
        """Shows how much of the model has arrived, so a long first download doesn't look like it's broken."""
        try:
            from huggingface_hub import constants
            folder = os.path.join(constants.HF_HUB_CACHE, "models--" + repo.replace("/", "--"))
        except Exception:
            return
        last = -1
        while key in self.loading and key not in self.models:
            size = 0
            for root, _, files in os.walk(folder):
                for f in files:
                    try:
                        size += os.path.getsize(os.path.join(root, f))
                    except OSError:
                        pass
            mb = size // 1_000_000
            if mb != last and 5 < mb < total_mb - 10:
                last = mb
                self._state("downloading", f"Downloading the translation model: {mb} / {total_mb} MB (one time). "
                                           "Until it's ready, lines stay in the language they were spoken in.")
            time.sleep(1.0)

    def translate(self, texts, src, dst, final):
        """Translates a list of texts, sentence by sentence. Drafts repeat the same words many times while someone
        talks, and the word check translates lines back to English, so every sentence is remembered: one seen
        before costs nothing, and in a growing draft only the last, unfinished sentence is translated again."""
        quick, exact = self.routes(src, dst)             # drafts come from the quick model, finished lines from the
        key = exact if final else quick                  # exact one; while one of them is still loading, the other
        if key not in self.models:                       # does both
            key = quick if final else exact
        model, careful = self.models[key], final and key == exact
        parts = [split_sentences(t) for t in texts]
        out, todo = {}, []
        with self.cache_lock:
            for sentence in dict.fromkeys(s for part in parts for s in part):
                hit = self.cache.get((src, dst, sentence))
                if hit and (hit[1] or not careful):      # a careful (final) translation also serves the drafts
                    self.cache.move_to_end((src, dst, sentence))
                    out[sentence] = hit[0]
                else:
                    todo.append(sentence)
        if todo:
            started = time.perf_counter()
            try:
                done = model.translate(todo, src, dst, MT_BEAM if final else 1)
                self.gpu_errors = 0
            except Exception as err:
                self._gpu_trouble(err)
                raise
            self.seconds = time.perf_counter() - started
            with self.cache_lock:
                for sentence, result in zip(todo, done):
                    out[sentence] = result
                    self.cache[(src, dst, sentence)] = (result, careful)
                    self.cache.move_to_end((src, dst, sentence))
                while len(self.cache) > self.CACHE_SIZE:
                    self.cache.popitem(last=False)
        else:
            self.seconds = 0.0
        return [" ".join(filter(None, (out[s] for s in part))) for part in parts]

    def _gpu_trouble(self, err):
        """The GPU keeps failing under the translation model (out of video memory next to a game?): move it to the CPU."""
        if self.device != "cuda" or not is_gpu_error(err):
            return
        self.gpu_errors += 1
        if self.gpu_errors >= 3:
            log("The GPU keeps failing for text translation - moving it to the CPU.", error=True)
            self.gpu_errors, self.device = 0, "cpu"
            if self.general == "m2m100-1.2b" and str(TRANSLATION_MODEL).lower() == "auto":
                self.general = "m2m100-418m"             # the big model is too slow there
            self.models.clear()                          # they load again on the CPU the next time they're asked for


class Pipeline:
    """Speech -> text in the right language, following the language dial.
    Speech in a -> subtitles in b."""

    def __init__(self, engine, translator, hub, cfg):
        self.engine, self.translator, self.hub, self.cfg = engine, translator, hub, cfg
        self.target = hub.languages["b"]   # language the shown text is actually in (for the "PL >" tag)
        self.heard = None
        self.speech_ms = self.text_ms = 0.0   # how long the last pass took: listening / translating text
        self.forget()

    def forget(self):
        """Start fresh (the languages or the mic changed)."""
        self.said, self.said_in = "", None    # what was said before, in the spoken language, and which language
        self.fresh, self.last_size = None, 0  # the last careful pass's own words, until its line is locked in

    def words_prompt(self):
        words = self.cfg.get("custom_words") or []
        return ("Names and terms: " + ", ".join(words) + ".") if words else None

    def __call__(self, audio, final, prompt):
        started = time.perf_counter()
        self.translator.seconds = text = 0.0
        segs, lang, src = self._speech_to_text(audio, final, prompt)
        text += self.translator.seconds
        self.translator.seconds = 0.0
        segs = self.shield(segs, src, lang)
        text += self.translator.seconds
        self.speech_ms, self.text_ms = (time.perf_counter() - started - text) * 1000, text * 1000
        return segs

    def shield(self, segs, src, lang):
        """The word lists catch what they know. A line shown in a language other than English is also translated
        back to English (offline, with the translation model) and checked there; the words that come back as a hate
        word are hidden, or the whole line if they can't be pinned down. (See CENSOR_CHECK for when it's skipped.)"""
        if not segs or not needs_check(src, lang):
            return segs
        tr = self.translator
        if not tr.ready(lang, "en"):
            if tr.gave_up(lang, "en"):                   # can't check at all: the notice says the model failed
                return segs
            tr.ensure(lang, "en")
            return []                                    # held back until the check is ready (seconds, after the
                                                         # one-time download)
        try:
            back = tr.translate([s["text"] for s in segs], lang, "en", final=False)
        except Exception as err:
            log(f"Word check failed, line hidden: {err}", error=True)
            return [dict(s, text=mask_all(s["text"])) for s in segs]
        return [dict(s, text=self._hide_words(s["text"], lang)) if censor(english) != english else s
                for s, english in zip(segs, back)]

    def _hide_words(self, text, lang):
        words = text.split()
        idx = [i for i, w in enumerate(words) if re.search(r"\w", w)]
        try:
            english = self.translator.translate([words[i] for i in idx], lang, "en", final=False) if idx else []
        except Exception:
            english = []
        bad = {i for i, e in zip(idx, english) if censor(e) != e}
        if not bad:
            return mask_all(text)                        # it's in there somewhere: hide the whole line
        return " ".join(mask_all(w) if i in bad else w for i, w in enumerate(words))

    def _own_context(self, src, audio):
        """The hint for writing down speech that's then translated as text: the custom words plus the last things
        said in the spoken language. A stretch of audio that's shorter than the one before means the previous line
        was locked in and a new one started: that's when its words join the context."""
        if audio.size < self.last_size and self.fresh and self.cfg["use_context"]:
            self.said = as_context(self.said if self.said_in == src else "", self.fresh)
            self.said_in = src
        if audio.size < self.last_size:
            self.fresh = None
        self.last_size = audio.size
        parts = [self.words_prompt(), self.said if self.said_in == src else ""]
        return " ".join(p for p in parts if p) or None

    def _speech_to_text(self, audio, final, prompt):
        """Returns (segments, the language their text is in, the language that was spoken)."""
        langs = self.hub.languages
        a, b = langs["a"], langs["b"]
        conversation = False
        src, dst = a, b
        self.target = dst
        if self.heard != (src, dst):
            self.heard = (src, dst)
            self.hub.set_status(heard=f"{LANGUAGES[src]} → {LANGUAGES[dst]}" if src != dst else LANGUAGES[src])
        if dst == "en" and src != "en" and self.engine.writes_english(src):
            # Whisper translates to English by itself (best quality, fastest). In a conversation the earlier lines
            # may be in the other language, so only the custom words go into the prompt.
            return self.engine.transcribe(audio, final, self.words_prompt() if conversation else prompt, src, "translate"), dst, src
        # other targets: write down what was said, then translate the text. The earlier-sentence context that comes
        # in is in the subtitle language, so it only fits when that's also the spoken one; otherwise the words
        # written down here are kept as the context for the next sentence.
        same = src == dst and not conversation
        segs = self.engine.transcribe(audio, final, prompt if same else self._own_context(src, audio), src, "transcribe")
        if final and not same:                           # non-stop talking gets cut, with part of it heard again:
            long = audio.size >= int(self.cfg["max_segment"] * RATE)        # those words mustn't become the hint
            self.fresh = None if long or not segs else join(segs)
        if src == dst or not segs:
            self.target = src
            return segs, src, src
        tr = self.translator
        if not tr.ready(src, dst):
            tr.ensure(src, dst)
            self.target = src                            # shown in the original language until the model is ready
            return segs, src, src
        try:
            units = sentence_groups(segs, audio.size >= int(self.cfg["max_segment"] * RATE)) if final else segs
            texts = tr.translate([censor(u["text"]) for u in units], src, dst, final)   # hidden before it's translated
        except Exception as err:                        # never lose the line because of the translation step
            log(f"Translation step failed, showing the original: {err}", error=True)
            self.target = src
            return segs, src, src
        return [dict(u, text=t) for u, t in zip(units, texts) if t], dst, src



# ---------------------------------------------------------------- sentence logic
class Sentences:
    """feed() audio, call step() whenever audio arrived, get ("partial", text, stage) / ("commit", text) events."""
    FRAME = int(0.03 * RATE)

    def __init__(self, transcribe, cfg):
        self.transcribe, self.cfg = transcribe, cfg
        self.preroll = int(0.4 * RATE)
        self.end_silence, self.long_silence = int(cfg["end_silence"] * RATE), int(cfg["long_silence"] * RATE)
        self.early_silence = int(float(cfg.get("early_silence") or 0) * RATE)
        self.max_len, self.min_speech = int(cfg["max_segment"] * RATE), int(cfg["min_speech"] * RATE)
        self.context = ""
        self.reset()

    def reset(self):
        self.buf, self.vad_rest = np.zeros(0, np.float32), np.zeros(0, np.float32)
        self.noise = None
        self.speech = self.silence = self.run = self.new_audio = 0   # voiced samples / silence / voiced frames in a row
        self.partial, self.pending = "", None                        # pending = final pass awaiting confirmation
        self.early = None                                            # careful pass made in a short pause: (speech, segs)

    @property
    def state(self):
        if self.speech < self.min_speech:
            return "recording" if self.run >= 3 else "ready"         # react to the voice itself (~90 ms)
        return "recording" if self.silence < self.end_silence else "processing"

    def prompt(self):
        parts = []
        if self.cfg.get("custom_words"):
            parts.append("Names and terms: " + ", ".join(self.cfg["custom_words"]) + ".")
        if self.cfg["use_context"] and self.context:
            parts.append(self.context)
        return " ".join(parts) or None

    def feed(self, audio):           # voice activity detection
        if audio.size == 0:
            return
        f = self.FRAME
        self.buf = np.concatenate([self.buf, audio])
        self.new_audio += audio.size
        x = np.concatenate([self.vad_rest, audio])
        n = x.size // f
        if n:
            rms = np.sqrt((x[: n * f].reshape(n, f) ** 2).mean(axis=1))
            if self.noise is None:   # start low so speech right at startup isn't taken as noise
                self.noise = min(max(float(np.percentile(rms, 10)), 1e-4), 0.005)
            for r in map(float, rms):
                if r > max(self.noise * self.cfg["vad_sensitivity"], self.cfg["min_level"]):
                    self.run += 1
                else:
                    self.run = 0     # noise floor falls fast, rises slowly
                    self.noise = 0.9 * self.noise + 0.1 * r if r < self.noise else 0.995 * self.noise + 0.005 * r
                if self.run >= 3:    # >= 90 ms of sound: a voice, not a click
                    self.speech += f * (3 if self.run == 3 else 1)
                    self.silence = 0
                else:
                    self.silence += f
        self.vad_rest = x[n * f:]
        self.buf = self.buf[-2 * self.max_len:]

    def _commit(self, text, events):
        text = collapse_repeats(text)
        if text:
            events.append(("commit", text))
            if self.cfg["use_context"]:
                self.context = as_context(self.context, text)
        elif self.partial:
            events.append(("partial", "", "draft"))
        self.partial, self.pending, self.early = "", None, None

    def _partial(self, text, events, stage="draft"):
        if text != self.partial or stage == "check":
            self.partial = text
            events.append(("partial", text, stage))

    def flush(self):                 # lock in what's on screen (mic changed)
        events = []
        if self.partial:
            self._commit(self.partial, events)
        self.reset()
        return events

    def _after_commit(self):
        self.buf = self.buf[-self.preroll:]
        self.speech = self.silence = self.run = 0

    def step(self, run_partial=True, run_final=True):
        events = []
        if self.speech < self.min_speech:
            if self.speech == 0 or self.silence > self.end_silence:   # nothing, or just a bump
                self.speech = 0
                self.buf = self.buf[-self.preroll:]
                if self.partial:
                    self._partial("", events)
            return events
        paused, long_pause = self.silence >= self.end_silence, self.silence >= self.long_silence
        too_long = self.buf.size >= self.max_len
        if self.pending and self.pending[0] == self.speech and not too_long:   # final pass done, still quiet
            if long_pause:
                self._commit(join(self.pending[1]), events)
                self._after_commit()
            return events
        self.pending = None
        if not (paused or too_long):                                  # still talking: live draft
            if self.silence >= int(0.25 * RATE):                      # a short pause: no drafts (nothing new to hear)...
                if (self.early_silence and self.silence >= self.early_silence and run_final
                        and not (self.early and self.early[0] == self.speech)):
                    # ...but it may be the end of the sentence. The careful pass runs now instead of after the
                    # full pause, so if nothing more is said the line locks in the moment the pause is long
                    # enough, without waiting for a pass then. If the talking goes on, it was one better draft.
                    segs = self.transcribe(self.buf, True, self.prompt())
                    self.new_audio = 0
                    self.early = (self.speech, segs)
                    self._partial(join(segs), events)
            elif run_partial and self.new_audio >= int(0.15 * RATE):
                self.new_audio = 0
                self._partial(join(self.transcribe(self.buf, False, self.prompt())), events)
            return events
        if self.early and self.early[0] == self.speech and not too_long:
            segs = self.early[1]                                      # nothing was said since the early careful pass
        elif not run_final:                                           # GPU needs a breather first
            return events
        else:
            segs = self.transcribe(self.buf, True, self.prompt())
        self.early = None
        self.new_audio = 0
        text = join(segs)
        if paused and not too_long:
            if text and not ends_sentence(text) and not long_pause and self.buf.size < 0.75 * self.max_len:
                self.pending = (self.speech, segs)                   # looks unfinished (a breath?): wait a bit
                self._partial(text, events, "check")
                return events
            self._commit(text, events)
            self._after_commit()
            return events
        if len(segs) >= 2:                                            # non-stop talking: lock in finished sentences
            cut_i = next((i for i in range(len(segs) - 2, -1, -1) if ends_sentence(segs[i]["text"])), len(segs) - 2)
            cut = int(segs[cut_i + 1]["start"] * RATE)
            if 0 < cut < self.buf.size:
                self._commit(join(segs[: cut_i + 1]), events)
                self.buf = self.buf[cut:]
                self.speech = self.buf.size
                self._partial(join(segs[cut_i + 1:]), events)
                return events
        self._commit(text, events)
        self.buf = np.zeros(0, np.float32)
        self.speech = 0
        return events


# ---------------------------------------------------------------- translator loop
def reconnect_mic(mic, hub):
    """After an unplug: reopen the saved mic (or the default one) as soon as it's back."""
    saved = hub.settings.get("mic") if isinstance(hub.settings.get("mic"), dict) else {}
    devices = mic.devices(rescan=True)
    dev = find_device(devices, saved["name"], saved.get("hostapi")) if saved.get("name") else None
    if dev is None and not saved.get("name"):
        dev = mic.default()
    if dev is not None and mic.use(dev)[0]:
        log("Microphone reconnected.")


def translate_forever(mic, hub, cfg, stopping=None):
    stopping = stopping or threading.Event()
    engine = Whisper(cfg)
    engine.size = hub.speech_size
    while True:
        try:
            hub.set_status(model=engine.load(hub))
            break
        except Exception as err:
            log(f"Could not load Whisper model: {err}", error=True)
            if engine.size == "auto":
                hub.set_status(model="failed", error=f"Could not load Whisper model: {err}")
                hub.set_state("error")
                return
            # the size picked on the control page didn't load (too big for the GPU? no internet for the first
            # download?): start with Auto instead, so there are subtitles at all
            name = engine.model_for(hub.languages)
            hub.set_status(speech_problem=f"Could not load the {engine.size} speech model '{name}' ({str(err)[:200]}),"
                                          " so Auto is used.")
            engine.size = "auto"
            hub.set_speech_size("auto", reload=False)
    # the translation model runs where the speech model does (CTranslate2 on the GPU), otherwise on the CPU
    translator = TextTranslator(hub, "cuda" if engine.kind == "faster" and engine.device == "cuda" else "cpu")
    pipeline = Pipeline(engine, translator, hub, cfg)
    translator.prepare(hub.languages, engine.writes_english)  # start the (first-time) download right away
    proc = Sentences(pipeline, cfg)
    interval = 1.0 / max(0.2, float(cfg["updates_per_second"]))
    passes = deque()                                  # (time, seconds busy) of model passes in the last 5 s
    last_status = next_partial = next_pass = last_retry = 0.0
    gen, lang_version, gpu_errors = None, hub.lang_version, 0

    def show(events):
        for kind, text, *stage in events:
            if kind == "commit":
                hub.commit(text)
            else:
                hub.set_partial(text, *stage)

    def switch_model():
        """The language setting or the speech model size changed: load the speech model that fits it, if that's
        another one."""
        nonlocal proc, gen
        size_before, engine.size = engine.size, hub.speech_size
        want = engine.model_for(hub.languages)
        if want == engine.name:
            hub.set_status(speech_problem=None)
            return True
        before, problem = engine.name, None
        log(f"The language setting or the speech model size changed: switching the speech model from '{before}' to '{want}'.")
        hub.set_state("loading")
        for name in (want, before):
            try:
                hub.set_status(model=engine.load(hub, name=name), error=None)
                break
            except Exception as err:
                log(f"Could not load the speech model '{name}': {err}", error=True)
                hub.set_status(error=f"Could not load the speech model '{name}': {err}")
                problem = problem or f"Could not load '{name}' ({str(err)[:200]})"
        else:
            hub.set_status(model="failed")
            hub.set_state("error")
            return False
        if name == want:
            hub.set_status(speech_problem=None)
        else:                                         # the new size didn't load: the buttons show what's running
            engine.size = size_before
            hub.set_speech_size(size_before, reload=False)
            hub.set_status(speech_problem=f"{problem}, so '{before}' is still used.")
        mic.read()                                    # what was said while it loaded is dropped
        proc = Sentences(pipeline, cfg)
        gen = None
        return True

    while not stopping.is_set():
        try:
            mic.fresh.wait(0.05)                      # wakes up the moment new audio arrives
            mic.fresh.clear()
            t0 = time.monotonic()
            mic.check()
            audio, mic_gen = mic.read()
            if mic_gen != gen or hub.lang_version != lang_version:   # mic or languages changed: lock in what's shown, start fresh
                changed = hub.lang_version != lang_version
                gen, lang_version = mic_gen, hub.lang_version
                show(proc.flush())
                proc.context = ""
                pipeline.forget()
                if changed:
                    if not switch_model():
                        return
                    translator.retry()
                    translator.prepare(hub.languages, engine.writes_english)
            while passes and passes[0][0] < t0 - 5.0:
                passes.popleft()
            if t0 - last_status > 1.0:
                last_status = t0
                hub.set_status(mic=mic.device["label"] if mic.device else None, error=mic.error,
                               listening=mic.device is not None,
                               updates_per_sec=round(len(passes) / 5.0, 1),
                               gpu_busy=f"{min(100.0, sum(b for _, b in passes) / 5.0 * 100):.0f}%",
                               speed=[round(pipeline.speech_ms), round(pipeline.text_ms)] if passes else None)
            if hub.paused:                                 # "Stop listening": mic closed, nothing runs on the GPU or
                hub.set_state("paused")                    # CPU; the models stay loaded for an instant start
                hub.resumed.wait(1.0)
                continue
            if mic.device is None:
                hub.set_state("no_mic")
                if t0 - last_retry > 5.0:
                    last_retry = t0
                    reconnect_mic(mic, hub)
                time.sleep(0.3)
                continue
            proc.feed(audio)
            hub.set_state(proc.state)
            busy0 = time.monotonic()
            try:
                gpu_free = busy0 >= next_pass
                sentence_done = proc.silence >= proc.end_silence   # the line that's waiting to lock in goes first;
                events = proc.step(run_partial=gpu_free and busy0 >= next_partial,   # the breather comes after it
                                   run_final=gpu_free or sentence_done)
            except Exception as err:
                log(f"Translation error: {err}", error=True)
                proc.reset()
                hub.set_partial("")                        # don't leave a half-finished draft stuck on screen
                gpu_errors = gpu_errors + 1 if engine.device == "cuda" and is_gpu_error(err) else 0
                if gpu_errors >= 3:                        # the GPU keeps failing (out of memory while streaming?):
                    gpu_errors = 0                         # carry on on the CPU instead of stopping
                    log("The GPU keeps failing - moving speech recognition to the CPU.", error=True)
                    hub.set_state("loading")
                    engine.cpu_only = True
                    try:
                        hub.set_status(model=engine.load(hub, device="cpu", name=engine.model_for(hub.languages, "cpu")),
                                       notice="The GPU was too busy (or out of video memory), so subtitles now run on "
                                              "the CPU. Restart the translator to use the GPU again.")
                    except Exception as err2:
                        log(f"Could not move to the CPU: {err2}", error=True)
                        hub.set_status(model="failed", error=f"Speech model stopped working: {err2}")
                        hub.set_state("error")
                        return
                    proc = Sentences(pipeline, cfg)
                    gen = None
                else:
                    time.sleep(2.0 if gpu_errors else 0.5)  # give a busy GPU a moment
                continue
            now = time.monotonic()
            show(events)
            hub.set_state(proc.state)
            if now - busy0 > 0.01:                         # a model pass ran: rest so busy time stays under the limit
                gpu_errors = 0
                busy = now - busy0
                passes.append((now, busy))
                limit = max(0.1, min(1.0, hub.gpu_limit / 100))
                next_pass = now + busy * (1.0 - limit) / limit
                next_partial = now + max(0.0, interval - busy)
        except Exception as err:                       # keep translating whatever happens
            log(f"Unexpected problem, carrying on: {err}", error=True)
            time.sleep(0.5)



def open_saved_or_default_mic(mic, hub):
    saved = hub.settings.get("mic") if isinstance(hub.settings.get("mic"), dict) else {}
    dev = find_device(mic.devices(), saved["name"], saved.get("hostapi")) if isinstance(saved.get("name"), str) else None
    if not (dev and mic.use(dev)[0]):
        dev = mic.default()
        if dev:
            mic.use(dev)
        else:
            log("No microphone found.", error=True)


def engine_config():
    return {**ENGINE, **RESPONSIVENESS.get(CONFIG.get("responsiveness"), RESPONSIVENESS["balanced"]), **CONFIG}


def app_browsers():
    """Edge and Chrome, which can show a page as an app window. Edge comes with Windows 10 and 11."""
    if sys.platform == "win32":
        roots = [os.environ.get(k) for k in ("ProgramFiles(x86)", "ProgramFiles", "LOCALAPPDATA")]
        tails = [r"Microsoft\Edge\Application\msedge.exe", r"Google\Chrome\Application\chrome.exe"]
        return [os.path.join(r, t) for t in tails for r in roots if r]
    if sys.platform == "darwin":
        return ["/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
                "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"]
    found = (shutil.which(n) for n in ("microsoft-edge", "google-chrome", "chromium", "chromium-browser"))
    return [p for p in found if p]


# The app window only shows pages from this PC. These switch off the browser's own background traffic too
# (updates, sync, crash reports, usage statistics, safe-browsing look-ups, ...), so the window stays offline.
APP_WINDOW_FLAGS = ["--window-size=1280,900", "--no-first-run", "--no-default-browser-check", "--disable-background-mode",
                    "--disable-background-networking", "--disable-component-update", "--disable-sync",
                    "--disable-default-apps", "--disable-extensions", "--disable-breakpad", "--disable-domain-reliability",
                    "--disable-client-side-phishing-detection", "--metrics-recording-only", "--no-pings",
                    "--dns-prefetch-disable", "--disable-features=Translate,OptimizationHints,MediaRouter,AutofillServerCommunication"]


def open_app_window(url):
    """Shows the control page in its own window. Returns the browser process (it ends when the window and its
    pop-outs are closed), or None when no Edge / Chrome was found and the page opened in the normal browser."""
    profile = os.path.join(HERE, "window_profile")   # own profile: own process
    for exe in app_browsers():
        if os.path.isfile(exe):
            try:
                return subprocess.Popen([exe, f"--app={url}", f"--user-data-dir={profile}", *APP_WINDOW_FLAGS])
            except OSError:
                pass
    webbrowser.open(url)
    return None


def close_with_window(proc, hub):
    started = time.monotonic()
    proc.wait()
    if time.monotonic() - started < 15:
        # Ended right away: the browser handed the window to another of its processes, or it was closed straight
        # after opening. Then follow the pages instead: once no page or pop-out of this PC is open any more
        # (for half a minute, so a reload doesn't count), the translator turns off.
        quiet_since = None
        while True:
            time.sleep(2)
            with hub.clients_lock:
                open_pages = len(hub.clients)
            if open_pages:
                quiet_since = None
            elif quiet_since is None:
                quiet_since = time.monotonic()
            elif time.monotonic() - quiet_since > 30:
                break
        log("No translator window open any more.")
    else:
        log("App window closed.")
    hub.quit()


def let_games_go_first():
    """Lower the translator's CPU priority a step (Windows "below normal"), so a game and OBS win when the CPU is
    busy. The GPU is kept in check by GPU_LIMIT instead."""
    if not (GAME_FIRST and sys.platform == "win32"):
        return
    try:
        import ctypes
        kernel32 = ctypes.windll.kernel32
        kernel32.GetCurrentProcess.restype = ctypes.c_void_p
        if kernel32.SetPriorityClass(ctypes.c_void_p(kernel32.GetCurrentProcess()), 0x4000):   # BELOW_NORMAL
            log("Running at below-normal CPU priority, so the game and OBS go first.")
    except Exception as err:
        log(f"Could not lower the CPU priority: {err}", error=True)


def translator_on(port):
    """Is this translator (not some other program) answering on that port of this PC?"""
    import urllib.request
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))   # straight to this PC, never a proxy
    try:
        with opener.open(f"http://{HOST}:{port}/ping", timeout=2) as r:
            return r.read(64) == b"live-translator"
    except Exception:
        return False


def choose_port():
    """PORT if it's free. If the translator already runs, its page is opened and this copy ends. If another
    program has the port, the next free one is used and remembered, so the OBS links stay the same."""
    global PORT
    settings = load_settings()
    saved = settings.get("port")
    usable = isinstance(saved, int) and 1024 <= saved <= 65535 and settings.get("port_for") == PORT
    candidates = ([saved] if usable else []) + [PORT] + [p for p in range(PORT + 1, PORT + 30) if p <= 65535]
    for port in dict.fromkeys(candidates):
        if port_is_free(HOST, port):
            if port != PORT:
                if port != saved:
                    log(f"Port {PORT} is used by another program on this PC, so the translator uses port {port} "
                        f"from now on.\nIn OBS, use http://{HOST}:{port}/overlay (the control page shows the links).",
                        error=True)
                    settings.update(port=port, port_for=PORT)   # same port next time, even if the other program
                    save_settings(settings)                     # isn't running then: the OBS links keep working
                PORT = port
            return
        if translator_on(port):
            log(f"The translator is already running: opening http://{HOST}:{port}/control")
            if OPEN_BROWSER or APP_WINDOW:
                webbrowser.open(f"http://{HOST}:{port}/control")
            sys.exit(0)
    log(f"Ports {PORT}-{PORT + 29} are all in use on this PC. Set another PORT at the top of the .py file.", error=True)
    sys.exit(1)


def main():
    choose_port()
    let_games_go_first()
    mic = Mic()
    hub = Hub(mic, remote_control=True)
    open_saved_or_default_mic(mic, hub)
    if not START_LISTENING:
        hub.set_paused(True)
    threading.Thread(target=translate_forever, args=(mic, hub, engine_config()), daemon=True).start()
    control = f"http://{HOST}:{PORT}/control"
    log(f"\nLive Translator ({VERSION})\nControl page:  {control}\nOBS overlay:   {hub.overlay_url}\nPress Ctrl+C to stop.\n")
    if APP_WINDOW:
        window = open_app_window(control)
        if window:
            threading.Thread(target=close_with_window, args=(window, hub), daemon=True).start()
    elif OPEN_BROWSER:
        webbrowser.open(control)
    try:
        hub.run()
    except KeyboardInterrupt:
        pass
    finally:
        mic.close()
        log("\nStopped.")


# ---------------------------------------------------------------- pages
OVERLAY_HTML = r"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>Live subtitles</title>
<style>
{% for name, file in local_fonts.items() %}  @font-face { font-family: "{{ name }}"; src: url("/fonts/{{ file|urlencode }}"); }
{% endfor %}
  html, body { margin: 0; padding: 0; background: transparent; overflow: hidden; width: 100%; height: 100%; }
  canvas { position: absolute; inset: 0; width: 100%; height: 100%; }
  #fx { display: none; }
  #ind { position: absolute; left: 0; top: 0; display: none; align-items: center; gap: .5em; padding: .35em .95em .35em .7em;
         border-radius: 999px; font-weight: 700; letter-spacing: .02em; white-space: nowrap;
         box-shadow: 0 .15em .6em rgba(0, 0, 0, .25); transition: background .2s; }
  #mic { position: relative; width: 1.2em; height: 1.2em; display: inline-flex; flex: 0 0 auto; transition: color .2s; }
  #mic svg { width: 100%; height: 100%; }
  #mic.pulse::after { content: ""; position: absolute; inset: -.2em; border-radius: 50%; border: .12em solid currentColor;
                      animation: ping 1.2s ease-out infinite; }
  @keyframes ping { 0% { transform: scale(.55); opacity: .9; } 100% { transform: scale(1.35); opacity: 0; } }
</style>
</head>
<body>
<canvas id="plain"></canvas>
<canvas id="fx"></canvas>
<div id="ind">
  <span id="mic"><svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
    <rect x="8.5" y="2.5" width="7" height="12" rx="3.5"/>
    <path d="M5.5 11a6.5 6.5 0 0 0 13 0M12 17.5V21M8.5 21h7" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
  </svg></span><span id="indtext"></span>
</div>
<script nonce="{{ nonce }}">
const BADGE_STATES = ['ready', 'recording', 'processing'];
const MAX_RIPPLES = 15;
const FADE_S = 0.12;
const bus = new EventSource('/events');           // live updates from the translator on this PC only
const on = (name, fn) => bus.addEventListener(name, e => { let d; try { d = JSON.parse(e.data); } catch (err) { return; } fn(d); });
const $ = id => document.getElementById(id);
const plain = $('plain'), fx = $('fx'), ctx = plain.getContext('2d');
const ind = $('ind'), mic = $('mic'), indText = $('indtext');
let style = null, status = null, lines = [], part = '', stage = 'draft', minId = 0, hiddenPartial = null, hideTimer = null;
const effects = new Map();
const FX_MS = {fix: 1400, settle: 500, new: 220};
let W = 0, H = 0, dpr = 1, level = 0;
let dirty = true, current = null, drawn = null, alpha = 0;
function rgba(hex, a) { const n = parseInt(hex.slice(1), 16); return `rgba(${n>>16&255},${n>>8&255},${n&255},${a})`; }
function rgb01(hex) { const n = parseInt(hex.slice(1), 16); return [(n>>16&255)/255, (n>>8&255)/255, (n&255)/255]; }
function mix(a, b, t) {            // blend two #rrggbb colours, t = 0 -> a, 1 -> b
  const x = parseInt(a.slice(1), 16), y = parseInt(b.slice(1), 16), c = s => (x >> s & 255) + ((y >> s & 255) - (x >> s & 255)) * t;
  return `rgb(${c(16) | 0},${c(8) | 0},${c(0) | 0})`;
}
const ease = t => 1 - Math.pow(1 - Math.min(1, Math.max(0, t)), 3);
const norm = w => w.toLowerCase().replace(/[^\p{L}\p{N}']/gu, '');
function compare(oldW, newW) {      // per new word: 'same', 'fix' (replaced an old word) or 'new' (added)
  const n = oldW.length, m = newW.length, T = Array.from({length: n + 1}, () => new Uint16Array(m + 1));
  for (let i = n - 1; i >= 0; i--) for (let j = m - 1; j >= 0; j--)
    T[i][j] = norm(oldW[i]) === norm(newW[j]) ? T[i + 1][j + 1] + 1 : Math.max(T[i + 1][j], T[i][j + 1]);
  const out = new Array(m).fill('new');
  let i = 0, j = 0, gapOld = 0, gapNew = [];
  const closeGap = () => { gapNew.slice(0, gapOld).forEach(k => out[k] = 'fix'); gapOld = 0; gapNew = []; };
  while (i < n || j < m) {
    if (i < n && j < m && norm(oldW[i]) === norm(newW[j])) { closeGap(); out[j] = 'same'; i++; j++; }
    else if (j >= m || (i < n && T[i + 1][j] >= T[i][j + 1])) { gapOld++; i++; }
    else { gapNew.push(j); j++; }
  }
  closeGap();
  return out;
}
function fontSpec(isPartial) {
  const s = style;
  return `${isPartial && s.italic_partial ? 'italic ' : ''}${s.font_weight} ${s.font_size}px "${s.font_family}", Arial, sans-serif`;
}
function roundRect(c, x, y, w, h, r) {
  r = Math.min(r, w / 2, h / 2);
  c.beginPath(); c.moveTo(x + r, y);
  c.arcTo(x + w, y, x + w, y + h, r); c.arcTo(x + w, y + h, x, y + h, r);
  c.arcTo(x, y + h, x, y, r); c.arcTo(x, y, x + w, y, r); c.closePath();
}
function loadFont() {
  if (document.fonts) document.fonts.load(fontSpec(false)).then(redraw).catch(() => {});
}
if (document.fonts) document.fonts.addEventListener('loadingdone', redraw);
function resize() {
  dpr = window.devicePixelRatio || 1; W = window.innerWidth; H = window.innerHeight;
  for (const c of [plain, fx]) { c.width = Math.round(W * dpr); c.height = Math.round(H * dpr); }
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  if (gl) gl.viewport(0, 0, fx.width, fx.height);
  redraw();
}
window.addEventListener('resize', resize);
const words = t => t.split(/\s+/).filter(Boolean);
const showDrafts = () => style.progress !== 'final';
function visibleWords() {           // [text, isDraft, effect key]
  const out = [];
  lines.filter(l => l[0] >= minId).slice(-12).forEach(([id, t]) => words(t).forEach((w, i) => out.push([w, false, `L${id}:${i}`])));
  if (showDrafts() && part && part !== hiddenPartial) {
    words(part).forEach((w, i) => out.push([w, true, `P:${i}`]));
    if (stage === 'draft') out.push(['\u2022\u2022\u2022', true, 'dots']);   // "still listening" dots
  }
  return out;
}
function noteChanges(oldLines, oldPart, newLines, newPart) {
  const now = performance.now(), full = style && style.progress === 'full';
  const known = new Set(oldLines.map(l => l[0]));
  const fresh = newLines.filter(l => !known.has(l[0]));
  let draft = words(oldPart);
  for (const [id, t] of fresh) {      // a finished line arrived: compare it with the draft it replaces
    const w = words(t), cmp = draft.length && showDrafts() ? compare(draft, w) : null;
    w.forEach((_, i) => effects.set(`L${id}:${i}`, {kind: !cmp ? 'new' : cmp[i] === 'fix' && full ? 'fix' : 'settle', t: now}));
    draft = [];
  }
  for (const k of [...effects.keys()]) if (k.startsWith('P:')) effects.delete(k);
  if (!showDrafts()) return;
  compare(draft, words(newPart)).forEach((kind, i) => {
    if (kind !== 'same') effects.set(`P:${i}`, {kind: kind === 'fix' && full ? 'fix' : 'new', t: now});
  });
}
function wordLook(wd, now) {        // colour + alpha of one word right now
  const s = style;
  let color = wd.partial ? (stage === 'check' ? mix(s.partial_color, s.color, 0.5) : s.partial_color) : s.color, a = 1;
  const e = effects.get(wd.key);
  if (e) {
    const t = (now - e.t) / FX_MS[e.kind];
    if (t >= 1) effects.delete(wd.key);
    else if (e.kind === 'fix') color = mix(s.fix_color, color, ease((t - 0.45) / 0.55));   // hold, then fade back
    else if (e.kind === 'settle') color = mix(s.partial_color, color, ease(t));
    else a = ease(t);
  }
  if (wd.key === 'dots') a = 0.35 + 0.35 * Math.sin(now / 160);
  return {color, a};
}
function layout() {
  const s = style, fs = s.font_size, padX = 0.6 * fs, padY = 0.2 * fs, lh = 1.25 * fs;
  const areaW = Math.max(fs * 2, (W - 40) * s.max_width / 100);
  const maxText = Math.max(fs, areaW - 2 * padX);
  ctx.font = fontSpec(false);
  const space = ctx.measureText(' ').width;
  const rows = [];
  let cur = [], curW = 0;
  const flush = () => { if (cur.length) rows.push({words: cur, w: curW}); cur = []; curW = 0; };
  for (const [text, isP, key] of visibleWords()) {
    ctx.font = fontSpec(isP);
    let pieces = [text];
    if (ctx.measureText(text).width > maxText) {           // break very long words
      pieces = []; let chunk = '';
      for (const ch of text) {
        if (chunk && ctx.measureText(chunk + ch).width > maxText) { pieces.push(chunk); chunk = ''; }
        chunk += ch;
      }
      if (chunk) pieces.push(chunk);
    }
    for (const piece of pieces) {
      const w = ctx.measureText(piece).width;
      if (cur.length && curW + space + w > maxText) flush();
      curW += (cur.length ? space : 0) + w;
      cur.push({text: piece, partial: isP, w, key});
    }
  }
  flush();
  const shownRows = rows.slice(-s.max_lines);
  const textW = shownRows.reduce((m, r) => Math.max(m, r.w), 0);
  const bw = shownRows.length ? textW + 2 * padX : areaW * 0.6;
  const bh = Math.max(1, shownRows.length) * lh + 2 * padY;
  const x = s.align === 'left' ? 20 : s.align === 'right' ? W - 20 - bw : (W - bw) / 2;
  const y = s.position === 'top' ? s.margin : s.position === 'middle' ? (H - bh) / 2 : H - s.margin - bh;
  return {rows: shownRows, x, y, w: bw, h: bh, padX, padY, lh, space};
}
function draw(L, a, now) {
  ctx.clearRect(0, 0, W, H);
  if (!L || !L.rows.length || a <= 0.001) return;
  const s = style;
  ctx.globalAlpha = a;
  if (s.bg_opacity > 0) {
    ctx.fillStyle = rgba(s.bg_color, s.bg_opacity);
    roundRect(ctx, L.x, L.y, L.w, L.h, 0.2 * s.font_size); ctx.fill();
  }
  ctx.textBaseline = 'middle';
  L.rows.forEach((row, i) => {
    const cy = L.y + L.padY + i * L.lh + L.lh / 2;
    const x0 = s.align === 'left' ? L.x + L.padX : s.align === 'right' ? L.x + L.w - L.padX - row.w : L.x + (L.w - row.w) / 2;
    for (const pass of ['outline', 'fill']) {
      if (pass === 'outline' && !s.outline_width) continue;
      let x = x0;
      for (const wd of row.words) {
        ctx.font = fontSpec(wd.partial);
        const look = wordLook(wd, now);
        ctx.globalAlpha = a * look.a;
        if (pass === 'outline') {
          ctx.lineJoin = 'round'; ctx.lineWidth = s.outline_width * 2; ctx.strokeStyle = s.outline_color;
          ctx.shadowColor = s.outline_color; ctx.shadowBlur = s.outline_width * 2;
          ctx.strokeText(wd.text, x, cy);
          ctx.shadowBlur = 0;
        } else {
          ctx.fillStyle = look.color;
          ctx.fillText(wd.text, x, cy);
        }
        x += wd.w + L.space;
      }
    }
  });
  ctx.globalAlpha = 1;
}
function badgeOn() { return style && style.show_indicator && status && BADGE_STATES.includes(status.state); }
function renderIndicator() {
  const on = badgeOn();
  ind.style.display = on ? 'inline-flex' : 'none';
  if (!on) return;
  indText.textContent = status.state_label;
  mic.style.color = status.state_color;
  mic.classList.toggle('pulse', status.state === 'recording');
  placeBadge();
}
function placeBadge() {
  if (!badgeOn() || !current) return;
  const L = current, iw = ind.offsetWidth, ih = ind.offsetHeight, gap = 0.4 * style.font_size;
  const left = style.align === 'left' ? L.x : style.align === 'right' ? L.x + L.w - iw : (W - iw) / 2;
  let top = L.y - gap - ih;
  if (top < 0) top = L.y + L.h + gap;
  ind.style.transform = `translate(${Math.round(left)}px, ${Math.round(top)}px)`;
}
const VERT = `
  attribute vec2 a_position;
  varying vec2 v_uv;
  void main() {
    gl_Position = vec4(a_position, 0.0, 1.0);
    v_uv = a_position * 0.5 + 0.5;
    v_uv.y = 1.0 - v_uv.y;
  }`;
const FRAG = `
  precision mediump float;
  varying vec2 v_uv;
  uniform sampler2D u_tex;
  uniform vec2 u_res;
  uniform int u_count;
  uniform vec3 u_ripples[${MAX_RIPPLES}];
  uniform vec3 u_colors[${MAX_RIPPLES}];
  uniform float u_alphas[${MAX_RIPPLES}];
  uniform float u_strength;
  uniform float u_glow;
  void main() {
    vec2 uv = v_uv;
    vec2 distort = vec2(0.0);
    vec3 neon = vec3(0.0);
    float ring = 0.0;
    float aspect = u_res.x / u_res.y;
    for (int i = 0; i < ${MAX_RIPPLES}; i++) {
      if (i >= u_count) break;
      vec2 center = u_ripples[i].xy / u_res;
      float radius = u_ripples[i].z / u_res.y;
      float a = u_alphas[i];
      vec2 p = uv - center;
      p.x *= aspect;
      float dist = length(p);
      float ringDist = abs(dist - radius);
      if (ringDist < 0.06) {
        float influence = smoothstep(0.06, 0.0, ringDist);
        vec2 dir = p / (dist + 0.0001);
        distort += dir * sin((dist - radius) * 80.0) * influence * 0.015 * a * u_strength;
        if (ringDist < 0.01) {
          float g = smoothstep(0.01, 0.0, ringDist) * a * u_glow;
          neon += u_colors[i] * g;
          ring += g;
        }
      }
    }
    distort.x /= aspect;
    vec4 t = texture2D(u_tex, uv + distort);
    gl_FragColor = vec4(t.rgb + neon, max(t.a, clamp(ring, 0.0, 1.0)));
  }`;
let gl = null, U = {}, tex = null;
function initGL() {
  try { gl = fx.getContext('webgl', {premultipliedAlpha: true, alpha: true, antialias: false}); } catch (e) { gl = null; }
  if (!gl) return false;
  const sh = (type, src) => { const s = gl.createShader(type); gl.shaderSource(s, src); gl.compileShader(s); return s; };
  const prog = gl.createProgram();
  gl.attachShader(prog, sh(gl.VERTEX_SHADER, VERT));
  gl.attachShader(prog, sh(gl.FRAGMENT_SHADER, FRAG));
  gl.linkProgram(prog);
  if (!gl.getProgramParameter(prog, gl.LINK_STATUS)) { console.warn(gl.getProgramInfoLog(prog)); gl = null; return false; }
  gl.useProgram(prog);
  const buf = gl.createBuffer();
  gl.bindBuffer(gl.ARRAY_BUFFER, buf);
  gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1,-1, 1,-1, -1,1, -1,1, 1,-1, 1,1]), gl.STATIC_DRAW);
  const loc = gl.getAttribLocation(prog, 'a_position');
  gl.enableVertexAttribArray(loc);
  gl.vertexAttribPointer(loc, 2, gl.FLOAT, false, 0, 0);
  tex = gl.createTexture();
  gl.bindTexture(gl.TEXTURE_2D, tex);
  for (const [k, v] of [[gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE], [gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE],
                        [gl.TEXTURE_MIN_FILTER, gl.LINEAR], [gl.TEXTURE_MAG_FILTER, gl.LINEAR]]) gl.texParameteri(gl.TEXTURE_2D, k, v);
  gl.pixelStorei(gl.UNPACK_PREMULTIPLY_ALPHA_WEBGL, true);
  for (const n of ['u_res', 'u_count', 'u_ripples', 'u_colors', 'u_alphas', 'u_strength', 'u_glow']) U[n] = gl.getUniformLocation(prog, n);
  gl.clearColor(0, 0, 0, 0);
  return true;
}
class Ripple {
  constructor(x, y, volume) {
    this.x = x; this.y = y; this.radius = 0; this.alpha = 1;
    this.maxRadius = Math.max(fx.width, fx.height) * 0.15;
    this.speed = (0.2 + volume * 0.01) * 60 * dpr;          // px per second (visualizer: per frame @60 fps)
    this.whiten = Math.min(1, volume / 255) * 0.6;           // louder = whiter, like the visualizer
  }
  update(dt) { this.radius += this.speed * dt; this.alpha = Math.max(0, 1 - this.radius / this.maxRadius); }
}
let ripples = [], lastSound = 0, lastRipple = 0, spawnX = 0, spawnY = 0, glStale = true, hadRipples = false;
const ripF = new Float32Array(MAX_RIPPLES * 3), colF = new Float32Array(MAX_RIPPLES * 3), alpF = new Float32Array(MAX_RIPPLES);
function levelToVolume(rms) {      // mic RMS -> 0..255 like the visualizer's frequency average
  const db = 20 * Math.log10(Math.max(rms, 1e-6));
  return Math.max(0, Math.min(255, (db + 55) * 3.5));
}
function pickSpawn() {
  if (style.wave_area === 'screen' || !current) {
    spawnX = (100 + Math.random() * Math.max(1, W - 200)) * dpr;
    spawnY = (100 + Math.random() * Math.max(1, H - 200)) * dpr;
  } else {                                                    // somewhere on the subtitle box
    spawnX = (current.x + Math.random() * current.w) * dpr;
    spawnY = (current.y + Math.random() * current.h) * dpr;
  }
}
function updateRipples(now, dt) {
  const vol = levelToVolume(level);
  if (status && status.state === 'recording' && vol > 8) {
    if (now - lastSound > 200) pickSpawn();
    lastSound = now;
    if (now - lastRipple > 300) {
      ripples.push(new Ripple(spawnX, spawnY, vol));
      lastRipple = now;
      if (ripples.length > MAX_RIPPLES) ripples.shift();
    }
  }
  ripples.forEach(r => r.update(dt));
  ripples = ripples.filter(r => r.alpha > 0);
}
function renderGL(upload) {          // upload = the text layer changed (a GPU-to-GPU copy, no read-back)
  if (upload) {
    gl.bindTexture(gl.TEXTURE_2D, tex);
    gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, gl.RGBA, gl.UNSIGNED_BYTE, plain);
  }
  alpF.fill(0);
  const base = rgb01(style.wave_color);                       // read every frame, so colour changes apply live
  ripples.forEach((r, i) => {
    ripF[i*3] = r.x; ripF[i*3+1] = r.y; ripF[i*3+2] = r.radius;
    for (let c = 0; c < 3; c++) colF[i*3+c] = base[c] + (1 - base[c]) * r.whiten;
    alpF[i] = r.alpha;
  });
  gl.uniform2f(U.u_res, fx.width, fx.height);
  gl.uniform1i(U.u_count, ripples.length);
  gl.uniform3fv(U.u_ripples, ripF);
  gl.uniform3fv(U.u_colors, colF);
  gl.uniform1fv(U.u_alphas, alpF);
  gl.uniform1f(U.u_strength, style.wave_strength);
  gl.uniform1f(U.u_glow, style.wave_mode === 'blue' ? 1.0 : 0.0);
  gl.clear(gl.COLOR_BUFFER_BIT);
  gl.drawArrays(gl.TRIANGLES, 0, 6);
}
// Drawing only happens while something moves, at most 30 times a second, and stops completely when the
// subtitles are still: OBS, the game and the stream encoder keep the GPU.
const FRAME_MS = 1000 / 30, DOTS_MS = 100;
let lastT = 0, lastDraw = 0, lastDots = 0, running = false, waves = null;
function redraw() { dirty = true; kick(); }
function kick() { if (!running) { running = true; requestAnimationFrame(frame); } }
function wavesOn() { return glOK && style && style.wave_mode !== 'off'; }
function frame(now) {
  if (now - lastDraw < FRAME_MS - 2) { requestAnimationFrame(frame); return; }
  const dt = lastT ? Math.min(0.1, (now - lastT) / 1000) : 0; lastT = lastDraw = now;
  if (!style) { running = false; lastT = 0; return; }
  let changed = false;
  if (dirty) {
    dirty = false; changed = true;
    current = layout();
    if (current.rows.length) drawn = current;
    placeBadge();
  }
  const target = current && current.rows.length ? 1 : 0;
  if (alpha !== target) {
    alpha = target > alpha ? Math.min(1, alpha + dt / FADE_S) : Math.max(0, alpha - dt / FADE_S);
    changed = true;
  }
  for (const [k, e] of effects) if (now - e.t > FX_MS[e.kind]) effects.delete(k);
  const dots = !!current && current.rows.some(r => r.words.some(w => w.key === 'dots'));
  if (effects.size > 0) changed = true;
  else if (dots && now - lastDots >= DOTS_MS) { changed = true; lastDots = now; }   // the pulsing dots: ~10 fps is plenty
  if (changed) draw(drawn, alpha, now);
  const w = wavesOn();
  if (w !== waves) { waves = w; plain.style.display = w ? 'none' : 'block'; fx.style.display = w ? 'block' : 'none'; glStale = true; }
  const listening = w && status && status.state === 'recording';
  if (w) {
    updateRipples(now, dt);
    if (changed || glStale || ripples.length || hadRipples) renderGL(changed || glStale);
    hadRipples = ripples.length > 0;
    glStale = false;
  } else ripples = [];
  if (dirty || alpha !== target || effects.size > 0 || dots || ripples.length || listening) requestAnimationFrame(frame);
  else { running = false; lastT = 0; }       // nothing moves: stop until the next update arrives
}
function hideNow() {
  if (lines.length) minId = lines[lines.length - 1][0] + 1;
  hiddenPartial = part;
  redraw();
}
function previewRipple(prev, s) {
  if (!prev || s.wave_mode === 'off') return;
  const keys = ['wave_mode', 'wave_color', 'wave_strength', 'wave_area'];
  if (!keys.some(k => prev[k] !== s[k])) return;
  pickSpawn();
  ripples.push(new Ripple(spawnX, spawnY, 90));
  if (ripples.length > MAX_RIPPLES) ripples.shift();
  kick();
}
const glOK = initGL();
resize();
// A link can carry its own layout, e.g. /overlay?font_size=44&margin=520 for a vertical TikTok canvas: those values
// win over the control page's, for this overlay only (text size, lines, position and width).
const OWN = {}, LIMITS = {font_size: [8, 200], margin: [0, 1800], max_width: [20, 100], max_lines: [1, 3]};
new URLSearchParams(location.search).forEach((v, k) => {
  if (LIMITS[k] && v !== '' && isFinite(+v)) OWN[k] = Math.round(Math.max(LIMITS[k][0], Math.min(LIMITS[k][1], +v)));
  else if (k === 'position' && ['top', 'middle', 'bottom'].includes(v)) OWN[k] = v;
  else if (k === 'align' && ['left', 'center', 'right'].includes(v)) OWN[k] = v;
});
on('style', s => {
  const prev = style;
  s = Object.assign({}, s, OWN);
  style = s;
  previewRipple(prev, s);
  loadFont();
  ind.style.fontFamily = `"${s.font_family}", Arial, sans-serif`;
  ind.style.fontSize = Math.max(14, Math.round(s.font_size * 0.4)) + 'px';
  ind.style.color = s.color;
  ind.style.background = rgba(s.bg_color, Math.max(s.bg_opacity, 0.45));
  glStale = true;
  redraw();
  renderIndicator();
});
on('status', s => { status = s; renderIndicator(); if (wavesOn() && s.state === 'recording') kick(); });
on('level', v => { level = +v || 0; });
on('subtitle', d => {
  const changed = JSON.stringify(d.lines) !== JSON.stringify(lines) || d.partial !== part;
  if (changed && style) noteChanges(lines, part, d.lines, d.partial);
  lines = d.lines; part = d.partial; stage = d.stage || 'draft';
  if (changed && (part || d.lines.some(l => l[0] >= minId))) {
    if (part !== hiddenPartial) hiddenPartial = null;
    clearTimeout(hideTimer);
    if (style && style.hide_after > 0) hideTimer = setTimeout(hideNow, style.hide_after * 1000);
  }
  redraw();
});
</script>
</body>
</html>
"""

CONTROL_HTML = r"""<!DOCTYPE html>
<html lang="en" data-theme="{{ ui.theme }}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{{ modules[dock] ~ ' · ' if dock }}Live Translator</title>
<style>
  :root { --bg:#14161a; --bg-img:none; --panel:#1d2026; --line:#2e323a; --text:#e8e8ea; --muted:#9aa0aa; --accent:#3b82f6;
          --field:#101216; --btn:#2a2e36; --seg-on:#242a35; --on-bg:#1f3a2c; --on-line:#2f6b4c; --radius:10px;
          --blur:none; --shadow:none; --check1:#2a2d33; --check2:#23262b; --font:"Segoe UI", Roboto, Arial, sans-serif;
          color-scheme:dark; }
  /* ---- themes (the picker at the top; every pop-out and OBS dock follows it) ---- */
  /* Glass panels are tinted, not blurred: blurring the starry sky would smear stars into grey spots, and the
     twinkle would make the browser re-blur every panel on every frame (GPU work that belongs to the game). */
  [data-theme="glass"] { --bg:#000; --line:rgba(255,255,255,.16); --text:#f5f7ff; --muted:#c3c8dc;
          --panel:linear-gradient(150deg, rgba(255,255,255,.10), rgba(255,255,255,.03) 45%, rgba(255,255,255,.06)), rgba(12,12,18,.9);
          --accent:#a78bfa; --field:#060609; --btn:rgba(255,255,255,.09); --seg-on:rgba(255,255,255,.18);
          --on-bg:rgba(52,211,153,.22); --on-line:rgba(110,231,183,.5); --radius:18px; --blur:none;
          --shadow:0 8px 32px rgba(0,0,0,.6), inset 0 1px 0 rgba(255,255,255,.14); --check1:rgba(255,255,255,.08); --check2:rgba(255,255,255,.03); }
  /* black night sky: tiny white stars (a few of them twinkle) behind the glass */
  [data-theme="glass"] body::before, [data-theme="glass"] body::after { content:""; position:fixed; inset:0; z-index:-1; pointer-events:none; }
  [data-theme="glass"] body::before { background-image:
      radial-gradient(1px 1px at 82px 38px, rgba(255,255,255,0.9), transparent),
      radial-gradient(1px 1px at 101px 12px, rgba(255,255,255,0.9), transparent),
      radial-gradient(1px 1px at 18px 24px, rgba(255,255,255,0.9), transparent),
      radial-gradient(1px 1px at 93px 14px, rgba(255,255,255,0.9), transparent),
      radial-gradient(1px 1px at 129px 54px, rgba(255,255,255,0.9), transparent),
      radial-gradient(1px 1px at 9px 22px, rgba(255,255,255,0.9), transparent),
      radial-gradient(1px 1px at 111px 107px, rgba(255,255,255,0.9), transparent),
      radial-gradient(1.5px 1.5px at 17px 61px, rgba(255,255,255,0.8), transparent),
      radial-gradient(1.5px 1.5px at 23px 141px, rgba(255,255,255,0.8), transparent),
      radial-gradient(1.5px 1.5px at 108px 15px, rgba(255,255,255,0.8), transparent),
      radial-gradient(1.5px 1.5px at 144px 31px, rgba(255,255,255,0.8), transparent),
      radial-gradient(1.5px 1.5px at 57px 161px, rgba(255,255,255,0.8), transparent),
      radial-gradient(1.5px 1.5px at 160px 149px, rgba(255,255,255,0.8), transparent),
      radial-gradient(2px 2px at 31px 203px, rgba(255,255,255,0.95), transparent),
      radial-gradient(2px 2px at 25px 113px, rgba(255,255,255,0.95), transparent),
      radial-gradient(2px 2px at 23px 285px, rgba(255,255,255,0.95), transparent),
      radial-gradient(2px 2px at 68px 148px, rgba(255,255,255,0.95), transparent),
      radial-gradient(1px 1px at 53px 18px, rgba(255,255,255,0.45), transparent),
      radial-gradient(1px 1px at 69px 15px, rgba(255,255,255,0.45), transparent),
      radial-gradient(1px 1px at 73px 39px, rgba(255,255,255,0.45), transparent),
      radial-gradient(1px 1px at 71px 87px, rgba(255,255,255,0.45), transparent),
      radial-gradient(1px 1px at 23px 13px, rgba(255,255,255,0.45), transparent);
    background-size:131px 131px, 131px 131px, 131px 131px, 131px 131px, 131px 131px, 131px 131px, 131px 131px, 197px 197px, 197px 197px, 197px 197px, 197px 197px, 197px 197px, 197px 197px, 293px 293px, 293px 293px, 293px 293px, 293px 293px, 89px 89px, 89px 89px, 89px 89px, 89px 89px, 89px 89px; }
  [data-theme="glass"] body::after { background-image:
      radial-gradient(2px 2px at 148px 146px, rgba(255,255,255,1), transparent),
      radial-gradient(2px 2px at 163px 48px, rgba(255,255,255,1), transparent),
      radial-gradient(2px 2px at 95px 24px, rgba(255,255,255,1), transparent),
      radial-gradient(2px 2px at 140px 16px, rgba(255,255,255,1), transparent),
      radial-gradient(2.5px 2.5px at 144px 15px, rgba(255,255,255,1), transparent),
      radial-gradient(2.5px 2.5px at 158px 52px, rgba(255,255,255,1), transparent),
      radial-gradient(2.5px 2.5px at 127px 174px, rgba(255,255,255,1), transparent);
    background-size:173px 173px, 173px 173px, 173px 173px, 173px 173px, 251px 251px, 251px 251px, 251px 251px; animation:twinkle 3.5s ease-in-out infinite alternate; }
  @keyframes twinkle { from { opacity:.15; } to { opacity:1; } }
  @media (prefers-reduced-motion: reduce) { [data-theme="glass"] body::after { animation:none; opacity:.7; } }
  [data-theme="light"] { --bg:#f3f4f7; --panel:#ffffff; --line:#dde1e8; --text:#1b1f27; --muted:#5f6775; --accent:#2563eb;
          --field:#f7f8fa; --btn:#eef0f4; --seg-on:#ffffff; --on-bg:#dcfce7; --on-line:#86efac; --shadow:0 1px 3px rgba(16,24,40,.08);
          --check1:#e5e7eb; --check2:#d6d9de; color-scheme:light; }
  [data-theme="neon"] { --bg:#07070d; --panel:#0e0e1a; --line:#2b2050; --text:#e6fbff; --muted:#8f94c2; --accent:#00f0ff;
          --field:#05050a; --btn:#161630; --seg-on:#22224a; --on-bg:#0b3340; --on-line:#00f0ff; --radius:4px;
          --shadow:0 0 0 1px rgba(0,240,255,.10), 0 0 26px rgba(255,43,214,.13); --check1:#141428; --check2:#0c0c1a;
          --font:Consolas, "Cascadia Mono", "Segoe UI", monospace;
          --bg-img:linear-gradient(rgba(255,43,214,.06) 1px, transparent 1px), linear-gradient(90deg, rgba(0,240,255,.06) 1px, transparent 1px); }
  [data-theme="sakura"] { --bg:#fff4f8; --panel:rgba(255,255,255,.82); --line:#f6cfe0; --text:#4a2b3a; --muted:#9b6b82; --accent:#ec4899;
          --field:#fffafc; --btn:#fde6f0; --seg-on:#ffffff; --on-bg:#e3f9ee; --on-line:#9be3bf; --radius:16px;
          --shadow:0 4px 18px rgba(236,72,153,.10); --check1:#fbe3ee; --check2:#f7d3e3; color-scheme:light;
          --bg-img:radial-gradient(50vw 40vw at 0% 0%, #ffd9e8, transparent 65%), radial-gradient(50vw 40vw at 100% 100%, #e9ddff, transparent 65%); }
  [data-theme="midnight"] { --bg:#000; --panel:#0b0b12; --line:#1f1b2e; --text:#ece9f5; --muted:#8e88a3; --accent:#8b5cf6;
          --field:#050508; --btn:#15121f; --seg-on:#1e1930; --on-bg:#1a2b22; --on-line:#2f6b4c; --radius:12px; --check1:#121018; --check2:#0a0910; }
  * { box-sizing: border-box; }
  body { margin:0; min-height:100vh; font-family:var(--font); background:var(--bg-img), var(--bg); background-attachment:fixed; color:var(--text); }
  [data-theme="neon"] body { background-size:32px 32px, 32px 32px, auto; }
  header { max-width:1400px; margin:0 auto; padding:20px 20px 0; display:flex; align-items:center; justify-content:space-between; gap:12px; flex-wrap:wrap; }
  header h1 { font-size:18px; margin:0; font-weight:600; }
  header .url { font-size:12px; color:var(--muted); }
  header .tools { display:flex; align-items:center; gap:8px; font-size:13px; color:var(--muted); }
  header .tools select { width:auto; }
  [data-theme="neon"] header h1 { color:var(--accent); text-shadow:0 0 12px rgba(0,240,255,.6); }
  main { max-width:1400px; margin:0 auto; padding:16px 20px 20px; display:grid; grid-template-columns:repeat(auto-fill, minmax(340px, 1fr));
         grid-auto-flow:row dense; gap:16px; align-items:start; }
  section { background:var(--panel); border:1px solid var(--line); border-radius:var(--radius); padding:16px; min-width:0;
            box-shadow:var(--shadow); backdrop-filter:var(--blur); -webkit-backdrop-filter:var(--blur); }
  section.wide { grid-column:span 2; }
  @media (max-width: 760px) { section.wide { grid-column:auto; } }
  h2 { font-size:12px; margin:0; text-transform:uppercase; letter-spacing:.08em; color:var(--muted); font-weight:600; flex:1; min-width:0;
       white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
  /* ---- module title bar: drag handle, fold, wide, pop out ---- */
  .modhead { display:flex; align-items:center; gap:6px; margin:-6px -6px 12px; }
  .modhead .grip { cursor:grab; padding:2px 6px; background:none; border:1px solid transparent; color:var(--muted); font-size:15px; line-height:1; letter-spacing:-2px; }
  .modhead .tool { padding:3px 7px; font-size:13px; line-height:1; background:transparent; border-color:transparent; color:var(--muted); }
  .modhead .tool:hover, .modhead .grip:hover { border-color:var(--line); color:var(--text); }
  section.collapsed .modhead { margin-bottom:-6px; }
  section.collapsed > :not(.modhead), section.popped > :not(.modhead):not(.popnote) { display:none !important; }
  main.sorting iframe { pointer-events:none; }
  section.dragging { opacity:.45; outline:2px dashed var(--accent); outline-offset:3px; }
  .popnote { display:none; font-size:13px; color:var(--muted); align-items:center; justify-content:space-between; gap:10px; }
  section.popped .popnote { display:flex; }
  label { display:block; font-size:13px; color:var(--muted); margin:12px 0 5px; }
  label.check { display:flex; align-items:center; gap:8px; color:var(--text); }
  select, input[type=text], input[type=number] { width:100%; padding:7px 8px; background:var(--field); color:var(--text); border:1px solid var(--line); border-radius:6px; font-family:inherit; }
  select option, select optgroup { background:var(--bg); color:var(--text); }
  input[type=color] { width:44px; height:30px; border:1px solid var(--line); background:none; padding:0; border-radius:4px; }
  input[type=range] { width:100%; accent-color:var(--accent); }
  input[type=checkbox] { accent-color:var(--accent); }
  .row { display:flex; gap:10px; align-items:end; flex-wrap:wrap; }
  .row > * { flex:1; }
  .row .fixed { flex:0 0 auto; }
  button { padding:7px 12px; background:var(--btn); color:var(--text); border:1px solid var(--line); border-radius:6px; cursor:pointer; font-weight:600; font-family:inherit; }
  button:hover { border-color:var(--accent); }
  code { background:var(--field); padding:2px 6px; border-radius:4px; }
  .val { color:var(--text); font-variant-numeric:tabular-nums; }
  .indicator { display:flex; align-items:center; gap:14px; padding:14px 16px; border-radius:12px; background:var(--field); border:1px solid var(--line); transition:border-color .25s; }
  .indicator .mic { position:relative; width:44px; height:44px; border-radius:50%; flex:0 0 auto; display:grid; place-items:center;
                    color:var(--muted); background:color-mix(in srgb, currentColor 16%, transparent); transition:color .25s; }
  .indicator .mic svg { width:24px; height:24px; }
  .indicator.recording .mic::after { content:""; position:absolute; inset:0; border-radius:50%; border:2px solid currentColor; animation:ping 1.2s ease-out infinite; }
  .indicator .label { font-size:19px; font-weight:700; transition:color .25s; }
  .indicator .hint { font-size:13px; color:var(--muted); margin-top:3px; }
  @keyframes ping { 0% { transform:scale(.85); opacity:.9; } 100% { transform:scale(1.45); opacity:0; } }
  .microw { display:flex; gap:8px; margin-top:14px; }
  .microw select { flex:1; min-width:0; }
  .power { display:flex; gap:8px; margin-top:8px; }
  .power button { flex:1; padding:9px 12px; }
  .power button.on { background:var(--on-bg); border-color:var(--on-line); }
  button.danger:hover { border-color:#f87171; color:#ff8a8a; }
  .meter { height:8px; background:var(--field); border-radius:4px; overflow:hidden; margin-top:10px; }
  .meter div { height:100%; width:0; background:linear-gradient(90deg,#22c55e,#eab308,#ef4444); transition:width .1s; }
  .stats { font-size:12px; color:var(--muted); margin-top:8px; }
  .stats .err, .note .err { color:#f87171; display:block; margin-top:4px; }
  .mtstate { margin-top: 8px; font-size: 13px; padding: 7px 10px; border-radius: 8px; background: #2a2412; color: #ffd27a; }
  .mtstate.ok { background: #12261c; color: #6ee7a8; }
  .mtstate.bad { background: #2c1518; color: #ff9aa5; }
  [data-theme="light"] .mtstate, [data-theme="sakura"] .mtstate { background:#fff4d6; color:#8a5a00; }
  [data-theme="light"] .mtstate.ok, [data-theme="sakura"] .mtstate.ok { background:#dcfce7; color:#166534; }
  [data-theme="light"] .mtstate.bad, [data-theme="sakura"] .mtstate.bad { background:#fee2e2; color:#991b1b; }
  .stats .notice { color:#fbbf24; display:block; margin-top:4px; }
  .langrow { display:flex; gap:8px; align-items:end; margin-top:4px; }
  .langrow > div { flex:1; min-width:0; }
  .langrow button { flex:0 0 auto; height:33px; }
  .seg { display:flex; gap:4px; padding:4px; background:var(--field); border:1px solid var(--line); border-radius:10px; }
  .seg button { flex:1; background:transparent; border:1px solid transparent; color:var(--muted); padding:7px 6px; }
  .seg button[aria-pressed="true"] { background:var(--seg-on); border-color:var(--line); color:var(--text); }
  [data-theme="neon"] .seg button[aria-pressed="true"] { border-color:var(--accent); box-shadow:0 0 10px rgba(0,240,255,.35); }
  .swatches { display:flex; flex-wrap:wrap; gap:8px; align-items:center; }
  .swatch { width:30px; height:30px; padding:0; border-radius:50%; border:2px solid transparent; background:var(--c); box-shadow:inset 0 0 0 2px rgba(0,0,0,.25); }
  .swatch[aria-pressed="true"] { border-color:var(--text); box-shadow:0 0 0 3px color-mix(in srgb, var(--c) 45%, transparent); }
  .swatches input[type=color] { width:30px; height:30px; border-radius:50%; overflow:hidden; cursor:pointer; }
  .swatches input[type=color]::-webkit-color-swatch-wrapper { padding:0; }
  .swatches input[type=color]::-webkit-color-swatch { border:none; border-radius:50%; }
  .note { font-size:12px; color:var(--muted); margin-top:8px; line-height:1.45; }
  .note b { font-weight:600; }
  .preview { position:relative; height:300px; border-radius:6px; overflow:hidden; background:repeating-conic-gradient(var(--check1) 0% 25%, var(--check2) 0% 50%) 50% / 24px 24px; }
  .preview iframe { position:absolute; inset:0; width:100%; height:100%; border:0; color-scheme:normal; }   /* keeps the overlay see-through in dark looks */
  .log { height:220px; overflow:auto; background:var(--field); border:1px solid var(--line); border-radius:6px; padding:8px 10px; font-size:14px; line-height:1.45; }
  .log .p { color:var(--muted); font-style:italic; }
  /* ---- one module on its own: pop-out windows and OBS docks ---- */
  body.dock header, body.dock .modhead { display:none; }
  body.dock main { display:block; max-width:none; padding:8px; }
  body.dock section { display:none; }
  body.dock section.shown { display:block; }
  body.dock .preview { height:calc(100vh - 50px); min-height:160px; }
  body.dock .log { height:calc(100vh - 50px); min-height:120px; }
</style>
</head>
<body class="{{ 'dock' if dock }}">
<header>
  <h1 id="title">Live Translator</h1>
  <div class="url">OBS Browser Source: <code>{{ overlay_url }}</code></div>
  <div class="tools">
    <label for="theme" style="margin:0">Look</label>
    <select id="theme">{% for k, v in themes.items() %}<option value="{{ k }}">{{ v }}</option>{% endfor %}</select>
    <button type="button" id="layout_reset" title="Put every module back where it started">Reset layout</button>
  </div>
</header>
<main id="grid">
    <section data-mod="status">
      <div class="indicator" id="indicator">
        <span class="mic" id="ind-mic"><svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
          <rect x="8.5" y="2.5" width="7" height="12" rx="3.5"/>
          <path d="M5.5 11a6.5 6.5 0 0 0 13 0M12 17.5V21M8.5 21h7" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
        </svg></span>
        <div><div class="label" id="ind-label">Connecting</div><div class="hint" id="ind-hint">Waking the translator up...</div></div>
      </div>
      <div class="microw">
        <select id="mic" aria-label="Microphone"></select>
        <button id="rescan" title="Look for microphones again">&#x21bb;</button>
        <button id="clear">Clear</button>
      </div>
      <div class="power">
        <button id="pause" title="Closes the microphone until you press it again">&#x23F8; Stop listening</button>
        <button id="quit" class="danger" title="Closes the translator completely">&#x23FB; Turn off</button>
      </div>
      <div class="meter"><div id="lvl"></div></div>
      {% if gpu_slider %}<label for="gpu_limit">Max GPU use <span class="val" id="gpu_limit_v"></span>%</label>
      <input type="range" id="gpu_limit" min="10" max="100" step="5" title="Lower = smoother games, slower subtitles">{% endif %}
      <div class="stats" id="stats"></div>
    </section>
    <section data-mod="languages">
      <div class="langrow">
        <div><label for="lang_a" id="lang_a_label">Spoken</label><select id="lang_a"></select></div>
        <button type="button" id="lang_swap" title="Swap the two languages">&#x21c4;</button>
        <div><label for="lang_b" id="lang_b_label">Subtitles in</label><select id="lang_b"></select></div>
      </div>
      <div class="note" id="lang_note"></div>
      <div class="mtstate" id="lang_mt" hidden></div>
      <label>Speech model</label>
      <div class="seg" id="speech_size" role="group" aria-label="Speech model size">
        <button type="button" data-v="auto" title="Picks the model that fits the languages and your graphics card">Auto</button>
        {% for k in speech_sizes %}<button type="button" data-v="{{ k }}">{{ k|capitalize }}</button>{% endfor %}
      </div>
      <div class="note" id="speech_note"></div>
    </section>
    <section data-mod="subtitles">
      <label style="margin-top:0">Text size <span class="val" id="font_size_v"></span></label>
      <input type="range" id="font_size" min="20" max="80" data-style>
      <div class="row">
        <div><label>Lines</label><div class="seg" data-field="max_lines">
          <button type="button" data-v="1">1</button><button type="button" data-v="2">2</button><button type="button" data-v="3">3</button></div></div>
        <div><label>Position</label><div class="seg" data-field="position">
          <button type="button" data-v="bottom">Bottom</button><button type="button" data-v="middle">Middle</button><button type="button" data-v="top">Top</button></div></div>
      </div>
      <label>While she talks, show</label>
      <div class="seg" data-field="progress">
        <button type="button" data-v="full">Drafts + fixes</button>
        <button type="button" data-v="drafts">Drafts</button>
        <button type="button" data-v="final">Finished only</button>
      </div>
      <div class="note"><b>Drafts</b> appear in a softer colour with &bull;&bull;&bull; while she's speaking.
        <b>Fixes</b> flash when the translator corrects a word, then the line turns white when it's final.</div>
    </section>
    <section data-mod="waves">
      <div class="seg" data-field="wave_mode">
        <button type="button" data-v="blue">Glowing</button>
        <button type="button" data-v="clear">See-through</button>
        <button type="button" data-v="off">Off</button>
      </div>
      <label>Ripple colour</label>
      <div class="swatches" id="wave_swatches">
        <button type="button" class="swatch" style="--c:#0096ff" data-color="#0096ff" title="Ocean blue"></button>
        <button type="button" class="swatch" style="--c:#38e1ff" data-color="#38e1ff" title="Aqua"></button>
        <button type="button" class="swatch" style="--c:#a78bfa" data-color="#a78bfa" title="Lavender"></button>
        <button type="button" class="swatch" style="--c:#ff7eb6" data-color="#ff7eb6" title="Sakura pink"></button>
        <button type="button" class="swatch" style="--c:#fb923c" data-color="#fb923c" title="Peach"></button>
        <button type="button" class="swatch" style="--c:#34d399" data-color="#34d399" title="Mint"></button>
        <button type="button" class="swatch" style="--c:#ffffff" data-color="#ffffff" title="White"></button>
        <input type="color" id="wave_color" title="Any colour" data-style>
      </div>
    </section>
    <section data-mod="look">
      <label style="margin-top:0">Font</label>
      <select id="font_family">
        {% if local_fonts %}<optgroup label="Your font files (fonts folder)">{% for f in local_fonts %}<option>{{ f }}</option>{% endfor %}</optgroup>{% endif %}
        <optgroup label="Installed on Windows">{% for f in system_fonts %}<option>{{ f }}</option>{% endfor %}</optgroup>
      </select>
      <label>Or type any font installed on this PC (other fonts: put the .ttf / .otf file in the fonts folder)</label>
      <input type="text" id="custom_font" placeholder="e.g. Segoe UI Black">
      <label>Weight</label>
      <select id="font_weight" data-style><option value="400">Normal</option><option value="600">Semi-bold</option><option value="700">Bold</option><option value="900">Black</option></select>
      <div class="row">
        <div class="fixed"><label>Text</label><input type="color" id="color" data-style></div>
        <div class="fixed"><label>Drafts</label><input type="color" id="partial_color" data-style></div>
        <div class="fixed"><label>Fixes</label><input type="color" id="fix_color" data-style></div>
        <div class="fixed"><label>Outline</label><input type="color" id="outline_color" data-style></div>
        <div class="fixed"><label>Box</label><input type="color" id="bg_color" data-style></div>
      </div>
      <div class="row">
        <div><label>Outline <span class="val" id="outline_width_v"></span>px</label><input type="range" id="outline_width" min="0" max="10" data-style></div>
        <div><label>Box opacity <span class="val" id="bg_opacity_v"></span></label><input type="range" id="bg_opacity" min="0" max="1" step="0.05" data-style></div>
      </div>
      <label class="check"><input type="checkbox" id="italic_partial" data-style> Drafts in italic</label>
      <div class="row">
        <div><label>Align</label><select id="align" data-style><option>center</option><option>left</option><option>right</option></select></div>
        <div><label>Hide after (s, 0 = never)</label><input type="number" id="hide_after" min="0" max="300" step="1" data-style></div>
      </div>
      <div class="row">
        <div><label>Edge margin <span class="val" id="margin_v"></span>px</label><input type="range" id="margin" min="0" max="400" data-style></div>
        <div><label>Max width <span class="val" id="max_width_v"></span>%</label><input type="range" id="max_width" min="20" max="100" data-style></div>
      </div>
      <div class="row">
        <div><label>Ripples start</label><select id="wave_area" data-style><option value="subtitles">On the subtitles</option><option value="screen">Anywhere</option></select></div>
        <div><label>Wave strength <span class="val" id="wave_strength_v"></span></label><input type="range" id="wave_strength" min="0" max="3" step="0.1" data-style></div>
      </div>
      <label class="check"><input type="checkbox" id="show_indicator" data-style> Show the "Speak now / Recording" badge in OBS</label>
    </section>
    <section data-mod="bot">
      <div class="note" style="margin-top:0">In Mix It Up, add a <b>Web Request</b> action (GET) with one of these links, e.g. to a channel point
        redeem. While stopped the mic is off and nothing runs, but everything stays loaded, so it starts again instantly.
        Keep the links private.</div>
      {% for action, label in remote_actions %}
      <label for="remote_{{ action }}">{{ label }}</label>
      <div class="row"><input type="text" readonly id="remote_{{ action }}" value="{{ remote_urls[action] }}"><button type="button" class="fixed copy" data-copy="remote_{{ action }}">Copy</button></div>
      {% endfor %}
      <button type="button" id="remote_new" class="danger" style="margin-top:12px">Make new links (the old ones stop working)</button>
    </section>
    <section data-mod="preview">
      <div class="preview">{% if not dock or dock == 'preview' %}<iframe src="/overlay" title="Live preview, exactly what OBS shows"></iframe>{% endif %}</div>
    </section>
    <section data-mod="transcript">
      <div class="log" id="log"></div>
    </section>
    <section data-mod="links">
      <div class="note" style="margin-top:0">Every module has its own link. In OBS: <b>Docks &rarr; Custom Browser Docks</b>, type a name,
        paste the link and press Apply. Or press &#x2197; on a module here to pop it out into its own window.</div>
      <label for="link_overlay">Subtitles overlay (Browser Source, 1920 &times; 1080: Twitch, YouTube)</label>
      <div class="row"><input type="text" readonly id="link_overlay" value="{{ overlay_url }}"><button type="button" class="fixed copy" data-copy="link_overlay">Copy</button></div>
      <label for="link_vertical">Subtitles overlay for a vertical canvas (Browser Source, 1080 &times; 1920: TikTok)</label>
      <div class="row"><input type="text" readonly id="link_vertical" value="{{ overlay_url }}?font_size=44&amp;margin=520"><button type="button" class="fixed copy" data-copy="link_vertical">Copy</button></div>
      <div class="note">The vertical link carries its own text size and distance from the edge (change the numbers in the link to taste;
        <code>max_lines</code>, <code>max_width</code>, <code>position</code> and <code>align</code> work too). Everything else follows the control page.</div>
      {% for m, url in dock_urls.items() if m != 'links' %}
      <label for="dock_{{ m }}">{{ modules[m] }}</label>
      <div class="row"><input type="text" readonly id="dock_{{ m }}" value="{{ url }}"><button type="button" class="fixed copy" data-copy="dock_{{ m }}">Copy</button></div>
      {% endfor %}
    </section>
</main>
<script nonce="{{ nonce }}">
const TOKEN = {{ token|tojson }};                  // made fresh every start: only this page can change settings
const bus = new EventSource('/events');           // live updates from the translator on this PC only
const on = (name, fn) => bus.addEventListener(name, e => { let d; try { d = JSON.parse(e.data); } catch (err) { return; } fn(d); });
function api(name, data) {
  return fetch('/api/' + name, {method: 'POST', headers: {'Content-Type': 'application/json', 'X-Token': TOKEN},
                                body: JSON.stringify(data ?? {}), cache: 'no-store'})
    .then(r => r.ok ? r.json() : null).catch(() => null);
}
const $ = id => document.getElementById(id);
const esc = s => String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
const INPUTS = ['font_size','font_weight','color','partial_color','fix_color','italic_partial','outline_color','outline_width',
                'bg_color','bg_opacity','align','margin','max_width','hide_after','show_indicator','wave_area','wave_color','wave_strength'];
const SEGS = [...document.querySelectorAll('.seg[data-field]')];
const SLIDER_VALUES = ['font_size','outline_width','bg_opacity','margin','max_width','wave_strength'];
let style = {}, filling = false, timer = null;
function showVals() { SLIDER_VALUES.forEach(k => $(k + '_v').textContent = $(k).value); }
function collect() {
  const s = {};
  INPUTS.forEach(k => { const el = $(k); s[k] = el.type === 'checkbox' ? el.checked : el.value; });
  SEGS.forEach(g => s[g.dataset.field] = style[g.dataset.field]);
  s.font_family = $('custom_font').value.trim() || $('font_family').value;
  return s;
}
function send() { showVals(); if (filling) return; clearTimeout(timer); timer = setTimeout(() => api('style', collect()), 120); }
function sendNow() { clearTimeout(timer); api('style', collect()); }
function mark() {
  SEGS.forEach(g => g.querySelectorAll('button').forEach(b => b.setAttribute('aria-pressed', String(b.dataset.v === String(style[g.dataset.field])))));
  const color = ($('wave_color').value || '').toLowerCase();
  document.querySelectorAll('#wave_swatches .swatch').forEach(b => b.setAttribute('aria-pressed', String(b.dataset.color === color)));
}
SEGS.forEach(g => g.querySelectorAll('button').forEach(b => b.onclick = () => { style[g.dataset.field] = b.dataset.v; mark(); sendNow(); }));
document.querySelectorAll('#wave_swatches .swatch').forEach(b => b.onclick = () => { $('wave_color').value = b.dataset.color; mark(); sendNow(); });
document.querySelectorAll('[data-style]').forEach(el => { el.addEventListener('input', send); el.addEventListener('change', send); });
$('wave_color').addEventListener('input', mark);
$('font_family').addEventListener('change', () => { $('custom_font').value = ''; send(); });
$('custom_font').addEventListener('input', send);
on('style', s => {
  filling = true;
  style = s;
  INPUTS.forEach(k => { const el = $(k); if (el.type === 'checkbox') el.checked = !!s[k]; else el.value = s[k]; });
  const opts = [...$('font_family').options].map(o => o.value);
  if (opts.includes(s.font_family)) { $('font_family').value = s.font_family; if (document.activeElement !== $('custom_font')) $('custom_font').value = ''; }
  else if (document.activeElement !== $('custom_font')) $('custom_font').value = s.font_family;
  showVals(); mark();
  filling = false;
});
function loadDevices(rescan) {
  api('devices', {rescan}).then(d => {
    if (!d || !Array.isArray(d.devices)) return;
    const sel = $('mic'); sel.innerHTML = '';
    if (d.current === null) sel.add(new Option('Choose a microphone', '', true, true));
    d.devices.forEach(dev => sel.add(new Option(dev.label, dev.index, false, dev.index === d.current)));
  });
}
bus.onopen = () => loadDevices(false);
bus.onerror = () => turnedOff || setIndicator({state: 'error', state_label: 'Translator is off', state_hint: 'Start it again and this page reconnects by itself', state_color: '#94a3b8'});
$('mic').addEventListener('change', e => { if (e.target.value !== '') api('mic', {index: e.target.value}); });
$('rescan').onclick = () => loadDevices(true);
$('clear').onclick = () => api('clear');
document.querySelectorAll('button.copy').forEach(b => b.onclick = () => {
  const el = $(b.dataset.copy);
  el.select();
  (navigator.clipboard ? navigator.clipboard.writeText(el.value) : Promise.reject()).catch(() => document.execCommand('copy'));
  b.textContent = 'Copied'; setTimeout(() => { b.textContent = 'Copy'; }, 1200);
});
$('remote_new').onclick = () => {
  if (!confirm('Make new links? The old ones stop working, so paste the new ones into Mix It Up.')) return;
  api('remote_key').then(d => { if (d && d.urls) Object.entries(d.urls).forEach(([k, v]) => { const el = $('remote_' + k); if (el) el.value = v; }); });
};
let turnedOff = false;
$('pause').onclick = () => api('listening', {paused: !status.paused});
$('quit').onclick = () => {
  if (!confirm('Turn the translator off?\n\nStart it again with its shortcut when you need it.')) return;
  turnedOff = true;
  api('quit');
  bus.close();                                     // don't keep trying to reconnect
  setIndicator({state: 'error', state_label: 'Turned off', state_hint: 'The translator is closed. You can close this tab.', state_color: '#94a3b8'});
  document.querySelectorAll('button, select, input').forEach(el => el.disabled = true);
  if (window.opener || APP_WINDOW) setTimeout(() => window.close(), 1500);   // pop-out / app window: close it too
};
function showPause(paused) {
  $('pause').innerHTML = paused ? '&#x25B6; Start listening' : '&#x23F8; Stop listening';
  $('pause').classList.toggle('on', !!paused);
}

// ---- language dial ----
const LANGS = {{ languages|tojson }};
const TEXT_EN = {{ text_to_english|tojson }};       // spoken languages that are written down first, then translated to English as text
const TUNED = {{ tuned_speech|tojson }};            // spoken languages with a speech model trained for just that language
let langs = {mode: 'one_way', a: 'sv', b: 'en'};
Object.entries(LANGS).sort((x, y) => x[1].localeCompare(y[1])).forEach(([code, name]) => {
  $('lang_a').add(new Option(name, code)); $('lang_b').add(new Option(name, code));
});
function showLangs() {
  const conv = false;
  $('lang_a').value = langs.a; $('lang_b').value = langs.b;
  $('lang_a_label').textContent = conv ? 'Person 1 speaks' : 'Spoken';
  $('lang_b_label').textContent = conv ? 'Person 2 speaks' : 'Subtitles in';
  const A = LANGS[langs.a], B = LANGS[langs.b];
  let note = conv ? `Each sentence is recognised as ${A} or ${B} and shown in the other language, marked with its code (e.g. ${langs.a.toUpperCase()} \u203a ...).`
                  : (langs.a === langs.b ? `${A} speech shown as ${A} subtitles (no translation).` : `${A} speech \u2192 ${B} subtitles.`);
  if (conv && langs.a === langs.b) note = 'Pick two different languages for a conversation.';
  if (!conv && langs.b === 'en' && TEXT_EN.includes(langs.a))
    note += ` The ${A} words are written down${TUNED.includes(langs.a) ? ` by a speech model trained for ${A}` : ''}, then translated by a text model made for ${A} \u2192 English (got ready once, about 0.5 GB; works offline after).`;
  else if (conv ? langs.a !== langs.b : langs.b !== 'en' && langs.a !== langs.b)    // other English targets come straight from Whisper
    note += ' Subtitles in a language other than English are translated by a second model on this PC: the first time it is downloaded (0.5 \u2013 1.3 GB), after that it works offline.';
  $('title').textContent = 'Live Translator \u00b7 ' + (conv ? `${A} \u21c4 ${B}` : (langs.a === langs.b ? A : `${A} \u2192 ${B}`));
  $('lang_note').textContent = note;
}
function showModelState(s) {
  const box = $('lang_mt');
  box.hidden = !s.mt_needed;                        // the translator says whether this setting uses a translation model
  if (box.hidden) return;
  const mt = s.mt || 'off';
  box.className = 'mtstate' + (mt === 'ready' ? ' ok' : mt === 'failed' ? ' bad' : '');
  box.textContent = mt === 'ready' ? `\u2713 Translation ready${s.mt_model ? ' (' + s.mt_model + ')' : ''}.` + (s.notice ? ' ' + s.notice : '')
    : (s.mt_model ? `Ready so far: ${s.mt_model}. ` : '') + (s.notice || 'Starting the translation model... until it is ready, lines stay in the language they were spoken in.');
}
function sendLangs() { showLangs(); showModelState(status); api('languages', langs); }
$('lang_a').onchange = () => { langs.a = $('lang_a').value; sendLangs(); };
$('lang_b').onchange = () => { langs.b = $('lang_b').value; sendLangs(); };
$('lang_swap').onclick = () => { [langs.a, langs.b] = [langs.b, langs.a]; sendLangs(); };

// ---- speech model size: Auto / Small / Medium / Large (SPEECH_SIZES in translator_http.py) ----
const SIZE_FIXED = {{ speech_fixed|tojson }};      // model_size set by hand in translator_http.py: the buttons are off
const SIZE_HINTS = {
  auto: 'Auto picks the model that fits the languages and your graphics card.',
  small: 'Small: the quickest and lightest (about 0.5 GB of video memory), but the most mistakes. For a heavy game or a PC without a graphics card.',
  medium: 'Medium: fewer mistakes than Small, but every pass takes about twice as long (about 1 GB of video memory).',
  large: 'Large: the fewest mistakes. Where Whisper turns the speech into English by itself, and for Swedish on its own, it is a full large model, the slowest and heaviest (2 \u2013 3.5 GB of video memory); otherwise the quick large-v3-turbo (about 1 GB).',
};
let speechSize = 'auto', sizeSent = 0;            // sizeSent: clicks the translator hasn't answered yet
function showSpeechSize(s) {
  document.querySelectorAll('#speech_size button').forEach(b => {
    b.setAttribute('aria-pressed', String(!SIZE_FIXED && b.dataset.v === speechSize));
    b.disabled = !!SIZE_FIXED;
  });
  let html = SIZE_FIXED ? `Set by hand in translator_http.py (<b>model_size = "${esc(SIZE_FIXED)}"</b>); set it to "auto" to use these buttons.`
                        : esc(SIZE_HINTS[speechSize] || '');
  const now = /^(.+) on (cuda|cpu)$/.exec(s.model || '');
  if (now) html += ` Now: <b>${esc(now[1])}</b> on the ${now[2] === 'cpu' ? 'CPU' : 'graphics card'}.`;
  else if (s.model && s.model !== 'failed') html += ` Now: ${esc(s.model)}`;
  if (now && now[2] === 'cpu' && !SIZE_FIXED && !['auto', 'small'].includes(speechSize))
    html += ' Without a graphics card a bigger model is slow: the subtitles lag behind.';
  if (!SIZE_FIXED) html += ' Switching takes a few seconds; the first time, the model is downloaded (0.5 \u2013 3 GB) and the subtitles wait for it.';
  if (s.speech_problem) html += `<span class="err">${esc(s.speech_problem)}</span>`;
  $('speech_note').innerHTML = html;
}
document.querySelectorAll('#speech_size button').forEach(b => b.onclick = () => {
  if (SIZE_FIXED || b.dataset.v === speechSize) return;
  speechSize = b.dataset.v; sizeSent++;
  showSpeechSize(status);
  api('speech_size', {value: speechSize}).then(d => {
    sizeSent--;
    if (d && d.value && !sizeSent) { speechSize = d.value; showSpeechSize(status); }
  });
});
on('level', v => { const db = 20 * Math.log10(Math.max(v, 1e-5)); $('lvl').style.width = Math.max(0, Math.min(100, (db + 60) / 60 * 100)) + '%'; });
function setIndicator(s) {
  $('indicator').className = 'indicator ' + (s.state || '');
  $('indicator').style.borderColor = s.state_color || '';
  $('ind-mic').style.color = s.state_color || '';
  $('ind-label').textContent = s.state_label || '';
  $('ind-label').style.color = s.state_color || '';
  $('ind-hint').textContent = s.state_hint || '';
}
let status = {};
on('status', update => {
  const s = status = Object.assign(status, update);    // the server sends everything, but keep old values just in case
  setIndicator(s);
  showPause(s.paused);
  if ($('gpu_limit') && document.activeElement !== $('gpu_limit') && s.gpu_limit) { $('gpu_limit').value = s.gpu_limit; $('gpu_limit_v').textContent = s.gpu_limit; }
  let html = `${esc(s.model ?? '...')} &middot; ${esc(s.updates_per_sec ?? 0)} updates/s &middot; using ${esc(s.gpu_busy ?? '-')} of the GPU`;
  if (Array.isArray(s.speed)) html += ` &middot; last pass: speech ${esc(s.speed[0])} ms` + (s.speed[1] ? ` + translation ${esc(s.speed[1])} ms` : '');
  if (s.languages && LANGS[s.languages.a] && LANGS[s.languages.b] && document.activeElement !== $('lang_a') && document.activeElement !== $('lang_b')) { langs = s.languages; showLangs(); }
  showModelState(s);
  if (s.speech_size && !sizeSent) speechSize = s.speech_size;   // (until the translator answers a click, the click stands)
  showSpeechSize(s);
  if (s.notice) html += `<span class="notice">${esc(s.notice)}</span>`;
  if (s.error) html += `<span class="err">${esc(s.error)}</span>`;
  $('stats').innerHTML = html;
});
on('subtitle', d => {
  const log = $('log');
  const atBottom = log.scrollTop + log.clientHeight >= log.scrollHeight - 5;
  log.innerHTML = '';
  d.lines.forEach(l => { const div = document.createElement('div'); div.textContent = l[1]; log.appendChild(div); });
  if (d.partial) { const div = document.createElement('div'); div.className = 'p'; div.textContent = d.partial; log.appendChild(div); }
  if (atBottom) log.scrollTop = log.scrollHeight;
});
// ---- layout: drag modules around, fold them, make them wide, pop them out. Each one also has its own page
// (/dock/<name>) for OBS custom browser docks. Theme and layout are saved by the translator, so every open
// page, pop-out and dock follows along. ----
const DOCK = {{ dock|tojson }};
const APP_WINDOW = {{ app_window|tojson }};
const TITLES = {{ modules|tojson }};
const grid = $('grid');
const MODS = {};
let ui = {{ ui|tojson }}, dragging = null;
const popped = {};
const toggleIn = (list, id) => list.includes(id) ? list.filter(x => x !== id) : [...list, id];
function applyUi(u) {
  ui = u;
  document.documentElement.dataset.theme = u.theme;
  $('theme').value = u.theme;
  if (DOCK || dragging) return;
  u.order.forEach(id => { if (MODS[id]) grid.appendChild(MODS[id]); });
  Object.entries(MODS).forEach(([id, sec]) => {
    const folded = u.collapsed.includes(id);
    sec.classList.toggle('wide', u.wide.includes(id));
    sec.classList.toggle('collapsed', folded);
    const b = sec.querySelector('[data-act="collapse"]');
    b.innerHTML = folded ? '&#x25B8;' : '&#x25BE;';
    b.setAttribute('aria-expanded', String(!folded));
  });
}
function saveUi() {
  if (!DOCK) ui.order = [...grid.children].map(sec => sec.dataset.mod);
  applyUi(ui);
  api('ui', ui);
}
function popOut(id) {
  if (popped[id] && !popped[id].closed) { popped[id].focus(); return; }
  const r = MODS[id].getBoundingClientRect();
  const w = window.open('/dock/' + id, 'lt_' + id,
    `popup=yes,width=${Math.round(Math.max(340, r.width))},height=${Math.round(Math.min(900, Math.max(220, r.height)))}`);
  if (!w) return;
  popped[id] = w;
  MODS[id].classList.add('popped');
}
setInterval(() => Object.entries(popped).forEach(([id, w]) => {
  if (w.closed) { delete popped[id]; MODS[id].classList.remove('popped'); }
}), 700);
document.querySelectorAll('section[data-mod]').forEach(sec => {
  const id = sec.dataset.mod;
  MODS[id] = sec;
  if (DOCK) { sec.classList.toggle('shown', id === DOCK); return; }
  const head = document.createElement('div');
  head.className = 'modhead';
  head.innerHTML = `<button type="button" class="grip" draggable="true" title="Drag to move (or focus it and use the arrow keys)"
      aria-label="Move ${esc(TITLES[id])}">&#x2807;&#x2807;</button><h2>${esc(TITLES[id])}</h2>`
    + '<button type="button" class="tool" data-act="collapse" title="Fold up / open"></button>'
    + '<button type="button" class="tool" data-act="wide" title="Wider / narrower">&#x2194;</button>'
    + '<button type="button" class="tool" data-act="pop" title="Pop out into its own window">&#x2197;</button>';
  sec.prepend(head);
  const note = document.createElement('div');
  note.className = 'popnote';
  note.innerHTML = '<span>Open in its own window.</span><button type="button">Bring back</button>';
  note.querySelector('button').onclick = () => { if (popped[id]) popped[id].close(); };
  sec.appendChild(note);
  head.addEventListener('click', e => {
    const act = e.target.closest('[data-act]')?.dataset.act;
    if (act === 'collapse') { ui.collapsed = toggleIn(ui.collapsed, id); saveUi(); }
    else if (act === 'wide') { ui.wide = toggleIn(ui.wide, id); saveUi(); }
    else if (act === 'pop') popOut(id);
  });
  const grip = head.querySelector('.grip');
  grip.addEventListener('dragstart', e => {
    dragging = sec;
    sec.classList.add('dragging'); grid.classList.add('sorting');
    e.dataTransfer.effectAllowed = 'move';
    e.dataTransfer.setData('text/plain', id);
    const r = sec.getBoundingClientRect();
    e.dataTransfer.setDragImage(sec, e.clientX - r.left, e.clientY - r.top);
  });
  grip.addEventListener('dragend', () => {
    sec.classList.remove('dragging'); grid.classList.remove('sorting');
    dragging = null;
    saveUi();
  });
  grip.addEventListener('keydown', e => {
    const back = e.key === 'ArrowLeft' || e.key === 'ArrowUp', fwd = e.key === 'ArrowRight' || e.key === 'ArrowDown';
    if (!back && !fwd) return;
    e.preventDefault();
    if (back && sec.previousElementSibling) grid.insertBefore(sec, sec.previousElementSibling);
    if (fwd && sec.nextElementSibling) grid.insertBefore(sec.nextElementSibling, sec);
    grip.focus();
    saveUi();
  });
});
grid.addEventListener('dragover', e => {
  if (!dragging) return;
  e.preventDefault();
  const over = e.target.closest('section[data-mod]');
  if (!over || over === dragging) return;
  const kids = [...grid.children];
  grid.insertBefore(dragging, kids.indexOf(dragging) < kids.indexOf(over) ? over.nextSibling : over);
});
grid.addEventListener('drop', e => e.preventDefault());
if ($('gpu_limit')) {
  let gpuTimer = null;
  $('gpu_limit').addEventListener('input', () => {
    $('gpu_limit_v').textContent = $('gpu_limit').value;
    clearTimeout(gpuTimer);
    gpuTimer = setTimeout(() => api('gpu_limit', {value: +$('gpu_limit').value}), 200);   // saved once you stop dragging
  });
}
$('theme').onchange = () => { ui.theme = $('theme').value; saveUi(); };
$('layout_reset').onclick = () => {
  if (confirm('Put every module back where it started? (The look stays.)')) api('ui', {theme: ui.theme});
};
on('ui', applyUi);
applyUi(ui);
</script>
</body>
</html>
"""


if __name__ == "__main__":
    main()
