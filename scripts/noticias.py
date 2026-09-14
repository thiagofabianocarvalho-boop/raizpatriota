#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Raiz Patriota - coletor de noticias.

Le as fontes, monta os cartoes e reescreve APENAS o miolo entre os
marcadores <!--XXX:INI--> e <!--XXX:FIM--> do index.html.
Nada fora dos marcadores e tocado.

A Camara de Sao Jose nao e coletada: o robots.txt dela pede
explicitamente que robos nao acessem o site. O bloco recebe um aviso
fixo com o link para o site oficial.
"""

import base64
import html
import io
import re
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timezone, timedelta

from PIL import Image

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/128.0 Safari/537.36")
TZ = timezone(timedelta(hours=-3))
QTD = 6                      # cartoes por bloco
THUMB = (184, 138)           # 92x69 CSS em 2x
MESES = {"jan": 1, "fev": 2, "mar": 3, "abr": 4, "mai": 5, "jun": 6,
         "jul": 7, "ago": 8, "set": 9, "out": 10, "nov": 11, "dez": 12}
MESES_EXT = {"janeiro": 1, "fevereiro": 2, "marco": 3, "março": 3, "abril": 4,
             "maio": 5, "junho": 6, "julho": 7, "agosto": 8, "setembro": 9,
             "outubro": 10, "novembro": 11, "dezembro": 12}


def get(url, binary=False, timeout=30):
    url = urllib.parse.quote(url, safe=":/?&=%#+,;@!$'()*~")
    req = urllib.request.Request(url, headers={
        "User-Agent": UA,
        "Accept-Language": "pt-BR,pt;q=0.9",
    })
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = r.read()
    return data if binary else data.decode("utf-8", "ignore")


def limpa(t):
    t = re.sub(r"<[^>]+>", "", t or "")
    return html.unescape(t).strip()


# ----------------------------------------------------------------- RSS

def rss(url, limite=QTD):
    doc = get(url)
    itens = []
    for bloco in re.findall(r"<item[ >](.*?)</item>", doc, re.S)[: limite * 3]:
        def campo(tag):
            m = re.search(r"<%s[^>]*>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</%s>"
                          % (tag, tag), bloco, re.S)
            return limpa(m.group(1)) if m else ""

        link = campo("link")
        titulo = campo("title")
        if not link or not titulo:
            continue
        img = ""
        m = (re.search(r'<enclosure[^>]+url="([^"]+)"', bloco)
             or re.search(r'<media:content[^>]+url="([^"]+)"', bloco)
             or re.search(r'<img[^>]+src="([^"]+)"', bloco))
        if m:
            img = html.unescape(m.group(1))
        itens.append({"titulo": titulo, "url": link,
                      "data": data_de(campo("pubDate")), "img": img})
        if len(itens) >= limite:
            break
    return itens


def data_de(txt):
    txt = (txt or "").strip()
    for fmt in ("%a, %d %b %Y %H:%M:%S %z", "%d/%m/%Y %H:%M", "%d/%m/%Y"):
        try:
            d = datetime.strptime(txt.replace(" EST", "").strip(), fmt)
            return d.astimezone(TZ) if d.tzinfo else d.replace(tzinfo=TZ)
        except ValueError:
            pass
    m = re.search(r"(\d{1,2}) de (\w{3})\w*\.? de (\d{4})", txt)
    if m and m.group(2).lower() in MESES:
        return datetime(int(m.group(3)), MESES[m.group(2).lower()],
                        int(m.group(1)), tzinfo=TZ)
    return None


# ------------------------------------------------------------- Prefeitura

def prefeitura(limite=QTD):
    """Le o site da Prefeitura em vez do RSS: o feed deles atrasa um a dois
    dias. As manchetes ficam divididas entre o carrossel do topo e a lista
    de baixo, e a data esta no proprio endereco da materia."""
    base = "https://www.sjc.sp.gov.br"
    doc = get(base + "/noticias/")
    achados = {}
    for m in re.finditer(
            r'href="(/noticias/(\d{4})/([a-zç]+)/(\d{1,2})/[^"]+)"', doc, re.I):
        href, ano, mes, dia = m.groups()
        link = urllib.parse.urljoin(base, html.unescape(href))
        janela = doc[m.end():m.end() + 1600]
        titulo = ""
        for rx in (r'<h3[^>]*>\s*(.*?)\s*</h3>',
                   r'<img[^>]+alt="([^"]{8,})"',
                   r'<span[^>]*>\s*([^<]{8,})\s*</span>'):
            t = re.search(rx, janela, re.S)
            if t:
                titulo = limpa(t.group(1))
                break
        if not titulo:
            t = re.search(r'title="([^"]{8,})"', doc[m.start() - 300:m.end() + 300])
            titulo = limpa(t.group(1)) if t else ""
        im = re.search(r'<img[^>]+src="([^"]+)"', janela)
        reg = achados.setdefault(link, {
            "titulo": "", "url": link, "img": "",
            "data": datetime(int(ano), MESES_EXT.get(mes.lower(), 1), int(dia),
                             tzinfo=TZ)})
        if titulo and not reg["titulo"]:
            reg["titulo"] = titulo
        if im and not reg["img"]:
            reg["img"] = urllib.parse.urljoin(base, html.unescape(im.group(1)))

    itens = [v for v in achados.values() if v["titulo"]]
    itens.sort(key=lambda x: x["data"], reverse=True)
    return itens[:limite]


# --------------------------------------------------------------- Next.js

def nextjs(url, base, prefixo, limite=QTD):
    """Meon e Brasil Paralelo: mesmo padrao de marcacao (Next.js)."""
    doc = get(url)

    # As duas paginas misturam dois formatos de cartao na mesma listagem:
    # uns tem o titulo no aria-label do link, outros num <h3> dentro dele.
    achados = []
    for rx, ordem in (
        (r'<a[^>]+aria-label="([^"]+)"[^>]*href="(%s[^"]+)"' % prefixo, "th"),
        (r'<a[^>]+href="(%s[^"]+)"[^>]*aria-label="([^"]+)"' % prefixo, "ht"),
        (r'<a[^>]+href="(%s[^"]+)"[^>]*>.{0,400}?<h[34][^>]*>(.*?)</h[34]>'
         % prefixo, "ht"),
    ):
        for m in re.finditer(rx, doc, re.S):
            a, b = m.group(1), m.group(2)
            titulo, href = (a, b) if ordem == "th" else (b, a)
            achados.append((m.start(), limpa(titulo), href))
    achados.sort(key=lambda x: x[0])

    vistos, itens = set(), []
    for pos, titulo, href in achados:
        titulo = re.sub(r"^(Ver|Leia)\s*:\s*", "", titulo).strip()
        link = urllib.parse.urljoin(base, html.unescape(href))
        if link in vistos or not titulo:
            continue
        vistos.add(link)

        janela = doc[max(0, pos - 6000):pos]
        imgs = re.findall(r'/_next/image\?url=([^&"]+)', janela)
        img = urllib.parse.unquote(html.unescape(imgs[-1])) if imgs else ""

        depois = doc[pos:pos + 4000]
        dm = re.search(r"\d{1,2} de \w{3}\w*\.? de \d{4}", depois)
        itens.append({"titulo": titulo, "url": link,
                      "data": data_de(dm.group(0)) if dm else None, "img": img})
        if len(itens) >= limite:
            break
    return itens


def meon():
    return nextjs("https://www.meon.com.br/noticias",
                  "https://www.meon.com.br/", "/noticias/")


def bp():
    return nextjs("https://www.brasilparalelo.com.br/noticias",
                  "https://www.brasilparalelo.com.br/", "/noticias/")


def enriquece(itens):
    """Quando a fonte nao traz foto ou data, busca og:image e a data na
    propria materia."""
    for it in itens:
        if it.get("img") and it.get("data"):
            continue
        try:
            pag = get(it["url"], timeout=20)
        except Exception:
            continue
        if not it.get("img"):
            m = (re.search(r'<meta[^>]+property="og:image"[^>]+content="([^"]+)"', pag)
                 or re.search(r'<meta[^>]+content="([^"]+)"[^>]+property="og:image"', pag))
            if m:
                it["img"] = urllib.parse.urljoin(it["url"], html.unescape(m.group(1)))
        if not it.get("data"):
            m = re.search(r'<meta[^>]+(?:article:published_time|og:updated_time)'
                          r'"[^>]+content="([^"]+)"', pag)
            if m:
                try:
                    it["data"] = datetime.fromisoformat(
                        m.group(1).replace("Z", "+00:00")).astimezone(TZ)
                except ValueError:
                    pass
            if not it.get("data"):
                m = re.search(r"\d{1,2} de \w{3}\w*\.? de \d{4}", pag) \
                    or re.search(r"\d{2}/\d{2}/\d{4}", pag)
                if m:
                    it["data"] = data_de(m.group(0))
    return itens


# ----------------------------------------------------------------- imagem

def miniatura(url):
    if not url:
        return ""
    try:
        im = Image.open(io.BytesIO(get(url, binary=True, timeout=25)))
        im = im.convert("RGB")
        larg, alt = THUMB
        prop = max(larg / im.width, alt / im.height)
        im = im.resize((max(1, round(im.width * prop)),
                        max(1, round(im.height * prop))), Image.LANCZOS)
        esq = (im.width - larg) // 2
        topo = (im.height - alt) // 2
        im = im.crop((esq, topo, esq + larg, topo + alt))
        buf = io.BytesIO()
        im.save(buf, "WEBP", quality=72, method=4)
        return "data:image/webp;base64," + base64.b64encode(buf.getvalue()).decode()
    except Exception as e:
        print("      aviso: imagem falhou (%s)" % e, file=sys.stderr)
        return ""


# ---------------------------------------------------------------- cartoes

def cartoes(itens):
    saida = []
    for i, it in enumerate(itens, 1):
        thumb = miniatura(it.get("img"))
        titulo = html.escape(it["titulo"])
        dia = it["data"].strftime("%d/%m") if it.get("data") else ""
        em = "<em>%s</em>" % dia if dia else ""
        img = ('<img class="ft" loading="lazy" src="%s" alt="">' % thumb) if thumb else ""
        saida.append(
            '  <a class="nt%s" href="%s" target="_blank" rel="noopener">'
            '<span class="n">%02d</span>%s<span class="h">%s%s</span></a>'
            % (" comfoto" if thumb else "", html.escape(it["url"], quote=True),
               i, img, titulo, em))
    return "\n".join(saida)


AVISO_CAMARA = (
    '  <a class="nt" href="https://www.camarasjc.sp.gov.br/noticias/" '
    'target="_blank" rel="noopener"><span class="n">&middot;</span>'
    '<span class="h">A C&acirc;mara pede que as p&aacute;ginas dela n&atilde;o '
    'sejam lidas por rob&ocirc;s, e n&oacute;s respeitamos o pedido. '
    'Toque aqui para ver as not&iacute;cias no site oficial.</span></a>'
)


def troca(doc, chave, miolo):
    ini, fim = "<!--%s:INI-->" % chave, "<!--%s:FIM-->" % chave
    a, b = doc.find(ini), doc.find(fim)
    if a < 0 or b < 0:
        print("  ! marcador %s nao encontrado - bloco ignorado" % chave)
        return doc, False
    return doc[:a + len(ini)] + "\n" + miolo + "\n" + doc[b:], True


def main(caminho="index.html"):
    doc = original = open(caminho, encoding="utf-8").read()
    fontes = [
        ("MEON", "Meon", meon),
        ("PREF", "Prefeitura de SJC", prefeitura),
        ("OESTE", "Revista Oeste", lambda: rss("https://revistaoeste.com/politica/feed/")),
        ("BP", "Brasil Paralelo", bp),
    ]
    for chave, nome, fn in fontes:
        print("-> %s" % nome)
        try:
            itens = fn()
        except Exception as e:
            print("  ! falhou (%s) - bloco mantido como estava" % e)
            continue
        if not itens:
            print("  ! nenhuma noticia encontrada - bloco mantido como estava")
            continue
        itens = enriquece(itens)
        doc, ok = troca(doc, chave, cartoes(itens))
        if ok:
            print("  %d noticias, mais recente %s"
                  % (len(itens),
                     itens[0]["data"].strftime("%d/%m") if itens[0].get("data") else "sem data"))

    doc, _ = troca(doc, "CAMARA", AVISO_CAMARA)

    hoje = datetime.now(TZ).strftime("%d/%m/%Y")
    doc = re.sub(r"(<!--DATA:INI-->).*?(<!--DATA:FIM-->)",
                 r"\g<1>%s\g<2>" % hoje, doc, flags=re.S)

    if doc == original:
        print("\nNada mudou.")
        return 0
    open(caminho, "w", encoding="utf-8").write(doc)
    print("\nindex.html atualizado (%.0f KB)." % (len(doc.encode()) / 1024))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "index.html"))
