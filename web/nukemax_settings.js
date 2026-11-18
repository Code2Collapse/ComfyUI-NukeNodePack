// NukeMax settings (L3.02; design docs/research/L3_settings_secrets_audit.md S9 in the C2C workspace). Declared here
// so they exist when NukeMax is installed alone; the backend reads the saved values through
// nukemax/_c2c_saved_setting.py. NUKEMAX_UPLOAD_MAX_MB still wins for both when it is set.
import { app } from "../../scripts/app.js";

app.registerExtension({
    name: "C2C.NukeMax.Settings",
    settings: [
        {
            id: "c2c.nukemax.uploadMaxMB.exr",
            name: "Largest EXR upload (MB)",
            category: ["C2C", "NukeMax", "Upload", "exr"],
            type: "number",
            defaultValue: 4096,
            attrs: { min: 1, max: 1000000, step: 1 },
            tooltip: "Biggest single file the EXR reader accepts from its upload button. "
                + "The environment variable NUKEMAX_UPLOAD_MAX_MB overrides this when it is set.",
        },
        {
            id: "c2c.nukemax.uploadMaxMB.media",
            name: "Largest media upload (MB)",
            category: ["C2C", "NukeMax", "Upload", "media"],
            type: "number",
            defaultValue: 16384,
            attrs: { min: 1, max: 1000000, step: 1 },
            tooltip: "Biggest single file the media reader accepts from its upload button. "
                + "The environment variable NUKEMAX_UPLOAD_MAX_MB overrides this when it is set.",
        },
    ],
});
