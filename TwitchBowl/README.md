# Twitch Bowl

A stream overlay that drops a ball into a bowl for every new follower, first-time chatter, bits use and sub. It starts with Windows and runs silently in the background, so there is nothing to remember when you go live.

| Event | Balls |
| --- | --- |
| New follower | 1 (each person only once, even if they follow again) |
| First-time chatter | 1 |
| Bits | 1 per 100 bits, always at least 1 |
| Sub, resub shared in chat, or gifted sub | 1 each |

## Install on your streaming PC

Everything it needs is in the zip, so there's nothing else to install first.

1. Copy `TwitchBowl.zip` to your streaming PC and extract it to a folder you'll keep, such as Documents. The bowl runs from that folder.
2. Open the folder and double-click `install.bat`. If Windows warns about an unknown app, choose **More info**, then **Run anyway**.
3. Follow the window. The first time, it opens a Twitch page to register a free app and asks for the Client ID. Twitch requires two-factor authentication on your account for this.
4. Approve the Twitch page that opens next, logged in as your streaming account.
5. In OBS or Streamlabs, add a **Browser** source with the URL `http://127.0.0.1:7373`, width 800 and height 800.

That's it. From now on the bowl starts when you sign in to Windows, and the source stays in your scene.

## Make it yours

Double-click **Bowl Editor** in this folder. It opens in your browser. Changes save by themselves and appear in OBS straight away, with no refresh.

- **Pictures:** choose your own bowl and ball. Any picture works, and the ball is cropped to a circle. A bowl with a transparent background looks best.
- **Move picture:** drag the bowl where you want it, and use **Bowl size** to resize it.
- **Draw outline:** trace the inside of your bowl. Click to add points, or hold and draw. Balls stop exactly on this line, so it can be any shape.
  - Drag a point to move it.
  - Click the line to add a point.
  - Right-click a point to remove it.
- **Drop point:** drag the ball at the top to where balls should appear. **Drop width** spreads them out.
- **Settings:** ball size, gravity, bounciness, friction and bits for one ball.
- **Test the physics:** drop test balls to try it out. They stay in that page, so your real bowl isn't affected.

The stage is 800 by 800, the same as the source in OBS.

## Check it's working

- See what it's doing: open `http://127.0.0.1:7373/log`
- Add a real ball: open `http://127.0.0.1:7373/test`
- Empty the real bowl: use the button in Bowl Editor, or open `http://127.0.0.1:7373/reset`

To use a different Twitch Client ID, change it in `config.json` and run `install.bat` again. Running it again is safe and keeps your balls and your login. Do the same if you move the folder.

## Remove it

Double-click `uninstall.bat`, then delete the folder.

## Privacy

Everything runs on your PC. It only ever talks to Twitch, it can only read from your channel, and it never posts anything. The overlay and the editor can only be reached from the PC they run on.

`data.json` holds the ball count and your Twitch login, so don't share it. Delete it and run `install.bat` to start over and log in again.
