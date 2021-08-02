# Swap to True when running migrations. algobuilder does not have permissions to alter database structure.
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql_psycopg2',
        'NAME': 'algotrader',
        'USER': '[db_username]',
        'PASSWORD': '[db_password]',
        'HOST': 'localhost',
        'PORT': '5432',
        # 'OPTIONS': {
        #    'sslmode': 'require',
        #    'sslrootcert': os.path.join(BASE_DIR, 'algobuilder/server-ca.pem'),
        #    'sslcert': os.path.join(BASE_DIR, 'algobuilder/client-cert.pem'),
        #    'sslkey':  os.path.join(BASE_DIR, 'algobuilder/client-key.pem')
        # },
    },
}

CELERY_BROKER_URL = 'amqp://[rabbitmq_username]:[rabbitmq_password]@localhost:5672/algobuilder'

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = '[secret_key]'