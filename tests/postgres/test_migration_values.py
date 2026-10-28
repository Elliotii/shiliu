from datetime import datetime,timezone
import pytest
from shiliu.migration.values import JsonDocument,MigrationRejected,convert,logical_hash


def test_canonical_is_typed_null_order_offset_and_float():
    cols={'j':{'type':'jsonb'},'at':{'type':'timestamptz'},'n':{'type':'double precision'}}
    row={'j':None,'at':datetime.fromisoformat('2026-10-23T08:00:00+08:00'),'n':1.5}
    h=logical_hash([row],cols)
    assert h!=logical_hash([dict(row,j=JsonDocument(None))],cols)
    assert h==logical_hash([dict(row,at=datetime.fromisoformat('2026-10-23T00:00:00+00:00'))],cols)
    assert logical_hash([dict(row,j=JsonDocument([3,1,2]))],cols)!=logical_hash([dict(row,j=JsonDocument([1,2,3]))],cols)
    assert logical_hash([dict(row,j=JsonDocument({'a':None}))],cols)!=logical_hash([dict(row,j=JsonDocument({}))],cols)


@pytest.mark.parametrize('value,typ',[('NaN','jsonb'),('','jsonb'),(2,'boolean'),('1','bigint'),(float('inf'),'double precision'),('2026-10-23T00:00:00','timestamptz')])
def test_invalid_column_values_rejected(value,typ):
    with pytest.raises(MigrationRejected):convert(value,{'type':typ,'nullable':True},field='synthetic.field')


def test_reviewed_historical_schema_variants_do_not_relax_value_contract():
    from copy import deepcopy
    from shiliu.migration.source_contract import check_columns
    from shiliu.migration.snapshot import mapping
    from shiliu.migration.values import MigrationRejected,convert
    import pytest
    expected=mapping()['tables']['assistant_spaces']['source']['columns']
    actual=deepcopy(expected)[::-1]
    next(c for c in actual if c['name']=='maintenance_mode')['dflt_value']="'automatic'"
    assert len(check_columns('assistant_spaces',actual,expected))==2
    next(c for c in actual if c['name']=='maintenance_mode')['type']='BLOB'
    with pytest.raises(MigrationRejected,match='source_column_contract_mismatch'):
        check_columns('assistant_spaces',actual,expected)
    definition=mapping()['tables']['retrieval_index_meta']['columns']['updated_at']
    with pytest.raises(MigrationRejected,match='null_required_column'):
        convert(None,definition,field='retrieval_index_meta.updated_at')
