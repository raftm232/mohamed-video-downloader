const CACHE='mr-downloader-shell-v1';
self.addEventListener('install',event=>event.waitUntil(caches.open(CACHE).then(cache=>cache.addAll(['/','/manifest.webmanifest']))));
self.addEventListener('activate',event=>event.waitUntil(self.clients.claim()));
self.addEventListener('fetch',event=>{
  const u=new URL(event.request.url);
  if(event.request.method!=='GET'||u.pathname.startsWith('/api/')) return;
  event.respondWith(fetch(event.request).then(response=>{
    const copy=response.clone(); caches.open(CACHE).then(cache=>cache.put(event.request,copy)); return response;
  }).catch(()=>caches.match(event.request)));
});
