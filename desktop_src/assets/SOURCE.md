# Art used by the Desktop page

- `pioneer-wordmark.svg`: the Pioneer wordmark, drawn by Acadine Intelligence. It is a trademark and is not covered by the code licence.
- The page background is drawn in code (`Waypoint` in `plugin.src.js`). No image ships with the plugin.

A personal build can carry its own background image: `python3 scripts/build_desktop.py --art my.avif -o my-plugin.js`.
The image is inlined into that one file and stays out of this repo.
