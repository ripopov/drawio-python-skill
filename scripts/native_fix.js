/* Bounded, offset-only search in the installed native renderer. No XML serialization. */
function nativeFixPage(graph, inspect, before, options) {
    const model = graph.getModel(), maxMove = options.max_move;
    const original = new Map(before.labels.map(l => [l.id, l]));
    const routes = new Map(before.routes.map(r => [r.id, r]));
    const changes = new Map(), skipped = new Map();
    const geometries = new Map();
    let current = before, attempts = 0;
    const receipt = {before, changes: [], skipped: [], attempts: 0, passes: 0, stop_reason: 'no-improvement'};
    const warnings = r => r.collisions.filter(c => c.severity === 'warning').length;
    const key = c => JSON.stringify([c.type, ...[c.a, c.b].sort()]);
    const severity = {info: 0, advisory: 1, warning: 2};
    const center = b => ({x: b.x + b.width / 2, y: b.y + b.height / 2});
    const contains = (a, b) => b.x >= a.x && b.y >= a.y &&
        b.x + b.width <= a.x + a.width && b.y + b.height <= a.y + a.height;
    const overlap = (a, b) => a.x < b.x + b.width && b.x < a.x + a.width &&
        a.y < b.y + b.height && b.y < a.y + a.height;
    function segmentBox(a, b, box, pad = 1) {
        let lo = 0, hi = 1;
        for (const [v, d, min, max] of [
            [a.x, b.x-a.x, box.x-pad, box.x+box.width+pad],
            [a.y, b.y-a.y, box.y-pad, box.y+box.height+pad]]) {
            if (Math.abs(d) < 1e-9) { if (v < min || v > max) return false; }
            else {
                const t1 = (min-v)/d, t2 = (max-v)/d;
                lo = Math.max(lo, Math.min(t1,t2)); hi = Math.min(hi, Math.max(t1,t2));
                if (lo > hi) return false;
            }
        }
        return true;
    }
    function carrier(route, box) {
        const c = center(box);
        const result = [];
        for (let i=1; i<route.points.length; i++) {
            const a = route.points[i-1], b = route.points[i], dx=b.x-a.x, dy=b.y-a.y;
            const length2 = dx*dx + dy*dy;
            if (length2 < 1e-9) continue;
            const t = Math.max(0, Math.min(1, ((c.x-a.x)*dx+(c.y-a.y)*dy)/length2));
            const distance = Math.hypot(c.x-a.x-t*dx, c.y-a.y-t*dy);
            const side = ((c.x-a.x)*dy-(c.y-a.y)*dx) / Math.sqrt(length2);
            result.push({index: i-1, distance, side, dx, dy});
        }
        result.sort((a,b) => a.distance-b.distance || a.index-b.index);
        return result[0];
    }
    function ancestors(id) {
        const ids = new Set();
        for (let c=model.getParent(model.getCell(id)); c; c=model.getParent(c)) ids.add(c.id);
        return ids;
    }
    function locked(cell) {
        for (let c=cell; c; c=model.getParent(c)) {
            const s = graph.getCellStyle(c) || {};
            if (s.locked == 1 || s.movable == 0 || s.labelMovable == 0 || s.autofix == 0) return true;
        }
        return false;
    }
    function eligible(label) {
        const cell=model.getCell(label.id), geo=model.getGeometry(cell), s=graph.getCellStyle(cell) || {};
        if (!label.edge) return 'node-label';
        if (options.only.length && !options.only.includes(label.id)) return 'not-selected';
        if (options.keep.includes(label.id) || options.keep.includes(label.edge) || locked(cell)) return 'locked';
        if (label.id !== label.edge && (model.getParent(cell).id !== label.edge ||
            geo.width !== 0 || geo.height !== 0 || model.getChildCount(cell))) return 'non-text-edge-child';
        if (!geo.relative || (geo.offset && ![geo.offset.x,geo.offset.y].every(Number.isFinite))) return 'unsupported-geometry';
        if (s.rotation && Number(s.rotation) !== 0 || s.horizontal == 0 || s.textRotation && Number(s.textRotation) !== 0 ||
            s.labelPosition && s.labelPosition !== 'center' || s.verticalLabelPosition && s.verticalLabelPosition !== 'middle') return 'unsupported-text-transform';
        if (s.textDirection === 'rtl' || /<\s*(img|svg|math)\b|\$\$/i.test(label.text)) return 'unsupported-rich-label';
        const route=routes.get(label.edge);
        if (!route || !route.supported || !carrier(route,label.bounds)) return 'unsupported-route';
        // Sized child cells can carry ports or structure. Moving any label with descendants is unsafe.
        if (model.getChildCount(cell)) return 'label-has-children';
        return null;
    }
    function guard(label, box) {
        const old = original.get(label.id).bounds, own=routes.get(label.edge);
        const c0=carrier(own,old), c1=carrier(own,box);
        if (c0.index !== c1.index) return false;
        // Keep an established side of the connection, and stay close to the same carrier segment.
        if (Math.abs(c0.side)>3 && c0.side*c1.side < -1e-6) return false;
        const half = (Math.abs(c0.dy)*box.width + Math.abs(c0.dx)*box.height) /
            (2*Math.hypot(c0.dx,c0.dy));
        if (c1.distance > Math.max(c0.distance,half+12)+.01) return false;
        const parents=ancestors(label.edge);
        for (const obstacle of before.obstacles) {
            if (parents.has(obstacle.id)) {
                if (contains(obstacle.bounds,old) && !contains(obstacle.bounds,box)) return false;
            } else if (overlap(box,obstacle.bounds) && !overlap(old,obstacle.bounds)) return false;
        }
        for (const route of routes.values()) {
            for (let i=1;i<route.points.length;i++) {
                if (route.id === label.edge && i-1 === c0.index) continue;
                const a=route.points[i-1],b=route.points[i];
                if (segmentBox(a,b,box) && !segmentBox(a,b,old)) return false;
                // Do not hop across another connector while moving between two clear positions.
                const swept={x:Math.min(old.x,box.x),y:Math.min(old.y,box.y),
                    width:Math.max(old.x+old.width,box.x+box.width)-Math.min(old.x,box.x),
                    height:Math.max(old.y+old.height,box.y+box.height)-Math.min(old.y,box.y)};
                if (segmentBox(a,b,swept) && !segmentBox(a,b,old)) return false;
            }
            if (route.id !== label.edge) {
                const other0=carrier(route,old),other1=carrier(route,box);
                if (other0 && other1 && other0.distance >= c0.distance-.1 && other1.distance < c1.distance-.1) return false;
            }
        }
        return true;
    }
    function noRegression(next, previous) {
        if (next.unmeasured_labels.length || next.labels.length !== before.labels.length ||
            JSON.stringify(next.routes) !== JSON.stringify(before.routes)) return false;
        const known = new Map(previous.collisions.map(c => [key(c),severity[c.severity]]));
        return next.collisions.every(c => known.has(key(c)) && severity[c.severity] <= known.get(key(c)));
    }
    function setOffset(id, offset) {
        const geo=geometries.get(id).clone();
        geo.offset = new mxPoint(offset[0], offset[1]);
        model.setGeometry(model.getCell(id), geo);
        graph.getView().validate();
    }
    function candidates(label, snapshot) {
        const b=label.bounds, base=original.get(label.id).bounds;
        const geo=geometries.get(label.id), origin=[geo.offset ? geo.offset.x:0,geo.offset ? geo.offset.y:0];
        const c=carrier(routes.get(label.edge),base), length=Math.hypot(c.dx,c.dy);
        const directions=[[0,-1],[0,1],[-1,0],[1,0],[-c.dy/length,c.dx/length],[c.dy/length,-c.dx/length]];
        const result=[];
        function add(dx,dy) {
            const x=Math.round((b.x-base.x+dx)*1000)/1000, y=Math.round((b.y-base.y+dy)*1000)/1000;
            if (Math.hypot(x,y)>maxMove+.001 || Math.hypot(x,y)<.01) return;
            const box={...base,x:base.x+x,y:base.y+y};
            if (guard(label,box)) result.push({offset:[origin[0]+x,origin[1]+y],move:Math.hypot(x,y),box});
        }
        // Clearance-derived displacements resolve small conflicts without coarse grid jumps.
        for (const finding of snapshot.collisions) {
            if (finding.a !== label.id && finding.b !== label.id) continue;
            const other = finding.type === 'label-label' ? snapshot.labels.find(l=>l.id===(finding.a===label.id?finding.b:finding.a)) :
                snapshot.obstacles.find(s=>s.id===finding.b);
            if (!other) continue;
            const r=other.bounds,pad=nativeCheckInput.padding+1;
            add(0,r.y-b.y-b.height-pad); add(0,r.y+r.height-b.y+pad);
            add(r.x-b.x-b.width-pad,0); add(r.x+r.width-b.x+pad,0);
        }
        for (const distance of [4,8,12,16,24,32,maxMove]) for (const [x,y] of directions) add(x*distance,y*distance);
        const unique=new Map(result.map(c=>[JSON.stringify(c.offset),c]));
        return [...unique.values()].sort((a,b)=>a.move-b.move || a.offset[0]-b.offset[0] || a.offset[1]-b.offset[1]).slice(0,24);
    }
    if (before.unmeasured_labels.length || before.routes.some(r=>!r.supported)) {
        receipt.stop_reason = before.unmeasured_labels.length ? 'incomplete-measurement' : 'unsupported-route-on-page';
        return receipt;
    }
    const affected=new Set(before.collisions.filter(c=>c.severity==='warning').flatMap(c=>[c.a,c.b]));
    for (const label of before.labels) {
        const reason=eligible(label);
        if (reason && affected.has(label.id)) skipped.set(label.id,reason);
        if (!reason) geometries.set(label.id,model.getGeometry(model.getCell(label.id)).clone());
    }
    function evaluate(moves) {
        if (attempts >= options.max_attempts) return null;
        attempts++;
        const saved=moves.map(([label])=>model.getGeometry(model.getCell(label.id)).clone());
        try {
            for (const [label,candidate] of moves) setOffset(label.id,candidate.offset);
            const next=inspect();
            const valid=moves.every(([label,candidate])=> {
                const rendered=next.labels.find(l=>l.id===label.id), old=original.get(label.id).bounds;
                return rendered && Math.abs(rendered.bounds.width-old.width)<.1 &&
                    Math.abs(rendered.bounds.height-old.height)<.1 &&
                    Math.abs(rendered.bounds.x-candidate.box.x)<.15 &&
                    Math.abs(rendered.bounds.y-candidate.box.y)<.15 && guard(label,rendered.bounds);
            });
            if (!valid || !noRegression(next,current) || warnings(next)>=warnings(current)) return null;
            return {moves,next,score:[warnings(next),next.collisions.length,
                moves.reduce((sum,[,c])=>sum+c.move,0)]};
        } finally {
            moves.forEach(([label],i)=>model.setGeometry(model.getCell(label.id),saved[i]));
            graph.getView().validate();
        }
    }
    function better(a,b) {
        if (!b) return true;
        for (let i=0;i<a.score.length;i++) if (a.score[i]!==b.score[i]) return a.score[i]<b.score[i];
        return false;
    }
    function accept(best) {
        for (const [label,candidate] of best.moves) {
            setOffset(label.id,candidate.offset);
            const geo=geometries.get(label.id);
            changes.set(label.id,{id:label.id,edge:label.edge,
                before:[geo.offset?geo.offset.x:0,geo.offset?geo.offset.y:0],
                after:candidate.offset,displacement:candidate.move});
        }
        current=best.next;
    }
    // Every accepted single or coupled step strictly removes warnings. All offsets stay bounded
    // relative to the input, so successive passes cannot walk a label arbitrarily far away.
    let stalled=false;
    for (let round=0; round<options.max_passes && warnings(current); round++) {
        receipt.passes++;
        let improved=false;
        const involved=new Set(current.collisions.filter(c=>c.severity==='warning').flatMap(c=>[c.a,c.b]));
        const labels=current.labels.filter(l=>involved.has(l.id) && geometries.has(l.id)).sort((a,b)=>a.id<b.id?-1:a.id>b.id?1:0);
        for (const label of labels) {
            if (!current.collisions.some(c=>c.severity==='warning' && (c.a===label.id || c.b===label.id))) continue;
            let best=null;
            for (const candidate of candidates(current.labels.find(l=>l.id===label.id),current)) {
                if (attempts>=options.max_attempts) break;
                const result=evaluate([[label,candidate]]);
                if (result && better(result,best)) best=result;
            }
            if (best) { accept(best); improved=true; }
            else skipped.set(label.id,'no-safe-improvement');
        }
        // A tight pair can require both labels to move; never publish either half of such a fix.
        for (const collision of [...current.collisions]) {
            if (attempts>=options.max_attempts) break;
            if (collision.severity!=='warning' || collision.type!=='label-label' ||
                !geometries.has(collision.a) || !geometries.has(collision.b)) continue;
            const a=current.labels.find(l=>l.id===collision.a), b=current.labels.find(l=>l.id===collision.b);
            const ca=candidates(a,current).slice(0,8), cb=candidates(b,current).slice(0,8);
            let best=null;
            for (const x of ca) for (const y of cb) {
                if (attempts>=options.max_attempts) break;
                const result=evaluate([[a,x],[b,y]]);
                if (result && better(result,best)) best=result;
            }
            if (best) { accept(best); improved=true; }
        }
        if (!improved) stalled=true;
        if (!improved || attempts>=options.max_attempts) break;
    }
    receipt.changes=[...changes.values()];
    receipt.skipped=[...skipped].filter(([id])=>!changes.has(id)).map(([id,reason])=>({id,reason}));
    receipt.attempts=attempts;
    receipt.stop_reason=!warnings(current)?'warnings-cleared':attempts>=options.max_attempts?'attempt-budget':
        !stalled && receipt.passes>=options.max_passes?'pass-budget':'no-safe-improvement';
    return receipt;
}
