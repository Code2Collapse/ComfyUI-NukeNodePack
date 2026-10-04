// _vue_canvas.js — renderer-aware canvas widget install.
//
// LiteGraph "custom" widgets (node.addCustomWidget with a draw(ctx,…) +
// mouse() pair) are NOT rendered under ComfyUI's Nodes 2.0 / Vue renderer —
// Vue never calls draw(), so these editors show up blank there. This adapter
// keeps the CLASSIC path byte-identical (it just calls addCustomWidget) and,
// only when Vue nodes is active, additionally mounts a real <canvas> DOM
// widget that drives the SAME draw()/mouse() logic. The classic renderer —
// the default, and what everything is tuned for — is therefore never touched.
//
// Usage in a widget file, replacing `node.addCustomWidget(widget);`:
//     import { installCanvasWidget } from "../_vue_canvas.js";
//     installCanvasWidget(node, widget, 320);   // 320 = drawn height in px

function _vueActive() {
    try {
        return window.app?.ui?.settings?.getSettingValue?.("Comfy.VueNodes.Enabled") === true;
    } catch (_) {
        return false;
    }
}

export function installCanvasWidget(node, widget, height) {
    // Classic renderer: identical to the original call — zero behaviour change.
    node.addCustomWidget(widget);
    if (!_vueActive()) return widget;

    // Vue renderer: hide the custom widget from Vue (canvasOnly skips it) and
    // mount a DOM <canvas> that runs the widget's own draw()/mouse().
    widget.options = widget.options || {};
    widget.options.canvasOnly = true;          // Vue's shouldRenderAsVue() skips it
    widget.computeSize = () => [0, -4];         // don't double-count height

    const host = document.createElement("div");
    host.style.cssText = `width:100%;height:${height}px;position:relative;overflow:hidden;`;
    const cvs = document.createElement("canvas");
    cvs.style.cssText = "width:100%;height:100%;display:block;outline:none;touch-action:none;";
    cvs.tabIndex = 0;
    host.appendChild(cvs);

    let domWidget;
    try {
        domWidget = node.addDOMWidget(widget.name + "_vue", "canvas", host, {
            serialize: false,
            getMinHeight: () => height,
            getHeight: () => height,
        });
    } catch (_) {
        return widget;   // addDOMWidget unavailable — classic path already ran
    }

    const ctx = cvs.getContext("2d");
    let raf = 0;

    // Everything below works in the node's own (unzoomed) pixels. The screen
    // rect is zoomed by the canvas transform, so it is only used to convert
    // pointer positions and to pick a sharp backing-store size. (The old loop
    // drew with the zoomed width and the unzoomed height: stretched at zoom != 1.)
    const layoutW = () => Math.max(1, cvs.clientWidth || 320);

    const localXY = (e) => {
        const r = cvs.getBoundingClientRect();
        const x = (e.clientX - r.left) * (layoutW() / (r.width || 1));
        const y = (e.clientY - r.top) * (height / (r.height || height));
        return [x, y];
    };

    const forward = (e, type) => {
        try {
            widget.mouse?.({ type, button: e.button, buttons: e.buttons,
                             shiftKey: e.shiftKey, ctrlKey: e.ctrlKey,
                             altKey: e.altKey, metaKey: e.metaKey,
                             deltaY: e.deltaY, deltaX: e.deltaX },
                           localXY(e), node);
        } catch (_) { /* a handler error must not stop redraws */ }
        invalidate();
    };
    cvs.addEventListener("pointerdown", (e) => { cvs.focus(); forward(e, "pointerdown"); e.stopPropagation(); });
    cvs.addEventListener("pointermove", (e) => forward(e, "pointermove"));
    cvs.addEventListener("pointerup",   (e) => forward(e, "pointerup"));
    cvs.addEventListener("wheel",       (e) => forward(e, "wheel"), { passive: true });
    cvs.addEventListener("contextmenu", (e) => e.preventDefault());

    // Draw on demand, not every frame. This used to repaint 60 times a second
    // for every such node, forever, with a forced layout read each time. Now a
    // frame is drawn when something asks for one: pointer input, a resize, the
    // node coming into view, or node.setDirtyCanvas() - which is how both
    // users of this adapter announce their changes. A 2/s redraw while the node
    // is on screen catches state that changed without saying so.
    let visible = true;
    const draw = () => {
        raf = 0;
        if (node.graph == null) return teardown();
        if (!visible || document.hidden) return;
        const w = layoutW();
        const zoom = Math.max(0.25, (cvs.getBoundingClientRect().width || w) / w);
        const k = (window.devicePixelRatio || 1) * Math.min(zoom, 3);
        const pw = Math.round(w * k), ph = Math.round(height * k);
        if (cvs.width !== pw || cvs.height !== ph) { cvs.width = pw; cvs.height = ph; }
        ctx.setTransform(k, 0, 0, k, 0, 0);
        ctx.clearRect(0, 0, w, height);
        widget.size = [w, height];          // keep the mouse handler's scaling correct
        try { widget.draw(ctx, node, w, 0, height); } catch (_) { /* next frame may succeed */ }
    };
    function invalidate() { if (!raf) raf = requestAnimationFrame(draw); }

    const ro = typeof ResizeObserver === "function" ? new ResizeObserver(invalidate) : null;
    ro?.observe(cvs);
    const io = typeof IntersectionObserver === "function"
        ? new IntersectionObserver((es) => { visible = es.some((x) => x.isIntersecting); if (visible) invalidate(); })
        : null;
    io?.observe(host);
    const heartbeat = setInterval(() => { if (visible && !document.hidden) invalidate(); }, 500);

    const ownDirty = node.setDirtyCanvas;
    node.setDirtyCanvas = function (...a) {
        invalidate();
        return ownDirty?.apply(this, a);
    };
    invalidate();

    let tornDown = false;
    function teardown() {
        if (tornDown) return;
        tornDown = true;
        if (raf) cancelAnimationFrame(raf);
        raf = 0;
        clearInterval(heartbeat);
        ro?.disconnect();
        io?.disconnect();
    }

    const origRemoved = node.onRemoved;
    node.onRemoved = function (...a) {
        teardown();
        try { host.remove(); } catch (_) {}
        return origRemoved?.apply(this, a);
    };

    return widget;
}
