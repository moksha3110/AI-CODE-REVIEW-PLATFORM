// Every backend call in this app goes straight from the browser to the
// owning microservice (no Next.js API-route proxy layer) - each service
// already exposes CORS + a JWT-protected REST API of its own, so a BFF
// layer here would just be an extra hop with nothing to add. See the
// README for the trade-off this implies for the access token.

export const AUTH_SERVICE_URL =
  process.env.NEXT_PUBLIC_AUTH_SERVICE_URL ?? "http://localhost:8000";
export const REPOSITORY_SERVICE_URL =
  process.env.NEXT_PUBLIC_REPOSITORY_SERVICE_URL ?? "http://localhost:8001";
export const REVIEW_SERVICE_URL =
  process.env.NEXT_PUBLIC_REVIEW_SERVICE_URL ?? "http://localhost:8003";
export const NOTIFICATION_SERVICE_URL =
  process.env.NEXT_PUBLIC_NOTIFICATION_SERVICE_URL ?? "http://localhost:8004";
