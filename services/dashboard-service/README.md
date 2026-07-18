# Dashboard Service

The platform's frontend - a Next.js app that lets a user connect a GitHub
repository, watch every push get reviewed by Claude, and browse the
resulting bugs, security issues, optimizations, and quality trends. It's
the only piece of the platform that runs in the browser rather than as a
backend service, and it talks to Auth Service, Repository Service, Review
Service, and Notification Service directly - no BFF or proxy layer in
between.

## Why no BFF

Every backend service already verifies JWTs locally and has its own CORS
config scoped to this app's origin, so a proxy hop here would add latency
without adding security. The trade-off is that this app owns cross-origin
auth end-to-end: the access token lives only in React state (never
`localStorage`), and the httpOnly refresh cookie only auth-service can
read is what survives a page reload.

## What's implemented

- **Auth**: GitHub OAuth login via Auth Service, in-memory access token,
  silent httpOnly-cookie-backed refresh on mount, automatic 401-retry-once
  on every authenticated fetch.
- **Repositories**: list connected repos, connect a new one via the
  GitHub App install flow, land back here after GitHub redirects.
- **Repository detail**: paginated review history plus a quality-trends
  chart (complexity score and issue counts over time), both from Review
  Service.
- **Review detail**: per-file summary, complexity score, bugs and security
  issues (with severity and line numbers), optimizations, and
  documentation suggestions.
- **Notifications bell**: unread badge, dropdown list from Notification
  Service, mark-read on click.

## Running locally

```bash
cp .env.local.example .env.local
npm install
npm run dev
```

Requires Auth Service (8000), Repository Service (8001), Review Service
(8003), and Notification Service (8004) running - see the root
`docker-compose.yml`. Without real GitHub OAuth/App credentials, the
fastest way to exercise the UI is to seed rows directly into each
service's database and mint a JWT with Auth Service's own signing key
(see `HANDOFF.md` at the repo root for the exact scripts used to do this).

## Known gaps / honest trade-offs

- **A hard page reload loses the session** if the httpOnly refresh cookie
  isn't valid (e.g. no real GitHub OAuth login happened) - this is the
  documented cost of keeping the access token out of any storage API an
  XSS payload could read. Client-side navigation (clicking a link)
  preserves the in-memory token fine; only a full navigation/reload
  depends on the refresh cookie.
- **No server-side route protection.** Since the access token is never in
  a cookie the server can read, all of `/repositories`, `/repositories/*`,
  and `/reviews/*` are gated client-side (`components/protected.tsx`)
  after the initial silent-refresh attempt resolves, not by Next.js
  middleware/proxy.
- **No repository-ownership check on the client.** The dashboard only ever
  navigates to repository/review ids it already fetched for the signed-in
  user, but it doesn't independently re-verify ownership - that
  enforcement lives in Repository Service's `GET /repositories` (see that
  service's README).
- **Zero automated tests.** Every page and flow here was verified manually
  through the browser against seeded data, not covered by a test suite -
  a real gap for a project otherwise built around genuinely running its
  backend tests, not just writing them.
- **shadcn's dropdown-menu primitive needs `DropdownMenuGroup` around
  `DropdownMenuLabel`.** This project's shadcn install uses base-ui (not
  Radix); base-ui's `Menu.GroupLabel` throws if it isn't inside a
  `Menu.Group` ancestor. `components/notifications-bell.tsx` and
  `components/user-menu.tsx` both wrap their label in
  `DropdownMenuGroup` for this reason - if you add a new dropdown menu
  with a label, do the same or it will crash on open.
