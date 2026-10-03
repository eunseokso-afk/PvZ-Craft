# PvZ Craft

*Infinite Craft, but Plants vs. Zombies.* Drag elements onto the lawn and drop one on top of another to combine them.

- **Plant Mode** – start with Sun, Water, Seed and Dirt and grow all **49 plants** (Peashooter → Repeater → Gatling Pea, Puff-shroom → Doom-shroom, Cabbage-pult → Cob Cannon, ...).
- **Zombie Mode** – start with a Zombie, Brain, Grave, Junk and Water and raise all **26 zombies** (Conehead, Pole Vaulter, Zomboni, Gargantuar, ... Dr. Zomboss).
- **It's infinite:** any pair without a recipe makes a brand-new *hybrid* (Sun + Water = "Sunter", Peashooter + Wall-nut = "Pea-nut", ...), and hybrids can be combined again.
- The Almanac shows the real in-game descriptions for everything you've found, plus how you made it.
- Hint button, search, filters, sound effects, and your progress saves in the browser.

## Play

It's a static site, so any web server works:

```sh
python3 -m http.server 8000
# open http://localhost:8000
```

You can also turn on GitHub Pages for this repo (Settings → Pages → deploy from branch, root folder).

**Controls:** drag from the sidebar to the lawn (or tap/click an item to drop it on the lawn) · drop an item onto another to combine · double-click to duplicate · right-click or drag to the trash / off the lawn to remove · right-click a sidebar item to open it in the Almanac.

## How the assets are made

All the art, sounds and almanac text come from the game's own `main.pak`, which is stored here split into `main.pak.001`–`main.pak.005`.
`tools/build_assets.py` rebuilds everything:

1. joins the pieces back into `build/main.pak`,
2. decrypts it (XOR `0xF7`) and unpacks the PopCap pak format into `build/pak/`,
3. renders each plant/zombie icon from its `.reanim` skeletal animation (`tools/reanim.py`),
4. copies the sounds and backgrounds into `assets/`, and
5. writes `js/entities.js` (names, icons, almanac text from `LawnStrings.txt`).

```sh
pip install pillow
python3 tools/build_assets.py          # add --force to re-unpack the pak
```

The generated `assets/` and `js/entities.js` are committed, so you only need to run this if you change the entity list. `build/` is git-ignored.

Recipes live in `js/recipes.js` — add a line `['a', 'b', 'result']` to create a new one.

## Files

| Path | What |
| --- | --- |
| `index.html`, `css/style.css` | page + styling |
| `js/game.js` | game logic (drag & drop, combining, hybrids, almanac, saving) |
| `js/recipes.js` | starting elements and recipes for both modes |
| `js/entities.js` | generated entity data |
| `tools/` | pak unpacker, reanim renderer, asset builder |
