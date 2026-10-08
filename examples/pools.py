"""BPMN-style pools with editable composite symbols; not BPMN execution semantics."""
import argparse
from drawio_arch import Diagram, style, BLOCK, EDGE


def event(p,x,y,*,parent='1',id=None,end=False,envelope=None,timer=False):
    d=42; g=p.group(x-d/2,y-d/2,d,d,parent=parent,id=id)
    p.node('',0,0,d,d,parent=g,connectable=0,
           style=style(BLOCK,shape='ellipse',fillColor='#ffffff',strokeColor='#333333',strokeWidth=3.5 if end else 1.5))
    stroke=style(EDGE,endArrow='none',strokeColor='#ffffff' if envelope=='filled' else '#333333',strokeWidth=1.5)
    if envelope:
        p.node('',9,14,24,15,parent=g,connectable=0,
               style=style(BLOCK,fillColor='#000000' if envelope=='filled' else '#ffffff',strokeColor='#333333'))
        p.edge(source_point=(9,14),target_point=(21,24),parent=g,routing='manual',style=stroke)
        p.edge(source_point=(21,24),target_point=(33,14),parent=g,routing='manual',style=stroke)
    if timer:
        for end_point in [(21,9),(30,21)]:
            p.edge(source_point=(21,21),target_point=end_point,parent=g,routing='manual',style=stroke)
    return g


def build():
    doc=Diagram(); p=doc.page('Scheduling and factory',width=1520,height=990,background='#efefef')
    task=style(BLOCK,rounded=1,fillColor='#333333',strokeColor='#999999',fontColor='#ffffff',fontStyle=1,fontSize=12)
    arrow=style(EDGE,strokeColor='#888888',strokeWidth=1,labelBackgroundColor='#efefef')
    def pool(name,y,height,id):
        group=p.group(60,y,1400,height,id=id)
        p.node('',0,0,1400,height,parent=group,connectable=0,style=style(BLOCK,rounded=1,arcSize=10,fillColor='#ffffff',strokeColor='#bbbbbb'))
        p.node(name,0,0,44,height,parent=group,connectable=0,style=style(BLOCK,rounded=1,horizontal=0,fillColor='#ffe0b2',strokeColor='#e0b483',fontStyle=1))
        return group
    scheduling=pool('SCHEDULING',60,190,'scheduling')
    factory=pool('FACTORY',430,470,'factory')
    start=event(p,109,95,parent=scheduling,id='s_start')
    names=[('get','Get Task'),('create','Create Schedule'),('verify','Verify Schedule'),('commit','Commit Schedule')]
    for i,(ident,label) in enumerate(names): p.node(label,190+i*220,68,150,54,id=ident,parent=scheduling,style=task)
    end=event(p,1109,95,parent=scheduling,id='s_end',end=True)
    expected=[]
    def link(a,b,label='',source='E',target='W',**kwargs):
        expected.append((a,b,label)); return p.connect(a,b,label,source_side=source,target_side=target,style=kwargs.pop('style',arrow),**kwargs)
    for a,b in zip([start,'get','create','verify','commit'],['get','create','verify','commit',end]): link(a,b)
    document=p.node('Order List',224,290,170,100,id='document',style=style(BLOCK,shape='note',fillColor='#f7a45a',strokeColor='#d97f2b',fontStyle=1))
    link('create',document,source='S',target='E',via=[(545,340)],style=style(arrow,dashed=1))
    clock=event(p,109,250,parent=factory,id='clock',timer=True)
    region=p.node('',190,80,1050,340,id='region',parent=factory,style=style(BLOCK,rounded=1,arcSize=12,fillColor='#fdece0',strokeColor='#e6b184'))
    link(clock,region)
    f_start=event(p,59,170,parent=region,id='f_start')
    for ident,label,x,y,w,h in [('compose','Compose Specification',130,143,150,54),('check','Check Warehouse',330,143,150,54),('available','Available?',530,138,110,64),('produce','Produce Goods',710,143,150,54)]:
        p.node(label,x,y,w,h,id=ident,parent=region,style=task)
    complete=event(p,939,170,parent=region,id='complete',end=True,envelope='filled')
    no_message=event(p,585,280,parent=region,id='no_message',envelope='outline')
    for a,b in [(f_start,'compose'),('compose','check'),('check','available'),('produce',complete)]: link(a,b)
    link('available','produce','Yes',label_offset=(0,-12))
    link('available',no_message,'No','S','N',label_offset=(18,0))
    link(no_message,'produce',source='E',target='S',via=[(1035,790)])
    f_end=event(p,1309,250,parent=factory,id='f_end',end=True)
    link(region,f_end)
    link(document,f_start,source='S',target='N',style=style(arrow,dashed=1,startArrow='open',endArrow='open'))
    link(complete,'create','Order Completed','N','S',via=[(1189,270),(597.5,270)],target_fraction=.85,label_offset=(0,-12),style=style(arrow,dashed=1))
    p.assert_connections(expected)
    assert not p.layout_warnings(), p.layout_warnings()
    return doc


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',default='/tmp/bpmn.drawio')
    print(build().save(parser.parse_args().output))
