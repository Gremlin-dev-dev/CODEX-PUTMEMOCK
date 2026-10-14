// Minimal service worker — just enough to satisfy PWA install requirements.
// It doesn't do offline caching of exam data (correct, since questions and
// results must always come fresh from the server), but it lets the browser
// treat this as an installable app.

self.addEventListener('install', (event) => {
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  self.clients.claim();
});

// Pass every request straight through to the network — no offline caching.
// This keeps things simple and correct: exam questions, login state, and
// results must always be current, never served stale from a cache.
self.addEventListener('fetch', (event) => {
  event.respondWith(fetch(event.request));
});
