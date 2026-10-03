#!/usr/bin/env python3
"""Rebuild main.pak from its split pieces, unpack it and generate the web assets.

Usage:  python3 tools/build_assets.py

Steps
  1. concatenate main.pak.001 .. main.pak.NNN -> build/main.pak
  2. decrypt (XOR 0xF7) + unpack the PopCap pak  -> build/pak/
  3. render plant / zombie icons from the .reanim animation data -> assets/icons/
  4. copy sounds + backgrounds                                   -> assets/
  5. write js/entities.js (names, icons, almanac text)
"""
import glob, json, math, os, re, shutil, struct, sys

from PIL import Image, ImageDraw, ImageFilter

sys.path.insert(0, os.path.dirname(__file__))
import reanim  # noqa: E402

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
BUILD = os.path.join(ROOT, 'build')
PAK = os.path.join(BUILD, 'pak')
ASSETS = os.path.join(ROOT, 'assets')
ICON_SIZE = 128


# --------------------------------------------------------------------- pak --
def join_pieces():
    pieces = sorted(glob.glob(os.path.join(ROOT, 'main.pak.[0-9][0-9][0-9]')))
    if not pieces:
        sys.exit('no main.pak.NNN pieces found')
    os.makedirs(BUILD, exist_ok=True)
    out = os.path.join(BUILD, 'main.pak')
    with open(out, 'wb') as o:
        for p in pieces:
            with open(p, 'rb') as f:
                shutil.copyfileobj(f, o)
    print(f'joined {len(pieces)} pieces -> {out} ({os.path.getsize(out)} bytes)')
    return out


def unpack(path):
    data = bytes(b ^ 0xF7 for b in open(path, 'rb').read())
    if data[:4] != b'\xc0\x4a\xc0\xba':
        sys.exit('not a PopCap pak file')
    p, entries = 8, []
    while True:
        flags = data[p]; p += 1
        if flags & 0x80:
            break
        n = data[p]; p += 1
        name = data[p:p + n].decode('latin1'); p += n
        size, = struct.unpack('<I', data[p:p + 4]); p += 12  # size + filetime
        entries.append((name, size))
    for name, size in entries:
        dst = os.path.join(PAK, name.replace('\\', '/'))
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        with open(dst, 'wb') as f:
            f.write(data[p:p + size])
        p += size
    print(f'unpacked {len(entries)} files -> {PAK}')


# ------------------------------------------------------------------ images --
def pak(*parts):
    return os.path.join(PAK, *parts)


def load_image(rel):
    """Load a pak image, applying a PopCap '<name>_.png' alpha mask when present."""
    path = pak(rel)
    im = Image.open(path).convert('RGBA')
    base, _ = os.path.splitext(path)
    for ext in ('.png', '.gif', '.jpg'):
        mask = base + '_' + ext
        if os.path.exists(mask) and not base.endswith('_'):
            m = Image.open(mask).convert('L')
            im.putalpha(m)
            break
    return im


def cell(im, cols, rows, idx):
    w, h = im.size[0] // cols, im.size[1] // rows
    x, y = (idx % cols) * w, (idx // cols) * h
    return im.crop((x, y, x + w, y + h))


def fit(im, size=ICON_SIZE, pad=4):
    bbox = im.getbbox()
    if bbox:
        im = im.crop(bbox)
    w, h = im.size
    s = (size - 2 * pad) / max(w, h)
    im = im.resize((max(1, round(w * s)), max(1, round(h * s))), Image.LANCZOS)
    out = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    out.alpha_composite(im, ((size - im.size[0]) // 2, (size - im.size[1]) // 2))
    return out


def circle_crop(im):
    s = min(im.size)
    im = im.crop(((im.size[0] - s) // 2, (im.size[1] - s) // 2,
                  (im.size[0] + s) // 2, (im.size[1] + s) // 2))
    mask = Image.new('L', im.size, 0)
    ImageDraw.Draw(mask).ellipse((2, 2, s - 3, s - 3), fill=255)
    im.putalpha(mask)
    return im


def draw_moon():
    s = 256
    im = Image.new('RGBA', (s, s), (0, 0, 0, 0))
    glow = Image.new('RGBA', (s, s), (0, 0, 0, 0))
    ImageDraw.Draw(glow).ellipse((20, 20, s - 20, s - 20), fill=(190, 210, 255, 120))
    im.alpha_composite(glow.filter(ImageFilter.GaussianBlur(14)))
    d = ImageDraw.Draw(im)
    d.ellipse((40, 40, s - 40, s - 40), fill=(244, 240, 214, 255), outline=(150, 145, 120, 255), width=6)
    for (x, y, r) in ((100, 95, 18), (150, 150, 26), (95, 160, 12), (160, 90, 10)):
        d.ellipse((x - r, y - r, x + r, y + r), fill=(214, 206, 170, 255))
    return im


def sandify(im):
    r, g, b, a = im.split()
    lum = Image.merge('RGB', (r, g, b)).convert('L').point(lambda v: min(255, int(v * 1.6)))
    tinted = Image.merge('RGB', (lum.point(lambda v: min(255, v + 90)), lum.point(lambda v: min(255, v + 60)), lum.point(lambda v: v // 2 + 20)))
    tinted.putalpha(a)
    return tinted


def render_reanim(name, **kw):
    return reanim.render(pak('reanim', name + '.reanim'), pak('reanim'), **kw)


def group(*ims, spread=0.45):
    """Overlap several images left->right (used for 'horde' style icons)."""
    ims = [fit(i, 160, 0) for i in ims]
    w = int(160 + 160 * spread * (len(ims) - 1))
    out = Image.new('RGBA', (w, 160), (0, 0, 0, 0))
    for k, i in enumerate(reversed(ims)):
        out.alpha_composite(i, (int(160 * spread * (len(ims) - 1 - k)), 0))
    return out


# Tracks that belong to optional zombie accessories in Zombie.reanim
ZOMBIE_EXTRAS = [r'anim_cone', r'anim_bucket', r'screendoor', r'Zombie_flaghand', r'duckytube',
                 r'whitewater', r'Zombie_mustache', r'anim_tongue']
ZOMBIE_ARM = [r'^Zombie_outerarm_(hand|upper|lower)$']


def basic_zombie(show=(), hide=(), **kw):
    hidden = [h for h in ZOMBIE_EXTRAS if not any(re.search(h, s, re.I) for s in show)] + list(hide)
    return render_reanim('Zombie', hide=hidden, **kw)


# --------------------------------------------------------------- entities --
# (id, display name, icon factory, almanac string key or None, sound)
P = 'plant'
Z = 'zombie'


def R(name, **kw):
    return lambda: render_reanim(name, **kw)


def I(rel, *c):
    return lambda: cell(load_image(rel), *c) if c else load_image(rel)


ENTITIES = [
    # ---------------- plant mode: base & intermediate elements --------------
    dict(id='sun', name='Sun', mode=P, icon=R('Sun', hide=[r'Sun3']), tip='The currency of the lawn.'),
    dict(id='water', name='Water', mode=P, icon=I('images/waterdrop.png'), tip='Wet. Good for growing.'),
    dict(id='seed', name='Seed', mode=P, icon=I('images/seeds.png', 9, 1, 3), tip='Every plant starts as a seed packet.'),
    dict(id='dirt', name='Dirt', mode=P, icon=lambda: group(*[cell(load_image('images/dirtbig.png'), 4, 2, k) for k in (0, 1, 2)], spread=0.3), tip='Good, honest lawn dirt.'),
    dict(id='sprout', name='Sprout', mode=P, icon=R('ZenGarden_sprout'), tip='A tiny plant, full of potential.'),
    dict(id='night', name='Night', mode=P, icon=draw_moon, tip='When the sun goes under the dirt, the shrooms wake up.'),
    dict(id='fire', name='Fire', mode=P, icon=R('fire'), tip='Hot hot hot.'),
    dict(id='rock', name='Rock', mode=P, icon=lambda: group(*[cell(load_image('images/RockSmall.png'), 8, 2, k) for k in (3, 0, 5)], spread=0.35), tip='A pebble from the yard.'),
    dict(id='ice', name='Ice', mode=P, icon=I('images/icetrap.png'), tip='Brrrr.'),
    dict(id='pool', name='Pool', mode=P, icon=lambda: circle_crop(load_image('images/pool.jpg').crop((260, 0, 420, 159))), tip='The backyard pool.'),
    dict(id='pea', name='Pea', mode=P, icon=I('images/ProjectilePea.png'), tip='Ammunition.'),
    dict(id='explosion', name='Explosion', mode=P, icon=I('particles/Pow.png'), tip='POW!!'),
    dict(id='tree', name='Tree', mode=P, icon=R('treeofWisdom', anim='anim_grow30', hide=['^bg$', 'grass', 'overlay']), tip='The Tree of Wisdom knows many things.'),
    dict(id='grave', name='Grave', mode=P, icon=I('images/Night_grave_graphic.png'), tip='Something is stirring underneath...'),
    dict(id='zombie_p', name='Zombie', mode=P, icon=lambda: load_image('particles/ZombieHead.png'), tip='Brains!'),
    dict(id='metal', name='Metal', mode=P, icon=I('reanim/Zombie_catapult_manhole.png'), tip='Shiny and magnetic.'),
    dict(id='gold', name='Gold', mode=P, icon=R('Coin_gold'), tip='Bling!'),
    dict(id='sand', name='Sand', mode=P, icon=lambda: sandify(group(*[cell(load_image('images/dirtbig.png'), 4, 2, k) for k in (2, 0)], spread=0.4)), tip='Tiny rocks.'),
    dict(id='rain', name='Rain', mode=P, icon=lambda: group(load_image('images/waterdrop.png'), load_image('images/waterdrop.png'), load_image('images/waterdrop.png'), spread=0.55), tip='Water, but falling.'),
    dict(id='wind', name='Wind', mode=P, icon=I('particles/ExplosionCloud.png'), tip='Whoosh.'),
    dict(id='star', name='Star', mode=P, icon=I('particles/Star40.png'), tip='Twinkle twinkle.'),
    dict(id='lawn_mower', name='Lawn Mower', mode=P, icon=R('LawnMower'), tip='The last line of defense.'),
    dict(id='crazy_dave', name='Crazy Dave', mode=P, icon=R('CrazyDave', anim='anim_idle', hide=['zombie_', 'grabhand', 'handinghand']), key='CRAZY_DAVE', tip="He's CRAZY!"),
    dict(id='taco', name='Taco', mode=P, icon=I('images/Taco.png'), key='TACO'),

    # ---------------------------- plant mode: the 49 plants --------------------
    dict(id='peashooter', name='Peashooter', mode=P, icon=R('PeaShooterSingle'), key='PEASHOOTER'),
    dict(id='sunflower', name='Sunflower', mode=P, icon=R('SunFlower'), key='SUNFLOWER'),
    dict(id='cherry_bomb', name='Cherry Bomb', mode=P, icon=R('CherryBomb'), key='CHERRY_BOMB'),
    dict(id='wall_nut', name='Wall-nut', mode=P, icon=R('Wallnut'), key='WALL_NUT'),
    dict(id='potato_mine', name='Potato Mine', mode=P, icon=R('PotatoMine', anim='anim_armed'), key='POTATO_MINE'),
    dict(id='snow_pea', name='Snow Pea', mode=P, icon=R('SnowPea'), key='SNOW_PEA'),
    dict(id='chomper', name='Chomper', mode=P, icon=R('Chomper', anim='anim_idle'), key='CHOMPER'),
    dict(id='repeater', name='Repeater', mode=P, icon=R('PeaShooter'), key='REPEATER'),
    dict(id='puff_shroom', name='Puff-shroom', mode=P, icon=R('PuffShroom'), key='PUFF_SHROOM'),
    dict(id='sun_shroom', name='Sun-shroom', mode=P, icon=R('SunShroom', anim='anim_bigidle'), key='SUN_SHROOM'),
    dict(id='fume_shroom', name='Fume-shroom', mode=P, icon=R('FumeShroom'), key='FUME_SHROOM'),
    dict(id='grave_buster', name='Grave Buster', mode=P, icon=R('Gravebuster', anim='anim_idle'), key='GRAVE_BUSTER'),
    dict(id='hypno_shroom', name='Hypno-shroom', mode=P, icon=R('HypnoShroom'), key='HYPNO_SHROOM'),
    dict(id='scaredy_shroom', name='Scaredy-shroom', mode=P, icon=R('ScaredyShroom'), key='SCAREDY_SHROOM'),
    dict(id='ice_shroom', name='Ice-shroom', mode=P, icon=R('IceShroom'), key='ICE_SHROOM'),
    dict(id='doom_shroom', name='Doom-shroom', mode=P, icon=R('DoomShroom'), key='DOOM_SHROOM'),
    dict(id='lily_pad', name='Lily Pad', mode=P, icon=R('LilyPad'), key='LILY_PAD'),
    dict(id='squash', name='Squash', mode=P, icon=R('Squash'), key='SQUASH'),
    dict(id='threepeater', name='Threepeater', mode=P, icon=R('ThreePeater', anim=['anim_idle', 'anim_head_idle1', 'anim_head_idle2', 'anim_head_idle3']), key='THREEPEATER'),
    dict(id='tangle_kelp', name='Tangle Kelp', mode=P, icon=R('Tanglekelp'), key='TANGLE_KELP'),
    dict(id='jalapeno', name='Jalapeno', mode=P, icon=R('Jalapeno'), key='JALAPENO'),
    dict(id='spikeweed', name='Spikeweed', mode=P, icon=R('Caltrop'), key='SPIKEWEED'),
    dict(id='torchwood', name='Torchwood', mode=P, icon=R('Torchwood'), key='TORCHWOOD'),
    dict(id='tall_nut', name='Tall-nut', mode=P, icon=R('Tallnut'), key='TALL_NUT'),
    dict(id='sea_shroom', name='Sea-shroom', mode=P, icon=R('SeaShroom'), key='SEA_SHROOM'),
    dict(id='plantern', name='Plantern', mode=P, icon=R('Plantern'), key='PLANTERN'),
    dict(id='cactus', name='Cactus', mode=P, icon=R('Cactus'), key='CACTUS'),
    dict(id='blover', name='Blover', mode=P, icon=R('Blover'), key='BLOVER'),
    dict(id='split_pea', name='Split Pea', mode=P, icon=R('SplitPea', anim=['anim_idle', 'anim_head_idle', 'anim_splitpea_idle']), key='SPLIT_PEA'),
    dict(id='starfruit', name='Starfruit', mode=P, icon=R('Starfruit'), key='STARFRUIT'),
    dict(id='pumpkin', name='Pumpkin', mode=P, icon=R('Pumpkin'), key='PUMPKIN'),
    dict(id='magnet_shroom', name='Magnet-shroom', mode=P, icon=R('Magnetshroom'), key='MAGNET_SHROOM'),
    dict(id='cabbage_pult', name='Cabbage-pult', mode=P, icon=R('Cabbagepult'), key='CABBAGE_PULT'),
    dict(id='flower_pot', name='Flower Pot', mode=P, icon=R('Pot'), key='FLOWER_POT'),
    dict(id='kernel_pult', name='Kernel-pult', mode=P, icon=R('Cornpult'), key='KERNEL_PULT'),
    dict(id='coffee_bean', name='Coffee Bean', mode=P, icon=R('Coffeebean'), key='COFFEE_BEAN'),
    dict(id='garlic', name='Garlic', mode=P, icon=R('Garlic'), key='GARLIC'),
    dict(id='umbrella_leaf', name='Umbrella Leaf', mode=P, icon=R('Umbrellaleaf'), key='UMBRELLA_LEAF'),
    dict(id='marigold', name='Marigold', mode=P, icon=R('Marigold'), key='MARIGOLD'),
    dict(id='melon_pult', name='Melon-pult', mode=P, icon=R('Melonpult'), key='MELON_PULT'),
    dict(id='gatling_pea', name='Gatling Pea', mode=P, icon=R('GatlingPea', anim=['anim_idle', 'anim_head_idle']), key='GATLING_PEA'),
    dict(id='twin_sunflower', name='Twin Sunflower', mode=P, icon=R('TwinSunflower'), key='TWIN_SUNFLOWER'),
    dict(id='gloom_shroom', name='Gloom-shroom', mode=P, icon=R('GloomShroom'), key='GLOOM_SHROOM'),
    dict(id='cattail', name='Cattail', mode=P, icon=R('Cattail'), key='CATTAIL'),
    dict(id='winter_melon', name='Winter Melon', mode=P, icon=R('WinterMelon'), key='WINTER_MELON'),
    dict(id='gold_magnet', name='Gold Magnet', mode=P, icon=R('GoldMagnet'), key='GOLD_MAGNET'),
    dict(id='spikerock', name='Spikerock', mode=P, icon=R('SpikeRock'), key='SPIKEROCK'),
    dict(id='cob_cannon', name='Cob Cannon', mode=P, icon=R('CobCannon'), key='COB_CANNON'),
    dict(id='imitater', name='Imitater', mode=P, icon=R('Imitater'), key='IMITATER'),

    # ------------------------ zombie mode: base & intermediate elements -------
    dict(id='z_zombie', name='Zombie', mode=Z, icon=lambda: basic_zombie(), key='ZOMBIE'),
    dict(id='brain', name='Brain', mode=Z, icon=I('images/brain.png'), tip='Delicious.'),
    dict(id='z_grave', name='Grave', mode=Z, icon=I('images/Night_grave_graphic.png'), tip='Home sweet home.'),
    dict(id='junk', name='Junk', mode=Z, icon=I('reanim/Zombie_gargantuar_trashcan1.png'), tip="One zombie's trash is another zombie's armor."),
    dict(id='z_water', name='Water', mode=Z, icon=I('images/waterdrop.png'), tip='Zombies can swim. Sort of.'),
    dict(id='z_metal', name='Metal', mode=Z, icon=I('reanim/Zombie_catapult_manhole.png'), tip='Heavy and shiny.'),
    dict(id='z_night', name='Night', mode=Z, icon=draw_moon, tip='The best time to shamble.'),
    dict(id='z_ice', name='Ice', mode=Z, icon=I('images/icetrap.png'), tip='Frozen solid.'),
    dict(id='traffic_cone', name='Traffic Cone', mode=Z, icon=I('reanim/Zombie_cone1.png'), tip='Found on the side of the road.'),
    dict(id='bucket', name='Bucket', mode=Z, icon=I('reanim/Zombie_bucket1.png'), tip='Makes a great hat.'),
    dict(id='newspaper', name='Newspaper', mode=Z, icon=I('reanim/Zombie_paper_paper1.png'), tip='Read all about it!'),
    dict(id='screen_door', name='Screen Door', mode=Z, icon=I('reanim/Zombie_screendoor1.png'), tip='A sturdy shield.'),
    dict(id='football_helmet', name='Football Helmet', mode=Z, icon=I('reanim/Zombie_football_helmet.png'), tip='Protects the brain.'),
    dict(id='pole', name='Pole', mode=Z, icon=I('reanim/Zombie_polevaulter_pole.png'), tip='Long and pointy.'),
    dict(id='ladder', name='Ladder', mode=Z, icon=I('reanim/Zombie_ladder_1.png'), tip='Over the wall!'),
    dict(id='pogo_stick', name='Pogo Stick', mode=Z, icon=lambda: render_reanim('Zombie_pogo', anim='anim_pogo', show_only=['pogo_stick'], hide=['stickhands', 'stick[23]']), tip='Boing boing boing.'),
    dict(id='pickaxe', name='Pickaxe', mode=Z, icon=I('reanim/Zombie_digger_pickaxe.png'), tip='For digging.'),
    dict(id='flag', name='Flag', mode=Z, icon=I('reanim/Zombie_flag1.png'), tip='A huge wave of zombies is approaching!'),
    dict(id='ducky_tube', name='Ducky Tube', mode=Z, icon=I('reanim/Zombie_duckytube_whole.png'), tip='Quack.'),
    dict(id='dolphin', name='Dolphin', mode=Z, icon=R('Zombie_dolphinrider', anim='anim_walkdolphin', show_only=[r'dolphin(body|fin|jaw)']), tip='Smart and slippery.'),
    dict(id='music', name='Music', mode=Z, icon=I('images/Phonograph.png'), tip='Thriller night!'),
    dict(id='jack_in_the_box', name='Jack-in-the-Box', mode=Z, icon=I('reanim/Zombie_jackbox_box.png'), tip='Pop goes the weasel...'),
    dict(id='balloon', name='Balloon', mode=Z, icon=lambda: render_reanim('Zombie_balloon', show_only=[r'balloon_(top|bottom|string)'], anim='anim_idle'), tip='Up, up and away!'),
    dict(id='bungee_cord', name='Bungee Cord', mode=Z, icon=I('images/BungeeCord.png'), tip='Stretchy.'),
    dict(id='vehicle', name='Vehicle', mode=Z, icon=I('images/Store_Car.jpg'), tip='Zombies love a road trip.'),
    dict(id='horde', name='Horde', mode=Z, icon=lambda: group(basic_zombie(), basic_zombie(show=['anim_cone'], hide=['anim_hair']), basic_zombie()), tip='Zombies, zombies everywhere.'),
    dict(id='big_brain', name='Big Brain', mode=Z, icon=I('images/Credits_BigBrain.jpg'), tip='A genius-level brain.'),

    # ------------------------------ zombie mode: the zombies -------------------
    dict(id='flag_zombie', name='Flag Zombie', mode=Z, icon=lambda: flag_zombie(), key='FLAG_ZOMBIE'),
    dict(id='conehead', name='Conehead Zombie', mode=Z, icon=lambda: basic_zombie(show=['anim_cone'], hide=['anim_hair']), key='CONEHEAD_ZOMBIE'),
    dict(id='buckethead', name='Buckethead Zombie', mode=Z, icon=lambda: basic_zombie(show=['anim_bucket'], hide=['anim_hair']), key='BUCKETHEAD_ZOMBIE'),
    dict(id='pole_vaulting', name='Pole Vaulting Zombie', mode=Z, icon=R('Zombie_polevaulter', anim='anim_idle', hide=['pole2']), key='POLE_VAULTING_ZOMBIE'),
    dict(id='newspaper_zombie', name='Newspaper Zombie', mode=Z, icon=R('Zombie_paper', anim='anim_idle'), key='NEWSPAPER_ZOMBIE'),
    dict(id='screen_door_zombie', name='Screen Door Zombie', mode=Z, icon=lambda: basic_zombie(show=['screendoor'], hide=ZOMBIE_ARM), key='SCREEN_DOOR_ZOMBIE'),
    dict(id='football_zombie', name='Football Zombie', mode=Z, icon=R('Zombie_football', anim='anim_idle', hide=['anim_hair']), key='FOOTBALL_ZOMBIE'),
    dict(id='dancing_zombie', name='Dancing Zombie', mode=Z, icon=R('Zombie_disco', anim='anim_walk', hide=['outerhand_point', 'upper_bone']), key='DANCING_ZOMBIE'),
    dict(id='backup_dancer', name='Backup Dancer', mode=Z, icon=R('Zombie_backup', anim='anim_walk'), key='BACKUP_DANCER'),
    dict(id='ducky_tube_zombie', name='Ducky Tube Zombie', mode=Z, icon=lambda: basic_zombie(show=['duckytube'], hide=['whitewater']), key='DUCKY_TUBE_ZOMBIE'),
    dict(id='snorkel_zombie', name='Snorkel Zombie', mode=Z, icon=R('Zombie_snorkle', anim='anim_idle', hide=['whitewater']), key='SNORKEL_ZOMBIE'),
    dict(id='zomboni', name='Zomboni', mode=Z, icon=R('Zombie_zamboni', anim='anim_drive'), key='ZOMBONI'),
    dict(id='bobsled_team', name='Zombie Bobsled Team', mode=Z, icon=lambda: bobsled(), key='ZOMBIE_BOBSLED_TEAM'),
    dict(id='dolphin_rider', name='Dolphin Rider Zombie', mode=Z, icon=R('Zombie_dolphinrider', anim='anim_walkdolphin', hide=['whitewater', 'watershadow', 'inwater', r'^Layer']), key='DOLPHIN_RIDER_ZOMBIE'),
    dict(id='jack_zombie', name='Jack-in-the-Box Zombie', mode=Z, icon=R('Zombie_jackbox', anim='anim_walk', hide=['clown']), key='JACK_IN_THE_BOX_ZOMBIE'),
    dict(id='balloon_zombie', name='Balloon Zombie', mode=Z, icon=R('Zombie_balloon', anim='anim_idle', hide=['balloon_pop', 'propeller', r'^hat$']), key='BALLOON_ZOMBIE'),
    dict(id='digger_zombie', name='Digger Zombie', mode=Z, icon=R('Zombie_digger', anim='anim_walk', hide=['digger_dirt', 'digger_rise', 'digger_dig']), key='DIGGER_ZOMBIE'),
    dict(id='pogo_zombie', name='Pogo Zombie', mode=Z, icon=R('Zombie_pogo', anim='anim_pogo', hide=['anim_hair']), key='POGO_ZOMBIE'),
    dict(id='zombie_yeti', name='Zombie Yeti', mode=Z, icon=R('Zombie_yeti', anim='anim_walk'), key='ZOMBIE_YETI'),
    dict(id='bungee_zombie', name='Bungee Zombie', mode=Z, icon=R('Zombie_bungi', anim='anim_idle'), key='BUNGEE_ZOMBIE'),
    dict(id='ladder_zombie', name='Ladder Zombie', mode=Z, icon=R('Zombie_ladder', anim='anim_idle'), key='LADDER_ZOMBIE'),
    dict(id='catapult_zombie', name='Catapult Zombie', mode=Z, icon=R('Zombie_catapult', anim='anim_idle', hide=[r'basketball[234]']), key='CATAPULT_ZOMBIE'),
    dict(id='gargantuar', name='Gargantuar', mode=Z, icon=R('Zombie_gargantuar', anim='anim_idle', hide=['trashcan', 'whiterope']), key='GARGANTUAR'),
    dict(id='imp', name='Imp', mode=Z, icon=R('Zombie_imp', anim='anim_walk'), key='IMP'),
    dict(id='dr_zomboss', name='Dr. Zomboss', mode=Z, icon=R('Zombie_boss', anim=['anim_idle', 'anim_head_idle'], hide=['RV', 'eyeglow_(red|black)', 'mouthglow_red', 'bits']), key='BOSS'),
]


def flag_zombie():
    z = basic_zombie(show=['Zombie_flaghand'], hide=[r'innerarm_hand', r'anim_innerarm'])
    flag = render_reanim('Zombie_flagpole', anim=None)
    out = Image.new('RGBA', (z.size[0] + flag.size[0] // 2, max(z.size[1], flag.size[1] + 20)), (0, 0, 0, 0))
    out.alpha_composite(flag, (0, 0))
    out.alpha_composite(z, (out.size[0] - z.size[0], out.size[1] - z.size[1]))
    return out


def bobsled():
    sled = load_image('images/Zombie_bobsled1.png')
    zs = [render_reanim('Zombie_bobsled', anim='anim_idle') for _ in range(3)]
    w = sled.size[0] * 2
    z0 = zs[0]
    scale = sled.size[1] * 2.4 / z0.size[1]
    zs = [z.resize((int(z.size[0] * scale), int(z.size[1] * scale)), Image.LANCZOS) for z in zs]
    h = zs[0].size[1] + sled.size[1]
    out = Image.new('RGBA', (w, h), (0, 0, 0, 0))
    for k, z in enumerate(zs):
        out.alpha_composite(z, (int(w * 0.08 + k * w * 0.2), 0))
    out.alpha_composite(sled.resize((w, sled.size[1] * 2)), (0, h - sled.size[1] * 2))
    return out


# -------------------------------------------------------------- strings --
def load_strings():
    txt = open(pak('properties', 'LawnStrings.txt'), encoding='latin1').read()
    out = {}
    for m in re.finditer(r'^\[([A-Z0-9_]+)\]\s*\n(.*?)(?=^\[|\Z)', txt, re.S | re.M):
        out[m.group(1)] = m.group(2).strip()
    return out


def clean(s):
    s = re.sub(r'\{[A-Z_]+\}', '\n', s)
    s = re.sub(r'\{\d+\}', '', s)
    return re.sub(r'[ \t]*\n[ \t\n]*', '\n', s).strip()


def almanac(strings, key):
    tip = strings.get(key + '_TOOLTIP', '').strip()
    desc = strings.get(key + '_DESCRIPTION', '')
    flavor = ''
    stats = []
    if desc:
        parts = desc.split('{FLAVOR}')
        for ln in clean(parts[0]).split('\n'):
            if stats and stats[-1].endswith(':'):
                stats[-1] += ' ' + ln
            elif ln:
                stats.append(ln)
        flavor = clean(parts[1]).replace('\n', ' ') if len(parts) > 1 else ''
    return tip, stats, flavor


# --------------------------------------------------------------- main -----
SOUNDS = ['plant', 'plant2', 'seedlift', 'buzzer', 'groan', 'groan2', 'groan3', 'groan4', 'achievement',
          'points', 'tap', 'shovel', 'evillaugh', 'awooga', 'cherrybomb', 'chomp', 'bleep', 'floop',
          'paper', 'lightfill', 'prize', 'gravebutton', 'hugewave', 'crazydaveshort1', 'crazydaveshort2']
BACKGROUNDS = ['background1.jpg', 'background2.jpg', 'Almanac_GroundDay.jpg', 'Almanac_GroundNight.jpg',
               'titlescreen.jpg', 'SeedChooser_Background.png', 'SeedBank.png', 'Almanac_PlantCard.png',
               'Almanac_ZombieCard.png', 'Almanac_IndexBack.jpg', 'PvZ_Logo.jpg', 'ZombieNote.jpg']


def main():
    if not os.path.isdir(PAK) or '--force' in sys.argv:
        unpack(join_pieces())
    icons = os.path.join(ASSETS, 'icons')
    os.makedirs(icons, exist_ok=True)
    strings = load_strings()
    out = []
    for e in ENTITIES:
        img = fit(e['icon']())
        img.save(os.path.join(icons, e['id'] + '.png'), optimize=True)
        tip, stats, flavor = (almanac(strings, e['key']) if e.get('key') else ('', [], ''))
        goal = bool(e.get('key')) and e['id'] not in ('crazy_dave', 'taco')
        out.append(dict(id=e['id'], name=e['name'], mode=e['mode'], goal=goal,
                        tip=tip or e.get('tip', ''), stats=stats, flavor=flavor))
        print('icon', e['id'])
    snd = os.path.join(ASSETS, 'sounds')
    os.makedirs(snd, exist_ok=True)
    for s in SOUNDS:
        shutil.copy(pak('sounds', s + '.ogg'), snd)
    bg = os.path.join(ASSETS, 'images')
    os.makedirs(bg, exist_ok=True)
    for b in BACKGROUNDS:
        im = load_image('images/' + b)
        name = os.path.splitext(b)[0]
        if b.endswith('.jpg') and not os.path.exists(pak('images', name + '_.png')):
            im.convert('RGB').save(os.path.join(bg, name + '.jpg'), quality=88)
        else:
            im.save(os.path.join(bg, name + '.png'), optimize=True)
    with open(os.path.join(ROOT, 'js', 'entities.js'), 'w') as f:
        f.write('// Generated by tools/build_assets.py from main.pak - do not edit by hand.\n')
        f.write('window.ENTITIES = ' + json.dumps(out, indent=1, ensure_ascii=False) + ';\n')
    print(f'wrote {len(out)} entities')


if __name__ == '__main__':
    main()
