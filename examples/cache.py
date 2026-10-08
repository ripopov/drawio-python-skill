"""Dense SoC datapath: explicit signal names, computed endpoints and reserved lanes."""
import argparse
from pathlib import Path
import tempfile

from drawio_arch import Diagram, style, BLOCK, EDGE, TEXT


def build():
    doc=Diagram(); p=doc.page('L1D',width=2050,height=1210,grid=0)
    p.text('L1 data cache · 32 KiB · 8 ways · 64 sets · 64 B lines · 48-bit PA · PIPT · write-back / write-allocate',40,5,560,40,style=style(TEXT,fontSize=12))
    cpu=p.node('CPU load/store interface\nPA · request type\nstore data · byte enables',40,100,210,100,id='cpu',style=style(BLOCK,fontSize=12))
    hidden='ellipse;opacity=0;fillColor=none;strokeColor=none;'
    for ident,side,y in [('req',1,.2),('store_in',1,.4),('load_out',1,.6),('done',0,.8)]:
        p.port(cpu,'',side,y,id=ident,size=6,style=hidden)
    address=p.container('48-bit physical address',340,60,270,180,id='address')
    for ident,label,y in [('tag','Tag [47:12]',45),('index','Set index [11:6]',90),('offset','Byte offset [5:0]',135)]:
        p.node(label,20,y,230,30,id=ident,parent=address,style=style(BLOCK,fillColor='#fff2cc',fontSize=12))
    tags=p.container('Tag + metadata · 64 sets × 8 ways',780,60,820,160,id='tags')
    compare=p.container('8 parallel comparisons · hit[i] = valid[i] AND (tag[i] == request tag)',780,300,820,110,id='compare')
    data=p.container('Data arrays · 8 ways × 64 sets × 64 B',780,590,820,200,id='data')
    for i in range(8):
        p.node('Way %d\ntag · V · D'%i,10+i*100,50,90,80,id='tw%d'%i,parent=tags,style=style(BLOCK,fillColor='#d5e8d4',fontSize=12))
        p.node('=%d'%i,10+i*100,45,90,40,id='cmp%d'%i,parent=compare,style=style(BLOCK,shape='ellipse',fillColor='#ffe6cc'))
        p.node('Way %d\n64 sets\n64 B / set'%i,10+i*100,55,90,100,id='dw%d'%i,parent=data,style=style(BLOCK,fillColor='#d5e8d4',fontSize=12))
    p.node('Way-select\nmux',610,640,110,120,id='mux',style=style(BLOCK,shape='trapezoid',fillColor='#ffe6cc'))
    p.node('Word / byte selection',340,650,210,90,id='select',style=style(BLOCK,fillColor='#ffe6cc'))
    p.node('Store-hit update\nselected way + byte enables',340,330,230,90,id='store',style=style(BLOCK,fillColor='#f8cecc',fontSize=12))
    p.node('MSHRs\ntrack outstanding misses\nmerge same-line requests',40,390,240,90,id='mshr',style=style(BLOCK,fillColor='#e1d5e7',fontSize=12))
    p.node('Replacement\ninvalid way first\notherwise tree-PLRU',40,650,240,100,id='replacement',style=style(BLOCK,fillColor='#e1d5e7',fontSize=12))
    p.node('Write-back buffer\ndirty victim lines',40,890,240,100,id='writeback',style=style(BLOCK,fillColor='#f8cecc'))
    p.node('L2 interface\nrefill requests · returned lines · dirty write-backs',780,980,600,100,id='l2',style=style(BLOCK,fillColor='#b1ddf0'))
    expected=[]
    bus=style(EDGE,fontSize=12,jumpStyle='arc',jumpSize=6,labelBackgroundColor='#ffffff')
    def link(a,b,label,source='E',target='W',color='#333333',**kwargs):
        expected.append((a,b,label))
        return p.connect(a,b,label,source_side=source,target_side=target,
                         style=style(bus,strokeColor=color),**kwargs)
    link('req',address,'48-bit PA\nrequest type',label_offset=(0,-18))
    link('tag',compare,'request tag → all comparators',lane=685,color='#b8860b',label_segment=1,label_offset=(115,10))
    link('index',tags,'set index',lane=730,color='#b8860b',label_offset=(0,-12))
    # A row-selection bus approaches data from above without crossing intervening blocks.
    p.edge('index',data,'set index → all ways',id='index_data',exit=(1,.5),entry=(.5,0),routing='manual',
           waypoints=[(745,165),(745,550),(1190,550)],style=style(bus,strokeColor='#b8860b'),label_position=(2*(155+385+445/2)/(155+385+445+40)-1),label_offset=(0,-15))
    expected.append(('index',data,'set index → all ways'))
    link('offset','select','byte offset','E','N',via=[(630,210),(630,530),(445,530)],color='#b8860b',label_segment=3,label_offset=(-80,0))
    link(tags,compare,'8 tags + valid bits','S','N',label_offset=(-95,0))
    link(compare,'mux','hit[7:0] selects way','W','N',via=[(735,355),(735,535),(665,535)],color='#9673a6',label_segment=3,label_offset=(-80,-25))
    link(data,'mux','8-way data','W','E',lane=750,color='#32824a',label_offset=(0,20))
    link('mux','select','hit line','W','E',color='#0066cc',label_offset=(0,-12))
    link('select','load_out','load data + completion','W','E',via=[(300,695),(300,160)],color='#0066cc',label_segment=1,label_offset=(-100,-120))
    link('store_in','store','store data + byte enables','E','N',via=[(300,140),(300,260),(455,260)],color='#b85450',label_offset=(0,15))
    link(compare,'store','hit[7:0]','W','E',via=[(700,355),(700,375)],color='#b85450',label_segment=2,label_offset=(0,-12))
    link('store',data,'update selected bytes','N','E',via=[(455,280),(1660,280),(1660,690)],color='#b85450',label_offset=(0,-12))
    link('store',tags,'store hit: dirty = 1','E','E',via=[(650,375),(650,25),(1680,25),(1680,140)],color='#b85450',label_offset=(0,15))
    link(compare,'mshr','no way hits → allocate / merge','W','E',via=[(710,355),(710,450),(310,450),(310,435)],color='#9673a6',label_segment=2,label_offset=(0,-12))
    link('mshr','l2','refill request','S','W',via=[(160,540),(310,540),(310,1030)],color='#9673a6',label_segment=2,label_offset=(-100,0))
    link('mshr','done','complete pending requests','W','W',lane=20,color='#9673a6',label_segment=1,label_offset=(95,-75))
    link(tags,'replacement','valid / dirty metadata','W','E',via=[(760,140),(760,500),(290,500),(290,700)],color='#9673a6',label_segment=2,label_offset=(0,-12))
    link('replacement','writeback','dirty victim selection','S','N',label_offset=(100,0))
    link(data,'writeback','victim line data','S','E',via=[(1190,880),(320,880),(320,940)],color='#b85450',label_offset=(0,-12))
    link('writeback','l2','dirty-line write-back','S','S',lane=1120,color='#b85450',label_offset=(0,-12))
    link('l2',data,'refill 64 B line','N','S',via=[(1080,840),(1190,840)],color='#6c8ebf',label_offset=(0,-12))
    link('l2',tags,'refill: tag, valid = 1, dirty = 0','E','E',lane=1720,color='#6c8ebf',label_offset=(110,0))
    link('l2','mshr','refill → resolve MSHRs','W','E',via=[(650,1030),(650,800),(320,800),(320,435)],color='#6c8ebf',label_segment=2,label_offset=(0,-12))
    p.assert_connections(expected)
    assert not p.layout_warnings(), p.layout_warnings()
    assert not p.label_warnings(), p.label_warnings()
    return doc


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', default=Path(tempfile.gettempdir()) / 'l1-cache.drawio')
    print(build().save(parser.parse_args().output))
