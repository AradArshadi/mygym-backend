import sys
from pathlib import Path

from decouple import config, Csv
from django.core.exceptions import ImproperlyConfigured

IMGBB_API_KEY = config("IMGBB_API_KEY", default="")

BASE_DIR = Path(__file__).resolve().parent.parent

RUNNING_TESTS = any(arg == 'test' for arg in sys.argv)

ENVIRONMENT = config('ENVIRONMENT', default='development')
IS_PRODUCTION = ENVIRONMENT.lower() in {'production', 'prod'}

SECRET_KEY = config('SECRET_KEY', default='')
if not SECRET_KEY:
    if IS_PRODUCTION:
        raise ImproperlyConfigured('SECRET_KEY must be set when ENVIRONMENT=production.')
    SECRET_KEY = 'dev-secret-key-change-me'
elif IS_PRODUCTION and SECRET_KEY == 'dev-secret-key-change-me':
    raise ImproperlyConfigured('Production cannot use the development SECRET_KEY fallback.')

DEBUG = config('DEBUG', default=not IS_PRODUCTION, cast=bool)
ALLOWED_HOSTS = config('ALLOWED_HOSTS', default='127.0.0.1,localhost', cast=Csv())
if IS_PRODUCTION and not DEBUG:
    local_only_hosts = {'127.0.0.1', 'localhost', ''}
    if not ALLOWED_HOSTS or set(ALLOWED_HOSTS).issubset(local_only_hosts):
        raise ImproperlyConfigured('Production ALLOWED_HOSTS must include the deployed domain.')

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'rest_framework',
    'drf_spectacular',
    'drf_spectacular_sidecar',
    'apps.accounts',
    'apps.gyms',
    'apps.bookings',
    'apps.reviews',
    'apps.analytics',
    'apps.dashboard',
    'apps.fitness',
    'apps.notifications',
    'apps.controlpanel',
    'apps.emails',
    'apps.systemlogs',
    'apps.api',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'apps.systemlogs.middleware.RequestLoggingMiddleware',
]

ROOT_URLCONF = 'core.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'core.wsgi.application'

DB_ENGINE = config('DB_ENGINE', default='sqlite')
USE_SQLITE_FOR_TESTS = config('USE_SQLITE_FOR_TESTS', default=True, cast=bool)

# Tests should be isolated from the developer/production database.
# By default, `python manage.py test ...` uses an in-memory SQLite database, even if
# the application itself is configured for MySQL. This prevents broken or leftover
# MySQL test schemas from causing migration errors such as
# "Table 'gyms_importbatch' already exists".
# Set USE_SQLITE_FOR_TESTS=False only when you intentionally want to run the
# suite against MySQL and you have a clean test database.
if RUNNING_TESTS and USE_SQLITE_FOR_TESTS:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': ':memory:',
        }
    }
elif DB_ENGINE == 'mysql':
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.mysql',
            'NAME': config('DB_NAME'),
            'USER': config('DB_USER'),
            'PASSWORD': config('DB_PASSWORD'),
            'HOST': config('DB_HOST', default='localhost'),
            'PORT': config('DB_PORT', default='3306'),
            'TEST': {
                'NAME': config('TEST_DB_NAME', default='test_' + config('DB_NAME')),
            },
        }
    }
else:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': BASE_DIR / config('DB_NAME', default='db.sqlite3'),
        }
    }

AUTH_USER_MODEL = 'accounts.User'

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'Europe/Berlin'
USE_I18N = True
USE_TZ = True

STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_DIRS = [BASE_DIR / 'static']
STORAGES = {
    'default': {
        'BACKEND': 'django.core.files.storage.FileSystemStorage',
    },
    'staticfiles': {
        'BACKEND': 'whitenoise.storage.CompressedManifestStaticFilesStorage' if IS_PRODUCTION else 'django.contrib.staticfiles.storage.StaticFilesStorage',
    },
}
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

EMAIL_BACKEND = config('EMAIL_BACKEND', default='django.core.mail.backends.console.EmailBackend')
EMAIL_HOST = config('EMAIL_HOST', default='')
EMAIL_PORT = config('EMAIL_PORT', default=587, cast=int)
EMAIL_USE_TLS = config('EMAIL_USE_TLS', default=True, cast=bool)
EMAIL_USE_SSL = config('EMAIL_USE_SSL', default=False, cast=bool)
EMAIL_HOST_USER = config('EMAIL_HOST_USER', default='')
EMAIL_HOST_PASSWORD = config('EMAIL_HOST_PASSWORD', default='')
EMAIL_TIMEOUT = config('EMAIL_TIMEOUT', default=20, cast=int)
DEFAULT_FROM_EMAIL = config('DEFAULT_FROM_EMAIL', default='myGym <noreply@mygym.local>')
SERVER_EMAIL = config('SERVER_EMAIL', default=DEFAULT_FROM_EMAIL)
SUPPORT_EMAIL = config('SUPPORT_EMAIL', default=DEFAULT_FROM_EMAIL)
SITE_URL = config('SITE_URL', default='http://127.0.0.1:8000')
DEMO_TOOLS_ENABLED = config('DEMO_TOOLS_ENABLED', default=not IS_PRODUCTION, cast=bool)
MAX_GYM_IMAGE_UPLOAD_MB = config('MAX_GYM_IMAGE_UPLOAD_MB', default=5, cast=int)
ALLOWED_GYM_IMAGE_EXTENSIONS = [ext.lower().strip() for ext in config('ALLOWED_GYM_IMAGE_EXTENSIONS', default='jpg,jpeg,png,webp', cast=Csv()) if ext.strip()]

if RUNNING_TESTS:
    EMAIL_BACKEND = 'django.core.mail.backends.locmem.EmailBackend'
    PASSWORD_HASHERS = ['django.contrib.auth.hashers.MD5PasswordHasher']


# REST API / OpenAPI documentation
REST_FRAMEWORK = {
    'DEFAULT_SCHEMA_CLASS': 'drf_spectacular.openapi.AutoSchema',
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework.authentication.BasicAuthentication',
        'rest_framework.authentication.SessionAuthentication',
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
    ],
    'DEFAULT_THROTTLE_RATES': {
        'login': config(
            'API_LOGIN_THROTTLE_RATE',
            default='5/min',
        ),
    },
}

SPECTACULAR_SETTINGS = {
    'TITLE': 'myGym API',
    'DESCRIPTION': (
        'Internal and future-facing API layer for myGym. '
        'Dangerous demo/control endpoints require staff/admin access and DEMO_TOOLS_ENABLED=True. '
        'Use Swagger for testing, demo seeding, owner analytics inspection, fitness debugging, and email diagnostics.'
    ),
    'VERSION': '0.9.3.0',
    'SERVE_INCLUDE_SCHEMA': False,
    'SWAGGER_UI_DIST': 'SIDECAR',
    'SWAGGER_UI_FAVICON_HREF': 'SIDECAR',
    'REDOC_DIST': 'SIDECAR',
    'SWAGGER_UI_SETTINGS': {
        'deepLinking': True,
        'persistAuthorization': True,
        'displayOperationId': False,
        'filter': True,
        'defaultModelsExpandDepth': 1,
        'defaultModelExpandDepth': 2,
        'docExpansion': 'none',
        'tagsSorter': 'alpha',
        'operationsSorter': 'alpha',
    },
    'TAGS': [
        {'name': 'Demo Tools', 'description': 'Admin-only testing/demo operations. Must be disabled for real production.'},
        {'name': 'Owner Analytics', 'description': 'Owner portfolio and per-gym analytics backed by bookings, subscriptions, and QR check-ins.'},
        {'name': 'Gyms', 'description': 'Gym exploration and detail APIs.'},
        {'name': 'Favorites', 'description': 'Customer favorite gym actions.'},
        {'name': 'Fitness', 'description': 'Workout logs, activity map, and customer fitness home data.'},
        {'name': 'Security', 'description': 'Sanitized deployment and safety diagnostics.'},
        {'name': 'Email Diagnostics', 'description': 'Sanitized email config and SMTP/API probe actions.'},
    ],
}

LOGIN_REDIRECT_URL = 'fitness_home'
LOGOUT_REDIRECT_URL = 'gym_list'

# Production security switches. Defaults remain local-dev friendly unless ENVIRONMENT=production.
USE_X_FORWARDED_HOST = config('USE_X_FORWARDED_HOST', default=IS_PRODUCTION, cast=bool)
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https') if config('SECURE_PROXY_SSL_HEADER_ENABLED', default=IS_PRODUCTION, cast=bool) else None
SECURE_SSL_REDIRECT = config('SECURE_SSL_REDIRECT', default=IS_PRODUCTION, cast=bool)
SESSION_COOKIE_SECURE = config('SESSION_COOKIE_SECURE', default=IS_PRODUCTION, cast=bool)
CSRF_COOKIE_SECURE = config('CSRF_COOKIE_SECURE', default=IS_PRODUCTION, cast=bool)
SECURE_HSTS_SECONDS = config('SECURE_HSTS_SECONDS', default=31536000 if IS_PRODUCTION else 0, cast=int)
SECURE_HSTS_INCLUDE_SUBDOMAINS = config('SECURE_HSTS_INCLUDE_SUBDOMAINS', default=IS_PRODUCTION, cast=bool)
SECURE_HSTS_PRELOAD = config('SECURE_HSTS_PRELOAD', default=IS_PRODUCTION, cast=bool)
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = 'DENY'
CSRF_TRUSTED_ORIGINS = [origin for origin in config('CSRF_TRUSTED_ORIGINS', default='', cast=Csv()) if origin]


# Logging / observability
LOG_DIR = BASE_DIR / 'logs'
LOG_DIR.mkdir(exist_ok=True)
LOG_LEVEL = config('LOG_LEVEL', default='INFO')
LOG_ALL_REQUESTS = config('LOG_ALL_REQUESTS', default=False, cast=bool)

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '[{asctime}] {levelname} {name} {module}:{lineno} - {message}',
            'style': '{',
        },
        'simple': {
            'format': '{levelname} {name}: {message}',
            'style': '{',
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'simple',
        },
        'app_file': {
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': LOG_DIR / 'mygym.log',
            'maxBytes': 1024 * 1024 * 5,
            'backupCount': 5,
            'formatter': 'verbose',
        },
        'email_file': {
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': LOG_DIR / 'emails.log',
            'maxBytes': 1024 * 1024 * 5,
            'backupCount': 5,
            'formatter': 'verbose',
        },
    },
    'loggers': {
        'django': {
            'handlers': ['console', 'app_file'],
            'level': LOG_LEVEL,
            'propagate': True,
        },
        'mygym.events': {
            'handlers': ['console', 'app_file'],
            'level': LOG_LEVEL,
            'propagate': False,
        },
        'mygym.requests': {
            'handlers': ['console', 'app_file'],
            'level': LOG_LEVEL,
            'propagate': False,
        },
        'mygym.emails': {
            'handlers': ['console', 'email_file'],
            'level': LOG_LEVEL,
            'propagate': False,
        },
    },
}
