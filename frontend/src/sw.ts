/// <reference lib="webworker" />
/**
 * Service worker: the app shell opens offline and last-viewed data stays readable (GET API
 * responses are cached, network first). Writes are never queued: saving needs a connection and
 * the app says so (PRD section 10). Push shows the daily summary (counts only).
 */
import { precacheAndRoute, createHandlerBoundToURL } from "workbox-precaching";
import { NavigationRoute, registerRoute } from "workbox-routing";
import { NetworkFirst } from "workbox-strategies";

declare const self: ServiceWorkerGlobalScope & { __WB_MANIFEST: { url: string; revision: string | null }[] };

precacheAndRoute(self.__WB_MANIFEST);
registerRoute(new NavigationRoute(createHandlerBoundToURL("/index.html"), { denylist: [/^\/api\//] }));

const SAFE_TO_CACHE = /^\/api\/v1\/(daybook|dues|dashboard|borrowers|loans|settings|categories|auth\/me)/;
registerRoute(
  ({ url, request }) => request.method === "GET" && SAFE_TO_CACHE.test(url.pathname) && !url.pathname.endsWith(".pdf"),
  new NetworkFirst({ cacheName: "api-reads", networkTimeoutSeconds: 6 }),
);

self.addEventListener("message", (event) => {
  if (event.data?.type === "SKIP_WAITING") void self.skipWaiting();
});

self.addEventListener("push", (event) => {
  const data = event.data?.json() ?? { title: "Loan Tracker", body: "" };
  event.waitUntil(self.registration.showNotification(data.title, { body: data.body, icon: "/icon-192.png",
    badge: "/icon-192.png", data: { url: data.url ?? "/" } }));
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  event.waitUntil(self.clients.openWindow(event.notification.data?.url ?? "/"));
});
