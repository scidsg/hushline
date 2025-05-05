self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open('hushline-cache').then((cache) => {
      return cache.addAll([
        '/',
        '/static/css/style.css',
        '/static/favicon/android-chrome-192x192.png',
        '/static/favicon/android-chrome-512x512.png'
      ]);
    })
  );
});

self.addEventListener('fetch', (event) => {
  event.respondWith(
    caches.match(event.request).then((response) => {
      return response || fetch(event.request);
    })
  );
});
