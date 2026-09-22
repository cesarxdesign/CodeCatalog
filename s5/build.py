"""Build each screen into a self-contained folder: fonts embedded, assets copied in.

src/<name>.html  ->  <name>/index.html + <name>/assets/*
"""
import base64, pathlib, re, shutil, sys

HERE = pathlib.Path(__file__).parent
POOL = HERE / "pool"
SRC = HERE / "src"

def b64(name):
    return base64.b64encode((POOL / name).read_bytes()).decode()

FONTS = f"""@font-face {{ font-family: 'Montserrat'; font-style: normal; font-weight: 100 900; font-display: block;
  src: url(data:font/woff2;base64,{b64('montserrat-latin.woff2')}) format('woff2'); }}
@font-face {{ font-family: 'Montserrat'; font-style: italic; font-weight: 400; font-display: block;
  src: url(data:font/woff2;base64,{b64('montserrat-italic-latin.woff2')}) format('woff2'); }}"""

COMMON = (SRC / "common.css").read_text()

IOS = """<div class="abs ios" data-node-id="{id}">
    <div class="abs ios-bg">
      <img class="abs" style="left:0;top:0" src="assets/ios-background.svg" alt="">
      <div class="abs ios-div"></div>
    </div>
    <p class="tx tx-c t-ios-url" style="left:145px;top:40px;width:84px;height:15px"><span class="trk">getpenfold.com</span></p>
    <div class="abs ios-status">
      <p class="tx tx-c t-ios-time" style="left:19.894px;top:14px;width:54px;height:18px"><span class="trk">{time}</span></p>
      <div class="abs ios-ctr">
        <img class="abs" style="left:42.5px;top:0" src="assets/ios-battery.svg" alt="">
        <div class="abs ios-fill"></div>
        <img class="abs" style="left:0;top:0.4401px" src="assets/ios-signal.svg" alt="">
        <img class="abs" style="left:22.1001px;top:0.24px" src="assets/ios-wifi.svg" alt="">
      </div>
    </div>
  </div>"""

def build(name):
    html = (SRC / f"{name}.html").read_text()
    html = html.replace("/*@FONTS*/", FONTS).replace("/*@COMMON*/", COMMON)
    html = re.sub(r'<!--@IOS id="([^"]+)" time="([^"]+)"-->',
                  lambda m: IOS.format(id=m.group(1), time=m.group(2)), html)
    out = HERE / name
    if out.exists():
        shutil.rmtree(out)
    (out / "assets").mkdir(parents=True)
    used = sorted(set(re.findall(r'assets/([\w.-]+\.svg)', html)))
    for a in used:
        shutil.copy(POOL / a, out / "assets" / a)
    (out / "index.html").write_text(html)
    print(f"{name}: {len(used)} assets, {len(html)//1024} KB")

for n in sys.argv[1:] or [p.stem for p in SRC.glob("*.html")]:
    build(n)
