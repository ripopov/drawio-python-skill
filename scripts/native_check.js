/* Read-only checker using installed Draw.io Graph and native text geometry. */
(async function () {
    function finish(report) {
        const out = document.createElement('pre');
        out.id = 'native-check-result';
        out.textContent = JSON.stringify(report);
        document.body.appendChild(out);
    }
    try {
        const reports = [];
        for (const input of nativeCheckInput.pages) {
            const container = document.createElement('div');
            container.style.cssText = 'position:relative;width:2000px;height:2000px';
            document.body.appendChild(container);
            const graph = new Graph(container);
            graph.setEnabled(false);
            const xml = mxUtils.parseXml(input.xml);
            new mxCodec(xml).decode(xml.documentElement, graph.getModel());
            graph.getView().validate();
            await document.fonts.ready;
            // Timers work with headless virtual time even when frames are throttled.
            await new Promise(resolve => setTimeout(resolve, 50));
            graph.refresh();
            const model = graph.getModel();
            const labels = [], shapes = [], unmeasured = [];
            const labelStates = new Map();
            const rect = b => ({x: b.x, y: b.y, width: b.width, height: b.height});
            function edgeOwner(cell) {
                for (let c = cell; c; c = model.getParent(c)) {
                    if (model.isEdge(c)) return c.id;
                }
                return null;
            }
            function ancestor(a, b) {
                for (let c = model.getParent(b); c; c = model.getParent(c)) {
                    if (c === a) return true;
                }
                return false;
            }
            for (const cell of Object.values(model.cells)) {
                const state = graph.getView().getState(cell);
                if (!state) continue; // Hidden/collapsed cells have no rendered state.
                const s = state.style || {};
                const text = String(graph.getLabel(cell) || '');
                const owner = edgeOwner(cell);
                if (text && s.noLabel !== 1 && s.noLabel !== '1' &&
                    s.opacity !== 0 && s.opacity !== '0' &&
                    s.textOpacity !== 0 && s.textOpacity !== '0') {
                    const b = state.text && state.text.boundingBox;
                    if (b && [b.x, b.y, b.width, b.height].every(Number.isFinite) && b.width > 0 && b.height > 0) {
                        labels.push({id: cell.id, edge: owner, text, bounds: rect(b)});
                        labelStates.set(cell.id, state);
                    } else {
                        unmeasured.push({id: cell.id, edge: owner, text});
                    }
                }
                const geo = model.getGeometry(cell);
                if (model.isVertex(cell) && !owner && geo && !geo.relative &&
                    s.opacity !== 0 && s.opacity !== '0' && s.shape !== 'text' &&
                    s.fillColor !== 'none' && s.fillOpacity !== 0 && s.fillOpacity !== '0') {
                    shapes.push({id: cell.id, cell, state, bounds: rect(state)});
                }
            }
            function intersection(a, b, clearance = nativeCheckInput.padding) {
                const pad = clearance / 2;
                const left = Math.max(a.x - pad, b.x - pad);
                const top = Math.max(a.y - pad, b.y - pad);
                const right = Math.min(a.x + a.width + pad, b.x + b.width + pad);
                const bottom = Math.min(a.y + a.height + pad, b.y + b.height + pad);
                return right > left && bottom > top ? {x: left, y: top, width: right-left, height: bottom-top} : null;
            }
            function opacity(style, key) {
                return style[key] == null ? 1 : Number(style[key]) / 100;
            }
            function colorAlpha(color) {
                if (!color || color === 'none') return 0;
                const probe = document.createElement('span');
                probe.style.color = color;
                if (!probe.style.color) return 0; // Unknown colors cannot justify occlusion.
                document.body.appendChild(probe);
                const normalized = getComputedStyle(probe).color;
                probe.remove();
                if (normalized === 'transparent') return 0;
                const rgba = normalized.match(/^rgba\([^,]+,[^,]+,[^,]+,\s*([\d.]+)\)$/);
                return rgba ? Number(rgba[1]) : normalized.startsWith('rgb(') ? 1 : 0;
            }
            // Hit testing follows browser paint/stacking order, including HTML label panes.
            // Temporarily enabling pointer events changes no pixels or source geometry.
            function paintOrder(labelNode, shapeNode, overlap) {
                if (!labelNode || !shapeNode || !overlap) return 'unknown';
                const changed = [];
                for (const root of [labelNode, shapeNode]) {
                    for (const node of [root, ...root.querySelectorAll('*')]) {
                        changed.push([node, node.style.getPropertyValue('pointer-events'),
                            node.style.getPropertyPriority('pointer-events')]);
                        node.style.setProperty('pointer-events', 'all', 'important');
                    }
                }
                let above = 0, below = 0;
                try {
                    const pos = container.getBoundingClientRect();
                    window.scrollTo(window.scrollX + pos.left + overlap.x + overlap.width/2 - innerWidth/2,
                        window.scrollY + pos.top + overlap.y + overlap.height/2 - innerHeight/2);
                    const origin = container.getBoundingClientRect();
                    for (const fx of [.2, .5, .8]) for (const fy of [.2, .5, .8]) {
                        const x = origin.left + overlap.x + overlap.width*fx;
                        const y = origin.top + overlap.y + overlap.height*fy;
                        const stack = document.elementsFromPoint(x, y);
                        const label = stack.findIndex(n => n === labelNode || labelNode.contains(n));
                        const shape = stack.findIndex(n => n === shapeNode || shapeNode.contains(n));
                        if (label < 0 || shape < 0) continue;
                        if (shape < label) above++; else if (label < shape) below++;
                    }
                } finally {
                    for (const [node, value, priority] of changed) {
                        if (value) node.style.setProperty('pointer-events', value, priority);
                        else node.style.removeProperty('pointer-events');
                    }
                }
                return above && !below ? 'shape-above-label' : below && !above ? 'label-above-shape' : 'unknown';
            }
            const collisions = [];
            for (let i=0; i<labels.length; i++) {
                const a = labels[i];
                for (let j=i+1; j<labels.length; j++) {
                    const b = labels[j];
                    if (!a.edge && !b.edge) continue;
                    const overlap = intersection(a.bounds, b.bounds);
                    if (overlap) {
                        const actual = intersection(a.bounds, b.bounds, 0);
                        collisions.push({type: 'label-label', a: a.id, b: b.id, overlap,
                            severity: actual ? 'warning' : 'advisory',
                            reason: actual ? 'overlapping-label-bounds' : 'insufficient-clearance'});
                    }
                }
                if (!a.edge) continue;
                const edge = model.getCell(a.edge);
                for (const b of shapes) {
                    if (ancestor(b.cell, edge)) continue; // Intentional containing groups/pools.
                    const overlap = intersection(a.bounds, b.bounds);
                    if (!overlap) continue;
                    const actual = intersection(a.bounds, b.bounds, 0);
                    const labelState = labelStates.get(a.id);
                    const shapeStyle = b.state.style || {};
                    const labelStyle = labelState.style || {};
                    const fill = b.state.shape && b.state.shape.fill;
                    const alpha = colorAlpha(fill) * opacity(shapeStyle, 'opacity') * opacity(shapeStyle, 'fillOpacity');
                    if (alpha === 0) continue;
                    const order = paintOrder(labelState.text.node, b.state.shape && b.state.shape.node, actual);
                    const background = colorAlpha(labelState.text.background) * opacity(labelStyle, 'opacity') * opacity(labelStyle, 'textOpacity');
                    let severity = 'advisory', reason = 'shape-overlap-needs-review';
                    if (!actual) reason = 'insufficient-clearance';
                    else if (order === 'shape-above-label' && alpha >= .999) {
                        severity = 'warning'; reason = 'possible-label-occlusion';
                    } else if (order === 'label-above-shape' && background >= .999) {
                        severity = 'info'; reason = 'label-background-protects-text';
                    } else if (order === 'label-above-shape') reason = 'label-visible-above-shape';
                    else if (order === 'shape-above-label') reason = 'translucent-shape-above-label';
                    collisions.push({type: 'label-shape', a: a.id, b: b.id, overlap,
                        severity, reason, paint_order: order, shape_fill_alpha: alpha,
                        label_background_alpha: background});
                }
            }
            const summary = {warning: 0, advisory: 0, info: 0};
            for (const finding of collisions) summary[finding.severity]++;
            reports.push({index: input.index, name: input.name, labels, summary,
                bounds: rect(graph.getGraphBounds()),
                shapes: shapes.map(s => ({id: s.id, bounds: s.bounds})),
                collisions, unmeasured_labels: unmeasured});
            graph.destroy();
            container.remove();
        }
        finish({renderer: 'Draw.io Graph in Chromium', padding: nativeCheckInput.padding,
            browser: navigator.userAgent,
            limitations: ['Rectangle intersections and sampled paint order are potential issues, not pixel-level proof; intentional overlaps and rotated/nonrectangular shapes need review.',
                'Only visible cells are checked; hidden and collapsed contents are excluded.',
                'Offline fonts may fall back; remote assets, math typesetting and line-label intersections are not verified.'],
            pages: reports});
    } catch (error) {
        finish({error: String(error.stack || error)});
    }
})();
