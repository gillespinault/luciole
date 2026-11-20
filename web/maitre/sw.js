/* Cache de la page du maître, pour qu'elle s'ouvre sans réseau : le réseau
 * d'abord (la dernière version quand il y en a), le cache sinon.
 * Les caches sont communs à tout le site : celui-ci ne nettoie que les siens
 * (préfixe luciole-maitre-), pas ceux de la page de mise au point. */
const PREFIXE = 'luciole-maitre-', CACHE = PREFIXE + 'v1';
const FILES = ['./', './index.html', './manifest.webmanifest', './icon.svg'];
self.addEventListener('install', e => e.waitUntil(caches.open(CACHE).then(c => c.addAll(FILES)).then(() => self.skipWaiting())));
self.addEventListener('activate', e => e.waitUntil(caches.keys().then(ks => Promise.all(ks.filter(k => k.startsWith(PREFIXE) && k !== CACHE).map(k => caches.delete(k)))).then(() => self.clients.claim())));
self.addEventListener('fetch', e => {
  if (e.request.method !== 'GET') return;
  e.respondWith(fetch(e.request).then(r => { const copy = r.clone(); caches.open(CACHE).then(c => c.put(e.request, copy)); return r; }).catch(() => caches.match(e.request)));
});
