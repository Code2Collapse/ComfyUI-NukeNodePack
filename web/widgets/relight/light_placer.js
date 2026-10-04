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
import {
  mountPanel,
  button,
  sliderRow,
  statusLine,
  section,
} from "../../c2c_ui/index.js";

const NODE_NAME = "NukeMax_LightRigBuilder";
const PANEL_MIN = 360;
const NODE_MIN_W = 360;

const DEFAULT_LIGHTS = [
  { name: "key", azimuth: -45, elevation: 30, color: [1.0, 0.95, 0.85], intensity: 1.0, type: "directional" },
  { name: "fill", azimuth: 60, elevation: 15, color: [0.6, 0.7, 1.0], intensity: 0.4, type: "directional" },
  { name: "rim", azimuth: 170, elevation: 40, color: [1.0, 1.0, 1.0], intensity: 0.6, type: "directional" },
];

function chainOnRemoved(node, cleanup) {
  const orig = node.onRemoved;
  node.onRemoved = function (...a) {
    try { cleanup?.(); } catch (_e) { /* ignore */ }
    return orig?.apply(this, a);
  };
}

function azElToDirection(azDeg, elDeg) {
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

function sphereStyles() {
  const cs = getComputedStyle(document.documentElement);
  const g = (v, fb) => cs.getPropertyValue(v).trim() || fb;
  return {
    panel: g("--cu-panel", "#1e1f47"),
    edge: g("--cu-edge", "#2a2a57"),
    sunken: g("--cu-sunken", "#0c0d23"),
    ink: g("--cu-ink", "#e8e6f7"),
    dim: g("--cu-ink-dim", "#6f6d9b"),
    grid: g("--cu-edge", "#2a2a57"),
    accent: g("--cu-accent", "#b494ff"),
  };
}

function createLightRigWidget(node) {
  const rigState = {
    lights: DEFAULT_LIGHTS.map((L) => ({ ...L })),
    ambient: 0.05,
    selected: 0,
  };

  const stateWidget = node.widgets?.find((w) => w.name === "rig_state");
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
      lights: rigState.lights.map(lightToPayload),
      ambient: rigState.ambient,
    });
    node.graph?.setDirtyCanvas(true, true);
  }

  try {
    const raw = stateWidget?.value;
    if (raw && String(raw).trim()) {
      const d = JSON.parse(raw);
      if (Array.isArray(d?.lights) && d.lights.length) {
        rigState.lights = d.lights.map((p, i) => {
          const base = DEFAULT_LIGHTS[i] || DEFAULT_LIGHTS[0];
          const dir = Array.isArray(p.direction) ? p.direction : null;
          let azimuth = base.azimuth, elevation = base.elevation;
          if (dir && dir.length === 3) {
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
      if (Number.isFinite(d?.ambient)) rigState.ambient = d.ambient;
    }
  } catch (_) { /* keep defaults */ }

  const root = document.createElement("div");
  root.style.display = "flex";
  root.style.flexDirection = "column";
  root.style.gap = "6px";
  root.style.width = "100%";
  root.style.height = "100%";
  root.style.minHeight = "0";

  const chips = document.createElement("div");
  chips.style.display = "flex";
  chips.style.gap = "4px";
  chips.style.flexWrap = "wrap";

  const stageWrap = document.createElement("div");
  stageWrap.style.position = "relative";
  stageWrap.style.flex = "1 1 auto";
  stageWrap.style.minHeight = "120px";
  stageWrap.style.display = "flex";
  stageWrap.style.alignItems = "center";
  stageWrap.style.justifyContent = "center";
  stageWrap.style.overflow = "hidden";
  stageWrap.style.borderRadius = "6px";

  const sphere = document.createElement("div");
  sphere.style.position = "relative";
  sphere.style.borderRadius = "50%";
  sphere.style.touchAction = "none";

  const crossH = document.createElement("div");
  const crossV = document.createElement("div");
  crossH.style.cssText = "position:absolute;left:0;right:0;top:50%;height:1px;pointer-events:none;";
  crossV.style.cssText = "position:absolute;top:0;bottom:0;left:50%;width:1px;pointer-events:none;";
  sphere.append(crossH, crossV);
  stageWrap.appendChild(sphere);

  const readout = statusLine();
  let intensityRow;

  const hint = statusLine();
  hint.setText("drag a light to aim it · scroll over the sphere for intensity", "default");

  const chipEls = [];
  const dotEls = [];

  function applyTheme() {
    const t = sphereStyles();
    stageWrap.style.background = t.sunken;
    crossH.style.background = t.grid;
    crossV.style.background = t.grid;
    sphere.style.border = `1px solid ${t.edge}`;
    sphere.style.background =
      `radial-gradient(circle at 35% 30%, ${t.panel} 0%, ${t.sunken} 70%)`;
  }

  function geom() {
    const r = sphere.clientWidth / 2;
    return { r: r || 1 };
  }

  function aimFromPointer(clientX, clientY, idx) {
    const rect = sphere.getBoundingClientRect();
    const r = rect.width / 2;
    const dx = clientX - (rect.left + r);
    const dy = clientY - (rect.top + r);
    const nx = Math.max(-1, Math.min(1, dx / r));
    const ny = Math.max(-1, Math.min(1, -dy / r));
    const az = (Math.atan2(nx, Math.sqrt(Math.max(0, 1 - nx * nx - ny * ny))) * 180) / Math.PI;
    const el = (Math.asin(ny) * 180) / Math.PI;
    const L = rigState.lights[idx];
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
      if (e.button === 2) {
        rigState.selected = (rigState.selected + 1) % rigState.lights.length;
        render();
        return;
      }
      rigState.selected = i;
      dragging = true;
      dot.style.cursor = "grabbing";
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
      dot.style.cursor = "grab";
      try { dot.releasePointerCapture(e.pointerId); } catch (_) {}
    };
    dot.addEventListener("pointerup", end);
    dot.addEventListener("pointercancel", end);
    dot.addEventListener("contextmenu", (e) => { e.preventDefault(); e.stopPropagation(); });
  }

  for (let i = 0; i < rigState.lights.length; i++) {
    const L = rigState.lights[i];
    const chip = button(L.name, {
      onClick: () => { rigState.selected = i; render(); },
    });
    chip.style.display = "inline-flex";
    chip.style.alignItems = "center";
    chip.style.gap = "5px";
    const sw = document.createElement("span");
    sw.style.width = "9px";
    sw.style.height = "9px";
    sw.style.borderRadius = "50%";
    sw.style.boxShadow = "0 0 0 1px rgba(0,0,0,.5)";
    sw.style.background = rgbCss(L.color);
    chip.prepend(sw);
    chips.appendChild(chip);
    chipEls.push({ chip, sw });

    const dot = document.createElement("div");
    dot.style.position = "absolute";
    dot.style.borderRadius = "50%";
    dot.style.transform = "translate(-50%,-50%)";
    dot.style.cursor = "grab";
    dot.style.touchAction = "none";
    dot.style.boxShadow = "0 0 0 1px rgba(0,0,0,.55)";
    dot.title = `${L.name} — drag to aim`;
    const tag = document.createElement("span");
    tag.style.position = "absolute";
    tag.style.left = "calc(100% + 5px)";
    tag.style.top = "50%";
    tag.style.transform = "translateY(-50%)";
    tag.style.font = "10px ui-monospace,monospace";
    tag.style.whiteSpace = "nowrap";
    tag.style.pointerEvents = "none";
    tag.style.textShadow = "0 1px 2px rgba(0,0,0,.85)";
    tag.textContent = L.name;
    dot.appendChild(tag);
    sphere.appendChild(dot);
    dotEls.push({ dot, tag });
    wireDot(i, dot);
  }

  sphere.addEventListener("pointerdown", (e) => {
    if (e.target !== sphere && e.target !== crossH && e.target !== crossV) return;
    e.preventDefault();
    e.stopPropagation();
    aimFromPointer(e.clientX, e.clientY, rigState.selected);
  });

  stageWrap.addEventListener("wheel", (e) => {
    e.preventDefault();
    e.stopPropagation();
    const L = rigState.lights[rigState.selected];
    L.intensity = Math.max(0, Math.min(10, L.intensity + (e.deltaY < 0 ? 0.1 : -0.1)));
    sync();
    render();
  }, { passive: false });

  function render() {
    applyTheme();
    const t = sphereStyles();
    const s = Math.max(40, Math.min(stageWrap.clientWidth, stageWrap.clientHeight) - 12);
    sphere.style.width = s + "px";
    sphere.style.height = s + "px";
    const { r } = geom();
    const rr = r * 0.9;

    rigState.lights.forEach((L, i) => {
      const az = (L.azimuth * Math.PI) / 180;
      const el = (L.elevation * Math.PI) / 180;
      const px = r + Math.cos(el) * Math.sin(az) * rr;
      const py = r - Math.sin(el) * rr;
      const isSel = i === rigState.selected;
      const { dot, tag } = dotEls[i];
      const d = isSel ? 18 : 12;
      dot.style.left = px + "px";
      dot.style.top = py + "px";
      dot.style.width = d + "px";
      dot.style.height = d + "px";
      dot.style.background = rgbCss(L.color);
      dot.style.boxShadow = isSel
        ? `0 0 0 2px ${t.ink}, 0 0 8px 2px rgba(255,255,255,.25)`
        : "0 0 0 1px rgba(0,0,0,.55)";
      tag.style.color = t.ink;

      const { chip, sw } = chipEls[i];
      if (isSel) {
        chip.style.borderColor = t.accent;
        chip.classList.add("c2c-ui-btn--primary");
      } else {
        chip.style.borderColor = "";
        chip.classList.remove("c2c-ui-btn--primary");
      }
      sw.style.background = rgbCss(L.color);
    });

    const sel = rigState.lights[rigState.selected];
    readout.setText(
      `[${sel.name}] az ${sel.azimuth.toFixed(0)}°  el ${sel.elevation.toFixed(0)}°  I ${sel.intensity.toFixed(2)}`,
    );
    if (intensityRow) {
      const range = intensityRow.querySelector("input[type=range]");
      const num = intensityRow.querySelector("input[type=number]");
      if (document.activeElement !== range && document.activeElement !== num) {
        if (range) range.value = String(sel.intensity);
        if (num) num.value = String(sel.intensity);
      }
    }
  }

  intensityRow = sliderRow("Intensity", {
    min: 0, max: 10, step: 0.05, value: rigState.lights[0].intensity,
    onChange: (v) => {
      rigState.lights[rigState.selected].intensity = v;
      sync();
      render();
    },
  });
  intensityRow.querySelector("input[type=range]")?.addEventListener("pointerdown", (e) => {
    e.stopPropagation();
  });

  const body = document.createElement("div");
  body.style.display = "flex";
  body.style.flexDirection = "column";
  body.style.gap = "6px";
  body.style.flex = "1 1 auto";
  body.style.minHeight = "0";
  body.append(chips, stageWrap, readout.el, intensityRow, hint.el);
  // The section and its inner body must flex too, or the body's flex:1 has
  // nothing to grow into and the spare panel height sat as dead space below
  // the hint instead of enlarging the sphere.
  const sec = section("Light rig", body);
  for (const el of [sec, sec.querySelector(".c2c-ui-section__body")]) {
    if (!el) continue;
    el.style.display = "flex";
    el.style.flexDirection = "column";
    el.style.flex = "1 1 auto";
    el.style.minHeight = "0";
  }
  root.appendChild(sec);

  mountPanel(node, "light_sphere", root, { minHeight: PANEL_MIN, fill: true });

  const ro = new ResizeObserver(() => render());
  ro.observe(stageWrap);
  chainOnRemoved(node, () => {
    try { ro.disconnect(); } catch (_) {}
    delete node._nmxLightRig;
  });

  sync();
  render();
  setTimeout(render, 30);

  try {
    node.setSize([
      Math.max(node.size?.[0] || 0, NODE_MIN_W),
      Math.max(node.size?.[1] || 0, 420),
    ]);
  } catch (_) {}

  node._nmxLightRig = { render, sync, state: rigState };
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
