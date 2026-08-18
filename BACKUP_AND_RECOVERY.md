# myGym Backup & Recovery Guide

Use this checklist before migrations, deployments, or destructive demo-data cleanup.

## 1. Django JSON backup

```bash
mkdir -p backups
python manage.py dumpdata --natural-foreign --natural-primary --indent 2 -o backups/mygym_backup.json
```

Restore into an empty database:

```bash
python manage.py migrate
python manage.py loaddata backups/mygym_backup.json
```

## 2. Media backup

Owner-uploaded images live in `media/`. Back it up together with the database:

```bash
tar -czf backups/mygym_media_backup.tar.gz media/
```

On Windows PowerShell, zip the `media` folder manually or use:

```powershell
Compress-Archive -Path media -DestinationPath backups\mygym_media_backup.zip
```

## 3. MySQL dump if available

If `mysqldump` is available:

```bash
mysqldump -u USER -p --databases DB_NAME --result-file=backups/mygym_mysql_backup.sql
```

On Windows, prefer `--result-file` instead of PowerShell `>` redirection.

## 4. Before-deploy checklist

```bash
python manage.py check
python manage.py test apps.bookings
python manage.py test apps.dashboard
python manage.py test apps.gyms
python manage.py test apps.fitness
python manage.py test apps.controlpanel
```

For production-like environments:

```bash
python manage.py check --deploy
```

## 5. Demo data warning

`seed_demo_analytics` is append-only. Running it repeatedly creates more fake bookings, check-ins, subscriptions, favorites and workout logs. Keep `DEMO_TOOLS_ENABLED=False` for real production.
