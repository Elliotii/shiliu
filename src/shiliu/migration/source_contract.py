"""Reviewed Schema26 history variants, without changing the W00 frozen schema.

Column order reflects different dynamic ALTER histories. These two attribute
variants were observed read-only in candidate A. Neither changes stored values;
all actual NULL/time/enum values still pass the strict target converter.
"""
from shiliu.migration.values import MigrationRejected

VARIANTS = {
    ('assistant_spaces','maintenance_mode','dflt_value'): {"'automatic'"},
    ('retrieval_index_meta','updated_at','notnull'): {0},
}


def check_columns(table,actual,expected):
    a={c['name']:c for c in actual};b={c['name']:c for c in expected}
    if len(a)!=len(actual) or set(a)!=set(b):raise MigrationRejected('source_column_set_mismatch',table_name=table)
    changes=[]
    if [c['name'] for c in actual]!=[c['name'] for c in expected]:changes.append({'table':table,'kind':'column_order'})
    for name,c in b.items():
        for attribute in ('type','notnull','dflt_value','pk','hidden'):
            if a[name][attribute]==c[attribute]:continue
            if a[name][attribute] not in VARIANTS.get((table,name,attribute),set()):
                raise MigrationRejected('source_column_contract_mismatch',table_name=table)
            changes.append({'table':table,'column':name,'attribute':attribute,'value':a[name][attribute]})
    return changes
