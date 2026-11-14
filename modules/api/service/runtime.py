"""Container entry point with only the restricted runtime SQL login and signing key."""
import os
from pathlib import Path
import psycopg
import uvicorn
from database.settings import read_jsonc, validate_provisioning
from api.service.config import load
from api.service.migrations import LOGIN, inspect_contract
from api.service.store import Store
from api.service.app import create_app
from api.service import tls
from database.settings import ConfigurationError


def main():
    root=Path('/runtime')
    settings=load(root)
    certificate=Path('/run/secrets/api_tls_certificate')
    private_key=Path('/run/secrets/api_tls_private_key')
    tls.validate(certificate,private_key,settings['tls']['server_name'])
    document=validate_provisioning(read_jsonc(root/'provisioning.jsonc'))
    password=Path('/run/secrets/api_sql_password').read_text(encoding='utf-8')
    arguments={'host':'postgresql','port':5432,'dbname':document['database_name'],'user':LOGIN,'password':password}
    with psycopg.connect(**arguments,connect_timeout=settings['connect_timeout_seconds']) as connection:
        inspect_contract(connection,document,require_api=True)
    store=Store(document,settings,arguments)
    with store.transaction() as session:
        effective=session.limits()
        settings['limits']['request_bytes']['value']=effective['request_bytes']
    key=Path('/run/secrets/api_token_signing_key').read_text(encoding='utf-8')
    app=create_app(store,key)
    import ssl
    uvicorn.run(app,host='0.0.0.0',port=8000,workers=1,access_log=False,log_level='warning',timeout_keep_alive=15,
                proxy_headers=False,ssl_certfile=str(certificate),ssl_keyfile=str(private_key),
                ssl_version=ssl.PROTOCOL_TLS_SERVER)


if __name__=='__main__':
    try:
        main()
    except ConfigurationError as error:
        raise SystemExit(str(error)) from None
    except Exception:
        raise SystemExit('API startup failed; verify the registered contract, operator bounds and restricted SQL login') from None
