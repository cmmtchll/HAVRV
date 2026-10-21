import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const frontend = new URL("../custom_components/havrv/frontend/", import.meta.url);
const dataModule = (source) => `data:text/javascript;base64,${Buffer.from(source).toString("base64")}`;
const modelUrl = dataModule(await readFile(new URL("havrv-config-model.js", frontend), "utf8"));
const enUrl = dataModule(await readFile(new URL("havrv-config-en.js", frontend), "utf8"));
const { ConfigDraft, entityChoices, equalValues, fieldSection } = await import(modelUrl);

const number = (name, extra = {}) => ({ name, label: `Label ${name}`, selector: { number: { min: 0 } }, ...extra });
const entity = (name, multiple = false) => ({
  name, label: `Label ${name}`, selector: { entity: { domain: ["sensor", "number", "input_number"], multiple } },
});
function snapshot() {
  return {
    revision: "revision-1", profile: { name: "Test RV" }, options: {},
    entry_state: "loaded", devices: 3, entities: 8,
    translations: { config: { error: { invalid_measurement: "Invalid measurement" } } },
    values: {
      profile: { name: "Test RV", measurement_system: "us_customary", length: 30 },
      options: { power_entities: ["sensor.power"], tire_front_left_pressure: "number.tpms" },
      power: { house_bank_1: { voltage: "sensor.voltage" }, house_bank_2: { voltage: "sensor.bank2" } },
      unit_system: "us_customary",
    },
    schema: {
      profile: [
        { name: "name", label: "Name", selector: { text: {} } },
        { name: "measurement_system", label: "Units", selector: { select: { options: [
          { value: "us_customary", label: "US customary" }, { value: "metric", label: "Metric" },
        ] } } },
        number("length"), number("fresh_water_tank_capacity"),
        number("house_battery_bank_count", { suggested_value: 1 }),
        { name: "coach_model", label: "Coach model", selector: { text: {} } },
      ],
      options: [
        entity("power_entities", true), entity("water_entities", true),
        entity("fresh_water_tank_level"), number("fresh_water_tank_warning"),
        entity("tire_front_left_pressure"), number("tire_front_pressure_low"),
        { name: "enabled", label: "Optional boolean", selector: { boolean: {} } },
      ],
      power: ["house_bank_1", "house_bank_2"].map((key) => ({
        key, name: key === "house_bank_1" ? "House bank 1" : "House bank 2", battery: true,
        fields: [entity("voltage"), number("nominal_voltage", { suggested_value: 12 })],
      })),
      tires: [{ key: "front_left", name: "Front left", group: "front" }], defaults: {},
    },
  };
}

function server(overrides = {}) {
  const initial = snapshot();
  const calls = [];
  const callWS = async (message) => {
    assert.notEqual(message.type, "config_entries/reload", "HA has no reload websocket command");
    calls.push(structuredClone(message));
    const action = message.type.split("/").at(-1);
    if (overrides[action]) return overrides[action](message, initial);
    if (action === "get") return structuredClone(initial);
    if (action === "validate") return {
      valid: true, errors: [], impacts: [], revision: initial.revision,
      values: structuredClone(message.values), schema: structuredClone(initial.schema),
    };
    if (action === "apply") return { saved: true, revision: "revision-2", reload_required: false };
    if (action === "reload") return { loaded: true, restart_required: false };
    throw new Error(`Unexpected command ${message.type}`);
  };
  return { initial, calls, callWS };
}
async function loaded(overrides) {
  const api = server(overrides);
  const draft = new ConfigDraft(api.callWS, "entry");
  await draft.load();
  return { api, draft };
}

test("opening a draft does not fill suggested values or write anything", async () => {
  const { api, draft } = await loaded();
  assert.equal(draft.dirty, false);
  assert.equal(draft.value("profile", "house_battery_bank_count"), undefined);
  assert.equal(draft.value("power", "nominal_voltage", "house_bank_1"), undefined);
  assert.equal(draft.payload().unit_system, "us_customary");
  assert.equal("name" in draft.payload().profile, false);
  assert.equal(await draft.apply(() => assert.fail("unchanged draft must not prompt")), false);
  assert.deepEqual(api.calls.map((message) => message.type), ["havrv/config/get"]);
});

test("shore line-count refresh keeps hidden drafts but excludes Line 2 from one-line saves", async () => {
  const { api, draft } = await loaded({
    validate: (message, initial) => {
      const schema = structuredClone(initial.schema);
      const fields = [number("line_count"), entity("voltage"), entity("energy")];
      if (message.values.power.shore_power.line_count === 2) fields.push(entity("line_2_voltage"));
      schema.power.push({ key: "shore_power", name: "Shore Power", fields });
      const values = structuredClone(message.values);
      if (values.power.shore_power.line_count === 1) delete values.power.shore_power.line_2_voltage;
      return { valid: true, values, schema, errors: [], impacts: [] };
    },
  });
  draft.schema.power.push({
    key: "shore_power", name: "Shore Power",
    fields: [number("line_count"), entity("voltage"), entity("energy"), entity("line_2_voltage")],
  });
  draft.setValue("power", "line_count", 2, "shore_power");
  draft.setValue("power", "line_2_voltage", "number.template_line2", "shore_power");
  draft.setValue("power", "energy", "sensor.shared_energy", "shore_power");
  draft.setValue("power", "line_count", 1, "shore_power");
  await draft.refreshSchema();
  assert.equal(draft.payload().power.shore_power.line_2_voltage, undefined);
  assert.equal(draft.value("power", "line_2_voltage", "shore_power"), "number.template_line2");
  draft.setValue("power", "line_count", 2, "shore_power");
  await draft.refreshSchema();
  assert.equal(draft.payload().power.shore_power.line_2_voltage, "number.template_line2");
  assert.equal(draft.payload().power.shore_power.energy, "sensor.shared_energy");
  assert.equal(api.calls.filter((call) => call.type.endsWith("/apply")).length, 0);
});

test("one draft preserves fields across sections and source selections; discard restores all", async () => {
  const { draft } = await loaded();
  draft.setValue("profile", "coach_model", "Custom");
  draft.setValue("options", "fresh_water_tank_level", "input_number.fresh");
  draft.setValue("power", "voltage", "number.voltage", "house_bank_1");
  draft.setValue("power", "voltage", "input_number.voltage", "house_bank_2");
  draft.setValue("options", "tire_front_left_pressure", "sensor.pressure");
  assert.equal(draft.changes().length, 5);
  assert.equal(draft.value("power", "voltage", "house_bank_1"), "number.voltage");
  draft.discard();
  assert.equal(draft.dirty, false);
  assert.equal(draft.value("power", "voltage", "house_bank_1"), "sensor.voltage");
});

test("omitted, zero, false, explicit override and clear retain distinct meanings", async () => {
  const { draft } = await loaded();
  assert.equal(draft.setValue("profile", "name", "Renamed"), false);
  draft.setValue("profile", "house_battery_bank_count", 0);
  draft.setValue("options", "enabled", false);
  draft.setValue("power", "nominal_voltage", 24, "house_bank_1");
  draft.setValue("options", "tire_front_left_pressure", undefined);
  const values = draft.payload();
  assert.equal(values.profile.house_battery_bank_count, 0);
  assert.equal(values.options.enabled, false);
  assert.equal(values.power.house_bank_1.nominal_voltage, 24);
  assert.equal("tire_front_left_pressure" in values.options, false);
  assert.equal(draft.changes().find((change) => change.name === "tire_front_left_pressure").after, undefined);
  draft.setValue("power", "nominal_voltage", undefined, "house_bank_1");
  assert.equal("nominal_voltage" in draft.payload().power.house_bank_1, false);
  assert.equal(equalValues({ b: 1, a: 2 }, { a: 2, b: 1 }), true);
});

test("validation is read-only, and cancellation never sends apply", async () => {
  const { api, draft } = await loaded();
  draft.setValue("profile", "coach_model", "Updated");
  let reviewed = false;
  assert.equal(await draft.apply((changes, impacts) => {
    reviewed = true;
    assert.equal(changes[0].after, "Updated");
    assert.deepEqual(impacts, []);
    return false;
  }), false);
  assert.equal(reviewed, true);
  assert.equal(draft.dirty, true);
  assert.deepEqual(api.calls.map((message) => message.type), ["havrv/config/get", "havrv/config/validate"]);
});

test("invalid configuration keeps draft and field errors without prompting or writing", async () => {
  const errors = [{ section: "profile", field: "length", code: "invalid_measurement" }];
  const { api, draft } = await loaded({ validate: async () => ({ valid: false, errors, impacts: [] }) });
  draft.setValue("profile", "length", -1);
  assert.equal(await draft.apply(() => assert.fail("invalid draft prompted")), false);
  assert.equal(draft.value("profile", "length"), -1);
  assert.deepEqual(draft.errors, errors);
  assert.equal(api.calls.some((message) => message.type.endsWith("/apply")), false);
});

test("invalid layout validation cannot adopt old schema, partial values or suggested defaults", async () => {
  const errors = [{ section: "profile", field: "length", code: "invalid_measurement" }];
  const { api, draft } = await loaded({
    validate: async (_message, initial) => ({
      valid: false, errors, impacts: ["power.house_bank_2"],
      schema: initial.schema,
      values: { ...initial.values, profile: { length: 30, house_battery_bank_count: 1 } },
    }),
  });
  const extra = { key: "house_bank_3", name: "House bank 3", fields: [entity("voltage")] };
  draft.schema.power.push(extra);
  draft.setValue("profile", "house_battery_bank_count", 3);
  draft.setValue("power", "voltage", "input_number.new_bank", extra.key);
  draft.setValue("profile", "length", -1);
  draft.setValue("options", "tire_front_left_pressure", undefined);
  const beforeValues = structuredClone(draft.values);
  const beforeSchema = structuredClone(draft.schema);
  const beforeChanges = draft.changes();
  await draft.refreshSchema();
  assert.deepEqual(draft.values, beforeValues);
  assert.deepEqual(draft.schema, beforeSchema);
  assert.deepEqual(draft.changes(), beforeChanges);
  assert.deepEqual(draft.errors, errors);
  assert.equal(draft.payload().power.house_bank_3.voltage, "input_number.new_bank");
  assert.equal("tire_front_left_pressure" in draft.payload().options, false);
  assert.equal(await draft.apply(() => assert.fail("invalid layout prompted")), false);
  assert.deepEqual(draft.values, beforeValues);
  assert.equal(api.calls.some((message) => message.type.endsWith("/apply")), false);
});

for (const code of ["conflict", "not_found", "not_loaded", "invalid_config", "confirmation_required", "unauthorized"]) {
  test(`rejected apply (${code}) preserves the draft and expected revision`, async () => {
    const { draft } = await loaded({ apply: async () => { throw { code }; } });
    draft.setValue("profile", "length", 31);
    assert.equal(await draft.apply(() => true), false);
    assert.equal(draft.error, code);
    assert.equal(draft.snapshot.revision, "revision-1");
    assert.equal(draft.value("profile", "length"), 31);
    assert.equal(draft.uncertain, false);
  });
}

test("a conflict during validation never writes and keeps the local revision", async () => {
  const { api, draft } = await loaded({ validate: async () => { throw { code: "conflict" }; } });
  draft.setValue("profile", "coach_model", "Local edit");
  await draft.apply(() => assert.fail("conflicted draft prompted"));
  assert.equal(draft.error, "conflict");
  assert.equal(draft.snapshot.revision, "revision-1");
  assert.equal(draft.value("profile", "coach_model"), "Local edit");
  assert.equal(api.calls.some((message) => message.type.endsWith("/apply")), false);
});

test("reducing and restoring draft topology retains edited source and tire values", async () => {
  let reduced = true;
  const { draft } = await loaded({
    validate: async (message, initial) => {
      const schema = structuredClone(initial.schema);
      if (reduced) {
        schema.power = schema.power.slice(0, 1);
        schema.tires = [];
        schema.options = schema.options.filter((field) => field.name !== "tire_front_left_pressure");
      }
      return { valid: true, errors: [], impacts: ["power.house_bank_2"], values: message.values, schema };
    },
  });
  draft.setValue("power", "voltage", "input_number.changed", "house_bank_2");
  draft.setValue("options", "tire_front_left_pressure", "sensor.changed");
  await draft.refreshSchema();
  assert.equal("house_bank_2" in draft.payload().power, false);
  assert.equal("tire_front_left_pressure" in draft.payload().options, false);
  assert.equal(draft.value("power", "voltage", "house_bank_2"), "input_number.changed");
  reduced = false;
  await draft.refreshSchema();
  assert.equal(draft.payload().power.house_bank_2.voltage, "input_number.changed");
  assert.equal(draft.payload().options.tire_front_left_pressure, "sensor.changed");
});

test("normalized units are accepted once before subsequent edit, validation and apply", async () => {
  let conversions = 0;
  const { api, draft } = await loaded({
    validate: async (message, initial) => {
      const values = structuredClone(message.values);
      if (values.profile.measurement_system !== values.unit_system) {
        values.profile.length *= 0.3048;
        values.unit_system = values.profile.measurement_system;
        conversions++;
      }
      return { valid: true, errors: [], impacts: [], values, schema: initial.schema };
    },
  });
  draft.setValue("profile", "measurement_system", "metric");
  await draft.refreshSchema();
  assert.equal(draft.value("profile", "length"), 9.144);
  assert.equal(draft.payload().unit_system, "metric");
  draft.setValue("profile", "coach_model", "After conversion");
  await draft.apply(() => true);
  assert.equal(conversions, 1);
  assert.equal(api.calls.find((message) => message.type.endsWith("/apply")).values.profile.length, 9.144);
});

test("normalizer's omitted empty mapping groups do not become dirty defaults", async () => {
  const { draft } = await loaded({
    validate: async (message) => ({
      valid: true, errors: [], impacts: [],
      values: { ...message.values, options: { ...message.values.options, water_entities: [] } },
    }),
  });
  draft.setValue("profile", "coach_model", "Updated");
  await draft.refreshSchema();
  assert.equal("water_entities" in draft.payload().options, false);
  assert.equal(draft.changes().length, 1);
});

test("backend-shaped unit normalization preserves immutable name and canonical empty category arrays", async () => {
  const categories = ["power", "water", "chassis", "climate", "location", "other"];
  const { api, draft } = await loaded({
    get: async (_message, initial) => {
      for (const category of categories) {
        const key = `${category}_entities`;
        initial.values.options[key] ||= [];
        if (!initial.schema.options.some((field) => field.name === key)) initial.schema.options.push(entity(key, true));
      }
      return initial;
    },
    validate: async (message, initial) => {
      const values = structuredClone(message.values);
      values.profile.name = initial.profile.name;
      for (const category of categories) values.options[`${category}_entities`] ||= [];
      if (values.profile.measurement_system !== values.unit_system) {
        values.profile.length *= 0.3048;
        values.unit_system = values.profile.measurement_system;
      }
      return { valid: true, errors: [], impacts: [], values, schema: initial.schema };
    },
  });
  await draft.refreshSchema();
  assert.equal(draft.dirty, false);
  assert.equal(draft.values.profile.name, "Test RV");
  assert.equal("name" in draft.payload().profile, false);
  draft.setValue("profile", "measurement_system", "metric");
  await draft.refreshSchema();
  assert.deepEqual(draft.changes().map((change) => change.name).sort(), ["length", "measurement_system"]);
  assert.equal(draft.values.unit_system, "metric");
  assert.equal(draft.value("profile", "length"), 9.144);
  for (const category of categories.filter((item) => item !== "power")) {
    assert.deepEqual(draft.payload().options[`${category}_entities`], []);
  }
  await draft.refreshSchema();
  assert.equal(draft.value("profile", "length"), 9.144);
  assert.equal(await draft.apply(() => true), true);
  assert.equal(draft.dirty, false);
  const submitted = api.calls.find((message) => message.type.endsWith("/apply")).values;
  assert.equal("name" in submitted.profile, false);
  assert.equal(submitted.unit_system, "metric");
});

test("hidden tire quantities cannot silently be reinterpreted after a unit change", async () => {
  const { draft } = await loaded();
  draft.setValue("options", "tire_front_pressure_low", 90);
  draft.schema.options = draft.schema.options.filter((field) => field.name !== "tire_front_pressure_low");
  assert.equal(draft.setValue("profile", "measurement_system", "metric"), false);
  assert.equal(draft.error, "inactive_units");
  assert.equal(draft.values.unit_system, "us_customary");
  assert.equal(draft.value("profile", "measurement_system"), "us_customary");
  assert.equal(draft.value("options", "tire_front_pressure_low"), 90);
});

test("double apply is suppressed, impacts are confirmed and update listener owns reload", async () => {
  let finish;
  let reloaded = false;
  const confirmation = new Promise((resolve) => { finish = resolve; });
  const { api, draft } = await loaded({
    validate: async () => ({ valid: true, errors: [], impacts: ["power.house_bank_2"] }),
    apply: async () => ({ saved: true, revision: "revision-2", reload_required: true }),
    get: async (_message, initial) => ({ ...initial, revision: "revision-2",
      entry_state: reloaded ? "loaded" : "setup_error", reload_result: reloaded ? "loaded" : "failed" }),
    reload: async () => { reloaded = true; return { loaded: true, restart_required: false }; },
  });
  draft.setValue("profile", "house_battery_bank_count", 1);
  const first = draft.apply(() => confirmation);
  assert.equal(await draft.apply(() => true), false);
  finish(true);
  assert.equal(await first, true);
  assert.equal(draft.dirty, false);
  assert.equal(draft.reloadState, "reload_failed");
  assert.equal(api.calls.filter((message) => message.type === "havrv/config/reload").length, 0);
  assert.equal(api.calls.find((message) => message.type.endsWith("/apply")).confirm_impacts, true);
  await draft.retryReload();
  assert.deepEqual(api.calls.find((message) => message.type === "havrv/config/reload"),
    { type: "havrv/config/reload", entry_id: "entry" });
  assert.equal(draft.reloadState, "loaded");
  await draft.checkStatus();
  assert.equal(draft.reloadState, "loaded", "subsequent status checks retain the authoritative loaded entry state");
});

test("saved reload polling tolerates transient unload and stops when the listener completes", async () => {
  let reads = 0;
  const { api, draft } = await loaded({
    get: async (_message, initial) => {
      reads++;
      if (reads === 1) return initial;
      if (reads < 4) return { ...initial, entry_state: "not_loaded", reload_result: "pending" };
      return { ...initial, entry_state: "loaded", reload_result: "loaded" };
    },
    apply: async () => ({ saved: true, revision: "revision-2", reload_required: true }),
  });
  draft.wait = async () => {};
  draft.setValue("profile", "length", 31);
  assert.equal(await draft.apply(() => true), true);
  assert.equal(draft.reloadState, "loaded");
  assert.equal(reads, 4);
  assert.equal(api.calls.filter((message) => message.type.endsWith("/apply")).length, 1);
});

test("failed listener reload wins over loaded entry state on open and ordinary status checks", async () => {
  const { draft } = await loaded({
    get: async (_message, initial) => ({ ...initial, entry_state: "loaded", reload_result: "failed" }),
  });
  assert.equal(draft.reloadState, "reload_failed");
  await draft.checkStatus();
  assert.equal(draft.reloadState, "reload_failed");
  draft.discard();
  assert.equal(draft.reloadState, "reload_failed");
});

test("acknowledging a reload never overrides a recorded failed outcome", async () => {
  const { draft } = await loaded({
    get: async (_message, initial) => ({ ...initial, entry_state: "loaded", reload_result: "failed" }),
    reload: async () => ({ loaded: true, restart_required: false }),
  });
  await draft.retryReload();
  assert.equal(draft.reloadState, "reload_failed");
});

test("false reload result is a failure even with lingering loaded state and no status record", async () => {
  const { draft } = await loaded({
    reload: async () => ({ loaded: false, restart_required: false }),
  });
  await draft.retryReload();
  assert.equal(draft.reloadState, "reload_failed");
});

test("restart-required reload outcome has a distinct terminal status", async () => {
  const { draft } = await loaded({
    get: async (_message, initial) => ({ ...initial, reload_result: "restart_required" }),
    reload: async () => ({ loaded: false, restart_required: true }),
  });
  assert.equal(draft.reloadState, "restart_required");
  await draft.retryReload();
  assert.equal(draft.reloadState, "restart_required");
  await draft.checkStatus();
  assert.equal(draft.reloadState, "restart_required");
  draft.wait = () => assert.fail("restart-required status must not keep polling");
  await draft.waitForReload();
  assert.equal(draft.reloadState, "restart_required");
});

for (const code of ["unauthorized", "not_found", "connection"]) {
  test(`reload error ${code} is retained without touching values or revision`, async () => {
    const { api, draft } = await loaded({ reload: async () => { throw { code }; } });
    const before = structuredClone(draft.values);
    await draft.retryReload();
    assert.equal(draft.error, code);
    assert.equal(draft.busy, false);
    assert.equal(draft.uncertain, false);
    assert.deepEqual(draft.values, before);
    assert.equal(draft.snapshot.revision, "revision-1");
    assert.equal(api.calls.some((message) => message.type.endsWith("/apply")), false);
  });
}

test("reload cannot bypass dirty draft, busy or uncertain-save guards", async () => {
  const { api, draft } = await loaded();
  draft.setValue("profile", "coach_model", "Unsaved");
  await draft.retryReload();
  assert.equal(draft.value("profile", "coach_model"), "Unsaved");
  draft.discard();
  draft.busy = true;
  await draft.retryReload();
  draft.busy = false;
  draft.uncertain = true;
  await draft.retryReload();
  assert.equal(api.calls.length, 1);
});

test("malformed reload booleans cannot masquerade as a successful reload", async () => {
  const { draft } = await loaded({ reload: async () => ({ loaded: "false", restart_required: false }) });
  await draft.retryReload();
  assert.equal(draft.error, "invalid_reload_result");
  assert.equal(draft.reloadState, "status_unknown");
});

test("bounded reload observation leaves pending status instead of inventing failure", async () => {
  let reads = 0;
  const { draft } = await loaded({
    get: async (_message, initial) => reads++ === 0 ? initial
      : { ...initial, entry_state: "not_loaded", reload_result: "pending" },
    apply: async () => ({ saved: true, revision: "revision-2", reload_required: true }),
  });
  draft.wait = async () => {};
  draft.setValue("profile", "length", 31);
  assert.equal(await draft.apply(() => true), true);
  assert.equal(reads, 9);
  assert.equal(draft.reloadState, "reload_pending");
  assert.equal(draft.saved, true);
});

test("interrupted writes are uncertain and never blindly retried", async () => {
  const { api, draft } = await loaded({ apply: async () => { throw new Error("Disconnected"); } });
  draft.setValue("profile", "length", 31);
  await draft.apply(() => true);
  assert.equal(draft.uncertain, true);
  assert.equal(draft.dirty, true);
  assert.equal(await draft.apply(() => true), false);
  await draft.checkStatus();
  assert.equal(draft.error, "not_saved");
  assert.equal(draft.value("profile", "length"), 31);
  await draft.retryReload();
  assert.equal(api.calls.filter((message) => message.type.endsWith("/apply")).length, 1);
  assert.equal(api.calls.filter((message) => message.type === "havrv/config/reload").length, 0);
  await draft.load();
  assert.equal(draft.uncertain, false);
});

test("acknowledged persistence followed by status read failure is not a failed save", async () => {
  let reads = 0;
  const { draft } = await loaded({
    get: async (_message, initial) => {
      if (reads++) throw new Error("Offline");
      return initial;
    },
    apply: async () => ({ saved: true, revision: "revision-2", reload_required: true }),
  });
  draft.setValue("profile", "length", 31);
  assert.equal(await draft.apply(() => true), true);
  assert.equal(draft.dirty, false);
  assert.equal(draft.saved, true);
  assert.equal(draft.uncertain, false);
  assert.equal(draft.reloadState, "status_unknown");
});

test("load failure preserves an existing draft", async () => {
  const { api, draft } = await loaded();
  draft.setValue("profile", "length", 42);
  draft.callWS = async () => { throw { code: "not_found" }; };
  assert.equal(await draft.load(), false);
  assert.equal(draft.error, "not_found");
  assert.equal(draft.value("profile", "length"), 42);
  assert.equal(api.calls.length, 1);
});

test("late validation cannot overwrite edits made while its response was pending", async () => {
  let finish;
  const { draft } = await loaded({
    validate: (message) => new Promise((resolve) => {
      finish = () => resolve({ valid: true, values: message.values });
    }),
  });
  const pending = draft.validate();
  draft.setValue("profile", "coach_model", "Newer local edit");
  finish();
  assert.equal((await pending).stale, true);
  assert.equal(draft.value("profile", "coach_model"), "Newer local edit");
});

test("entity choices support numeric helpers, filter domains, friendly names and missing selections", () => {
  const states = {
    "sensor.reading": { state: "1", attributes: { friendly_name: "<b>Untrusted</b>" } },
    "number.reading": { state: "2", attributes: {} },
    "input_number.reading": { state: "3", attributes: {} },
    "switch.control": { state: "on", attributes: {} },
  };
  const choices = entityChoices(states, entity("field").selector, ["sensor.missing"]);
  assert.deepEqual(choices.map((item) => item.value), [
    "input_number.reading", "number.reading", "sensor.missing", "sensor.reading",
  ]);
  assert.equal(choices.find((item) => item.value === "sensor.missing").unavailable, true);
  assert.equal(choices.at(-1).label, "<b>Untrusted</b> (sensor.reading)");
  assert.equal(entityChoices(states, { entity: { filter: [{ domain: "number" }, { domain: "input_number" }] } }).length, 2);
  assert.equal(fieldSection("profile", "fresh_water_tank_capacity"), "tanks");
  assert.equal(fieldSection("options", "power_entities"), "systems");
});

// A deliberately small DOM fixture exercises the standard-element contract
// without adding a framework or a production/browser dependency. Browser layout
// and HA router integration still require an actual Home Assistant smoke test.
class Node {
  constructor(tag = "") {
    this.tagName = tag.toUpperCase();
    this.children = [];
    this.attributes = new Map();
    this.listeners = new Map();
    this._text = "";
    this.value = "";
  }
  set textContent(value) { this._text = String(value); this.children = []; }
  get textContent() { return this._text + this.children.map((child) => child.textContent).join(""); }
  setAttribute(key, value) { this.attributes.set(key, value); if (key === "id") this.id = value; if (key === "value") this.value = value; }
  getAttribute(key) { return this.attributes.get(key); }
  hasAttribute(key) { return this.attributes.has(key); }
  addEventListener(type, callback) { this.listeners.set(type, [...(this.listeners.get(type) || []), callback]); }
  removeEventListener(type, callback) { this.listeners.set(type, (this.listeners.get(type) || []).filter((item) => item !== callback)); }
  append(...children) {
    for (const child of children) {
      if (child.tagName === "#FRAGMENT") this.append(...child.children);
      else { child.parentNode = this; this.children.push(child); }
    }
  }
  replaceChildren(...children) { this.children = []; this._text = ""; this.append(...children); }
  remove() { this.parentNode.children = this.parentNode.children.filter((child) => child !== this); }
  focus() { globalThis.document.activeElement = this; rootOf(this).activeElement = this; }
  getElementById(id) { return walk(this).find((node) => node.id === id); }
  showModal() { this.open = true; }
  close() { this.open = false; }
  fire(type, extra = {}) {
    const event = { target: this, preventDefault() { this.prevented = true; },
      stopImmediatePropagation() { this.stopped = true; }, ...extra };
    for (const listener of this.listeners.get(type) || []) listener(event);
    return event;
  }
  dispatchEvent(event) {
    for (const listener of this.listeners.get(event.type) || []) listener(event);
    return true;
  }
}
const rootOf = (node) => node.parentNode ? rootOf(node.parentNode) : node;
const walk = (node) => [node, ...node.children.flatMap(walk)];
const findText = (root, tag, text) => walk(root).find((node) => node.tagName === tag.toUpperCase() && node.textContent === text);
const documentFixture = new Node("document");
documentFixture.createElement = (tag) => new Node(tag);
documentFixture.createDocumentFragment = () => new Node("#fragment");
globalThis.document = documentFixture;
globalThis.HTMLElement = class extends Node {
  constructor() { super("havrv-config-panel"); }
  attachShadow() { this.shadowRoot = new Node("#shadow"); return this.shadowRoot; }
};
const registrations = new Map();
globalThis.customElements = { get: (name) => registrations.get(name), define: (name, value) => registrations.set(name, value) };
const windowFixture = new Node("window");
windowFixture.location = { href: "http://ha.test/havrv-config?config_entry=entry" };
windowFixture.history = { replaceState(_state, _unused, href) { windowFixture.location.href = href; } };
windowFixture.confirm = () => true;
globalThis.window = windowFixture;
const source = (await readFile(new URL("havrv-config-panel.js", frontend), "utf8"))
  .replace('moduleUrl("./havrv-config-model.js")', JSON.stringify(modelUrl))
  .replace('moduleUrl("./havrv-config-en.js")', JSON.stringify(enUrl));
const { HavrvConfigPanel } = await import(dataModule(source));
const tick = () => new Promise((resolve) => setImmediate(resolve));
async function panelFixture(options = {}) {
  windowFixture.location.href = "http://ha.test/havrv-config?config_entry=entry";
  windowFixture.confirm = () => true;
  const api = server(options);
  const panel = new HavrvConfigPanel();
  panel.hass = {
    user: { is_admin: true }, states: {
      "sensor.power": { state: "100", attributes: { friendly_name: "Power <img onerror=bad>" } },
      "number.tpms": { state: "unavailable", attributes: { friendly_name: "Tire pressure" } },
    }, callWS: api.callWS,
  };
  panel.connectedCallback();
  await tick();
  return { panel, api, root: panel.shadowRoot };
}

test("panel is a registered standard custom element with six accessible tabs", async () => {
  const { panel, api, root } = await panelFixture();
  assert.equal(registrations.get("havrv-config-panel"), HavrvConfigPanel);
  const tabs = walk(root).filter((node) => node.getAttribute("role") === "tab");
  assert.equal(tabs.length, 6);
  assert.equal(tabs[0].getAttribute("aria-selected"), "true");
  assert.equal(walk(root).some((node) => node.tagName === "A" &&
    node.getAttribute("href") === "/config/devices/dashboard?config_entry=entry"), true);
  tabs[0].fire("keydown", { key: "End" });
  assert.equal(panel.section, "systems");
  assert.equal(window.location.href, "http://ha.test/havrv-config?config_entry=entry");
  assert.equal(api.calls.length, 1);
  panel.disconnectedCallback();
});

test("field controls have accessible labels, suggestions do not set values, and clear removes a key", async () => {
  const { panel, root, api } = await panelFixture();
  panel.navigate("profile");
  const field = root.getElementById("field-profile--house_battery_bank_count");
  assert.equal(field.value, "");
  assert.equal(walk(root).some((node) => node.tagName === "LABEL" && node.getAttribute("for") === field.id), true);
  assert.equal(root.textContent.includes("Suggested: 1 (not applied)"), true);
  field.value = "0"; field.valueAsNumber = 0; field.fire("change");
  assert.equal(panel.model.payload().profile.house_battery_bank_count, 0);
  await tick();
  panel.navigate("profile");
  const length = root.getElementById("field-profile--length");
  const clear = walk(length.parentNode).find((node) => node.getAttribute("aria-label") === "Clear Label length");
  clear.fire("click");
  assert.equal("length" in panel.model.payload().profile, false);
  assert.equal(api.calls.some((message) => message.type.endsWith("/apply")), false);
  panel.disconnectedCallback();
});

test("tabs and source selectors retain edits; hass state updates do not reset them", async () => {
  const { panel, root, api } = await panelFixture();
  panel.navigate("power");
  const input = root.getElementById("field-power-house_bank_1-voltage");
  input.value = "input_number.custom"; input.fire("change");
  root.getElementById("select-source-house_bank_2").fire("click");
  assert.equal(root.getElementById("field-power-house_bank_2-voltage").value, "sensor.bank2");
  panel.navigate("tanks");
  panel.hass = { ...panel.hass, states: { ...panel.hass.states, "sensor.power": { state: "101", attributes: {} } } };
  panel.navigate("power");
  root.getElementById("select-source-house_bank_1").fire("click");
  assert.equal(root.getElementById("field-power-house_bank_1-voltage").value, "input_number.custom");
  assert.equal(api.calls.length, 1);
  panel.disconnectedCallback();
});

test("tank capacities share a single draft value between profile and tanks", async () => {
  const { panel, root } = await panelFixture();
  panel.navigate("profile");
  const capacity = root.getElementById("field-profile--fresh_water_tank_capacity");
  capacity.value = "100"; capacity.valueAsNumber = 100; capacity.fire("change");
  panel.navigate("tanks");
  assert.equal(root.getElementById("field-profile--fresh_water_tank_capacity").value, 100);
  assert.equal(panel.model.changes().filter((change) => change.name === "fresh_water_tank_capacity").length, 1);
  panel.disconnectedCallback();
});

test("entity datalist keeps missing IDs, filters other domains and treats labels as literal text", async () => {
  const { panel, root } = await panelFixture();
  panel.navigate("systems");
  const list = root.getElementById("field-options--power_entities-sources");
  assert.equal(list.children.some((node) => node.value === "sensor.power"), true);
  assert.equal(list.textContent.includes("Power <img onerror=bad>"), true);
  assert.equal(walk(root).some((node) => node.tagName === "IMG"), false);
  panel.navigate("power");
  const missing = root.getElementById("field-power-house_bank_1-voltage-sources");
  assert.equal(missing.children.some((node) => node.value === "sensor.voltage"), true);
  assert.equal(root.textContent.includes("Unavailable or missing"), true);
  panel.disconnectedCallback();
});

test("clear actions share a row with every optional control without changing draft semantics", async () => {
  const { panel, root } = await panelFixture();
  for (const section of ["profile", "power", "tanks", "tires", "systems"]) {
    panel.navigate(section);
    for (const clear of walk(root).filter((node) => node.getAttribute("class") === "clear-control")) {
      if (!clear.getAttribute("aria-label").startsWith("Clear ")) continue;
      assert.equal(clear.parentNode.getAttribute("class"), "control-row");
      assert.ok(clear.parentNode.children.some((node) => ["INPUT", "SELECT", "TEXTAREA"].includes(node.tagName)));
      assert.equal(clear.textContent, "×");
    }
  }
  panel.navigate("power");
  const input = root.getElementById("field-power-house_bank_1-voltage");
  const clear = input.parentNode.children.find((node) => node.getAttribute("class") === "clear-control");
  clear.fire("click");
  assert.equal(panel.model.value("power", "voltage", "house_bank_1"), undefined);
  assert.equal(panel.model.dirty, true);
  panel.disconnectedCallback();
});

test("entity identity is inline with the title; live value shares the input row and opens native more-info", async () => {
  const { panel, root, api } = await panelFixture();
  panel.hass = { ...panel.hass, states: { ...panel.hass.states,
    "sensor.voltage": { state: "13.4", attributes: { friendly_name: "House <b>bank</b>", unit_of_measurement: "V" } },
  } };
  panel.navigate("power");
  const input = root.getElementById("field-power-house_bank_1-voltage");
  const box = input.parentNode.parentNode;
  const heading = box.children.find((node) => node.getAttribute("class") === "field-heading");
  assert.equal(heading.children[0].tagName, "LABEL");
  assert.equal(heading.children[1].tagName, "SMALL");
  assert.equal(heading.children[1].textContent, "House <b>bank</b> (sensor.voltage)");
  assert.equal(walk(box).some((node) => node.tagName === "B"), false);
  const value = input.parentNode.children.find((node) => node.getAttribute("class") === "source-value");
  assert.equal(value.textContent, "13.4 V");
  let info;
  panel.addEventListener("hass-more-info", (event) => { info = event; });
  value.fire("click");
  assert.deepEqual(info.detail, { entityId: "sensor.voltage" });
  assert.equal(info.bubbles, true);
  assert.equal(info.composed, true);
  assert.equal(panel.model.dirty, false);
  assert.equal(api.calls.length, 1);
  panel.disconnectedCallback();
});

test("live previews update without replacing focused or uncommitted input or resetting drafts", async () => {
  const { panel, root } = await panelFixture();
  panel.navigate("tires");
  const input = root.getElementById("field-options--tire_front_left_pressure");
  input.value = "sensor.partially_typed";
  input.focus();
  panel.model.setValue("profile", "coach_model", "Unsaved");
  panel.hass = { ...panel.hass, formatEntityState: (state) => `${state.state} psi`, states: {
    ...panel.hass.states, "number.tpms": { state: "112", attributes: { friendly_name: "Front left" } },
  } };
  assert.equal(root.getElementById(input.id), input);
  assert.equal(input.value, "sensor.partially_typed");
  assert.equal(root.activeElement, input);
  assert.equal(root.textContent.includes("112 psi"), true);
  assert.equal(panel.model.value("profile", "coach_model"), "Unsaved");
  assert.equal(panel.model.value("options", "tire_front_left_pressure"), "number.tpms");
  assert.equal(root.getElementById("tire-position-front_left").getAttribute("class"), "tire-position");
  panel.disconnectedCallback();
});

test("source states use HA formatting and plain entity-row typography instead of button badges", async () => {
  const { panel, root } = await panelFixture();
  const calls = [];
  panel.hass = { ...panel.hass, formatEntityState: (state) => {
    calls.push(state);
    return state.state === "unavailable" ? "Indisponible" : "1.234,50 kPa";
  } };
  panel.navigate("tires");
  let value = walk(root).find((node) => node.getAttribute("class") === "source-value");
  assert.equal(value.textContent, "Indisponible");
  assert.equal(calls.at(-1), panel.hass.states["number.tpms"]);
  panel.hass = { ...panel.hass, states: { ...panel.hass.states,
    "number.tpms": { state: "1234.5", attributes: { unit_of_measurement: "kPa" } },
  } };
  assert.equal(value.textContent, "1.234,50 kPa");
  assert.equal(value.disabled, false);
  const style = walk(root).find((node) => node.tagName === "STYLE").textContent;
  assert.match(style, /\.field button\.source-value\{[^}]*border:0;[^}]*border-radius:0;[^}]*background:none;/);
  assert.match(style, /\.field button\.source-value\{[^}]*color:var\(--primary-text-color[^}]*font-weight:400/);
  assert.match(style, /\.source-value:focus-visible\{/);
  assert.equal(panel.model.dirty, false);
  panel.disconnectedCallback();
});

test("missing sources stay visible but cannot open nonexistent history; unavailable sources can", async () => {
  const { panel, root } = await panelFixture();
  panel.navigate("power");
  let events = 0;
  panel.addEventListener("hass-more-info", () => events++);
  let value = walk(root).find((node) => node.getAttribute("class") === "source-value");
  assert.equal(value.disabled, true);
  value.fire("click");
  assert.equal(events, 0);
  panel.navigate("tires");
  value = walk(root).find((node) => node.getAttribute("class") === "source-value");
  assert.equal(value.disabled, false);
  assert.equal(value.textContent, "Unavailable or missing");
  value.fire("click");
  assert.equal(events, 1);
  assert.equal(root.getElementById("tire-position-front_left").getAttribute("class"), "tire-position missing");
  panel.disconnectedCallback();
});

test("multi-source mappings show individual live values and retain independent removal controls", async () => {
  const { panel, root } = await panelFixture();
  panel.navigate("systems");
  const list = walk(root).find((node) => node.getAttribute("class") === "source-list" && node.children.length);
  assert.equal(list.children[0].textContent.includes("100"), true);
  assert.equal(list.children[0].textContent.includes("Power <img onerror=bad>"), true);
  const remove = list.children[0].children.find((node) => node.getAttribute("aria-label") === "Remove sensor.power");
  remove.fire("click");
  assert.deepEqual(panel.model.value("options", "power_entities"), []);
  assert.equal(panel.model.dirty, true);
  panel.disconnectedCallback();
});

test("RV diagram follows arbitrary draft axles and duals with independent keyboard-accessible positions", async () => {
  const { panel, root } = await panelFixture();
  const keys = ["front_left", "front_right",
    ...["axle_1", "axle_2", "tag_axle"].flatMap((axle) =>
      ["left", "right"].flatMap((side) => ["inner", "outer"].map((wheel) => `${axle}_${side}_${wheel}`)))];
  panel.model.schema.tires = keys.map((key) => ({ key, name: key, group: "axle" }));
  panel.model.setValue("profile", "coach_model", "Keep me");
  panel.navigate("tires");
  const wheels = walk(root).filter((node) => node.getAttribute("class")?.startsWith("tire-position"));
  assert.equal(wheels.length, keys.length);
  assert.equal(new Set(wheels.map((node) => node.getAttribute("style"))).size, keys.length);
  assert.ok(wheels.every((node) => node.tagName === "BUTTON" && node.getAttribute("aria-label")));
  const axleTops = [...new Set(wheels.map((node) =>
    Number(node.getAttribute("style").match(/top:([\d.]+)%/)[1]) * 280 / 100))].sort((a, b) => a - b);
  assert.ok(axleTops.at(-1) + 40 <= 280, "wheels must fit the narrow-screen coach");
  assert.ok(axleTops.slice(1).every((top, index) => top - axleTops[index] >= 40),
    "maximum axle layout must not overlap on narrow screens");
  root.getElementById("tire-position-axle_2_right_outer").fire("click");
  assert.equal(panel.selectedTire, "axle_2_right_outer");
  assert.equal(root.getElementById(`select-position-${panel.selectedTire}`).getAttribute("aria-pressed"), "true");
  assert.equal(root.getElementById(`tire-position-${panel.selectedTire}`).getAttribute("aria-pressed"), "true");
  assert.equal(panel.model.value("profile", "coach_model"), "Keep me");
  panel.model.schema.tires = [];
  panel.render();
  assert.equal(walk(root).filter((node) => node.getAttribute("class")?.startsWith("tire-position")).length, 0);
  panel.disconnectedCallback();
});

test("power and tire selectors use icon rows with draft mappings and live availability, not dropdowns", async () => {
  const { panel, root, api } = await panelFixture();
  panel.navigate("power");
  assert.equal(root.getElementById("picker-source"), undefined);
  const first = root.getElementById("select-source-house_bank_1");
  assert.equal(first.getAttribute("aria-pressed"), "true");
  assert.equal(walk(first).find((node) => node.tagName === "HA-ICON").getAttribute("icon"), "mdi:car-battery");
  assert.equal(first.textContent.includes("1 source mapped"), true);
  assert.equal(first.textContent.includes("1 unavailable or missing"), true);
  panel.hass = { ...panel.hass, states: { ...panel.hass.states,
    "sensor.voltage": { state: "13.2", attributes: { unit_of_measurement: "V" } },
  } };
  assert.equal(root.getElementById(first.id), first, "live updates must not rebuild editors");
  assert.equal(first.textContent.includes("unavailable"), false);
  const input = root.getElementById("field-power-house_bank_1-voltage");
  input.value = "input_number.edited"; input.fire("change");
  root.getElementById(first.id).fire("keydown", { key: "ArrowDown" });
  assert.equal(panel.selectedPower, "house_bank_2");
  assert.equal(root.activeElement.id, "select-source-house_bank_2");
  root.getElementById("select-source-house_bank_2").fire("keydown", { key: "Home" });
  assert.equal(root.getElementById(input.id).value, "input_number.edited");
  panel.navigate("tires");
  assert.equal(root.getElementById("picker-position"), undefined);
  const tire = root.getElementById("select-position-front_left");
  assert.equal(walk(tire).find((node) => node.tagName === "HA-ICON").getAttribute("icon"), "mdi:circle-double");
  assert.equal(tire.getAttribute("aria-pressed"), "true");
  assert.equal(tire.getAttribute("type"), "button");
  assert.equal(tire.parentNode.getAttribute("role"), "group");
  assert.equal(tire.textContent.includes("1 unavailable or missing"), true);
  assert.equal(root.getElementById("tire-position-front_left").getAttribute("aria-pressed"), "true");
  panel.hass = { ...panel.hass, states: { ...panel.hass.states,
    "number.tpms": { state: "112", attributes: { unit_of_measurement: "psi" } },
  } };
  assert.equal(root.getElementById(tire.id), tire);
  assert.equal(tire.textContent.includes("1 source mapped"), true);
  assert.equal(tire.textContent.includes("unavailable"), false);
  assert.equal(panel.model.value("power", "voltage", "house_bank_1"), "input_number.edited");
  assert.equal(api.calls.some((message) => message.type.endsWith("/apply")), false);
  panel.disconnectedCallback();
});

test("power selector supports every generated bank and AC source without guessing availability", async () => {
  const { panel, root } = await panelFixture();
  panel.model.schema.power.push(
    { key: "house_bank_3", name: "House bank 3", battery: true, fields: [entity("voltage")] },
    ...["inverter", "generator", "shore_power"].map((key) => ({ key, name: key, fields: [entity("voltage")] })),
  );
  panel.navigate("power");
  for (const [key, icon] of [
    ["house_bank_3", "mdi:car-battery"], ["inverter", "mdi:sine-wave"],
    ["generator", "mdi:engine"], ["shore_power", "mdi:power-plug"],
  ]) {
    const row = root.getElementById(`select-source-${key}`);
    assert.equal(row.textContent.includes("No sources mapped"), true);
    assert.equal(row.textContent.includes("available"), false);
    assert.equal(walk(row).find((node) => node.tagName === "HA-ICON").getAttribute("icon"), icon);
    row.fire("click");
    assert.equal(panel.selectedPower, key);
    assert.ok(root.getElementById(`field-power-${key}-voltage`));
  }
  assert.equal(panel.model.dirty, false);
  root.getElementById("select-source-shore_power").fire("keydown", { key: "ArrowDown" });
  assert.equal(panel.selectedPower, "house_bank_1");
  root.getElementById("select-source-house_bank_1").fire("keydown", { key: "End" });
  assert.equal(panel.selectedPower, "shore_power");
  panel.model.busy = true;
  panel.render();
  assert.equal(root.getElementById("select-source-generator").disabled, true);
  root.getElementById("select-source-generator").fire("keydown", { key: "Home" });
  assert.equal(panel.selectedPower, "shore_power");
  panel.disconnectedCallback();
});

test("overview has descriptive system navigation, scoped registry links and a draft profile summary", async () => {
  const { panel, root, api } = await panelFixture();
  panel.model.values.profile.rear_axle_count = "two";
  panel.model.schema.profile.push({ name: "rear_axle_count", selector: { select: { options: [
    { value: "two", label: "2, including tag" },
  ] } } });
  panel.model.schema.power.push({
    key: "chassis_bank_1", name: "Chassis bank 1", battery: true, fields: [entity("voltage")],
  });
  panel.model.setValue("profile", "coach_model", "Retain this draft");
  panel.navigate("overview");
  for (const text of ["Your RV, organized", "Configure your systems", "Your Home Assistant",
    "Profile name", "Measurement system", "US customary", "2, including tag", "2 / 1",
    "3 independent battery banks", "1 positions from your draft axle layout",
    "Fresh, gray and black water"]) assert.equal(root.textContent.includes(text), true, text);
  assert.equal(walk(root).some((node) => node.getAttribute("href") === "/config/entities?config_entry=entry"), true);
  assert.equal(walk(root).some((node) => node.getAttribute("href")?.includes("/lovelace")), false);
  root.getElementById("configure-power").fire("click");
  assert.equal(panel.section, "power");
  panel.navigate("overview");
  root.getElementById("edit-profile").fire("click");
  assert.equal(panel.section, "profile");
  panel.navigate("overview");
  const review = walk(root).find((node) => node.tagName === "BUTTON" &&
    node.textContent === "Review unavailable source: number.tpms");
  review.fire("click");
  assert.equal(panel.section, "tires");
  assert.equal(panel.selectedTire, "front_left");
  assert.equal(root.activeElement.id, "field-options--tire_front_left_pressure");
  assert.equal(panel.model.value("profile", "coach_model"), "Retain this draft");
  assert.equal(api.calls.length, 1);
  panel.disconnectedCallback();
});

test("zero or omitted banks, empty tires and removed selections do not invent mappings or defaults", async () => {
  const { panel, root, api } = await panelFixture();
  panel.navigate("power");
  root.getElementById("select-source-house_bank_2").fire("click");
  panel.model.values.profile.house_battery_bank_count = 0;
  panel.model.values.profile.chassis_battery_bank_count = 0;
  panel.model.schema.power = [{ key: "shore_power", name: "<b>Shore</b>", battery: false, fields: [entity("voltage")] }];
  panel.render();
  assert.equal(panel.selectedPower, "shore_power");
  assert.equal(root.getElementById("select-source-house_bank_2"), undefined);
  assert.equal(root.getElementById("select-source-shore_power").textContent.includes("<b>Shore</b>"), true);
  assert.equal(walk(root.getElementById("select-source-shore_power")).some((node) => node.tagName === "B"), false);
  panel.model.schema.tires = [];
  panel.navigate("tires");
  assert.equal(panel.selectedTire, undefined);
  assert.equal(root.getElementById("select-position-front_left"), undefined);
  assert.equal(walk(root).filter((node) => node.getAttribute("class") === "tire-position").length, 0);
  panel.navigate("overview");
  assert.equal(root.textContent.includes("0 / 0"), true);
  assert.equal(root.textContent.includes("0 positions"), true);
  delete panel.model.values.profile.house_battery_bank_count;
  delete panel.model.values.profile.chassis_battery_bank_count;
  panel.model.schema.power = snapshot().schema.power.slice(0, 1);
  panel.model.schema.tires = snapshot().schema.tires;
  panel.model.schema.profile.find((field) => field.name === "measurement_system").selector.select.options[0].label = "Translated units";
  panel.render();
  assert.equal(root.textContent.includes("1 / 0"), true, "summaries follow backend schema defaults, never assumed counts");
  assert.equal(root.textContent.includes("Translated units"), true);
  assert.equal(panel.model.value("profile", "house_battery_bank_count"), undefined);
  assert.equal(panel.model.value("profile", "rear_axle_count"), undefined);
  assert.equal(api.calls.length, 1);
  panel.disconnectedCallback();
});

test("optional boolean is not conflated with false and errors link to focused fields", async () => {
  const { panel, root } = await panelFixture();
  panel.navigate("systems");
  const control = root.getElementById("field-options--enabled");
  assert.equal(control.value, "");
  control.value = "false"; control.fire("change");
  assert.equal(panel.model.value("options", "enabled"), false);
  panel.model.errors = [{ section: "profile", field: "length", code: "invalid_measurement" }];
  panel.render();
  const error = root.getElementById("errors");
  assert.equal(error.getAttribute("role"), "alert");
  const link = walk(error).find((node) => node.tagName === "BUTTON" && node.textContent.includes("Label length"));
  link.fire("click");
  assert.equal(panel.section, "profile");
  const invalid = root.getElementById("field-profile--length");
  assert.equal(invalid.getAttribute("aria-invalid"), "true");
  assert.equal(invalid.getAttribute("aria-describedby").includes("-error"), true);
  assert.equal(root.activeElement, invalid);
  panel.disconnectedCallback();
});

test("beforeunload and in-app navigation guard retain a cancelled draft and clean up on disconnect", async () => {
  const { panel } = await panelFixture();
  panel.model.setValue("profile", "length", 42);
  const unload = windowFixture.fire("beforeunload");
  assert.equal(unload.prevented, true);
  windowFixture.confirm = () => false;
  const link = new Node("a");
  link.href = "http://ha.test/config/integrations";
  const click = documentFixture.fire("click", { composedPath: () => [link] });
  assert.equal(click.prevented, true);
  assert.equal(panel.model.dirty, true);
  windowFixture.location.href = "http://ha.test/other";
  const navigation = windowFixture.fire("location-changed");
  assert.equal(navigation.stopped, true);
  assert.equal(windowFixture.location.href, "http://ha.test/havrv-config?config_entry=entry");
  panel.disconnectedCallback();
  assert.equal((windowFixture.listeners.get("beforeunload") || []).includes(panel._beforeUnload), false);
  assert.equal((documentFixture.listeners.get("click") || []).includes(panel._clickGuard), false);
});

test("non-admin panel does not fetch configuration", () => {
  const panel = new HavrvConfigPanel();
  panel.hass = { user: { is_admin: false }, callWS: () => assert.fail("non-admin fetch") };
  panel.connectedCallback();
  assert.equal(panel.shadowRoot.textContent.includes("administrators only"), true);
  panel.disconnectedCallback();
});

test("a missing config_entry does not invent another profile or fetch unagreed APIs", () => {
  windowFixture.location.href = "http://ha.test/havrv-config";
  const panel = new HavrvConfigPanel();
  panel.hass = { user: { is_admin: true }, callWS: () => assert.fail("missing entry fetch") };
  panel.connectedCallback();
  assert.equal(panel.shadowRoot.textContent.includes("using the HAVRV integration gear"), true);
  panel.disconnectedCallback();
});

test("review uses a labelled native dialog and cancellation preserves draft", async () => {
  const { panel, root, api } = await panelFixture();
  panel.model.setValue("profile", "coach_model", "<script>unsafe</script>");
  const pending = panel.model.apply((changes, impacts) => panel.review(changes, impacts));
  await tick();
  const dialog = walk(root).find((node) => node.tagName === "DIALOG");
  assert.equal(dialog.open, true);
  assert.equal(dialog.getAttribute("aria-labelledby"), "review-title");
  assert.equal(dialog.textContent.includes("<script>unsafe</script>"), true);
  assert.equal(walk(dialog).some((node) => node.tagName === "SCRIPT"), false);
  findText(dialog, "button", "Keep editing").fire("click");
  assert.equal(await pending, false);
  assert.equal(panel.model.dirty, true);
  assert.equal(api.calls.some((message) => message.type.endsWith("/apply")), false);
  panel.disconnectedCallback();
});

test("global Apply opens review, disables repeated saves and writes only after confirmation", async () => {
  const { panel, root, api } = await panelFixture();
  panel.model.setValue("profile", "coach_model", "Updated RV");
  panel.render();
  findText(root, "button", "Apply changes").fire("click");
  await tick();
  const dialog = walk(root).find((node) => node.tagName === "DIALOG");
  assert.equal(api.calls.some((message) => message.type.endsWith("/apply")), false);
  assert.equal(findText(root, "button", "Apply changes").disabled, true);
  findText(dialog, "button", "Confirm and apply").fire("click");
  await tick();
  assert.equal(api.calls.filter((message) => message.type.endsWith("/apply")).length, 1);
  assert.equal(panel.model.dirty, false);
  assert.equal(root.textContent.includes("Configuration is persisted."), true);
  panel.disconnectedCallback();
});

test("tank removal review names the device and sensors rather than a source mapping", async () => {
  const { panel, root } = await panelFixture();
  const pending = panel.review([], ["tanks.fresh_water", "tanks.gray_water", "tanks.black_water"]);
  const dialog = walk(root).find((node) => node.tagName === "DIALOG");
  for (const name of ["Fresh-water tank", "Gray-water tank", "Black-water tank"]) {
    assert.ok(dialog.textContent.includes(`Remove HAVRV tank sensors and empty device: ${name}`));
  }
  assert.ok(!dialog.textContent.includes("Remove HAVRV mapping: tanks."));
  findText(dialog, "button", "Keep editing").fire("click");
  assert.equal(await pending, false);
  panel.disconnectedCallback();
});

test("restart-needed outcome is shown explicitly rather than as loaded or generic failure", async () => {
  const { panel, root } = await panelFixture({
    reload: async () => ({ loaded: false, restart_required: true }),
  });
  await panel.run(() => panel.model.retryReload());
  assert.equal(panel.model.reloadState, "restart_required");
  assert.equal(root.textContent.includes("Saved; Home Assistant restart required"), true);
  panel.disconnectedCallback();
});
