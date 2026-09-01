// Feature flags — build-time constants, not runtime config.
//
// SIM_ENABLED hides the full simulation tier from the UI while panel is the
// product. Nothing is deleted: the routes, the API modules and the whole
// backend sim pipeline stay exactly where they are, so flipping this back to
// true restores the entry points. Backend endpoints are deliberately NOT
// blocked — this is a UI-level hide only.
export const SIM_ENABLED = false
