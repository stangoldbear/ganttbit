/* ============================================================================
   GanttBit — service worker.

   What it is for, and what it is deliberately not for.

   The vault is a directory on a machine. When that machine is unreachable the
   data is unreachable, and a cached chart that silently refuses to save is
   worse than a page that says so. So:

     /static/  cache first, revalidated in the background — the shell
     /api/     never cached, never intercepted — the data is the file on disk
     a page    network first, with a plain "not connected" page as the fallback

   Which leaves the honest benefit: a home screen icon, a standalone window,
   and a shell that paints instantly.
   ========================================================================== */
'use strict';

var CACHE = 'ganttbit-shell-v1';
var SHELL = [
  '/static/app.css',
  '/static/themes.css',
  '/static/app.js',
  '/static/theme.js',
  '/static/logo.svg',
  '/static/icon.svg',
  '/static/icon-192.png',
  '/static/icon-512.png'
];

self.addEventListener('install', function (event) {
  event.waitUntil(
    caches.open(CACHE)
      .then(function (cache) { return cache.addAll(SHELL); })
      .then(function () { return self.skipWaiting(); })
  );
});

self.addEventListener('activate', function (event) {
  event.waitUntil(
    caches.keys().then(function (keys) {
      return Promise.all(keys.map(function (key) {
        return key === CACHE ? null : caches.delete(key);
      }));
    }).then(function () { return self.clients.claim(); })
  );
});

var OFFLINE = '<!DOCTYPE html><meta charset="utf-8">' +
  '<meta name="viewport" content="width=device-width,initial-scale=1">' +
  '<title>Not connected</title>' +
  '<style>body{font:15px system-ui;margin:0;display:flex;min-height:100vh;' +
  'align-items:center;justify-content:center;background:#0f172a;color:#e2e8f0}' +
  'div{max-width:32ch;padding:24px;text-align:center}p{color:#94a3b8;font-size:13px}' +
  'button{margin-top:16px;padding:8px 14px;border:0;border-radius:6px;' +
  'background:#e2e8f0;color:#0f172a;font:inherit;font-size:13px}</style>' +
  '<div><h1>Not connected</h1><p>The vault lives on your machine, and this app ' +
  'cannot reach it right now. Nothing has been lost — it is all still in the ' +
  'files.</p><button onclick="location.reload()">Try again</button></div>';

self.addEventListener('fetch', function (event) {
  var request = event.request;
  if (request.method !== 'GET') return;

  var url = new URL(request.url);
  if (url.origin !== self.location.origin) return;
  if (url.pathname.indexOf('/api/') === 0) return;      // the data is never cached

  if (url.pathname.indexOf('/static/') === 0) {
    event.respondWith(
      caches.match(request).then(function (hit) {
        var fresh = fetch(request).then(function (response) {
          if (response && response.ok) {
            var copy = response.clone();
            caches.open(CACHE).then(function (cache) { cache.put(request, copy); });
          }
          return response;
        }).catch(function () { return hit; });
        return hit || fresh;
      })
    );
    return;
  }

  if (request.mode === 'navigate') {
    event.respondWith(
      fetch(request).catch(function () {
        return new Response(OFFLINE, { headers: { 'Content-Type': 'text/html; charset=utf-8' } });
      })
    );
  }
});
