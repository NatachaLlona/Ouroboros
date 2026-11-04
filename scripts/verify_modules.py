"""Exercise owned disposable containers; never authenticate against the normal database."""
import argparse
import json
import os
from pathlib import Path
import secrets
import shutil
import socket
import subprocess
import sys
import tempfile
import re

ROOT = Path(__file__).resolve().parents[1]


def command(arguments, env=None, input=None, timeout=180):
    result = subprocess.run(arguments, input=input, capture_output=True, env=env, timeout=timeout)
    if result.returncode:
        # Persist only structural Python traceback metadata; never output request data or credentials.
        diagnostic=result.stderr.decode('utf-8',errors='replace')
        categories=re.findall(r'^([A-Za-z]+Error|[A-Za-z]+Exception)(?::|$)',diagnostic,re.MULTILINE)
        locations=re.findall(r'File "([^"\n]+)", line (\d+)',diagnostic)
        print('Disposable failure categories:',categories,'locations:',locations[-4:],file=sys.stderr)
        raise RuntimeError('Disposable verification command failed: '+arguments[-1])
    return result.stdout


BOOTSTRAP = '''import sys
sys.path.insert(0,'/runtime')
from pathlib import Path
from app.config import load_config
from modules.base.runtime import database_settings
from app.database import Database, connect
from app.migrate import migrate
from app.api_users import APIUserStore
from app.api_credentials import PASSWORD_HASHER, configure_api_credentials
config=load_config()
password=Path('/run/secrets/postgres_password').read_text()
settings=database_settings(config)
with connect(settings,password) as connection:
    migrate(connection)
    migrate(connection)
database=Database(settings,password)
try:
    users=APIUserStore(database)
    users.bootstrap_administrator('module_qa',PASSWORD_HASHER.hash(password))
    configure_api_credentials(config,users)
finally:database.close()
print('Disposable database migrated; disposable administrator created.')
'''


PROBE = '''import sys
from pathlib import Path
import httpx
degraded='--degraded' in sys.argv
base='http://127.0.0.1:8000' if degraded else 'http://frontend:8080'
headers={'Host':'localhost:6969','Origin':'http://localhost:6969'}
with httpx.Client(base_url=base,headers=headers,timeout=1500,trust_env=False) as client:
    assert client.get('/health').status_code==200
    assert client.get('/docs').status_code==200
    schema=client.get('/openapi.json').json()
    assert '/tags' in schema['paths'] and '/tag_categories' in schema['paths']
    if not degraded:
        guest=client.get('/cadastros')
        assert guest.status_code==303 and 'destino=cadastros' in guest.headers['location']
        assert client.get('/frontend/runtime-config.json').status_code==200
        assert '--assistant-text' in client.get('/frontend/assistant-theme.css').text
    password=Path('/run/secrets/postgres_password').read_text()
    login=client.post('/browser/login',json={'username':'module_qa','password':password})
    assert login.status_code==200, ('login',login.status_code)
    assert 'httponly' in login.headers['set-cookie'].lower()
    csrf=login.json()['csrf_token']
    client.headers['X-CSRF-Token']=csrf
    assert client.get('/work_classifications').status_code==200
    if degraded:
        assert client.get('/browser/transcription/options').status_code==503
        payload={'mode':'create','message':'Disposable request','history':[],
            'values':{'display_name_work_classifications':'','work_classification_name':'','description_work_classifications':'','tier':''}}
        assert client.post('/browser/assistant/work-classifications',json=payload).status_code==503
        assert client.get('/tags').status_code==200
        print('PASS: API, Swagger, login and catalogue work without frontend/assistance; assistant fails safely.')
    else:
        protected=client.get('/cadastros')
        assert protected.status_code==200
        assert "style-src 'self'" in protected.headers['content-security-policy']
        created=client.post('/work_classifications',json={'work_classification_name':'module_qa','display_name_work_classifications':'Module QA'})
        assert created.status_code in (200,201), ('create',created.status_code)
        identifier=created.json()['id_work_classifications']
        listing=client.get('/work_classifications',params={'page':1,'page_size':10,'order_by':'tier','order_direction':'asc'})
        assert listing.status_code==200
        assert client.delete('/work_classifications/'+str(identifier)).status_code in (200,204)
        token=client.post('/token',data={'username':'module_qa','password':password})
        assert token.status_code==200
        assert client.get('/tags',headers={'Authorization':'Bearer '+token.json()['access_token']}).status_code==200
        options=client.get('/browser/transcription/options')
        assert options.status_code==200 and options.json()['max_duration_seconds']==600
        if Path('/qa/live-assistant').exists():
            payload={'mode':'create','message':'Use o Nome Fantasia Classificação QA. Mantenha a posição automática.','history':[],
                'values':{'display_name_work_classifications':'','work_classification_name':'','description_work_classifications':'','tier':''}}
            response=client.post('/browser/assistant/work-classifications',json=payload)
            assert response.status_code==200, ('assistant',response.status_code)
            assert response.json()['reply'] and isinstance(response.json()['proposals'],list)
            print('PASS: one live GPT-5.4 structured suggestion through the isolated API; response content omitted; no save.')
        audio=Path('/qa/audio.wav')
        if audio.exists():
            response=client.post('/browser/transcription',content=audio.read_bytes(),headers={'Content-Type':'audio/wav'})
            assert response.status_code==200, ('transcription',response.status_code)
            assert response.json()['complete'] and len(response.json()['text'])>10
            print('PASS: real containerized transcription returned a complete result; content omitted.')
        print('PASS: frontend assets/proxy, protected navigation, HttpOnly login, CSRF CRUD, bearer API and speech options.')
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--audio', type=Path)
    parser.add_argument('--publish', action='store_true', help='Publish QA frontend only on the approved port, when free')
    parser.add_argument('--live-assistant', action='store_true', help='Make one live GPT-5.4 call with the configured provider file mounted only into disposable assistance')
    args = parser.parse_args()
    if args.publish:
        with socket.socket() as probe:
            if probe.connect_ex(('127.0.0.1',6969)) == 0:
                raise RuntimeError('Approved port 6969 is occupied; verification never selects another port or stops its owner')
    project = 'ouroboros-module-qa-'+secrets.token_hex(5)
    directory = Path(tempfile.mkdtemp(prefix='module-qa-',dir=ROOT/'.tmp'))
    env = os.environ.copy()
    for key in ('OPENAI_API_KEY','PGPASSWORD','POSTGRES_PASSWORD'):
        env.pop(key,None)
    base = ['docker','compose','--project-name',project,'--project-directory',str(ROOT)]
    qa = base+['--file',str(directory/'compose.json')]
    started = False
    try:
        sys.path.insert(0,str(ROOT))
        from app.credentials import write_secret
        password=secrets.token_urlsafe(36)
        secret=write_secret(password,directory)
        write_secret(secrets.token_urlsafe(64),directory,'assistance_service_key')
        write_secret(secrets.token_urlsafe(64),directory,'jwt_signing_key')
        env.update(OUROBOROS_DB_NAME='module_qa',OUROBOROS_DB_USER='module_qa',
            OUROBOROS_DB_PORT='6669',OUROBOROS_DB_SECRET_FILE=str(secret),
            OUROBOROS_PUBLIC_HOST='127.0.0.1',OUROBOROS_PUBLIC_PORT='6969')
        document=json.loads(command(base+['--file',str(ROOT/'compose.yaml'),'config','--format','json'],env))
        document.pop('volumes',None)
        document['secrets']['postgres_password']['file']=str(secret)
        document['secrets']['service_key']['file']=str(directory/'.secrets/assistance_service_key')
        def mount(source,target,readonly=True):
            return {'type':'bind','source':str(source),'target':target,'read_only':readonly}
        config=json.loads((ROOT/'modules/base/config.example.json').read_text(encoding='utf-8'))
        config['database'].update(name='module_qa',user='module_qa')
        config['browser']={'origin':'http://localhost:6969','allow_loopback_http':True}
        folder=directory/'base';folder.mkdir()
        (folder/'.config.json').write_text(json.dumps(config),encoding='utf-8')
        (directory/'public.json').write_bytes((ROOT/'frontend/public/runtime-config.json').read_bytes())
        (directory/'ai.json').write_bytes((ROOT/'modules/assistance/config.example.json').read_bytes())
        (directory/'empty.env').touch()
        if args.live_assistant:
            (directory/'live-assistant').touch()
        (directory/'logs').mkdir()
        (directory/'bootstrap.py').write_text(BOOTSTRAP,encoding='utf-8')
        (directory/'probe.py').write_text(PROBE,encoding='utf-8')
        if args.audio:
            shutil.copyfile(args.audio,directory/'audio.wav')
        services=document['services']
        if not args.publish:
            services['frontend']['ports']=[]
        services['postgres']['ports']=[]
        services['postgres']['volumes']=[]
        services['postgres']['tmpfs']=['/var/lib/postgresql/data']
        for name in ('api','assistance','frontend'):
            services[name].pop('build',None)
            services[name]['image']='ouroboros-'+name+':latest'
        services['api']['volumes']=[mount(folder,'/config/base',False),mount(directory/'.secrets','/runtime/.secrets',False),
            mount(directory/'logs','/runtime/logs',False),mount(directory,'/qa')]
        services['assistance']['volumes']=[mount(directory/'ai.json','/config/assistance.json'),
            mount(ROOT/'.env' if args.live_assistant else directory/'empty.env','/runtime/.env'),mount(ROOT/'.cache/speech','/models')]
        services['frontend']['volumes']=[mount(directory/'public.json','/config/frontend.json'),
            mount(ROOT/'frontend/public/images','/usr/share/nginx/html/frontend/images')]
        (directory/'compose.json').write_text(json.dumps(document),encoding='utf-8')
        started=True
        command(qa+['up','--detach','--wait','postgres'],env)
        command(qa+['run','--rm','-T','--no-deps','api','python','/qa/bootstrap.py'],env)
        command(qa+['up','--detach','--wait','api','assistance','frontend'],env)
        output=command(qa+['exec','-T','api','python','/qa/probe.py'],env,timeout=1800)
        print(output.decode(),end='')
        public=json.loads((directory/'public.json').read_text(encoding='utf-8'))
        public['nome_assistente_2']='Disposable runtime assistant'
        public['assistant_2_colors']['primary']='#EFEFEF'
        (directory/'public.json').write_text(json.dumps(public),encoding='utf-8')
        runtime_probe="import httpx; c=httpx.Client(trust_env=False); before=c.get('http://frontend:8080/frontend/build-info.json').json()['build_id']; print(before)"
        before=command(qa+['exec','-T','api','python','-c',runtime_probe],env).strip()
        command(qa+['restart','frontend'],env)
        runtime_check="import httpx; c=httpx.Client(trust_env=False); assert c.get('http://frontend:8080/frontend/runtime-config.json').json()['nome_assistente_2']=='Disposable runtime assistant'; assert '#EFEFEF' in c.get('http://frontend:8080/frontend/assistant-theme.css').text; print(c.get('http://frontend:8080/frontend/build-info.json').json()['build_id'])"
        after=command(qa+['exec','-T','api','python','-c',runtime_check],env).strip()
        assert before==after
        print('PASS: public name/color changed after frontend restart without Angular rebuild; compiled build identity unchanged.')
        command(qa+['stop','frontend','assistance'],env)
        print(command(qa+['exec','-T','api','python','/qa/probe.py','--degraded'],env).decode(),end='')
    finally:
        if started:
            # Only this randomly named, explicitly owned tmpfs stack is removed; no volumes are deleted.
            command(qa+['down'],env)
        if directory.resolve().parent != (ROOT/'.tmp').resolve() or not directory.name.startswith('module-qa-'):
            raise RuntimeError('Disposable cleanup target escaped the owned QA directory')
        shutil.rmtree(directory)


if __name__=='__main__':
    main()
