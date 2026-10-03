"""Minimal renderer for PvZ .reanim (text) files -> still PIL images."""
import math, os, re
from PIL import Image

TAG = re.compile(r'<(x|y|kx|ky|sx|sy|f|i|a)>([^<]*)</\1>')


def parse(path):
    txt = open(path, encoding='latin1').read()
    tracks = []
    for tm in re.finditer(r'<track>(.*?)</track>', txt, re.S):
        body = tm.group(1)
        name = re.search(r'<name>(.*?)</name>', body).group(1)
        frames = []
        cur = dict(x=0.0, y=0.0, kx=0.0, ky=0.0, sx=1.0, sy=1.0, f=0, i=None, a=1.0)
        for t in re.findall(r'<t>(.*?)</t>|<t\s*/>', body, re.S):
            for k, v in TAG.findall(t):
                if k == 'i':
                    cur[k] = v
                elif k == 'f':
                    cur[k] = int(v)
                else:
                    cur[k] = float(v)
            frames.append(dict(cur))
        tracks.append((name, frames))
    return tracks


def anim_range(tracks, anim):
    for name, frames in tracks:
        if name == anim:
            vis = [i for i, fr in enumerate(frames) if fr['f'] != -1]
            if vis:
                return vis[0], vis[-1]
    return None


_imgcache = {}


def load_part(imgdir, ident):
    key = ident.replace('IMAGE_REANIM_', '').lower()
    if key not in _imgcache:
        idx = {}
        for f in os.listdir(imgdir):
            if not f.lower().endswith(('.png', '.jpg', '.gif')):
                continue
            idx.setdefault(f.lower().rsplit('.', 1)[0], f)
        fn = idx.get(key)
        img = None
        if fn:
            img = Image.open(os.path.join(imgdir, fn)).convert('RGBA')
            mask = idx.get(key + '_')  # PopCap separate alpha mask
            if mask:
                img.putalpha(Image.open(os.path.join(imgdir, mask)).convert('L'))
        _imgcache[key] = img
    return _imgcache[key]


def render(path, imgdir, anim=None, frame_offset=0, hide=(), show_only=None,
           extra=(), scale=2.0, size=None):
    """extra: list of (path, anim, hide) reanims drawn into same canvas (e.g. heads)."""
    tracks = parse(path)
    if anim is None:
        for cand in ('anim_full_idle', 'anim_idle', 'anim_walk', 'anim_idle2'):
            if anim_range(tracks, cand):
                anim = cand
                break
    anims = anim if isinstance(anim, (list, tuple)) else [anim]
    starts = []
    for a in anims:
        rng = anim_range(tracks, a) if a else None
        starts.append((rng[0] if rng else 0) + frame_offset)
    hide_re = [re.compile(h, re.I) for h in hide]
    show_re = [re.compile(h, re.I) for h in show_only] if show_only else None
    layers = []
    for name, frames in tracks:
        # use the first requested anim in which this track is visible
        fr = None
        for fi in starts:
            if fi < len(frames) and frames[fi]['i'] and frames[fi]['f'] != -1:
                fr = frames[fi]
                break
        if fr is None:
            continue
        if any(h.search(name) or h.search(fr['i']) for h in hide_re):
            continue
        if show_re and not any(h.search(name) or h.search(fr['i']) for h in show_re):
            continue
        img = load_part(imgdir, fr['i'])
        if img is None:
            continue
        ax = -math.radians(fr['kx'])
        ay = -math.radians(fr['ky'])
        # forward: X = a*u + b*v + e ; Y = c*u + d*v + f
        a = math.cos(ax) * fr['sx'] * scale
        c = -math.sin(ax) * fr['sx'] * scale
        b = math.sin(ay) * fr['sy'] * scale
        d = math.cos(ay) * fr['sy'] * scale
        e, f = fr['x'] * scale, fr['y'] * scale
        layers.append((img, fr['a'], (a, b, c, d, e, f)))
    if not layers:
        return Image.new('RGBA', (1, 1), (0, 0, 0, 0))
    xs, ys = [], []
    for img, _, (a, b, c, d, e, f) in layers:
        w, h = img.size
        for u, v in ((0, 0), (w, 0), (0, h), (w, h)):
            xs.append(a * u + b * v + e)
            ys.append(c * u + d * v + f)
    x0, y0 = math.floor(min(xs)), math.floor(min(ys))
    size_ = (max(1, math.ceil(max(xs)) - x0), max(1, math.ceil(max(ys)) - y0))
    canvas = Image.new('RGBA', size_, (0, 0, 0, 0))
    for img, alpha, (a, b, c, d, e, f) in layers:
        e, f = e - x0, f - y0
        det = a * d - b * c
        if abs(det) < 1e-6:
            continue
        ia, ib, ic, id_ = d / det, -b / det, -c / det, a / det
        coeffs = (ia, ib, -(ia * e + ib * f), ic, id_, -(ic * e + id_ * f))
        part = img
        if alpha < 1.0:
            part = img.copy()
            part.putalpha(part.getchannel('A').point(lambda p: int(p * max(0.0, alpha))))
        layer = part.transform(canvas.size, Image.AFFINE, coeffs, resample=Image.BICUBIC)
        canvas = Image.alpha_composite(canvas, layer)
    bbox = canvas.getbbox()
    if bbox:
        canvas = canvas.crop(bbox)
    if size:
        w, h = canvas.size
        s = size / max(w, h)
        canvas = canvas.resize((max(1, round(w * s)), max(1, round(h * s))), Image.LANCZOS)
        out = Image.new('RGBA', (size, size), (0, 0, 0, 0))
        out.paste(canvas, ((size - canvas.size[0]) // 2, (size - canvas.size[1]) // 2))
        canvas = out
    return canvas
