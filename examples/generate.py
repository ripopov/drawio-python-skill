"""Run: python3 generate.py [--output-dir /path/to/output] [--rows 4 --cols 4]."""
import argparse
from pathlib import Path
import sys
import tempfile
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from drawio_arch import Diagram, style, BLOCK, EDGE, TEXT


def mesh(rows=4, cols=4, bits=128):
    doc = Diagram()
    p = doc.page('Mesh', width=max(650, cols*170+100), height=max(650, rows*150+100))
    p.text('%d×%d mesh NoC • bidirectional %d-bit links' % (rows, cols, bits), 40, 15, cols*170, 30)
    ports = {}
    for r in range(rows):
        for c in range(cols):
            router = p.node('R%d%d' % (r, c), 70+c*170, 90+r*150, 70, 60, id='r%d_%d' % (r,c))
            for name, x, y in [('N', .5, 0), ('E', 1, .5), ('S', .5, 1), ('W', 0, .5)]:
                ports[r,c,name] = p.port(router, name, x, y)
    bidirectional = style(EDGE, startArrow='block', endArrow='block', strokeColor='#6c8ebf')
    for r in range(rows):
        for c in range(cols):
            if c+1 < cols:
                p.edge(ports[r,c,'E'], ports[r,c+1,'W'], style=bidirectional)
            if r+1 < rows:
                p.edge(ports[r,c,'S'], ports[r+1,c,'N'], style=bidirectional)
    return doc


def cpu():
    doc = Diagram()
    p = doc.page('CPU', width=1120, height=520)
    cpu = p.container('CPU', 30, 50, 1040, 370)
    front = p.container('Front-end', 25, 55, 310, 240, parent=cpu)
    back = p.container('Back-end', 360, 55, 650, 240, parent=cpu)
    bpu = p.node('BPU', 25, 60, 100, 55, parent=front)
    ifu = p.node('IFU', 175, 60, 100, 55, parent=front)
    iq = p.node('IQ', 175, 160, 100, 55, parent=front)
    units = [p.node(name, 25+i*155, 160, 120, 55, parent=back) for i,name in enumerate(['Rename','Issue','Execute','ROB'])]
    # Cross-container edges use page coordinates; endpoints stay bound when moved.
    p.edge(bpu, ifu, 'prediction', exit=(1,.5), entry=(0,.5))
    p.edge(ifu, iq, 'instructions', exit=(.5,1), entry=(.5,0))
    for a,b in zip([iq]+units, units):
        p.edge(a,b,'uops',exit=(1,.5),entry=(0,.5))
    p.edge(units[-1], bpu, 'branch feedback', exit=(.5,0), entry=(.5,0), waypoints=[(940,85),(105,85)], style=style(EDGE, dashed=1, strokeColor='#b85450', fontColor='#b85450'))
    p.text('BPU: Branch Prediction Unit   IFU: Instruction Fetch Unit   IQ: Instruction Queue\nROB: Reorder Buffer', 40, 440, 1010, 50)
    return doc


def axi():
    doc = Diagram()
    p = doc.page('AXI test system', width=1080, height=740)
    gray = style(BLOCK, fillColor='#eeeeee', strokeColor='#000000')
    full = 'ellipse;html=0;fillColor=#ffe599;strokeColor=#000000;fontSize=11;labelBackgroundColor=#ffffff;'
    lite = style(full, fillColor='#fff2cc')
    cyan = style(full, fillColor='#a2e8ef')
    e = style(EDGE, strokeColor='#000000', jumpStyle='arc', jumpSize=8)
    test = p.node('Test Control', 400, 30, 240, 65, style=gray)
    tp = p.port(test, 'AXI master', .5, 1, style=full)
    bus = p.node('AXI Interconnect', 60, 150, 940, 65, style=style(gray, fillColor='#e1d5e7'))
    p.edge(tp, p.port(bus, '', .49, 0, style=cyan), style=e)
    conv = p.node('AXI2AXI-Lite', 415, 295, 210, 70, style=gray)
    cin = p.port(conv, 'Full', .5, 0, style=full)
    cout = p.port(conv, 'Lite', .5, 1, style=lite)
    simp = p.node('AXI-Lite bus simplifier', 380, 425, 280, 70, style=gray)
    upstream = p.port(simp, 'upstream', .5, 0, style=lite)
    p.edge(p.port(bus, '', .49, 1, style=cyan), cin, style=e)
    p.edge(cout, upstream, style=e)
    downstream = [p.port(simp, 'port%d' % i, .15+.23*i, 1, style=lite) for i in range(4)]
    blocks = []
    for i, name in enumerate(['S2MM', 'MM2S', 'MM2M', 'Memory']):
        x = 70+i*250
        node = p.node(name, x, 625, 170, 70, style=gray)
        fp = p.port(node, 'Full', .25, 0, style=full)
        lane = 720 if i == 2 else x+42.5
        bp = p.port(bus, '', (lane-60)/940, 1, style=cyan)
        points = [(lane,600),(x+42.5,600)] if i == 2 else []
        p.edge(bp, fp, style=e, exit=(.5,1), entry=(.5,0), waypoints=points)
        if i < 3:
            lp = p.port(node, 'Lite', .75, 0, style=lite)
            sx = 380+280*(.15+.23*i)
            tx = x+127.5
            p.edge(downstream[i], lp, style=e, exit=(.5,1), entry=(.5,0), waypoints=[(sx,540+i*25),(tx,540+i*25)])
        blocks.append(node)
    return doc


GLOBE = '''<shape w="72" h="72" aspect="fixed" strokewidth="inherit"><background><ellipse x="1" y="1" w="70" h="70"/></background><foreground><stroke/><ellipse x="20" y="1" w="32" h="70"/><stroke/><path><move x="1" y="36"/><line x="71" y="36"/><move x="6" y="19"/><curve x1="24" y1="25" x2="48" y2="25" x3="66" y3="19"/><move x="6" y="53"/><curve x1="24" y1="47" x2="48" y2="47" x3="66" y3="53"/></path><stroke/></foreground></shape>'''
ROUTER_TOP = '''<shape w="155" h="18" aspect="variable" strokewidth="inherit"><foreground><path><move x="1" y="17"/><curve x1="3" y1="-3" x2="152" y2="-3" x3="154" y3="17"/><close/></path><fillstroke/></foreground></shape>'''


def network():
    doc = Diagram()
    p = doc.page('Home network', width=450, height=680)
    blue, dark, light = '#1678b5', '#145b89', '#b7e2f4'
    label = style(TEXT, fontSize=32, fontStyle=1, fontFamily='Arial')
    equipment = style(BLOCK, rounded=1, arcSize=12, fillColor=blue, strokeColor=dark, strokeWidth=2)
    def part(parent, x,y,w,h, fill, shape='rectangle'):
        return p.node('',x,y,w,h,parent=parent,style=style(equipment,shape=shape,fillColor=fill))
    p.text('Internet',75,40,300,40,style=label)
    globe = p.group(189,100,72,72)
    p.stencil('', GLOBE,0,0,72,72,parent=globe,style=style(BLOCK,fillColor='none',strokeColor=blue,strokeWidth=3))
    router_label = p.text('Router',75,210,300,40,style=label)
    router = p.group(147.5,265,155,80)
    part(router,10,0,4,35,'#111111')
    part(router,141,0,4,35,'#111111')
    part(router,0,25,155,55,blue)
    p.stencil('',ROUTER_TOP,0,25,155,18,parent=router,style=style(equipment,fillColor=blue))
    part(router,3,44,149,32,dark)
    for x in [20,35,50]:
        part(router,x,56,6,6,'#72dd70','ellipse')
    switch_label = p.text('Switch',75,385,300,40,style=label)
    switch = p.group(157,432,136,45)
    part(switch,0,0,136,45,blue)
    for i in range(5):
        part(switch,12+i*24,17,14,12,light)
    monitor = p.group(90,520,70,65)
    part(monitor,0,0,70,45,dark)
    part(monitor,5,5,60,34,light)
    part(monitor,30,45,10,12,dark)
    part(monitor,19,58,32,5,dark)
    laptop = p.group(190,523,70,62)
    part(laptop,4,0,62,42,dark)
    part(laptop,9,5,52,30,light)
    part(laptop,0,43,70,12,dark,'trapezoid')
    phone = p.group(316,520,38,65)
    part(phone,0,0,38,65,dark)
    part(phone,4,9,30,45,light)
    part(phone,13,4,12,2,light)
    part(phone,16,57,6,5,light,'ellipse')
    # Bound group endpoints; straight edges keep branches outside icon interiors.
    arrow = style(EDGE,edgeStyle='none',strokeColor='#000000',strokeWidth=2)
    p.edge(globe,router_label,exit=(.5,1),entry=(.5,0),style=arrow)
    p.edge(router,switch_label,exit=(.5,1),entry=(.5,0),style=arrow)
    for device, sx in [(monitor,.15),(laptop,.5),(phone,.85)]:
        p.edge(switch,device,exit=(sx,1),entry=(.5,0),style=style(arrow,endArrow='none'))
    p.text('Devices',75,600,300,45,style=label)
    return doc


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', default=Path(tempfile.gettempdir()) / 'drawio-demo')
    parser.add_argument('--rows',type=int,default=4)
    parser.add_argument('--cols',type=int,default=4)
    parser.add_argument('--width',type=int,default=128,help='Link width in bits')
    args = parser.parse_args()
    if min(args.rows,args.cols,args.width) < 1:
        parser.error('Rows, columns and width must be positive')
    for name,doc in [('mesh',mesh(args.rows,args.cols,args.width)),('cpu',cpu()),('axi_test_system',axi()),('network',network())]:
        path = doc.save(Path(args.output_dir)/(name+'.drawio'))
        print(path)


if __name__ == '__main__':
    main()
