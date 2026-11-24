// Redirect the public production *.pages.dev alias to the canonical domain.
//
// Why: Cloudflare Pages exposes the build at incremento-site.pages.dev as well
// as at incremento.eu. Google indexed the pages.dev copy (it is crawlable and
// its canonical tag is only a hint), so search was surfacing a throwaway URL
// instead of the real domain. A 301 on the whole host hands that equity to
// incremento.eu and removes the duplicate from the index.
//
// Scope: matches ONLY the exact production alias. Branch-preview hosts
// (<hash>.incremento-site.pages.dev) are left alone so previews stay usable,
// and the custom domain never matches, so live traffic passes straight through.
export async function onRequest(context) {
  const { request, next } = context;
  const url = new URL(request.url);

  if (url.hostname === "incremento-site.pages.dev") {
    url.hostname = "incremento.eu";
    url.protocol = "https:";
    url.port = "";
    return Response.redirect(url.toString(), 301);
  }

  return next();
}
