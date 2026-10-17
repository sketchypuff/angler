# Angler

A reporter plugin for [Glyphs 3](https://glyphsapp.com). It shows the angle of whatever you have selected in the Edit View, and you can click an angle to type in a new one.

It's made for catching lines and handles that are *almost* horizontal or vertical, and for setting exact angles (italic slants, diagonal stems, handle tension) without trial and error.

## What it does

Turn it on with **View › Show Angler**. A label (badge) appears for:

- **Line segments**, when both of their on-curve ends are selected
- **Handles (BCPs)**, when the handle is selected; measured from its on-curve node
- **Handles of a selected node**: select an on-curve node to see both of its handles
- **Any two points**, when exactly two unrelated points are selected

Angles run from 0° to 180° from the horizontal, and direction doesn't matter: a line pointing left reads the same as one pointing right. Each badge sits next to its line, with a small arc drawn against the horizontal.

| Badge | Meaning |
| --- | --- |
| Dark | A normal angle |
| **Orange** | Within 0.5° of horizontal or vertical, but not exactly on it. Usually a mistake you'll want to fix. |
| **Green** | Exactly horizontal or vertical |

## Editing an angle

1. Click a badge, or right-click in the canvas and choose **Set Angle (…)…**.
2. Type the angle you want, for example `12` or `90`.
3. Press **Enter** to apply. Press **Esc**, or click somewhere else, to cancel.

What moves:

- **Handles** rotate around their on-curve node.
- **Line segments and point pairs**: the second point (in path order) rotates around the first. If that point is an on-curve node, its handles move with it.
- The distance between the two points stays the same.
- The new position is snapped to the font's grid, so the final angle can be a hair off what you typed.
- **Smooth nodes** stay smooth: the handle on the other side rotates to stay in line. One exception: if the other side is a straight line, the line isn't moved, so that node stops being truly smooth.
- One **Cmd+Z** undoes the whole edit.

Holding Shift, Cmd, Option or Control while you click a badge sends the click to Glyphs as usual, so shift-click selection keeps working.

## Installation

You need **Glyphs 3** to use Angler. It hasn't been tested in Glyphs 4.

### Install

1. **Download it.** Near the top of this page, click the green **Code** button, then click **Download ZIP**.
2. **Unzip it.** Open your Downloads folder and double-click the file you just downloaded. You'll get a folder called `angler-main`.
3. **Install it in Glyphs.** Open the `angler-main` folder and double-click **Angler.glyphsReporter**. Glyphs will ask if you want to install it. Click **Install**.
4. **Restart Glyphs.** Quit Glyphs fully (**Glyphs › Quit Glyphs**), then open it again.
5. **Turn it on.** Open any glyph and choose **View › Show Angler** from the menu bar.

Now select a handle or a straight line, and its angle appears next to it.

### Update to a newer version

Follow the same steps again. If Glyphs asks whether to replace the old version, say yes.

### If "Show Angler" doesn't appear in the View menu

Sometimes your Mac blocks plugins downloaded from the internet. To unblock Angler:

1. Open the **Terminal** app. Press **Cmd + Space**, type `Terminal`, and press **Return**.
2. Copy the line below, paste it into the Terminal window, and press **Return**:

   ```bash
   xattr -dr com.apple.quarantine ~/Library/Application\ Support/Glyphs\ 3/Plugins/Angler.glyphsReporter
   ```

   Nothing will appear to happen. That's normal.
3. Close Terminal and restart Glyphs.

### If something else goes wrong

In Glyphs, choose **Window › Macro Panel**. If you see any red error text there, copy it and send it along when you [report the problem](https://github.com/sketchypuff/angler/issues).

### Uninstall

1. In Finder, choose **Go › Go to Folder…** from the menu bar.
2. Paste `~/Library/Application Support/Glyphs 3/Plugins/` and press **Return**.
3. Drag **Angler.glyphsReporter** to the Trash.
4. Restart Glyphs.
