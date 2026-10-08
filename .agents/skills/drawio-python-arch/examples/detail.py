"""Small example for layers, page links, containers and waypoints."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from drawio_arch import Diagram, style, EDGE


def build():
    doc = Diagram()
    overview = doc.page('Overview',id='overview')
    data = overview.layer('Datapath')
    blocks = [overview.node(name,40+i*240,120,170,65,parent=data,id=name.lower().replace(' ','-')) for i,name in enumerate(['Sensor','Capture','Sample FIFO','DMA'])]
    for a,b in zip(blocks,blocks[1:]):
        overview.edge(a,b,'16-bit samples',parent=data)
    # Native page link stored in a metadata wrapper.
    overview.node('Capture detail →',280,230,170,40,parent=data,metadata={'link':'data:page/id,capture-detail'})
    p = doc.page('Capture detail',id='capture-detail')
    lane = p.container('Capture',30,60,840,400)
    input_reg = p.node('Input register',30,140,150,60,parent=lane)
    and_stencil = '<shape w="100" h="60" aspect="variable" strokewidth="inherit"><background><path><move x="0" y="0"/><line x="60" y="0"/><curve x1="113" y1="0" x2="113" y2="60" x3="60" y3="60"/><line x="0" y="60"/><close/></path></background><foreground><fillstroke/></foreground></shape>'
    gate = p.stencil('AND mask',and_stencil,310,140,110,60,parent=lane)
    output_reg = p.node('Output register',600,140,150,60,parent=lane)
    mask = p.node('16-bit mask register',275,290,190,60,parent=lane)
    p.edge(input_reg,gate,'16-bit',parent=lane,entry=(0,.3))
    p.edge(gate,output_reg,'16-bit',parent=lane)
    p.edge(mask,gate,'16-bit mask',parent=lane,exit=(0,.5),entry=(0,.7),waypoints=[(240,320),(240,182)])
    clocks = p.layer('Clock')
    clock = p.node('clk_sample',40,510,150,40,parent=clocks)
    for node, x in [(input_reg,135),(output_reg,705),(mask,400)]:
        p.edge(clock,node,'',parent=clocks,exit=(.5,0),entry=(.5,1),waypoints=[(115,490),(x,490)],style=style(EDGE,dashed=1,strokeColor='#b85450'))
    return doc


if __name__ == '__main__':
    print(build().save(sys.argv[1] if len(sys.argv)>1 else '/tmp/drawio-demo/detail.drawio'))
