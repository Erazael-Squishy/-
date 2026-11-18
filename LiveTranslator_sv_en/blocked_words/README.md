# blocked_words

Every word and phrase in the `.txt` files in this folder is hidden in the subtitles (shown as `@#$%&!`),
in every language. One entry per line; `#` starts a comment; a `*` at the end means "and any ending".
Edits are picked up within a few seconds, even while the translator is running.

- `my_words.txt`: your own additions.
- The other files, named after their language code (`en.txt`, `de.txt`, `ja.txt` ...), come from the
  **List of Dirty, Naughty, Obscene, and Otherwise Bad Words** by Shutterstock and contributors
  (https://github.com/LDNOOBW/List-of-Dirty-Naughty-Obscene-and-Otherwise-Bad-Words), licensed under
  Creative Commons Attribution 4.0 (https://creativecommons.org/licenses/by/4.0/). They are used unchanged.

These lists contain ordinary swear words too. The ones in `ALLOWED_WORDS` at the top of the translator's
`.py` file (fuck, shit, damn, hell ...) stay visible; anything else in the lists is hidden. If a normal
word you need keeps getting hidden, add it to `ALLOWED_WORDS`.

Languages with a file here: Arabic, Chinese, Czech, Dutch, English, Finnish, French, German, Hindi,
Hungarian, Italian, Japanese, Korean, Norwegian, Polish, Portuguese, Russian, Spanish, Swedish, Thai,
Turkish. Lines in every language (with or without a file) are also translated back to English and
checked there.
