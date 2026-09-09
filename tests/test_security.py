import pytest
from factory.security import safe_relative,redact,token_matches,include_file,run_path


@pytest.mark.parametrize('value',['../file','/etc/passwd','C:/secret',r'a\b','a/../../b',''])
def test_bad_paths(value):
    with pytest.raises(ValueError):safe_relative(value)


def test_path_and_redaction(tmp_path):
    assert str(safe_relative('docs/readme.md'))=='docs/readme.md'
    assert redact('Bearer ABC secret',['secret'])=='Bearer [REDACTED] [REDACTED]'
    assert '[REDACTED]' in redact('postgresql+psycopg://user:password@db/a')
    assert token_matches('a','a') and not token_matches('a','')
    with pytest.raises(ValueError):run_path(tmp_path,'../escape')


@pytest.mark.parametrize('name',['.env','.env.prod','a.key','a.pem','credentials.json','node_modules/file.js','.git/config'])
def test_secret_exclusions(tmp_path,name):
    p=tmp_path/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text('secret')
    assert not include_file(p,tmp_path)


def test_example_env_allowed(tmp_path):
    p=tmp_path/'.env.example';p.write_text('API_KEY=')
    assert include_file(p,tmp_path)
