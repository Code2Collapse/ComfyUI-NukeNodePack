// Roto Spline Editor canvas widget.
// Attaches a click-to-add / drag bezier editor to nodes named
// "NukeMax_RotoSplineEditor". The widget writes its JSON state into
// the hidden `spline_state` STRING widget so the value persists in
// the workflow.

import { app } from "../../../../scripts/app.js";
import { installCanvasWidget } from "../_vue_canvas.js";

const NODE_NAME = "NukeMax_RotoSplineEditor";

// Resolve a CSS custom property at draw time; fall back to a hex literal
// if the token isn't registered (e.g. C2C theme module not loaded).
function _tok(name, fallback) {
    try {
        const v = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
        return v || fallback;
    } catch {
        return fallback;
    }
}

function createRotoWidget(node) {
    const state = {
        frames: [
            { points: [], in: [], out: [], feather: [] },
        ],
        closed: true,
        canvas: { h: 512, w: 512 },
        currentFrame: 0,
    };

    // Find the state widget (created from the Python INPUT_TYPES) and truly
    // collapse it — the editor below authors it entirely; the raw JSON
    // textarea is clutter. Value still serializes; the socket still works.
    const stateWidget = node.widgets.find(w => w.name === "spline_state");
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

    const widget = {
        type: "custom",
        name: "roto_canvas",
        size: [320, 320],
        // Without computeSize LiteGraph reserves only the default ~20px row for a
        // custom widget — the 320px editor then painted PAST the node's bottom
        // border (canvas overflowing onto the graph). This makes layout reserve
        // the true drawn height so the node body contains the editor.
        computeSize(width) { return [width || 320, 320]; },
        draw(ctx, node, widget_width, y, widget_height) {
            const x = 0;
            const w = widget_width;
            const h = 320;
            ctx.save();
            ctx.fillStyle = _tok("--c2c-surface1", "#222");
            ctx.fillRect(x, y, w, h);
            const frame = state.frames[state.currentFrame] || { points: [] };
            if (frame.points.length === 0) {
                // Empty state: dark checkerboard artboard + centred hint —
                // a flat grey void reads as "broken node". Literal colors:
                // canvas fillStyle can't parse var(--x).
                const tile = 24;
                for (let ty = 0; ty < h; ty += tile) {
                    for (let tx = 0; tx < w; tx += tile) {
                        ctx.fillStyle = (((tx + ty) / tile) % 2 === 0) ? "#15151d" : "#1a1a24";
                        ctx.fillRect(x + tx, y + ty, Math.min(tile, w - tx), Math.min(tile, h - ty));
                    }
                }
                ctx.textAlign = "center";
                ctx.textBaseline = "middle";
                ctx.fillStyle = "rgba(148,158,190,0.55)";
                ctx.font = "26px system-ui, sans-serif";
                ctx.fillText("✎", x + w / 2, y + h / 2 - 26);
                ctx.fillStyle = "rgba(168,178,208,0.78)";
                ctx.font = "600 13px system-ui, sans-serif";
                ctx.fillText("Click to place roto points", x + w / 2, y + h / 2 + 2);
                ctx.fillStyle = "rgba(128,138,166,0.6)";
                ctx.font = "11px system-ui, sans-serif";
                ctx.fillText("Right-click removes the nearest point", x + w / 2, y + h / 2 + 20);
                ctx.textAlign = "left";
                ctx.textBaseline = "alphabetic";
            }
            const sx = w / state.canvas.w;
            const sy = h / state.canvas.h;
            // Polyline
            ctx.strokeStyle = _tok("--c2c-blue", "#5cf");
            ctx.lineWidth = 1.5;
            ctx.beginPath();
            frame.points.forEach((p, i) => {
                const px = x + p[0] * sx;
                const py = y + p[1] * sy;
                if (i === 0) ctx.moveTo(px, py);
                else ctx.lineTo(px, py);
            });
            if (state.closed && frame.points.length > 2) ctx.closePath();
            ctx.stroke();
            // Vertices
            ctx.fillStyle = _tok("--c2c-yellow", "#fc6");
            frame.points.forEach(p => {
                ctx.beginPath();
                ctx.arc(x + p[0] * sx, y + p[1] * sy, 4, 0, Math.PI * 2);
                ctx.fill();
            });
            ctx.fillStyle = _tok("--c2c-sub", "#aaa");
            ctx.font = "10px monospace";
            ctx.fillText(`frame ${state.currentFrame + 1}/${state.frames.length}  pts:${frame.points.length}`, x + 6, y + 14);
            ctx.restore();
        },
        mouse(event, pos, node) {
            if (event.type !== "pointerdown") return false;
            const w = widget.size?.[0] || 320;
            const h = 320;
            const sx = state.canvas.w / w;
            const sy = state.canvas.h / h;
            const px = pos[0] * sx;
            const py = pos[1] * sy;
            const frame = state.frames[state.currentFrame];
            // Right-click removes nearest; left-click adds.
            if (event.button === 2) {
                let bestI = -1, bestD = 1e9;
                frame.points.forEach((p, i) => {
                    const d = (p[0] - px) ** 2 + (p[1] - py) ** 2;
                    if (d < bestD) { bestD = d; bestI = i; }
                });
                if (bestI >= 0 && bestD < 100) {
                    frame.points.splice(bestI, 1);
                    frame.in.splice(bestI, 1);
                    frame.out.splice(bestI, 1);
                    frame.feather.splice(bestI, 1);
                }
            } else {
                frame.points.push([px, py]);
                frame.in.push([px, py]);
                frame.out.push([px, py]);
                frame.feather.push(0);
            }
            sync();
            node.setDirtyCanvas(true, true);
            return true;
        },
    };

    function sync() {
        if (stateWidget) stateWidget.value = JSON.stringify({
            frames: state.frames,
            closed: state.closed,
            canvas: state.canvas,
        });
    }

    sync();
    installCanvasWidget(node, widget, 320);   // classic path unchanged; adds Vue DOM canvas
    // Grow the node so the freshly-reserved 320px editor row fits on creation
    // (computeSize now includes it; without this the node opened at ~200px).
    try {
        const sz = node.computeSize();
        node.setSize([Math.max(node.size?.[0] || 0, sz[0], 360), Math.max(node.size?.[1] || 0, sz[1])]);
    } catch (_) {}
    return widget;
}

app.registerExtension({
    name: "NukeMax.Roto",
    async beforeRegisterNodeDef(nodeType, nodeData, app) {
        if (nodeData.name !== NODE_NAME) return;
        const onCreated = nodeType.prototype.onNodeCreated;
        nodeType.prototype.onNodeCreated = function () {
            onCreated?.apply(this, arguments);
            try { createRotoWidget(this); } catch (e) { console.error("[NukeMax] roto widget failed", e); }
        };
    },
});
