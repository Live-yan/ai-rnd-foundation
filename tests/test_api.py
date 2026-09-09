from factory.database import Run, Outbox
from factory.schemas import demo_spec
from sqlalchemy import select

A={'X-Actor':'a'};B={'X-Actor':'b'}

def project(c):
    r=c.post('/factory-api/projects',headers=A,json={'title':'test','requirement':'设备检修管理测试'})
    assert r.status_code==201,r.text
    return r.json()['id']


def start(c,p,key='test-idempotent-001',**overrides):
    return c.post(f'/factory-api/projects/{p}/runs',headers=A,json={'idempotency_key':key,**overrides})


def test_auth_is_required(platform):
    c,_=platform
    assert c.get('/factory-api/projects').status_code==401


def test_project_ownership(platform):
    c,_=platform;p=project(c)
    assert c.get('/factory-api/projects',headers=B).json()==[]
    assert c.get('/factory-api/projects/'+p,headers=B).status_code==404
    assert c.post(f'/factory-api/projects/{p}/messages',headers=B,json={'content':'attack'}).status_code==404


def test_idempotency_and_outbox(platform,db):
    c,_=platform;p=project(c)
    one=start(c,p);two=start(c,p)
    assert one.status_code==202 and one.json()['id']==two.json()['id']
    conflict=start(c,project(c))
    assert conflict.status_code==409
    with db.session() as s:
        assert len(list(s.scalars(select(Outbox))))==1


def test_requirement_snapshot(platform,db):
    c,_=platform;p=project(c);r=start(c,p).json()
    assert c.post(f'/factory-api/projects/{p}/messages',headers=A,json={'content':'后来增加需求'}).status_code==200
    with db.session() as s:
        assert len(s.get(Run,r['id']).request['messages'])==1


def test_approval_requires_state_hash_and_limitations(platform,db):
    c,_=platform;p=project(c);r=start(c,p).json();path=f'/factory-api/runs/{r["id"]}/decision';spec=demo_spec()
    approval={'spec_digest':spec.digest(),'approve':True,'accept_limitations':True}
    assert c.post(path,headers=A,json=approval).status_code==409
    with db.session() as s:
        row=s.get(Run,r['id']);row.spec=spec.model_dump();row.spec_digest=spec.digest();row.status='AWAITING_APPROVAL'
    assert c.post(path,headers=B,json=approval).status_code==404
    assert c.post(path,headers=A,json=approval|{'spec_digest':'0'*64}).status_code==409
    assert c.post(path,headers=A,json=approval|{'accept_limitations':False}).status_code==422
    assert c.post(path,headers=A,json=approval).status_code==200
    assert c.post(path,headers=A,json=approval).status_code==200
    assert c.post(path,headers=A,json=approval|{'approve':False}).status_code==409


def test_litellm_does_not_fall_back(platform):
    c,_=platform
    assert start(c,project(c),provider='litellm').status_code==422


def test_unconfigured_tools_rejected(platform):
    c,_=platform;p=project(c)
    assert start(c,p,use_serena=True).status_code==422
    assert start(c,p,sandbox='cube').status_code==422
    assert start(c,p,sandbox='docker').status_code==422


def test_download_not_ready(platform):
    c,_=platform;r=start(c,project(c)).json()
    assert c.get(f'/factory-api/runs/{r["id"]}/download',headers=A).status_code==409
    assert c.get(f'/factory-api/runs/{r["id"]}/download',headers=B).status_code==404


def test_coder_admin_boundary(platform):
    c,_=platform;r=start(c,project(c)).json()
    assert c.post(f'/factory-api/runs/{r["id"]}/coder',headers=A).status_code==403
