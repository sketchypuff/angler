# Angler

A Glyphs 3 reporter plugin that shows the angle of your selection in the Edit View.

Turn it on with **View › Show Angler**. It labels:

- **Line segments**: both on-curve ends selected
- **BCP handles**: a selected off-curve point, measured from its on-curve node
- **Handles of selected nodes**: select an on-curve node to see both of its handles
- **Any two points**: when exactly two unrelated points are selected

Angles run from 0° to 180° measured from horizontal, and direction doesn't matter. Each label is a badge with a small arc against the horizontal.

- **Orange**: within 0.5° of horizontal or vertical but not exactly on it. These are almost-straight lines you probably want to fix.
- **Green**: exactly horizontal or vertical.

## Editing an angle

Click a badge, or right-click and choose **Set Angle (…)…**, to type a new angle. Press **Enter** to apply, or **Esc** (or click away) to cancel. Clicking a badge with Shift, Cmd, Option, or Control held passes the click through to Glyphs.

- **Handles** rotate around their on-curve node.
- **Segments and two-point pairs**: the second point (in path order) rotates around the first. If that point is on-curve, its handles move with it.
- The length is kept and the result is snapped to the font grid, so the final angle may be a hair off what you typed.
- **Smooth nodes** keep their opposite handle in line. If the other side of a smooth node is a straight line, the line stays put, so the node stops being truly smooth.
- One **Cmd+Z** undoes the whole edit.

## Development install

```bash
ln -s "$PWD/Angler.glyphsReporter" ~/Library/Application\ Support/Glyphs\ 3/Plugins/
```

Restart Glyphs after each edit. Errors show up in **Window › Macro Panel**.
