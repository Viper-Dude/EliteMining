#!/usr/bin/env python3
"""
Mining Card Generator
Creates visual PNG cards from mining session data
"""

import os
import re
import sys
from PIL import Image, ImageDraw, ImageFont

try:
    from localization import t, get_material, get_abbr
except Exception:
    def t(key, **kwargs):
        return key

    def get_material(name):
        return name

    def get_abbr(name):
        return name

MODERN_THEMES = ("modern", "modern_slate", "modern_orange")
CARD_WIDTH = 560
PAD = 24
NAME_W = 125
BAR_W = 34
CONTENT_W = CARD_WIDTH - 2 * PAD


def _palette(theme):
    if theme in MODERN_THEMES:
        from ui.theme import get_theme_colors
        c = get_theme_colors(theme)
        return {
            'modern': True, 'bg': c['bg'], 'panel': c['panel'], 'row_alt': c['row_alt'],
            'line': c['border'], 'text': c['fg'], 'muted': c['fg_muted'],
            # Slate's own accent is light grey like its text, so the card keeps the plain orange
            'accent': "#FF9A32" if theme == "modern_slate" else c['accent'],
            'bar_bg': c['border'],
        }
    return {
        'modern': False, 'bg': "#141419", 'panel': "#2D2D32", 'row_alt': "#1C1C22",
        'line': "#FF8C00", 'text': "#DCDCDC", 'muted': "#A0A0A5", 'accent': "#FFB43C",
        'bar_bg': "#323237",
    }


def _font(size, bold=False):
    for name in (("arialbd.ttf", "arial.ttf") if bold else ("arial.ttf",)):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def _fit(draw, text, font, max_w):
    text = str(text)
    if draw.textlength(text, font=font) <= max_w:
        return text
    while text and draw.textlength(text + "…", font=font) > max_w:
        text = text[:-1]
    return text + "…"


def _wrap(draw, text, font, max_w):
    lines = []
    for para in str(text).splitlines() or [""]:
        line = ""
        for word in para.split():
            trial = f"{line} {word}".strip()
            if line and draw.textlength(trial, font=font) > max_w:
                lines.append(line)
                line = word
            else:
                line = trial
        lines.append(_fit(draw, line, font, max_w))
    return lines


def _right(draw, x_right, y, text, font, fill):
    draw.text((x_right - draw.textlength(text, font=font), y), text, fill=fill, font=font)


def _panel(draw, box, pal, fill=None):
    fill = pal['panel'] if fill is None else fill
    if pal['modern']:
        draw.rounded_rectangle(box, radius=8, fill=fill, outline=pal['line'], width=1)
    else:
        draw.rectangle(box, fill=fill, outline=pal['line'], width=2)


def _section(draw, y, title, pal, font):
    draw.text((PAD, y), title, fill=pal['accent'], font=font)
    y += 30
    draw.line([(PAD, y), (CARD_WIDTH - PAD, y)], fill=pal['line'], width=1 if pal['modern'] else 2)
    return y + 12


def _number(value):
    try:
        return float(str(value).replace('%', '').replace(',', '').strip() or 0)
    except (TypeError, ValueError):
        return 0.0


def _normalize_materials(materials_mined):
    rows = []
    for name, data in (materials_mined or {}).items():
        try:
            if isinstance(data, dict):
                tons = data.get('tons', 0)
                if isinstance(tons, dict):
                    tph = float(tons.get('tph', 0))
                    tons = float(tons.get('tons', 0))
                else:
                    tons = float(tons)
                    tph = float(data.get('tph', 0))
            else:
                tons, tph = float(data or 0), 0.0
        except (TypeError, ValueError):
            continue
        rows.append((name, tons, tph))
    return sorted(rows, key=lambda r: r[1], reverse=True)


def _mineral_rows(materials_mined, mineral_performance, total_tons):
    """One row per mineral: refined minerals by tons first, then minerals only prospected."""
    perf_all = mineral_performance or {}
    rows = []
    seen = set()
    for name, tons, tph in _normalize_materials(materials_mined):
        rows.append((name, tons, tph, perf_all.get(name)))
        seen.add(name)
    for name, perf in perf_all.items():
        if name not in seen:
            rows.append((name, None, None, perf))

    out = []
    for name, tons, tph, perf in rows:
        perf = perf or {}
        hits = int(_number(perf.get('finds') or perf.get('hits') or 0))
        core_hits = int(_number(perf.get('core_hits') or 0))
        is_core_name = name.endswith(' (Core)')
        base = name[:-len(' (Core)')] if is_core_name else name
        pure_core = is_core_name or (core_hits > 0 and core_hits >= hits)
        has_yield = bool(perf) and not pure_core
        out.append({
            'base': base,
            'suffix': f" ({t('mining_card.core')})" if pure_core and perf else "",
            'tons': tons,
            'tph': tph,
            'share': (tons / total_tons * 100) if tons and total_tons > 0 else None,
            'avg': f"{_number(perf.get('avg')):.1f}%" if has_yield else "—",
            'best': f"{_number(perf.get('best')):.1f}%" if has_yield else "—",
            'hits': str(hits) if perf else "—",
        })
    return out


def _logo_path():
    if getattr(sys, 'frozen', False):
        # PyInstaller - executable is in Configurator folder, app is one level up
        app_dir = os.path.join(os.path.dirname(os.path.dirname(sys.executable)), 'app')
    else:
        app_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(app_dir, 'Images', 'EliteMining_txt_logo_transp_resize.png')


def _app_version():
    try:
        from version import __version__
        return __version__
    except Exception:
        return ""


def generate_mining_card(session_data, output_path, cmdr_info=None, theme=None):
    """
    Generate a mining card PNG from session data

    Args:
        session_data: Dict containing session information
        output_path: Full path where PNG will be saved
        cmdr_info: Optional dict with 'cmdr' and 'comment' keys
        theme: App theme name; defaults to the saved theme

    Returns:
        bool: True if successful, False otherwise
    """
    try:
        if theme is None:
            try:
                from config import load_theme
                theme = load_theme()
            except Exception:
                theme = "modern"
        pal = _palette(theme)
        f_title = _font(22, True)
        f_sub = _font(14)
        f_section = _font(16, True)
        f_tile_val = _font(19, True)
        f_label = _font(12)
        f_body = _font(15)
        f_body_bold = _font(15, True)
        f_head = _font(12, True)
        f_stat = _font(17, True)

        # Draw on a tall canvas and crop to the content height at the end
        img = Image.new('RGB', (CARD_WIDTH, 4000), pal['bg'])
        draw = ImageDraw.Draw(img)
        y = 30

        # Logo
        logo_drawn = False
        try:
            path = _logo_path()
            if os.path.exists(path):
                logo = Image.open(path).convert('RGBA')
                if logo.width > 200:
                    logo = logo.resize((200, int(logo.height * 200 / logo.width)), Image.LANCZOS)
                img.paste(logo, ((CARD_WIDTH - logo.width) // 2, y), logo)
                y += logo.height + 22
                logo_drawn = True
        except Exception as e:
            print(f"[CARD] Could not load logo: {e}")
        if not logo_drawn:
            title = "ELITEMINING"
            draw.text(((CARD_WIDTH - draw.textlength(title, font=f_title)) // 2, y), title, fill=pal['accent'], font=f_title)
            y += 50

        # Title: System · Body, then CMDR · Ship · date
        system = session_data.get('system') or "?"
        body = session_data.get('body') or ""
        title = f"{system}  ·  {body}" if body else system
        draw.text((PAD, y), _fit(draw, title, f_title, CONTENT_W), fill=pal['text'], font=f_title)
        y += 38
        sub_parts = []
        if cmdr_info and cmdr_info.get('cmdr'):
            sub_parts.append(f"CMDR {cmdr_info['cmdr']}")
        if session_data.get('ship'):
            sub_parts.append(session_data['ship'])
        if session_data.get('session_date'):
            sub_parts.append(session_data['session_date'])
        if sub_parts:
            draw.text((PAD, y), _fit(draw, "  ·  ".join(sub_parts), f_sub, CONTENT_W), fill=pal['muted'], font=f_sub)
            y += 24
        ring_parts = [(t('mining_card.post_ring_type'), session_data.get('ring_type')),
                      (t('mining_card.post_reserve'), session_data.get('reserve'))]
        ring_parts = [(label, value) for label, value in ring_parts if value]
        if ring_parts:
            x = PAD
            for i, (label, value) in enumerate(ring_parts):
                if i:
                    draw.text((x, y), "  ·  ", fill=pal['muted'], font=f_sub)
                    x += draw.textlength("  ·  ", font=f_sub)
                draw.text((x, y), f"{label} ", fill=pal['muted'], font=f_sub)
                x += draw.textlength(f"{label} ", font=f_sub)
                draw.text((x, y), value, fill=pal['text'], font=f_sub)
                x += draw.textlength(value, font=f_sub)
            y += 24
        y += 20

        # Stat tiles
        total_tons = _number(session_data.get('total_tons'))
        prospectors = int(_number(session_data.get('prospectors_used')))
        per_limpet = total_tons / prospectors if prospectors > 0 else 0
        tiles = [
            (t('mining_card.duration'), str(session_data.get('duration') or "—")),
            (t('mining_card.total_tons'), f"{total_tons:,.0f}t"),
            (t('mining_card.tons_per_hour'), f"{_number(session_data.get('tph')):,.1f}"),
            (t('mining_card.prospectors'), str(prospectors) if prospectors else "—"),
            (t('mining_card.tons_per_limpet'), f"{per_limpet:.2f}" if per_limpet else "—"),
        ]
        gap = 8
        tile_w = (CONTENT_W - gap * (len(tiles) - 1)) // len(tiles)
        tile_h = 62
        for i, (label, value) in enumerate(tiles):
            x = PAD + i * (tile_w + gap)
            _panel(draw, [x, y, x + tile_w, y + tile_h], pal)
            value = _fit(draw, value, f_tile_val, tile_w - 8)
            draw.text((x + (tile_w - draw.textlength(value, font=f_tile_val)) / 2, y + 10), value, fill=pal['accent'], font=f_tile_val)
            label = _fit(draw, label, f_label, tile_w - 8)
            draw.text((x + (tile_w - draw.textlength(label, font=f_label)) / 2, y + 39), label, fill=pal['muted'], font=f_label)
        y += tile_h + 28

        # Minerals table
        y = _section(draw, y, t('mining_card.minerals'), pal, f_section)
        rows = _mineral_rows(session_data.get('materials_mined'), session_data.get('mineral_performance'), total_tons)
        if rows:
            x0 = PAD
            col = {'name': x0 + 8, 'tons': x0 + 178, 'tph': x0 + 234, 'bar': x0 + 241, 'pct': x0 + 324,
                   'avg': x0 + 374, 'best': x0 + 436, 'hits': x0 + CONTENT_W - 8}
            row_h = 30
            draw.text((col['name'], y), t('mining_card.col_mineral'), fill=pal['muted'], font=f_head)
            for key, label_key in (('tons', 'col_tons'), ('tph', 'col_tph'), ('pct', 'col_share'),
                                   ('avg', 'col_avg'), ('best', 'col_best'), ('hits', 'col_hits')):
                _right(draw, col[key], y, t(f'mining_card.{label_key}'), f_head, pal['muted'])
            y += 22
            for i, row in enumerate(rows):
                if i % 2 == 1:
                    draw.rectangle([x0, y, x0 + CONTENT_W, y + row_h - 2], fill=pal['row_alt'])
                ty = y + 6
                name = get_material(row['base']) + row['suffix']
                if draw.textlength(name, font=f_body) > NAME_W:
                    name = get_abbr(row['base']) + row['suffix']
                draw.text((col['name'], ty), _fit(draw, name, f_body, NAME_W), fill=pal['text'], font=f_body)
                _right(draw, col['tons'], ty, f"{row['tons']:,.0f}t" if row['tons'] is not None else "—", f_body_bold, pal['text'])
                _right(draw, col['tph'], ty, f"{row['tph']:,.1f}" if row['tph'] is not None else "—", f_body, pal['text'])
                if row['share'] is not None:
                    bar_y = y + row_h // 2 - 4
                    draw.rectangle([col['bar'], bar_y, col['bar'] + BAR_W, bar_y + 7], fill=pal['bar_bg'])
                    fill_w = int(BAR_W * min(row['share'], 100) / 100)
                    if fill_w > 0:
                        draw.rectangle([col['bar'], bar_y, col['bar'] + fill_w, bar_y + 7], fill=pal['accent'])
                    _right(draw, col['pct'], ty, f"{row['share']:.0f}%", f_body, pal['accent'])
                _right(draw, col['avg'], ty, row['avg'], f_body, pal['text'])
                _right(draw, col['best'], ty, row['best'], f_body, pal['text'])
                _right(draw, col['hits'], ty, row['hits'], f_body, pal['text'])
                y += row_h
        else:
            draw.text((PAD + 12, y), t('mining_card.no_minerals'), fill=pal['muted'], font=f_body)
            y += 30
        y += 20

        # Prospecting stats strip
        cells = []
        asteroids = int(_number(session_data.get('asteroids_prospected')))
        if asteroids > 0:
            cells.append((t('mining_card.asteroids_prospected'), str(asteroids)))
        hit_rate = _number(session_data.get('hit_rate'))
        if hit_rate > 0:
            cells.append((t('mining_card.hit_rate'), f"{hit_rate:.1f}%"))
        cores = int(_number(session_data.get('core_asteroids')))
        if cores > 0:
            cells.append((t('mining_card.cores_found'), str(cores)))
        avg_yield = _number(session_data.get('avg_yield'))
        if avg_yield > 0:
            cells.append((t('mining_card.avg_yield'), f"{avg_yield:.1f}%"))
        if cells:
            strip_h = 62
            _panel(draw, [PAD, y, CARD_WIDTH - PAD, y + strip_h], pal)
            cell_w = CONTENT_W / len(cells)
            for i, (label, value) in enumerate(cells):
                cx = PAD + i * cell_w
                label = _fit(draw, label, f_label, cell_w - 6)
                draw.text((cx + (cell_w - draw.textlength(label, font=f_label)) / 2, y + 10), label, fill=pal['muted'], font=f_label)
                draw.text((cx + (cell_w - draw.textlength(value, font=f_stat)) / 2, y + 30), value, fill=pal['text'], font=f_stat)
            y += strip_h + 24

        # Engineering materials
        eng_total = int(_number(session_data.get('engineering_materials_total')))
        if eng_total > 0:
            y = _section(draw, y, t('mining_card.engineering', count=eng_total), pal, f_section)
            items = []
            for mat in session_data.get('engineering_materials_list') or []:
                grade = re.search(r"(\d+)", str(mat.get('grade', '')))
                grade_txt = f" (G{grade.group(1)})" if grade else ""
                items.append(f"{get_material(mat.get('material', ''))}{grade_txt} ×{mat.get('quantity', 0)}")
            for line in _wrap(draw, ",  ".join(items) if items else str(eng_total), f_body, CONTENT_W - 12):
                draw.text((PAD + 12, y), line, fill=pal['text'], font=f_body)
                y += 26
            y += 16

        # Notes
        comment = (cmdr_info or {}).get('comment')
        if comment:
            y = _section(draw, y, t('mining_card.notes'), pal, f_section)
            for line in _wrap(draw, f"“{comment}”", f_body, CONTENT_W - 12):
                draw.text((PAD + 12, y), line, fill=pal['text'], font=f_body)
                y += 26
            y += 16

        # Footer
        y += 4
        draw.line([(PAD, y), (CARD_WIDTH - PAD, y)], fill=pal['line'], width=1 if pal['modern'] else 2)
        y += 12
        draw.text((PAD, y), t('mining_card.tagline'), fill=pal['muted'], font=f_label)
        version = _app_version()
        _right(draw, CARD_WIDTH - PAD, y, f"EliteMining v{version}" if version else "EliteMining", f_label, pal['muted'])
        y += 18 + 26

        img = img.crop((0, 0, CARD_WIDTH, y))
        draw = ImageDraw.Draw(img)
        if pal['modern']:
            draw.rectangle([0, 0, CARD_WIDTH - 1, y - 1], outline=pal['line'], width=1)
            draw.rectangle([0, 0, CARD_WIDTH - 1, 3], fill=pal['accent'])
        else:
            draw.rectangle([0, 0, CARD_WIDTH - 1, y - 1], outline=pal['line'], width=3)
            draw.rectangle([8, 8, CARD_WIDTH - 9, y - 9], outline=pal['line'], width=1)

        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        img.save(output_path, 'PNG')
        print(f"[MINING CARD] Generated: {output_path}")
        return True

    except Exception as e:
        print(f"[MINING CARD] Error generating card: {e}")
        import traceback
        traceback.print_exc()
        return False


def create_card_from_session(cargo_session_data, session_info, output_path, cmdr_info=None, theme=None):
    """
    Create mining card from session end data

    Args:
        cargo_session_data: Cargo tracking session data from end_session_tracking()
        session_info: Additional session info (system, body, ship, duration text, session date)
        output_path: Full path where PNG will be saved
        cmdr_info: Optional dict with 'cmdr' and 'comment' keys
        theme: App theme name; defaults to the saved theme

    Returns:
        bool: True if successful, False otherwise
    """
    try:
        hours = cargo_session_data.get('session_duration', 0) / 3600.0
        total_tons = cargo_session_data.get('total_tons_mined', 0)
        materials = {}
        for name, quantity in (cargo_session_data.get('materials_mined') or {}).items():
            if isinstance(quantity, dict):
                materials[name] = {'tons': quantity.get('tons', 0), 'tph': quantity.get('tph', 0)}
            else:
                tons = float(quantity) if quantity else 0
                materials[name] = {'tons': tons, 'tph': tons / hours if hours > 0 else 0}

        card_data = {
            'system': session_info.get('system', ''),
            'body': session_info.get('body', ''),
            'ship': session_info.get('ship'),
            'session_date': session_info.get('session_date', ''),
            'ring_type': session_info.get('ring_type', ''),
            'reserve': session_info.get('reserve', ''),
            'duration': session_info.get('duration_text', ''),
            'total_tons': total_tons,
            'tph': total_tons / hours if hours > 0 else 0,
            'prospectors_used': cargo_session_data.get('prospectors_used', 0),
            'avg_yield': cargo_session_data.get('avg_yield', 0),
            'asteroids_prospected': cargo_session_data.get('asteroids_prospected', 0),
            'core_asteroids': cargo_session_data.get('core_asteroids', 0),
            'hit_rate': cargo_session_data.get('hit_rate', 0),
            'mineral_performance': cargo_session_data.get('mineral_performance', {}),
            'engineering_materials_total': cargo_session_data.get('engineering_materials_total', 0),
            'engineering_materials_list': cargo_session_data.get('engineering_materials_list', []),
            'materials_mined': materials,
        }
        return generate_mining_card(card_data, output_path, cmdr_info, theme)

    except Exception as e:
        print(f"[MINING CARD] Error creating card: {e}")
        import traceback
        traceback.print_exc()
        return False
