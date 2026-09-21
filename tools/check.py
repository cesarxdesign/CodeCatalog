#!/usr/bin/env python3
"""CodeCatalog self-test. Run before trusting the catalogue:  python3 tools/check.py

Checks, in order:
  1. every screen folder has a complete meta.json and every file it names exists
  2. catalog.json, index.html and every embed.html are newer than what they are built from
  3. nothing refers to a path on this machine (/Users, /private, file://)
  4. each embed loads the web fonts its CSS asks for
  5. every embed.html and screen.html really renders in headless Chrome: the shadow root
     attaches, there is text on the page, it has height, and no script throws

Exit code 0 means every screen is usable. Anything else is listed with the screen it is in.
"""
import html, json, os, re, subprocess, sys, tempfile
from concurrent.futures import ThreadPoolExecutor

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)
CHROME = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
REQUIRED = ['id', 'project', 'platform', 'name', 'frame', 'interactive', 'files', 'embed_from', 'fonts']
problems, warnings = [], []
def bad(where, msg): problems.append('%-38s %s' % (where, msg))
def warn(where, msg): warnings.append('%-38s %s' % (where, msg))
def rd(p): return open(p, encoding='utf-8').read()

# ---------- 1. metadata and files ----------
screens = []
for dirpath, _, files in os.walk('screens'):
    if 'meta.json' not in files: continue
    try: m = json.load(open(os.path.join(dirpath, 'meta.json'), encoding='utf-8'))
    except Exception as e: bad(dirpath, 'meta.json does not parse: %s' % e); continue
    key = '%s/%s/%s' % (m.get('project'), m.get('platform'), m.get('id'))
    for f in REQUIRED:
        if f not in m: bad(key, 'meta.json missing "%s"' % f)
    if dirpath.replace(os.sep, '/') != 'screens/' + key: bad(key, 'folder does not match project/platform/id')
    f = m.get('files', {})
    for name in [f.get('screen'), f.get('embed'), f.get('preview'), m.get('embed_from')] + f.get('extra', []) + f.get('source', []):
        if name and not os.path.exists(os.path.join(dirpath, name)): bad(key, 'missing file ' + name)
    if m.get('platform') == 'desktop' and bool(m.get('interactive')) != bool(m.get('live')):
        bad(key, 'interactive screens need a live link, static ones must not have one')
    screens.append((key, dirpath, m))
if not screens: bad('screens/', 'no screens found')

# ---------- 2. built outputs are current ----------
# Compared by content fingerprint, never by timestamp: copies and git clones reset timestamps.
import hashlib
def fingerprint(d, m):
    h = hashlib.sha1()
    for name in ('meta.json', m['embed_from']): h.update(open(os.path.join(d, name), 'rb').read())
    h.update(open(os.path.join(ROOT, 'tools', 'build.py'), 'rb').read())
    return h.hexdigest()[:12]
fps = {}
for key, d, m in screens:
    try: fps[key] = fingerprint(d, m)
    except OSError: continue
    emb = os.path.join(d, 'embed.html')
    if os.path.exists(emb):
        got = (re.search(r'· fp ([0-9a-f]{12})', rd(emb)) or [None, None])[1]
        if got != fps[key]: bad(key, 'embed.html is out of date - run tools/build.py')
build = hashlib.sha1(''.join(k + fps[k] for k in sorted(fps, key=lambda k: next(
    (m['project'], {'desktop': 0, 'mobile': 1}[m['platform']], m['order']) for kk, _, m in screens if kk == k))).encode()).hexdigest()[:12]
if os.path.exists('catalog.json'):
    cat = json.load(open('catalog.json', encoding='utf-8'))
    if cat.get('build') != build: bad('catalog.json', 'out of date - run tools/build.py')
    have = sorted(k for k, _, _ in screens); listed = sorted(s['key'] for s in cat['screens'])
    if have != listed: bad('catalog.json', 'does not match the screen folders - run tools/build.py')
    for s in cat['screens']:
        for v in s['files'].values():
            for p in (v if isinstance(v, list) else [v]):
                if not os.path.exists(p): bad(s['key'], 'catalog.json points at missing ' + p)
else: bad('catalog.json', 'missing - run tools/build.py')
if not os.path.exists('index.html'): bad('index.html', 'missing - run tools/build.py')
elif ('<meta name="cc-build" content="%s">' % build) not in rd('index.html'): bad('index.html', 'out of date - run tools/build.py')

# ---------- 3. no machine paths ----------
for dirpath, _, files in os.walk('.'):
    if '.git' in dirpath or '.cache' in dirpath: continue
    for fn in files:
        if fn.endswith(('.html', '.json', '.md', '.py')) and fn != 'check.py':
            if re.search(r'/Users/|/private/|scratch-workspaces|file://', rd(os.path.join(dirpath, fn))):
                bad(os.path.join(dirpath, fn), 'refers to a path on this machine')

# ---------- 4. fonts ----------
for key, d, m in screens:
    p = os.path.join(d, 'embed.html')
    if not os.path.exists(p): continue
    e = rd(p); link = (re.search(r'<link rel="stylesheet" href="([^"]+)"', e) or [None, ''])[1]
    for fam in ('Montserrat', 'Roboto Mono'):
        if re.search(r'''["']?%s["']?''' % fam, e.split('</style>')[0]) and fam.replace(' ', '+') not in link:
            bad(key, 'embed uses %s but does not load it' % fam)

# ---------- 5. it renders ----------
PROBE_HEAD = "<script>window.__cc_err=[];addEventListener('error',function(e){__cc_err.push(String(e.message))});</script>"
PROBE_TAIL = """<script>addEventListener('load',function(){setTimeout(function(){
  var txt=0, roots=0, h=document.documentElement.scrollHeight;
  (function walk(n){ if(n.shadowRoot){roots++; txt+=n.shadowRoot.textContent.replace(/\\s+/g,'').length; walk(n.shadowRoot);}
    for(var c=n.firstElementChild;c;c=c.nextElementSibling) walk(c); })(document.documentElement);
  txt+=document.body.innerText.replace(/\\s+/g,'').length;
  document.documentElement.setAttribute('data-cc-result',JSON.stringify({roots:roots,text:txt,height:h,errors:__cc_err}));
},400)});</script>"""
def probe(key, path, kind, expect_shadow):
    src = rd(path)
    if kind == 'embed': page = '<!doctype html><meta charset="utf-8"><body>' + PROBE_HEAD + src + PROBE_TAIL + '</body>'
    else:
        page = re.sub(r'(<head[^>]*>)', r'\1' + PROBE_HEAD.replace('\\', '\\\\'), src, count=1) if '<head' in src else PROBE_HEAD + src
        page = page.replace('</body>', PROBE_TAIL + '</body>') if '</body>' in page else page + PROBE_TAIL
    with tempfile.NamedTemporaryFile('w', suffix='.html', delete=False, encoding='utf-8') as t:
        t.write(page); tmp = t.name
    try:
        out = subprocess.run([CHROME, '--headless', '--enable-unsafe-swiftshader', '--virtual-time-budget=6000',
                              '--window-size=1400,1000', '--dump-dom', 'file://' + tmp],
                             capture_output=True, text=True, timeout=60).stdout
    finally: os.unlink(tmp)
    m = re.search(r'data-cc-result="([^"]*)"', out)
    if not m: return (key, kind, 'did not finish loading')
    r = json.loads(html.unescape(m.group(1)))
    if r['errors']: return (key, kind, 'script error: ' + r['errors'][0])
    if expect_shadow and r['roots'] < 1: return (key, kind, 'shadow root did not attach')
    if r['text'] < 20: return (key, kind, 'renders almost no text (%d chars)' % r['text'])
    if r['height'] < 300: return (key, kind, 'renders %dpx tall' % r['height'])
    return None

if not os.path.exists(CHROME):
    warn('render check', 'skipped - Google Chrome not found at ' + CHROME)
else:
    jobs = []
    for key, d, m in screens:
        jobs.append((key, os.path.join(d, 'embed.html'), 'embed', True))
        jobs.append((key, os.path.join(d, 'screen.html'), 'screen', m['platform'] == 'mobile'))
    with ThreadPoolExecutor(4) as ex:
        for res in ex.map(lambda j: probe(*j) if os.path.exists(j[1]) else (j[0], j[2], 'file missing'), jobs):
            if res: bad(res[0], '%s.html: %s' % (res[1], res[2]))
    rendered = len(jobs)

# ---------- report ----------
print('CodeCatalog check · %d screens' % len(screens))
if os.path.exists(CHROME): print('rendered %d pages in headless Chrome' % rendered)
for w in warnings: print('  warn  ' + w)
for p in problems: print('  FAIL  ' + p)
print('OK - every screen is usable.' if not problems else '%d problem(s).' % len(problems))
sys.exit(1 if problems else 0)
