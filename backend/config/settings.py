from datetime import timedelta
from pathlib import Path
from decouple import Csv, config

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = config('DJANGO_SECRET_KEY', default='dev-secret-key-not-for-production')
DEBUG = config('DEBUG', default=False, cast=bool)
ALLOWED_HOSTS = ['*']

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'rest_framework',
    'rest_framework.authtoken',
    'django_tasks',
    'django_tasks_db',
    'core',
    'accounts',
    'contracts',
    'billing',
    'webhooks',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
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

WSGI_APPLICATION = 'config.wsgi.application'

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': config('DB_NAME', default='yunojuno'),
        'USER': config('DB_USER', default='yunojuno'),
        'PASSWORD': config('DB_PASSWORD', default='yunojuno'),
        'HOST': config('DB_HOST', default='localhost'),
        'PORT': config('DB_PORT', default='5432'),
    }
}

REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework.authentication.TokenAuthentication',
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
    ],
}

EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST = config('EMAIL_HOST', default='localhost')
EMAIL_PORT = config('EMAIL_PORT', default=1025, cast=int)
EMAIL_USE_TLS = False
EMAIL_USE_SSL = False

STATIC_URL = '/static/'
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True

# Background tasks queue in Postgres (the django.tasks backport), so enqueueing is part of the caller's transaction.
TASKS = {'default': {'BACKEND': 'django_tasks_db.DatabaseBackend', 'QUEUES': ['default']}}


# Webhook settings start

# Webhook hosts exempt from the https and SSRF checks: the local receiver, and only in development.
WEBHOOK_DEV_ALLOWED_HOSTS = config(
    'WEBHOOK_DEV_ALLOWED_HOSTS', default='localhost,webhook-receiver' if DEBUG else '', cast=Csv()
)

# Stamped on every payload envelope; receivers branch on it. From the environment, so dev can run ahead of prod.
WEBHOOK_PAYLOAD_VERSION = config('WEBHOOK_PAYLOAD_VERSION', default=1, cast=int)

# How long to wait for a destination before counting the attempt as failed.
WEBHOOK_TIMEOUT_SECONDS = 10
# The destination controls error text, so don't store unbounded amounts of it.
WEBHOOK_MAX_ERROR_LENGTH = 500
# How much of an error goes into log lines and alert emails.
WEBHOOK_ERROR_SUMMARY_LENGTH = 200

# Retry n waits WEBHOOK_RETRY_DELAYS[n - 1]; from retry 7 it stays at the last (8h) delay.
WEBHOOK_RETRY_DELAYS = [
    timedelta(minutes=1),
    timedelta(minutes=5),
    timedelta(minutes=15),
    timedelta(hours=1),
    timedelta(hours=2),
    timedelta(hours=4),
    timedelta(hours=8),
]
# ±10%, so retries to a destination that's just recovered don't all arrive at once.
WEBHOOK_RETRY_JITTER = 0.1
# Stop retrying, and disable the endpoint, this long after the first attempt.
WEBHOOK_GIVE_UP_AFTER = timedelta(days=7)
# Admins hear about a failing endpoint once this retry fails (the 4th is about 1h20m in).
WEBHOOK_EMAIL_AFTER_RETRY = 4

# How long the old secret keeps signing after a rotation, so receivers can switch over without failed deliveries.
WEBHOOK_SECRET_ROTATION_GRACE = timedelta(hours=24)
# How many payloads the delivery log shows.
WEBHOOK_RECENT_DELIVERIES = 20

# Webhook settings end

# Print webhook delivery outcomes (info and up) wherever the worker or server runs.
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {'console': {'class': 'logging.StreamHandler'}},
    'loggers': {'webhooks': {'handlers': ['console'], 'level': 'INFO'}},
}
