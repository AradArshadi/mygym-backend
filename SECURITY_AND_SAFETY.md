# myGym Security & Safety Notes

## Production `.env` essentials

```env
ENVIRONMENT=production
DEBUG=False
SECRET_KEY=<long-random-secret>
ALLOWED_HOSTS=your-domain.example
CSRF_TRUSTED_ORIGINS=https://your-domain.example
SITE_URL=https://your-domain.example
SESSION_COOKIE_SECURE=True
CSRF_COOKIE_SECURE=True
SECURE_SSL_REDIRECT=True
DEMO_TOOLS_ENABLED=False
```

On PythonAnywhere, test HTTPS redirect carefully to avoid proxy redirect loops.

## Operational checks

```bash
python manage.py check
python manage.py check --deploy
python manage.py show_email_config
python manage.py email_probe you@example.com --template
```

## Upload safety

Gym image uploads are restricted to JPG, JPEG, PNG and WEBP by default, with a maximum size controlled by `MAX_GYM_IMAGE_UPLOAD_MB`.

## Control Deck Safety Center

Admins can review safety status at:

```text
/control/security/
```

Demo/test seed tools live at:

```text
/control/demo-tools/
```

Keep demo tools disabled for real production.
