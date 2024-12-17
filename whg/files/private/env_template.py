# env_template.py

'''
Include here all environment variables which are required either for Docker compose or in JavaScript.
This file is parsed by `load_env.py` and variables are set appropriately for the site context.
Boolean values must be set here as strings: `local_settings.py` will convert them to Python boolean values.

NB: IF YOU CHANGE SETTINGS HERE, YOU MUST RUN `python ./.env/load_env.py` FROM THE PROJECT FOLDER TO UPDATE SETTINGS

'''

ENV_VARS = {
    'base': {
        'DEBUG': '1',
        'SECRET_KEY': 'mje%e)l(w8r9rdxtvj_$01^h!3bp8fuc*6bsluqwsy6&yln2-2x',
        'USER_NAME': 'whgadmin',
        'WHGADMIN_PASSWORD': 'v3rs10n3',
        'DOCKER_IMAGE': 'worldhistoricalgazetteer/web',
        'DB_PORT_INTERNAL': '5432',
        'DB_USER': 'whgadmin',
        'DB_PASSWORD': 'xV#5tY$9@pQ2zR',
        'DOI_USER_ID': 'pitt.whg',
        'DOI_LANDING_PAGE': 'https://whgazetteer.org/',
        'ELASTIC_PASSWORD': 'OS0JPq3vXY8gJiwx9llF',
        'ES_HOST': '144.126.204.70',
        'ES_PORT': '9200',
        'ES_SCHEME': 'https',
        'TILEBOSS': 'https://tiles.whgazetteer.org',
        'TILER_URL': 'http://tiles.whgazetteer.org:3000/tiler',
        'FLOWER_BASIC_AUTH': 'whgadmin:0nw4rd!',
        'URL_FRONT': 'http://localhost:8001/', # Used in local development, overridden by specific SITES settings
        'VESPA_NETWORK': 'vespa-net',
        'VESPA_IMAGE': 'vespaengine/vespa:8.412.20', # Vespa Docker image
        'VESPA_CONFIG_HOSTNAME': 'vespa-cfg',
        'VESPA_CONFIG_IP': '172.18.0.2',
        'VESPA_CONFIG_PORT': '19071',
        'VESPA_CONFIG_SERVICE_PORT': '7070',
        'VESPA_SERVICE_HOSTNAME': 'vespa-ssrv',
        'VESPA_SERVICE_IP': '172.18.0.3',
        'VESPA_SERVICE_PORT': '7080',
    },
    'sites': {
        'local': {
            'DOCKER_IMAGE_TAG': '0.1.4',
            'URL_FRONT': 'https://local.whgazetteer.org/',
            'NGINX_SERVER_NAME': 'local.whgazetteer.org',
            'DEBUG': 'True',
            'SUBNET': '172.20.0.0/16',
            'DOCKER_HOST_IP':'localhost:2375',
            'APP_PORT': '8001',
            # 'DB_HOST': 'db', # default for local setup from sample
            # 'DB_HOST': 'db_beta', # default for local setup from cloned database
            'DB_HOST': 'postgres', # Used for Kubernetes
            'DB_PORT': '5432',
            # 'DB_NAME': 'whgv3', # default for local setup from sample
            'DB_NAME': 'whgv3beta',
            'DB_DIR': '/home/stephen/workspace/whg_database',
            'DOI_PASSWORD': 'QdTZxi5C8d3wEUW',  # for DataCite test API
            'DOI_PREFIX': '10.83427',  # for DataCite test API
            'REDIS_PORT': '6380',
            'FLOWER_PORT': '5557',
            'ES_WHG': 'whg3dev',
            'ES_PUB': 'pub_dev',
            'TESTING': 'True', # Used by Captcha
        },
        'dev-whgazetteer-org': {
            'DOCKER_IMAGE_TAG': '0.1.4',
            'URL_FRONT': 'https://dev.whgazetteer.org/',
            'NGINX_SERVER_NAME': 'dev.whgazetteer.org',
            'DEBUG': 'True',
            'SUBNET': '172.21.0.0/16', # If you change this, you will need to regenerate Docker certificates
            'DOCKER_HOST_IP':'172.21.0.1:2376', # If you change this, you will need to regenerate Docker certificates
            'APP_PORT': '8004',
            # 'DB_HOST': 'db_beta',
            'DB_HOST': 'postgres', # Used for Kubernetes
            'DB_PORT': '5435',
            'DB_NAME': 'whgv3beta',
            'DOI_PASSWORD': 'QdTZxi5C8d3wEUW', # for DataCite test API
            'DOI_PREFIX': '10.83427', # for DataCite test API
            'REDIS_PORT': '6381',
            'FLOWER_PORT': '5558',
            'ES_WHG': 'whg3dev',
            'ES_PUB': 'pub_dev',
            'TESTING': 'True', # Used by Captcha
        },
        'whgazetteer-org': {
            'DOCKER_IMAGE_TAG': '0.1.4',
            'URL_FRONT': 'https://whgazetteer.org/',
            'NGINX_SERVER_NAME': 'whgazetteer.org',
            'DEBUG': 'False',
            'SUBNET': '172.20.0.0/16', # If you change this, you will need to regenerate Docker certificates
            'DOCKER_HOST_IP':'172.20.0.1:2376', # If you change this, you will need to regenerate Docker certificates
            'APP_PORT': '8005',
            # 'DB_HOST': 'db_beta',
            'DB_HOST': 'postgres', # Used for Kubernetes
            'DB_PORT': '5436',
            'DB_NAME': 'whgv3beta',
            'DOI_PASSWORD': 'Scoured6Filter4broom', # for DataCite live API
            'DOI_PREFIX': '10.60681', # for DataCite live API
            'REDIS_PORT': '6382',
            'FLOWER_PORT': '5559',
            'ES_WHG': 'whg',
            'ES_PUB': 'pub',
        }
    }
}
