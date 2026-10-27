/** In-memory, profile-wide management draft. No source states are persisted. */
const clone = (value) => structuredClone(value);
const canonical = (value) => {
  if (Array.isArray(value)) return value.map(canonical);
  if (value && typeof value === "object") {
    return Object.fromEntries(Object.keys(value).sort().map((key) => [key, canonical(value[key])]));
  }
  return value;
};
export const equalValues = (a, b) => JSON.stringify(canonical(a)) === JSON.stringify(canonical(b));

export const SECTIONS = ["overview", "profile", "operations", "power", "tanks", "tires", "systems"];

export function fieldSection(group, name) {
  if (name.startsWith("operations_")) return "operations";
  if (group === "power") return "power";
  if (name.startsWith("tire_")) return "tires";
  if (name.includes("water_tank") || name.startsWith("tank_")) return "tanks";
  if (name.endsWith("_entities")) return "systems";
  return group === "profile" ? "profile" : "systems";
}

/** Match HA entity selectors, including OR filters and legacy domain arrays. */
export function entityChoices(states, selector, selected = []) {
  const config = selector.entity || {};
  const filters = config.filter ? (Array.isArray(config.filter) ? config.filter : [config.filter]) : [config];
  const matches = (id, state) => filters.some((filter) => {
    const domains = filter.domain ? [].concat(filter.domain) : [];
    const classes = filter.device_class ? [].concat(filter.device_class) : [];
    return (!domains.length || domains.includes(id.split(".")[0])) &&
      (!classes.length || classes.includes(state.attributes?.device_class)) &&
      (!filter.integration || state.platform === filter.integration);
  });
  const ids = new Set(Object.entries(states || {}).filter(([id, state]) => matches(id, state)).map(([id]) => id));
  for (const id of [].concat(selected || [])) if (id) ids.add(id);
  return [...ids].sort().map((id) => ({
    value: id,
    label: states?.[id]?.attributes?.friendly_name
      ? `${states[id].attributes.friendly_name} (${id})` : id,
    unavailable: !states?.[id] || ["unavailable", "unknown"].includes(states[id].state),
  }));
}

export class ConfigDraft {
  constructor(callWS, entryId) {
    this.callWS = callWS;
    this.entryId = entryId;
    this.snapshot = null;
    this.values = null;
    this.schema = null;
    this.errors = [];
    this.impacts = [];
    this.error = null;
    this.busy = false;
    this.uncertain = false;
    this.reloadState = null;
    this.saved = false;
    this.generation = 0;
    this.wait = (milliseconds) => new Promise((resolve) => setTimeout(resolve, milliseconds));
  }

  request(action, extra = {}) {
    return this.callWS({ type: `havrv/config/${action}`, entry_id: this.entryId, ...extra });
  }

  /** Only explicit load/discard replaces the entire draft, never a hass update. */
  async load() {
    if (this.busy) return false;
    this.busy = true;
    try {
      this.accept(await this.request("get"));
      return true;
    } catch (error) {
      this.error = error.code || "connection";
      return false;
    } finally {
      this.busy = false;
    }
  }

  accept(snapshot) {
    this.snapshot = clone(snapshot);
    this.values = clone(snapshot.values);
    this.schema = clone(snapshot.schema);
    this.errors = [];
    this.impacts = [];
    this.error = null;
    this.uncertain = false;
    this.reloadState = snapshot.entry_state;
    if (snapshot.reload_result === "failed") this.reloadState = "reload_failed";
    else if (snapshot.reload_result === "pending") this.reloadState = "reload_pending";
    else if (snapshot.reload_result === "restart_required") this.reloadState = "restart_required";
    this.generation++;
  }

  discard() {
    if (!this.busy && this.snapshot) this.accept(this.snapshot);
  }

  fields() {
    return [
      ...(this.schema?.profile || []).map((field) => ({ ...field, group: "profile" })),
      ...(this.schema?.options || []).map((field) => ({ ...field, group: "options" })),
      ...(this.schema?.power || []).flatMap((source) => source.fields.map((field) => ({
        ...field, group: "power", source: source.key,
      }))),
    ].filter((field) => field.name !== "name" && field.name !== "configure_power_sources");
  }

  value(group, name, source) {
    return (group === "power" ? this.values?.power?.[source] : this.values?.[group])?.[name];
  }

  setValue(group, name, value, source) {
    if (this.busy || !this.values || name === "name") return false;
    if (group === "profile" && name === "measurement_system" && value !== this.values.unit_system) {
      const activeOptions = new Set(this.schema.options.map((field) => field.name));
      const hiddenQuantities = Object.keys(this.values.options).some((key) =>
        !activeOptions.has(key) && (/^tire_.*_pressure_(low|high)$/.test(key) || key === "tire_temperature_high"));
      // The API converts submitted quantities, not inactive in-memory archives.
      // Do not silently reinterpret a hidden threshold on later restoration.
      if (hiddenQuantities) { this.error = "inactive_units"; return false; }
    }
    const target = group === "power"
      ? (this.values.power[source] ||= {}) : this.values[group];
    if (value === undefined) delete target[name];
    else target[name] = clone(value);
    this.errors = [];
    this.error = null;
    this.generation++;
    return true;
  }

  /** Submit only active editable fields; hidden source drafts remain in memory. */
  payload() {
    const result = { profile: {}, options: {}, power: {}, unit_system: this.values.unit_system };
    for (const field of this.fields()) {
      const value = this.value(field.group, field.name, field.source);
      if (field.group === "power") result.power[field.source] ||= {};
      if (value !== undefined) {
        (field.group === "power" ? result.power[field.source] : result[field.group])[field.name] = clone(value);
      }
    }
    return result;
  }

  changes() {
    if (!this.snapshot) return [];
    const result = [];
    // Include inactive fields so reducing a layout does not hide pending removals.
    const paths = (values) => {
      const entries = [];
      for (const group of ["profile", "options"]) {
        for (const [name, value] of Object.entries(values[group] || {})) entries.push({ group, name, value });
      }
      for (const [source, fields] of Object.entries(values.power || {})) {
        for (const [name, value] of Object.entries(fields)) entries.push({ group: "power", source, name, value });
      }
      return entries;
    };
    const all = new Map();
    for (const item of [...paths(this.snapshot.values), ...paths(this.values)]) {
      all.set(JSON.stringify([item.group, item.source, item.name]), item);
    }
    for (const field of all.values()) {
      const before = (field.group === "power" ? this.snapshot.values.power?.[field.source] : this.snapshot.values[field.group])?.[field.name];
      const after = this.value(field.group, field.name, field.source);
      if (field.name !== "name" && !equalValues(before, after)) result.push({ ...field, before, after });
    }
    return result;
  }

  get dirty() { return this.changes().length > 0; }

  /** Validation is read-only; invalid results and websocket errors retain edits. */
  async validate() {
    const generation = this.generation;
    const submitted = this.payload();
    const previousFields = this.fields();
    const result = await this.request("validate", {
      revision: this.snapshot.revision, values: submitted,
    });
    if (generation !== this.generation) return { valid: false, stale: true };
    this.errors = result.errors || [];
    this.impacts = result.impacts || [];
    // Invalid responses can describe the old persisted layout and partial
    // normalized/default values. They are diagnostics, not a replacement draft.
    if (!result.valid) return result;
    if (result.schema) this.schema = clone(result.schema);
    if (result.values) {
      const activeFields = new Set(this.fields().map((field) =>
        `${field.group}:${field.source || ""}:${field.name}`));
      // Normalized values include conversions on unit switches. Keep inactive
      // source drafts without resurrecting explicitly cleared active fields.
      for (const field of previousFields) {
        if (!activeFields.has(`${field.group}:${field.source || ""}:${field.name}`)) continue;
        const target = field.group === "power"
          ? (this.values.power[field.source] ||= {}) : this.values[field.group];
        delete target[field.name];
      }
      Object.assign(this.values.profile, clone(result.values.profile || {}));
      for (const [name, value] of Object.entries(result.values.options || {})) {
        // Some normalizers return empty mapping groups. Do not materialize an
        // omitted optional group merely by validating another setting.
        if (Array.isArray(value) && !value.length && !(name in submitted.options)) continue;
        this.values.options[name] = clone(value);
      }
      for (const [source, fields] of Object.entries(result.values.power || {})) {
        Object.assign(this.values.power[source] ||= {}, clone(fields));
      }
      this.values.unit_system = result.values.unit_system;
    }
    return result;
  }

  async refreshSchema() {
    if (this.busy || !this.snapshot) return;
    this.busy = true;
    try { await this.validate(); }
    catch (error) { this.error = error.code || "connection"; }
    finally { this.busy = false; }
  }

  async apply(confirm) {
    if (this.busy || !this.dirty || this.uncertain) return false;
    this.busy = true;
    this.error = null;
    let writing = false;
    try {
      const validation = await this.validate();
      if (!validation.valid || !(await confirm(this.changes(), this.impacts))) return false;
      writing = true;
      const response = await this.request("apply", {
        revision: this.snapshot.revision, values: this.payload(),
        confirm_impacts: this.impacts.length > 0,
      });
      if (!response.saved && !response.unchanged) {
        this.error = "invalid_config";
        return false;
      }
      // Persisted success is distinct from runtime reload success. Do not retry
      // this write if status polling fails.
      this.snapshot = {
        ...this.snapshot, revision: response.revision,
        values: clone(this.payload()), schema: clone(this.schema),
      };
      this.values = clone(this.snapshot.values);
      this.reloadState = response.reload_required ? "reload_pending" : "loaded";
      this.saved = true;
      this.errors = [];
      this.impacts = [];
      if (response.reload_required) await this.waitForReload();
      return true;
    } catch (error) {
      this.error = error.code || "connection";
      this.uncertain = writing && !new Set([
        "conflict", "not_found", "not_loaded", "invalid_config",
        "confirmation_required", "unauthorized", "forbidden",
      ]).has(error.code);
      return false;
    } finally { this.busy = false; }
  }

  async checkStatus() {
    try {
      const current = await this.request("get");
      this.reloadState = current.reload_result === "restart_required" ? "restart_required"
        : current.reload_result === "pending" ? "reload_pending"
        : current.reload_result === "failed" ? "reload_failed" : current.entry_state;
      // Reconciliation after an interrupted write never discards a draft.
      // A different revision must be explicitly loaded before further writes.
      if (this.uncertain) {
        this.error = current.revision === this.snapshot.revision ? "not_saved" : "conflict";
      }
      return current;
    } catch (error) {
      this.reloadState = "status_unknown";
      this.error = error.code || "connection";
      return null;
    }
  }

  /** Bounded observation only: a temporary unload is not a failed save/reload. */
  async waitForReload() {
    for (let attempt = 0; attempt < 8; attempt++) {
      const current = await this.checkStatus();
      if (!current || ["loaded", "reload_failed", "restart_required"].includes(this.reloadState)) return;
      this.reloadState = "reload_pending";
      if (attempt < 7) await this.wait(500);
    }
  }

  async retryReload() {
    if (this.dirty || this.busy || this.uncertain) return;
    this.busy = true;
    try {
      const result = await this.request("reload");
      if (typeof result.loaded !== "boolean" || typeof result.restart_required !== "boolean") {
        this.error = "invalid_reload_result";
        this.reloadState = "status_unknown";
        return;
      }
      this.error = null;
      this.reloadState = result.restart_required ? "restart_required" : result.loaded ? "loaded" : "reload_failed";
      await this.checkStatus();
      // A response is an actual reload outcome, not merely acknowledgement.
      // Never let a lingering loaded entry state hide a failed unload/reload.
      if (result.restart_required) this.reloadState = "restart_required";
      else if (!result.loaded) this.reloadState = "reload_failed";
    } catch (error) { this.error = error.code || "connection"; }
    finally { this.busy = false; }
  }
}
