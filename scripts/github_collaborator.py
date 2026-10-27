"""Check the authorized repository and optionally invite its requested collaborator.

Credentials are obtained from the GitHub CLI keyring in memory, never printed or
written. --resolve-ip optionally handles a broken local DNS route while keeping
HTTPS certificate and hostname verification enabled for api.github.com.
"""
import argparse
import datetime
import json
from pathlib import Path
import socket
import subprocess
import http.client
import urllib.error
import urllib.request

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--invite',action='store_true')
    parser.add_argument('--resolve-ip')
    args=parser.parse_args()
    if args.resolve_ip:
        original=socket.getaddrinfo
        def resolve(host,port,*a,**kw):
            return original(args.resolve_ip if host=='api.github.com' else host,port,*a,**kw)
        socket.getaddrinfo=resolve
    auth=subprocess.run(['gh','auth','token'],capture_output=True,text=True,check=True)
    token=auth.stdout.strip()
    connection=http.client.HTTPSConnection('api.github.com',timeout=8)
    def request(path,method='GET',body=None):
        assert path.startswith('/repos/aminemons/project') or path=='/user'
        data=json.dumps(body).encode() if body is not None else None
        headers={'Authorization':'Bearer '+token,'Accept':'application/vnd.github+json','X-GitHub-Api-Version':'2022-11-28','User-Agent':'ThermoBridge-setup'}
        for attempt in range(3):
            try:
                connection.request(method,path,body=data,headers=headers)
                response=connection.getresponse(); payload=response.read()
                return response.status,json.loads(payload) if payload else None
            except (OSError,TimeoutError,http.client.HTTPException):
                connection.close()
                if attempt==2: raise RuntimeError('GitHub API network timeout; no successful invitation response confirmed')
        raise RuntimeError('Unreachable')
    _,user=request('/user')
    code,repo=request('/repos/aminemons/project')
    if code!=200: raise RuntimeError(f'Repository access failed: HTTP {code}')
    permissions=repo.get('permissions',{})
    result={'repository':'aminemons/project','authenticated_login':user.get('login'),
            'requested_user':'Ishaq-ML','requested_permission':'push',
            'timestamp_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),
            'authenticated_repository_permissions':permissions}
    code,_=request('/repos/aminemons/project/collaborators/Ishaq-ML')
    if code==204:
        _,level=request('/repos/aminemons/project/collaborators/Ishaq-ML/permission')
        result.update(status='already_collaborator',permission=level.get('permission'))
    elif code==404:
        code,pending=request('/repos/aminemons/project/invitations')
        if code!=200: raise RuntimeError(f'Cannot check pending invitations: HTTP {code}')
        invitation=next((item for item in pending if item.get('invitee',{}).get('login','').lower()=='ishaq-ml'),None)
        if invitation:
            result.update(status='pending_acceptance',invitation_id=invitation['id'],permission=invitation.get('permissions'))
        elif not args.invite:
            result.update(status='absent')
        else:
            code,invitation=request('/repos/aminemons/project/collaborators/Ishaq-ML','PUT',{'permission':'push'})
            if code==201:
                result.update(status='invited_pending_acceptance',invitation_id=invitation['id'],permission=invitation.get('permissions'))
            elif code==204:
                result.update(status='already_collaborator')
            else:
                result.update(status='blocked',http_status=code,message=invitation.get('message'))
    else:
        result.update(status='blocked',http_status=code)
    output=Path(__file__).resolve().parents[1]/'reports/collaborator.json'
    output.parent.mkdir(exist_ok=True)
    output.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))
    if result['status']=='blocked': raise SystemExit(1)

if __name__=='__main__':main()
