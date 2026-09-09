import pytest


def create_device(c,owner='a'):
    r=c.post('/business-api/device',json={'name':'泵','code':'P1','enabled':True},headers={'X-Actor':owner})
    assert r.status_code==201,r.text
    return r.json()['id']


def test_crud_and_isolation(business):
    c=business;id=create_device(c)
    assert c.get('/business-api/device').json()['total']==1
    assert c.get('/business-api/device',headers={'X-Actor':'b'}).json()['total']==0
    assert c.patch(f'/business-api/device/{id}',json={'name':'新泵'}).status_code==200
    assert c.patch(f'/business-api/device/{id}',json={'name':'steal'},headers={'X-Actor':'b'}).status_code==404
    assert c.delete(f'/business-api/device/{id}',headers={'X-Actor':'b'}).status_code==404
    assert c.delete(f'/business-api/device/{id}').status_code==200


def test_reference_and_delete_restrict(business):
    c=business;id=create_device(c)
    payload={'device_id':id,'performed_on':'2026-09-08','notes':'检修'}
    assert c.post('/business-api/maintenance',json=payload,headers={'X-Actor':'b'}).status_code==422
    child=c.post('/business-api/maintenance',json=payload)
    assert child.status_code==201
    assert c.delete(f'/business-api/device/{id}').status_code==409
    assert c.delete('/business-api/maintenance/'+str(child.json()['id'])).status_code==200
    assert c.delete(f'/business-api/device/{id}').status_code==200


@pytest.mark.parametrize('patch',[{'owner_id':'b'},{'name':None},{'enabled':'true'},{'enabled':1},{'unknown':1}])
def test_invalid_patch(business,patch):
    id=create_device(business)
    assert business.patch(f'/business-api/device/{id}',json=patch).status_code==422


@pytest.mark.parametrize('query',['limit=0','limit=201','offset=-1','offset=100001'])
def test_pagination_bounds(business,query):
    assert business.get('/business-api/device?'+query).status_code==422


def test_search_escapes_wildcard(business):
    create_device(business)
    assert business.get('/business-api/device?q=%25').json()['total']==0
    assert business.get('/business-api/device?q=泵').json()['total']==1


def test_schema_and_openapi(business):
    assert len(business.get('/business-api/schema').json()['entities'])==2
    doc=business.get('/openapi.json').json()
    assert 'post' in doc['paths']['/business-api/device']
