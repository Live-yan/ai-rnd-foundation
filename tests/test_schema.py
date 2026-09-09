import pytest
from pydantic import ValidationError
from factory.schemas import ProjectSpec, FieldSpec, EntitySpec, demo_spec
from factory.generator import migration_source


def test_demo_roundtrip():
    spec=demo_spec()
    assert ProjectSpec.model_validate_json(spec.model_dump_json()).digest()==spec.digest()


@pytest.mark.parametrize('name',['../escape','UPPER','with-dash','class','a b','x'*41,'id','owner_id','created_at'])
def test_invalid_field_names(name):
    with pytest.raises(ValidationError):
        FieldSpec(name=name,label='x',kind='string')


@pytest.mark.parametrize('name',['schema','docs','health','openapi'])
def test_reserved_routes(name):
    with pytest.raises(ValidationError):
        EntitySpec(name=name,label='x',fields=[FieldSpec(name='title',label='x',kind='string')])


def test_cycle_rejected():
    value=demo_spec().model_dump()
    value['entities'][0]['fields'].append({'name':'backlink','label':'x','kind':'reference','references':'maintenance'})
    with pytest.raises(ValidationError): ProjectSpec.model_validate(value)


def test_unknown_reference_rejected():
    value=demo_spec().model_dump();value['entities'][1]['fields'][0]['references']='missing'
    with pytest.raises(ValidationError):ProjectSpec.model_validate(value)


def test_duplicate_fields_rejected():
    value=demo_spec().model_dump();value['entities'][0]['fields'].append(value['entities'][0]['fields'][0])
    with pytest.raises(ValidationError):ProjectSpec.model_validate(value)


def test_extra_fields_rejected():
    with pytest.raises(ValidationError):ProjectSpec.model_validate(demo_spec().model_dump() | {'shell':'rm -rf /'})


def test_long_index_names_fit_postgres():
    import ast
    value=demo_spec().model_dump()
    long='entity_'+'a'*33
    value['entities'][0]['name']=long
    value['entities'][1]['fields'][0]['references']=long
    value['entities'][1]['fields'][0]['name']='reference_'+'x'*30
    tree=ast.parse(migration_source(ProjectSpec.model_validate(value)))
    names=[node.args[0].value for node in ast.walk(tree) if isinstance(node,ast.Call)
           and isinstance(node.func,ast.Attribute) and node.func.attr=='create_index']
    assert all(len(name)<=63 for name in names)
