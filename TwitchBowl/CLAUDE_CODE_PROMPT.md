# Prompt for Claude Code: turn Twitch Bowl into a single-file Mix It Up overlay

Copy everything below the line into Claude Code, opened in the folder where you unzipped `TwitchBowl.zip`.

---

## Who I am and what I want

I'm a streamer and a beginner at code. The project in this folder ("Twitch Bowl") is a stream overlay: a bowl on screen fills with physics balls, one for each event on my channel. Right now it is a Node.js server that logs into Twitch itself. I want three things from you:

1. **`bowl.html`**: one self-contained HTML file that does everything the current project does, plus the new features below. It should take its events from **Mix It Up** (the streaming bot I already use) and never connect to Twitch itself. No Node, no server, no install, no `config.json`, no separate image files.
2. **`bowl-guide.html`**: a second file that teaches me how to build `bowl.html` myself from an empty file, and explains every part of the code: what each section, function and setting does, why it is there, and what changes on screen if I change it. I want to understand everything, so assume I know almost nothing.
3. **`MIXITUP_SETUP.md`**: click-by-click steps to wire it into Mix It Up and OBS.

Please read every file in this folder before you start. The `node.exe` runtime was left out of the zip on purpose to keep it small; you won't need it.

## What the current project does (keep all of this)

Read `README.md`, `server.js`, `overlay.html` and `editor.html` for the details. In short:

**Ball rules** (currently in `server.js`, `handleEvent` and `connectChat`):
| Event | Balls |
| --- | --- |
| New follower | 1, and each person only once, even if they unfollow and follow again |
| First-time chatter | 1 |
| Bits | 1 per `bitsPerBall` bits (default 100), always at least 1 |
| Sub, resub shared in chat, or each gifted sub | 1 each |

**Overlay** (`overlay.html`, uses Matter.js from `matter.min.js`):
- 800×800 stage, transparent background, scales to the OBS source.
- The traced outline becomes thick invisible walls on the outer side of the line (`addWalls`, `signedArea`), so balls rest exactly on the drawn line and fast balls can't tunnel through. Keep the speed cap (`maxSpeed`).
- The ball picture is cropped to a circle once (`makeBallSprite`).
- Several balls arriving at once are dropped one every 150 ms with a little random scatter across the drop width.
- On load, the pile is rebuilt out of sight, capped at roughly what fits (`capacity`, `refill`).
- Balls that fall off the bottom of the stage are removed.

**Editor** (`editor.html`):
- Change the bowl and ball pictures (any image; resized so the longest side is at most 1600 px).
- "Move picture" mode: drag the bowl; "Bowl size" slider resizes it.
- "Draw outline" mode: click to add points or hold and draw freehand (a point every 16 px); drag a point to move it; click the line to insert a point; right-click a point to delete it; Undo; Clear outline.
- Drag the ball marker to set the drop point; "Drop width" spreads the drops.
- Sliders: bowl size, drop width, ball size, gravity, bounciness, friction. Number box: bits for one ball.
- "Test the physics": +1 / +10 / +50 / Empty test balls, without touching the real count.
- "Empty the real bowl" button (with a confirm).
- Changes save by themselves.

Keep the look and feel of the editor (dark panel, purple accent) unless something has to change.

## New features

### 1. Get events from Mix It Up instead of Twitch
Remove all Twitch login, EventSub and IRC code. Mix It Up already sees follows, subs, gifted subs, bits and chat, so let it decide when balls are added and just tell the bowl.

**Before writing this part, check Mix It Up's current docs** (https://mixitup.bot/docs and https://dev.site.mixitupapp.com/docs). What I found:
- Mix It Up has **Custom Overlay Widgets**: you write HTML, CSS and JavaScript, and they show in Mix It Up's own overlay, which is already a browser source in OBS.
- Any Mix It Up command can run an **Overlay Action → "Run Widget Function"**, which calls a named JavaScript function in a widget and passes parameters. The docs don't say exactly how the parameters arrive (one string? several arguments? an object?), so check the default template Mix It Up generates for a Custom widget, and write the receiving functions defensively: accept numbers or strings, trim them, and ignore bad input instead of crashing.
- Custom widgets can also get some events directly (Chat Messages, Follows, Twitch Subscriptions, Twitch Bits, and others), each passed to a matching function with a `data` object.

**Design I'd like, unless you find a better way that still works without a server:**
- `bowl.html` exposes a few small global functions that Mix It Up calls with Run Widget Function:
  - `addBalls(count)` to drop that many balls
  - `addFollower(username)` to drop 1 ball only the first time that username is seen (keep the list of seen followers saved)
  - `addBits(amount)` to drop `max(1, floor(amount / bitsPerBall))` balls
  - `emptyBowl()` and `breakBowl()`
- The ball count, the seen-followers list and all settings live in `localStorage` so they survive OBS restarts and source refreshes. Wrap every `localStorage` read and write in try/catch.
- In `MIXITUP_SETUP.md`, tell me exactly which Mix It Up **Event Commands** to make (follow, subscribe, resub, gifted sub, bits/cheer, first-time chatter) and which special identifiers to pass, such as the bits amount and the username. Check the real special identifier names and the real names of the event commands in the docs, and say in the guide if any of them you couldn't confirm. If Mix It Up has no first-time chatter event, say so and give me the closest workable option.
- If the Custom widget can't hold a whole HTML document as one paste, still keep `bowl.html` as the one source file, and have the setup guide say exactly which part goes into which tab (HTML / CSS / JavaScript). If that split is needed, make it trivial, for example by clearly marked sections I can copy, or a small "Copy for Mix It Up" button in the editor that puts each part on the clipboard.

### 2. Single file
- Inline Matter.js into `bowl.html` and keep its license header comment.
- Store the bowl and ball pictures as data URLs inside the settings.
- **Editing:** opening `bowl.html` directly in Chrome (double-click) should show the editor. Running inside OBS or Mix It Up should show only the overlay. Pick a clear rule, such as `#edit` in the URL or an "Edit" key, and explain it in the guide.
- Because the copy I edit in Chrome and the copy running in Mix It Up/OBS don't share storage, add a **"Save a copy with these settings"** button that downloads a new `bowl.html` with the current settings and pictures written into it as the defaults. Also add Export/Import settings as text, as a backup.
- The test-physics view and the "Empty the real bowl" button must still work.

### 3. Several bowls
Let me **add new bowls** and keep a list of them. Each bowl has its own picture, position, size, traced outline, drop point and drop width. In the editor: add a bowl, rename it, duplicate it, delete it (with a confirm), and choose which one is live. Ball picture and physics settings can stay shared.

### 4. The bowl breaks when it's full
- A bowl is "full" when it holds a set number of balls. Add a setting, "Breaks at ___ balls", and fill in a sensible default from the bowl's traced area (like the existing `capacity` estimate). Also add an "Auto" option that breaks when the pile reaches the top of the outline.
- Breaking should look good: the bowl picture cracks into several shards along random lines, the shards and the balls fall off-screen with physics, and a moment later an empty bowl fades back in. Add settings for how many shards, how long until the bowl comes back, and whether the next bowl in my list comes back instead of the same one (cycle through the bowls).
- Balls that arrive during the break wait and drop into the new bowl. Balls above the limit carry over to the new bowl.
- Add a "Break now" test button in the editor's test view, and make `breakBowl()` callable from Mix It Up, for example from a chat command.
- Optional but nice: a simple way for Mix It Up to react when the bowl breaks. Only add this if the docs show a reliable way for a widget to notify Mix It Up. Otherwise, say in the setup guide that it can't.

## How I want you to work
1. Read the existing code and the Mix It Up docs first. Tell me briefly what you found about how Run Widget Function passes parameters and how a Custom widget is structured, and adjust the plan if it differs from the design above.
2. Build `bowl.html`. Keep the code readable for a beginner: clear section headers, plain names, a short comment on anything non-obvious, and no build step or framework.
3. Test what you can. Open it in a headless browser if you have one, check that there are no console errors, that balls drop and settle inside the outline, that a break happens at the limit and the bowl comes back, that settings and the count survive a reload, and that the downloaded copy keeps the settings. Simulate Mix It Up by calling the global functions from the console.
4. Write `bowl-guide.html`, a self-contained page that reads well in a browser, with a table of contents, code blocks and plain explanations:
   - **Part 1, the big picture:** what the pieces are (HTML, CSS, JavaScript, Matter.js, localStorage, Mix It Up widget) and how an event travels from Twitch → Mix It Up → the bowl.
   - **Part 2, build it yourself:** step-by-step from an empty file, in small stages where I can open the file after each step and see something work: a canvas, then a falling ball, then walls from an outline, then pictures, then the editor tools, then saving, then several bowls, then breaking, then Mix It Up. Give the full code to add at each step and say where it goes.
   - **Part 3, the finished code explained:** walk through **all** of `bowl.html` in order, section by section. Show each piece of code, then explain what it does, why, and what each setting or number changes ("raise this and…").
   - **Part 4, changing things:** recipes such as changing the ball rules, adding a new event type, changing the break animation, changing the stage size.
   - **Part 5, troubleshooting:** e.g. balls fall through the bowl, nothing happens when someone follows, settings didn't carry over to OBS.
5. Write `MIXITUP_SETUP.md`.
6. Finish with a short summary of what you built, anything from this list you couldn't do or couldn't verify, and anything I need to decide.

Leave the old files alone and put the three new files next to them.
