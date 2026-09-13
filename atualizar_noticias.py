#!/usr/bin/env python3
"""Atualiza as seções de notícias do index.html:
   - Prefeitura de São José dos Campos  (marcador PREF)
   - Câmara Municipal de São José dos Campos (marcador CAMARA)
   - Revista Oeste, seção de política, via RSS (marcador OESTE)
   - Meon, Vale do Paraíba e Região (marcador MEON)
   - Brasil Paralelo, notícias, via RSS (marcador BP)
Se uma fonte falhar, a lista antiga dela permanece e o script sai com erro,
para o GitHub avisar. Nunca publica lista vazia."""
import base64, io, re, html, sys, urllib.parse, urllib.request
try:
    from PIL import Image
except ImportError:
    Image = None

QTD, MIN = 6, 3
MES = {'janeiro':'01','fevereiro':'02','marco':'03','março':'03','abril':'04','maio':'05','junho':'06',
       'julho':'07','agosto':'08','setembro':'09','outubro':'10','novembro':'11','dezembro':'12'}

def baixar(url, enc):
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 (RaizPatriota)'})
    return urllib.request.urlopen(req, timeout=40).read().decode(enc, 'replace')

def camara():
    h = baixar('https://www.camarasjc.sp.gov.br/noticias/', 'cp1252')
    itens = []
    for b in re.findall(r'<div class="col-lg-12 noticia">(.*?)</div>\s*</div>\s*</div>', h, re.S):
        link = re.search(r'href="(https://www\.camarasjc\.sp\.gov\.br/noticias/\d+/[^"]+)"', b)
        tit = re.search(r'<h[1-6][^>]*>(.*?)</h[1-6]>', b, re.S)
        dt = re.search(r'<time datetime="(\d{4})-(\d{2})-(\d{2})', b)
        if not (link and tit): continue
        t = re.sub(r'\s+', ' ', html.unescape(re.sub('<[^>]+>', '', tit.group(1)))).strip()
        im = re.search(r'src="(/arquivo/noticias/[^"]+)"', b)
        if t: itens.append({'u': link.group(1), 't': t,
                            'd': f'{dt.group(3)}/{dt.group(2)}' if dt else '',
                            'img': 'https://www.camarasjc.sp.gov.br' + im.group(1) if im else ''})
        if len(itens) >= QTD: break
    return itens

def prefeitura():
    h = baixar('https://www.sjc.sp.gov.br/noticias/', 'utf-8')
    pat = re.compile(r'href="(/noticias/(\d{4})/([a-zç]+)/(\d{1,2})/[a-z0-9\-]+/)"([^>]*)>(.*?)</a>', re.S)
    vist, fotos = {}, {}
    for m in pat.finditer(h):
        url, ano, mes, dia, attrs, inner = m.groups()
        im = re.search(r'src="(/media/[^"?]+\.(?:jpg|jpeg|png|webp|avif))', inner)
        if im:                       # a foto pode estar num link só de imagem,
            fotos.setdefault(url, 'https://www.sjc.sp.gov.br' + im.group(1))
        t = re.search(r'title="([^"]{12,})"', attrs)
        tit = t.group(1) if t else ''
        if not tit:
            sp = re.search(r'<span[^>]*>(.*?)</span>', inner, re.S)
            if sp: tit = re.sub('<[^>]+>', '', sp.group(1))
        if not tit:
            hh = re.search(r'<h[1-6][^>]*>(.*?)</h[1-6]>', inner, re.S)
            if hh: tit = re.sub('<[^>]+>', '', hh.group(1))
        tit = re.sub(r'\s+', ' ', html.unescape(tit)).strip()
        if not tit or tit.lower().endswith(('.jpg', '.png')) or url in vist: continue
        vist[url] = {'t': tit, 'd': f"{int(dia):02d}/{MES.get(mes,'??')}",
                     'o': f"{ano}{MES.get(mes,'00')}{int(dia):02d}", 'img': ''}
    for u in vist:                   # separado do título, noutra âncora
        vist[u]['img'] = fotos.get(u, '')
    itens = [{'u': 'https://www.sjc.sp.gov.br' + u, **v} for u, v in vist.items()]
    itens.sort(key=lambda x: x['o'], reverse=True)
    return itens[:QTD]

def oeste():
    x = baixar('https://revistaoeste.com/politica/feed/', 'utf-8')
    MESI = {'Jan':'01','Feb':'02','Mar':'03','Apr':'04','May':'05','Jun':'06',
            'Jul':'07','Aug':'08','Sep':'09','Oct':'10','Nov':'11','Dec':'12'}
    itens = []
    for b in re.findall(r'<item>(.*?)</item>', x, re.S)[:QTD]:
        t = re.search(r'<title>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</title>', b, re.S)
        l = re.search(r'<link>(.*?)</link>', b, re.S)
        d = re.search(r'<pubDate>\w+, (\d{2}) (\w{3})', b)
        if not (t and l): continue
        im = re.search(r'src=[\\"\']([^"\'\\]+-\d+x\d+\.[a-z.]{3,12})', b)
        if not im: im = re.search(r'<media:content url="([^"]+)"', b)
        itens.append({'u': l.group(1).strip(),
                      't': re.sub(r'\s+', ' ', html.unescape(t.group(1))).strip(),
                      'd': f"{d.group(1)}/{MESI.get(d.group(2),'??')}" if d else '',
                      'img': html.unescape(im.group(1)) if im else ''})
    return itens

def meon():
    """Meon — editoria Vale do Paraíba e Região. Página renderizada no servidor."""
    h = baixar('https://www.meon.com.br/noticias/vale-do-paraiba-regiao', 'utf-8')
    itens, vistos = [], set()
    for a in re.findall(r'<article[^>]*>(.*?)</article>', h, re.S):
        l = re.search(r'href="(/noticias/[a-z0-9\-/]{25,})"', a)
        t = re.search(r'<h[1-6][^>]*>(.*?)</h[1-6]>', a, re.S)
        d = re.search(r'dateTime="(\d{4})-(\d{2})-(\d{2})', a)
        if not (l and t): continue
        tit = re.sub(r'\s+', ' ', html.unescape(re.sub('<[^>]+>', '', t.group(1)))).strip()
        if len(tit) < 15 or l.group(1) in vistos: continue
        vistos.add(l.group(1))
        img = re.search(r'url=([^&"\s]+)', a)
        foto = urllib.parse.unquote(html.unescape(img.group(1))) if img else ''
        if not foto.startswith('https://'): foto = ''
        itens.append({'u': 'https://www.meon.com.br' + l.group(1), 't': tit,
                      'd': f'{d.group(3)}/{d.group(2)}' if d else '', 'img': foto})
        if len(itens) >= QTD: break
    return itens

def brasilparalelo():
    """Brasil Paralelo — seção de notícias, via RSS."""
    x = baixar('https://www.brasilparalelo.com.br/rss.xml', 'utf-8')
    MESI = {'Jan':'01','Feb':'02','Mar':'03','Apr':'04','May':'05','Jun':'06',
            'Jul':'07','Aug':'08','Sep':'09','Oct':'10','Nov':'11','Dec':'12'}
    itens = []
    for b in re.findall(r'<item>(.*?)</item>', x, re.S):
        l = re.search(r'<link>(.*?)</link>', b, re.S)
        t = re.search(r'<title>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</title>', b, re.S)
        d = re.search(r'<pubDate>\w+, (\d{2}) (\w{3})', b)
        if not (l and t): continue
        link = l.group(1).strip()
        if '/noticias/' not in link: continue
        im = re.search(r'<enclosure url="([^"]+)"', b)
        itens.append({'u': link,
                      't': re.sub(r'\s+', ' ', html.unescape(t.group(1))).strip(),
                      'd': f"{d.group(1)}/{MESI.get(d.group(2),'??')}" if d else '',
                      'img': html.unescape(im.group(1)) if im else ''})
        if len(itens) >= QTD: break
    return itens

def miniatura(url, larg=184):
    """Baixa a foto, recorta em 4:3, reduz e devolve embutida no próprio HTML.
    Se algo falhar, devolve '' e a linha fica sem foto."""
    if not url or Image is None:
        return ''
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 (RaizPatriota)'})
        dados = urllib.request.urlopen(req, timeout=25).read()
        im = Image.open(io.BytesIO(dados)).convert('RGB')
        w, h = im.size
        alvo = w * 3 // 4
        if h > alvo:                       # recorta a altura, mantendo o centro
            topo = (h - alvo) // 3
            im = im.crop((0, topo, w, topo + alvo))
        else:
            novo = h * 4 // 3
            esq = max(0, (w - novo) // 2)
            im = im.crop((esq, 0, esq + min(novo, w), h))
        im = im.resize((larg, larg * 3 // 4), Image.LANCZOS)
        buf = io.BytesIO(); im.save(buf, 'WEBP', quality=72, method=5)
        return 'data:image/webp;base64,' + base64.b64encode(buf.getvalue()).decode()
    except Exception:
        return ''

def esc(t):
    return t.replace('&','&amp;').replace('<','&lt;').replace('>','&gt;').replace('"','&quot;')

def escrever(marca, itens, pagina):
    def linha(i, x):
        emb = miniatura(x.get('img', ''))
        foto = f'<img class="ft" loading="lazy" src="{emb}" alt="">' if emb else ''
        cls = 'nt comfoto' if foto else 'nt'
        return (f'  <a class="{cls}" href="{esc(x["u"])}" target="_blank" rel="noopener">'
                f'<span class="n">{i+1:02d}</span>{foto}'
                f'<span class="h">{esc(x["t"])}<em>{esc(x["d"])}</em></span></a>\n')
    linhas = ''.join(linha(i, x) for i, x in enumerate(itens))
    novo = f'<!--{marca}:INI-->\n' + linhas + f'<!--{marca}:FIM-->'
    if f'<!--{marca}:INI-->' not in pagina:
        raise RuntimeError(f'marcadores {marca} não encontrados no index.html')
    return re.sub(rf'<!--{marca}:INI-->.*?<!--{marca}:FIM-->', lambda m: novo, pagina, flags=re.S)

def main():
    pagina = open('index.html', encoding='utf-8').read()
    original, erros = pagina, []
    for marca, fonte, nome in [('PREF', prefeitura, 'Prefeitura'), ('CAMARA', camara, 'Câmara'), ('OESTE', oeste, 'Revista Oeste'), ('MEON', meon, 'Meon'), ('BP', brasilparalelo, 'Brasil Paralelo')]:
        try:
            itens = fonte()
            if len(itens) < MIN:
                raise RuntimeError(f'só {len(itens)} notícia(s) — o layout pode ter mudado')
            pagina = escrever(marca, itens, pagina)
            print(f'{nome}: {len(itens)} notícias.')
        except Exception as e:
            erros.append(f'{nome}: {e}')
            print(f'{nome}: FALHOU — {e}')
    if pagina != original:
        open('index.html', 'w', encoding='utf-8').write(pagina)
        print('index.html atualizado.')
    else:
        print('Nada mudou.')
    if erros:
        sys.exit(1)

if __name__ == '__main__':
    main()
