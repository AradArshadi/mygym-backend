# myGym API & Swagger Control Layer

This build adds a documented API surface for internal testing, debugging, and future mobile/API work.

## Main URLs

- Swagger UI: `/api/docs/`
- ReDoc: `/api/redoc/`
- OpenAPI schema: `/api/schema/`

The documentation pages are protected with Django staff access. In production/demo environments, open Swagger after logging in with a staff/admin account.

## Swagger authentication

For `POST`, `DELETE`, and other API actions, use Swagger's **Authorize** button and authenticate with an admin/staff account using Basic Auth. This avoids CSRF problems when using Swagger's “Try it out” actions.

## Endpoint groups

### Demo Tools

- `GET /api/demo/status/`
- `POST /api/demo/seed-analytics/`
- `POST /api/demo/reset-analytics/`

These endpoints require staff/admin access and `DEMO_TOOLS_ENABLED=True`.

Example seed request:

```json
{
  "days": 180,
  "customers": 80,
  "reset_demo": true,
  "dry_run": false,
  "subscriptions_per_gym": 55,
  "bookings_per_gym": 100,
  "checkins_per_gym": 650,
  "favorites_per_gym": 28,
  "workouts_per_customer": 25,
  "seed": 9309
}
```

### Owner Analytics

- `GET /api/owner/analytics/?days=30`
- `GET /api/owner/gyms/<gym_id>/analytics/?days=30`

Returns portfolio and per-gym analytics based on bookings, subscriptions, favorites, views, and QR check-ins.

### Gyms and Favorites

- `GET /api/gyms/?page=1&page_size=20`
- `GET /api/gyms/<slug>/`
- `POST /api/gyms/<slug>/favorite/`
- `DELETE /api/gyms/<slug>/favorite/`

### Fitness

- `GET /api/fitness/summary/?activity_days=30`
- `GET /api/fitness/activity/?days=30`
- `GET /api/fitness/workouts/`
- `POST /api/fitness/workouts/`

### Security and Email Diagnostics

- `GET /api/security/status/`
- `GET /api/email/config/`
- `POST /api/email/probe/`

These endpoints are sanitized. They never return the SMTP password or secret keys.

## Production safety rules

- Keep `DEMO_TOOLS_ENABLED=False` for real production.
- Keep `/api/docs/` staff-only.
- Never expose secrets through API responses.
- Use Swagger demo tools only for test/demo servers.
- Keep terminal management commands available for backups and emergency recovery.
