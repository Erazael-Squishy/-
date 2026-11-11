# Twitch Bowl: setting it up in Mix It Up and OBS

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
5. Press **OK**, then drag and resize the source where you want it.

Done. Follows, subs, resubs, gifted subs, bits and first-time chatters now drop balls.

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

| Event (exact name in Mix It Up) | Function Name | Parameter Name | Parameter Value |
| --- | --- | --- | --- |
| Twitch Channel Followed | `addFollower` | `username` | `$username` |
| Twitch Channel Subscribed | `addBalls` | `count` | `1` |
| Twitch Channel Resubscribed | `addBalls` | `count` | `1` |
| Twitch Channel Subscription Gifted | `addBalls` | `count` | `1` |
| Twitch Channel Mass Subscriptions Gifted | `addBalls` | `count` | `$subsgiftedamount` |
| Twitch Channel Bits Cheered | `addBits` | `amount` | `$bitsamount` |
| Chat User First Message | `addBalls` | `count` | `1` |

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

Make each one with **Add Action** → **Overlay** → **Run Widget Function** → **Widget** `Twitch Bowl`, as above. Set the permission to **Mod** so viewers can't use them. `!addballs 10` adds 10 balls, which is handy for testing.

---

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
- **Without Mix It Up:** open `bowl.html#overlay` in Chrome, press **F12** → **Console**, and type `addBalls(5)`, `addBits(250)`, `addFollower("someone")`, `breakBowl()` or `emptyBowl()`. This uses Chrome's own storage, not OBS's.

More fixes are in `bowl-guide.html`, Part 5.

---

## What I checked, and what I couldn't

Mix It Up's documentation websites couldn't be reached from where this was built, so everything here was worked out from **Mix It Up's own source code** (the public `MixItUpBot/desktop` repository, November 2026):

- **Confirmed in the source:** the exact event names; that *Run Widget Function* passes named parameters as text in one object, and that `$identifiers` in the values are filled in first; that the Custom widget runs in its own page that keeps browser storage; the widget event functions (`Follow`, `Subscription`, `SubscriptionGifted`, `MassSubscriptionGifted`, `TwitchBits`, `ChatMessageReceived`) and what they receive; `$username`, `$bitsamount` and `$subsgiftedamount`; how mass gifts are reported; the Developer API's run-command address; and the `.miuoverlay` file format.
- **Tested** by rebuilding Mix It Up's overlay page from its own templates and calling the bowl exactly the way Mix It Up does. All checks passed, including when the Javascript tab still holds Mix It Up's example code.
- **Not tested in the real Mix It Up app:** importing the `.miuoverlay` file, and the menu click paths (the labels come from Mix It Up's interface code). If the import complains, use the fallback: **Add Overlay Widget** → **Custom**, then in the HTML tab paste what **Copy for Mix It Up** gives you, empty the CSS and Javascript tabs, tick the four event boxes, and set Display Option to Single Widget URL.
- **First-time chatter** means the first message *Mix It Up* has ever seen from that person (Mix It Up keeps a message count per viewer). That's the same rule as its *Chat User First Message* event. People who chatted before you installed Mix It Up count once more, the first time they chat after that.
