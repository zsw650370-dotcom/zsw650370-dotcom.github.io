(() => {
  const host = document.getElementById('recommendations');
  if (!host) return;
  let dataPromise;
  let generation = 0;
  const element = (tag, text) => {
    const node = document.createElement(tag);
    if (text) node.textContent = text;
    return node;
  };
  const appendGroup = (parent, name, entries, titles) => {
    if (!entries.length) return;
    parent.append(element('h3', name));
    const list = element('ul');
    for (const [url, reason] of entries) {
      const item = element('li');
      const link = element('a', titles[url]);
      link.href = url;
      item.append(link, element('p', reason));
      list.append(item);
    }
    parent.append(list);
  };
  window.legalRelations = {
    async render(query, alias, matches) {
      const request = ++generation;
      host.hidden = true;
      if (!query || !matches.length) return;
      dataPromise ??= fetch('/law-relations.json?v=20261105').then(response => {
        if (!response.ok) throw Error('Related provisions unavailable');
        return response.json();
      });
      try {
        const data = await dataPromise;
        if (request !== generation) return;
        const debt = matches.some(row => row.url === '/articles/675/') ||
          (/欠钱不还|借钱不还/.test(alias || query) && matches.some(row => row.type === '民法典'));
        const seen = new Set();
        const unique = entries => entries.filter(([url]) => {
          if (seen.has(url) || !data.titles[url]) return false;
          seen.add(url);
          return true;
        });
        const heading = element('h2', '相关条款推荐');
        const more = element('details');
        more.append(element('summary', '展开更多'));
        const fragment = document.createDocumentFragment();
        fragment.append(heading);
        if (debt) {
          for (const [name, entries] of Object.entries(data.debt)) {
            appendGroup(name === '直接相关' ? fragment : more, name, unique(entries), data.titles);
          }
        } else {
          const related = unique(matches.flatMap(row => data.graph[row.url] || []));
          appendGroup(fragment, '与匹配法条相关', related.slice(0, 3), data.titles);
          appendGroup(more, '其他相关条款', related.slice(3, 15), data.titles);
        }
        if (!seen.size) return;
        if (more.children.length > 1) fragment.append(more);
        host.replaceChildren(fragment);
        host.hidden = false;
      } catch {
        if (request === generation) host.hidden = true;
        dataPromise = undefined;
      }
    }
  };
})();
