// 2D light placement for ReLight 2D — drag the lights on the frame.
//
// WHY THIS IS NOT the hemisphere placer next door. That one drives
// NukeMax_LightRigBuilder: a 3D DIRECTIONAL rig, where a light is an angle on
// a sphere and distance is meaningless. This node is the other kind — lights
// PAINTED ON THE PLATE at a position in the frame, with an inner and outer
// radius. Same word, different geometry, so the same widget cannot serve both:
// dragging a dot on a sphere and dragging a dot on a picture are not the same
// gesture and do not produce the same numbers.
//
// WHAT IT REPLACES. ReLight 2D shipped its lights as six numeric widgets —
// light_position_x, light_position_y, and the same again for lights 2 and 3,
// plus four radii. Every one of them is a place on the picture, and a place on
// a picture is something you point at. Typing 0.7 / 0.3 and re-rendering to
// see where that landed is the slowest possible way to place a key light.
//
// It writes the SAME widgets the node already reads. There is no new backend
// field and no hidden state: drag a dot and the numeric widget moves, type in
// the numeric widget and the dot moves. That matters because the numbers are
// what a saved workflow stores — a widget with its own private state would
// lose the placement on reload, which is the classic version of this bug.
//
// The radius rings are drawn to scale against the frame's SHORT edge, matching
// how the backend builds its falloff mask. A ring drawn against the long edge
// would look right on a square and lie on a 16:9 plate.

import { app } from "../../../../scripts/app.js";

const NODE_NAME = "NukeMax_ReLight2D";
const STATE = "_nmxLight2D";

// light index -> the widget names it owns. Light 1 uses the unprefixed names,
// which is upstream's own scheme; 2 and 3 are prefixed.
const LIGHTS = [
    {
        n: 1, colour: "#ffd479",
        x: "light_position_x", y: "light_position_y",
        inner: "inner_circle_radius", outer: "outer_circle_radius",
    },
    {
        n: 2, colour: "#79c0ff",
        x: "light2_position_x", y: "light2_position_y",
        inner: "light2_inner_radius", outer: "light2_outer_radius",
    },
    {
        n: 3, colour: "#7ee787",
        x: "light3_position_x", y: "light3_position_y",
        inner: "light3_inner_radius", outer: "light3_outer_radius",
    },
];

const CSS = `
.nmx-l2-wrap{padding:6px 8px 8px;font:12px system-ui,-apple-system,sans-serif;}
.nmx-l2-stage{position:relative;width:100%;background:#15171b;border:1px solid #33383f;
  border-radius:6px;overflow:hidden;cursor:crosshair;touch-action:none;}
.nmx-l2-grid{position:absolute;inset:0;pointer-events:none;
  background-image:linear-gradient(#ffffff0d 1px,transparent 1px),
                   linear-gradient(90deg,#ffffff0d 1px,transparent 1px);}
.nmx-l2-thirds{position:absolute;background:#ffffff1f;pointer-events:none;}
.nmx-l2-ring{position:absolute;border-radius:50%;transform:translate(-50%,-50%);
  pointer-events:none;border-style:solid;}
.nmx-l2-dot{position:absolute;width:13px;height:13px;border-radius:50%;
  transform:translate(-50%,-50%);border:2px solid #10121599;cursor:grab;
  box-shadow:0 0 0 1px #0006,0 1px 4px #0008;}
.nmx-l2-dot[data-drag="1"]{cursor:grabbing;transform:translate(-50%,-50%) scale(1.18);}
.nmx-l2-dot[data-off="1"]{opacity:.28;}
.nmx-l2-tag{position:absolute;transform:translate(-50%,-50%);pointer-events:none;
  font:600 9px ui-monospace,monospace;color:#101215;}
.nmx-l2-foot{display:flex;justify-content:space-between;gap:8px;
  margin-top:5px;color:#8b94a3;font-size:11px;}
.nmx-l2-foot b{color:#c9d1d9;font-weight:600;font-variant-numeric:tabular-nums;}
`;

function injectCss() {
    if (document.getElementById("nmx-l2-css")) return;
    const s = document.createElement("style");
    s.id = "nmx-l2-css";
    s.textContent = CSS;
    document.head.appendChild(s);
}

const clamp01 = (v) => Math.max(0, Math.min(1, v));

function build(node) {
    injectCss();
    const wrap = document.createElement("div");
    wrap.className = "nmx-l2-wrap";

    const stage = document.createElement("div");
    stage.className = "nmx-l2-stage";
    const grid = document.createElement("div");
    grid.className = "nmx-l2-grid";
    stage.appendChild(grid);

    // rule-of-thirds guides: a key light lands on one more often than not
    for (const [k, v] of [["left", "33.333%"], ["left", "66.667%"],
                          ["top", "33.333%"], ["top", "66.667%"]]) {
        const g = document.createElement("div");
        g.className = "nmx-l2-thirds";
        if (k === "left") { g.style.left = v; g.style.top = 0; g.style.bottom = 0; g.style.width = "1px"; }
        else { g.style.top = v; g.style.left = 0; g.style.right = 0; g.style.height = "1px"; }
        stage.appendChild(g);
    }

    const foot = document.createElement("div");
    foot.className = "nmx-l2-foot";
    const hint = document.createElement("span");
    const readout = document.createElement("span");
    foot.append(hint, readout);
    wrap.append(stage, foot);

    const st = { stage, wrap, hint, readout, dots: [], rings: [], dragging: null };
    node[STATE] = st;

    const W = (name) => node.widgets?.find((w) => w.name === name);

    // How many lights the node is actually using, so 2 and 3 grey out until
    // they are switched on rather than looking like they do nothing.
    const activeCount = () => {
        const w = W("num_light_sources");
        const n = Number(w?.value);
        return Number.isFinite(n) ? Math.max(1, Math.min(3, n)) : 1;
    };

    // The frame's aspect, so the stage is the shape of the plate rather than
    // a square that lies about where the middle is.
    const aspect = () => {
        const img = node.imgs?.[0];
        if (img?.naturalWidth && img?.naturalHeight) return img.naturalWidth / img.naturalHeight;
        return 16 / 9;
    };

    for (const L of LIGHTS) {
        const outer = document.createElement("div");
        outer.className = "nmx-l2-ring";
        const inner = document.createElement("div");
        inner.className = "nmx-l2-ring";
        const dot = document.createElement("div");
        dot.className = "nmx-l2-dot";
        dot.style.background = L.colour;
        dot.title = `Light ${L.n} — drag to place`;
        const tag = document.createElement("div");
        tag.className = "nmx-l2-tag";
        tag.textContent = String(L.n);
        stage.append(outer, inner, dot, tag);
        st.rings.push({ L, outer, inner });
        st.dots.push({ L, dot, tag });

        const begin = (ev) => {
            if (L.n > activeCount()) return;
            st.dragging = L;
            dot.dataset.drag = "1";
            dot.setPointerCapture?.(ev.pointerId);
            ev.stopPropagation();
            ev.preventDefault();
        };
        dot.addEventListener("pointerdown", begin);
    }

    const place = (ev) => {
        if (!st.dragging) return;
        const r = stage.getBoundingClientRect();
        if (!r.width || !r.height) return;
        const L = st.dragging;
        const wx = W(L.x), wy = W(L.y);
        if (wx) { wx.value = clamp01((ev.clientX - r.left) / r.width); wx.callback?.(wx.value); }
        if (wy) { wy.value = clamp01((ev.clientY - r.top) / r.height); wy.callback?.(wy.value); }
        render();
        node.setDirtyCanvas(true, true);
        ev.preventDefault();
    };
    const end = (ev) => {
        if (!st.dragging) return;
        const d = st.dots.find((x) => x.L === st.dragging);
        if (d) delete d.dot.dataset.drag;
        st.dragging = null;
        // Finalise on release, so a drag is one undo step rather than sixty.
        node.graph?.setDirtyCanvas?.(true, true);
        ev?.preventDefault?.();
    };
    // On the window, not the dot: a fast drag leaves the element behind and
    // the light would stick to the cursor after the button came up.
    window.addEventListener("pointermove", place);
    window.addEventListener("pointerup", end);
    window.addEventListener("pointercancel", end);
    st._detach = () => {
        window.removeEventListener("pointermove", place);
        window.removeEventListener("pointerup", end);
        window.removeEventListener("pointercancel", end);
    };

    // Click empty stage to move the nearest ACTIVE light there - faster than
    // finding a 13px dot, and it cannot grab a light that is switched off.
    stage.addEventListener("pointerdown", (ev) => {
        if (ev.target !== stage && !ev.target.classList.contains("nmx-l2-grid")
            && !ev.target.classList.contains("nmx-l2-thirds")) return;
        const r = stage.getBoundingClientRect();
        const px = (ev.clientX - r.left) / r.width, py = (ev.clientY - r.top) / r.height;
        let best = null, bestD = Infinity;
        for (const L of LIGHTS.slice(0, activeCount())) {
            const x = Number(W(L.x)?.value ?? 0.5), y = Number(W(L.y)?.value ?? 0.5);
            const d = (x - px) ** 2 + (y - py) ** 2;
            if (d < bestD) { bestD = d; best = L; }
        }
        if (!best) return;
        st.dragging = best;
        place(ev);
        end(ev);
    });

    function render() {
        const r = stage.getBoundingClientRect();
        const w = r.width || 320;
        stage.style.aspectRatio = String(aspect());
        const h = w / aspect();
        grid.style.backgroundSize = `${w / 8}px ${h / 8}px`;

        const active = activeCount();
        // Radii are fractions of the SHORT edge, matching how the backend
        // builds its falloff. Scaling against the long edge would look right
        // on a square and be wrong on every real plate.
        const shortEdge = Math.min(w, h);

        for (const { L, outer, inner } of st.rings) {
            const on = L.n <= active;
            const x = Number(W(L.x)?.value ?? 0.5) * 100;
            const y = Number(W(L.y)?.value ?? 0.5) * 100;
            const ri = Number(W(L.inner)?.value ?? 0.3);
            const ro = Number(W(L.outer)?.value ?? 0.6);
            for (const [el, rad, style, alpha] of [
                [outer, ro, "dashed", on ? 0.5 : 0.15],
                [inner, ri, "solid", on ? 0.85 : 0.2],
            ]) {
                const d = Math.max(0, rad) * shortEdge * 2;
                el.style.left = `${x}%`;
                el.style.top = `${y}%`;
                el.style.width = `${d}px`;
                el.style.height = `${d}px`;
                el.style.borderWidth = "1px";
                el.style.borderStyle = style;
                el.style.borderColor = L.colour;
                el.style.opacity = String(alpha);
            }
        }
        for (const { L, dot, tag } of st.dots) {
            const on = L.n <= active;
            const x = Number(W(L.x)?.value ?? 0.5) * 100;
            const y = Number(W(L.y)?.value ?? 0.5) * 100;
            dot.style.left = `${x}%`; dot.style.top = `${y}%`;
            tag.style.left = `${x}%`; tag.style.top = `${y}%`;
            dot.dataset.off = on ? "0" : "1";
            tag.style.opacity = on ? "1" : "0.3";
        }

        hint.textContent = active === 1
            ? "Drag the light, or click anywhere to move it."
            : `Drag any of ${active} lights. Click moves the nearest.`;
        const L1 = LIGHTS[0];
        readout.innerHTML = `<b>${Number(W(L1.x)?.value ?? 0.5).toFixed(2)}, `
            + `${Number(W(L1.y)?.value ?? 0.5).toFixed(2)}</b>`;
    }
    st.render = render;

    // Typing in a numeric widget must move the dot. Without this the two
    // disagree and the picture follows whichever was touched last, which
    // reads as the widget being broken.
    for (const L of LIGHTS) {
        for (const nm of [L.x, L.y, L.inner, L.outer]) {
            const w = W(nm);
            if (!w) continue;
            const prev = w.callback;
            w.callback = function (...a) { const out = prev?.apply(this, a); render(); return out; };
        }
    }
    const nw = W("num_light_sources");
    if (nw) {
        const prev = nw.callback;
        nw.callback = function (...a) { const out = prev?.apply(this, a); render(); return out; };
    }

    node.addDOMWidget?.("nmx_light_2d", "div", wrap, {
        serialize: false,          // the numeric widgets ARE the saved state
        hideOnZoom: false,
        getMinHeight: () => 210,
    });

    const onRemoved = node.onRemoved;
    node.onRemoved = function (...a) {
        try { st._detach?.(); } catch (_e) { /* removal must not throw */ }
        delete node[STATE];
        return onRemoved?.apply(this, a);
    };

    requestAnimationFrame(render);
}

if (!(app.extensions || []).some((e) => e?.name === "NukeMax.ReLight2D.Placer")) {
    app.registerExtension({
        name: "NukeMax.ReLight2D.Placer",
        async beforeRegisterNodeDef(nodeType, nodeData) {
            if (nodeData.name !== NODE_NAME) return;
            const onCreated = nodeType.prototype.onNodeCreated;
            nodeType.prototype.onNodeCreated = function () {
                onCreated?.apply(this, arguments);
                try { build(this); }
                catch (e) { console.error("[NukeMax] ReLight 2D placer failed", e); }
            };
            const onConfigure = nodeType.prototype.onConfigure;
            nodeType.prototype.onConfigure = function (...a) {
                const out = onConfigure?.apply(this, a);
                this[STATE]?.render?.();
                return out;
            };
        },
    });
}
