#!/usr/bin/env python3
"""
Fatura Bilgi Yardımcısı (prototip)
- İndirilenler klasörünü izler, yeni PDF faturaları yerelde işler.
- Çıktı: ~/FaturaYardimcisi/rapor.html ve faturalar.csv
- Hiçbir veri dışarı gönderilmez.

Kurulum:   pip3 install pypdf
Çalıştır:  python3 fatura_yardimcisi.py            (yalnızca yeni inen PDF'ler)
           python3 fatura_yardimcisi.py --hepsi    (klasördeki mevcut PDF'leri de işle)
           python3 fatura_yardimcisi.py --klasor ~/Downloads/faturalar
"""
import argparse, csv, hashlib, json, re, secrets, threading, time, webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from pypdf import PdfReader

OUT = Path.home() / "FaturaYardimcisi"
DB = OUT / "kayitlar.json"
CSV = OUT / "faturalar.csv"
KONTROL = "Kontrol gerekli"
TOKEN = secrets.token_urlsafe(16)
LOCK = threading.Lock()
STATE = {"html": "", "db": {}, "gorulen": set(), "klasor": None}
COLS = ["Fatura No", "Tarih", "Alıcı Firma", "VKN/TCKN", "Tutar", "Açıklama/Not", "Dosya"]


def pdf_metni(yol):
    r = PdfReader(str(yol))
    return "\n".join((p.extract_text() or "") for p in r.pages)


def ilk(rx, s, flags=re.I):
    m = re.search(rx, s, flags)
    return m.group(1).strip() if m else ""


ADRES_RX = r"(Mah\.?|Mahalle|Cad\.?|Cd\.?|Sok\.?|Sk\.?|Bulvar|Blv\.?|No\s*:|Caddesi|Sokak)"
FIRMA_SONEK_RX = r"(A\.?\s?Ş\.?|LTD\.?(\s*ŞTİ\.?)?|ŞTİ\.?|ŞİRKETİ|LİMİTED|ANONİM|KOLL\.?|ORT\.?)\s*$"
VKN_RX = r"(?:VKN|TCKN|Vergi\s*(?:Kimlik\s*)?No|T\.?C\.?\s*Kimlik\s*No)\s*[:\-]?\s*(\d{10,11})"


def alici_blogu(t):
    """'SAYIN' satırından sonra: ilk satır alıcı adı, sonraki ilk VKN/TCKN alıcıya aittir."""
    m = re.search(r"^\s*SAYIN\s*:?\s*$", t, re.I | re.M)
    if not m:
        return "", ""
    sonrasi = t[m.end():]
    satirlar = [l.strip() for l in sonrasi.splitlines() if l.strip()]
    ad = satirlar[0] if satirlar else ""
    # Ad iki satıra bölünmüşse (ilk satır firma son ekiyle bitmiyor, ikinci satır adres değil) birleştir
    if len(satirlar) > 1 and not re.search(FIRMA_SONEK_RX, ad, re.I) and not re.search(ADRES_RX, satirlar[1], re.I):
        ad += " " + satirlar[1]
    v = re.search(VKN_RX, sonrasi, re.I)
    return ad, (v.group(1) if v else "")


def notlar(t):
    """'Genel Açıklamalar' kutusundaki satırlardan şablon/IBAN/banka satırlarını ayıklar."""
    m = re.search(r"Genel\s*Açıklamalar", t, re.I)
    if not m:
        return []
    bulunan, iban_sonrasi = [], False
    for l in (x.strip() for x in t[m.end():].splitlines()):
        if not l:
            continue
        if re.match(r"İBAN\s*BİLGİLERİ", l, re.I):
            iban_sonrasi = True
            hesap_sahibi_atla = True
            continue
        if iban_sonrasi and hesap_sahibi_atla:  # IBAN başlığından sonraki satır hesap sahibi
            hesap_sahibi_atla = False
            continue
        if re.match(r"YALNIZ\b", l) or re.match(r"İrsaliye yerine geçer", l, re.I):
            continue
        if re.match(r"TR\s?\d{2}(\s?\d{4}){3,}", l) or re.search(r"BANKASI|BANK(ASI)?\s*$|KATILIM", l):
            continue
        bulunan.append(re.sub(r"\s+", " ", l))
    return bulunan


def ayikla(t):
    ad, vkn = alici_blogu(t)
    no = ilk(r"Fatura\s*No\s*[:\-]?\s*([A-Z0-9]{8,20})", t)
    return {
        "Fatura No": no,
        "Tarih": ilk(r"Fatura\s*Tarihi\s*[:\-]?\s*(\d{2}[-./]\d{2}[-./]\d{4})", t),
        "Alıcı Firma": ad,
        "VKN/TCKN": vkn,
        "Tutar": ilk(r"Ödenecek\s*Tutar\s*[:\-]?\s*([\d.,]+\s*(?:TL|TRY)?)", t),
        "Açıklama/Not": " | ".join(notlar(t)),
    }


def yukle():
    return json.loads(DB.read_text("utf-8")) if DB.exists() else {}


def kaydet(db):
    OUT.mkdir(parents=True, exist_ok=True)
    DB.write_text(json.dumps(db, ensure_ascii=False, indent=1), "utf-8")
    satirlar = sorted(db.values(), key=lambda r: r.get("_ts", 0), reverse=True)  # en yeni indirilen üstte
    with CSV.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, COLS, extrasaction="ignore")
        w.writeheader()
        w.writerows(satirlar)
    veri = json.dumps(satirlar, ensure_ascii=False).replace("</", "<\\/")
    STATE["html"] = SABLON.replace("__VERI__", veri).replace("__KONTROL__", KONTROL).replace("__TOKEN__", TOKEN)


def isle(yol, db):
    h = hashlib.sha256(yol.read_bytes()).hexdigest()
    if h in db:
        return False
    try:
        kayit = ayikla(pdf_metni(yol))
        if not any(kayit.values()):
            kayit = {c: KONTROL for c in COLS[:4]}
            kayit["Açıklama/Not"] = "PDF'den metin çıkarılamadı (taranmış olabilir)"
    except Exception as e:
        kayit = {c: KONTROL for c in COLS[:4]}
        kayit["Açıklama/Not"] = f"Okuma hatası: {e}"
    for c in COLS[:5]:
        kayit[c] = kayit.get(c) or KONTROL
    kayit["Dosya"] = yol.name
    st = yol.stat()
    kayit["_ts"] = getattr(st, "st_birthtime", st.st_mtime)  # dosyanın indirilme (oluşma) zamanı
    # aynı fatura numarası başka dosyada tekrar inmişse mükerrer sayma
    if kayit["Fatura No"] != KONTROL and any(r["Fatura No"] == kayit["Fatura No"] for r in db.values()):
        return False
    db[h] = kayit
    return True


def hazir_mi(yol):
    """Chrome indirmeyi bitirene kadar bekle (boyut sabitlenmeli)."""
    a = -1
    for _ in range(10):
        b = yol.stat().st_size
        if b == a and b > 0:
            return True
        a = b
        time.sleep(0.5)
    return False


class Sunucu(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _yanit(self, kod, govde=b"", tip="text/plain; charset=utf-8"):
        self.send_response(kod)
        self.send_header("Content-Type", tip)
        self.send_header("Content-Length", str(len(govde)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(govde)

    def do_GET(self):
        if self.path.split("#")[0] in ("/", "/index.html"):
            with LOCK:
                self._yanit(200, STATE["html"].encode("utf-8"), "text/html; charset=utf-8")
        else:
            self._yanit(404)

    def do_POST(self):
        if self.path != "/temizle?t=" + TOKEN:
            return self._yanit(403)
        with LOCK:
            STATE["db"].clear()
            STATE["gorulen"].update(STATE["klasor"].glob("*.pdf"))  # eski PDF'ler tekrar eklenmesin
            kaydet(STATE["db"])
        self._yanit(200, b"ok")


def sunucu_baslat():
    for port in range(8765, 8776):
        try:
            srv = ThreadingHTTPServer(("127.0.0.1", port), Sunucu)  # yalnızca bu bilgisayardan erişilir
            threading.Thread(target=srv.serve_forever, daemon=True).start()
            return f"http://127.0.0.1:{port}/"
        except OSError:
            continue
    raise SystemExit("Boş port bulunamadı (8765-8775).")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--klasor", default=str(Path.home() / "Downloads"))
    ap.add_argument("--hepsi", action="store_true")
    a = ap.parse_args()
    klasor = Path(a.klasor).expanduser()
    OUT.mkdir(parents=True, exist_ok=True)
    db = yukle()
    gorulen = set() if a.hepsi else {p for p in klasor.glob("*.pdf")}
    STATE.update(db=db, gorulen=gorulen, klasor=klasor)
    with LOCK:
        kaydet(db)
    url = sunucu_baslat()
    webbrowser.open(url)
    print(f"İzleniyor: {klasor}\nRapor: {url}\nDurdurmak için Ctrl+C")
    try:
        while True:
            for p in sorted(klasor.glob("*.pdf"), key=lambda x: x.stat().st_mtime):
                if p in gorulen:
                    continue
                if not hazir_mi(p):
                    continue
                with LOCK:
                    gorulen.add(p)
                    if isle(p, db):
                        kaydet(db)
                        print("+", p.name)
            time.sleep(2)
    except KeyboardInterrupt:
        print("\nDurduruldu.")


SABLON = """<!doctype html><html lang="tr"><head><meta charset="utf-8">
<title>Fatura Bilgi Yardımcısı</title>
<style>
body{font:14px -apple-system,system-ui,sans-serif;margin:24px;color:#222}
input{padding:8px 10px;width:340px;font-size:14px}
button{padding:8px 12px;font-size:14px;cursor:pointer}
.sil{color:#b00020}
table{border-collapse:collapse;width:100%;margin-top:14px}
th,td{border-bottom:1px solid #ddd;padding:7px 9px;text-align:left;vertical-align:top}
th{background:#f4f4f4;position:sticky;top:0}
.k{background:#fff3cd}
@media(prefers-color-scheme:dark){body{background:#1b1b1b;color:#eee}th{background:#2a2a2a}td,th{border-color:#444}input,button{background:#2a2a2a;color:#eee;border:1px solid #555}.k{background:#5a4a10}.sil{color:#ff8a80}}
</style></head><body>
<h2>Fatura Bilgi Yardımcısı</h2>
<input id="q" placeholder="Firma, fatura no veya not ara…">
<button id="s"></button>
<button id="t" class="sil">Listeyi temizle</button>
<span id="n"></span>
<table><thead><tr id="h"></tr></thead><tbody id="b"></tbody></table>
<script>
const D=__VERI__, C=["Fatura No","Tarih","Alıcı Firma","VKN/TCKN","Tutar","Açıklama/Not"], K="__KONTROL__", T="__TOKEN__";
const q=document.getElementById("q"), sb=document.getElementById("s");
q.value=decodeURIComponent(location.hash.slice(1));
let eskiUste=true; try{eskiUste=localStorage.getItem("sira")!=="eski";}catch(e){}
document.getElementById("h").innerHTML=C.map(c=>"<th>"+c+"</th>").join("");
const esc=s=>String(s??"").replace(/[&<>]/g,m=>({"&":"&amp;","<":"&lt;",">":"&gt;"}[m]));
function draw(){
 sb.textContent="İndirme sırası: "+(eskiUste?"yeni → eski":"eski → yeni");
 const t=q.value.toLocaleLowerCase("tr");history.replaceState(null,"","#"+encodeURIComponent(q.value));
 const R=D.filter(r=>!t||C.some(c=>String(r[c]||"").toLocaleLowerCase("tr").includes(t)))
  .sort((a,b)=>(eskiUste?-1:1)*((a._ts||0)-(b._ts||0)));
 document.getElementById("n").textContent=R.length+" / "+D.length+" fatura";
 document.getElementById("b").innerHTML=R.map(r=>"<tr>"+C.map(c=>"<td"+(r[c]===K?" class=k":"")+">"+esc(r[c])+"</td>").join("")+"</tr>").join("");}
q.oninput=draw;
sb.onclick=()=>{eskiUste=!eskiUste;try{localStorage.setItem("sira",eskiUste?"yeni":"eski");}catch(e){}draw();};
document.getElementById("t").onclick=async()=>{
 if(!confirm("Listedeki tüm kayıtlar silinecek. PDF dosyalarına dokunulmaz. Devam edilsin mi?"))return;
 const r=await fetch("/temizle?t="+T,{method:"POST"});
 if(r.ok)location.reload(); else alert("Temizleme başarısız oldu.");};
draw(); setTimeout(()=>location.reload(),8000);
</script></body></html>"""

if __name__ == "__main__":
    main()
