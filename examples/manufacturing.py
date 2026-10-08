"""Outside return lanes and branch labels. Run with PYTHONPATH=skill/scripts."""
import argparse
from pathlib import Path
import tempfile

from drawio_arch import Diagram, style, BLOCK, EDGE


def build():
    doc = Diagram(); p = doc.page('Manufacturing',width=2220,height=980)
    process = style(BLOCK,rounded=1,fillColor='#dae8fc',strokeColor='#333333',fontColor='#000000')
    decision = style(process,shape='rhombus',rounded=0,fillColor='#ffe6cc')
    limit = style(process,shape='ellipse',fillColor='#fff2cc')
    nodes = [
        ('start','Start',60,100,150,60,limit),
        ('raw','Process raw materials',290,95,200,70,process),
        ('inspect','Inspect raw materials',570,95,200,70,process),
        ('materials_ok','Materials quality\nOK?',845,70,190,120,decision),
        ('reject','Reject and return\nmaterials',1160,95,220,70,process),
        ('begin','Begin production',845,330,200,70,process),
        ('assemble','Assemble widgets',1125,330,200,70,process),
        ('initial','Initial testing',1405,330,200,70,process),
        ('initial_ok','Pass initial\ntesting?',1685,305,190,120,decision),
        ('rework','Rework',1960,330,190,70,process),
        ('qc','Quality control',585,565,200,70,process),
        ('qc_ok','Pass quality\ncontrol?',865,540,190,120,decision),
        ('package','Package widgets',1115,565,200,70,process),
        ('ship','Ship widgets',1405,565,200,70,process),
        ('end','End',1685,570,150,60,limit),
        ('scrap','Scrap',870,810,180,70,process),
    ]
    for ident,label,x,y,w,h,s in nodes: p.node(label,x,y,w,h,id=ident,style=s)
    expected = []
    def link(a,b,label='',source='E',target='W',**kwargs):
        expected.append((a,b,label))
        return p.connect(a,b,label,source_side=source,target_side=target,
                         style=style(EDGE,strokeColor='#333333',labelBackgroundColor='#ffffff'),
                         label_offset=(0,-12) if label else (0,0),**kwargs)
    for a,b in [('start','raw'),('raw','inspect'),('inspect','materials_ok'),('begin','assemble'),('assemble','initial'),('initial','initial_ok'),('qc','qc_ok'),('package','ship'),('ship','end')]: link(a,b)
    link('materials_ok','reject','No')
    link('materials_ok','begin','Yes','S','N',label_position=-.6)
    link('reject','raw',source='N',target='N',lane=25)
    link('initial_ok','rework','No')
    link('rework','assemble',source='N',target='N',lane=275)
    link('initial_ok','qc','Yes','S','N',lane=475)
    link('qc_ok','package','Yes')
    link('qc_ok','scrap','No','S','N',label_position=-.6)
    link('scrap','begin',source='W',target='W',lane=520)
    p.assert_connections(expected)
    assert not p.layout_warnings(), p.layout_warnings()
    return doc


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', default=Path(tempfile.gettempdir()) / 'manufacturing.drawio')
    args=parser.parse_args()
    print(build().save(Path(args.output)))
