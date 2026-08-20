# myGym Security Patch Report — SEC-001 / SEC-002

This archive was produced from the uploaded backend source and patched in-place.

## Changes applied

- `apps/api/customer_views.py`
  - Added explicit Django CSRF protection to `LoginAPIView`.
  - Added `LoginRateThrottle` to the login endpoint.
- `apps/api/throttles.py`
  - Added an IP-based DRF `SimpleRateThrottle` with scope `login`.
- `core/settings.py`
  - Added `DEFAULT_THROTTLE_RATES['login']`.
  - Default rate is `5/min`, configurable with `API_LOGIN_THROTTLE_RATE`.
- `apps/api/test_security.py`
  - Added regression tests for missing-CSRF rejection, valid-CSRF processing, throttling, and no-500 behavior.
- `.env.example`
  - Added `API_LOGIN_THROTTLE_RATE=5/min`.
  - Changed demo tools example to `DEMO_TOOLS_ENABLED=False` for safe-by-default production setup.

## Validation performed in the packaging environment

- All Python source files compile successfully with `python -m compileall`.
- The uploaded archive contained no `.env`, SQLite database, SQL dump, or `data_backup*.json` files.
- The patch matched the actual `LoginAPIView` and `REST_FRAMEWORK` structures in the uploaded backend.

## Runtime validation to run locally

The packaging sandbox cannot install Django dependencies from the internet, so the Django runtime test suite could not be executed here.

Run inside your existing backend virtual environment:

```powershell
python manage.py test apps.api.test_security -v 2
python manage.py test
```

Then start Django and rerun Sentinel. The intended results are:

```text
SEC-001  PASS  login without CSRF -> 403
SEC-002  PASS  repeated failed login attempts -> eventually 429
```
