# Deployment health check

After deployment, verify:

```bash
python manage.py check --deploy
python manage.py show_email_config
python manage.py email_probe your-email@example.com --template
```

Expected SMTP result:

- `EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend`
- `EMAIL_HOST_PASSWORD=SET`
- `Connection opened.`
- `Diagnostic email sent ...`

If Gmail SMTP is used, use an app password, not your normal Gmail password.
