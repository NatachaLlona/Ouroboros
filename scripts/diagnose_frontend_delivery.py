"""Compare public HTTP delivery with the current frontend build, without login.

Only public shell/static URLs are read. An optional, uniquely named inert probe
is created and removed in the build directory to establish its live ownership.
No configuration, secret, cookie, account or catalogue data is read or modified.
"""
import argparse
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import sys
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlsplit
from urllib.request import Request, build_opener, HTTPRedirectHandler, ProxyHandler
import uuid
from datetime import datetime, timezone

ROOT=Path(__file__).resolve().parents[1]
BUILD=ROOT/'frontend/dist/browser'

class Assets(HTMLParser):
    def __init__(self):
        super().__init__();self.urls=[]
    def handle_starttag(self, tag, attributes):
        values=dict(attributes)
        if tag=='script' and values.get('src'):self.urls.append(values['src'])
        if tag=='link' and values.get('rel')=='stylesheet':self.urls.append(values['href'])

class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, response, code, message, headers, url):return None

def digest(value):return hashlib.sha256(value).hexdigest()

def source_fingerprint():
    """Match the build stamper's fixed public source inputs, excluding tests."""
    frontend=ROOT/'frontend';files=[]
    for directory in ('src','styles','assets','scripts'):
        files.extend(path for path in (frontend/directory).rglob('*') if path.is_file() and not path.is_symlink() and not path.name.endswith('.spec.ts'))
    files.extend(frontend/name for name in ('package.json','package-lock.json','angular.json','tsconfig.json','tsconfig.app.json'))
    result=hashlib.sha256()
    for path in sorted(files,key=str):
        result.update((path.relative_to(frontend).as_posix()+'\0').encode());result.update(path.read_bytes())
    return result.hexdigest()

def inspect(origin, probe=False):
    """Inspect only fixed loopback HTTP origins and their reachable static graph."""
    parts=urlsplit(origin)
    if parts.scheme!='http' or parts.hostname not in ('localhost','127.0.0.1','::1') or parts.port!=6969 or parts.username or parts.password or parts.path not in ('','/') or parts.query or parts.fragment:
        raise ValueError('Use the approved loopback HTTP application origin on 6969')
    origin=origin.rstrip('/')
    opener=build_opener(ProxyHandler({}),NoRedirect())
    def get(path):
        url=urljoin(origin+'/',path)
        if urlsplit(url).netloc!=parts.netloc:raise ValueError('External asset reference rejected')
        try:response=opener.open(Request(url,headers={'Cache-Control':'no-cache','Accept-Encoding':'identity'}),timeout=15)
        except HTTPError as response:
            return {'status':response.code,'headers':{key.lower():value for key,value in response.headers.items() if key.lower() in ('cache-control','content-type','location','etag','last-modified','server')}},response.read(1048576)
        with response:
            return {'status':response.status,'headers':{key.lower():value for key,value in response.headers.items() if key.lower() in ('cache-control','content-type','location','etag','last-modified','server')}},response.read(8388608)
    home,body=get('/')
    parser=Assets();parser.feed(body.decode('utf-8'))
    local=(BUILD/'index.html').read_bytes()
    report={'checked_at':datetime.now(timezone.utc).isoformat(),'origin':origin,'build_directory':str(BUILD.resolve()),'shell':{**home,'http_sha256':digest(body),'disk_sha256':digest(local),'matches_disk':body==local,'asset_urls':parser.urls},'routes':{},'assets':[],'service_worker_paths':{},'directory_probe':{'executed':False}}
    for path in ('/cadastrar','/consultar','/cadastros','/consultas','/docs','/openapi.json'):
        info,content=get(path);report['routes'][path]={**info,'matches_index':content==local}
    queue=list(parser.urls);seen=set();texts={}
    while queue:
        path=queue.pop(0)
        if path in seen:continue
        seen.add(path)
        if not path.startswith('/frontend/') or '..' in path or not path.endswith(('.js','.css')):raise ValueError('Unexpected asset path')
        disk=BUILD/path.removeprefix('/frontend/')
        if BUILD.resolve() not in disk.resolve().parents:raise ValueError('Asset outside build directory')
        info,content=get(path);expected=disk.read_bytes() if disk.is_file() else b''
        report['assets'].append({'url':path,**info,'bytes':len(content),'http_sha256':digest(content),'disk_sha256':digest(expected),'matches_disk':info['status']==200 and content==expected})
        text=content.decode('utf-8');texts[path]=text
        if path.endswith('.js'):
            for name in re.findall(r'["\'`](?:\./|/frontend/)?((?:chunk|main)-[A-Za-z0-9_-]+\.js)["\'`]',text):
                queue.append('/frontend/'+name)
    all_js='\n'.join(text for path,text in texts.items() if path.endswith('.js'))
    all_css='\n'.join(text for path,text in texts.items() if path.endswith('.css'))
    markers={'save_edit':'Salvar edição','cancel':'Cancelar','discard':'Descartar alterações','where_access':'Onde acessar','application':'Aplicativo','website':'Site','price_placeholder':'00,00','currency_eur':'Euro','currency_usd':'Dólar americano','currency_brl':'Real brasileiro','classification_append':'Adicionar ao final','classification_order':'Ordem atual completa','advanced_filters':'Filtros avançados','clear_filters':'Limpar filtros','recent_searches':'Pesquisas recentes','home_return':'Voltar ao início'}
    report['delivered_markers']={key:value in all_js for key,value in markers.items()}
    report['delivered_markers']['accent']=bool(re.search(r'--accent\s*:\s*#e6bd68',all_css,re.I))
    report['delivered_markers']['home_return_scoped_css']='.home-return{' in all_css
    report['service_worker_code_reference']=bool(re.search(r'navigator\.serviceWorker|provideServiceWorker|ngsw-worker|service-worker\.js',all_js))
    for path in ('/ngsw-worker.js','/ngsw.json','/service-worker.js','/sw.js'):
        info,_=get(path);report['service_worker_paths'][path]=info
    if probe:
        name='delivery-probe-'+uuid.uuid4().hex+'.txt';target=BUILD/name;value=('Ouroboros static directory probe '+uuid.uuid4().hex).encode()
        try:
            with target.open('xb') as output:output.write(value)
            info,content=get('/frontend/'+name)
            report['directory_probe']={'executed':True,'status':info['status'],'matches_owned_probe':content==value,'directory':str(BUILD.resolve())}
        finally:target.unlink(missing_ok=True)
    report['all_assets_match']=all(item['matches_disk'] for item in report['assets'])
    info,manifest_body=get('/frontend/build-info.json')
    report['build_manifest']={'status':info['status'],'headers':info['headers']}
    if info['status']==200:
        manifest=json.loads(manifest_body)
        records={asset['url']:asset for asset in manifest['assets']}
        meta=re.search(r'<meta name="ouroboros-build" content="([0-9a-f]+)">',body.decode('utf-8'))
        report['build_manifest'].update(build_id=manifest['build_id'],source_sha256=manifest['source_sha256'],source_matches_current=manifest['source_sha256']==source_fingerprint(),index_matches=manifest['index_sha256']==digest(body),meta_matches=bool(meta and meta[1]==manifest['build_id']),asset_graph_matches=set(records)=={asset['url'] for asset in report['assets']} and all(records[asset['url']]['sha256']==asset['http_sha256'] for asset in report['assets']))
    report['browser_loaded_document_and_worker_registrations']='NOT_VERIFIED: HTTP cannot inspect an already-open browser document or its existing worker registrations'
    return report

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--origin',default='http://localhost:6969');parser.add_argument('--probe-directory',action='store_true');parser.add_argument('--output',type=Path);parser.add_argument('--summary',action='store_true')
    args=parser.parse_args()
    try:
        report=inspect(args.origin,args.probe_directory)
        if args.output:
            destination=args.output.resolve()
            if (ROOT/'reports').resolve() not in destination.parents:raise ValueError('Report must be under reports/')
            destination.parent.mkdir(exist_ok=True,parents=True);destination.write_text(json.dumps(report,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
        printed={key:report[key] for key in ('checked_at','origin','shell','directory_probe','all_assets_match','build_manifest','delivered_markers','browser_loaded_document_and_worker_registrations')} if args.summary else report
        print(json.dumps(printed,indent=2,ensure_ascii=False))
    except (OSError,URLError,ValueError) as error:
        print(json.dumps({'status':'FAILED','error_type':type(error).__name__}));return 1
    return 0

if __name__=='__main__':sys.exit(main())
