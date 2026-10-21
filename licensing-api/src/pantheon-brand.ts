/** Presentation only. Called exclusively after Pantheon login/register routing. */
export function pantheonAuthBrand(response: Response): Response {
  const version = '20261021-unified-2';
  return new HTMLRewriter()
    .on('html', { element(element) { element.setAttribute('data-pantheon-brand', ''); } })
    .on('head', { element(element) {
      element.prepend(`<script src="/pantheon/theme.js?v=${version}"></script><link rel="stylesheet" href="/pantheon/design.css?v=${version}"><link rel="preload" as="font" type="font/ttf" href="/pantheon/chivo-variable.ttf" crossorigin>`, {html:true});
      element.append(`<link rel="stylesheet" href="/pantheon/auth.css?v=${version}"><script src="/pantheon/auth.js?v=${version}" defer></script>`, {html:true});
    } })
    .on('link[rel="icon"]', { element(element) { element.setAttribute('href', '/pantheon/temple.svg'); element.setAttribute('type','image/svg+xml'); } })
    .transform(response);
}
