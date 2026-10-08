"""Editable records work for schemas, register maps and interface inventories."""
import argparse
from drawio_arch import Diagram, style, EDGE

TABLES = {
    'Coverage': ['ID','CoverageName','CoverageGroup','Code','IsPolicyCoverage','IsVehicleCoverage','Description'],
    'Vehicle_Coverage': ['ID','Vehicle_ID','Coverage_ID','Active','CreatedDate'],
    'PolicyEditLog': ['ID','Policy_ID','EditedTableName','EditedDate','AdditionalInfo','EditedBy'],
    'Policy_Coverage': ['ID','Policy_ID','Coverage_ID','Active','CreatedDate'],
    'Policy': ['ID','PolicyNumber','PolicyEffectiveDate','PolicyExpireDate','PaymentOption','TotalAmount','Active','AdditionalInfo','CreatedDate'],
    'Bill': ['ID','Policy_ID','DueDate','MinimumPayment','CreatedDate','Balance','Status'],
}


def build():
    doc=Diagram(); p=doc.page('Insurance',width=1340,height=720,background='#f0f0f0')
    positions={'Coverage':(30,60),'Vehicle_Coverage':(30,390),
               'PolicyEditLog':(370,60),'Policy_Coverage':(370,390),
               'Policy':(710,220),'Bill':(1050,220)}
    for name,fields in TABLES.items():
        rows=[('PK' if f=='ID' else 'FK' if f.endswith('_ID') else '',f) for f in fields]
        p.table(name,rows,*positions[name],width=260,id=name)
    crow=style(EDGE,startArrow='ERone',endArrow='ERmany',startFill=0,endFill=0,
               strokeColor='#333333',strokeWidth=1.5,startSize=10,endSize=12)
    connections=[('Policy','PolicyEditLog','W','E'),('Policy','Policy_Coverage','W','E'),
                 ('Policy','Bill','E','W'),('Coverage','Policy_Coverage','E','W'),
                 ('Coverage','Vehicle_Coverage','S','N')]
    for a,b,source,target in connections:
        p.connect(a,b,source_side=source,target_side=target,style=crow)
    p.assert_connections([(a,b,'') for a,b,_,_ in connections])
    assert not p.layout_warnings(), p.layout_warnings()
    return doc


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',default='/tmp/insurance-schema.drawio')
    print(build().save(parser.parse_args().output))
