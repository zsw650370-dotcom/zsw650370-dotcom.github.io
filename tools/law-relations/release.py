import argparse
import html
import json
import re
import shutil
from collections import defaultdict
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

INVESTMENT = 'https://tfs.mofcom.gov.cn/fl/art/2021/art_6fec75c3a5bf436ba81173c46f9a9782.html'
ENVIRONMENT = 'https://www.mee.gov.cn/ywgz/fgbz/fl/202603/t20260313_1146496.shtml'
REPEALED = {
    '2c909fdd678bf17901678bf884f40acd': ('中外合作经营企业法', '2020-01-01', '外商投资法第四十二条', INVESTMENT),
    '2c909fdd678bf17901678bf82132091f': ('外资企业法', '2020-01-01', '外商投资法第四十二条', INVESTMENT),
    '2c909fdd678bf17901678bf76c1d0717': ('环境保护法', '2026-08-15', '生态环境法典第一千二百四十二条', ENVIRONMENT),
}
CIVIL = '中华人民共和国民法典'
PROCEDURE = '/laws/ff8081818a21dc13018b425303b7086d/'
DEBT = {
    '直接相关': [(675, '借款何时该还，取决于约定期限。期限仍无法确定时，贷款人可以催告借款人在合理期限内返还。'),
             (676, '已经逾期还款时，查约定或国家有关规定如何确定逾期利息。')],
    '未约定利息': [(680, '查借款期间的利息。没有约定利息的，视为没有利息。自然人之间约定不明的，也视为没有利息。')],
    '有保证人': [(681, '存在保证约定时，先确认第三人是否承诺在债务人不履行时承担责任。'),
              (686, '存在保证但方式约定不明时，查一般保证规则。'),
              (692, '要求保证人承担责任前，先核对保证期间及其起算。')],
    '诉讼时效': [(188, '查一般诉讼时效及起算规则，具体起算须结合还款期限和事实。'),
              (195, '已经提出履行请求、对方同意履行或提起诉讼等情形，查诉讼时效是否中断。')],
    '申请支付令': [(PROCEDURE + '225/', '请求给付金钱或有价证券、双方没有其他债务纠纷且能够送达时，查向有管辖权的基层法院申请支付令的条件。'),
               (PROCEDURE + '227/', '申请获受理后，查法院审查、债务人提出书面异议的期限及未异议时申请执行的条件。')],
}
NUM = '[零〇一二两三四五六七八九十百千万0-9０-９]+'
ARTICLE = re.compile(rf'第\s*({NUM})\s*条(?:之({NUM}))?')
QUALIFIER = rf'(?:\s*第{NUM}[款项])*'
SERIES = rf'{ARTICLE.pattern}{QUALIFIER}(?:\s*[、，和及]\s*{ARTICLE.pattern}{QUALIFIER})*'
CITATION = re.compile(rf'(?:《([^《》\n]+)》(?:的)?|(?P<own>本法典|本法)(?!律))\s*(?P<articles>{SERIES})')
EXAMPLE = re.compile(r'<section class="article-example" id="example">.*?</section>', re.S)
ANCHOR = re.compile(r'<a\b([^>]*?)\bhref=(["\'])(.*?)\2([^>]*?)>(.*?)</a>', re.S)


def number(value):
    if value.isdecimal():
        return int(value)
    digits = dict(zip('零一二三四五六七八九〇两', [*range(10), 0, 2]))
    if all(c in digits for c in value):
        return int(''.join(str(digits[c]) for c in value))
    total = digit = 0
    for c in value:
        if c in digits:
            digit = digits[c]
        elif c in '十百千':
            total += (digit or 1) * {'十': 10, '百': 100, '千': 1000}[c]
            digit = 0
        else:
            return None
    return total + digit


def key(match):
    first = number(match[1])
    suffix = number(match[2]) if match[2] else None
    if first and (not match[2] or suffix):
        return str(first) + (f'-{suffix}' if suffix else '')
    return None


def removed(url):
    parts = urlsplit(html.unescape(url))
    query = parse_qs(parts.query)
    if any(repealed_id in parts.path.split('/') or repealed_id in query.get('id', [])
           for repealed_id in REPEALED):
        return True
    titles = {entry[0] for entry in REPEALED.values()}
    return any(value.removeprefix('中华人民共和国') in titles
               for field in ('q', 'title') for value in query.get(field, []))


def section(groups):
    body = ''
    for heading, entries in groups.items():
        if not entries:
            continue
        body += f'<h3>{heading}</h3><ul>'
        for url, title, reason in entries:
            body += f'<li><a href="{html.escape(url)}">{html.escape(title)}</a><p>{html.escape(reason)}</p></li>'
        body += '</ul>'
    return ('<section class="panel law-related" aria-labelledby="related-laws"><h2 id="related-laws">关联法条</h2>'
            + (body or '<p>暂无已核对的站内关联法条。</p>') + '</section>')


def apply(public, report):
    def load(name):
        return json.loads((public / name).read_text(encoding='utf-8'))

    def save(name, data):
        (public / name).write_text(json.dumps(data, ensure_ascii=False, separators=(',', ':')) + '\n', encoding='utf-8')

    source = load('laws/corpus.json')
    index = load('search-index.json')
    ledger = load('other-law-example-status.json')
    corpus = [row for row in source if row['law_id'] not in REPEALED]
    manifest = []
    for law_id, (title, date, authority, url) in REPEALED.items():
        rows = [row for row in source if row['law_id'] == law_id]
        assert rows and all(row['status'] == '已废止' and row['repealed'] in ('', date) for row in rows), (law_id, rows[:1])
        directory = '/laws/' + law_id + '/'
        manifest.append(dict(law=title, version=rows[0]['version'], date=date, authority=authority, source=url,
                             routes=[directory] + [row['url'] for row in rows]))
        shutil.rmtree(public / directory.strip('/'))
    save('laws/corpus.json', corpus)
    retained = [row for row in index if not removed(row['url'])]
    save('search-index.json', retained)
    ledger['items'] = [row for row in ledger['items'] if row['law_id'] not in REPEALED]
    law_count = len({row['law_id'] for row in corpus})
    removed_articles = len(source) - len(corpus)
    ledger.update(total_laws=law_count, total_articles=len(corpus),
                  examples_complete=ledger['examples_complete'] - removed_articles)
    save('other-law-example-status.json', ledger)
    sitemap = public / 'sitemap.xml'
    data = sitemap.read_text(encoding='utf-8')
    sitemap.write_text(re.sub(r'<url>\s*<loc>([^<]+)</loc>.*?</url>',
                              lambda m: '' if removed(m[1]) else m[0], data, flags=re.S), encoding='utf-8')

    civil = [dict(row, law=CIVIL, article_label=row['title']) for row in retained if row['type'] == '民法典']
    articles = civil + [dict(row, article_label=f'《{row["law"].removeprefix("中华人民共和国")}》{row["article"]}') for row in corpus]
    live = {row['url']: row for row in articles if row['status'] == '有效' and row.get('entry_kind', 'article') == 'article'}
    titles = defaultdict(set)
    lookup = {}
    for url, row in live.items():
        law = row['law']
        titles[law].add(law)
        titles[law.removeprefix('中华人民共和国')].add(law)
        lookup[(law, url.rstrip('/').split('/')[-1])] = url
    debt = {group: [[f'/articles/{target}/' if isinstance(target, int) else target, reason]
                    for target, reason in entries] for group, entries in DEBT.items()}
    debt_targets = {url: reason for group in debt.values() for url, reason in group}
    assert debt_targets.keys() <= live.keys()
    debt_targets['/articles/510/'] = '合同约定有空缺时，查能否以补充协议、相关条款或交易习惯确定。'
    graph = {}
    explicit_count = editorial_count = 0
    for row in articles:
        origin = row['url']
        groups = {'原文引用': [], '相关阅读': []}
        seen = {origin}
        for match in CITATION.finditer(row['text']):
            if match['own']:
                target_law = row['law']
            else:
                names = titles.get(match[1], ())
                if len(names) != 1:
                    continue
                target_law = next(iter(names))
            for reference in ARTICLE.finditer(match['articles']):
                destination = lookup.get((target_law, key(reference)))
                if destination and destination not in seen:
                    seen.add(destination)
                    groups['原文引用'].append((destination, live[destination]['article_label'], '本条原文明确引用这条规定。'))
        if origin in debt_targets:
            peers = debt_targets if origin == '/articles/675/' else {'/articles/675/': debt_targets['/articles/675/']}
            for url, reason in peers.items():
                if url not in seen:
                    groups['相关阅读'].append((url, live[url]['article_label'], reason))
        explicit_count += len(groups['原文引用'])
        editorial_count += len(groups['相关阅读'])
        edges = [[url, reason] for entries in groups.values() for url, _, reason in entries]
        if edges:
            graph[origin] = edges
        page = public / origin.strip('/') / 'index.html'
        original = page.read_text(encoding='utf-8')
        updated, count = EXAMPLE.subn(lambda m: m[0] + section(groups), original)
        assert count == 1, origin
        page.write_text(updated, encoding='utf-8')
    save('law-relations.json', {'titles': {url: live[url]['article_label'] for url in
         {u for edges in graph.values() for u, _ in edges} | debt_targets.keys()}, 'graph': graph, 'debt': debt})

    for path in public.rglob('*.html'):
        original = path.read_text(encoding='utf-8')
        data = original
        if path == public / 'laws/index.html':
            data = re.sub(r'<article class="law-card"[^>]*>.*?</article>',
                          lambda m: '' if any(i in m[0] for i in REPEALED) else m[0], data, flags=re.S)
        data = ANCHOR.sub(lambda m: m[5] if removed(m[3]) else m[0], data)
        if path.relative_to(public).as_posix() in {'index.html', 'laws/index.html', 'coverage/index.html', 'examples-missing/index.html'}:
            data = data.replace('39部', f'{law_count}部').replace('>39</strong>', f'>{law_count}</strong>')
            data = data.replace('5745', str(len(corpus))).replace('5,745', f'{len(corpus):,}')
        if data != original:
            path.write_text(data, encoding='utf-8')
    catalogue = (public / 'laws/index.html').read_text(encoding='utf-8')
    assert len(re.findall(r'<article class="law-card"', catalogue)) == law_count
    search = public / 'search/index.html'
    data = search.read_text(encoding='utf-8')
    assert data.count('<div id="results" data-kind=""></div>') == 1
    data = data.replace('<div id="results" data-kind=""></div>', '<div id="results" data-kind=""></div><section id="recommendations" class="panel law-related" aria-live="polite" hidden></section>')
    data = data.replace('<script src="/app.js?', '<script src="/law-relations.js?v=20261105" defer></script><script src="/app.js?')
    search.write_text(data.replace('/app.js?v=20261024-redesign', '/app.js?v=20261105-relations'), encoding='utf-8')
    app = public / 'app.js'
    data = app.read_text(encoding='utf-8')
    anchor = " if(sort.value==='title')found.sort"
    assert data.count(anchor) == 1
    data = data.replace(anchor, " window.legalRelations?.render(q,route.key,found.slice(0,6));\n" + anchor)
    app.write_text(data.replace("const searchVersion='20261024-redesign'", "const searchVersion='20261105-relations'"), encoding='utf-8')
    shutil.copyfile(Path(__file__).with_name('law-relations.js'), public / 'law-relations.js')
    with (public / 'style.css').open('a', encoding='utf-8') as css:
        css.write('\n.law-related{margin-block:1.5rem;overflow-wrap:anywhere}.law-related h3{margin-block:1.2rem .4rem}.law-related ul{padding-inline-start:1.4rem}.law-related li{margin-block:.65rem}.law-related li p{margin:.2rem 0}.law-related a{text-decoration:underline;text-underline-offset:.18em}.law-related summary{cursor:pointer}.law-related[hidden]{display:none}\n')
    counts = dict(other_laws=law_count, other_articles=len(corpus), civil_articles=len(civil),
                  removed_search_rows=len(index)-len(retained), explicit_links=explicit_count,
                  editorial_links=editorial_count, article_pages=len(articles))
    print(json.dumps(counts, ensure_ascii=False))
    if report:
        report.write_text(json.dumps(dict(counts=counts, removed=manifest), ensure_ascii=False, indent=2)+'\n', encoding='utf-8')


if __name__ == '__main__':
    cli = argparse.ArgumentParser()
    cli.add_argument('public', type=Path)
    cli.add_argument('--report', type=Path)
    args = cli.parse_args()
    apply(args.public, args.report)
