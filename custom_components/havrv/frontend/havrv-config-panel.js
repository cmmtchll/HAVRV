// Carry the content revision into sibling imports instead of letting a cached
// helper module survive an integration upgrade.
const moduleUrl = (name) => new URL(`${name}${new URL(import.meta.url).search}`, import.meta.url).href;
const { ConfigDraft, SECTIONS, entityChoices, fieldSection } = await import(moduleUrl("./havrv-config-model.js"));
const { t } = await import(moduleUrl("./havrv-config-en.js"));

const STYLE = `
  :host{display:block;height:100%;overflow:auto;color:var(--primary-text-color,#212121);
    background:var(--primary-background-color,#fafafa);font:14px var(--paper-font-body1_-_font-family,Roboto,Arial,sans-serif)}
  *{box-sizing:border-box}button,input,select,textarea{font:inherit}button,a,input,select,textarea{outline-offset:4px}
  button{cursor:pointer;border:1px solid var(--divider-color,#ddd);border-radius:20px;padding:10px 17px;
    background:var(--card-background-color,#fff);color:var(--primary-color,#03a9f4);min-height:42px}
  button:disabled{opacity:.5;cursor:default}.primary{background:var(--primary-color,#03a9f4);color:var(--text-primary-color,#fff)}
  a{color:var(--primary-color,#03a9f4)}h1{font-size:21px;font-weight:500;margin:0}h2{font-size:26px;font-weight:500}
  h3{font-size:18px;font-weight:500}p{line-height:1.6}.muted,small{color:var(--secondary-text-color,#666)}
  header{display:flex;align-items:center;gap:18px;padding:18px 26px;background:var(--card-background-color,#fff);
    border-bottom:1px solid var(--divider-color,#ddd)}header strong{margin-left:auto}
  nav{display:flex;overflow:auto;background:var(--card-background-color,#fff);border-bottom:1px solid var(--divider-color,#ddd)}
  nav button{border:0;border-radius:0;white-space:nowrap;padding:18px;border-bottom:3px solid transparent}
  nav button[aria-selected=true]{border-bottom-color:var(--primary-color,#03a9f4)}
  main{max-width:1150px;margin:auto;padding:20px 28px 150px}section.card,.card{border:1px solid var(--divider-color,#ddd);
    background:var(--card-background-color,#fff);border-radius:12px;padding:22px;margin:18px 0}
  .grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:20px}.grid>.card{margin:0}
  .fields{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:22px}
  .field{min-width:0;padding:12px;border:1px solid var(--divider-color,#bbb);border-radius:8px}
  .field.changed{border-color:var(--primary-color,#03a9f4)}.field label{display:block;font-size:13px;margin-bottom:9px}
  .field input:not([type=checkbox]),.field select,.field textarea{width:100%;padding:10px;
    border:1px solid var(--divider-color,#bbb);border-radius:4px;color:var(--primary-text-color,#212121);
    background:var(--card-background-color,#fff);min-height:42px}
  .field small{display:block;margin:9px 0;line-height:1.5}.field button{padding:6px 12px;margin:6px 5px 0 0}
  .field-heading{display:flex;align-items:baseline;flex-wrap:wrap;gap:6px 12px;margin-bottom:8px}
  .field-heading label{margin:0}.field-heading small{margin:0;overflow-wrap:anywhere;min-width:0}
  .field-heading .source-identity{flex:1;min-width:100px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
  .control-row{display:flex;align-items:center;gap:8px;min-width:0}
  .control-row>input,.control-row>select,.control-row>textarea{flex:1;min-width:0}
  .control-row button{flex:none;margin:0;min-width:42px}
  .field .clear-control{border-radius:50%;width:42px;padding:0;font-size:22px}
  .field button.source-value{margin:0;padding:0 4px;border:0;border-radius:0;background:none;
    color:var(--primary-text-color,#212121);font:inherit;font-weight:400;text-align:end;
    white-space:nowrap;max-width:40%;overflow:hidden;text-overflow:ellipsis;min-height:42px}
  .field button.source-value:disabled{opacity:1;color:var(--secondary-text-color,#666)}
  .field button.source-value:focus-visible{outline:2px solid var(--primary-color,#03a9f4)}
  .source-list{padding:0;list-style:none}.source-list li{display:flex;align-items:center;flex-wrap:wrap;gap:8px;margin:8px 0}
  .source-list small{flex:1;min-width:0;overflow-wrap:anywhere;margin:0}
  .system-workspace{display:grid;grid-template-columns:240px minmax(0,1fr);gap:22px;align-items:start}
  .system-sidebar,.system-editor{min-width:0}.system-sidebar>.card{margin:18px 0}
  .selection-list.card{padding:0;overflow:hidden}.selection-list h3{padding:16px;margin:0}
  .selection-list .selection-items{max-height:520px;overflow:auto}
  .selection-list button,.action-row{display:flex;align-items:center;gap:14px;width:100%;padding:18px;
    text-align:start;color:var(--primary-text-color,#212121);border:0;border-radius:0;
    border-top:1px solid var(--divider-color,#ddd);background:transparent;text-decoration:none;min-width:0}
  .selection-list button[aria-pressed=true]{background:var(--secondary-background-color,#eee);
    box-shadow:inset 3px 0 var(--primary-color,#03a9f4)}
  .row-copy{display:flex;flex-direction:column;gap:6px;min-width:0;flex:1}
  .row-copy strong{font-weight:500}.row-copy small{line-height:1.5;overflow-wrap:anywhere}
  .row-icon{flex:none;color:var(--primary-color,#03a9f4);--mdc-icon-size:24px}
  .row-chevron{color:var(--secondary-text-color,#666);font-size:22px}
  .overview-grid{align-items:start}.overview-grid>.card{min-width:0}.overview-grid h3{margin:0 0 18px}
  .overview-grid .action-row{padding:16px 0}.profile-summary{margin:0}
  .overview-grid li button{max-width:100%;overflow-wrap:anywhere;text-align:start}
  .profile-summary>div{display:flex;justify-content:space-between;gap:18px;padding:14px 0;
    border-bottom:1px solid var(--divider-color,#ddd)}.profile-summary dt{color:var(--secondary-text-color,#666)}
  .profile-summary dd{margin:0;text-align:end;overflow-wrap:anywhere}
  .overview-grid .stats{margin-top:20px}.overview-grid .stat strong{font-size:24px}
  .overview-grid .stat span{font-size:12px;color:var(--secondary-text-color,#666)}
  .selected-heading{margin:18px 0 0}.system-editor .fields{margin-top:16px}
  .tire-map.card{padding:16px;margin:18px 0}
  .tire-map h3{font-size:16px;margin:0 0 8px}.tire-map p{font-size:12px}
  .coach{position:relative;margin:24px 14px;height:360px;border:2px solid var(--divider-color,#aaa);
    border-radius:36px 36px 22px 22px;background:var(--secondary-background-color,#eee)}
  .coach::before{content:"";position:absolute;top:20px;left:16%;width:68%;height:44px;
    border-radius:12px 12px 4px 4px;background:var(--primary-color,#03a9f4);opacity:.18}
  .coach-name{position:absolute;left:18%;right:18%;top:42%;text-align:center;font-size:11px;
    letter-spacing:1px;overflow-wrap:anywhere;color:var(--secondary-text-color,#666)}
  .coach .tire-position{position:absolute;width:19px;min-height:40px;padding:0;margin:0;border-radius:5px;
    border:2px solid var(--secondary-text-color,#777);background:var(--card-background-color,#fff)}
  .coach .tire-position[aria-pressed=true]{border-color:var(--primary-color,#03a9f4);background:var(--primary-color,#03a9f4)}
  .coach .tire-position.missing{border-style:dashed}
  @media(max-width:1100px){.system-workspace{grid-template-columns:210px minmax(0,1fr)}.system-editor .fields{grid-template-columns:1fr}}
  .error{color:var(--error-color,#db4437)}.notice{border-left:4px solid var(--primary-color,#03a9f4);padding:12px 18px;
    background:var(--secondary-background-color,#eee);margin:18px 0;line-height:1.6}.notice.error{border-color:var(--error-color,#db4437)}
  .stats{display:flex;flex-wrap:wrap;gap:26px}.stat strong{display:block;font-size:26px;font-weight:500}
  .links{display:flex;flex-wrap:wrap;gap:12px;margin-top:20px}.search{width:100%;padding:12px;margin:8px 0}
  footer{position:sticky;bottom:0;display:flex;align-items:center;gap:12px;padding:16px 28px;
    border-top:1px solid var(--divider-color,#ddd);background:var(--card-background-color,#fff);z-index:2}
  footer .draft{flex:1}footer small{display:block;margin-top:5px}
  dialog{max-width:680px;width:calc(100% - 32px);max-height:85vh;overflow:auto;border:1px solid var(--divider-color,#ddd);
    border-radius:12px;padding:24px;color:var(--primary-text-color,#212121);background:var(--card-background-color,#fff)}
  dialog::backdrop{background:#0008}dialog li{margin:12px 0;overflow-wrap:anywhere}.actions{display:flex;justify-content:flex-end;gap:12px}
  @media(max-width:700px){header{padding:15px}.grid,.fields{grid-template-columns:1fr}main{padding:16px 16px 70px}
    footer{padding:12px 16px;flex-wrap:wrap}footer .draft{flex-basis:100%}footer button{flex:1}nav button{padding:16px 12px}
    header strong{max-width:40%;overflow-wrap:anywhere}.card{padding:16px}
    .system-workspace{grid-template-columns:1fr}.tire-map.card{max-width:230px;width:100%;margin:12px auto}
    .selection-list .selection-items{display:grid;grid-auto-flow:column;grid-auto-columns:200px;max-height:none}
    .coach{height:280px}}
`;

/** Only textContent and DOM properties receive backend/entity/user strings. */
function element(tag, text, attributes = {}) {
  const node = document.createElement(tag);
  if (text !== undefined && text !== null) node.textContent = String(text);
  for (const [key, value] of Object.entries(attributes)) {
    if (value !== undefined && value !== null) node.setAttribute(key, String(value));
  }
  return node;
}
function button(text, action, attributes = {}) {
  const node = element("button", text, { type: "button", ...attributes });
  node.addEventListener("click", action);
  return node;
}
const SECTION_ICONS = {
  power: "mdi:lightning-bolt", tanks: "mdi:water-outline",
  tires: "mdi:circle-double", systems: "mdi:swap-horizontal", devices: "mdi:devices", entities: "mdi:shape-outline",
};
const powerIcon = (source) => source.battery ? "mdi:car-battery"
  : source.key === "inverter" ? "mdi:sine-wave"
  : source.key === "generator" ? "mdi:engine" : "mdi:power-plug";
function rowContent(title, description, icon) {
  const copy = element("span", null, { class: "row-copy" });
  copy.append(element("strong", title), element("small", description));
  return [element("ha-icon", null, { icon, class: "row-icon", "aria-hidden": "true" }), copy];
}
const fieldId = (field) => `field-${field.group}-${field.source || ""}-${field.name}`;
const printable = (value) => value === undefined || (Array.isArray(value) && !value.length)
  ? t("unset") : Array.isArray(value) ? value.join(", ") : String(value);
const STRUCTURE_FIELDS = new Set([
  "measurement_system", "house_battery_bank_count", "chassis_battery_bank_count",
  "rear_axle_count", "main_rear_wheel_configuration", "tag_axle_present", "tag_axle_wheel_configuration",
]);

export class HavrvConfigPanel extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this.section = "overview";
    this.selectedPower = null;
    this.selectedTire = null;
    this._connected = false;
    this._sourcePreviews = [];
    this._tireIndicators = [];
    this._selectionSummaries = [];
    this._lastUrl = null;
    this._beforeUnload = (event) => {
      if (!this.model?.dirty) return;
      event.preventDefault();
      event.returnValue = "";
    };
    this._clickGuard = (event) => {
      const anchor = event.composedPath().find((node) => node.tagName === "A" && node.href);
      if (!anchor || anchor.target === "_blank" || anchor.hasAttribute("download") ||
          event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
      if (new URL(anchor.href, window.location.href).href === window.location.href) return;
      if (!this.canLeave()) {
        event.preventDefault();
        event.stopImmediatePropagation();
      }
    };
    this._locationChanged = (event) => {
      const next = window.location.href;
      if (next === this._lastUrl) return;
      if (!this.canLeave()) {
        event.preventDefault();
        event.stopImmediatePropagation();
        window.history.replaceState(null, "", this._lastUrl);
        return;
      }
      this._lastUrl = next;
      this.initialize();
      this.render();
    };
  }

  set hass(value) {
    this._hass = value;
    if (!this._connected) return;
    this.initialize();
    // Ordinary source-state updates never replace or normalize a draft.
    if (this.section === "overview" && !this.model?.busy) this.render();
    else this.updateSourcePreviews();
  }
  get hass() { return this._hass; }
  set panel(value) { this._panel = value; if (this._connected) this.initialize(); }
  get panel() { return this._panel; }

  connectedCallback() {
    this._connected = true;
    this._lastUrl = window.location.href;
    window.addEventListener("beforeunload", this._beforeUnload);
    window.addEventListener("popstate", this._locationChanged, true);
    window.addEventListener("location-changed", this._locationChanged, true);
    document.addEventListener("click", this._clickGuard, true);
    this.initialize();
    this.render();
  }

  disconnectedCallback() {
    this._connected = false;
    window.removeEventListener("beforeunload", this._beforeUnload);
    window.removeEventListener("popstate", this._locationChanged, true);
    window.removeEventListener("location-changed", this._locationChanged, true);
    document.removeEventListener("click", this._clickGuard, true);
    this._reviewResolve?.(false);
    this._reviewResolve = null;
  }

  canLeave() {
    if (this.model?.busy) return false;
    if (!this.model?.dirty) return true;
    if (!window.confirm(t("leaveConfirm"))) return false;
    this.model.discard();
    return true;
  }

  initialize() {
    if (!this.hass || this.hass.user?.is_admin === false) return;
    const entry = new URL(window.location.href).searchParams.get("config_entry");
    if (!entry) { this.model = null; return; }
    if (entry === this.model?.entryId) return;
    this.model = new ConfigDraft((message) => this.hass.callWS(message), entry);
    const model = this.model;
    const loading = model.load();
    this.render();
    loading.then(() => { if (this._connected && this.model === model) this.render(); });
  }

  async run(action, focusErrors = false) {
    const pending = action();
    this.render();
    await pending;
    if (!this._connected) return;
    this.render();
    if (focusErrors && (this.model.errors.length || this.model.error)) {
      this.shadowRoot.getElementById("errors")?.focus();
    }
  }

  navigate(section, field) {
    this.section = section;
    if (field?.source) this.selectedPower = field.source;
    if (field?.name?.startsWith("tire_")) {
      const position = this.model.schema.tires?.find((item) => field.name.startsWith(`tire_${item.key}_`));
      if (position) this.selectedTire = position.key;
    }
    this.render();
    this.shadowRoot.getElementById(field ? fieldId(field) : "section-title")?.focus();
  }

  label(field) {
    return field.label || this.model.snapshot.translations?.fields?.[field.name] || field.name.replaceAll("_", " ");
  }

  fieldError(field) {
    return this.model.errors.find((error) =>
      error.field === field.name && (field.group !== "power" ||
        !error.section?.startsWith("power.") || error.section === `power.${field.source}`));
  }

  errorText(error) {
    const translations = this.model.snapshot.translations;
    return error.message || translations?.errors?.[error.code] ||
      translations?.options?.error?.[error.code] || translations?.config?.error?.[error.code] ||
      t(`errors.${error.code}`);
  }

  renderErrors(main) {
    if (!this.model.error && !this.model.errors.length && !this.model.uncertain) return;
    const box = element("section", null, { class: "notice error", id: "errors", role: "alert", tabindex: "-1" });
    box.append(element("h3", t("errorSummary")));
    if (this.model.error) box.append(element("p", t(`errors.${this.model.error}`)));
    if (this.model.uncertain) box.append(element("p", t("uncertain")));
    const list = element("ul");
    for (const error of this.model.errors) {
      const fields = this.model.fields();
      const field = fields.find((item) => item.name === error.field &&
        (!error.section?.startsWith("power.") || error.section === `power.${item.source}`));
      const item = element("li");
      if (field) item.append(button(t("errorField", { field: this.label(field), error: this.errorText(error) }),
        () => this.navigate(fieldSection(field.group, field.name), field)));
      else if (SECTIONS.includes(error.section)) {
        item.append(button(this.errorText(error), () => {
          if (error.section === "power" && this.model.schema.power.some((source) => source.key === error.field)) {
            this.selectedPower = error.field;
          }
          this.navigate(error.section);
        }));
      } else item.append(element("span", this.errorText(error)));
      list.append(item);
    }
    box.append(list);
    box.append(button(t("refresh"), () => {
      if (!this.model.dirty || window.confirm(t("discardConfirm"))) this.run(() => this.model.load());
    }));
    if (this.model.uncertain) box.append(button(t("status"), () => this.run(() => this.model.checkStatus())));
    main.append(box);
  }

  render() {
    if (!this.shadowRoot) return;
    const activeId = this.shadowRoot.activeElement?.id;
    this._sourcePreviews = [];
    this._tireIndicators = [];
    this._selectionSummaries = [];
    const style = element("style", STYLE);
    const header = element("header");
    header.append(element("a", t("back"), { href: "/config/integrations/integration/havrv" }),
      element("h1", t("title")));
    if (this.model?.snapshot) header.append(element("strong", this.model.snapshot.profile.name || ""));
    const main = element("main");
    const fragment = document.createDocumentFragment();
    fragment.append(style, header);
    if (this.hass?.user?.is_admin === false) {
      main.append(element("p", t("readOnly"), { role: "alert" }));
    } else if (!this.model) {
      main.append(element("p", t("missingEntry"), { role: "status" }));
    } else if (!this.model.snapshot) {
      main.append(element("p", this.model.error ? t(`errors.${this.model.error}`) : t("loading"), { role: "status" }));
      if (this.model.error) main.append(button(t("refresh"), () => this.run(() => this.model.load())));
    } else {
      const nav = element("nav", null, { role: "tablist", "aria-label": t("navigation") });
      SECTIONS.forEach((section, index) => {
        const tab = button(t(section), () => this.navigate(section), {
          role: "tab", id: `tab-${section}`, "aria-selected": section === this.section,
          "aria-controls": "section", tabindex: section === this.section ? "0" : "-1",
        });
        tab.addEventListener("keydown", (event) => {
          let target;
          if (event.key === "ArrowRight") target = (index + 1) % SECTIONS.length;
          if (event.key === "ArrowLeft") target = (index + SECTIONS.length - 1) % SECTIONS.length;
          if (event.key === "Home") target = 0;
          if (event.key === "End") target = SECTIONS.length - 1;
          if (target === undefined) return;
          event.preventDefault();
          this.navigate(SECTIONS[target]);
          this.shadowRoot.getElementById(`tab-${SECTIONS[target]}`)?.focus();
        });
        nav.append(tab);
      });
      fragment.append(nav);
      this.renderErrors(main);
      if (this.model.saved) {
        const notice = element("div", null, { class: "notice", role: "status", "aria-live": "polite" });
        notice.append(element("strong", t(this.model.reloadState || "status_unknown")), element("p", t("savedHint")));
        notice.append(button(t("status"), () => this.run(() => this.model.checkStatus())));
        if (this.model.reloadState !== "loaded") {
          const retry = button(t("retryReload"), () => this.run(() => this.model.retryReload()));
          retry.disabled = this.model.busy || this.model.dirty || this.model.uncertain;
          notice.append(retry);
        }
        main.append(notice);
      }
      const section = element("section", null, {
        id: "section", role: "tabpanel", "aria-labelledby": `tab-${this.section}`,
        "aria-busy": this.model.busy,
      });
      section.append(element("h2", t(this.section === "overview" ? "overviewTitle" : this.section), { id: "section-title", tabindex: "-1" }),
        element("p", t(`${this.section === "overview" ? "overview" : this.section}Hint`), { class: "muted" }));
      if (this.section === "overview") this.renderOverview(section);
      else this.renderEditor(section);
      main.append(section);
    }
    fragment.append(main);
    if (this.model?.snapshot && this.hass?.user?.is_admin !== false) fragment.append(this.renderFooter());
    this.shadowRoot.replaceChildren(fragment);
    this.updateSourcePreviews();
    if (activeId) this.shadowRoot.getElementById(activeId)?.focus();
  }

  renderOverview(parent) {
    const snapshot = this.model.snapshot;
    const grid = element("div", null, { class: "grid overview-grid" });
    const card = element("section", null, { class: "card" });
    const state = this.model.reloadState || snapshot.entry_state;
    card.append(element("h3", t("integrationState")), element("p", t(state)));
    if (this.model.saved) card.append(element("p", t("savedHint")));
    const status = button(t("status"), () => this.run(() => this.model.checkStatus()));
    status.disabled = this.model.busy;
    card.append(status);
    if (state !== "loaded") {
      const retry = button(t("retryReload"), () => this.run(() => this.model.retryReload()));
      retry.disabled = this.model.busy || this.model.dirty || this.model.uncertain;
      card.append(retry);
    }
    const sources = new Set();
    const mappedFields = [];
    for (const field of this.model.fields()) {
      if (!field.selector?.entity) continue;
      for (const id of [].concat(this.model.value(field.group, field.name, field.source) || [])) if (id) {
        sources.add(id); mappedFields.push({ id, field });
      }
    }
    const unavailable = [...sources].filter((id) =>
      !this.hass.states[id] || ["unavailable", "unknown"].includes(this.hass.states[id].state));
    const stats = element("div", null, { class: "stats" });
    for (const [key, count] of [["devices", snapshot.devices], ["entities", snapshot.entities],
      ["sources", sources.size], ["unavailable", unavailable.length]]) {
      const stat = element("div", null, { class: "stat" });
      stat.append(element("strong", count), element("span", t(key)));
      stats.append(stat);
    }
    card.append(stats, element("p", t("availabilityHint"), { class: "muted" }));
    if (unavailable.length) {
      const list = element("ul");
      unavailable.forEach((id) => {
        const field = mappedFields.find((item) => item.id === id).field;
        const item = element("li");
        item.append(button(t("reviewSource", { entity: id }),
          () => this.navigate(fieldSection(field.group, field.name), field)));
        list.append(item);
      });
      card.append(list);
    }
    const entry = encodeURIComponent(this.model.entryId);
    const registry = element("section", null, { class: "card" });
    registry.append(element("h3", t("yourHomeAssistant")));
    for (const [key, href] of [
      ["devices", `/config/devices/dashboard?config_entry=${entry}`],
      ["entities", `/config/entities?config_entry=${entry}`],
    ]) {
      const link = element("a", null, { class: "action-row", href });
      link.append(...rowContent(t(key), t(`${key}Hint`), SECTION_ICONS[key]),
        element("span", "›", { class: "row-chevron", "aria-hidden": "true" }));
      registry.append(link);
    }
    const systems = element("section", null, { class: "card" });
    systems.append(element("h3", t("configureSystems")));
    for (const section of ["power", "tanks", "tires", "systems"]) {
      const row = button("", () => this.navigate(section), { class: "action-row", id: `configure-${section}` });
      const description = section === "power"
        ? t("powerSummary", { count: this.model.schema.power.filter((source) => source.battery).length })
        : section === "tires" ? t("tiresSummary", { count: this.model.schema.tires.length })
        : t(`${section}Summary`);
      row.append(...rowContent(t(section), description, SECTION_ICONS[section]),
        element("span", "›", { class: "row-chevron", "aria-hidden": "true" }));
      systems.append(row);
    }
    const profile = element("section", null, { class: "card" });
    profile.append(element("h3", t("profile")));
    const summary = element("dl", null, { class: "profile-summary" });
    const values = this.model.values.profile;
    const units = values.measurement_system || this.model.values.unit_system;
    const unitField = this.model.schema.profile.find((field) => field.name === "measurement_system");
    const unitOption = unitField?.selector?.select?.options.find((option) =>
      (typeof option === "object" ? option.value : option) === units);
    const axleField = this.model.schema.profile.find((field) => field.name === "rear_axle_count");
    const axleOption = axleField?.selector?.select?.options.find((option) =>
      (typeof option === "object" ? option.value : option) === values.rear_axle_count);
    const axles = typeof axleOption === "object" ? axleOption.label : axleOption;
    for (const [label, value] of [
      ["profileName", snapshot.profile.name],
      ["measurementSystem", typeof unitOption === "object" ? unitOption.label : t(units)],
      ["rearAxles", axles || values.rear_axle_count || t("unset")],
      ["batteryBanks", `${this.model.schema.power.filter((source) => source.key.startsWith("house_bank_")).length} / ${this.model.schema.power.filter((source) => source.key.startsWith("chassis_bank_")).length}`],
    ]) {
      const row = element("div");
      row.append(element("dt", t(label)), element("dd", value));
      summary.append(row);
    }
    profile.append(summary, button(t("editProfile"), () => this.navigate("profile"), { id: "edit-profile", class: "action-row" }),
      element("p", t("referenceHint"), { class: "muted" }),
      element("small", t("draftSummaryHint")));
    grid.append(card, registry, systems, profile);
    parent.append(grid);
  }

  renderEditor(parent) {
    let fields = this.model.fields().filter((field) => fieldSection(field.group, field.name) === this.section ||
      // Water capacities are the same profile fields in both editors, not
      // independently saved copies.
      (this.section === "profile" && field.group === "profile" && field.name.includes("water_tank_capacity")));
    if (this.section === "power") {
      const sources = this.model.schema.power || [];
      if (!sources.some((source) => source.key === this.selectedPower)) this.selectedPower = sources[0]?.key;
      const workspace = element("div", null, { class: "system-workspace" });
      const sidebar = element("div", null, { class: "system-sidebar" });
      sidebar.append(this.selectionList("source", sources, this.selectedPower));
      const editor = element("div", null, { class: "system-editor" });
      const source = sources.find((item) => item.key === this.selectedPower);
      editor.append(element("h3", source?.name || t("source"), { class: "selected-heading" }));
      const selected = fields.filter((field) => field.source === this.selectedPower);
      editor.append(element("h3", t("sourceMappings")));
      this.renderFields(editor, selected.filter((field) => field.selector?.entity));
      editor.append(element("h3", t("powerSpecifications")));
      this.renderFields(editor, selected.filter((field) => !field.selector?.entity));
      workspace.append(sidebar, editor);
      parent.append(workspace);
      return;
    }
    if (this.section === "tires") {
      const tires = this.model.schema.tires || [];
      if (!tires.some((item) => item.key === this.selectedTire)) this.selectedTire = tires[0]?.key;
      const positionFields = fields.filter((field) => tires.some((item) => field.name.startsWith(`tire_${item.key}_`)));
      const selected = positionFields.filter((field) => field.name.startsWith(`tire_${this.selectedTire}_`));
      const limits = fields.filter((field) => !positionFields.includes(field));
      const workspace = element("div", null, { class: "system-workspace" });
      const sidebar = element("div", null, { class: "system-sidebar" });
      sidebar.append(this.selectionList("position", tires, this.selectedTire), this.renderTireMap(tires));
      workspace.append(sidebar);
      const editor = element("div", null, { class: "system-editor" });
      editor.append(element("h3", tires.find((tire) => tire.key === this.selectedTire)?.name || t("position"), { class: "selected-heading" }));
      this.renderFields(editor, selected);
      editor.append(element("h3", t("limits")));
      this.renderFields(editor, limits);
      workspace.append(editor);
      parent.append(workspace);
      return;
    }
    this.renderFields(parent, fields);
  }

  renderTireMap(tires) {
    const map = element("section", null, { class: "tire-map card", "aria-label": t("configuredPositions") });
    map.append(element("h3", t("configuredPositions")), element("p", t("frontAtTop"), { class: "muted" }));
    const coach = element("div", null, { class: "coach", role: "group", "aria-label": t("position") });
    coach.append(element("span", this.model.snapshot.profile.name, { class: "coach-name" }));
    const axleKey = (tire) => tire.key.replace(/_(left|right)(_(inner|outer))?$/, "");
    const axles = [...new Set(tires.map(axleKey))];
    for (const tire of tires) {
      const key = axleKey(tire);
      const index = axles.indexOf(key);
      const top = key === "front" ? 22 : 82 - (axles.length - 1 - index) * 15;
      const side = tire.key.includes("_left") ? "left" : "right";
      const offset = tire.key.endsWith("_inner") ? 9 : -12;
      const wheel = button("", () => {
        this.selectedTire = tire.key; this.render();
        this.shadowRoot.getElementById(`tire-position-${tire.key}`)?.focus();
      }, {
        id: `tire-position-${tire.key}`, class: "tire-position",
        "aria-label": tire.name, "aria-pressed": tire.key === this.selectedTire,
        title: tire.name, style: `top:${top}%;${side}:${offset}px`,
      });
      wheel.disabled = this.model.busy;
      this._tireIndicators.push({ wheel, tire });
      coach.append(wheel);
    }
    map.append(coach, element("p", t("tireMapHint"), { class: "muted" }));
    return map;
  }

  sourcePreview(entityId, identity = true) {
    const name = identity ? element("small", "", { class: "source-identity" }) : null;
    const value = button("", () => {
      if (!this.hass.states[entityId]) return;
      this.dispatchEvent(new CustomEvent("hass-more-info", {
        detail: { entityId }, bubbles: true, composed: true,
      }));
    }, { class: "source-value" });
    this._sourcePreviews.push({ entityId, name, value });
    return { name, value };
  }

  updateSourcePreviews() {
    for (const { entityId, name, value } of this._sourcePreviews) {
      const state = this.hass?.states?.[entityId];
      const friendly = state?.attributes?.friendly_name;
      if (name) {
        name.textContent = friendly && friendly !== entityId ? `${friendly} (${entityId})` : entityId;
        name.title = name.textContent;
      }
      const missing = !state || ["unknown", "unavailable"].includes(state.state);
      let reading = missing ? t("unavailable") : state.state;
      if (state && this.hass.formatEntityState) reading = this.hass.formatEntityState(state);
      else if (!missing && state.attributes?.unit_of_measurement) reading += ` ${state.attributes.unit_of_measurement}`;
      value.textContent = reading;
      value.disabled = !state;
      value.title = t("showHistory", { entity: entityId });
      value.setAttribute("aria-label", `${value.title}: ${reading}`);
    }
    for (const { wheel, tire } of this._tireIndicators) {
      const ids = ["pressure", "temperature", "battery"]
        .map((metric) => this.model.value("options", `tire_${tire.key}_${metric}`)).filter(Boolean);
      const missing = ids.some((id) => !this.hass.states[id] ||
        ["unknown", "unavailable"].includes(this.hass.states[id].state));
      wheel.setAttribute("class", `tire-position${missing ? " missing" : ""}`);
      wheel.title = `${tire.name}${missing ? ` · ${t("unavailable")}` : ""}`;
    }
    for (const { summary, fields } of this._selectionSummaries) {
      const ids = [...new Set(fields.flatMap((field) =>
        [].concat(this.model.value(field.group, field.name, field.source) || [])))];
      const missing = ids.filter((id) => !this.hass.states[id] ||
        ["unknown", "unavailable"].includes(this.hass.states[id].state)).length;
      summary.textContent = ids.length ? t(ids.length === 1 ? "mappedSingle" : "mappedSummary", { count: ids.length })
        + (missing ? ` · ${t("unavailableCount", { count: missing })}` : "") : t("noSourcesMapped");
    }
  }

  selectionList(kind, items, selected) {
    const list = element("section", null, { class: "selection-list card", "aria-label": t(kind) });
    list.append(element("h3", t(kind)));
    const options = element("div", null, { class: "selection-items", role: "group", "aria-label": t(kind) });
    const choose = (key) => {
      if (kind === "source") this.selectedPower = key;
      else this.selectedTire = key;
      this.render();
      this.shadowRoot.getElementById(`select-${kind}-${key}`)?.focus();
    };
    for (const [index, item] of items.entries()) {
      const row = button("", () => choose(item.key), {
        id: `select-${kind}-${item.key}`, "aria-pressed": item.key === selected,
      });
      row.append(...rowContent(item.name, "", kind === "source" ? powerIcon(item) : SECTION_ICONS.tires));
      const summary = row.children[1].children[1];
      this._selectionSummaries.push({ summary, fields: this.model.fields().filter((field) =>
        field.selector?.entity && (kind === "source" ? field.source === item.key
          : field.name.startsWith(`tire_${item.key}_`))) });
      row.disabled = this.model.busy;
      row.addEventListener("keydown", (event) => {
        let target;
        if (event.key === "ArrowDown" || event.key === "ArrowRight") target = (index + 1) % items.length;
        if (event.key === "ArrowUp" || event.key === "ArrowLeft") target = (index + items.length - 1) % items.length;
        if (event.key === "Home") target = 0;
        if (event.key === "End") target = items.length - 1;
        if (target === undefined || this.model.busy) return;
        event.preventDefault();
        choose(items[target].key);
      });
      options.append(row);
    }
    if (!items.length) options.append(element("p", t("empty")));
    list.append(options);
    return list;
  }

  renderFields(parent, fields) {
    const grid = element("div", null, { class: "fields card" });
    for (const field of fields) grid.append(this.renderField(field));
    if (!fields.length) grid.append(element("p", t("empty")));
    parent.append(grid);
  }

  updateField(field, value) {
    if (!this.model.setValue(field.group, field.name, value, field.source)) { this.render(); return; }
    if (STRUCTURE_FIELDS.has(field.name)) this.run(() => this.model.refreshSchema(), true);
    else this.render();
  }

  renderField(field) {
    // The selected unit system is needed to interpret every numeric draft.
    // Native flow metadata marks profile fields optional, but clearing units
    // here would leave a draft whose quantities have no declared target units.
    if (field.name === "measurement_system") field = { ...field, required: true };
    const id = fieldId(field);
    const value = this.model.value(field.group, field.name, field.source);
    const changed = this.model.changes().some((change) => change.group === field.group &&
      change.name === field.name && change.source === field.source);
    const error = this.fieldError(field);
    const box = element("div", null, { class: `field${changed ? " changed" : ""}` });
    const heading = element("div", null, { class: "field-heading" });
    heading.append(element("label", `${this.label(field)}${field.required ? ` · ${t("required")}` : ""}`, { for: id }));
    box.append(heading);
    let preview;
    if (field.selector?.entity && !field.selector.entity.multiple && value) {
      preview = this.sourcePreview(value);
      heading.append(preview.name);
    }
    if (changed) heading.append(element("small", t("changed")));
    const row = element("div", null, { class: "control-row" });
    const selector = field.selector || { text: {} };
    let control;
    const onChange = (next) => this.updateField(field, next);
    if (selector.entity) {
      control = this.entityControl(field, value, box, row, onChange);
    } else if (selector.select || selector.boolean) {
      control = element("select", null, { id });
      const multiple = !!selector.select?.multiple;
      control.multiple = multiple;
      if (multiple) control.size = Math.min(8, Math.max(3, selector.select.options.length));
      if (!multiple && !field.required) control.append(element("option", t("unset"), { value: "" }));
      const options = selector.boolean ? [{ value: "true", label: t("yes") }, { value: "false", label: t("no") }]
        : selector.select.options.map((option) => typeof option === "object" ? option : { value: option, label: option });
      for (const option of options) {
        const node = element("option", option.label, { value: option.value });
        node.selected = multiple ? (value || []).includes(option.value) : String(value) === String(option.value);
        control.append(node);
      }
      if (!multiple) control.value = value === undefined ? "" : String(value);
      control.addEventListener("change", () => onChange(multiple
        ? [...control.selectedOptions].map((item) => item.value)
        : control.value === "" ? undefined : selector.boolean ? control.value === "true" : control.value));
    } else {
      control = element(selector.text?.multiline ? "textarea" : "input", null, { id });
      if (selector.number) {
        control.type = "number";
        for (const key of ["min", "max"]) if (selector.number[key] !== undefined) control[key] = selector.number[key];
        control.step = selector.number.step ?? "any";
      } else if (control.tagName === "INPUT") control.type = selector.text?.type || (selector.date ? "date" : "text");
      control.value = value ?? "";
      control.addEventListener("change", () => {
        if (control.value === "") onChange(undefined);
        else if (selector.number) onChange(control.valueAsNumber);
        else onChange(control.value);
      });
    }
    control.disabled = this.model.busy;
    if (field.required) control.required = true;
    const described = [];
    if (field.description) {
      box.append(element("small", field.description, { id: `${id}-description` }));
      described.push(`${id}-description`);
    }
    if (selector.number?.unit_of_measurement) box.append(element("small", t("unit", { unit: selector.number.unit_of_measurement })));
    if (value === undefined && field.suggested_value !== undefined) {
      box.append(element("small", t("suggested", { value: printable(field.suggested_value) })));
    }
    if (error) {
      box.append(element("small", this.errorText(error), { class: "error", id: `${id}-error` }));
      described.push(`${id}-error`);
      control.setAttribute("aria-invalid", "true");
    }
    if (described.length) control.setAttribute("aria-describedby", described.join(" "));
    if (!control.parentNode) row.append(control);
    if (preview) row.append(preview.value);
    if (!field.required && value !== undefined) {
      const clear = button("×", () => onChange(undefined), {
        class: "clear-control", title: t("clear"), "aria-label": `${t("clear")} ${this.label(field)}`,
      });
      clear.disabled = this.model.busy;
      row.append(clear);
    }
    box.append(row);
    return box;
  }

  entityControl(field, value, box, row, onChange) {
    const id = fieldId(field);
    const multiple = !!field.selector.entity.multiple;
    const values = multiple ? (value || []) : (value ? [value] : []);
    const choices = entityChoices(this.hass.states, field.selector, values);
    const input = element("input", null, { id, type: "text", list: `${id}-sources`, autocomplete: "off",
      placeholder: t("search") });
    input.value = multiple ? "" : (value || "");
    const datalist = element("datalist", null, { id: `${id}-sources`, "aria-label": t("availableSources") });
    for (const choice of choices) datalist.append(element("option", choice.label, { value: choice.value }));
    box.append(datalist);
    if (multiple) {
      const list = element("ul", null, { class: "source-list" });
      for (const selected of values) {
        const item = element("li");
        const preview = this.sourcePreview(selected);
        item.append(preview.name, preview.value);
        const remove = button("×",
          () => onChange(values.filter((entry) => entry !== selected)),
          { class: "clear-control", title: t("removeSource", { value: selected }),
            "aria-label": t("removeSource", { value: selected }) });
        remove.disabled = this.model.busy;
        item.append(remove); list.append(item);
      }
      box.append(list);
      const add = () => {
        const next = input.value.trim();
        if (next && !values.includes(next)) onChange([...values, next]);
      };
      input.addEventListener("keydown", (event) => { if (event.key === "Enter") { event.preventDefault(); add(); } });
      const addButton = button(t("addSource"), add);
      addButton.disabled = this.model.busy;
      row.append(input, addButton);
    } else {
      input.addEventListener("change", () => onChange(input.value.trim() || undefined));
    }
    return input;
  }

  renderFooter() {
    const footer = element("footer");
    const draft = element("div", null, { class: "draft", role: "status", "aria-live": "polite" });
    const count = this.model.changes().length;
    draft.append(element("strong", this.model.busy ? t("busy") : count ? t("dirty", { count }) : t("clean")),
      element("small", t("draftHint")));
    const discard = button(t("discard"), () => {
      if (window.confirm(t("discardConfirm"))) { this.model.discard(); this.render(); }
    });
    discard.disabled = !count || this.model.busy || this.model.uncertain;
    const apply = button(t("apply"), () => this.run(() => this.model.apply((changes, impacts) => this.review(changes, impacts)), true),
      { class: "primary" });
    apply.disabled = !count || this.model.busy || this.model.uncertain;
    footer.append(draft, discard, apply);
    return footer;
  }

  review(changes, impacts) {
    // run() has rendered the busy state by the time validation completes.
    this.render();
    return new Promise((resolve) => {
      this._reviewResolve = resolve;
      const dialog = element("dialog", null, { "aria-labelledby": "review-title", "aria-describedby": "review-hint" });
      dialog.append(element("h2", t("review"), { id: "review-title" }),
        element("p", t("reviewHint"), { id: "review-hint" }));
      const list = element("ul");
      for (const change of changes) {
        const field = this.model.fields().find((item) => item.group === change.group &&
          item.name === change.name && item.source === change.source) || change;
        list.append(element("li", `${change.source ? `${change.source} · ` : ""}${this.label(field)}: ` +
          t("beforeAfter", { before: printable(change.before), after: printable(change.after) })));
      }
      dialog.append(list);
      if (impacts.length) {
        dialog.append(element("h3", t("impacts")));
        const warnings = element("ul");
        impacts.forEach((impact) => {
          const source = this.model.snapshot.schema.power?.find((item) => impact === `power.${item.key}`);
          const tire = this.model.snapshot.schema.tires?.find((item) => impact === `tires.${item.key}`);
          const label = source ? t("removePower", { name: source.name })
            : tire ? t("removeTire", { name: tire.name })
            : t("removeMapping", { name: impact.replace(/^(options|power)\./, "") });
          warnings.append(element("li", label));
        });
        dialog.append(warnings);
      }
      const finish = (approved) => {
        this._reviewResolve = null;
        dialog.close(); dialog.remove(); resolve(approved);
      };
      dialog.addEventListener("cancel", (event) => { event.preventDefault(); finish(false); });
      const actions = element("div", null, { class: "actions" });
      actions.append(button(t("cancel"), () => finish(false)),
        button(t("confirmApply"), () => finish(true), { class: "primary" }));
      dialog.append(actions);
      this.shadowRoot.append(dialog);
      dialog.showModal();
    });
  }
}

if (!customElements.get("havrv-config-panel")) customElements.define("havrv-config-panel", HavrvConfigPanel);
