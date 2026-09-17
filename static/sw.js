// Service worker: caches the app shell and, additionally, keeps a
// last-known-good copy of every page the person actually visits — so if
// the connection drops, previously-opened pages (the ticket form, the
// login screen, an already-viewed ticket status page, etc.) still open
// instead of erroring out. IMPORTANT: this is NOT full offline usage —
// the backend is a live database (Flask + SQL), so submitting a new
// ticket, logging in, or seeing up-to-date lists still needs a real
// connection. What this buys is a usable app shell while offline
// (reading what was last loaded), not offline data entry.

const SHELL_CACHE = 'raed-tickets-shell-v2';
const PAGE_CACHE = 'raed-tickets-pages-v2';
const CURRENT_CACHES = [SHELL_CACHE, PAGE_CACHE];

const SHELL_ASSETS = [
  '/static/offline.html',
  '/static/logo.png',
  '/static/icon-192.png',
  '/static/icon-512.png',
  '/static/apple-touch-icon.png',
  '/static/manifest.json',
];

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(SHELL_CACHE).then((cache) => cache.addAll(SHELL_ASSETS)).catch(() => {})
  );
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((names) =>
      Promise.all(names.filter((n) => !CURRENT_CACHES.includes(n)).map((n) => caches.delete(n)))
    )
  );
  self.clients.claim();
});

self.addEventListener('fetch', (event) => {
  const req = event.request;

  // Page navigations: network-first (so anyone online always sees fresh
  // data), keeping a copy of every successful page for offline re-use;
  // fall back to that cached copy — and only then to offline.html — when
  // the network is unreachable.
  if (req.mode === 'navigate') {
    if (req.method !== 'GET') {
      // Don't intercept form submissions (e.g. the login POST). Some
      // browsers (notably Edge) fail to safely re-dispatch a
      // service-worker-intercepted POST request's body, which made
      // fetch() reject even though the network was fine — incorrectly
      // showing the offline page instead of actually logging in.
      return;
    }
    event.respondWith(
      fetch(req)
        .then((res) => {
          const copy = res.clone();
          caches.open(PAGE_CACHE).then((cache) => cache.put(req, copy)).catch(() => {});
          return res;
        })
        .catch(() =>
          caches.match(req).then((cached) => cached || caches.match('/static/offline.html'))
        )
    );
    return;
  }

  // For same-origin static shell assets, try cache first, then network.
  const url = new URL(req.url);
  if (url.origin === self.location.origin && SHELL_ASSETS.some((a) => url.pathname === a)) {
    event.respondWith(
      caches.match(req).then((cached) => cached || fetch(req))
    );
  }
  // Everything else (API calls, admin data, etc.) goes straight to the
  // network as normal — intentionally not intercepted, since that data
  // must always be live.
});

// ── Real Web Push — arrives even when the app/browser is fully closed ──
self.addEventListener('push', (event) => {
  let data = { title: 'إشعار جديد', body: '', url: '/admin/' };
  try {
    if (event.data) data = Object.assign(data, event.data.json());
  } catch (e) {}

  event.waitUntil((async () => {
    await self.registration.showNotification(data.title, {
      body: data.body,
      icon: '/static/icon-192.png',
      badge: '/static/icon-192.png',
      data: { url: data.url || '/admin/' },
      dir: 'rtl',
      lang: 'ar',
    });

    // Wake any open admin page IMMEDIATELY (no waiting for its next poll)
    // so the print station can react the instant a booking is approved —
    // this is what makes it feel like a live receipt printer instead of
    // something that catches up every few seconds.
    if (data.type === 'booking-approved') {
      const clients = await self.clients.matchAll({ type: 'window', includeUncontrolled: true });
      clients.forEach((client) => client.postMessage({ type: 'booking-approved' }));
    }
  })());
});

self.addEventListener('notificationclick', (event) => {
  event.notification.close();
  const url = (event.notification.data && event.notification.data.url) || '/admin/';
  event.waitUntil(
    clients.matchAll({ type: 'window', includeUncontrolled: true }).then((windowClients) => {
      for (const client of windowClients) {
        if (client.url.includes('/admin') && 'focus' in client) {
          client.navigate(url);
          return client.focus();
        }
      }
      if (clients.openWindow) return clients.openWindow(url);
    })
  );
});
