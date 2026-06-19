from __future__ import annotations

from pathlib import Path
import math
import shutil
import subprocess
import json
import csv
from typing import Dict, Iterable, Tuple

import cairosvg
from PIL import Image, ImageDraw, ImageFont

ROOT = Path('/mnt/data/Setpiece_Identity_Kit_v1')
if ROOT.exists():
    shutil.rmtree(ROOT)

DIRS = {
    'logo': ROOT / '01_Logo',
    'app': ROOT / '02_App_Icon',
    'tray': ROOT / '03_Tray_States',
    'digital': ROOT / '04_Digital_Creatives',
    'motion': ROOT / '05_Motion',
    'guide': ROOT / '06_Guidelines',
    'source': ROOT / 'Source',
}
for d in DIRS.values():
    d.mkdir(parents=True, exist_ok=True)

# Core palette
COLORS = {
    'ink': '#22272B',
    'paper': '#F7F4EE',
    'mineral': '#3C6F82',
    'deep_mineral': '#243A43',
    'mist': '#DDE7E8',
    'muted': '#687278',
    'waiting': '#A36B25',
    'attention': '#6E5A8A',
    'failure': '#A84942',
    'recovery': '#45715F',
    'neutral': '#70777C',
    'white': '#FFFFFF',
    'black': '#000000',
}

STATE_COLORS_LIGHT = {
    'ready': COLORS['mineral'],
    'running': COLORS['mineral'],
    'waiting': COLORS['waiting'],
    'confirmation': COLORS['attention'],
    'failure': COLORS['failure'],
    'recovery': COLORS['recovery'],
    'paused': COLORS['waiting'],
    'stopped': COLORS['neutral'],
}
STATE_COLORS_DARK = {
    'ready': '#76AFC1',
    'running': '#76AFC1',
    'waiting': '#D5A253',
    'confirmation': '#AB94CC',
    'failure': '#E17C73',
    'recovery': '#83B29D',
    'paused': '#D5A253',
    'stopped': '#B8BEC2',
}

STATES = ['ready', 'running', 'waiting', 'confirmation', 'failure', 'recovery', 'paused', 'stopped']
TRAY_SIZES = [16, 20, 24, 32, 40, 48, 64]
APP_SIZES = [16, 20, 24, 30, 32, 36, 40, 48, 60, 64, 72, 80, 96, 128, 256, 512]

FONT_FAMILY = 'Inter Display'
FONT_PATH = '/usr/share/fonts/opentype/inter/InterDisplay-Medium.otf'
FONT_REG_PATH = '/usr/share/fonts/opentype/inter/InterDisplay-Regular.otf'


def svg_doc(body: str, width: int, height: int, viewbox: str | None = None) -> str:
    vb = viewbox or f'0 0 {width} {height}'
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="{vb}">
{body}
</svg>'''


def glyph_svg(state: str, color: str, *, mono: bool = False) -> str:
    if state == 'ready':
        return f'<rect x="10.25" y="10.25" width="3.5" height="3.5" rx="0.72" fill="{color}" transform="rotate(45 12 12)"/>'
    if state == 'running':
        return f'<path d="M 10.45 9.05 L 15.25 12 L 10.45 14.95 Z" fill="{color}"/>'
    if state == 'waiting':
        return ''.join(f'<circle cx="{x}" cy="12" r="0.86" fill="{color}"/>' for x in (9.7, 12, 14.3))
    if state == 'confirmation':
        return (f'<rect x="11.08" y="8.55" width="1.84" height="4.55" rx="0.92" fill="{color}"/>'
                f'<circle cx="12" cy="15.12" r="1.02" fill="{color}"/>')
    if state == 'failure':
        return (f'<path d="M 9.45 9.45 L 14.55 14.55 M 14.55 9.45 L 9.45 14.55" '
                f'stroke="{color}" stroke-width="2.0" stroke-linecap="round"/>')
    if state == 'recovery':
        return (f'<path d="M 9.05 10.2 C 10.55 8.55 13.1 8.35 14.85 9.85 '
                f'C 16.55 11.35 16.7 14 15.1 15.65 C 13.55 17.15 11.1 17.35 9.35 16.05" '
                f'fill="none" stroke="{color}" stroke-width="1.62" stroke-linecap="round"/>'
                f'<path d="M 8.35 8.65 L 8.72 11.55 L 11.3 10.35 Z" fill="{color}"/>')
    if state == 'paused':
        return (f'<rect x="9.58" y="9.0" width="1.82" height="6" rx="0.78" fill="{color}"/>'
                f'<rect x="12.6" y="9.0" width="1.82" height="6" rx="0.78" fill="{color}"/>')
    if state == 'stopped':
        return f'<rect x="9.75" y="9.75" width="4.5" height="4.5" rx="0.7" fill="{color}"/>'
    raise ValueError(state)


def mark_group(*, state: str = 'ready', outer: str = COLORS['ink'], cue: str = COLORS['mineral'], stroke: float = 2.55, transform: str = '') -> str:
    # Two opposing pieces form a quiet abstract S around a replaceable center cue.
    paths = f'''
<path d="M 19 4.2 H 8.3 C 5.9 4.2 4.2 5.9 4.2 8.3 V 10.4 H 8.6"
      fill="none" stroke="{outer}" stroke-width="{stroke}" stroke-linecap="round" stroke-linejoin="round"/>
<path d="M 5 19.8 H 15.7 C 18.1 19.8 19.8 18.1 19.8 15.7 V 13.6 H 15.4"
      fill="none" stroke="{outer}" stroke-width="{stroke}" stroke-linecap="round" stroke-linejoin="round"/>
{glyph_svg(state, cue)}
'''
    return f'<g{(" transform=\"" + transform + "\"") if transform else ""}>{paths}</g>'


def write_svg(path: Path, body: str, width: int, height: int, viewbox: str | None = None) -> None:
    path.write_text(svg_doc(body, width, height, viewbox), encoding='utf-8')


def render_svg(svg_path: Path, png_path: Path, width: int, height: int) -> None:
    cairosvg.svg2png(url=str(svg_path), write_to=str(png_path), output_width=width, output_height=height)


def exact_stroke_for_px(px: int) -> float:
    if px <= 16:
        return 2.95
    if px <= 20:
        return 2.75
    if px <= 24:
        return 2.6
    if px <= 32:
        return 2.52
    return 2.45


def create_tray_icon_png(state: str, px: int, outer: str, cue: str, path: Path) -> None:
    stroke = exact_stroke_for_px(px)
    body = mark_group(state=state, outer=outer, cue=cue, stroke=stroke)
    svg = svg_doc(body, 24, 24, '0 0 24 24')
    cairosvg.svg2png(bytestring=svg.encode('utf-8'), write_to=str(path), output_width=px, output_height=px)


def combine_ico(png_paths: Iterable[Path], ico_path: Path) -> None:
    cmd = ['/opt/imagemagick/bin/convert', *[str(p) for p in png_paths], str(ico_path)]
    subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)


def make_logo_svgs() -> None:
    # Symbol masters
    write_svg(DIRS['logo'] / 'setpiece_mark_primary.svg', mark_group(), 24, 24, '0 0 24 24')
    write_svg(DIRS['logo'] / 'setpiece_mark_monochrome_dark.svg', mark_group(outer=COLORS['ink'], cue=COLORS['ink']), 24, 24, '0 0 24 24')
    write_svg(DIRS['logo'] / 'setpiece_mark_monochrome_light.svg', mark_group(outer=COLORS['paper'], cue=COLORS['paper']), 24, 24, '0 0 24 24')

    # Wordmark and lockups; use dotless i plus a diamond cue over the i.
    font_size = 72
    x_text = 120
    baseline = 84
    f = ImageFont.truetype(FONT_PATH, font_size)
    cue_x = x_text + float(f.getlength('Setp')) + float(f.getlength('ı')) / 2
    cue_y = 32.5

    def logo_body(bg: str | None, ink: str, accent: str, stacked: bool = False, wordmark_only: bool = False) -> Tuple[str, int, int]:
        if stacked:
            w, h = 420, 300
            bgrect = f'<rect width="{w}" height="{h}" fill="{bg}"/>' if bg else ''
            body = bgrect
            body += mark_group(outer=ink, cue=accent, transform='translate(162 26) scale(4)')
            body += f'<text x="58" y="250" font-family="{FONT_FAMILY}" font-weight="500" font-size="72" fill="{ink}">Setpıece</text>'
            # stacked text x is 58, so recalc diamond
            cx = 58 + float(f.getlength('Setp')) + float(f.getlength('ı'))/2
            body += f'<rect x="{cx-3}" y="195" width="6" height="6" rx="1" fill="{accent}" transform="rotate(45 {cx} 198)"/>'
            return body, w, h
        if wordmark_only:
            w, h = 360, 120
            bgrect = f'<rect width="{w}" height="{h}" fill="{bg}"/>' if bg else ''
            body = bgrect + f'<text x="18" y="84" font-family="{FONT_FAMILY}" font-weight="500" font-size="72" fill="{ink}">Setpıece</text>'
            cx = 18 + float(f.getlength('Setp')) + float(f.getlength('ı'))/2
            body += f'<rect x="{cx-3}" y="29.5" width="6" height="6" rx="1" fill="{accent}" transform="rotate(45 {cx} 32.5)"/>'
            return body, w, h
        w, h = 520, 120
        bgrect = f'<rect width="{w}" height="{h}" fill="{bg}"/>' if bg else ''
        body = bgrect
        body += mark_group(outer=ink, cue=accent, transform='translate(18 18) scale(3.5)')
        body += f'<text x="{x_text}" y="{baseline}" font-family="{FONT_FAMILY}" font-weight="500" font-size="{font_size}" fill="{ink}">Setpıece</text>'
        body += f'<rect x="{cue_x-3}" y="29.5" width="6" height="6" rx="1" fill="{accent}" transform="rotate(45 {cue_x} {cue_y})"/>'
        return body, w, h

    temp_specs = [
        ('setpiece_logo_horizontal_primary', None, COLORS['ink'], COLORS['mineral'], False, False),
        ('setpiece_logo_horizontal_reverse', COLORS['deep_mineral'], COLORS['paper'], '#76AFC1', False, False),
        ('setpiece_logo_stacked_primary', None, COLORS['ink'], COLORS['mineral'], True, False),
        ('setpiece_wordmark_primary', None, COLORS['ink'], COLORS['mineral'], False, True),
        ('setpiece_wordmark_monochrome_dark', None, COLORS['ink'], COLORS['ink'], False, True),
        ('setpiece_wordmark_monochrome_light', COLORS['deep_mineral'], COLORS['paper'], COLORS['paper'], False, True),
    ]

    for name, bg, ink, accent, stacked, wordmark_only in temp_specs:
        body, w, h = logo_body(bg, ink, accent, stacked, wordmark_only)
        temp = DIRS['source'] / f'{name}_text.svg'
        write_svg(temp, body, w, h)
        final = DIRS['logo'] / f'{name}.svg'
        subprocess.run(['inkscape', '-T', '-l', '-o', str(final), str(temp)], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        # PNG convenience preview at 2x
        render_svg(final, DIRS['logo'] / f'{name}.png', w * 2, h * 2)


def make_app_icons() -> None:
    # Plated application icon, intentionally distinct from monochrome tray microglyph.
    body = f'''
<rect x="2" y="2" width="60" height="60" rx="15" fill="{COLORS['deep_mineral']}"/>
<rect x="2.5" y="2.5" width="59" height="59" rx="14.5" fill="none" stroke="#35515C" stroke-width="1"/>
{mark_group(outer=COLORS['paper'], cue='#7DB5C6', stroke=2.55, transform='translate(8 8) scale(2)')}
'''
    master = DIRS['app'] / 'setpiece_app_icon_master.svg'
    write_svg(master, body, 64, 64, '0 0 64 64')

    pngs = []
    for size in APP_SIZES:
        p = DIRS['app'] / f'setpiece_app_icon_{size}.png'
        render_svg(master, p, size, size)
        pngs.append(p)

    # Windows multi-resolution ICO uses exact generated PNGs.
    ico_sizes = [16, 24, 32, 48, 256]
    combine_ico([DIRS['app'] / f'setpiece_app_icon_{s}.png' for s in ico_sizes], DIRS['app'] / 'setpiece_app_icon.ico')

    # Unplated foreground for packaging systems that supply their own background.
    unplated = DIRS['app'] / 'setpiece_app_icon_unplated.svg'
    write_svg(unplated, mark_group(outer=COLORS['paper'], cue='#7DB5C6', stroke=2.55), 24, 24, '0 0 24 24')


def make_tray_icons() -> None:
    variants = {
        'for_light_background': (COLORS['ink'], STATE_COLORS_LIGHT, False),
        'for_dark_background': (COLORS['paper'], STATE_COLORS_DARK, False),
        'monochrome_black': (COLORS['black'], {s: COLORS['black'] for s in STATES}, True),
        'monochrome_white': (COLORS['white'], {s: COLORS['white'] for s in STATES}, True),
    }
    for variant, (outer, cue_map, _mono) in variants.items():
        vdir = DIRS['tray'] / variant
        vdir.mkdir(parents=True, exist_ok=True)
        for state in STATES:
            sdir = vdir / state
            sdir.mkdir(parents=True, exist_ok=True)
            pngs = []
            for size in TRAY_SIZES:
                p = sdir / f'setpiece_tray_{state}_{size}.png'
                create_tray_icon_png(state, size, outer, cue_map[state], p)
                pngs.append(p)
            combine_ico(pngs, sdir / f'setpiece_tray_{state}.ico')
            # Editable master per state/variant
            write_svg(sdir / f'setpiece_tray_{state}_master.svg', mark_group(state=state, outer=outer, cue=cue_map[state]), 24, 24, '0 0 24 24')


def make_digital_creatives() -> None:
    app_master = DIRS['app'] / 'setpiece_app_icon_master.svg'
    # Favicon from app icon
    for size in (16, 32, 48):
        render_svg(app_master, DIRS['digital'] / f'favicon_{size}.png', size, size)
    combine_ico([DIRS['digital'] / f'favicon_{s}.png' for s in (16,32,48)], DIRS['digital'] / 'favicon.ico')
    shutil.copy2(DIRS['logo'] / 'setpiece_mark_primary.svg', DIRS['digital'] / 'favicon.svg')

    # Social/avatar tile
    render_svg(app_master, DIRS['digital'] / 'setpiece_avatar_512.png', 512, 512)

    # Header card
    header = f'''
<rect width="1600" height="400" fill="{COLORS['paper']}"/>
<path d="M 1130 -30 C 1290 35 1425 110 1600 270 V 400 H 990 C 1035 238 1075 92 1130 -30 Z" fill="{COLORS['mist']}"/>
{mark_group(outer=COLORS['ink'], cue=COLORS['mineral'], stroke=2.55, transform='translate(1120 68) scale(10)')}
<text x="120" y="180" font-family="{FONT_FAMILY}" font-size="92" font-weight="500" fill="{COLORS['ink']}">Setpıece</text>
<rect x="360" y="111" width="8" height="8" rx="1.4" fill="{COLORS['mineral']}" transform="rotate(45 364 115)"/>
<text x="124" y="245" font-family="Inter" font-size="30" font-weight="400" fill="{COLORS['muted']}">Everything in place. Ready to run.</text>
'''
    header_svg = DIRS['digital'] / 'setpiece_brand_header_1600x400.svg'
    write_svg(header_svg, header, 1600, 400)
    render_svg(header_svg, DIRS['digital'] / 'setpiece_brand_header_1600x400.png', 1600, 400)

    # Social card / Open Graph
    social = f'''
<rect width="1200" height="630" fill="{COLORS['deep_mineral']}"/>
<path d="M 815 0 H 1200 V 630 H 560 C 650 430 735 205 815 0 Z" fill="#2E4A55"/>
{mark_group(outer=COLORS['paper'], cue='#7DB5C6', stroke=2.55, transform='translate(765 115) scale(15)')}
<text x="90" y="285" font-family="{FONT_FAMILY}" font-size="104" font-weight="500" fill="{COLORS['paper']}">Setpıece</text>
<rect x="354" y="206" width="9" height="9" rx="1.4" fill="#7DB5C6" transform="rotate(45 358.5 210.5)"/>
<text x="96" y="360" font-family="Inter" font-size="34" fill="#DDE7E8">Everything in place.</text>
<text x="96" y="405" font-family="Inter" font-size="34" fill="#DDE7E8">Ready to run.</text>
'''
    social_svg = DIRS['digital'] / 'setpiece_social_card_1200x630.svg'
    write_svg(social_svg, social, 1200, 630)
    render_svg(social_svg, DIRS['digital'] / 'setpiece_social_card_1200x630.png', 1200, 630)

    # Optional package/file icon (format name intentionally generic until extension is selected)
    file_body = f'''
<path d="M 13 4 H 36 L 51 19 V 60 H 13 C 9.7 60 7 57.3 7 54 V 10 C 7 6.7 9.7 4 13 4 Z" fill="{COLORS['paper']}" stroke="{COLORS['ink']}" stroke-width="3"/>
<path d="M 36 4 V 19 H 51" fill="{COLORS['mist']}" stroke="{COLORS['ink']}" stroke-width="3" stroke-linejoin="round"/>
{mark_group(outer=COLORS['ink'], cue=COLORS['mineral'], stroke=2.7, transform='translate(13 25) scale(1.55)')}
'''
    file_svg = DIRS['digital'] / 'setpiece_package_file_icon_master.svg'
    write_svg(file_svg, file_body, 64, 64, '0 0 64 64')
    file_pngs=[]
    for size in (16,24,32,48,64,128,256):
        p=DIRS['digital']/f'setpiece_package_file_icon_{size}.png'
        render_svg(file_svg,p,size,size)
        file_pngs.append(p)
    combine_ico([DIRS['digital']/f'setpiece_package_file_icon_{s}.png' for s in (16,24,32,48,256)], DIRS['digital']/ 'setpiece_package_file_icon.ico')


def make_motion_assets() -> None:
    # Four-frame storyboard and a restrained assembly GIF for launch/about use only.
    frame_w, frame_h = 280, 240
    body = [f'<rect width="1200" height="340" fill="{COLORS["paper"]}"/>',
            f'<text x="60" y="48" font-family="Inter" font-size="26" font-weight="600" fill="{COLORS["ink"]}">Setpiece motion signature</text>',
            f'<text x="60" y="77" font-family="Inter" font-size="14" fill="{COLORS["muted"]}">Two pieces settle; the current cue appears. No bounce, glow, or perpetual motion.</text>']
    captions=['1 · Establish', '2 · Arrange', '3 · Cue', '4 · Ready']
    for i in range(4):
        x=60+i*285
        body.append(f'<rect x="{x}" y="105" width="250" height="190" rx="16" fill="#FFFFFF" stroke="#E2DDD4"/>')
        if i==0:
            g=f'''<path d="M 19 4.2 H 8.3 C 5.9 4.2 4.2 5.9 4.2 8.3 V 10.4 H 8.6" fill="none" stroke="{COLORS['ink']}" stroke-width="2.55" stroke-linecap="round" stroke-linejoin="round"/>'''
        elif i==1:
            g=f'''<path d="M 19 4.2 H 8.3 C 5.9 4.2 4.2 5.9 4.2 8.3 V 10.4 H 8.6" fill="none" stroke="{COLORS['ink']}" stroke-width="2.55" stroke-linecap="round" stroke-linejoin="round"/><path d="M 5 19.8 H 15.7 C 18.1 19.8 19.8 18.1 19.8 15.7 V 13.6 H 15.4" fill="none" stroke="{COLORS['ink']}" stroke-width="2.55" stroke-linecap="round" stroke-linejoin="round"/>'''
        elif i==2:
            g=mark_group(outer=COLORS['ink'], cue=COLORS['mineral'])
        else:
            g=mark_group(outer=COLORS['ink'], cue=COLORS['mineral'])
        body.append(f'<g transform="translate({x+61} 128) scale(5.3)">{g}</g>')
        body.append(f'<text x="{x+22}" y="280" font-family="Inter" font-size="13" font-weight="600" fill="{COLORS["muted"]}">{captions[i]}</text>')
    storyboard=DIRS['motion']/ 'setpiece_motion_storyboard.svg'
    write_svg(storyboard, ''.join(body), 1200, 340)
    render_svg(storyboard, DIRS['motion']/ 'setpiece_motion_storyboard.png', 1200, 340)

    # Animated GIF. Rasterize a clean 256 canvas sequence.
    frames=[]
    durations=[]
    for idx in range(18):
        t=idx/17
        # piece opacity and translation use smoothstep
        def smooth(a,b,x):
            if x<=a: return 0.0
            if x>=b: return 1.0
            u=(x-a)/(b-a)
            return u*u*(3-2*u)
        top=smooth(0.00,0.42,t)
        bottom=smooth(0.18,0.62,t)
        cue=smooth(0.52,0.84,t)
        top_dx=(1-top)*(-2.4)
        bottom_dx=(1-bottom)*(2.4)
        svg=f'''<svg xmlns="http://www.w3.org/2000/svg" width="256" height="256" viewBox="0 0 256 256">
<rect width="256" height="256" fill="{COLORS['paper']}"/>
<g transform="translate(32 32) scale(8)">
<g opacity="{top:.3f}" transform="translate({top_dx:.3f} 0)"><path d="M 19 4.2 H 8.3 C 5.9 4.2 4.2 5.9 4.2 8.3 V 10.4 H 8.6" fill="none" stroke="{COLORS['ink']}" stroke-width="2.55" stroke-linecap="round" stroke-linejoin="round"/></g>
<g opacity="{bottom:.3f}" transform="translate({bottom_dx:.3f} 0)"><path d="M 5 19.8 H 15.7 C 18.1 19.8 19.8 18.1 19.8 15.7 V 13.6 H 15.4" fill="none" stroke="{COLORS['ink']}" stroke-width="2.55" stroke-linecap="round" stroke-linejoin="round"/></g>
<g opacity="{cue:.3f}" transform="translate(12 12) scale({0.75+0.25*cue:.3f}) translate(-12 -12)">{glyph_svg('ready', COLORS['mineral'])}</g>
</g></svg>'''
        png=DIRS['source']/f'motion_{idx:02d}.png'
        cairosvg.svg2png(bytestring=svg.encode(), write_to=str(png), output_width=256, output_height=256)
        frames.append(Image.open(png).convert('RGBA'))
        durations.append(45 if idx<17 else 900)
    frames[0].save(DIRS['motion']/ 'setpiece_logo_assembly.gif', save_all=True, append_images=frames[1:], duration=durations, loop=0, disposal=2)


def make_contact_sheet() -> None:
    # Comprehensive review board.
    w,h=1600,1180
    body=[f'<rect width="{w}" height="{h}" fill="{COLORS["paper"]}"/>',
          f'<text x="70" y="68" font-family="Inter" font-size="34" font-weight="650" fill="{COLORS["ink"]}">Setpiece identity system · v1</text>',
          f'<text x="70" y="102" font-family="Inter" font-size="16" fill="{COLORS["muted"]}">Two arranged pieces form an abstract S around a stateful center cue.</text>']
    # Primary lockup area
    body += [f'<rect x="70" y="135" width="940" height="240" rx="20" fill="#FFFFFF" stroke="#E2DDD4"/>',
             mark_group(outer=COLORS['ink'], cue=COLORS['mineral'], transform='translate(110 175) scale(7)'),
             f'<text x="340" y="285" font-family="{FONT_FAMILY}" font-size="108" font-weight="500" fill="{COLORS["ink"]}">Setpıece</text>']
    ff=ImageFont.truetype(FONT_PATH,108)
    cx=340+float(ff.getlength('Setp'))+float(ff.getlength('ı'))/2
    body.append(f'<rect x="{cx-4.5}" y="202" width="9" height="9" rx="1.5" fill="{COLORS["mineral"]}" transform="rotate(45 {cx} 206.5)"/>')
    body.append(f'<text x="344" y="332" font-family="Inter" font-size="20" fill="{COLORS["muted"]}">Everything in place. Ready to run.</text>')
    # App icon
    body.append(f'<rect x="1050" y="135" width="480" height="240" rx="20" fill="#FFFFFF" stroke="#E2DDD4"/>')
    body.append(f'<rect x="1100" y="175" width="160" height="160" rx="40" fill="{COLORS["deep_mineral"]}"/>')
    body.append(mark_group(outer=COLORS['paper'], cue='#7DB5C6', transform='translate(1124 199) scale(4.65)'))
    body.append(f'<text x="1300" y="230" font-family="Inter" font-size="17" font-weight="650" fill="{COLORS["ink"]}">Application icon</text>')
    body.append(f'<text x="1300" y="262" font-family="Inter" font-size="14" fill="{COLORS["muted"]}">Plated for Start, taskbar,</text><text x="1300" y="283" font-family="Inter" font-size="14" fill="{COLORS["muted"]}">installer, and Store.</text>')
    # Tray states
    body.append(f'<text x="70" y="438" font-family="Inter" font-size="23" font-weight="650" fill="{COLORS["ink"]}">Tray state family</text>')
    labels={'ready':'Ready','running':'Running','waiting':'Waiting','confirmation':'Needs attention','failure':'Failed','recovery':'Recovering','paused':'Paused','stopped':'Stopped*'}
    for i,state in enumerate(STATES):
        x=70+(i%4)*375; y=470+(i//4)*165
        body.append(f'<rect x="{x}" y="{y}" width="345" height="135" rx="16" fill="#FFFFFF" stroke="#E2DDD4"/>')
        body.append(mark_group(state=state, outer=COLORS['ink'], cue=STATE_COLORS_LIGHT[state], transform=f'translate({x+32} {y+30}) scale(3.1)'))
        body.append(f'<text x="{x+125}" y="{y+56}" font-family="Inter" font-size="17" font-weight="650" fill="{COLORS["ink"]}">{labels[state]}</text>')
        desc={'ready':'Available; no run active.','running':'A sequence is executing.','waiting':'Blocked by a dependency.','confirmation':'A decision is required.','failure':'Execution stopped unsuccessfully.','recovery':'Restoring a checkpoint.','paused':'Stopped intentionally, resumable.','stopped':'Supplemental; normally returns to Ready.'}[state]
        body.append(f'<text x="{x+125}" y="{y+82}" font-family="Inter" font-size="13" fill="{COLORS["muted"]}">{desc}</text>')
        # micro sizes
        body.append(mark_group(state=state, outer=COLORS['ink'], cue=STATE_COLORS_LIGHT[state], transform=f'translate({x+129} {y+94}) scale(0.67)'))
        body.append(mark_group(state=state, outer=COLORS['ink'], cue=STATE_COLORS_LIGHT[state], transform=f'translate({x+167} {y+91}) scale(0.84)'))
        body.append(mark_group(state=state, outer=COLORS['ink'], cue=STATE_COLORS_LIGHT[state], transform=f'translate({x+211} {y+88}) scale(1.0)'))
    # Palette and rules
    body.append(f'<text x="70" y="835" font-family="Inter" font-size="23" font-weight="650" fill="{COLORS["ink"]}">Palette</text>')
    pal=[('Ink',COLORS['ink']),('Paper',COLORS['paper']),('Mineral',COLORS['mineral']),('Waiting',COLORS['waiting']),('Attention',COLORS['attention']),('Failure',COLORS['failure']),('Recovery',COLORS['recovery'])]
    for i,(name,c) in enumerate(pal):
        x=70+i*205
        body.append(f'<rect x="{x}" y="865" width="170" height="86" rx="12" fill="{c}" stroke="#D8D2C8"/>')
        txt=COLORS['paper'] if c not in [COLORS['paper']] else COLORS['ink']
        body.append(f'<text x="{x+14}" y="926" font-family="Inter" font-size="13" font-weight="650" fill="{txt}">{name}</text>')
        body.append(f'<text x="{x+14}" y="945" font-family="Inter Mono" font-size="11" fill="{txt}">{c}</text>')
    body.append(f'<text x="70" y="1012" font-family="Inter" font-size="18" font-weight="650" fill="{COLORS["ink"]}">Identity rules</text>')
    rules=['Keep the two outer pieces stable across states.','Change only the center cue for tray status.','Use the app icon for brand; use Fluent glyphs for ordinary commands.','No film frames, clapperboards, spotlights, neon, or perpetual animation.']
    for i,r in enumerate(rules):
        y=1045+i*28
        body.append(f'<circle cx="82" cy="{y-5}" r="3" fill="{COLORS["mineral"]}"/><text x="98" y="{y}" font-family="Inter" font-size="14" fill="{COLORS["muted"]}">{r}</text>')
    sheet=DIRS['guide']/ 'setpiece_identity_contact_sheet.svg'
    write_svg(sheet, ''.join(body), w,h)
    render_svg(sheet, DIRS['guide']/ 'setpiece_identity_contact_sheet.png', w,h)


def make_tokens_and_guides() -> None:
    tokens={
        'name':'Setpiece',
        'brand_definition':'A carefully arranged, repeatable sequence of coordinated actions.',
        'tagline':'Everything in place. Ready to run.',
        'mark_concept':'Two opposing pieces form an abstract S around a replaceable center cue.',
        'colors':COLORS,
        'tray_state_colors_light':STATE_COLORS_LIGHT,
        'tray_state_colors_dark':STATE_COLORS_DARK,
        'tray_states':{
            'ready':'diamond cue',
            'running':'play cue',
            'waiting':'ellipsis cue',
            'confirmation':'exclamation cue',
            'failure':'x cue',
            'recovery':'return arrow cue',
            'paused':'pause cue',
            'stopped':'square cue; supplemental only',
        },
        'font_recommendations':{
            'brand_wordmark':'Inter Display Medium (converted to outlines in supplied SVGs)',
            'product_ui':'Segoe UI Variable',
            'diagnostics':'Cascadia Mono',
        },
        'required_windows_icon_sizes':{
            'minimum_app_icon':[16,24,32,48,256],
            'tray_scale_set':[16,20,24,32,40,48,64],
        },
    }
    (DIRS['guide']/ 'setpiece_design_tokens.json').write_text(json.dumps(tokens,indent=2),encoding='utf-8')

    readme=f'''# Setpiece identity kit — v1

## Brand idea

**Setpiece** means a carefully arranged, repeatable sequence of coordinated actions.

The mark uses two opposing pieces that settle around a central cue. Together they create an abstract **S**, an open path, and a stable container for operational state.

**Tagline:** Everything in place. Ready to run.

## Included

- Primary, reverse, stacked, monochrome, and wordmark SVG/PNG assets
- Windows application icon master, PNG size set, and multi-resolution ICO
- Tray icons for Ready, Running, Waiting, Confirmation, Failure, Recovery, Paused, and Stopped
- Light-background, dark-background, black, and white tray variants
- Favicon, social avatar, documentation header, social card, and optional package/file icon
- Motion storyboard and restrained logo-assembly GIF
- Contact sheet, design tokens, and implementation manifest

## Logo behavior

The two outer pieces never change. They are the product identity. The center cue may change only when the mark is functioning as an operational status icon.

Use the static diamond cue for all brand, marketing, installer, documentation, and Store contexts.

## Tray mapping

| State | Center cue | Persistent tray use |
|---|---|---|
| Ready | Diamond | Yes |
| Running | Play | Yes |
| Waiting | Ellipsis | Yes |
| Confirmation | Exclamation | Yes |
| Failure | X | Yes |
| Recovery | Return arrow | Yes |
| Paused | Pause bars | Yes, when explicitly paused |
| Stopped | Square | No by default; return to Ready after the run is recorded |

A non-blocking warning remains in the tooltip or flyout. A warning requiring action maps to Confirmation. Completion returns to Ready.

## Tray theme selection

- `for_light_background`: dark outer mark with semantic center cue
- `for_dark_background`: light outer mark with brighter semantic center cue
- `monochrome_black` and `monochrome_white`: High Contrast and fallback assets

The tooltip remains authoritative. The icon communicates only broad state and urgency.

## Clear space and minimum size

- Brand lockups: clear space equal to the center diamond's diagonal on all sides.
- Symbol-only brand use: 20 px minimum for ordinary digital use.
- Tray use: supplied exact-size assets down to 16 px.
- Do not mechanically shrink the plated application icon into the tray.

## Typography

- Wordmark: outlined Inter Display Medium with a custom diamond over the `i`.
- Product UI: Segoe UI Variable.
- Paths, timestamps, and diagnostics: Cascadia Mono.

Font files are not included.

## Color

The identity is primarily graphite, warm paper, and mineral blue. State colors are secondary and never carry meaning alone.

## Motion

The brand motion is an assembly, not a performance:

1. The upper piece establishes position.
2. The lower piece settles opposite it.
3. The center cue appears.
4. The mark rests.

Target duration: 520–680 ms. Use once on onboarding, About, or launch marketing. Never animate continuously in the notification area.

## Interface icon policy

Use this custom family only for:

- Product identity
- Tray state
- Application/installer/Store icon
- Notification identity
- Optional Setpiece package/file type

Use Segoe Fluent Icons for ordinary actions such as Open, Edit, Settings, Retry, Delete, Pause, and Search.

## Prohibited treatments

- Film frames, clapperboards, cameras, curtains, spotlights, or “take” language
- Gamer neon, glow, chromatic aberration, or RGB effects
- Arbitrary gradients or glass effects
- A play triangle as the standalone logo
- State communicated through color alone
- Distortion, rotation, outline changes, or adding badges to the outer pieces
- Decorative animation in the tray

## Windows production notes

The kit includes exact tray sizes at 16, 20, 24, 32, 40, 48, and 64 px and a Windows ICO with 16, 24, 32, 48, and 256 px application assets. Select light/dark tray assets based on the actual taskbar background and provide black/white fallbacks for High Contrast.

Sources consulted for Windows production requirements:

- Microsoft Learn — Construct your Windows app's icon: https://learn.microsoft.com/windows/apps/design/iconography/app-icon-construction
- Microsoft Learn — Notifications and the Notification Area: https://learn.microsoft.com/windows/win32/shell/notification-area
- Microsoft Learn — Design guidelines for Windows app icons: https://learn.microsoft.com/windows/apps/design/iconography/app-icon-design

## Status

This is a production-shaped **v1 direction**, not a legal trademark clearance. Run small-size recognition, state-comprehension, and confusion testing before freezing geometry.
'''
    (ROOT/'README.md').write_text(readme,encoding='utf-8')

def make_preview_microgrid() -> None:
    # Enlarged nearest-neighbor check of exact raster assets at 16/20/24 px.
    cell=150
    w=70+len(STATES)*cell
    h=360
    canvas=Image.new('RGB',(w,h),COLORS['paper'])
    draw=ImageDraw.Draw(canvas)
    font=ImageFont.truetype(FONT_REG_PATH,16)
    small=ImageFont.truetype(FONT_REG_PATH,13)
    draw.text((30,24),'Exact-size tray raster check',font=ImageFont.truetype(FONT_PATH,24),fill=COLORS['ink'])
    for i,state in enumerate(STATES):
        x=40+i*cell
        draw.text((x,70),state,font=font,fill=COLORS['ink'])
        for j,size in enumerate((16,20,24)):
            p=DIRS['tray']/ 'for_light_background'/state/f'setpiece_tray_{state}_{size}.png'
            im=Image.open(p).convert('RGBA')
            zoom=4
            large=im.resize((size*zoom,size*zoom),Image.Resampling.NEAREST)
            canvas.alpha_composite(large,(x,105+j*78)) if canvas.mode=='RGBA' else canvas.paste(large,(x,105+j*78),large)
            draw.text((x+size*zoom+8,112+j*78),f'{size}px',font=small,fill=COLORS['muted'])
    canvas.save(DIRS['guide']/ 'tray_microgrid.png')



def make_tray_context_preview() -> None:
    width, height = 1280, 420
    canvas = Image.new('RGB', (width, height), COLORS['paper'])
    draw = ImageDraw.Draw(canvas)
    title = ImageFont.truetype(FONT_PATH, 26)
    label = ImageFont.truetype(FONT_PATH, 16)
    small = ImageFont.truetype(FONT_REG_PATH, 13)
    draw.text((42, 28), 'Tray icons in context', font=title, fill=COLORS['ink'])
    draw.text((42, 65), 'Exact 16 px assets shown at 4× for inspection; actual implementation remains static.', font=small, fill=COLORS['muted'])
    rows=[('Light taskbar', '#F3F3F3', 'for_light_background'), ('Dark taskbar', '#202020', 'for_dark_background')]
    for row,(row_name,bg,variant) in enumerate(rows):
        y=112+row*145
        draw.rounded_rectangle((42,y,1238,y+105), radius=18, fill=bg)
        draw.text((65,y+18),row_name,font=label,fill=('#22272B' if row==0 else '#F7F4EE'))
        for i,state in enumerate(['ready','running','waiting','confirmation','failure','recovery']):
            p=DIRS['tray']/variant/state/f'setpiece_tray_{state}_16.png'
            im=Image.open(p).convert('RGBA').resize((64,64),Image.Resampling.NEAREST)
            x=250+i*155
            canvas.paste(im,(x,y+19),im)
            draw.text((x+72,y+41),state,font=small,fill=('#4A5054' if row==0 else '#D7D7D7'))
    canvas.save(DIRS['guide']/ 'tray_context_preview.png')


def make_manifest() -> None:
    rows=[]
    for p in sorted(ROOT.rglob('*')):
        if p.is_file():
            rows.append({'path':str(p.relative_to(ROOT)),'format':p.suffix.lower().lstrip('.'),'bytes':p.stat().st_size})
    with (DIRS['guide']/ 'asset_manifest.csv').open('w',newline='',encoding='utf-8') as f:
        w=csv.DictWriter(f,fieldnames=['path','format','bytes'])
        w.writeheader(); w.writerows(rows)


def copy_source_script() -> None:
    shutil.copy2(Path(__file__), DIRS['source']/ 'generate_assets.py')


def make_zip() -> None:
    shutil.make_archive('/mnt/data/Setpiece_Identity_Kit_v1','zip',ROOT)


if __name__ == '__main__':
    make_logo_svgs()
    make_app_icons()
    make_tray_icons()
    make_digital_creatives()
    make_motion_assets()
    make_contact_sheet()
    make_tokens_and_guides()
    make_preview_microgrid()
    make_tray_context_preview()
    copy_source_script()
    make_manifest()
    make_zip()
    print(ROOT)
    print('/mnt/data/Setpiece_Identity_Kit_v1.zip')
