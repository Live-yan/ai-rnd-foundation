import asyncio
import json
import httpx
import pytest
from factory.config import Settings
from factory.providers.llm import LiteLLMPlanner
from factory.providers.coder import CoderClient
from factory.schemas import demo_spec


def test_llm_http_contract():
    def respond(request):
        assert request.url.path=='/v1/chat/completions'
        assert request.headers['authorization']=='Bearer test-key'
        assert json.loads(request.content)['response_format']=={'type':'json_object'}
        return httpx.Response(200,json={'choices':[{'message':{'content':demo_spec().model_dump_json()}}]})
    settings=Settings(_env_file=None,model_api_key='test-key',model_base_url='http://gateway/v1')
    result=asyncio.run(LiteLLMPlanner(settings,httpx.MockTransport(respond)).draft('a real user requirement'))
    assert result['slug']==demo_spec().slug


def test_llm_errors_are_not_demo_success():
    def respond(request):return httpx.Response(429,text='secret-provider-body')
    settings=Settings(_env_file=None,model_api_key='test-key')
    with pytest.raises(RuntimeError) as e:
        asyncio.run(LiteLLMPlanner(settings,httpx.MockTransport(respond)).draft('x'))
    assert '429' in str(e.value) and 'secret-provider-body' not in str(e.value)


def test_llm_rejects_markdown_json():
    def respond(request):return httpx.Response(200,json={'choices':[{'message':{'content':'```json\n{}\n```'}}]})
    with pytest.raises(ValueError):
        asyncio.run(LiteLLMPlanner(Settings(_env_file=None,model_api_key='x'),httpx.MockTransport(respond)).draft('x'))


def test_coder_http_contract_not_live():
    def respond(request):
        assert request.url.path=='/api/v2/users/me/workspaces'
        assert request.headers['Coder-Session-Token']=='coder-test'
        assert json.loads(request.content)['template_id']=='tpl'
        return httpx.Response(201,json={'id':'work','name':'test','owner_name':'admin'})
    settings=Settings(_env_file=None,coder_url='https://coder.test',coder_token='coder-test',coder_template_id='tpl')
    result=asyncio.run(CoderClient(settings,httpx.MockTransport(respond)).create_workspace('1234'))
    assert result['source_import']=='manual_zip_upload'
    assert result['readiness']=='created_not_build_verified'


def test_langgraph_demo_when_dependency_installed():
    pytest.importorskip('langgraph')
    from factory.planner import plan
    result=asyncio.run(plan('fixed demo requirement','demo',False,Settings(_env_file=None)))
    assert result.digest()==demo_spec().digest()
