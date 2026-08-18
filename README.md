
## v3 additions

- Gym detail pages now include a Photos section, Reviews section, plans, trainers, and booking form.
- Customers can submit one review per gym.
- Owners receive in-app notifications for bookings and reviews.
- Customers receive in-app notification after sending a booking request.
- Owner dashboard shows customer names, emails, requested booking time, status, and notes per gym.
- New notifications module: `/notifications/`.

After updating, run:

```bash
python manage.py makemigrations notifications reviews bookings gyms dashboard analytics accounts
python manage.py migrate
python manage.py runserver
```

## v0.8 UI/UX Bootstrap Refresh

- Added Bootstrap 5 CDN integration.
- Redesigned navbar, landing/explore page, gym cards, table view, map container, gym detail page, customer dashboard, owner dashboard, and auth pages.
- Kept backend logic unchanged; no migration required for this UI-only upgrade.

Run:

```bash
python manage.py check
python manage.py runserver
```


---

Powered by Arad Arshadi  
GitHub: https://github.com/AradArshadi

## v0.9 Control Deck

The project now includes a custom admin/operator dashboard at `/control/`.

Access is limited to superusers, staff users, or users with role `ADMIN`.

Control Deck features:
- Platform overview metrics
- User management and role changes
- Gym approval/rejection workflow
- Booking status controls
- Review moderation
- Links back to Django Admin for low-level database administration

Django Admin remains available at `/admin/` as the technical back office.

## v0.9.1 Email System

This version adds a centralized email service layer under `apps/emails/`.

Email events currently supported:
- Customer/owner/trainer welcome email after registration
- Booking request email to gym owner / gym contact email
- Booking status email to customer when accepted, rejected, cancelled, or updated by Control Deck
- Gym approval/rejection email to owner
- New review email to gym owner

### Local development

By default emails are printed to the terminal:

```env
EMAIL_BACKEND=django.core.mail.backends.console.EmailBackend
```

### SMTP deployment

For SMTP, set:

```env
EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
EMAIL_HOST=smtp.gmail.com
EMAIL_PORT=587
EMAIL_USE_TLS=True
EMAIL_HOST_USER=your-email@example.com
EMAIL_HOST_PASSWORD=your-app-password
DEFAULT_FROM_EMAIL=myGym <your-email@example.com>
SITE_URL=https://yourusername.pythonanywhere.com
```

### Test email

```bash
python manage.py test_email your-email@example.com
```

No database migration is required for v0.9.1.

## v0.9.2 Logging & Observability

This version adds a production debugging layer so silent failures are easier to detect.

Added:
- `apps/systemlogs` app
- `SystemLog` database model
- `/control/logs/` Control Deck page
- File logs in `logs/mygym.log` and `logs/emails.log`
- Email diagnostics for every send attempt, success, skip, and failure
- Request/error logging middleware
- `show_email_config` command for sanitized email configuration checks

After updating, run:

```bash
python manage.py migrate
python manage.py check
python manage.py show_email_config
python manage.py test_email your-email@example.com
```

Important deployment notes:
- The `logs/` directory is intentionally ignored by Git.
- Email credentials must stay inside `.env` and must never be committed.
- Use `/control/logs/` to inspect email failures and admin/business events.

Useful commands:

```bash
tail -n 80 logs/emails.log
tail -n 80 logs/mygym.log
```

## v0.9.2.2 — Real Gym Import Pipeline

This version replaces fake seed data with a safer import workflow for real public data.

### What changed

- Added `ImportBatch` model to group imported data.
- Added import tracking fields on `Gym`:
  - `is_imported`
  - `is_claimed`
  - `source`
  - `external_id`
  - `import_batch`
  - `imported_at`
- Added OpenStreetMap/Overpass import command.
- Added safe wipe commands so imported data can be removed without touching owner-created gyms.

### Run migrations

```bash
python manage.py makemigrations gyms
python manage.py migrate
```

### Import gyms from OpenStreetMap

```bash
python manage.py import_gyms_osm --city "Tabriz" --country "Iran"
```

Import as approved immediately:

```bash
python manage.py import_gyms_osm --city "Tabriz" --country "Iran" --approve
```

Dry run:

```bash
python manage.py import_gyms_osm --city "Tabriz" --country "Iran" --dry-run
```

Limit records:

```bash
python manage.py import_gyms_osm --city "Tabriz" --country "Iran" --limit 25
```

### List import batches

```bash
python manage.py list_import_batches
```

### Wipe one import batch

```bash
python manage.py wipe_import_batch 1
```

If some imported gyms have bookings/reviews/favorites, they are protected by default. To delete them anyway:

```bash
python manage.py wipe_import_batch 1 --force
```

### Wipe imported gyms by city

```bash
python manage.py wipe_imported_gyms --city "Tabriz"
```

This never deletes owner-created gyms or claimed gyms.

## v0.9.2.4 security/import hotfix notes

### Emergency rollback for accidentally approved imports

If a Geoapify batch was imported as approved, move it back to review/pending:

```bash
python manage.py mark_import_batch_pending 3
```

### Safer Geoapify importing

`--approve` is now ignored unless it is deliberately combined with `--allow-auto-approve`.
Default imported gyms stay `PENDING` for Control Deck review.

```bash
python manage.py import_gyms_geoapify --city "Tabriz" --country "Iran" --radius-km 25 --limit 100
```

Unsafe demo-only auto approval:

```bash
python manage.py import_gyms_geoapify --city "Tabriz" --country "Iran" --radius-km 25 --approve --allow-auto-approve
```

### Public signup role security

The public register page now only allows:

- Customer
- Gym Owner

Admin accounts cannot be created from public signup. Admin promotion is handled from the Control Deck, and promotion to `ADMIN` is restricted to Django superusers.

### Test data reset trigger

Delete imported, unclaimed test gyms safely:

```bash
python manage.py wipe_test_data --source geoapify --city Tabriz --yes --delete-empty-batches
```

Full demo/test cleanup, still protecting superusers and claimed gyms:

```bash
python manage.py wipe_test_data --yes --include-demo-users --delete-empty-batches
```

### Gym photos

Owner-uploaded gym photos are already supported through gym management. Geoapify Places does not reliably provide gym photos, so imported gyms still use the current placeholder unless photos are uploaded later by an owner/admin.

## v0.9.2.9 — Sessions + Digital Access Pass

This version adds the first operational access layer to myGym.

### What changed

- Added `Session` model for confirmed one-time visits.
- Added `GymSubscription` model for active gym memberships / Access Passes.
- Added `GymCheckIn` model for attendance history.
- Owner confirmation now creates a one-time `Session` automatically.
- If the accepted booking includes a non-trial membership plan, the system also creates an active `GymSubscription`.
- One-time session QR codes are generated for confirmed sessions and become invalid after check-in.
- Membership Access Pass QR codes are valid while the subscription is active and refresh every 24 hours when the user logs in or opens the dashboard/access pass page.
- Customers now have:
  - My Sessions page
  - My Access Passes page
  - QR display for upcoming sessions
  - QR display for active memberships
  - cancel upcoming session action
- Owners now have:
  - today's sessions
  - today's check-ins
  - active member count
  - QR validation/confirmation pages
- Added branded email templates, including QR emails for confirmed sessions and membership Access Passes.

### QR rules

One-time session QR:

```text
Confirmed booking -> Session -> QR -> owner scans -> check-in -> QR becomes used
```

Membership Access Pass QR:

```text
Active subscription -> Access Pass QR -> owner scans -> attendance recorded
```

The membership QR is not consumed after one scan. It remains valid until:

- 24 hours pass,
- the customer opens the account and receives a refreshed QR,
- the subscription expires,
- or the subscription is cancelled.

### Install / update commands

```bash
pip install -r requirements.txt
python manage.py migrate
python manage.py check
python manage.py runserver
```

### Demo flow

1. Customer opens a gym detail page.
2. Customer selects one-time/trial or a membership plan.
3. Customer sends a booking request.
4. Owner accepts the booking from the owner dashboard.
5. The system creates a `Session`.
6. If a paid/non-trial plan was selected, the system also creates a `GymSubscription`.
7. Customer opens `My Sessions` or `My Access Passes`.
8. Owner scans the QR URL with a phone.
9. Owner confirms entry.
10. The system records a `GymCheckIn`.

### Strategy note

This feature moves myGym from a simple discovery/booking platform toward gym operating infrastructure:

- access management
- attendance tracking
- member history
- check-in analytics
- future retention insights

This directly supports the larger strategic vision of myGym as a sports and wellness operating system rather than only a gym directory.

## v0.9.2.10 — Infrastructure hardening hotfix

This patch intentionally keeps the existing UI/templates/static styling unchanged and focuses on backend reliability.

### Fixed

- Control Deck booking confirmation now uses the same operational creation flow as owner confirmation.
  - Confirmed bookings create a `Session`.
  - Confirmed bookings with a non-trial plan create/reactivate a `GymSubscription` Access Pass.
  - QR emails are sent from both owner and Control Deck confirmation flows.
- Booking datetime input from HTML `datetime-local` is normalized into the active Django timezone (`Europe/Berlin`) before saving.
- Owner dashboard is now role-protected. Customers are redirected back to the customer dashboard instead of seeing an irrelevant empty owner view.
- Notification failures are logged through `SystemLog` instead of being silently swallowed.
- SystemLog categories now include `NOTIFICATION`, `SESSION`, `SUBSCRIPTION`, and `CHECKIN`.
- `.env.example` now has one clean email/config section instead of repeated SMTP blocks.
- Production settings are hardened behind `ENVIRONMENT=production`:
  - production requires a real `SECRET_KEY`,
  - production requires real `ALLOWED_HOSTS` when `DEBUG=False`,
  - HTTPS/security cookie/HSTS settings can be controlled from env.
- Added deployment assets:
  - `Dockerfile`
  - `docker-entrypoint.sh`
  - `Procfile`
  - `.dockerignore`
  - `HEALTHCHECK.md`
- Added tests for:
  - owner booking confirmation,
  - Control Deck/admin booking confirmation,
  - one-time QR check-in,
  - membership expiry refresh,
  - owner-dashboard permission behavior,
  - timezone-aware booking datetime handling.

### SMTP diagnostics

Use the existing sanitized config command first:

```bash
python manage.py show_email_config
```

Then run the deeper delivery probe:

```bash
python manage.py email_probe your-email@example.com --template
```

For real SMTP delivery, `.env` must use:

```env
EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
EMAIL_HOST=smtp.gmail.com
EMAIL_PORT=587
EMAIL_USE_TLS=True
EMAIL_USE_SSL=False
EMAIL_HOST_USER=your-email@gmail.com
EMAIL_HOST_PASSWORD=your-app-password
DEFAULT_FROM_EMAIL=myGym <your-email@gmail.com>
SITE_URL=https://your-domain.example
```

If Gmail is used, `EMAIL_HOST_PASSWORD` must be a Gmail app password, not the normal account password.

### After updating

```bash
pip install -r requirements.txt
python manage.py migrate
python manage.py check
python manage.py test apps.bookings
python manage.py show_email_config
python manage.py email_probe your-email@example.com --template
```

## v0.9.3.0 — Fitness Home, Owner Operations & Stability Build

This build consolidates the work after the previous public `v0.9.2.7` release into one clean `0.9.3.0` milestone candidate. It is still intended for testing and demo validation before an official tag is created.

### Product direction

myGym is evolving from a gym listing app into a fitness marketplace and operating system:

- Customer Fitness Home
- Gym discovery and favorites
- Booking requests, sessions, and QR access passes
- Workout logging and weekly consistency tracking
- Owner command center with bookings, members, check-ins, and analytics
- Gym Control Center for plans, trainers, photos, and profile edits
- Control Deck safety/demo tools for admin testing

### Main features in this build

- `apps.fitness` app with Fitness Home, workout logs, weekly goals, activity map, profile hub, and edit-account flow
- Mobile-first navigation with clearer labels: Home / Explore / + / MyGym / More
- GitHub-style interactive workout activity map with 30 / 90 / 120 / 360 day ranges
- Favorite gym support on gym cards and gym detail pages
- Owner dashboard with merged analytics, collapsible sections, and direct manage/edit actions
- Per-gym analytics embedded into the owner dashboard: QR peak times, growth, estimated income, conversion, favorites, and traffic
- Gym Control Center UX for plans, trainers, photos, and edit-info forms
- Explore pagination: backend sends 20 gyms per page
- Control Deck Safety Center and Demo Tools
- `seed_demo_analytics` command for realistic test/demo data
- Upload validation for owner gym images
- Dark/light mode consistency pass across marketplace cards, filters, dashboards, and control surfaces
- Security and backup documentation

### Useful commands

```bash
python manage.py migrate
python manage.py seed_demo_analytics --days 120 --customers 25
python manage.py seed_demo_analytics --days 120 --customers 25 --reset-demo
python manage.py check
python manage.py check --deploy
```

### Test commands

```bash
python manage.py test apps.accounts
python manage.py test apps.gyms
python manage.py test apps.bookings
python manage.py test apps.dashboard
python manage.py test apps.controlpanel
python manage.py test apps.fitness
```

### Control Deck pages

```text
/control/security/
/control/demo-tools/
```

Keep demo tools disabled in real production:

```env
DEMO_TOOLS_ENABLED=False
```

## API & Swagger Control Layer

This build includes a documented API layer for internal testing and future mobile/API work.

- Swagger UI: `/api/docs/`
- ReDoc: `/api/redoc/`
- OpenAPI schema: `/api/schema/`

Main API groups:

- Demo Tools: seed/reset realistic demo analytics data from Swagger.
- Owner Analytics: inspect portfolio and per-gym analytics as JSON.
- Gyms/Favorites: paginated gym explore API and favorite/unfavorite actions.
- Fitness: workout logs, activity calendar, and fitness summary APIs.
- Security/Email Diagnostics: sanitized safety and SMTP diagnostics.

Install/update dependencies after pulling this build:

```bash
pip install -r requirements.txt
python manage.py check
python manage.py test apps.api
```

For demo seeding through Swagger, set:

```env
DEMO_TOOLS_ENABLED=True
```

Keep this disabled in real production.
