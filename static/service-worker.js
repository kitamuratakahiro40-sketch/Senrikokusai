// PWAシェルキャッシュ。HTML(index)は「ネット優先」で常に最新を取りに行く（更新が即反映される）。
// その他のアセットは「キャッシュ優先」。AI呼び出し(/api)はキャッシュせず素通し。
const CACHE = "henyu-v4";
const SHELL = ["/", "/index.html", "/manifest.webmanifest", "/icon-192.png", "/icon-512.png", "/icon-apple-180.png"];
self.addEventListener("install", (e) => {
  e.waitUntil(caches.open(CACHE).then((c) => c.addAll(SHELL)).then(() => self.skipWaiting()));
});
self.addEventListener("activate", (e) => {
  e.waitUntil(caches.keys().then((ks) => Promise.all(ks.filter((k) => k !== CACHE).map((k) => caches.delete(k)))).then(() => self.clients.claim()));
});
self.addEventListener("fetch", (e) => {
  const req = e.request;
  const url = new URL(req.url);
  if (req.method !== "GET" || url.pathname.startsWith("/api/")) return; // APIは素通し

  // 画面本体(HTML)はネット優先。最新を取得し、取れたらキャッシュも更新。オフライン時だけキャッシュを使う。
  const isHTML = req.mode === "navigate" || url.pathname === "/" || url.pathname.endsWith("/index.html");
  if (isHTML) {
    e.respondWith(
      fetch(req).then((res) => {
        const copy = res.clone();
        caches.open(CACHE).then((c) => c.put("/index.html", copy)).catch(() => {});
        return res;
      }).catch(() => caches.match(req).then((h) => h || caches.match("/index.html")))
    );
    return;
  }

  // その他のアセットはキャッシュ優先。
  e.respondWith(
    caches.match(req).then((hit) => hit || fetch(req).then((res) => {
      const copy = res.clone();
      caches.open(CACHE).then((c) => c.put(req, copy)).catch(() => {});
      return res;
    }).catch(() => caches.match("/index.html")))
  );
});
