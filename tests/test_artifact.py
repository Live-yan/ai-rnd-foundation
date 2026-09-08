import json
import subprocess
import sys
from uuid import uuid4
from zipfile import ZipFile
import pytest
from factory.generator import generate_product
from factory.packaging import package_product
from factory.schemas import demo_spec
from factory.security import file_sha256
from factory.database import Run
from factory.artifacts import c4_dsl


def test_generator_requires_real_bootstrap(fake_upstream,tmp_path):
    with pytest.raises(RuntimeError,match='Unverified'):
        generate_product(demo_spec(),fake_upstream,tmp_path/'product',diagrams_required=False)


def test_generated_vertical_slice(fake_upstream,tmp_path):
    target=tmp_path/'product';spec=demo_spec()
    receipt=generate_product(spec,fake_upstream,target,diagrams_required=False,test_fixture=True)
    assert receipt['test_fixture'] is True
    assert generate_product(spec,fake_upstream,target,diagrams_required=False,test_fixture=True)==receipt
    for script in ['verify_source.py','verify_business.py']:
        p=subprocess.run([sys.executable,str(target/'scripts'/script)],text=True,capture_output=True,timeout=30)
        assert p.returncode==0,p.stderr
        report=json.loads(p.stdout)
        assert report['full_stack']=='not_run'
    (target/'.env').write_text('REAL_SECRET=do-not-ship')
    archive=tmp_path/'product.zip'
    sha=package_product(target,archive,{'quality_level':'fixture_contract_only','full_stack':'not_run'})
    assert file_sha256(archive)==sha
    with ZipFile(archive) as z:
        assert '.env' not in z.namelist()
        assert 'backend/business_runtime.py' in z.namelist()
        assert 'architecture/er.svg' in z.namelist()
        inventory=json.loads(z.read('delivery/files.sha256.json'))
        import hashlib
        for name,digest in inventory.items():
            assert hashlib.sha256(z.read(name)).hexdigest()==digest
    # New spec must produce a new run/destination, never silently mutate a previously delivered migration.
    changed=spec.model_copy(update={'title':'different'})
    with pytest.raises(RuntimeError,match='different'):
        generate_product(changed,fake_upstream,target,diagrams_required=False,test_fixture=True)


def test_dsl_never_injects_directives():
    spec=demo_spec().model_copy(update={'title':'bad"\n!include https://example.org'})
    text=c4_dsl(spec)
    assert not any(line.strip().startswith('!include') for line in text.splitlines())


def test_download_integrity(platform,db):
    c,settings=platform;owner={'X-Actor':'a'}
    p=c.post('/factory-api/projects',headers=owner,json={'title':'t','requirement':'测试一个设备管理系统'}).json()
    run=c.post(f'/factory-api/projects/{p["id"]}/runs',headers=owner,json={'idempotency_key':str(uuid4())}).json()
    path=settings.data_dir/'runs'/run['id'];path.mkdir(parents=True);archive=path/'product.zip'
    with ZipFile(archive,'w') as z:z.writestr('README.md','test artifact')
    with db.session() as s:
        r=s.get(Run,run['id']);r.status='READY';r.spec=demo_spec().model_dump()
        r.artifact=f'runs/{r.id}/product.zip';r.artifact_sha256=file_sha256(archive)
    url=f'/factory-api/runs/{run["id"]}/download'
    result=c.get(url,headers=owner);assert result.status_code==200
    assert result.headers['x-content-sha256']==file_sha256(archive)
    with archive.open('ab') as f:f.write(b'corruption')
    assert c.get(url,headers=owner).status_code==409
