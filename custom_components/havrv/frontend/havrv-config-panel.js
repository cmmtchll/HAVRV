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
  .field input:not([type=checkbox]),.field select,.field textarea,.picker select{width:100%;padding:10px;
    border:1px solid var(--divider-color,#bbb);border-radius:4px;color:var(--primary-text-color,#212121);
    background:var(--card-background-color,#fff);min-height:42px}
  .field small{display:block;margin:9px 0;line-height:1.5}.field button{padding:6px 12px;margin:6px 5px 0 0}
  .error{color:var(--error-color,#db4437)}.notice{border-left:4px solid var(--primary-color,#03a9f4);padding:12px 18px;
    background:var(--secondary-background-color,#eee);margin:18px 0;line-height:1.6}.notice.error{border-color:var(--error-color,#db4437)}
  .stats{display:flex;flex-wrap:wrap;gap:26px}.stat strong{display:block;font-size:26px;font-weight:500}
  .links{display:flex;flex-wrap:wrap;gap:12px;margin-top:20px}.picker{display:block;max-width:450px;margin:20px 0}
  .picker select{display:block;margin-top:10px}.search{width:100%;padding:12px;margin:8px 0}
  footer{position:sticky;bottom:0;display:flex;align-items:center;gap:12px;padding:16px 28px;
    border-top:1px solid var(--divider-color,#ddd);background:var(--card-background-color,#fff);z-index:2}
  footer .draft{flex:1}footer small{display:block;margin-top:5px}
  dialog{max-width:680px;width:calc(100% - 32px);max-height:85vh;overflow:auto;border:1px solid var(--divider-color,#ddd);
    border-radius:12px;padding:24px;color:var(--primary-text-color,#212121);background:var(--card-background-color,#fff)}
  dialog::backdrop{background:#0008}dialog li{margin:12px 0;overflow-wrap:anywhere}.actions{display:flex;justify-content:flex-end;gap:12px}
  @media(max-width:700px){header{padding:15px}.grid,.fields{grid-template-columns:1fr}main{padding:16px 16px 70px}
    footer{padding:12px 16px;flex-wrap:wrap}footer .draft{flex-basis:100%}footer button{flex:1}nav button{padding:16px 12px}
    header strong{max-width:40%;overflow-wrap:anywhere}.card{padding:16px}}
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
      section.append(element("h2", t(this.section), { id: "section-title", tabindex: "-1" }),
        element("p", t(`${this.section === "overview" ? "overview" : this.section}Hint`), { class: "muted" }));
      if (this.section === "overview") this.renderOverview(section);
      else this.renderEditor(section);
      main.append(section);
    }
    fragment.append(main);
    if (this.model?.snapshot && this.hass?.user?.is_admin !== false) fragment.append(this.renderFooter());
    this.shadowRoot.replaceChildren(fragment);
    if (activeId) this.shadowRoot.getElementById(activeId)?.focus();
  }

  renderOverview(parent) {
    const snapshot = this.model.snapshot;
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
    for (const field of this.model.fields()) {
      if (!field.selector?.entity) continue;
      for (const id of [].concat(this.model.value(field.group, field.name, field.source) || [])) if (id) sources.add(id);
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
      unavailable.forEach((id) => list.append(element("li", id)));
      card.append(list);
    }
    const entry = encodeURIComponent(this.model.entryId);
    const links = element("div", null, { class: "links" });
    links.append(element("a", t("devices"), { href: `/config/devices/dashboard?config_entry=${entry}` }),
      element("a", t("entities"), { href: `/config/entities?config_entry=${entry}` }));
    card.append(links);
    parent.append(card);
    const grid = element("div", null, { class: "grid" });
    for (const section of SECTIONS.filter((item) => item !== "overview")) {
      const box = element("section", null, { class: "card" });
      box.append(button(t(section), () => this.navigate(section)), element("p", t(`${section}Hint`), { class: "muted" }));
      grid.append(box);
    }
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
      parent.append(this.picker("source", sources, this.selectedPower, (key) => {
        this.selectedPower = key; this.render();
      }));
      fields = fields.filter((field) => field.source === this.selectedPower);
    }
    if (this.section === "tires") {
      const tires = this.model.schema.tires || [];
      if (!tires.some((item) => item.key === this.selectedTire)) this.selectedTire = tires[0]?.key;
      parent.append(this.picker("position", tires, this.selectedTire, (key) => {
        this.selectedTire = key; this.render();
      }));
      const positionFields = fields.filter((field) => tires.some((item) => field.name.startsWith(`tire_${item.key}_`)));
      const selected = positionFields.filter((field) => field.name.startsWith(`tire_${this.selectedTire}_`));
      const limits = fields.filter((field) => !positionFields.includes(field));
      this.renderFields(parent, selected);
      parent.append(element("h3", t("limits")));
      this.renderFields(parent, limits);
      return;
    }
    this.renderFields(parent, fields);
  }

  picker(label, items, selected, change) {
    const wrapper = element("label", t(label), { class: "picker", for: `picker-${label}` });
    const select = element("select", null, { id: `picker-${label}` });
    for (const item of items) {
      const option = element("option", item.name, { value: item.key });
      option.selected = item.key === selected;
      select.append(option);
    }
    select.disabled = this.model.busy;
    select.addEventListener("change", () => change(select.value));
    wrapper.append(select);
    return wrapper;
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
    box.append(element("label", `${this.label(field)}${field.required ? ` · ${t("required")}` : ""}`, { for: id }));
    if (changed) box.append(element("small", t("changed")));
    const selector = field.selector || { text: {} };
    let control;
    const onChange = (next) => this.updateField(field, next);
    if (selector.entity) {
      control = this.entityControl(field, value, box, onChange);
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
    if (!control.parentNode) box.append(control);
    if (!field.required && value !== undefined) {
      const clear = button(t("clear"), () => onChange(undefined), { "aria-label": `${t("clear")} ${this.label(field)}` });
      clear.disabled = this.model.busy;
      box.append(clear);
    }
    return box;
  }

  entityControl(field, value, box, onChange) {
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
      const list = element("ul");
      for (const selected of values) {
        const item = element("li");
        item.append(element("span", choices.find((choice) => choice.value === selected)?.label || selected));
        const remove = button(t("removeSource", { value: selected }),
          () => onChange(values.filter((entry) => entry !== selected)));
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
      box.append(input, addButton);
    } else {
      input.addEventListener("change", () => onChange(input.value.trim() || undefined));
      const selected = choices.find((choice) => choice.value === value);
      if (selected) box.append(element("small", `${selected.label}${selected.unavailable ? ` · ${t("unavailable")}` : ""}`));
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
