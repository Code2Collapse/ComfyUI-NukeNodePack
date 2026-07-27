// Light Rig Builder spherical light placer — REAL DOM (rewritten 2026-07-24).
//
// Attaches an interactive 2D-projected sphere widget to nodes named
// "NukeMax_LightRigBuilder". Drag lights on a hemisphere; the widget writes
// JSON state into the hidden `rig_state` STRING widget.
//
// REPLACES a canvas-painted version (17 ctx.* calls, 0 DOM elements) where the
// sphere, the light dots, the labels and the HUD were all pixels, and picking a
// light meant nearest-neighbour math against hand-computed dot positions. A
// sphere is a perfect CSS circle (`border-radius:50%`) and the lights are
// draggable handles — both are textbook DOM. Now: real per-light handles with
// pointer capture, real hover/selected states, crisp text at any zoom, plus
// discoverable controls (light chips + an intensity slider) replacing the
// undiscoverable "right-click to cycle / wheel to change intensity" (both of
// which still work as shortcuts).
//
// Coordinate convention matches `nukemax/core/shading.py`:
//   +X right, +Y up, -Z toward camera. Light direction points FROM
//   light TOWARD scene, so a light placed in front-right is
//   (-x, -y, -z) when projected.

import { app } from "../../../../scripts/app.js";

const NODE_NAME = "NukeMax_LightRigBuilder";

const DEFAULT_LIGHTS = [
    { name: "key",  azimuth: -45, elevation: 30, color: [1.0, 0.95, 0.85], intensity: 1.0, type: "directional" },
    { name: "fill", azimuth:  60, elevation: 15, color: [0.6, 0.7, 1.0],   intensity: 0.4, type: "directional" },
    { name: "rim",  azimuth: 170, elevation: 40, color: [1.0, 1.0, 1.0],   intensity: 0.6, type: "directional" },
];

function azElToDirection(azDeg, elDeg) {
    // Direction the light points toward the scene origin.
    const az = (azDeg * Math.PI) / 180;
    const el = (elDeg * Math.PI) / 180;
    const x = -Math.cos(el) * Math.sin(az);
    const y = -Math.sin(el);
    const z = -Math.cos(el) * Math.cos(az);
    return [x, y, z];
}

function lightToPayload(L) {
    return {
        direction: azElToDirection(L.azimuth, L.elevation),
        color: L.color,
        intensity: L.intensity,
        type: L.type,
        radius: 0.0,
        falloff: 2.0,
    };
}

const rgbCss = (c) => `rgb(${(c[0] * 255) | 0},${(c[1] * 255) | 0},${(c[2] * 255) | 0})`;

function ensureRelightStyles() {
    if (document.getElementById("nukemax-relight-styles")) return;
    const el = document.createElement("style");
    el.id = "nukemax-relight-styles";
    el.textContent = `
.nmx-lr-root{display:flex;flex-direction:column;gap:6px;width:100%;height:100%;
  box-sizing:border-box;padding:8px;min-height:0;font:11px ui-sans-serif,system-ui;color:#c9cfdb;}
.nmx-lr-chips{display:flex;gap:4px;flex:0 0 auto;flex-wrap:wrap;}
.nmx-lr-chip{display:flex;align-items:center;gap:5px;padding:3px 8px;border-radius:11px;
  background:#22222c;border:1px solid #34343e;cursor:pointer;transition:all .12s ease;
  font-size:10px;color:#aeb6c4;}
.nmx-lr-chip:hover{border-color:#4a4a58;color:#e6e9f0;}
.nmx-lr-chip.sel{background:#2b3a4d;border-color:#5b9dd9;color:#e6e9f0;}
.nmx-lr-chip .sw{width:9px;height:9px;border-radius:50%;box-shadow:0 0 0 1px rgba(0,0,0,.5);}
.nmx-lr-stage{position:relative;flex:1 1 auto;min-height:0;display:flex;
  align-items:center;justify-content:center;background:#1a1a22;border-radius:6px;overflow:hidden;}
.nmx-lr-sphere{position:relative;border-radius:50%;border:1px solid #444;
  background:radial-gradient(circle at 35% 30%, #262633 0%, #1c1c24 70%);touch-action:none;}
.nmx-lr-cross-h,.nmx-lr-cross-v{position:absolute;background:#2a2a32;pointer-events:none;}
.nmx-lr-cross-h{left:0;right:0;top:50%;height:1px;}
.nmx-lr-cross-v{top:0;bottom:0;left:50%;width:1px;}
.nmx-lr-dot{position:absolute;border-radius:50%;transform:translate(-50%,-50%);
  cursor:grab;touch-action:none;transition:width .1s ease,height .1s ease,box-shadow .1s ease;
  box-shadow:0 0 0 1px rgba(0,0,0,.55);}
.nmx-lr-dot:hover{box-shadow:0 0 0 2px rgba(255,255,255,.5);}
.nmx-lr-dot.sel{box-shadow:0 0 0 2px #fff,0 0 8px 2px rgba(255,255,255,.25);}
.nmx-lr-dot.drag{cursor:grabbing;}
.nmx-lr-tag{position:absolute;left:calc(100% + 5px);top:50%;transform:translateY(-50%);
  font:10px ui-monospace,monospace;color:#dcdfe6;white-space:nowrap;pointer-events:none;
  text-shadow:0 1px 2px rgba(0,0,0,.85);}
.nmx-lr-foot{display:flex;align-items:center;gap:8px;flex:0 0 auto;
  font:10px ui-monospace,monospace;color:#8b93a7;}
.nmx-lr-foot .rd{color:#c9cfdb;}
.nmx-lr-foot input[type=range]{flex:1 1 auto;min-width:60px;accent-color:#5b9dd9;height:14px;}
.nmx-lr-hint{flex:0 0 auto;font-size:9px;color:#6b7280;text-align:center;}
`;
    document.head.appendChild(el);
}

function createLightRigWidget(node) {
    ensureRelightStyles();

    const state = {
        lights: DEFAULT_LIGHTS.map((L) => ({ ...L })),
        ambient: 0.05,
        selected: 0,
    };

    const stateWidget = node.widgets?.find((w) => w.name === "rig_state");
    // rig_state is authored entirely by this widget — the raw JSON textarea is
    // clutter. Collapse it to a hidden state-carrier (value still serializes;
    // wiring via its socket still works).
    if (stateWidget) {
        stateWidget.type = "hidden";
        stateWidget.computeSize = () => [0, -4];
        stateWidget.hidden = true;
        if (stateWidget.options) stateWidget.options.hidden = true;
        setTimeout(() => {
            const el = stateWidget.element || stateWidget.inputEl;
            if (el) {
                el.style.display = "none";
                const wrap = el.parentElement;
                if (wrap?.classList?.contains("dom-widget")) wrap.style.display = "none";
            }
        }, 0);
    }

    function sync() {
        if (!stateWidget) return;
        stateWidget.value = JSON.stringify({
            lights: state.lights.map(lightToPayload),
            ambient: state.ambient,
        });
        node.graph?.setDirtyCanvas(true, true);
    }

    // Restore a previously-saved rig so reloading a workflow keeps the setup.
    // Payload carries `direction`, so invert the projection back to az/el.
    try {
        const raw = stateWidget?.value;
        if (raw && String(raw).trim()) {
            const d = JSON.parse(raw);
            if (Array.isArray(d?.lights) && d.lights.length) {
                state.lights = d.lights.map((p, i) => {
                    const base = DEFAULT_LIGHTS[i] || DEFAULT_LIGHTS[0];
                    const dir = Array.isArray(p.direction) ? p.direction : null;
                    let azimuth = base.azimuth, elevation = base.elevation;
                    if (dir && dir.length === 3) {
                        // Inverse of azElToDirection.
                        const el = Math.asin(Math.max(-1, Math.min(1, -dir[1])));
                        const az = Math.atan2(-dir[0], -dir[2]);
                        elevation = (el * 180) / Math.PI;
                        azimuth = (az * 180) / Math.PI;
                    }
                    return {
                        name: base.name,
                        azimuth, elevation,
                        color: Array.isArray(p.color) ? p.color : base.color,
                        intensity: Number.isFinite(p.intensity) ? p.intensity : base.intensity,
                        type: p.type || base.type,
                    };
                });
            }
            if (Number.isFinite(d?.ambient)) state.ambient = d.ambient;
        }
    } catch (_) { /* keep defaults */ }

    // ── DOM ──────────────────────────────────────────────────────────
    const root = document.createElement("div");
    root.className = "nmx-lr-root";

    const chips = document.createElement("div");
    chips.className = "nmx-lr-chips";
    root.appendChild(chips);

    const stage = document.createElement("div");
    stage.className = "nmx-lr-stage";
    const sphere = document.createElement("div");
    sphere.className = "nmx-lr-sphere";
    const crossH = document.createElement("div");
    crossH.className = "nmx-lr-cross-h";
    const crossV = document.createElement("div");
    crossV.className = "nmx-lr-cross-v";
    sphere.append(crossH, crossV);
    stage.appendChild(sphere);
    root.appendChild(stage);

    const foot = document.createElement("div");
    foot.className = "nmx-lr-foot";
    const readout = document.createElement("span");
    readout.className = "rd";
    const slider = document.createElement("input");
    slider.type = "range";
    slider.min = "0"; slider.max = "10"; slider.step = "0.05";
    slider.title = "Intensity of the selected light";
    foot.append(readout, slider);
    root.appendChild(foot);

    const hint = document.createElement("div");
    hint.className = "nmx-lr-hint";
    hint.textContent = "drag a light to aim it · scroll over the sphere for intensity";
    root.appendChild(hint);

    const chipEls = [];
    const dotEls = [];

    for (let i = 0; i < state.lights.length; i++) {
        const L = state.lights[i];

        const chip = document.createElement("div");
        chip.className = "nmx-lr-chip";
        chip.tabIndex = 0;
        const sw = document.createElement("span");
        sw.className = "sw";
        const nm = document.createElement("span");
        nm.textContent = L.name;
        chip.append(sw, nm);
        chip.addEventListener("pointerdown", (e) => {
            e.stopPropagation();
            state.selected = i;
            render();
        });
        chips.appendChild(chip);
        chipEls.push({ chip, sw });

        const dot = document.createElement("div");
        dot.className = "nmx-lr-dot";
        dot.title = `${L.name} — drag to aim`;
        const tag = document.createElement("span");
        tag.className = "nmx-lr-tag";
        tag.textContent = L.name;
        dot.appendChild(tag);
        sphere.appendChild(dot);
        dotEls.push({ dot, tag });

        wireDot(i, dot);
    }

    // Sphere geometry is derived from the live element size, so this stays
    // correct at any node size (the canvas version hard-coded 320px and had
    // to record `_lw`/`_ly` to undo LiteGraph's coordinate offsets).
    function geom() {
        const r = sphere.clientWidth / 2;
        return { r: r || 1 };
    }

    function aimFromPointer(clientX, clientY, idx) {
        const rect = sphere.getBoundingClientRect();
        const r = rect.width / 2;
        const dx = clientX - (rect.left + r);
        const dy = clientY - (rect.top + r);
        // Same clamped inverse projection as the canvas version.
        const nx = Math.max(-1, Math.min(1, dx / r));
        const ny = Math.max(-1, Math.min(1, -dy / r));
        const az = (Math.atan2(nx, Math.sqrt(Math.max(0, 1 - nx * nx - ny * ny))) * 180) / Math.PI;
        const el = (Math.asin(ny) * 180) / Math.PI;
        const L = state.lights[idx];
        L.azimuth = az;
        L.elevation = el;
        sync();
        render();
    }

    function wireDot(i, dot) {
        let dragging = false;
        dot.addEventListener("pointerdown", (e) => {
            e.preventDefault();
            e.stopPropagation();
            if (e.button === 2) {   // right-click cycles (legacy shortcut)
                state.selected = (state.selected + 1) % state.lights.length;
                render();
                return;
            }
            state.selected = i;
            dragging = true;
            dot.classList.add("drag");
            try { dot.setPointerCapture(e.pointerId); } catch (_) {}
            render();
        });
        dot.addEventListener("pointermove", (e) => {
            if (!dragging) return;
            e.preventDefault();
            e.stopPropagation();
            aimFromPointer(e.clientX, e.clientY, i);
        });
        const end = (e) => {
            if (!dragging) return;
            dragging = false;
            dot.classList.remove("drag");
            try { dot.releasePointerCapture(e.pointerId); } catch (_) {}
        };
        dot.addEventListener("pointerup", end);
        dot.addEventListener("pointercancel", end);
        dot.addEventListener("contextmenu", (e) => { e.preventDefault(); e.stopPropagation(); });
    }

    // Click anywhere on the sphere to aim the SELECTED light (legacy behaviour).
    sphere.addEventListener("pointerdown", (e) => {
        if (e.target !== sphere && e.target !== crossH && e.target !== crossV) return;
        e.preventDefault();
        e.stopPropagation();
        aimFromPointer(e.clientX, e.clientY, state.selected);
    });

    // Wheel = intensity of the selected light (legacy shortcut, kept).
    stage.addEventListener("wheel", (e) => {
        e.preventDefault();
        e.stopPropagation();
        const L = state.lights[state.selected];
        L.intensity = Math.max(0, Math.min(10, L.intensity + (e.deltaY < 0 ? 0.1 : -0.1)));
        sync();
        render();
    }, { passive: false });

    slider.addEventListener("input", () => {
        const L = state.lights[state.selected];
        L.intensity = Number(slider.value);
        sync();
        render();
    });
    slider.addEventListener("pointerdown", (e) => e.stopPropagation());

    function render() {
        // Keep the sphere a circle that fits the stage.
        const s = Math.max(40, Math.min(stage.clientWidth, stage.clientHeight) - 12);
        sphere.style.width = s + "px";
        sphere.style.height = s + "px";

        const { r } = geom();
        const rr = r * 0.9;   // same 0.45-of-size radius as the canvas version

        state.lights.forEach((L, i) => {
            const az = (L.azimuth * Math.PI) / 180;
            const el = (L.elevation * Math.PI) / 180;
            const px = r + Math.cos(el) * Math.sin(az) * rr;
            const py = r - Math.sin(el) * rr;
            const isSel = i === state.selected;
            const { dot } = dotEls[i];
            const d = isSel ? 18 : 12;
            dot.style.left = px + "px";
            dot.style.top = py + "px";
            dot.style.width = d + "px";
            dot.style.height = d + "px";
            dot.style.background = rgbCss(L.color);
            dot.classList.toggle("sel", isSel);

            const { chip, sw } = chipEls[i];
            chip.classList.toggle("sel", isSel);
            sw.style.background = rgbCss(L.color);
        });

        const sel = state.lights[state.selected];
        readout.textContent =
            `[${sel.name}] az ${sel.azimuth.toFixed(0)}°  el ${sel.elevation.toFixed(0)}°  I ${sel.intensity.toFixed(2)}`;
        if (document.activeElement !== slider) slider.value = String(sel.intensity);
    }

    node.addDOMWidget("light_sphere", "light_sphere", root, {
        getValue: () => "",
        setValue: () => {},
        serialize: false,
    });

    const ro = new ResizeObserver(() => render());
    ro.observe(stage);
    const origRemoved = node.onRemoved;
    node.onRemoved = function () {
        origRemoved?.apply(this, arguments);
        try { ro.disconnect(); } catch (_) {}
    };

    sync();
    setTimeout(render, 30);

    try {
        node.setSize([
            Math.max(node.size?.[0] || 0, 360),
            Math.max(node.size?.[1] || 0, 420),
        ]);
    } catch (_) {}

    node._nmxLightRig = { render, sync, state };
    return root;
}

if (!(app.extensions || []).some((e) => e?.name === "NukeMax.Relight")) {
    app.registerExtension({
        name: "NukeMax.Relight",
        async beforeRegisterNodeDef(nodeType, nodeData) {
            if (nodeData.name !== NODE_NAME) return;
            const onCreated = nodeType.prototype.onNodeCreated;
            nodeType.prototype.onNodeCreated = function () {
                onCreated?.apply(this, arguments);
                try { createLightRigWidget(this); }
                catch (e) { console.error("[NukeMax] light rig widget failed", e); }
            };
            const onConfigure = nodeType.prototype.onConfigure;
            nodeType.prototype.onConfigure = function () {
                onConfigure?.apply(this, arguments);
                this._nmxLightRig?.render();
            };
        },
    });
}
