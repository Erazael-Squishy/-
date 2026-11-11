# Twitch Bowl: setting it up in Mix It Up and OBS

*Version 3: gambling mode (pegs), grabbing balls, layered bowl pictures and several ball pictures, on top of version 2's names, colours, shaking, sounds, bubbles and counter. See "Extras" at the end.*

The bowl is one file, `bowl.html`. Mix It Up shows it on stream and tells it when to add balls. Nothing logs into Twitch, and nothing needs installing.

There are two ways to connect it. Pick **one**:

| | **A. Import the widget** (recommended) | **B. Event commands** |
| --- | --- | --- |
| Work | Import one file, paste one link into OBS | Build 7 event commands by hand |
| Good for | Getting going, sharing with friends | Changing the rules (e.g. 2 balls per sub) |
| First-time chatters | Yes | Yes |

Don't use both at once, or every event counts twice.

---

## Before you start

- **Mix It Up** (desktop app) logged into your Twitch account.
- In Mix It Up, open **Services** (left menu) and make sure **Overlay** is connected. Overlay widgets don't work without it.
- **OBS** (or Streamlabs Desktop).
- **Chrome** or **Edge**, to use the editor.

---

## Step 1. Make your bowl (optional)

Skip this to use the starter bowl.

1. Double-click `bowl.html`. It opens in your browser as the **Bowl Editor**.
   - If it opens the bowl without the panel, add `#edit` to the end of the address and press Enter.
2. Change the pictures, draw the outline, add more bowls, set when it breaks. Changes save by themselves (in that browser).
3. Press **Test the physics** to try it.

`bowl-guide.html` explains every button.

---

## Step 2A. Import the widget (recommended)

### Make the widget file

`Twitch Bowl.miuoverlay` in this folder is ready to import with the starter bowl. To use your own bowl instead:

1. In the Bowl Editor, press **Download Mix It Up widget**.
2. You get `Twitch Bowl.miuoverlay` in your Downloads folder. It holds the whole bowl: pictures, settings and code. **You can send this file to anyone**, and they can follow these same steps.

### Import it

1. In Mix It Up, open **Overlay Widgets** (left menu).
2. Press **Import Overlay Widget** and choose `Twitch Bowl.miuoverlay`.
3. The widget editor opens. Check these:
   - **Details** tab → **Display Option**: `Single Widget URL`. This gives the bowl its own link for OBS.
   - **HTML** tab: the whole bowl is in here. **CSS** and **Javascript** tabs: empty. Leave them empty.
   - The event boxes **Follows**, **Twitch Subscriptions**, **Twitch Bits** and **Chat Messages** are ticked. These are what add balls. Untick one to stop that event adding balls.
   - Leave **Refresh Time** at `0`. Anything else reloads the bowl over and over.
4. Press **Save**. Make sure the widget is enabled (its switch in the Overlay Widgets list is on).

### Put it in OBS

1. In the **Overlay Widgets** list, find the **Link** column for *Twitch Bowl* and press the copy button (**Copy Link For Twitch Bowl**).
2. In OBS: **Sources** → **+** → **Browser**. Name it "Twitch Bowl".
3. Paste the link into **URL**. Set **Width** `800` and **Height** `800`.
4. **Untick** "Shutdown source when not visible" and "Refresh browser when scene becomes active".
5. To hear the bowl's sounds on stream, tick **Control audio via OBS**. (Turn the sound off or down with *Sound volume* in the editor.)
6. Press **OK**, then drag and resize the source where you want it.

Done. Follows, subs, resubs, gifted subs, bits and first-time chatters now drop balls, each in its own colour and with the viewer's name.

> **Only one copy, please.** Add the bowl to OBS once. To show it in several scenes, add the *same* source to each scene (**+** → **Browser** → **Add Existing**), not a second browser source. Two copies running at once both count every event, so you'd get double balls. The same goes for importing the widget twice: delete the old widget first.

---

## Step 2B. Event commands instead (if you want your own rules)

Do Step 2A first (import and OBS). Then, so nothing counts twice, edit the widget in Mix It Up and **untick** **Follows**, **Twitch Subscriptions**, **Twitch Bits** and **Chat Messages**, and press **Save**.

Then make these **Event Commands**. In Mix It Up, open **Events** (left menu). The Twitch events are in the **Twitch** group; *Chat User First Message* is in the **Chat** group. For each one:

1. Press the **+** (add command) button next to the event.
2. **Add Action** → **Overlay**.
3. In the Overlay action, choose **Run Widget Function**.
4. **Widget**: `Twitch Bowl`. **Function Name**: from the table below.
5. For each parameter in the table, press **Add Parameter** and fill in **Name** and **Value**.
6. **Save**.

| Event (exact name in Mix It Up) | Function Name | Parameters (Name = Value) |
| --- | --- | --- |
| Twitch Channel Followed | `addFollower` | `username` = `$username` |
| Twitch Channel Subscribed | `addBalls` | `count` = `1`, `kind` = `sub`, `user` = `$username` |
| Twitch Channel Resubscribed | `addBalls` | `count` = `1`, `kind` = `sub`, `user` = `$username` |
| Twitch Channel Subscription Gifted | `addBalls` | `count` = `1`, `kind` = `sub`, `user` = `$username` |
| Twitch Channel Mass Subscriptions Gifted | `addBalls` | `count` = `$subsgiftedamount`, `kind` = `sub`, `user` = `$username` |
| Twitch Channel Bits Cheered | `addBits` | `amount` = `$bitsamount`, `user` = `$username` |
| Chat User First Message | `addBalls` | `count` = `1`, `kind` = `chat`, `user` = `$username` |

`kind` and `user` are optional. `kind` picks the ball's colour (`follow`, `sub`, `bits` or `chat`), and `user` is the name shown above the ball. For gifts, `$username` is the person who gave them.

Notes on these events:

- **Followers count once, forever.** Mix It Up runs *Twitch Channel Followed* only the first time someone follows while Mix It Up is open. The bowl also keeps its own list of everyone it has counted, so someone who unfollows and follows again next week doesn't add another ball.
- **Gifted subs.** A single gift runs *Subscription Gifted*. A bundle (for example, 5 gifts at once) runs *Mass Subscriptions Gifted* once, with `$subsgiftedamount` = 5. This only works while **Settings → Commands → Mass Gifted Subs Filter Amount** is switched on (it is by default, at 1). If you switch it off, a bundle runs both events and counts twice.
- **Bits.** `addBits` gives 1 ball per *Bits for one ball* (100 by default), and always at least 1.
- **Power-ups** (Gigantify an emote, message effects, celebrations) cost bits, but Mix It Up doesn't say how many, so they aren't counted. To count them anyway, add the three *Twitch Channel Power-Up …* events with `addBalls`, `count`, `1`.

You can use any numbers you like here. For example, set `count` to `5` for subs, and each sub drops 5 balls.

---

## Step 3. Chat commands for you and your mods (optional)

These work with either setup. In Mix It Up, open **Commands** (left menu) → **New Command** → **Chat Command**:

| Chat command | Function Name | Parameters | Who can use it |
| --- | --- | --- | --- |
| `!emptybowl` | `emptyBowl` | none | Mod |
| `!breakbowl` | `breakBowl` | none | Mod |
| `!addballs` | `addBalls` | `count` = `$arg1text` | Mod |
| `!shake` | `shakeBowl` | none, or `strength` = `1` to `3` | Anyone (give it a cooldown!) |

Make each one with **Add Action** → **Overlay** → **Run Widget Function** → **Widget** `Twitch Bowl`, as above. Set the permission to **Mod** so viewers can't use them. `!addballs 10` adds 10 balls, which is handy for testing.

---

### A "Shake the bowl" channel point reward

1. On Twitch, make a channel point reward called *Shake the bowl* (Creator Dashboard → Viewer Rewards → Channel Points).
2. In Mix It Up: **Commands** (left menu) → **Twitch Channel Points** → **New Command**, and pick your *Shake the bowl* reward.
3. **Add Action** → **Overlay** → **Run Widget Function** → **Widget** `Twitch Bowl`, **Function Name** `shakeBowl`. Optionally **Add Parameter**: `strength` = `2.5` for a big shake.
4. **Save**. Viewers can now spend points to bounce the pile. A strong shake can throw balls out of the bowl, which is half the fun.

## Step 4. Do something when the bowl breaks (optional)

The bowl can ask Mix It Up to run a command when it breaks: a chat message, a sound, an alert, anything.

1. In Mix It Up: **Services** → **Developer API** → **Connect**. This lets programs on your own PC run your commands. It only listens on your PC.
2. Make the command to run: **Commands** → **New Command** → **Custom Command**, e.g. "Bowl broke". Give it the actions you want. These special identifiers come from the bowl:

   | Identifier | What it is |
   | --- | --- |
   | `$bowlname` | Name of the bowl that broke (also `$arg1text`) |
   | `$bowlballs` | How many balls it held |
   | `$bowlbreaks` | How many times a bowl has broken so far |
   | `$nextbowlname` | The bowl that comes back |

   Example chat message: `The $bowlname shattered after $bowlballs balls! Here comes $nextbowlname.`
3. Find the command's ID: with Mix It Up open, open `http://localhost:8911/api/v2/commands?pageSize=500` in your browser. It lists every command. Find your command's `"Name"` and copy the `"ID"` just before it (it looks like `1a2b3c4d-...`). Paste it into the **Command ID** box in the Bowl Editor, under **Mix It Up**.
4. Update the widget (next section).

If the Developer API isn't connected, the bowl still breaks normally. It just can't tell Mix It Up.

---

## Changing the bowl later

Your ball count and follower list are kept by the overlay (in OBS's browser storage), not in the widget. Changing the widget doesn't reset them.

1. Change things in the Bowl Editor (double-click `bowl.html`).
2. Press **Copy for Mix It Up**.
3. In Mix It Up: **Overlay Widgets** → edit *Twitch Bowl* → **HTML** tab → click inside, **Ctrl+A**, **Ctrl+V** → **Save**.

This keeps the same widget and the same OBS link. Importing a new `.miuoverlay` instead creates a *second* widget with a *new* link. If you do that, delete the old widget and update the URL in OBS.

**Emptying the real bowl:** use `!emptybowl` (Step 3). Or press **Empty the real bowl** in the editor, then copy or download the widget again; that copy empties the bowl once when it loads.

---

## Sharing it with someone else

Send them `Twitch Bowl.miuoverlay` (made with **Download Mix It Up widget**) and this file. They follow **Step 2A**. Their bowl starts empty and counts their own channel. If they want to change it, also send `bowl.html` (or they can paste the widget's HTML tab into a file called `bowl.html`, since it's the same thing).

---

## Checking it works

- **Quickest:** make the `!addballs` chat command (Step 3) and type `!addballs 5` in your chat.
- **In the editor:** **Test the physics** shows exactly how it behaves, without touching the real bowl.
- **Without Mix It Up:** open `bowl.html#overlay` in Chrome, press **F12** → **Console**, and type `addBalls(5)`, `addBalls({ count: 1, kind: "sub", user: "Sam" })`, `addBits(250)`, `addFollower("someone")`, `shakeBowl(2)`, `breakBowl()` or `emptyBowl()`. This uses Chrome's own storage, not OBS's.

More fixes are in `bowl-guide.html`, Part 5.

---

## Extras

All of these are in the Bowl Editor, and work with both setups:

| Extra | What it does | Setting |
| --- | --- | --- |
| Names | Each new ball shows who sent it for 4 seconds | *Show who sent each ball* |
| Colours | Follow, sub, bits and first-chat balls each have a colour, and keep it after a reload | *Colour balls by event*, plus a colour picker for each |
| Shake | `shakeBowl` throws the pile into the air (Step 3) | — |
| Sounds | A "plip" for each ball, a crash when the bowl breaks, a "bwomp" for a shake | *Sound volume* (0 = off). Tick *Control audio via OBS* on the source |
| Bubbles | Bubbles float up and pop (with a pop sound) when the bowl breaks | *Bubbles when it breaks* |
| Counter | "47 / 176" above the bowl | *Show the count above the bowl* (off at first) |
| Gambling mode | Pegs on the stage that balls bounce off on the way down, so some miss the bowl. Misses are lost | *Gambling mode*: the on/off switch, peg size, bounce and colour, *Peg pattern*. Place pegs with the *Place pegs* tool |
| Grab balls | Click a ball and drag it, or throw it out of the bowl. A ball that leaves the stage comes off the count | *Let me grab balls with the mouse*. On stream: right-click the source in OBS → **Interact** |
| Ball pictures | Several pictures; each ball uses one | *Add ball pictures* (choose several at once); click one to remove it |
| Bowl layers | A **Back** picture behind the balls, a **Front** picture in front of them (so balls look inside the bowl), and an optional **Depth** picture | The three boxes under *Bowl pictures*. Choose 2 or 3 files at once with *Back* and they're sorted by name ("front", "back", "depth"). They line up by themselves; *Move picture* → *Move only the front/depth picture* pulls them apart, *Line up* puts them back |

**Since version 3, the count is always the balls you can see.** A ball that leaves the stage before its bowl breaks is gone for good: it missed (gambling mode), spilled, was shaken out or was dragged out.

Coming from version 1 or 2? Your ball count and followers carry over. Just paste or import the new copy as in "Changing the bowl later".

## What I checked, and what I couldn't

Mix It Up's documentation websites couldn't be reached from where this was built, so everything here was worked out from **Mix It Up's own source code** (the public `MixItUpBot/desktop` repository, November 2026):

- **Confirmed in the source:** the exact event names; that *Run Widget Function* passes named parameters as text in one object, and that `$identifiers` in the values are filled in first; that the Custom widget runs in its own page that keeps browser storage; the widget event functions (`Follow`, `Subscription`, `SubscriptionGifted`, `MassSubscriptionGifted`, `TwitchBits`, `ChatMessageReceived`) and what they receive; `$username`, `$bitsamount` and `$subsgiftedamount`; how mass gifts are reported; the Developer API's run-command address; and the `.miuoverlay` file format.
- **Tested** by rebuilding Mix It Up's overlay page from its own templates and calling the bowl exactly the way Mix It Up does. All checks passed, including when the Javascript tab still holds Mix It Up's example code.
- **Not tested in the real Mix It Up app:** importing the `.miuoverlay` file, and the menu click paths (the labels come from Mix It Up's interface code). If the import complains, use the fallback: **Add Overlay Widget** → **Custom**, then in the HTML tab paste what **Copy for Mix It Up** gives you, empty the CSS and Javascript tabs, tick the four event boxes, and set Display Option to Single Widget URL.
- **First-time chatter** means the first message *Mix It Up* has ever seen from that person (Mix It Up keeps a message count per viewer). That's the same rule as its *Chat User First Message* event. People who chatted before you installed Mix It Up count once more, the first time they chat after that.
