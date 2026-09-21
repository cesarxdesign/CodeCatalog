#!/usr/bin/env python3
"""CodeCatalog build.

Reads every screens/<project>/<platform>/<id>/meta.json and regenerates:
  - embed.html   per screen: a style-isolated, drop-in copy of the screen
  - screen.html  for mobile screens that only exist as a snippet
  - catalog.json the index Claude Code reads to find a screen
  - index.html   the catalogue page (published as the CodeCatalog artifact)

Run from anywhere:  python3 tools/build.py
Needs: python3, and macOS `sips` for the preview thumbnails.
"""
import base64, hashlib, json, os, re, subprocess, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)
CACHE = os.path.join(ROOT, '.cache', 'previews')
# Web fonts an embed may need, and how Google Fonts names them. A screen gets a link for
# exactly the families its own CSS asks for. System faces (-apple-system, SF Pro) need none.
WEB_FONTS = {
    'Montserrat':  'Montserrat:ital,wght@0,400;0,500;0,600;0,700;0,800;1,400',
    'Roboto Mono': 'Roboto+Mono:wght@400;700',
}
def fonts_used(css):
    return [f for f in WEB_FONTS if re.search(r'''["']?%s["']?''' % re.escape(f), css)] or ['Montserrat']
def font_link(fonts):
    return ('https://fonts.googleapis.com/css2?' +
            '&'.join('family=' + WEB_FONTS[f] for f in fonts) + '&display=swap')

def rd(p): return open(p, encoding='utf-8').read()
def fingerprint(folder, meta):
    """What an embed is built from. Content, not timestamps: survives copies and git clones."""
    h = hashlib.sha1()
    for name in ('meta.json', meta['embed_from']):
        h.update(open(os.path.join(folder, name), 'rb').read())
    h.update(open(__file__, 'rb').read())      # a change to this tool rebuilds everything
    return h.hexdigest()[:12]
def wr(p, s): open(p, 'w', encoding='utf-8').write(s)

# ---------- the screen, as a shadow root: (css, body) ----------
def shadow_parts(folder, meta):
    """Everything a shadow root needs, taken from the file the embed is built from."""
    w, h = meta['frame']
    src = rd(os.path.join(folder, meta['embed_from']))
    if meta['platform'] == 'mobile':           # already a shadow-root snippet
        inner = re.search(r'<template shadowrootmode="open">([\s\S]*)</template>', src).group(1)
        css = re.search(r'<style>([\s\S]*?)</style>', inner).group(1)
        body = re.sub(r'<style>[\s\S]*?</style>', '', inner, count=1).strip()
    else:
        css = "\n".join(m.group(1) for m in re.finditer(r'<style[^>]*>([\s\S]*?)</style>', src))
        m = re.search(r'<body[^>]*>([\s\S]*?)</body>', src)
        body = m.group(1) if m else src[src.rindex('</style>') + len('</style>'):]
        body = re.sub(r'</?(html|head|body)\b[^>]*>', '', body)
        # a shadow root has no html, body or :root - carry their rules onto :host
        css = re.sub(r'(^|[}\n;])\s*html\s*,\s*body\s*\{[^}]*\}', r'\1', css)
        css = re.sub(r'(^|[}\n])\s*body\s*\{', r'\1:host{', css)
        css = css.replace(':root{', ':host{')
    body = re.sub(r'<script[\s\S]*?</script>', '', body).strip()     # scripts never run in here
    if meta.get('embed_state'):                                       # pin one state, on the element only
        attr, val = meta['embed_state']
        pm = re.search(r'<div class="page"[^>]*>', body)
        if pm:
            tag = re.sub(r'\s+data-(state|step)="[^"]*"', '', pm.group(0))
            body = body[:pm.start()] + tag[:-1] + ' %s="%s">' % (attr, val) + body[pm.end():]
    css = (":host{display:block;width:%dpx;height:%dpx;overflow:hidden;"
           "font-family:'Montserrat',-apple-system,sans-serif;color:#133253}\n" % (w, h)) + css.strip()
    return css, body

def embed_html(key, meta, css, body, fp):
    w, h = meta['frame']
    link = font_link(fonts_used(css))
    return f'''<!-- CodeCatalog · {key} · {w}×{h} · built from {meta['embed_from']} · fp {fp}
     Drop-in, style-isolated copy of the screen. Paste it into any page.
     Scale:      .cc-screen{{--cc-scale:.5}}      (default 1)
     Background: .cc-screen{{--cc-bg:#F6F6F6}}    (default transparent)
     Scripts are not included; for the clickable version use screen.html. -->
<link rel="stylesheet" href="{link}">
<div class="cc-screen" data-cc="{key}" style="--cc-w:{w};--cc-h:{h};width:calc(var(--cc-w)*var(--cc-scale,1)*1px);height:calc(var(--cc-h)*var(--cc-scale,1)*1px);overflow:hidden;background:var(--cc-bg,transparent)">
<div style="width:{w}px;height:{h}px;transform:scale(var(--cc-scale,1));transform-origin:0 0"><template shadowrootmode="open"><style>
{css}
</style>
{body}
</template></div>
</div>
'''

def standalone_from_embed(key, meta, embed):
    w, h = meta['frame']
    return f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width={w}">
<title>{meta['project'].title()} · {meta['name'].replace('&','&amp;')}</title>
<style>html,body{{margin:0;background:#F4F4F4}}</style>
</head><body>
{embed}</body></html>
'''

def preview_b64(folder, meta, key):
    os.makedirs(CACHE, exist_ok=True)
    src = os.path.join(folder, meta['files']['preview'])
    out = os.path.join(CACHE, key.replace('/', '__') + '.jpg')
    if not os.path.exists(out) or os.path.getmtime(out) < os.path.getmtime(src):
        size = ['-Z', '1200'] if meta['platform'] == 'desktop' else []
        q = '74' if meta['platform'] == 'desktop' else '82'
        subprocess.run(['sips', '-s', 'format', 'jpeg', '-s', 'formatOptions', q, *size, src, '--out', out],
                       check=True, capture_output=True)
    return base64.b64encode(open(out, 'rb').read()).decode()

# ---------- walk the screens ----------
screens = []
for dirpath, _, files in os.walk('screens'):
    if 'meta.json' not in files: continue
    meta = json.load(open(os.path.join(dirpath, 'meta.json'), encoding='utf-8'))
    key = '%s/%s/%s' % (meta['project'], meta['platform'], meta['id'])
    css, body = shadow_parts(dirpath, meta)
    fp = fingerprint(dirpath, meta)
    emb = embed_html(key, meta, css, body, fp)
    wr(os.path.join(dirpath, 'embed.html'), emb)
    if meta.get('screen_generated') or not os.path.exists(os.path.join(dirpath, 'screen.html')):
        wr(os.path.join(dirpath, 'screen.html'), standalone_from_embed(key, meta, emb))
        meta['screen_generated'] = True
    screens.append(dict(key=key, dir=dirpath, meta=meta, css=css, body=body, fp=fp))

order = {'desktop': 0, 'mobile': 1}
screens.sort(key=lambda s: (s['meta']['project'], order[s['meta']['platform']], s['meta']['order']))
BUILD = hashlib.sha1(''.join(x['key'] + x['fp'] for x in screens).encode()).hexdigest()[:12]

# ---------- catalog.json: the index ----------
catalog = {
  'about': 'CodeCatalog index. One entry per screen; paths are relative to this file. '
           'Generated by tools/build.py from each screen\'s meta.json - edit those, not this.',
  'count': len(screens),
  'build': BUILD,
  'screens': [dict(
      key=s['key'], id=s['meta']['id'], project=s['meta']['project'], platform=s['meta']['platform'],
      flow=s['meta'].get('flow'), name=s['meta']['name'], title=s['meta'].get('title'), aliases=s['meta'].get('aliases', []),
      frame=s['meta']['frame'], interactive=s['meta']['interactive'], states=s['meta']['states'],
      provenance=s['meta']['provenance'], fonts=fonts_used(s['css']), live=s['meta'].get('live'),
      folder=s['dir'].replace(os.sep, '/'),
      files={k: (s['dir'].replace(os.sep, '/') + '/' + v if isinstance(v, str)
                 else [s['dir'].replace(os.sep, '/') + '/' + x for x in v])
             for k, v in s['meta']['files'].items()},
  ) for s in screens]}
wr('catalog.json', json.dumps(catalog, indent=2, ensure_ascii=False) + '\n')

# ---------- the catalogue page ----------
json_dumps = json.dumps
D = []; M = []
for s in screens:
    m = s['meta']; c = m['catalogue']
    d = dict(k=s['key'], n=m['name'], iw=m['frame'][0], ih=m['frame'][1], live=m.get('live'),
             p=m['project'], fl=m.get('flow') or '',
             s=preview_b64(s['dir'], m, s['key']), css=s['css'], body=s['body'])
    if m['platform'] == 'desktop':
        d.update(f=c['frame_label'], sc=m['source_scale'], src=m['source_frames'], tag=c.get('tag', ''),
                 m1=c['m1'], m1l=c['m1l'], m2=c['m2'], m2l=c['m2l'], note=c['note'])
        D.append(d)
    else:
        d.update(sc=c['sc'], diff=c['diff'], al=c['al'], note=c['note'], node=m['figma_node'],
                 rw=m['export_size'][0], rh=m['export_size'][1])
        M.append(d)

def scr(s):
    return ('<div class="scr">'
            f'<template shadowrootmode="open"><style>{s["css"]}</style>{s["body"]}</template></div>')

def title(x): return x.replace('-', ' ').title()
PROJECTS = sorted({s['p'] for s in D + M})
FLOWS = sorted({s['fl'] for s in D + M if s['fl']})
def options(values, all_label):
    return (f'<option value="">{all_label}</option>' +
            ''.join(f'<option value="{v}">{title(v)}</option>' for v in values))

def chip(s,i):
    return (f'<button type="button" class="fs" data-k="{s["k"]}" data-proj="{s["p"]}" data-fl="{s["fl"]}" '
            f'style="--iw:{s["iw"]};--ih:{s["ih"]}" '
            f'aria-pressed="{"true" if i==0 else "false"}">'
            f'<span class="fsimg"><span class="tscr" data-k="{s["k"]}"></span></span>'
            f'<span class="fsn" data-k="{s["k"]}">{s["n"]}</span></button>')
strip = ('<div class="grp desk"><span class="glab">measured from pictures &middot; no design file</span><div class="row">'
         + "".join(chip(s,i) for i,s in enumerate(D)) + '</div></div>'
         + '<div class="grp mob"><span class="glab">read from the Figma file</span><div class="row">'
         + "".join(chip(s,1) for s in M) + '</div></div>')

def sec_d(s,i):
    return f'''<section id="sec-{s['k']}" style="--iw:{s['iw']};--ih:{s['ih']}" {'' if i==0 else 'hidden'}>
<div class="stage"><div class="pair">
 <div class="pane ref"><div class="tag"><span class="k">Source</span><span class="d">Figma export &middot; {s['sc']}</span></div>
  <div class="shot"><img src="data:image/jpeg;base64,{s['s']}" alt="Source export of {s['n']}" loading="lazy"></div></div>
 <div class="pane build"><div class="tag"><span class="k">Code</span><span class="d">live HTML &amp; CSS &middot; {s['f']}</span></div>
  <div class="box"><div class="fit">{scr(s)}</div></div></div>
</div></div>
<div class="notes">
 <div class="card"><h2>Source</h2><p><span class="big">{s['m1']}</span>{s['m1l']}</p></div>
 <div class="card"><h2>Fit</h2><p><span class="big">{s['m2']}</span>{s['m2l']}</p></div>
 <div class="card c2"><h2>Notes</h2><p>{s['note']}</p>
  {('<p class="lnkrow"><a class="lnk" href="%s" target="_blank" rel="noopener">Open the clickable version &rarr;</a></p>' % s['live']) if s.get('live') else ''}</div>
</div></section>'''

def sec_m(s):
    b=dict(iw=s['iw'],ih=s['ih'])
    upscale=' &middot; shown at %d' % b['iw'] if s['rw']!=b['iw'] else ''
    return f'''<section id="sec-{s['k']}" class="mob" style="--pw:{b['iw']};--iw:{b['iw']};--ih:{b['ih']}" hidden>
<div class="stage"><div class="pair">
 <div class="pane ref"><div class="tag"><span class="k">Figma</span><span class="d">exported &middot; {s['rw']}&times;{s['rh']}{upscale}</span></div>
  <div class="shot"><img src="data:image/jpeg;base64,{s['s']}" alt="Figma export of {s['n']}" loading="lazy"></div></div>
 <div class="pane build"><div class="tag"><span class="k">Code</span><span class="d">live HTML &amp; CSS &middot; {b['iw']}&times;{b['ih']}</span></div>
  <div class="box"><div class="fit">{scr(s)}</div></div></div>
</div></div>
<div class="notes">
 <div class="card"><h2>Scale factor</h2><p><span class="big">{s['sc']}</span>{'never scaled' if s['sc']=='1.0' else 'same factor on both axes'}</p></div>
 <div class="card"><h2>Pixel difference</h2><p><span class="big">{s['diff']}</span>glyph outlines only &mdash; no filled shape differs</p></div>
 <div class="card"><h2>Alignment</h2><p><span class="big">{s['al']}</span>every measurable element</p></div>
 <div class="card"><h2>Node</h2><p><span class="big sm">{s['node']}</span>{b['iw']} &times; {b['ih']} in code</p></div>
 <div class="card c4"><h2>Notes</h2><p>{s['note']}</p>
  {('<p class="lnkrow"><a class="lnk" href="%s" target="_blank" rel="noopener">Open the live Figma-vs-code comparison &rarr;</a></p>' % s['live']) if s.get('live') else ''}</div>
</div></section>'''

secs = "".join(sec_d(s,i) for i,s in enumerate(D)) + "".join(sec_m(s) for s in M)
META={}
for s in D: META[s['k']]=dict(n=s['n'],f=s['f'],sc=s['sc'],src=s['src'],tag=s['tag'],p=s['p'],fl=s['fl'])
for s in M:
    META[s['k']]=dict(n=s['n'],f='%d × %d'%(s['iw'],s['ih']),sc=s['sc']+'×',src='node '+s['node'],tag='',
                      p=s['p'],fl=s['fl'])

page=f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta name="cc-build" content="{BUILD}">
<title>CodeCatalog</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500&family=IBM+Plex+Sans:wght@400;500;600&family=Montserrat:wght@400;500;600;700;800&family=Roboto+Mono:wght@400;700&display=swap" rel="stylesheet">
<style>
:root{{
  --bg:#EDEFF2; --panel:#FFFFFF; --sunk:#E3E7EC;
  --ink:#16202B; --muted:#5E6C7A; --line:#D3DAE2; --accent:#C9204E;
  --sans:'IBM Plex Sans',system-ui,-apple-system,sans-serif;
  --mono:'IBM Plex Mono',ui-monospace,SFMono-Regular,Menlo,monospace;
}}
@media (prefers-color-scheme:dark){{:root:not([data-theme="light"]){{
  --bg:#2C2C2C; --panel:#1F1F1F; --sunk:#262626;
  --ink:#E8EAED; --muted:#969CA4; --line:#3C3C3C; --accent:#FF5081;}}}}
:root[data-theme="dark"]{{
  --bg:#2C2C2C; --panel:#1F1F1F; --sunk:#262626;
  --ink:#E8EAED; --muted:#969CA4; --line:#3C3C3C; --accent:#FF5081;}}
*{{box-sizing:border-box}}
body{{background:var(--bg);color:var(--ink);font-family:var(--sans);margin:0;padding:0 16px;line-height:1.5}}
.wrap{{max-width:1180px;margin:0 auto;padding-block:32px 56px}}
header{{display:flex;flex-wrap:wrap;gap:20px 32px;align-items:flex-end;justify-content:space-between;
       padding-bottom:20px;border-bottom:1px solid var(--line)}}
h1{{font-size:23px;font-weight:600;margin:0;letter-spacing:-.015em;text-wrap:balance}}
.sub{{color:var(--muted);font-size:13.5px;margin:6px 0 0;max-width:66ch}}
.node{{font-family:var(--mono);font-size:12px;color:var(--muted);display:flex;flex-direction:column;gap:3px;text-align:right}}
.node b{{color:var(--ink);font-weight:500}}

.strip{{display:flex;gap:26px;overflow-x:auto;padding:4px 2px 18px;scrollbar-width:thin}}
body[data-plat="desk"] .grp.mob,body[data-plat="mob"] .grp.desk{{display:none}}
.grp{{display:flex;flex-direction:column;gap:9px;flex:0 0 auto}}
.glab{{font-family:var(--mono);font-size:10.5px;letter-spacing:.08em;text-transform:uppercase;color:var(--muted)}}
.row{{display:flex;gap:10px}}
.fs{{appearance:none;border:0;background:transparent;padding:0;cursor:pointer;flex:0 0 auto;
    display:flex;flex-direction:column;gap:7px;width:104px;text-align:left;font-family:inherit}}
.fsimg{{display:block;height:132px;width:104px;overflow:hidden;border-radius:5px;background:#F6F6F6;
       border:1px solid var(--line);box-shadow:0 1px 4px rgba(0,0,0,.14);line-height:0}}
.tscr{{display:block;transform-origin:top left;transform:scale(calc(104 / var(--iw)));
      width:calc(var(--iw)*1px);height:calc(var(--ih)*1px)}}
.fs .fsn{{font-size:11.5px;color:var(--muted);line-height:1.3}}
.fs[aria-pressed="true"] .fsimg{{border-color:var(--accent);box-shadow:0 0 0 2px var(--accent),0 2px 8px rgba(0,0,0,.2)}}
.fs[aria-pressed="true"] .fsn{{color:var(--ink);font-weight:600}}
.fs:focus-visible .fsimg{{outline:2px solid var(--accent);outline-offset:2px}}

.bar{{display:flex;flex-wrap:wrap;gap:12px 16px;align-items:center;margin:20px 0 14px}}
.seg{{display:inline-flex;background:var(--sunk);border:1px solid var(--line);border-radius:7px;padding:2px;gap:2px}}
.seg button{{appearance:none;border:0;background:transparent;cursor:pointer;font-family:var(--mono);
  font-size:11.5px;letter-spacing:.03em;color:var(--muted);padding:5px 11px;border-radius:5px}}
.seg button[aria-pressed="true"]{{background:var(--panel);color:var(--ink);font-weight:500;box-shadow:0 1px 2px rgba(0,0,0,.14)}}
.seg button:focus-visible{{outline:2px solid var(--accent);outline-offset:1px}}
.seg button i{{font-style:normal;opacity:.5;font-size:10.5px}}
.seg button:disabled{{opacity:.4;cursor:default}}
.pick{{display:inline-flex;align-items:center;gap:7px;font-family:var(--mono);font-size:11.5px;color:var(--muted)}}
.pick select{{appearance:none;-webkit-appearance:none;cursor:pointer;color:var(--ink);font-family:var(--mono);font-size:11.5px;
  background:var(--sunk) url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='10' height='6'%3E%3Cpath d='M1 1l4 4 4-4' fill='none' stroke='%23969CA4' stroke-width='1.5'/%3E%3C/svg%3E") no-repeat right 9px center;
  border:1px solid var(--line);border-radius:7px;padding:6px 28px 6px 10px}}
.pick select:focus-visible{{outline:2px solid var(--accent);outline-offset:1px}}
.fs[hidden],.grp[hidden]{{display:none}}
.ren{{appearance:none;background:var(--sunk);border:1px solid var(--line);border-radius:7px;cursor:pointer;
  font-family:var(--mono);font-size:11.5px;color:var(--muted);padding:6px 11px}}
.ren:hover{{color:var(--ink)}}
.ren:focus-visible{{outline:2px solid var(--accent);outline-offset:1px}}
.fsn.editing{{color:var(--ink);background:var(--panel);border-radius:3px;
  box-shadow:0 0 0 2px var(--accent);outline:none;padding:0 3px;cursor:text}}
.hint{{color:var(--muted);font-size:12px;font-family:var(--mono)}}

.stage{{overflow-x:auto;padding-bottom:6px}}
.pair{{display:flex;gap:28px;justify-content:center;min-width:min-content;padding:4px 0 8px}}
section{{--pw:544}}
body[data-view="code"] section{{--pw:800}}
.pane{{display:flex;flex-direction:column;flex:0 0 auto;width:calc(var(--pw)*1px)}}
.tag{{display:flex;align-items:baseline;gap:8px;padding:0 0 9px 1px}}
.tag .k{{font-family:var(--mono);font-size:11px;letter-spacing:.09em;text-transform:uppercase;
        font-weight:500;padding:2px 7px;border-radius:4px;color:#fff}}
.pane.ref .tag .k{{background:var(--muted)}}
.pane.build .tag .k{{background:var(--accent)}}
.tag .d{{font-size:12px;color:var(--muted);font-family:var(--mono);white-space:nowrap}}

/* the source shot: a picture, capped in height and scrollable */
.shot{{background:#F6F6F6;line-height:0;box-shadow:0 2px 10px rgba(0,0,0,.22);border-radius:3px;
      max-height:760px;overflow:auto;width:100%}}
.shot img{{display:block;width:100%;height:auto}}
/* the build: live DOM, scaled with a transform so type stays vector-sharp */
.box{{background:#F6F6F6;box-shadow:0 2px 10px rgba(0,0,0,.22);border-radius:3px;
     max-height:760px;overflow:auto;width:100%}}
.fit{{width:calc(var(--pw)*1px);height:calc(var(--ih) * var(--pw) / var(--iw) * 1px);overflow:hidden}}
.scr{{transform-origin:top left;transform:scale(calc(var(--pw)/var(--iw)));
     width:calc(var(--iw)*1px);height:calc(var(--ih)*1px)}}
body[data-view="code"] .box,body[data-view="code"] .shot{{max-height:880px}}
section.mob{{--pw:375}}
section.mob .box,section.mob .shot{{border-radius:9px;max-height:none}}
body[data-view="code"] section.mob .box{{max-height:none}}
body[data-view="code"] .pane.ref{{display:none}}
body[data-view="code"] .pair{{gap:0}}

.notes{{margin-top:28px;display:grid;gap:18px;grid-template-columns:repeat(4,1fr)}}
.card{{background:var(--panel);border:1px solid var(--line);border-radius:9px;padding:16px 17px}}
.card.c2{{grid-column:span 2}} .card.c4{{grid-column:span 4}}
.card h2{{margin:0 0 9px;font-size:12px;font-weight:600;letter-spacing:.07em;text-transform:uppercase;color:var(--muted)}}
.card p{{margin:0;font-size:13.5px}}
.card em{{color:var(--muted);font-style:normal}}
.lnkrow{{margin-top:11px}}
.big{{font-family:var(--mono);font-size:26px;font-weight:500;letter-spacing:-.02em;display:block;margin-bottom:2px}}
.big.sm{{font-size:19px}}
.lnk{{color:var(--accent);font-size:13px;font-weight:500;text-decoration:none}}
.lnk:hover{{text-decoration:underline}}
code{{font-family:var(--mono);font-size:12.5px;background:var(--sunk);padding:1px 4px;border-radius:3px}}
.foot{{margin-top:34px;display:grid;gap:18px;grid-template-columns:repeat(auto-fit,minmax(270px,1fr))}}
@media (max-width:900px){{
  .notes{{grid-template-columns:repeat(2,1fr)}} .card.c2,.card.c4{{grid-column:span 2}}
  .pair{{flex-direction:column;align-items:center}} .node{{text-align:left}}}}
</style></head>
<body data-view="both" data-plat="desk"><div class="wrap">
<header>
 <div>
  <h1>CodeCatalog</h1>
  <p class="sub">{' &middot; '.join(title(p) for p in PROJECTS)} &middot; {len(D)} desktop and {len(M)} mobile screens, every one live HTML
  and CSS rather than a picture of it. The desktop set was rebuilt from raster exports and squared up
  into one flow; the mobile set was read from the Figma file. Pick a screen, compare it with what it was
  built from, or lift it out whole &mdash; each lives in its own folder with a drop-in embed.</p>
 </div>
 <div class="node">
  <span>screen <b id="nName">&nbsp;</b></span>
  <span>frame <b id="nFrame">&nbsp;</b></span>
  <span>source <b id="nScale">&nbsp;</b> &middot; <span id="nSrc">&nbsp;</span></span>
  <span id="nTag" style="color:var(--accent)">&nbsp;</span>
 </div>
</header>

<div class="bar">
 <label class="pick"><span>Project</span><select id="fProj">{options(PROJECTS,'All projects')}</select></label>
 <label class="pick"><span>Flow</span><select id="fFlow">{options(FLOWS,'All flows')}</select></label>
 <div class="seg" data-kind="plat" role="group" aria-label="Platform">
  <button type="button" data-p="desk" aria-pressed="true">Desktop <i id="cDesk">{len(D)}</i></button>
  <button type="button" data-p="mob" aria-pressed="false">Mobile <i id="cMob">{len(M)}</i></button>
 </div>
 <div class="seg" data-kind="view" role="group" aria-label="View">
  <button type="button" data-v="both" aria-pressed="true">Source + code</button>
  <button type="button" data-v="code" aria-pressed="false">Code only</button>
 </div>
 <button type="button" class="ren" id="renBtn">Rename&hellip;</button>
 <span class="hint">&larr; &rarr; to step between screens</span>
</div>

<div class="strip" role="group" aria-label="Screens">{strip}</div>

{secs}

<div class="foot">
 <div class="card"><h2>Two different jobs</h2><p>The desktop screens had no design file behind them
  &mdash; only pictures. Sizes, colours and positions were measured out of the pixels and verified by
  re-rendering. The mobile screens came from the Figma file, so their values are exact; the work there
  was catching where the file&rsquo;s own model and the browser&rsquo;s disagree.</p></div>
 <div class="card"><h2>The typeface, corrected</h2><p>The desktop screens were first built in
  <b>Figtree</b>, a fitted match. They are now all <b>Montserrat</b>, which the Figma file uses for
  mobile and which the pictures confirm: measured against three separate headings, Montserrat lands
  within 1.4% of the source and Figtree is 9&ndash;19% too narrow. The old sizes had been inflated
  about 12% to fake that missing width, so they came down with it &mdash; 55px to 49, 22px to 19.4.</p></div>
 <div class="card"><h2>The shared shell</h2><p>Across the desktop set: column at
  <code>x&nbsp;183</code>, measure <code>770</code>, heading top <code>92</code> at
  <code>49px/57px</code> with <code>-0.9px</code> tracking, paragraphs <code>19.4px/29.5px</code>
  <code>23px</code> apart, body copy the same navy as the headings. Each screen's own internal
  spacing was left as measured and shifted whole, so nothing inside a screen changed rhythm.</p></div>
 <div class="card"><h2>Live, but not clickable here</h2><p>Each build is embedded in its own shadow
  root so {len(D)+len(M)} stylesheets can share one page without colliding. Their scripts are left out, so
  the multi-state screens show one state each &mdash; the links above open the clickable versions.</p></div>
</div>
</div>
<script>
var DATA={json.dumps(META)};
var K=Object.keys(DATA);
var KD={json.dumps([s['k'] for s in D])}, KM={json.dumps([s['k'] for s in M])};
var NAMES={{}}, dbRef=null, LS='penfold-catalogue-names';
try{{ NAMES=JSON.parse(localStorage.getItem(LS)||'{{}}')||{{}}; }}catch(e){{}}
/* names given before the catalogue moved used short keys */
var OLDKEYS={{"three": "penfold/desktop/three-things", "flow": "penfold/desktop/plan-selection", "calc": "penfold/desktop/savings-calculator", "signup": "penfold/desktop/sign-up-form", "pay": "penfold/desktop/monthly-payment", "docs": "penfold/desktop/document-consent", "email": "penfold/desktop/enter-email", "top": "penfold/desktop/sign-up-upper", "save": "penfold/desktop/savings-path", "so": "penfold/desktop/standing-order", "allset": "penfold/desktop/confirmation", "home": "penfold/mobile/home", "pause": "penfold/mobile/pause-resume", "pay2": "penfold/mobile/payment", "grow": "penfold/mobile/growth", "login": "penfold/mobile/login", "combine": "penfold/mobile/combine", "ben": "penfold/mobile/beneficiary", "tx": "penfold/mobile/transactions"}};
function migrate(o){{ var n={{}}; Object.keys(o||{{}}).forEach(function(k){{ n[OLDKEYS[k]||k]=o[k]; }}); return n; }}
NAMES=migrate(NAMES);

/* --- the filmstrip thumbnails are the builds themselves, cloned --- */
function buildThumbs(){{
  document.querySelectorAll('.tscr').forEach(function(t){{
    if(t.shadowRoot) return;
    /* keys contain '/', which a CSS #id selector cannot hold - look the section up by id */
    var sec=document.getElementById('sec-'+t.dataset.k), host=sec&&sec.querySelector('.scr');
    if(!host||!host.shadowRoot) return;
    try{{ t.attachShadow({{mode:'open'}}).innerHTML=host.shadowRoot.innerHTML; }}catch(e){{}}
  }});
}}

/* --- names --- */
function nameOf(k,el){{
  if(NAMES[k]) {{ el.textContent=NAMES[k]; }} else {{ el.innerHTML=DATA[k].n; }}
}}
function paintNames(){{
  document.querySelectorAll('.fsn').forEach(function(el){{
    if(!el.classList.contains('editing')) nameOf(el.dataset.k,el);
  }});
  var cur=current(); if(cur) nameOf(cur,nName);
}}
function saveNames(){{
  try{{ localStorage.setItem(LS,JSON.stringify(NAMES)); }}catch(e){{}}
  if(dbRef) dbRef.set(NAMES).catch(function(){{}});
}}
function current(){{ return K.filter(function(x){{return !document.getElementById('sec-'+x).hidden;}})[0]; }}

function startRename(k){{
  var el=document.querySelector('.fs[data-k="'+k+'"] .fsn');
  if(!el||el.classList.contains('editing')) return;
  var before=NAMES[k]||el.textContent.trim();
  el.textContent=before; el.classList.add('editing'); el.contentEditable='true';
  var r=document.createRange(); r.selectNodeContents(el);
  var sl=getSelection(); sl.removeAllRanges(); sl.addRange(r); el.focus();
  function stop(commit){{
    el.contentEditable='false'; el.classList.remove('editing');
    el.onkeydown=null; el.onblur=null;
    if(commit){{
      var v=el.textContent.replace(/\s+/g,' ').trim().slice(0,60);
      if(v) NAMES[k]=v; else delete NAMES[k];
      saveNames();
    }}
    paintNames();
  }}
  el.onkeydown=function(e){{
    e.stopPropagation();
    if(e.key==='Enter'){{e.preventDefault(); stop(true);}}
    else if(e.key==='Escape'){{e.preventDefault(); stop(false);}}
  }};
  el.onblur=function(){{ stop(true); }};
}}
renBtn.addEventListener('click',function(){{ var c=current(); if(c) startRename(c); }});
document.querySelectorAll('.fsn').forEach(function(el){{
  el.addEventListener('dblclick',function(e){{ e.preventDefault(); e.stopPropagation(); startRename(el.dataset.k); }});
}});

/* --- filters: project and flow, kept in the URL so a view can be bookmarked --- */
function ok(k){{ var d=DATA[k]; return (!fProj.value||d.p===fProj.value)&&(!fFlow.value||d.fl===fFlow.value); }}
function listFor(p){{ return (p==='desk'?KD:KM).filter(ok); }}
function writeHash(){{
  var q=[]; if(fProj.value) q.push('project='+fProj.value); if(fFlow.value) q.push('flow='+fFlow.value);
  var c=current(); if(c) q.push('screen='+c);
  try{{ history.replaceState(null,'',q.length?'#'+q.join('&'):location.pathname+location.search); }}catch(e){{}}
}}
function readHash(){{
  var q={{}}; location.hash.slice(1).split('&').forEach(function(kv){{ var i=kv.indexOf('='); if(i>0) q[kv.slice(0,i)]=decodeURIComponent(kv.slice(i+1)); }});
  [[fProj,q.project],[fFlow,q.flow]].forEach(function(x){{
    if(x[1]&&[].some.call(x[0].options,function(o){{return o.value===x[1];}})) x[0].value=x[1]; }});
  return DATA[q.screen]?q.screen:null;
}}
function applyFilter(want){{
  document.querySelectorAll('.fs').forEach(function(b){{ b.hidden=!ok(b.dataset.k); }});
  var nd=listFor('desk').length, nm=listFor('mob').length;
  cDesk.textContent=nd; cMob.textContent=nm;
  document.querySelector('.grp.desk').hidden=!nd; document.querySelector('.grp.mob').hidden=!nm;
  document.querySelectorAll('.seg[data-kind="plat"] button').forEach(function(b){{
    b.disabled=!(b.dataset.p==='desk'?nd:nm); }});
  if(want&&ok(want)) {{ sel(want); return; }}
  var p=document.body.dataset.plat; if(!listFor(p).length) p=(p==='desk'?'mob':'desk');
  var L=listFor(p); if(!L.length) return;
  sel(L.indexOf(current())>=0?current():L[0]);
}}
fProj.addEventListener('change',function(){{ applyFilter(); }});
fFlow.addEventListener('change',function(){{ applyFilter(); }});
addEventListener('hashchange',function(){{ applyFilter(readHash()); }});

/* --- selection --- */
function sel(k){{
  document.querySelectorAll('.fs').forEach(function(b){{b.setAttribute('aria-pressed',String(b.dataset.k===k));}});
  K.forEach(function(x){{document.getElementById('sec-'+x).hidden=(x!==k);}});
  var d=DATA[k];
  nameOf(k,nName); nFrame.textContent=d.f; nScale.textContent=d.sc; nSrc.textContent=d.src;
  nTag.textContent=d.tag||' ';
  var p=KD.indexOf(k)>=0?'desk':'mob';
  if(document.body.dataset.plat!==p) setPlat(p,true);
  var b=document.querySelector('.fs[data-k="'+k+'"]');
  if(b) b.scrollIntoView({{block:'nearest',inline:'nearest',behavior:'smooth'}});
  writeHash();
}}
function setPlat(p,keep){{
  document.body.dataset.plat=p;
  document.querySelectorAll('.seg[data-kind="plat"] button').forEach(function(b){{
    b.setAttribute('aria-pressed',String(b.dataset.p===p));}});
  if(keep) return;
  var list=listFor(p);
  if(list.length&&list.indexOf(current())<0) sel(list[0]);
}}
document.querySelectorAll('.seg[data-kind="plat"] button').forEach(function(b){{
  b.addEventListener('click',function(){{setPlat(b.dataset.p,false);}});}});
document.querySelectorAll('.fs').forEach(function(b){{
  b.addEventListener('click',function(){{sel(b.dataset.k);}});}});
document.querySelectorAll('.seg[data-kind="view"] button').forEach(function(b){{
  b.addEventListener('click',function(){{
    document.body.dataset.view=b.dataset.v;
    document.querySelectorAll('.seg[data-kind="view"] button').forEach(function(o){{
      o.setAttribute('aria-pressed',String(o===b));}});
  }});
}});
addEventListener('keydown',function(e){{
  if(e.key!=='ArrowLeft'&&e.key!=='ArrowRight') return;
  if(document.querySelector('.fsn.editing')||/SELECT|INPUT/.test((document.activeElement||{{}}).tagName)) return;
  var L=listFor(document.body.dataset.plat==='mob'?'mob':'desk'); if(!L.length) return;
  var cur=L.indexOf(current()); if(cur<0) cur=0;
  sel(L[(cur+(e.key==='ArrowRight'?1:L.length-1))%L.length]);
}});

var WANT=readHash();   /* before anything writes the hash */
buildThumbs(); setPlat('desk',true); applyFilter(WANT||K[0]); paintNames();

/* shared, durable names when the viewer can reach the store */
if(window.claude&&claude.use) claude.use('db').then(function(db){{
  if(!db) return;
  dbRef=db.doc('meta/names');
  dbRef.onSnapshot(function(snap){{
    if(!snap.exists) return;
    NAMES=migrate(snap.data()); paintNames();
    try{{ localStorage.setItem(LS,JSON.stringify(NAMES)); }}catch(e){{}}
  }},function(){{ dbRef=null; }});
}}).catch(function(){{}});
</script>
</body></html>
"""
wr('index.html', page)

print('built %d screens -> catalog.json, index.html (%.2f MB)' % (len(screens), os.path.getsize('index.html')/1048576))
