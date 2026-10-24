// Service worker do Prospector: abre offline e sempre tenta buscar os leads mais novos.
const VERSAO = "prospector-v1";
const BASICOS = ["./", "index.html", "manifest.webmanifest",
  "icones/icone-192.png", "icones/icone-512.png", "icones/apple-touch-icon.png"];

self.addEventListener("install", e => {
  e.waitUntil(caches.open(VERSAO).then(c => c.addAll(BASICOS)).then(() => self.skipWaiting()));
});

self.addEventListener("activate", e => {
  e.waitUntil(
    caches.keys()
      .then(chaves => Promise.all(chaves.filter(k => k !== VERSAO).map(k => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", e => {
  const url = new URL(e.request.url);
  if (e.request.method !== "GET" || url.origin !== location.origin) return;

  // Leads e a própria página: rede primeiro, cache se estiver offline.
  if (url.pathname.endsWith("/leads.json") || e.request.mode === "navigate") {
    const chave = url.pathname.endsWith("/leads.json") ? "leads.json" : "index.html";
    e.respondWith(
      fetch(e.request)
        .then(r => {
          if (r.ok) { const copia = r.clone(); caches.open(VERSAO).then(c => c.put(chave, copia)); }
          return r;
        })
        .catch(() => caches.match(chave))
    );
    return;
  }

  // Demais arquivos (ícones, manifesto): cache primeiro.
  e.respondWith(caches.match(e.request).then(r => r || fetch(e.request)));
});
