"""Editable Draw.io construction and preservation. Python 3.9+, standard library only."""
import argparse
import base64
import copy
import json
import math
import os
from pathlib import Path
import shutil
import struct
import subprocess
import tempfile
import urllib.parse
import xml.etree.ElementTree as ET
import zlib


def style(base=None, **values):
    """Merge native style strings/dicts; retain named styles and unknown keys."""
    entries = {}
    if isinstance(base, str):
        for item in base.split(';'):
            if item:
                key, sep, value = item.partition('=')
                entries[key] = value if sep else None
    elif base:
        entries.update(base)
    misplaced = {'exit', 'entry', 'waypoints', 'source_point', 'target_point', 'label_position', 'label_offset', 'routing'} & values.keys()
    if misplaced:
        raise ValueError('Pass ' + ', '.join(sorted(misplaced)) + ' to p.edge(...), not style(...); native anchors are exitX/exitY and entryX/entryY')
    entries.update(values)
    return ''.join(str(k) + ('' if v is None else '=' + str(int(v) if isinstance(v, bool) else v)) + ';' for k, v in entries.items())


BLOCK = 'rounded=0;whiteSpace=wrap;html=0;fillColor=#dae8fc;strokeColor=#6c8ebf;fontSize=14;'
EDGE = 'edgeStyle=orthogonalEdgeStyle;rounded=0;html=0;endArrow=block;strokeColor=#333333;fontSize=12;'
TEXT = 'text;html=0;strokeColor=none;fillColor=none;whiteSpace=wrap;align=center;verticalAlign=middle;fontSize=14;'
CONTAINER = 'swimlane;html=0;startSize=30;horizontal=1;fillColor=#f5f5f5;strokeColor=#666666;collapsible=0;align=center;verticalAlign=top;'
SIDES = {'N': (.5, 0), 'E': (1, .5), 'S': (.5, 1), 'W': (0, .5)}


def _styles(text):
    return dict(item.split('=', 1) if '=' in item else (item, None) for item in (text or '').split(';') if item)


def _pretty_xml(element, level=0):
    # Format element-only content; preserve mixed content and xml:space subtrees.
    if element.get('{http://www.w3.org/XML/1998/namespace}space') == 'preserve':
        return
    if not len(element) or (element.text and element.text.strip()) or any(child.tail and child.tail.strip() for child in element):
        return
    element.text = '\n' + '  ' * (level + 1)
    for child in element:
        _pretty_xml(child, level + 1)
        child.tail = '\n' + '  ' * (level + 1)
    element[-1].tail = '\n' + '  ' * level



def _xml(text):
    parser = ET.XMLParser(target=ET.TreeBuilder(insert_comments=True))
    return ET.fromstring(text, parser=parser)


def _number(value):
    value = float(value)
    if not math.isfinite(value):
        raise ValueError('Geometry must be finite')
    return str(int(value)) if value.is_integer() else str(value)


class Page:
    def __init__(self, diagram, model):
        self.diagram, self.model = diagram, model
        self.root = model.find('root')
        if self.root is None:
            raise ValueError('mxGraphModel has no root')

    def cells(self):
        """Map effective IDs to mxCells (including object/UserObject wrappers)."""
        result = {}
        for child in self.root:
            cell = child if child.tag == 'mxCell' else child.find('mxCell')
            if cell is not None:
                ident = child.get('id', cell.get('id'))
                result[ident] = cell
        return result

    def cell(self, ident):
        return self.cells()[str(ident)]

    def _id(self, ident):
        ids = self.cells()
        if ident is not None:
            ident = str(ident)
            if ident in ids:
                raise ValueError('Duplicate cell ID: ' + ident)
            return ident
        n = 2
        while 'c' + str(n) in ids:
            n += 1
        return 'c' + str(n)

    def _add(self, attrs, ident=None, metadata=None):
        ident = self._id(ident)
        attrs = {k: str(v) for k, v in attrs.items() if v is not None}
        if metadata is None:
            cell = ET.SubElement(self.root, 'mxCell', dict(attrs, id=ident))
        else:
            wrapper = ET.SubElement(self.root, 'object', dict({str(k): str(v) for k, v in metadata.items()}, id=ident, label=attrs.pop('value', '')))
            cell = ET.SubElement(wrapper, 'mxCell', attrs)
        return ident, cell

    def layer(self, name, *, id=None, visible=True, locked=False):
        ident, cell = self._add({'parent': '0', 'value': name, 'visible': int(visible), 'style': style(locked=locked)}, id)
        return ident

    def node(self, label, x, y, width=120, height=60, *, id=None, parent='1', style=BLOCK, metadata=None, **attrs):
        if width < 0 or height < 0:
            raise ValueError('Negative size')
        geometry = {'x': _number(x), 'y': _number(y), 'width': _number(width), 'height': _number(height), 'as': 'geometry'}
        ident, cell = self._add(dict(attrs, value=label, vertex='1', parent=parent, style=globals()['style'](style)), id, metadata)
        ET.SubElement(cell, 'mxGeometry', geometry)
        return ident

    def text(self, label, x, y, width=120, height=30, *, style=TEXT, **kwargs):
        return self.node(label, x, y, width, height, style=style, **kwargs)

    def group(self, x, y, width, height, *, parent='1', id=None):
        return self.node('', x, y, width, height, parent=parent, id=id, style='group;')

    def container(self, label, x, y, width, height, *, style=None, **kwargs):
        return self.node(label, x, y, width, height, style=globals()['style'](CONTAINER, **_styles(globals()['style'](style))), **kwargs)

    def port(self, parent, name, x, y, *, size=8, id=None, style=None):
        """Relative location x/y in [0,1], offset centered on boundary."""
        if not (0 <= x <= 1 and 0 <= y <= 1):
            raise ValueError('Port coordinates must be in [0,1]')
        ident = self.node(name, x, y, size, size, parent=parent, id=id, style=style or 'ellipse;html=0;fillColor=#ffffff;strokeColor=#666666;fontSize=10;labelPosition=center;verticalLabelPosition=top;')
        geo = self.cell(ident).find('mxGeometry')
        geo.set('relative', '1')
        ET.SubElement(geo, 'mxPoint', {'x': _number(-size / 2), 'y': _number(-size / 2), 'as': 'offset'})
        return ident

    def edge(self, source=None, target=None, label='', *, id=None, parent='1', style=EDGE, waypoints=(), source_point=None, target_point=None, exit=None, entry=None, metadata=None, routing='auto', label_position=0, label_offset=(0, 0), **attrs):
        if routing not in ('auto', 'manual'):
            raise ValueError("routing must be 'auto' or 'manual'")
        if routing == 'manual':
            style = globals()['style'](style, edgeStyle='none', noEdgeStyle=1)
        for anchor in (exit, entry):
            if anchor is not None and (len(anchor) != 2 or not all(0 <= v <= 1 for v in anchor)):
                raise ValueError('Entry/exit anchors must be pairs of fractions in [0,1]')
        # Build geometry before adding a cell so bad coordinates do not leave debris.
        geo = ET.Element('mxGeometry', {'relative': '1', 'as': 'geometry'})
        if not -1 <= label_position <= 1:
            raise ValueError('label_position must be in [-1,1]')
        if label_position:
            geo.set('x', _number(label_position))
        if label_offset != (0, 0):
            ET.SubElement(geo, 'mxPoint', {'x': _number(label_offset[0]), 'y': _number(label_offset[1]), 'as': 'offset'})
        if exit is not None:
            style = globals()['style'](style, exitX=exit[0], exitY=exit[1], exitDx=0, exitDy=0, exitPerimeter=0)
        if entry is not None:
            style = globals()['style'](style, entryX=entry[0], entryY=entry[1], entryDx=0, entryDy=0, entryPerimeter=0)
        for point, name in ((source_point, 'sourcePoint'), (target_point, 'targetPoint')):
            if point is not None:
                ET.SubElement(geo, 'mxPoint', {'x': _number(point[0]), 'y': _number(point[1]), 'as': name})
        if waypoints:
            array = ET.SubElement(geo, 'Array', {'as': 'points'})
            for x, y in waypoints:
                ET.SubElement(array, 'mxPoint', {'x': _number(x), 'y': _number(y)})
        ident, cell = self._add(dict(attrs, edge='1', parent=parent, source=source, target=target, value=label, style=globals()['style'](style)), id, metadata)
        cell.append(geo)
        return ident

    def edge_label(self, edge, label, *, position=0, offset=(0, 0), id=None, style=TEXT):
        ident = self.node(label, position, 0, 0, 0, parent=edge, id=id, style=style)
        geo = self.cell(ident).find('mxGeometry')
        geo.set('relative', '1')
        ET.SubElement(geo, 'mxPoint', {'x': _number(offset[0]), 'y': _number(offset[1]), 'as': 'offset'})
        return ident

    def stencil(self, label, stencil_xml, x, y, width, height, **kwargs):
        """Embed native mxStencil XML, not a bitmap."""
        if _xml(stencil_xml).tag != 'shape':
            raise ValueError('Stencil must have a shape root')
        compressed = zlib.compress(urllib.parse.quote(stencil_xml, safe="~()*!.'").encode())[2:-4]
        encoded = base64.b64encode(compressed).decode()
        native_style = globals()['style'](kwargs.pop('style', BLOCK), shape='stencil(' + encoded + ')')
        return self.node(label, x, y, width, height, style=native_style, **kwargs)

    def set_label(self, ident, label):
        cell = self.cell(ident)
        for child in self.root:
            if child is cell:
                cell.set('value', label)
                return
            if child.find('mxCell') is cell:
                child.set('label', label)
                return

    def set_style(self, ident, **values):
        cell = self.cell(ident)
        cell.set('style', style(cell.get('style'), **values))

    def move(self, ident, x, y, width=None, height=None):
        geo = self.cell(ident).find('mxGeometry')
        if geo is None:
            raise ValueError('Cell has no geometry')
        for k, v in [('x', x), ('y', y), ('width', width), ('height', height)]:
            if v is not None:
                geo.set(k, _number(v))


    def label(self, ident):
        """Read an editable label from a bare cell or metadata wrapper."""
        cell = self.cell(ident)
        for child in self.root:
            if child is cell:
                return cell.get('value', '')
            if child.find('mxCell') is cell:
                return child.get('label', cell.get('value', ''))
        return ''

    def bounds(self, ident, *, relative_to='1'):
        """Unrotated (x,y,width,height) in a layer/container coordinate system."""
        cells = self.cells()
        def absolute(key, seen):
            if key in seen:
                raise ValueError('Parent cycle while computing bounds: ' + key)
            cell = cells[key]
            if cell.get('edge') == '1':
                raise ValueError('Edge geometry is not a rectangle')
            geo = cell.find('mxGeometry')
            if geo is None:
                return (0., 0., 0., 0.)  # root/layer origin
            if float(_styles(cell.get('style')).get('rotation', 0)):
                raise ValueError('Bounds helper does not support rotated cells')
            x, y, w, h = [float(geo.get(k, 0)) for k in ('x', 'y', 'width', 'height')]
            parent = cell.get('parent')
            if parent in cells:
                px, py, pw, ph = absolute(parent, seen | {key})
                if geo.get('relative') == '1':
                    x, y = x * pw, y * ph
                    offset = geo.find("mxPoint[@as='offset']")
                    if offset is not None:
                        x += float(offset.get('x', 0)); y += float(offset.get('y', 0))
                x += px; y += py
            return x, y, w, h
        x, y, w, h = absolute(str(ident), set())
        ox, oy, _, _ = absolute(str(relative_to), set())
        return x - ox, y - oy, w, h

    def point(self, ident, side='E', *, fraction=.5, relative_to='1'):
        """Named side attachment in the edge parent's coordinates."""
        if side not in SIDES or not 0 <= fraction <= 1:
            raise ValueError('Side must be N/E/S/W; fraction must be in [0,1]')
        x, y, w, h = self.bounds(ident, relative_to=relative_to)
        fx, fy = SIDES[side]
        if side in ('N', 'S'):
            fx = fraction
        else:
            fy = fraction
        return x + fx*w, y + fy*h

    def connect(self, source, target, label='', *, source_side='E', target_side='W',
                via=None, lane=None, source_fraction=.5, target_fraction=.5, label_segment=None, parent='1', style=EDGE, **kwargs):
        """Bound, deterministic orthogonal polyline. No obstacle autorouting."""
        if source_side not in SIDES or target_side not in SIDES:
            raise ValueError('Sides must be N/E/S/W')
        if via is not None and lane is not None:
            raise ValueError('Choose via corners or a lane, not both')
        a = self.point(source, source_side, fraction=source_fraction, relative_to=parent)
        b = self.point(target, target_side, fraction=target_fraction, relative_to=parent)
        if via is None:
            horizontal_a = source_side in ('E','W')
            horizontal_b = target_side in ('E','W')
            if horizontal_a and horizontal_b:
                if lane is None:
                    lane = ((a[0]+b[0])/2 if source_side != target_side else
                            max(a[0],b[0])+30 if source_side=='E' else min(a[0],b[0])-30)
                via = [(lane,a[1]),(lane,b[1])]
            elif not horizontal_a and not horizontal_b:
                if lane is None:
                    lane = ((a[1]+b[1])/2 if source_side != target_side else
                            max(a[1],b[1])+30 if source_side=='S' else min(a[1],b[1])-30)
                via = [(a[0],lane),(b[0],lane)]
            else:
                if lane is not None:
                    raise ValueError('A lane requires both sides to be horizontal or both vertical')
                via = [(b[0],a[1])] if horizontal_a else [(a[0],b[1])]
        points = [a] + [tuple(float(_number(v)) for v in point) for point in via] + [b]
        points = [point for i,point in enumerate(points) if i==0 or point != points[i-1]]
        for start,end in zip(points,points[1:]):
            if start[0] != end[0] and start[1] != end[1]:
                raise ValueError('Diagonal segment in connect(): supply every orthogonal corner in via')
        if len(points) < 2:
            raise ValueError('Connection has no length')
        directions = {'E':(1,0),'W':(-1,0),'N':(0,-1),'S':(0,1)}
        for start,end,direction in [(points[0],points[1],directions[source_side]),
                                    (points[-1],points[-2],directions[target_side])]:
            dx,dy = end[0]-start[0],end[1]-start[1]
            if dx*direction[0]+dy*direction[1] <= 0:
                raise ValueError('Route must leave/enter the selected side outward; supply via corners around endpoints')
        if label_segment is not None:
            if 'label_position' in kwargs:
                raise ValueError('Choose label_segment or label_position, not both')
            lengths = [abs(end[0]-start[0])+abs(end[1]-start[1]) for start,end in zip(points,points[1:])]
            if not isinstance(label_segment,int) or not 0 <= label_segment < len(lengths):
                raise ValueError('label_segment must index a nonzero path segment')
            kwargs['label_position'] = 2*(sum(lengths[:label_segment])+lengths[label_segment]/2)/sum(lengths)-1
        def attachment(side,fraction):
            fx,fy = SIDES[side]
            return (fraction,fy) if side in ('N','S') else (fx,fraction)
        return self.edge(source,target,label,parent=parent,style=style,
                         exit=attachment(source_side,source_fraction),entry=attachment(target_side,target_fraction),
                         waypoints=points[1:-1],routing='manual',**kwargs)

    def table(self, title, rows, x, y, *, width=280, row_height=26, header_height=32,
              key_width=44, id=None, parent='1', style=None, header_style=None, text_style=None):
        """Generic editable two-column record/table; rows are strings or (key,text)."""
        rows = [('',row) if isinstance(row,str) else tuple(row) for row in rows]
        if any(len(row) != 2 for row in rows):
            raise ValueError('Table rows must be strings or (key, text) pairs')
        if min(row_height, header_height) <= 0 or not 0 < key_width < width:
            raise ValueError('Invalid table dimensions')
        height = header_height + row_height*len(rows) + 4
        group = self.group(x,y,width,height,id=id,parent=parent)
        body = globals()['style'](BLOCK,rounded=1,fillColor='#ffffff',strokeColor='#333333',fontSize=13)
        self.node('',0,0,width,height,parent=group,id=group+':body',style=globals()['style'](body,**_styles(globals()['style'](style))),connectable=0)
        heading = globals()['style'](BLOCK,rounded=0,fillColor='#333333',strokeColor='none',fontColor='#ffffff',fontStyle=1,fontSize=14)
        self.node(title,2,2,width-4,header_height-2,parent=group,id=group+':header',style=globals()['style'](heading,**_styles(globals()['style'](header_style))),connectable=0)
        field_style = globals()['style'](TEXT,align='left',fontSize=13,spacingLeft=6)
        field_style = globals()['style'](field_style,**_styles(globals()['style'](text_style)))
        for i,(key,value) in enumerate(rows):
            row_y = header_height+i*row_height
            self.text(str(key),2,row_y,key_width-2,row_height,parent=group,id=group+':key:'+str(i),style=field_style,connectable=0)
            self.text(str(value),key_width,row_y,width-key_width-2,row_height,parent=group,id=group+':row:'+str(i),style=field_style,connectable=0)
        return group

    def connections(self, *, include_loose=False):
        """Topology by ID, with both main and child edge labels, no root/label vertices."""
        cells = self.cells()
        result = []
        for ident,cell in cells.items():
            if cell.get('edge') == '1' and (include_loose or cell.get('source') is not None or cell.get('target') is not None):
                labels = [self.label(ident)] + [self.label(k) for k,c in cells.items() if c.get('parent')==ident and c.get('vertex')=='1']
                result.append({'id':ident,'source':cell.get('source'),'target':cell.get('target'),
                               'label':' '.join(' '.join(label.split()) for label in labels if label)})
        return result

    def assert_connections(self, expected, *, exact=True):
        """Check (source ID,target ID,label) triples, including parallel-edge counts."""
        from collections import Counter
        actual = Counter((c['source'],c['target'],c['label']) for c in self.connections())
        required = Counter((str(a),str(b),' '.join(label.split())) for a,b,label in expected)
        missing = required - actual
        extra = actual - required if exact else Counter()
        if missing or extra:
            raise ValueError('Topology mismatch: missing=' + repr(dict(missing)) + '; unexpected=' + repr(dict(extra)))

    def label_warnings(self):
        """Estimated plain-text manual-edge label collisions; font metrics are approximate."""
        cells, warnings, labels = self.cells(), [], []
        for ident,cell in cells.items():
            if cell.get('edge') != '1': continue
            values = _styles(cell.get('style'))
            if values.get('noEdgeStyle') != '1' or values.get('curved') == '1': continue
            geo = cell.find('mxGeometry')
            if geo is None: continue
            parent = cell.get('parent'); endpoints=[]
            try:
                ox,oy,_,_ = self.bounds(parent)
                for terminal,prefix in [('source','exit'),('target','entry')]:
                    ref = cell.get(terminal)
                    if ref is None:
                        point=geo.find("mxPoint[@as='"+terminal+"Point']")
                        if point is None: break
                        endpoints.append((float(point.get('x',0))+ox,float(point.get('y',0))+oy))
                    else:
                        if values.get(prefix+'Perimeter') != '0' or prefix+'X' not in values or prefix+'Y' not in values: break
                        x,y,w,h=self.bounds(ref)
                        endpoints.append((x+float(values[prefix+'X'])*w,y+float(values[prefix+'Y'])*h))
                if len(endpoints) != 2: continue
                points=[endpoints[0]]+[(float(pt.get('x',0))+ox,float(pt.get('y',0))+oy) for pt in geo.findall("Array[@as='points']/mxPoint")]+[endpoints[1]]
                lengths=[math.hypot(b[0]-a[0],b[1]-a[1]) for a,b in zip(points,points[1:])]
                total=sum(lengths)
                if not total: continue
                candidates=[(ident,cell,geo)]+[(k,c,c.find('mxGeometry')) for k,c in cells.items() if c.get('parent')==ident and c.get('vertex')=='1']
                for label_id,label_cell,label_geo in candidates:
                    text=self.label(label_id); label_style=_styles(label_cell.get('style'))
                    if not text or label_geo is None or label_style.get('html')=='1' or label_style.get('horizontal')=='0': continue
                    distance=(float(label_geo.get('x',0))+1)*total/2
                    for a,b,length in zip(points,points[1:],lengths):
                        if distance <= length and length: break
                        distance-=length
                    fraction=max(0,min(1,distance/length)) if length else 0
                    cx=a[0]+fraction*(b[0]-a[0]); cy=a[1]+fraction*(b[1]-a[1])
                    offset=label_geo.find("mxPoint[@as='offset']")
                    if offset is not None:
                        cx+=float(offset.get('x',0)); cy+=float(offset.get('y',0))
                    font=float(label_style.get('fontSize',12 if label_cell is cell else 14))
                    lines=text.splitlines() or ['']
                    width=max(len(line) for line in lines)*font*.55+4
                    height=len(lines)*font*1.25+4
                    labels.append((label_id,(cx-width/2,cy-height/2,width,height)))
            except (ValueError,KeyError):
                continue  # Unsupported imported geometry is left to native inspection.
        for i,(ident,a) in enumerate(labels):
            x,y,w,h=a
            for other,b in labels[i+1:]:
                xx,yy,ww,hh=b
                if min(x+w,xx+ww)>max(x,xx) and min(y+h,yy+hh)>max(y,yy):
                    warnings.append(ident+' / '+other+': estimated edge-label overlap')
        return warnings

    def layout_warnings(self):
        """Conservative bounds/manual-route checks, never a native rendering proof."""
        cells, warnings, boxes = self.cells(), [], {}
        def ancestors(key):
            result = set()
            while key in cells and key not in result:
                result.add(key); key = cells[key].get('parent')
            return result
        for ident,cell in cells.items():
            if cell.get('vertex') != '1' or cell.get('visible') == '0':
                continue
            geo = cell.find('mxGeometry')
            if geo is None or cells.get(cell.get('parent'),ET.Element('cell')).get('edge')=='1':
                continue
            try:
                bounds = self.bounds(ident)
            except (ValueError,KeyError):
                warnings.append(ident + ': geometry check skipped (unsupported bounds)'); continue
            boxes[ident] = bounds
            parent = cell.get('parent')
            if parent in cells and cells[parent].get('vertex')=='1' and geo.get('relative') != '1':
                px,py,pw,ph = self.bounds(parent)
                bx,by,bw,bh = bounds
                if bx < px or by < py or bx+bw > px+pw or by+bh > py+ph:
                    warnings.append(ident + ': child extends beyond parent ' + parent)
        def solid(ident):
            cell = cells[ident]; values = _styles(cell.get('style'))
            return (cell.get('connectable') != '0' and 'text' not in values
                    and values.get('opacity') != '0' and cell.find('mxGeometry').get('relative') != '1')
        shapes = [k for k in boxes if solid(k)]
        def overlap(a,b):
            x,y,w,h=a; xx,yy,ww,hh=b
            return min(x+w,xx+ww)>max(x,xx)+.1 and min(y+h,yy+hh)>max(y,yy)+.1
        for i,a in enumerate(shapes):
            for b in shapes[i+1:]:
                if cells[a].get('parent')==cells[b].get('parent') and overlap(boxes[a],boxes[b]):
                    warnings.append(a + ' overlaps sibling ' + b)
        for ident,cell in cells.items():
            if cell.get('edge') != '1':
                continue
            values = _styles(cell.get('style'))
            # Auto routes, curves and projected perimeter attachments need native rendering.
            if values.get('noEdgeStyle') != '1' or values.get('curved') == '1':
                continue
            geo = cell.find('mxGeometry')
            if geo is None:
                continue
            parent = cell.get('parent')
            points = []
            for terminal,prefix in [('source','exit'),('target','entry')]:
                ref = cell.get(terminal)
                if ref is None:
                    point = geo.find("mxPoint[@as='"+terminal+"Point']")
                    if point is None: break
                    endpoint = (float(point.get('x',0)),float(point.get('y',0)))
                else:
                    if values.get(prefix+'Perimeter') != '0' or prefix+'X' not in values or prefix+'Y' not in values: break
                    try: x,y,w,h = self.bounds(ref,relative_to=parent)
                    except (ValueError,KeyError): break
                    endpoint = (x+float(values[prefix+'X'])*w,y+float(values[prefix+'Y'])*h)
                points.append(endpoint)
            if len(points) != 2: continue
            points = [points[0]] + [(float(pt.get('x',0)),float(pt.get('y',0))) for pt in geo.findall("Array[@as='points']/mxPoint")] + [points[1]]
            ox,oy,_,_ = self.bounds(parent)
            related = ancestors(cell.get('source')) | ancestors(cell.get('target')) | ancestors(parent)
            for node in shapes:
                if node in related or cell.get('source') in ancestors(node) or cell.get('target') in ancestors(node): continue
                x,y,w,h = boxes[node]
                for (ax,ay),(bx,by) in zip(points,points[1:]):
                    ax+=ox; bx+=ox; ay+=oy; by+=oy
                    if (ax==bx and x<ax<x+w and min(ay,by)<y+h and max(ay,by)>y or
                        ay==by and y<ay<y+h and min(ax,bx)<x+w and max(ax,bx)>x):
                        warnings.append(ident + ': manual route crosses ' + node); break
        return warnings


class Diagram:
    def __init__(self):
        self.xml = ET.Element('mxfile', {'host': 'drawio-python-arch'})
        self.pages = []

    def page(self, name='Page-1', *, width=1100, height=850, id=None, **attrs):
        ident = id or 'page-' + str(len(self.pages) + 1)
        if any(p.diagram.get('id') == ident for p in self.pages):
            raise ValueError('Duplicate page ID')
        diagram = ET.SubElement(self.xml, 'diagram', {'id': ident, 'name': name})
        model = ET.SubElement(diagram, 'mxGraphModel', dict({'dx': '0', 'dy': '0', 'grid': '1', 'gridSize': '10', 'page': '1', 'pageScale': '1', 'pageWidth': _number(width), 'pageHeight': _number(height), 'background': '#ffffff'}, **{k: str(v) for k, v in attrs.items()}))
        root = ET.SubElement(model, 'root')
        ET.SubElement(root, 'mxCell', {'id': '0'})
        ET.SubElement(root, 'mxCell', {'id': '1', 'parent': '0'})
        page = Page(diagram, model)
        self.pages.append(page)
        return page

    @classmethod
    def load(cls, path):
        doc = cls()
        root = _xml(Path(path).read_bytes())
        if root.tag == 'mxGraphModel':
            wrapper = ET.Element('mxfile')
            ET.SubElement(wrapper, 'diagram', {'id': 'page-1', 'name': 'Page-1'}).append(root)
            root = wrapper
        if root.tag != 'mxfile':
            raise ValueError('Expected mxfile or mxGraphModel')
        doc.xml = root
        doc.xml.attrib.pop('compressed', None)
        for diagram in root.findall('diagram'):
            model = diagram.find('mxGraphModel')
            if model is None:
                payload = (diagram.text or '').strip()
                if payload.startswith('<'):
                    model = _xml(payload)
                else:
                    model = _xml(urllib.parse.unquote(zlib.decompress(base64.b64decode(payload), -15).decode()))
                diagram.text = None
                diagram.append(model)
            doc.pages.append(Page(diagram, model))
        return doc

    def validate(self):
        """Structural errors, not layout/semantic correctness; [] means pass."""
        errors = []
        if not self.pages:
            errors.append('No pages')
        page_ids = set()
        for page in self.pages:
            name = page.diagram.get('name', '?')
            def error(message):
                errors.append(name + ': ' + message)
            pid = page.diagram.get('id')
            if pid in page_ids:
                error('duplicate page ID')
            page_ids.add(pid)
            ids, cells = set(), page.cells()
            for child in page.root:
                cell = child if child.tag == 'mxCell' else child.find('mxCell')
                if cell is None:
                    continue
                ident = child.get('id', cell.get('id'))
                if not ident or ident in ids:
                    error('missing/duplicate ID ' + str(ident))
                ids.add(ident)
            if '0' not in cells or cells['0'].get('parent') is not None:
                error('missing/invalid root cell 0')
            for ident, cell in cells.items():
                native_style = _styles(cell.get('style'))
                for misplaced in ('exit', 'entry', 'waypoints', 'source_point', 'target_point'):
                    if misplaced in native_style:
                        error(str(ident) + ': ' + misplaced + ' belongs in p.edge(), not style()')
                parent = cell.get('parent')
                if ident != '0' and parent not in cells:
                    error(str(ident) + ': missing parent ' + str(parent))
                seen = {ident}
                ancestor = parent
                while ancestor in cells:
                    if ancestor in seen:
                        error(str(ident) + ': parent cycle')
                        break
                    seen.add(ancestor)
                    ancestor = cells[ancestor].get('parent')
                if cell.get('edge') == '1' and cell.get('vertex') == '1':
                    error(str(ident) + ': both edge and vertex')
                geo = cell.find('mxGeometry')
                if (cell.get('vertex') == '1' or cell.get('edge') == '1') and geo is None:
                    error(str(ident) + ': missing geometry')
                if geo is not None:
                    for item in geo.iter():
                        for key in ('x', 'y', 'width', 'height'):
                            if key in item.attrib:
                                try:
                                    value = float(item.get(key))
                                    if not math.isfinite(value) or (key in ('width', 'height') and value < 0):
                                        raise ValueError()
                                except ValueError:
                                    error(str(ident) + ': invalid ' + key)
                if cell.get('edge') == '1':
                    for terminal, point in [('source', 'sourcePoint'), ('target', 'targetPoint')]:
                        ref = cell.get(terminal)
                        if ref is not None:
                            if ref not in cells:
                                error(str(ident) + ': dangling ' + terminal)
                            elif cells[ref].get('vertex') != '1':
                                error(str(ident) + ': terminal is not a vertex')
                        elif geo is None or geo.find("mxPoint[@as='" + point + "']") is None:
                            error(str(ident) + ': missing ' + terminal + ' or point')
        return errors

    def save(self, path, *, validate=True, pretty=True):
        errors = self.validate() if validate else []
        if errors:
            raise ValueError('\n'.join(errors))
        tree = copy.deepcopy(self.xml)
        if pretty:
            _pretty_xml(tree)
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        # Atomic write; never truncate a previous diagram on validation failure.
        fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix='.drawio')
        try:
            with os.fdopen(fd, 'wb') as output:
                ET.ElementTree(tree).write(output, encoding='utf-8', xml_declaration=True)
                output.write(b'\n')
            os.replace(tmp, path)
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)
        return path


def _is_snap_executable(executable):
    """Recognize both Snap app binaries and symlinks to the Snap launcher."""
    path = Path(executable).absolute()
    resolved = path.resolve()
    # /snap/bin/drawio commonly resolves to /usr/bin/snap, not the app binary.
    return (str(path).startswith('/snap/') or str(resolved).startswith('/snap/')
            or resolved.name == 'snap')


def _check_snap_export_paths(source, output):
    home = Path.home().resolve()
    blocked = []
    for label, path in (('source', source), ('output', output)):
        try:
            relative = path.relative_to(home)
        except ValueError:
            blocked.append(label + ' is outside $HOME: ' + str(path))
        else:
            if any(part.startswith('.') for part in relative.parts):
                blocked.append(label + ' uses a hidden path: ' + str(path))
    if blocked:
        raise RuntimeError('Snap Draw.io cannot access these export paths: ' + '; '.join(blocked) + '. '
                           f'Copy sources and keep outputs in a non-hidden directory under $HOME ({home}), '
                           'such as $HOME/drawio-work. Snap has a private /tmp; '
                           'host /tmp files are not accessible. Use the .deb installation for unconfined export.')


def _export_failure(result):
    """Keep the first useful error instead of a tail dominated by GPU logs."""
    noise = ('egl driver message', 'egl_not_initialized', 'eglinitialize', 'libegl',
             'angle display::initialize', 'angle platform', 'gl_display.cc',
             'gl_surface_egl', 'gpu process exited', 'exiting gpu process',
             'could not open the default x display')
    lines = []
    for line in (result.stdout + '\n' + result.stderr).splitlines():
        line = line.strip()
        if line and not any(marker in line.lower() for marker in noise):
            lines.append(line)
    for line in lines:
        if any(marker in line.lower() for marker in ('error', 'failed', 'not found', 'denied')):
            return line[:2000]
    if lines:
        return '\n'.join(lines)[:2000]
    return (f'No actionable renderer output (exit code {result.returncode}); no PNG was produced. '
            'Check source/output access and the display or --headless setup.')


def export_png(source, output, *, page=0, scale=1, border=10, executable='drawio', headless=False, timeout=60, extra_args=()):
    """Native renderer; Draw.io Desktop is an optional external application."""
    if page < 0 or scale <= 0 or border < 0:
        raise ValueError('Invalid export options')
    source, output = Path(source).resolve(), Path(output).resolve()
    renderer = shutil.which(executable)
    if not renderer:
        raise RuntimeError('Native PNG export requires Draw.io Desktop on PATH (generation does not)')
    if _is_snap_executable(renderer):
        _check_snap_export_paths(source, output)
    if page >= len(Diagram.load(source).pages):
        raise ValueError('Page index out of range')
    if source == output:
        raise ValueError('Export must not overwrite source')
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=str(output.parent)) as directory:
        temporary = Path(directory) / 'render.png'
        cmd = [executable, '--export', '--format', 'png', '--page-index', str(page + 1), '--scale', str(scale), '--border', str(border), '--output', str(temporary)] + list(extra_args) + [str(source)]
        if headless:
            if not shutil.which('xvfb-run'):
                raise RuntimeError('Headless native export requires xvfb-run')
            cmd = ['xvfb-run', '-a'] + cmd
        env = dict(os.environ, DRAWIO_DISABLE_UPDATE='true')
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, env=env)
        if result.returncode or not temporary.exists():
            raise RuntimeError('Native export failed: ' + _export_failure(result))
        data = temporary.read_bytes()
        if len(data) < 24 or data[:8] != b'\x89PNG\r\n\x1a\n':
            raise RuntimeError('Renderer did not produce PNG')
        width, height = struct.unpack('>II', data[16:24])
        if not width or not height:
            raise RuntimeError('Empty PNG')
        os.replace(temporary, output)
        return width, height


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    validate = commands.add_parser('validate')
    validate.add_argument('source')
    inspect = commands.add_parser('inspect', help='Topology and conservative layout warnings (no renderer)')
    inspect.add_argument('source')
    from drawio_native import add_arguments, run as run_native_check
    add_arguments(commands.add_parser('native-check', help='Optional offline rendered label collision report (requires Draw.io assets and Chromium)'))
    from drawio_fix import add_arguments as add_fix_arguments, run as run_native_fix
    add_fix_arguments(commands.add_parser('native-fix', help='Conservative label-offset repair; verified dry-run unless --output is supplied'))
    from drawio_stack import add_arguments as add_stack_arguments, run as run_native_stack_fix
    add_stack_arguments(commands.add_parser('native-stack-fix', help='Independent stacking-only repair for hidden labels; dry-run by default'))
    export = commands.add_parser('export')
    export.add_argument('source')
    export.add_argument('output')
    export.add_argument('--page', type=int, default=0)
    export.add_argument('--scale', type=float, default=1)
    export.add_argument('--border', type=int, default=10)
    export.add_argument('--headless', action='store_true')
    export.add_argument('--executable', default='drawio')
    assets = export.add_mutually_exclusive_group()
    for flag in ('--drawio-asar', '--drawio-webapp'):
        assets.add_argument(flag, help='Accepted for CLI compatibility; PNG export uses '
                            '--executable and ignores this asset path')
    export.add_argument('--no-sandbox', action='store_true', help='Pass Electron flag only where required by the environment')
    args = parser.parse_args()
    if args.command == 'native-check':
        return run_native_check(args)
    if args.command == 'native-fix':
        return run_native_fix(args)
    if args.command == 'native-stack-fix':
        return run_native_stack_fix(args)
    if args.command == 'validate':
        errors = Diagram.load(args.source).validate()
        print('\n'.join(errors) if errors else 'Structural validation passed')
        return bool(errors)
    if args.command == 'inspect':
        doc = Diagram.load(args.source)
        errors = doc.validate()
        if errors:
            print('\n'.join(errors)); return 1
        for page in doc.pages:
            edges = page.connections()
            print(json.dumps({'page': page.diagram.get('name'), 'connections': edges, 'layout_warnings': page.layout_warnings(), 'estimated_label_warnings': page.label_warnings()}, indent=2, ensure_ascii=False))
        print('Bounds/manual routes checked; label overlaps estimated with approximate fonts. Native autoroutes, text fitting and symbols still need inspection.')
        return 0
    print(export_png(args.source, args.output, page=args.page, scale=args.scale, border=args.border, headless=args.headless, executable=args.executable, extra_args=['--no-sandbox'] if args.no_sandbox else ()))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
