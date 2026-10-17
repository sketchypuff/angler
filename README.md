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

## Development install

```bash
ln -s "$PWD/Angler.glyphsReporter" ~/Library/Application\ Support/Glyphs\ 3/Plugins/
```

Restart Glyphs after each edit. Errors show up in **Window › Macro Panel**.
