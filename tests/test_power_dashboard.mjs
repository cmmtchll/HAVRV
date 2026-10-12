import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

globalThis.HTMLElement = class {
  attachShadow() {
    this.shadowRoot = { addEventListener() {}, innerHTML: "" };
  }
};
const elements = new Map();
globalThis.customElements = {
  get: (key) => elements.get(key),
  define: (key, value) => elements.set(key, value),
};
globalThis.window = {};
globalThis.requestAnimationFrame = () => 1;
globalThis.cancelAnimationFrame = () => {};
const text = await readFile(
  new URL("../custom_components/havrv/frontend/havrv-dashboard.js", import.meta.url),
  "utf8",
);
const {
  buildModel, powerState, powerMarkers, renderVehicle, renderPowerReadings,
  rvView, HavrvDashboardStrategy, HavrvViewStrategy, HavrvRvCard,
} = await import(`data:text/javascript;base64,${Buffer.from(text).toString("base64")}`);

function fixture() {
  const rv = {
    id: "rv", name: "Test RV", identifiers: [["havrv", "entry"]],
    config_entries: ["entry"],
  };
  const hass = { devices: { rv }, entities: {}, states: {} };
  const source = (key, name, location) => {
    const id = `device_${key}`;
    hass.devices[id] = {
      id, name, identifiers: [["havrv", `entry_source_${key}`]],
    };
    for (const [role, value, unit] of [
      ["voltage", "24.5", "V"], ["current", "-2.5", "A"],
      ["enabled", "on"], ["charging", "off"], ["location", location],
    ]) {
      if (role === "charging" && !key.includes("bank")) continue;
      const entity_id = `${role === "enabled" || role === "charging" ? "binary_sensor" : "sensor"}.renamed_${key}_${role}`;
      hass.entities[entity_id] = {
        entity_id, platform: "havrv", device_id: id, translation_key: `power_${role}`,
      };
      hass.states[entity_id] = { state: value, attributes: { unit_of_measurement: unit } };
    }
  };
  source("house_bank_1", "House Bank One", "left_rear");
  source("house_bank_2", "House Bank Two", "left_rear");
  source("chassis_bank_1", "Chassis <Bank>", "right_front");
  source("inverter", "Inverter", "left_mid");
  source("generator", "Generator", "not_shown");
  source("shore_power", "Shore", "right");
  return { hass, rv };
}

test("registry discovery uses stable identities and watches every mapped role", () => {
  const { hass, rv } = fixture();
  const model = buildModel(hass, rv);
  assert.equal(model.powerSources.length, 6);
  assert.equal(model.systems.length, 0);
  assert.equal(model.watched.length, 27);
  const bank = model.powerSources.find((source) => source.key === "house_bank_2");
  assert.match(bank.voltage, /renamed_house_bank_2_voltage/);
  assert.equal(powerState(hass, bank).charging, false);
  assert.equal(powerState(hass, bank).enabled, true);
  assert.equal(powerState(hass, bank).current.value, -2.5);
  hass.states[bank.charging].state = "unknown";
  assert.equal(powerState(hass, bank).charging, undefined);
  hass.states[bank.voltage].state = "unavailable";
  assert.equal(powerState(hass, bank).voltage, undefined);
  const readings = renderPowerReadings(hass, model);
  assert.match(readings, /Voltage: No data/);
  assert.match(readings, /Charging: No data/);
  assert.match(readings, /Chassis &lt;Bank&gt;/);
  assert.doesNotMatch(readings, />GEN:/);
});

test("colocated banks share an interior marker and retain separate readouts", () => {
  const { hass, rv } = fixture();
  const model = buildModel(hass, rv);
  const horizontal = { map: (u, v) => [30 + u, 188 + v] };
  const markers = powerMarkers(hass, model, horizontal);
  assert.equal((markers.match(/class="power-marker"/g) || []).length, 4);
  assert.match(markers, /text-anchor="middle">2<\/text>/);
  assert.match(markers, /House Bank One: 24.5 V; -2.5 A/);
  assert.match(markers, /House Bank Two: 24.5 V; -2.5 A/);
  const readings = renderPowerReadings(hass, model);
  assert.equal((readings.match(/class="power-reading"/g) || []).length, 5);
  assert.match(readings, /HB1: House Bank One/);
  assert.match(readings, /HB2: House Bank Two/);
  assert.match(readings, /Enabled: Yes/);
  assert.match(readings, /Charging: No/);
  assert.match(readings, /R \(outside\)/);
});

test("all interior regions stay inside and shore stays outside in both orientations", () => {
  const { hass, rv } = fixture();
  const model = buildModel(hass, rv);
  const bank = model.powerSources.find((source) => source.key === "house_bank_1");
  const shore = model.powerSources.find((source) => source.key === "shore_power");
  const geometries = [
    { map: (u, v) => [30 + u, 188 + v], axis: 1, center: 188 },
    { map: (u, v) => [248 + v, 884 - u], axis: 0, center: 248 },
  ];
  for (const geometry of geometries) {
    for (const side of ["left", "right"]) {
      for (const region of ["front", "mid", "rear"]) {
        hass.states[bank.location].state = `${side}_${region}`;
        const svg = powerMarkers(hass, { powerSources: [bank] }, geometry);
        const [, x, y] = /<circle cx="([^"]+)" cy="([^"]+)"/.exec(svg);
        const center = [Number(x), Number(y)][geometry.axis];
        assert.ok(Math.abs(center - geometry.center) + 8 < 90);
      }
      hass.states[shore.location].state = side;
      const svg = powerMarkers(hass, { powerSources: [shore] }, geometry);
      const [, x, y] = /<circle cx="([^"]+)" cy="([^"]+)"/.exec(svg);
      const center = [Number(x), Number(y)][geometry.axis];
      assert.ok(Math.abs(center - geometry.center) - 8 > 90);
    }
  }
});

test("the diagram and both strategies can omit power without changing tire/tank rendering", async () => {
  const { hass, rv } = fixture();
  const model = buildModel(hass, rv);
  for (const orientation of ["horizontal", "vertical"]) {
    assert.match(renderVehicle(hass, model, orientation, 1), /class="power-marker"/);
    assert.doesNotMatch(renderVehicle(hass, model, orientation, 1, false), /class="power-marker"/);
  }
  const enabled = rvView(hass, rv);
  const disabled = rvView(hass, rv, { show_power: false });
  assert.equal(enabled.sections.length - disabled.sections.length, 6);
  assert.equal(disabled.sections[0].cards[0].show_power, false);
  const dashboard = await HavrvDashboardStrategy.generate({ show_power: false }, hass);
  assert.equal(dashboard.views[0].sections[0].cards[0].show_power, false);
  const view = await HavrvViewStrategy.generate({ device_id: rv.id, show_power: false }, hass);
  assert.equal(view.sections[0].cards[0].show_power, false);
});

test("live status, units, renaming and placement changes rerender the card", () => {
  const { hass } = fixture();
  const card = new HavrvRvCard();
  card.setConfig({ device_id: "rv" });
  card.hass = hass;
  const originalKey = card._renderKey;
  const charging = "binary_sensor.renamed_house_bank_1_charging";
  hass.states[charging].state = "on";
  card.hass = hass;
  assert.notEqual(card._renderKey, originalKey);
  assert.match(card.shadowRoot.innerHTML, /Charging: Yes/);
  const source = "sensor.renamed_house_bank_1_voltage";
  hass.states[source].attributes.unit_of_measurement = "mV";
  card.hass = hass;
  assert.match(card.shadowRoot.innerHTML, /24.5 mV/);
  hass.devices.device_house_bank_1.name = "Renamed House";
  card.hass = hass;
  assert.match(card.shadowRoot.innerHTML, /Renamed House/);
  hass.states["sensor.renamed_house_bank_1_location"].state = "not_shown";
  card.hass = hass;
  assert.doesNotMatch(card.shadowRoot.innerHTML, /HB1: Renamed House/);
  card.setConfig({ show_power: false });
  assert.doesNotMatch(card.shadowRoot.innerHTML, /class="power-marker"/);
});
