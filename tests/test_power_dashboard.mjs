import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

globalThis.HTMLElement = class {
  attachShadow() {
    const listeners = new Map();
    this.shadowRoot = {
      listeners,
      addEventListener: (type, listener) => listeners.set(type, listener),
      innerHTML: "",
    };
  }
};
globalThis.Element = class {
  constructor(entity) {
    this.dataset = entity ? { entity } : {};
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
  buildModel, powerState, layoutPowerBoxes, renderPowerBoxes, renderVehicle, summarize,
  rvView, HavrvDashboardStrategy, HavrvViewStrategy, HavrvRvCard,
  DISPLAY_CLASSES, dashboardOptions, visibleModel,
  rememberReadings, missingReadingText,
  convertTireValue, tireReading, pressureSparkline, pressureHistory,
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
      ["enabled", "on"], ["charging", "off"], ["warning", "off"], ["problem", "off"],
      ["location", location],
    ]) {
      if (role === "charging" && !key.includes("bank")) continue;
      const entity_id = `${["enabled", "charging", "warning", "problem"].includes(role) ? "binary_sensor" : "sensor"}.renamed_${key}_${role}`;
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

function shoreFixture() {
  const { hass, rv } = fixture();
  for (const [metric, value, unit] of [
    ["voltage", "118", "V"], ["current", "35", "A"], ["frequency", "60", "Hz"], ["power", "4160", "W"],
    ["line_2_voltage", "119", "V"], ["line_2_current", "27", "A"],
    ["line_2_frequency", "60", "Hz"], ["line_2_power", "3280", "W"], ["energy", "2.6", "kWh"],
  ]) {
    const entity_id = `sensor.renamed_shore_power_${metric}`;
    hass.entities[entity_id] = {
      entity_id, platform: "havrv", device_id: "device_shore_power", translation_key: `shore_${metric}`,
    };
    hass.states[entity_id] = { state: value, attributes: { unit_of_measurement: unit } };
  }
  return { hass, rv };
}

test("shore lines use registry roles and show one shared energy reading in both layouts", async () => {
  const { hass, rv } = shoreFixture();
  const model = buildModel(hass, rv);
  const shore = model.powerSources.find((source) => source.key === "shore_power");
  assert.equal(powerState(hass, shore).energy.value, 2.6);
  assert.equal(powerState(hass, shore).line_2_power.value, 3280);
  assert.ok(model.watched.includes(shore.line_2_frequency));
  assert.equal(model.watched.filter((id) => id === shore.energy).length, 1);
  for (const orientation of ["horizontal", "vertical"]) {
    const layout = layoutPowerBoxes(hass, model, orientation);
    const box = layout.boxes.find((box) => box.source === shore);
    assert.equal(box.metrics.length, 9);
    assert.equal(box.height, 180);
    assert.deepEqual(box.rows, [
      ["voltage", "line_2_voltage"], ["current", "line_2_current"],
      ["frequency", "line_2_frequency"], ["power", "line_2_power"],
      ["enabled"], ["energy"],
    ]);
    const svg = renderPowerBoxes(hass, layout);
    assert.match(svg, />Line 1<\/text>/);
    assert.match(svg, />Line 2<\/text>/);
    assert.match(svg, /class="shore-divider"/);
    assert.match(svg, />Combined<\/text>/);
    assert.match(svg, />Enabled<\/text>/);
    assert.match(svg, />On<\/tspan>/);
    for (const line of [1, 2]) {
      for (const label of ["Voltage", "Amps", "Frequency", "Watts"]) {
        assert.ok(svg.includes(`Line ${line} ${label}`));
      }
    }
    assert.equal((svg.match(/>Energy<\/text>/g) || []).length, 1);
    assert.match(svg, /kWh/);
    assert.doesNotMatch(svg, /Reset|reset/);
    for (const other of [...layout.boxes, ...layout.icons, ...layout.obstacles]) {
      if (other === box) continue;
      assert.ok(!(box.x < other.x + other.width && box.x + box.width > other.x
        && box.y < other.y + other.height && box.y + box.height > other.y));
    }
    assert.doesNotMatch(renderVehicle(hass, model, orientation, 1, false), /Line 2|kWh|power-box/);
  }
  for (const result of [
    rvView(hass, rv),
    (await HavrvDashboardStrategy.generate({}, hass)).views[0],
    await HavrvViewStrategy.generate({ device_id: rv.id }, hass),
  ]) {
    assert.equal(JSON.stringify(result).split(shore.energy).length - 1, 1);
    assert.ok(JSON.stringify(result).includes(shore.line_2_frequency));
  }
  hass.states[shore.energy].state = "0";
  assert.equal(powerState(hass, shore).energy.value, 0);
  hass.states[shore.line_2_frequency].state = "unavailable";
  assert.equal(powerState(hass, shore).line_2_frequency, undefined);
});

test("shore columns retain metric alignment, zeroes and unavailable readings", () => {
  const { hass, rv } = shoreFixture();
  delete hass.entities["sensor.renamed_shore_power_current"];
  const model = buildModel(hass, rv);
  const shore = model.powerSources.find((source) => source.key === "shore_power");
  hass.states[shore.line_2_voltage].state = "0";
  hass.states[shore.frequency].state = "unavailable";
  hass.states[shore.enabled].state = "off";
  hass.states[shore.energy].state = "0";
  for (const orientation of ["horizontal", "vertical"]) {
    const layout = layoutPowerBoxes(hass, model, orientation);
    const box = layout.boxes.find((box) => box.source === shore);
    assert.deepEqual(box.rows[1], [undefined, "line_2_current"]);
    const svg = renderPowerBoxes(hass, layout);
    const position = (metric) => {
      const group = svg.split(`<g data-entity="${shore[metric]}"`)[1].split("</g>")[0];
      const match = /<text class="power-value" x="([^"]+)" y="([^"]+)"/.exec(group);
      return match.slice(1).map(Number);
    };
    for (const metric of ["voltage", "frequency", "power"]) {
      const left = position(metric);
      const right = position(`line_2_${metric}`);
      assert.equal(right[0] - left[0], box.columnWidth);
      assert.equal(left[1], right[1]);
    }
    assert.ok(position("energy")[1] > position("power")[1]);
    assert.equal(position("energy")[1] - position("enabled")[1], 20);
    assert.match(svg, /Line 2 Voltage: 0.0 V/);
    assert.match(svg, /Line 1 Frequency: No data/);
    assert.match(svg, /Enabled: Off/);
    assert.match(svg, /Energy: 0.000 kWh/);
  }
});

test("shore combined status follows only Enabled, independently of warning and problem", () => {
  const { hass, rv } = shoreFixture();
  const model = buildModel(hass, rv);
  const shore = model.powerSources.find((source) => source.key === "shore_power");
  hass.states[shore.problem].state = "on";
  for (const [state, label] of [["on", "On"], ["off", "Off"], ["unavailable", "No data"]]) {
    hass.states[shore.enabled].state = state;
    const svg = renderPowerBoxes(hass, layoutPowerBoxes(hass, model, "vertical"));
    assert.match(svg, /class="power-box power-problem" data-source="shore_power"/);
    assert.ok(svg.includes(`aria-label="Shore: Enabled: ${label}"`));
  }
});

test("single-line shore omits Line 2 and Line 2-only mappings stay in the right column", () => {
  for (const line2Only of [false, true]) {
    const { hass, rv } = shoreFixture();
    for (const [id, entry] of Object.entries(hass.entities)) {
      if (entry.device_id !== "device_shore_power") continue;
      if (entry.translation_key === "power_location") continue;
      const metric = entry.translation_key.replace(/^shore_/, "");
      if (line2Only ? !metric.startsWith("line_2_") : metric.startsWith("line_2_")) {
        delete hass.entities[id];
        delete hass.states[id];
      }
    }
    const model = buildModel(hass, rv);
    const layout = layoutPowerBoxes(hass, model, "vertical");
    const box = layout.boxes.find((box) => box.source.key === "shore_power");
    const svg = renderPowerBoxes(hass, layout);
    if (line2Only) {
      assert.deepEqual(box.rows[0], [undefined, "line_2_voltage"]);
      assert.deepEqual(box.sharedMetrics, []);
      assert.doesNotMatch(svg, /Combined/);
    } else {
      assert.deepEqual(box.rows[0], ["voltage"]);
      assert.deepEqual(box.sharedMetrics, ["enabled", "energy"]);
      assert.doesNotMatch(svg, /Line 2/);
    }
  }
});

test("partial shore sources remain interactive without inventing unmapped line readings", () => {
  const { hass, rv } = shoreFixture();
  for (const [id, entry] of Object.entries(hass.entities)) {
    if (entry.device_id === "device_shore_power"
      && !["shore_energy", "power_location"].includes(entry.translation_key)) {
      delete hass.entities[id];
      delete hass.states[id];
    }
  }
  const model = buildModel(hass, rv);
  const layout = layoutPowerBoxes(hass, model, "vertical");
  const box = layout.boxes.find((box) => box.source.key === "shore_power");
  assert.deepEqual(box.metrics, ["energy"]);
  assert.ok(box.width >= 156);
  assert.match(renderPowerBoxes(hass, layout), /data-entity="sensor.renamed_shore_power_energy" tabindex="0" role="button"/);
  assert.doesNotMatch(renderPowerBoxes(hass, layout), /Line 1|Line 2/);
});

test("status-only shore uses the Combined section without inventing measurements", () => {
  const { hass, rv } = shoreFixture();
  for (const [id, entry] of Object.entries(hass.entities)) {
    if (entry.device_id === "device_shore_power"
      && !["power_enabled", "power_location"].includes(entry.translation_key)) {
      delete hass.entities[id];
      delete hass.states[id];
    }
  }
  const model = buildModel(hass, rv);
  const layout = layoutPowerBoxes(hass, model, "vertical");
  const box = layout.boxes.find((box) => box.source.key === "shore_power");
  assert.deepEqual(box.rows, [["enabled"]]);
  assert.equal(box.height, 64);
  const svg = renderPowerBoxes(hass, layout);
  assert.match(svg, />Combined<\/text>/);
  assert.match(svg, /aria-label="Shore: Enabled: On"/);
  assert.doesNotMatch(svg, /Line 1|Line 2|>Energy<\/text>/);
});

test("registry discovery uses stable identities and watches every mapped role", () => {
  const { hass, rv } = fixture();
  const model = buildModel(hass, rv);
  assert.equal(model.powerSources.length, 6);
  assert.equal(model.systems.length, 0);
  assert.equal(model.watched.length, 39);
  const bank = model.powerSources.find((source) => source.key === "house_bank_2");
  assert.match(bank.voltage, /renamed_house_bank_2_voltage/);
  assert.equal(powerState(hass, bank).charging, false);
  assert.equal(powerState(hass, bank).enabled, true);
  assert.equal(powerState(hass, bank).current.value, -2.5);
  hass.states[bank.charging].state = "unknown";
  assert.equal(powerState(hass, bank).charging, undefined);
  hass.states[bank.voltage].state = "unavailable";
  assert.equal(powerState(hass, bank).voltage, undefined);
  const readings = renderPowerBoxes(hass, layoutPowerBoxes(hass, model, "horizontal"));
  assert.match(readings, /Voltage: No data/);
  assert.match(readings, /Charging: No data/);
  assert.match(readings, /Chassis &lt;Bank&gt;/);
  assert.doesNotMatch(readings, />GEN:/);
});

test("the visual card editor exposes the power toggle with a readable label", () => {
  const form = HavrvRvCard.getConfigForm();
  const grid = form.schema.find((field) => field.type === "grid");
  const toggle = grid.schema.find((field) => field.name === "show_power");
  assert.deepEqual(toggle.selector, { boolean: {} });
  assert.equal(form.computeLabel(toggle), "Show placed power sources");
});

test("colocated banks have independent interactive readout boxes at their region", () => {
  const { hass, rv } = fixture();
  const model = buildModel(hass, rv);
  const layout = layoutPowerBoxes(hass, model, "horizontal");
  const readings = renderPowerBoxes(hass, layout);
  assert.equal(layout.boxes.length, 5);
  assert.equal((readings.match(/class="power-box /g) || []).length, 5);
  assert.match(readings, /HB1: House Bank One/);
  assert.match(readings, /HB2: House Bank Two/);
  assert.doesNotMatch(readings, /Enabled: Yes|Enabled: No/);
  assert.match(readings, /Charging: No/);
  assert.match(readings, /R \(outside\)/);
  assert.match(readings, /class="power-status" data-entity="binary_sensor.renamed_house_bank_1_enabled" tabindex="0" role="button"/);
  assert.equal((readings.match(/<circle class="dot"/g) || []).length, 5);
  assert.doesNotMatch(readings, /<text[^>]*>Problem|<text[^>]*>Warning/);
  assert.doesNotMatch(renderVehicle(hass, model, "horizontal", 1), /power-marker|power-readings/);
  const banks = layout.boxes.filter((box) => box.source.key.startsWith("house"));
  assert.notDeepEqual(banks[0].anchor, banks[1].anchor);
  for (const box of banks) {
    assert.deepEqual(box.anchor, layout.icons.find((icon) => icon.source === box.source).anchor);
  }
  assert.notDeepEqual([banks[0].x, banks[0].y], [banks[1].x, banks[1].y]);
});

test("boxes follow all configured regions and shore is external in both orientations", () => {
  const { hass, rv } = fixture();
  const model = buildModel(hass, rv);
  const bank = model.powerSources.find((source) => source.key === "house_bank_1");
  const shore = model.powerSources.find((source) => source.key === "shore_power");
  for (const orientation of ["horizontal", "vertical"]) {
    const vertical = orientation === "vertical";
    for (const side of ["left", "right"]) {
      for (const region of ["front", "mid", "rear"]) {
        hass.states[bank.location].state = `${side}_${region}`;
        const [box] = layoutPowerBoxes(hass, { ...model, powerSources: [bank] }, orientation).boxes;
        const u = region === "front" ? 680 : region === "rear" ? 110 : 430;
        assert.ok(Math.abs((vertical ? box.y + box.height / 2 : box.x + box.width / 2)
          - (vertical ? 884 - u : 30 + u)) <= (vertical ? 144 : 108));
        assert.ok(Math.abs((vertical ? box.anchor[1] : box.anchor[0]) - (vertical ? 884 - u : 30 + u)) <= 124);
        const center = vertical ? 248 : 188;
        const lateral = vertical ? box.x + box.width / 2 : box.y + box.height / 2;
        assert.ok(side === "left" ? lateral < center - 90 : lateral > center + 90);
      }
      hass.states[shore.location].state = side;
      const layout = layoutPowerBoxes(hass, model, orientation);
      const box = layout.boxes.find((item) => item.source.key === shore.key);
      const sameSide = layout.boxes.filter((item) => item !== box && item.side === box.side);
      for (const other of sameSide) {
        if (vertical) {
          assert.ok(box.x + box.width <= other.x || other.x + other.width <= box.x
            || box.y + box.height <= other.y || other.y + other.height <= box.y);
          continue;
        }
        assert.ok(side === "left"
          ? vertical ? box.x + box.width < other.x : box.y + box.height < other.y
          : vertical ? box.x > other.x + other.width : box.y > other.y + other.height);
      }
    }
  }
});

test("the diagram and both strategies can omit power without changing tire/tank rendering", async () => {
  const { hass, rv } = fixture();
  const model = buildModel(hass, rv);
  for (const orientation of ["horizontal", "vertical"]) {
    assert.match(renderVehicle(hass, model, orientation, 1), /class="power-box /);
    assert.doesNotMatch(renderVehicle(hass, model, orientation, 1, false), /class="power-box /);
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
  hass.states["binary_sensor.renamed_house_bank_1_warning"].state = "on";
  card.hass = hass;
  assert.match(card.shadowRoot.innerHTML, /class="power-box power-warning" data-source="house_bank_1"/);
  hass.states["binary_sensor.renamed_house_bank_1_problem"].state = "on";
  card.hass = hass;
  assert.match(card.shadowRoot.innerHTML, /class="power-box power-problem" data-source="house_bank_1"/);
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
  assert.doesNotMatch(card.shadowRoot.innerHTML, /class="power-box /);
});

test("status precedence distinguishes enabled, off, explicit alerts and unknown", () => {
  const { hass, rv } = fixture();
  const model = buildModel(hass, rv);
  const bank = model.powerSources.find((source) => source.key === "house_bank_1");
  for (const [enabled, warning, problem, expected] of [
    ["on", "off", "off", "on"], ["off", "off", "off", "off"],
    ["unknown", "off", "off", "unknown"], ["on", "unavailable", "off", "unknown"],
    ["on", "off", "unknown", "unknown"], ["off", "on", "off", "warning"],
    ["on", "on", "unavailable", "warning"], ["unknown", "unavailable", "on", "problem"],
    ["on", "on", "on", "problem"],
  ]) {
    for (const [metric, value] of [["enabled", enabled], ["warning", warning], ["problem", problem]]) {
      hass.states[bank[metric]].state = value;
    }
    assert.equal(powerState(hass, bank).level, expected);
    const svg = renderVehicle(hass, model, "horizontal", 1);
    assert.match(svg, new RegExp(`class="power-box power-${expected}" data-source="house_bank_1"`));
  }
  const legacy = { ...bank, warning: undefined, problem: undefined };
  assert.equal(powerState(hass, legacy).level, "on");
  delete hass.states[bank.enabled];
  assert.equal(powerState(hass, legacy).level, "unknown");
  assert.equal(powerState(hass, { ...legacy, enabled: undefined }).level, "unknown");
  assert.deepEqual(summarize(hass, model), { alert: 1, watch: 0, offline: 0 });
  assert.deepEqual(summarize(hass, model, false), { alert: 0, watch: 0, offline: 0 });
  hass.states[bank.problem].state = "off";
  hass.states[bank.warning].state = "on";
  assert.deepEqual(summarize(hass, model), { alert: 0, watch: 1, offline: 0 });
  hass.states[bank.warning].state = "unknown";
  assert.deepEqual(summarize(hass, model), { alert: 0, watch: 0, offline: 1 });
  hass.states[bank.location].state = "not_shown";
  assert.deepEqual(summarize(hass, model), { alert: 0, watch: 0, offline: 0 });
});

test("dense placements avoid tire labels, coach/tanks and each other without clipping", () => {
  const { hass, rv } = fixture();
  const model = buildModel(hass, rv);
  const bank = model.powerSources.find((source) => source.key === "house_bank_1");
  const sources = [];
  for (const side of ["left", "right"]) {
    for (const region of ["front", "mid", "rear"]) {
      for (let index = 0; index < 4; index++) {
        const location = `sensor.location_${side}_${region}_${index}`;
        hass.states[location] = { state: `${side}_${region}` };
        sources.push({ ...bank, key: `${side}_${region}_${index}`, location });
      }
    }
  }
  model.powerSources.push(...sources);
  model.axles = Array.from({ length: 4 }, (_, index) => ({
    key: index === 0 ? "front" : `rear_axle_${index}`,
    kind: index === 0 ? "front" : "drive",
    left: [{}, {}], right: [{}, {}],
  }));
  const intersects = (a, b) => a.x < b.x + b.width && a.x + a.width > b.x
    && a.y < b.y + b.height && a.y + a.height > b.y;
  for (const orientation of ["horizontal", "vertical"]) {
    const { boxes, icons, obstacles, bounds } = layoutPowerBoxes(hass, model, orientation);
    const coach = orientation === "horizontal"
      ? { x: 30, y: 98, width: 860, height: 180 }
      : { x: 158, y: 24, width: 180, height: 860 };
    for (const box of boxes) {
      for (const other of [...boxes, ...icons, ...obstacles, coach]) {
        if (box !== other) assert.equal(intersects(box, other), false);
      }
      assert.ok(box.x >= bounds.x && box.y >= bounds.y);
      assert.ok(box.x + box.width <= bounds.x + bounds.width);
      assert.ok(box.y + box.height <= bounds.y + bounds.height);
    }
    assert.deepEqual(layoutPowerBoxes(hass, model, orientation), { boxes, icons, obstacles, bounds });
    for (const icon of icons) {
      for (const other of [...icons, ...obstacles]) {
        if (icon !== other) assert.equal(intersects(icon, other), false);
      }
      assert.ok(icon.x >= bounds.x && icon.y >= bounds.y);
      assert.ok(icon.x + icon.width <= bounds.x + bounds.width);
      assert.ok(icon.y + icon.height <= bounds.y + bounds.height);
    }
  }
});

test("each placed power source has a colored graphic connected to its own box", () => {
  const { hass, rv } = fixture();
  const model = buildModel(hass, rv);
  hass.states["sensor.renamed_generator_location"].state = "right_mid";
  for (const orientation of ["horizontal", "vertical"]) {
    const layout = layoutPowerBoxes(hass, model, orientation);
    assert.equal(layout.icons.length, 6);
    for (const icon of layout.icons) {
      const box = layout.boxes.find((item) => item.source === icon.source);
      assert.deepEqual(icon.anchor, box.anchor);
      const lateral = orientation === "horizontal" ? icon.anchor[1] - 188 : icon.anchor[0] - 248;
      assert.ok(icon.source.key === "shore_power" ? Math.abs(lateral) > 90 : Math.abs(lateral) < 90);
    }
    const svg = renderVehicle(hass, model, orientation, 1);
    assert.equal((svg.match(/class="power-icon /g) || []).length, 6);
    assert.match(svg, /class="equipment-detail"/);
    assert.doesNotMatch(renderVehicle(hass, model, orientation, 1, false), /class="power-icon /);
    for (const level of ["warning", "problem", "off", "unknown"]) {
      const bank = model.powerSources.find((source) => source.key === "house_bank_1");
      hass.states[bank.warning].state = level === "warning" ? "on" : "off";
      hass.states[bank.problem].state = level === "problem" ? "on" : "off";
      hass.states[bank.enabled].state = level === "off" ? "off" : level === "unknown" ? "unknown" : "on";
      assert.match(renderVehicle(hass, model, orientation, 1),
        new RegExp(`class="power-icon power-${level}" data-source="house_bank_1"`));
    }
  }
});

test("source names and entity identifiers are escaped in SVG boxes", () => {
  const { hass, rv } = fixture();
  const model = buildModel(hass, rv);
  const bank = model.powerSources[0];
  bank.name = '<script>"bad"</script>';
  bank.warning = 'binary_sensor."><script>';
  const svg = renderVehicle(hass, model, "horizontal", 1);
  assert.doesNotMatch(svg, /<script>/);
  assert.match(svg, /&lt;script&gt;/);
  assert.match(svg, /data-entity="binary_sensor.&quot;&gt;&lt;script&gt;"/);
});

test("electrical boxes reuse tire tint, typography and circular status indicators", () => {
  const { hass, rv } = fixture();
  const svg = renderVehicle(hass, buildModel(hass, rv), "horizontal", 1);
  assert.match(svg, /<text class="chip-label"/);
  assert.match(svg, /<tspan class="mid"/);
  assert.match(svg, /<tspan class="unit"/);
  assert.match(svg, /<tspan class="small row-right"/);
  assert.match(text, /\.chip-bg, \.power-bg \{ fill: color-mix\(in srgb,[^;]+7%, var\(--hv-card\)\)/);
  assert.match(text, /\.tire rect, \.equipment-shell \{ fill: color-mix\(in srgb, var\(--lvl\) 82%, #000\)/);
  assert.match(text, /\.power-warning \{ --lvl: var\(--hv-watch\)/);
  assert.match(text, /\.power-problem \{ --lvl: var\(--hv-alert\)/);
  assert.match(text, /prefers-reduced-motion: reduce/);
});

test("very many colocated banks keep readable distinct graphics with outward overflow", () => {
  const { hass, rv } = fixture();
  const model = buildModel(hass, rv);
  const bank = model.powerSources.find((source) => source.key === "house_bank_1");
  model.powerSources = Array.from({ length: 50 }, (_, index) => ({
    ...bank, key: `house_bank_${index + 1}`,
  }));
  const layout = layoutPowerBoxes(hass, model, "vertical");
  assert.equal(layout.boxes.length, 50);
  assert.equal(layout.icons.length, 50);
  assert.ok(layout.icons.every((icon) => icon.width === 44));
  assert.ok(layout.icons.some((icon) => icon.x < 158));
  for (const icon of layout.icons) {
    assert.ok(icon.x >= layout.bounds.x && icon.x + icon.width <= layout.bounds.x + layout.bounds.width);
    assert.ok(icon.y >= layout.bounds.y && icon.y + icon.height <= layout.bounds.y + layout.bounds.height);
    for (const other of layout.icons) {
      if (other === icon) continue;
      assert.ok(icon.x + icon.width <= other.x || other.x + other.width <= icon.x
        || icon.y + icon.height <= other.y || other.y + other.height <= icon.y);
    }
  }
});

/** All existing discovered dashboard classes, including the maximum axle layout. */
function completeFixture() {
  const { hass, rv } = fixture();
  const addDevice = (part, readings) => {
    const id = `device_${part}`;
    hass.devices[id] = { id, name: part, identifiers: [["havrv", `entry_${part}`]] };
    for (const [role, state, unit] of readings) {
      const entity_id = `sensor.${part}_${role}`;
      hass.entities[entity_id] = { entity_id, platform: "havrv", device_id: id, translation_key: role };
      hass.states[entity_id] = { state, attributes: { unit_of_measurement: unit } };
    }
  };
  for (const axle of ["front", "rear_axle_1", "rear_axle_2", "rear_axle_3", "tag_axle"]) {
    for (const side of ["left", "right"]) {
      for (const wheel of axle.startsWith("rear") ? ["outer", "inner"] : ["single"]) {
        addDevice(`tire_${axle}_${side}${wheel === "single" ? "" : `_${wheel}`}`, [
          ["tire_pressure", "102", "psi"], ["tire_temperature", "83", "°F"],
          ["tire_pressure_problem", axle === "front" && side === "left" ? "on" : "off"],
        ]);
      }
    }
  }
  for (const type of ["fresh_water", "gray_water", "black_water"]) {
    addDevice(`tank_${type}`, [
      ["tank_percentage", "50", "%"], ["tank_level", "25", "gal"],
      ["tank_status", type === "black_water" ? "problem" : "ok"],
      ["tank_last_filled", "2026-10-13T12:00:00Z"],
    ]);
  }
  addDevice("tire_monitor", [["comparison", "0"]]);
  addDevice("operations", [["operation_mode", "driving"]]);
  addDevice("existing_mapping", [["mapped_sensor", "1"]]);
  hass.entities["sensor.coach_make"] = {
    entity_id: "sensor.coach_make", platform: "havrv", device_id: "rv", translation_key: "make",
  };
  hass.states["sensor.coach_make"] = { state: "Example make", attributes: {} };
  return { hass, rv, model: buildModel(hass, rv) };
}

function towFixture() {
  const { hass, rv } = completeFixture();
  hass.devices.renamed_tow = {
    id: "renamed_tow", name: "Custom tow", identifiers: [["havrv", "entry_tow"]],
  };
  for (const [domain, key, value, unit] of [
    ["switch", "towing", "off"], ["select", "tow_type", "car"],
    ["number", "tow_weight", "2500", "kg"],
  ]) {
    const entity_id = `${domain}.renamed_${key}`;
    hass.entities[entity_id] = {
      entity_id, platform: "havrv", device_id: "renamed_tow", translation_key: key,
    };
    hass.states[entity_id] = { state: value, attributes: { unit_of_measurement: unit } };
  }
  hass.entities = { ...hass.entities };
  return { hass, rv };
}

test("tow is discovered by registry roles and never leaks into generic system sections", async () => {
  const { hass, rv } = towFixture();
  const model = buildModel(hass, rv);
  assert.deepEqual(model.tow, {
    enabled: "switch.renamed_towing", type: "select.renamed_tow_type", weight: "number.renamed_tow_weight",
  });
  assert.ok(!model.systems.some((system) => system.key === "tow"));
  for (const id of Object.values(model.tow)) assert.ok(model.watched.includes(id));
  const hidden = visibleModel(model, { show_tow: false });
  assert.equal(hidden.tow, undefined);
  for (const id of Object.values(model.tow)) assert.ok(!hidden.watched.includes(id));
  for (const view of [
    rvView(hass, rv, { show_tow: false }),
    await HavrvViewStrategy.generate({ device_id: rv.id, show_tow: false }, hass),
    (await HavrvDashboardStrategy.generate({ show_tow: false }, hass)).views[0],
  ]) {
    assert.equal(view.sections[0].cards[0].show_tow, false);
    assert.doesNotMatch(JSON.stringify(view), /renamed_tow/);
  }
});

test("tow outlines respond live to towing, type, weight, missing data and visibility", () => {
  const { hass, rv } = towFixture();
  const card = new HavrvRvCard();
  card.setConfig({ device_id: rv.id });
  card.hass = hass;
  const off = card.shadowRoot.innerHTML;
  assert.doesNotMatch(off, /class="tow"/);
  hass.states["switch.renamed_towing"].state = "on";
  card.hass = hass;
  assert.match(card.shadowRoot.innerHTML, /data-tow-type="car"/);
  assert.match(card.shadowRoot.innerHTML, /2,500.0 kg/);
  for (const id of Object.values(buildModel(hass, rv).tow)) {
    assert.ok(card.shadowRoot.innerHTML.includes(`data-entity="${id}" tabindex="0" role="button"`));
  }
  hass.states["select.renamed_tow_type"].state = "trailer";
  hass.states["number.renamed_tow_weight"] = { state: "1000", attributes: { unit_of_measurement: "lb" } };
  card.hass = hass;
  assert.match(card.shadowRoot.innerHTML, /data-tow-type="trailer"/);
  assert.match(card.shadowRoot.innerHTML, /1,000.0 lb/);
  hass.states["number.renamed_tow_weight"].state = "unknown";
  card.hass = hass;
  assert.match(card.shadowRoot.innerHTML, /Trailer · No data/);
  assert.doesNotMatch(card.shadowRoot.innerHTML, /1,000.0 lb/);
  for (const status of ["off", "unknown", "unavailable"]) {
    hass.states["switch.renamed_towing"].state = status;
    card.hass = hass;
    assert.doesNotMatch(card.shadowRoot.innerHTML, /class="tow"/);
  }
  hass.states["switch.renamed_towing"].state = "on";
  for (const type of ["boat", "unknown", "unavailable", '<script>alert("bad")</script>']) {
    hass.states["select.renamed_tow_type"].state = type;
    card.hass = hass;
    assert.doesNotMatch(card.shadowRoot.innerHTML, /class="tow"|<script>/);
  }
  hass.states["select.renamed_tow_type"].state = "car";
  card.setConfig({ show_tow: false });
  assert.doesNotMatch(card.shadowRoot.innerHTML, /class="tow"/);
  card.setConfig({});
  assert.match(card.shadowRoot.innerHTML, /class="tow"/);
  assert.deepEqual(summarize(hass, buildModel(hass, rv)), { alert: 2, watch: 0, offline: 0 });
});

test("tow reserves rear space only when active, beyond dense layouts in both orientations", () => {
  const { hass, rv } = towFixture();
  const model = buildModel(hass, rv);
  const bounds = (svg) => /viewBox="([^"]+)"/.exec(svg)[1].split(" ").map(Number);
  for (const orientation of ["horizontal", "vertical"]) {
    for (const show_tires of [false, true]) {
      const config = { show_tires };
      const disabled = renderVehicle(hass, model, orientation, 9, config);
      hass.states["switch.renamed_towing"].state = "on";
      for (const type of ["car", "trailer"]) {
        hass.states["select.renamed_tow_type"].state = type;
        const active = renderVehicle(hass, model, orientation, 9, config);
        const before = bounds(disabled);
        const after = bounds(active);
        if (orientation === "horizontal") {
          assert.ok(after[0] < before[0] - 220);
          assert.ok(after[2] > before[2] + 220);
        } else {
          assert.ok(after[3] > before[3] + 220);
        }
        assert.equal(renderVehicle(hass, model, orientation, 9, { ...config, show_tow: false }), disabled);
        const noPower = renderVehicle(hass, model, orientation, 9, false);
        assert.match(noPower, /class="tow"/);
        assert.doesNotMatch(noPower, /class="power-box /);
        const power = layoutPowerBoxes(hass, visibleModel(model, config), orientation);
        for (const item of [...power.boxes, ...power.icons]) {
          assert.ok(item.x >= after[0] && item.y >= after[1]);
          assert.ok(item.x + item.width <= after[0] + after[2]);
          assert.ok(item.y + item.height <= after[1] + after[3]);
        }
      }
      hass.states["switch.renamed_towing"].state = "off";
      assert.equal(renderVehicle(hass, model, orientation, 9, config), disabled);
    }
  }
});

test("empty tank devices disappear from the card and strategies, not unavailable tanks", async () => {
  const { hass, rv } = completeFixture();
  const card = new HavrvRvCard();
  card.setConfig({ device_id: rv.id });
  card.hass = hass;
  assert.match(card.shadowRoot.innerHTML, /class="tank gray_water /);
  const grayDevice = "device_tank_gray_water";
  const grayIds = Object.values(hass.entities)
    .filter((entry) => entry.device_id === grayDevice).map((entry) => entry.entity_id);
  for (const id of grayIds) hass.states[id].state = "unavailable";
  card.hass = hass;
  assert.match(card.shadowRoot.innerHTML, /class="tank gray_water offline/);
  assert.equal(buildModel(hass, rv).tanks.length, 3);
  const before = summarize(hass, buildModel(hass, rv)).offline;
  hass.entities = Object.fromEntries(Object.entries(hass.entities).filter(([id]) => !grayIds.includes(id)));
  for (const id of grayIds) delete hass.states[id];
  // The device may linger if another integration has attached an entity to it.
  hass.entities["sensor.unrelated"] = {
    entity_id: "sensor.unrelated", platform: "other", device_id: grayDevice, translation_key: "tank_level",
  };
  hass.entities["sensor.custom_gray"] = {
    entity_id: "sensor.custom_gray", platform: "havrv", device_id: grayDevice, translation_key: "custom",
  };
  card.hass = hass;
  const model = buildModel(hass, rv);
  assert.deepEqual(model.tanks.map((tank) => tank.type), ["fresh_water", "black_water"]);
  assert.equal(summarize(hass, model).offline, before - 1);
  assert.doesNotMatch(card.shadowRoot.innerHTML, /class="tank gray_water /);
  for (const view of [
    rvView(hass, rv),
    await HavrvViewStrategy.generate({ device_id: rv.id }, hass),
    (await HavrvDashboardStrategy.generate({ device_id: rv.id }, hass)).views[0],
  ]) {
    assert.doesNotMatch(JSON.stringify(view), /sensor\.tank_gray_water_/);
  }
  hass.entities = Object.fromEntries(Object.entries(hass.entities)
    .filter(([, entry]) => !entry.device_id?.startsWith("device_tank_")));
  card.hass = hass;
  assert.equal(buildModel(hass, rv).tanks.length, 0);
  assert.doesNotMatch(card.shadowRoot.innerHTML, /class="tank /);
  const view = await HavrvViewStrategy.generate({ device_id: rv.id }, hass);
  assert.ok(!view.sections.some((section) => section.cards.some((item) => item.heading === "Tanks")));
});

test("all display classes declare shared true defaults, readable labels and editor fields", () => {
  const form = HavrvRvCard.getConfigForm();
  const schema = form.schema.find((field) => field.type === "grid").schema;
  assert.deepEqual(schema.map((field) => field.name), Object.keys(DISPLAY_CLASSES));
  for (const [key, group] of Object.entries(DISPLAY_CLASSES)) {
    assert.equal(group.default, true);
    assert.equal(dashboardOptions()[key], true);
    assert.equal(dashboardOptions({ [key]: false })[key], false);
    const field = schema.find((field) => field.name === key);
    assert.equal(field.default, true);
    assert.deepEqual(field.selector, { boolean: {} });
    assert.match(form.computeLabel(field), /^Show .+/);
  }
  assert.deepEqual(Object.keys(DISPLAY_CLASSES), [
    "show_header", "show_legend", "show_tires", "show_tanks", "show_power", "show_tow", "show_coach", "show_systems",
  ]);
  const card = new HavrvRvCard();
  card.setConfig({ show_tires: undefined, show_tanks: undefined });
  assert.equal(card._config.show_tires, true);
  assert.equal(card._config.show_tanks, true);
  assert.equal(HavrvRvCard.getStubConfig({ devices: {} }).show_tires, true);
});

test("visibility filtering is nonmutating, removes hidden alerts and preserves positional APIs", () => {
  const { hass, model } = completeFixture();
  const original = structuredClone(model);
  assert.deepEqual(summarize(hass, model), { alert: 2, watch: 0, offline: 0 });
  assert.deepEqual(summarize(hass, model, { show_tires: false }), { alert: 1, watch: 0, offline: 0 });
  assert.deepEqual(summarize(hass, model, { show_tanks: false }), { alert: 1, watch: 0, offline: 0 });
  const config = Object.fromEntries(Object.keys(DISPLAY_CLASSES).map((key) => [key, false]));
  const hidden = visibleModel(model, config);
  for (const key of ["axles", "tanks", "powerSources", "systems", "monitorEntities", "profileEntities"]) {
    assert.deepEqual(hidden[key], []);
  }
  assert.equal(hidden.operationMode, undefined);
  assert.deepEqual(hidden.watched, []);
  assert.deepEqual(hidden.profile, {});
  assert.deepEqual(summarize(hass, model, config), { alert: 0, watch: 0, offline: 0 });
  const legacy = { name: "Legacy model", axles: model.axles, tanks: model.tanks };
  assert.deepEqual(summarize(hass, legacy, false), { alert: 2, watch: 0, offline: 0 });
  assert.match(renderVehicle(hass, legacy, "horizontal", 7, false), /class="tire /);
  for (const orientation of ["horizontal", "vertical"]) {
    const svg = renderVehicle(hass, model, orientation, 7, config);
    assert.doesNotMatch(svg, /class="(?:chip|tire|tank|power-box|power-icon|axle)[ "]/);
    assert.doesNotMatch(renderVehicle(hass, hidden, orientation, 7), /class="tire /);
    const noPower = renderVehicle(hass, model, orientation, 7, false);
    assert.doesNotMatch(noPower, /class="power-box /);
    assert.match(noPower, /class="tire /);
    assert.match(noPower, /class="tank /);
    const bounds = (drawing) => /viewBox="([^"]+)"/.exec(drawing)[1].split(" ").map(Number);
    const hiddenBounds = bounds(svg);
    const visibleBounds = bounds(noPower);
    assert.ok(hiddenBounds[2] < visibleBounds[2] && hiddenBounds[3] < visibleBounds[3]);
    assert.equal(layoutPowerBoxes(hass, hidden, orientation).obstacles.length, 0);
  }
  assert.deepEqual(model, original);
});

test("both strategies propagate presentation and every visibility option and omit sections", async () => {
  const { hass, rv } = completeFixture();
  for (const layout of ["auto", "horizontal", "vertical"]) {
    const config = {
      device_id: rv.id, layout,
      ...Object.fromEntries(Object.keys(DISPLAY_CLASSES).map((key) => [key, false])),
    };
    const dashboard = await HavrvDashboardStrategy.generate(config, hass);
    const view = await HavrvViewStrategy.generate(config, hass);
    for (const generated of [rvView(hass, rv, config), dashboard.views[0], view]) {
      assert.equal(generated.sections.length, 1);
      assert.deepEqual(generated.sections[0].cards[0], { type: "custom:havrv-rv-card", ...config });
    }
  }
  const defaults = rvView(hass, rv);
  const headings = (config) => rvView(hass, rv, config).sections.flatMap((section) =>
    section.cards.filter((card) => card.type === "heading").map((card) => card.heading));
  assert.ok(headings({}).includes("Tanks"));
  assert.ok(headings({}).includes("Tire analysis"));
  assert.ok(headings({}).includes("Coach"));
  assert.ok(headings({}).includes("existing_mapping"));
  assert.ok(!headings({ show_tanks: false }).includes("Tanks"));
  assert.ok(!headings({ show_tires: false }).includes("Tire analysis"));
  assert.ok(!headings({ show_coach: false }).includes("Coach"));
  assert.ok(!headings({ show_systems: false }).includes("existing_mapping"));
  assert.equal(defaults.sections.length - rvView(hass, rv, { show_power: false }).sections.length, 6);
  assert.equal(defaults.sections[0].cards[0].show_tanks, true);
  assert.equal(defaults.sections[0].cards[0].show_tires, true);
});

test("card toggles hide diagrams, messages, counts and coach metadata, and restore live data", () => {
  const { hass } = completeFixture();
  const card = new HavrvRvCard();
  card.setConfig({ device_id: "rv" });
  card.hass = hass;
  assert.match(card.shadowRoot.innerHTML, /2 alerts/);
  assert.match(card.shadowRoot.innerHTML, /Example make/);
  const key = card._renderKey;
  card.setConfig({ show_tires: false, show_tanks: false, show_power: false, show_coach: false });
  assert.notEqual(card._renderKey, key);
  assert.doesNotMatch(card.shadowRoot.innerHTML, /class="tire |class="tank |class="chip |class="power-box |2 alerts|Set the axle layout|Example make|class="pill mode"/);
  card.setConfig({ show_header: false, show_legend: false, show_tires: false });
  assert.doesNotMatch(card.shadowRoot.innerHTML, /<header>|<div class="legend">/);
  assert.match(card.shadowRoot.innerHTML, /class="tank /);
  card.setConfig({});
  assert.match(card.shadowRoot.innerHTML, /2 alerts/);
  hass.states["sensor.tire_front_left_tire_pressure_problem"].state = "off";
  card.hass = hass;
  assert.match(card.shadowRoot.innerHTML, /1 alert/);
  hass.states["sensor.tank_fresh_water_tank_percentage"].state = "unavailable";
  card.hass = hass;
  assert.match(card.shadowRoot.innerHTML, /1 no data/);
  card.setConfig({ show_tanks: false });
  assert.doesNotMatch(card.shadowRoot.innerHTML, /1 no data|1 alert/);
});

test("empty models keep setup hints only for visible tires and strategies handle no profiles", async () => {
  const { hass } = fixture();
  const card = new HavrvRvCard();
  card.setConfig({});
  card.hass = hass;
  assert.match(card.shadowRoot.innerHTML, /Set the axle layout/);
  card.setConfig({ show_tires: false });
  assert.doesNotMatch(card.shadowRoot.innerHTML, /Set the axle layout|chip-bg ghost|class="tire /);
  assert.match(card.shadowRoot.innerHTML, /class="power-box /);
  const empty = { devices: {}, entities: {}, states: {} };
  card.hass = empty;
  assert.match(card.shadowRoot.innerHTML, /No HAVRV RV profile/);
  assert.match(JSON.stringify(await HavrvDashboardStrategy.generate({}, empty)), /No HAVRV RV profile/);
  assert.match(JSON.stringify(await HavrvViewStrategy.generate({}, empty)), /No HAVRV RV profile/);
});

test("resize switches auto orientation without shrinking, and explicit layouts stay fixed", () => {
  const { hass } = completeFixture();
  let callback;
  let disconnected = false;
  globalThis.ResizeObserver = class {
    constructor(handler) { callback = handler; }
    observe() {}
    disconnect() { disconnected = true; }
  };
  try {
    const card = new HavrvRvCard();
    card.setConfig({});
    card.hass = hass;
    card.connectedCallback();
    for (const [width, orientation] of [[320, "vertical"], [1200, "horizontal"], [480, "vertical"]]) {
      callback([{ contentRect: { width } }]);
      assert.equal(card._orientation, orientation);
      const html = card.shadowRoot.innerHTML;
      assert.match(html, new RegExp(`class="vehicle ${orientation}"`));
      const boundsWidth = Number(/viewBox="[^ ]+ [^ ]+ ([^ ]+) [^"]+"/.exec(html)[1]);
      assert.match(html, new RegExp(`min-width:${boundsWidth}px`));
      assert.match(html, /\.drawing \{ overflow: auto; max-height: 80vh;/);
      assert.doesNotMatch(html, /svg.vehicle.vertical \{ max-height/);
    }
    for (const layout of ["horizontal", "vertical"]) {
      card.setConfig({ layout });
      callback([{ contentRect: { width: layout === "horizontal" ? 320 : 1200 } }]);
      assert.equal(card._orientation, layout);
    }
    card.disconnectedCallback();
    assert.equal(disconnected, true);
  } finally {
    delete globalThis.ResizeObserver;
  }
});

test("maximum axles, duals, three tanks and dense banks have nonoverlapping readable layouts", () => {
  const { hass, model } = completeFixture();
  const bank = model.powerSources.find((source) => source.key === "house_bank_1");
  model.powerSources.push(...Array.from({ length: 30 }, (_, index) => ({
    ...bank, key: `house_bank_${index + 3}`,
  })));
  const intersects = (a, b) => a.x < b.x + b.width && a.x + a.width > b.x
    && a.y < b.y + b.height && a.y + a.height > b.y;
  for (const orientation of ["horizontal", "vertical"]) {
    const layout = layoutPowerBoxes(hass, model, orientation);
    const { boxes, icons, obstacles, bounds } = layout;
    const tankRegion = orientation === "horizontal"
      ? { x: 432, y: 120, width: 240, height: 136 }
      : { x: 180, y: 242, width: 136, height: 240 };
    assert.equal(obstacles.length, 10);
    assert.ok(obstacles.every((chip) => chip.width >= 156 && chip.height >= 52));
    assert.ok(icons.every((icon) => icon.width === 44));
    const items = [...boxes, ...icons, ...obstacles];
    for (const item of items) {
      for (const other of items) {
        if (item !== other) assert.equal(intersects(item, other), false);
      }
      assert.equal(intersects(item, tankRegion), false);
      assert.ok(item.x >= bounds.x && item.y >= bounds.y);
      assert.ok(item.x + item.width <= bounds.x + bounds.width);
      assert.ok(item.y + item.height <= bounds.y + bounds.height);
    }
    const svg = renderVehicle(hass, model, orientation, 1);
    assert.equal((svg.match(/class="tire (?:ok|alert)"/g) || []).length, 16);
    assert.equal((svg.match(/class="tank-label /g) || []).length, 3);
    assert.doesNotMatch(svg, /compact-tank|textLength=/);
    for (const chip of obstacles) {
      assert.ok(svg.includes(`x="${chip.x}" y="${chip.y}" width="${chip.width}" height="${chip.height}"`));
    }
    const withoutPower = renderVehicle(hass, model, orientation, 1, false);
    const viewBox = /viewBox="([^"]+)"/.exec(withoutPower)[1].split(" ").map(Number);
    for (const chip of obstacles) {
      assert.ok(chip.x >= viewBox[0] && chip.y >= viewBox[1]);
      assert.ok(chip.x + chip.width <= viewBox[0] + viewBox[2]);
      assert.ok(chip.y + chip.height <= viewBox[1] + viewBox[3]);
    }
    const noTires = layoutPowerBoxes(hass, visibleModel(model, { show_tires: false }), orientation);
    assert.equal(noTires.obstacles.length, 0);
    assert.ok(noTires.bounds.width <= bounds.width && noTires.bounds.height <= bounds.height);
  }
});

test("long electrical readings expand columns instead of squeezing glyphs", () => {
  const { hass, rv } = fixture();
  const model = buildModel(hass, rv);
  const bank = model.powerSources.find((source) => source.key === "house_bank_1");
  hass.states[bank.voltage].state = "123456789";
  hass.states[bank.voltage].attributes.unit_of_measurement = "mV";
  for (const orientation of ["horizontal", "vertical"]) {
    const layout = layoutPowerBoxes(hass, model, orientation);
    const box = layout.boxes.find((item) => item.source === bank);
    assert.ok(box.width > 156);
    const svg = renderVehicle(hass, model, orientation, 1);
    assert.doesNotMatch(svg, /textLength=|lengthAdjust=/);
    assert.match(svg, /123,456,789.0/);
  }
});

test("long tire readings expand labels and the power collision obstacles together", () => {
  const { hass, model } = completeFixture();
  const tire = model.axles[1].left[0];
  hass.states[tire.pressure].state = "123456789";
  for (const orientation of ["horizontal", "vertical"]) {
    const layout = layoutPowerBoxes(hass, model, orientation);
    const chip = layout.obstacles.find((box) => box.axle.key === "rear_axle_1" && box.side === "left");
    assert.ok(chip.width > 156);
    const svg = renderVehicle(hass, model, orientation, 1);
    assert.ok(svg.includes(`x="${chip.x}" y="${chip.y}" width="${chip.width}" height="${chip.height}"`));
    assert.match(svg, /123,456,789/);
  }
});

test("readouts use colors instead of Enabled rows, tire-sized graphics and one common legend", () => {
  const { hass, rv } = fixture();
  const model = buildModel(hass, rv);
  for (const orientation of ["horizontal", "vertical"]) {
    const layout = layoutPowerBoxes(hass, model, orientation);
    assert.ok(layout.icons.every((icon) => icon.width === 44));
    const svg = renderVehicle(hass, model, orientation, 1);
    assert.doesNotMatch(svg, /power-leader|Enabled: Yes|Enabled: No/);
    assert.equal((svg.match(/class="equipment-tag"/g) || []).length, layout.icons.length);
    assert.ok(layout.boxes.every((box) => !box.metrics.includes("enabled")));
  }
  const card = new HavrvRvCard();
  card.setConfig({ device_id: "rv" });
  card.hass = hass;
  assert.equal((card.shadowRoot.innerHTML.match(/<div class="legend">/g) || []).length, 1);
  assert.match(card.shadowRoot.innerHTML, /OK \/ On/);
  assert.match(card.shadowRoot.innerHTML, /Watch \/ Warning/);
  assert.match(card.shadowRoot.innerHTML, /Alert \/ Problem/);
  assert.doesNotMatch(card.shadowRoot.innerHTML, /Electrical:<\/span>/);
  card.setConfig({ show_power: false });
  assert.equal((card.shadowRoot.innerHTML.match(/<div class="legend">/g) || []).length, 1);
  assert.doesNotMatch(card.shadowRoot.innerHTML, /OK \/ On/);
  card.setConfig({ show_legend: false });
  assert.doesNotMatch(card.shadowRoot.innerHTML, /<div class="legend">/);
});

test("enlarged equipment avoids the reserved tank band and keeps colocated banks in their region", () => {
  const { hass, rv } = fixture();
  const model = buildModel(hass, rv);
  model.tanks = [{ name: "Fresh", type: "fresh_water" }];
  for (const orientation of ["horizontal", "vertical"]) {
    const layout = layoutPowerBoxes(hass, model, orientation);
    const tank = orientation === "horizontal"
      ? { x: 316, y: 120, width: 320, height: 136 }
      : { x: 180, y: 278, width: 136, height: 320 };
    for (const icon of layout.icons) {
      assert.ok(icon.x + icon.width <= tank.x || tank.x + tank.width <= icon.x
        || icon.y + icon.height <= tank.y || tank.y + tank.height <= icon.y);
    }
    const banks = layout.icons.filter((icon) => icon.source.key.startsWith("house"));
    for (const icon of banks) {
      const u = orientation === "horizontal" ? icon.anchor[0] - 30 : 884 - icon.anchor[1];
      assert.ok(Math.abs(u - 110) <= 124);
    }
  }
});

test("single and dual tire readouts put pressure and temperature on the same baseline", () => {
  const { hass, rv } = fixture();
  const model = buildModel(hass, rv);
  for (const [id, value, unit] of [
    ["sensor.pressure", "102", "psi"], ["sensor.temperature", "83", "°F"],
  ]) {
    hass.states[id] = { state: value, attributes: { unit_of_measurement: unit } };
  }
  const tire = { name: "Test tire", pressure: "sensor.pressure", temperature: "sensor.temperature" };
  for (const dual of [false, true]) {
    model.axles = [{
      kind: "front", key: "front",
      left: dual ? [tire, { ...tire, wheel: "inner" }] : [tire],
      right: [tire],
    }];
    for (const orientation of ["horizontal", "vertical"]) {
      const svg = renderVehicle(hass, model, orientation, 1);
      const rows = [...svg.matchAll(/<g class="row"[\s\S]*?<\/g>/g)].map(([row]) => row);
      assert.equal(rows.length, dual ? 3 : 2);
      for (const row of rows) {
        const pressureY = /class="row-pressure"[^>]* y="([^"]+)"/.exec(row)[1];
        const tempY = /class="small row-right"[^>]* y="([^"]+)"/.exec(row)[1];
        assert.equal(pressureY, tempY);
        assert.match(row, /83 °F/);
      }
    }
  }
  hass.states["sensor.pressure"].state = "unavailable";
  assert.match(renderVehicle(hass, model, "horizontal", 1), /83 °F/);
  hass.states["sensor.temperature"].state = "unavailable";
  assert.match(renderVehicle(hass, model, "horizontal", 1), /No data/);
});

test("single and dual tire readings target their own entities in both orientations", () => {
  const { hass, model } = completeFixture();
  for (const orientation of ["horizontal", "vertical"]) {
    for (const unavailable of [false, true]) {
      for (const axle of model.axles) {
        for (const tire of [...axle.left, ...axle.right]) {
          hass.states[tire.pressure].state = unavailable ? "unavailable" : "102";
          hass.states[tire.temperature].state = unavailable ? "unavailable" : "83";
        }
      }
      const svg = renderVehicle(hass, model, orientation, 1);
      for (const axle of model.axles) {
        for (const tire of [...axle.left, ...axle.right]) {
          for (const [role, css] of [["pressure", "row-pressure"], ["temperature", "small row-right"]]) {
            assert.ok(svg.includes(`data-entity="${tire[role]}" tabindex="0" role="button"`));
            const tags = [...svg.matchAll(new RegExp(`<text class="${css}"[^>]*>`, "g"))];
            assert.ok(tags.some(([tag]) => tag.includes(`data-entity="${tire[role]}"`)));
          }
          assert.ok(svg.includes(`data-entity="${tire.pressure}" tabindex="0" role="button" aria-label="${tire.name}:`));
        }
      }
    }
  }
  delete model.axles[0].left[0].temperature;
  for (const orientation of ["horizontal", "vertical"]) {
    const svg = renderVehicle(hass, model, orientation, 1);
    assert.doesNotMatch(svg, /data-entity="(?:undefined|null|)"/);
  }
});

test("tank volume, percentage, electrical values and tow type/weight have distinct targets", () => {
  const { hass, rv } = towFixture();
  const model = buildModel(hass, rv);
  hass.states[model.tow.enabled].state = "on";
  for (const orientation of ["horizontal", "vertical"]) {
    const svg = renderVehicle(hass, model, orientation, 1);
    for (const tank of model.tanks) {
      const volume = orientation === "horizontal"
        ? /<tspan class="tank-vol"[^>]*>/g : /<text class="tiny"[^>]*>/g;
      assert.ok([...svg.matchAll(volume)].some(([tag]) => tag.includes(`data-entity="${tank.level}"`)));
      const percentages = orientation === "horizontal" ? /<tspan dx="6"[^>]*>/g : /<text class="tank-pct[^>]*>/g;
      assert.ok([...svg.matchAll(percentages)].some(([tag]) => tag.includes(`data-entity="${tank.percentage}"`)));
    }
    assert.match(svg, new RegExp(`<text class="tow-label"[^>]*data-entity="${model.tow.type}"`));
    assert.match(svg, new RegExp(`<tspan[^>]*data-entity="${model.tow.weight}"`));
    const layout = layoutPowerBoxes(hass, model, orientation);
    for (const box of layout.boxes) {
      for (const metric of box.metrics) {
        assert.ok(svg.includes(`<g data-entity="${box.source[metric]}" tabindex="0" role="button"`));
      }
      for (const row of box.rows.filter((row) => row.length === 1)) {
        assert.ok([...svg.matchAll(/<text class="small power-label"[^>]*>/g)]
          .some(([tag]) => tag.includes(`data-entity="${box.source[row[0]]}"`)));
      }
    }
  }
});

test("single-tire HOT and BAT flags open temperature and battery rather than pressure", () => {
  const { hass, model } = completeFixture();
  const tire = model.axles[0].left[0];
  tire.temperatureProblem = "binary_sensor.hot";
  tire.batteryProblem = "binary_sensor.low_battery";
  tire.battery = "sensor.battery";
  hass.states[tire.temperatureProblem] = { state: "on", attributes: {} };
  hass.states[tire.batteryProblem] = { state: "on", attributes: {} };
  for (const orientation of ["horizontal", "vertical"]) {
    const svg = renderVehicle(hass, model, orientation, 1);
    assert.ok(svg.includes(`<tspan data-entity="${tire.temperature}" tabindex="0" role="button">HOT</tspan>`));
    assert.ok(svg.includes(`<tspan data-entity="${tire.battery}" tabindex="0" role="button">BAT</tspan>`));
  }
  delete tire.battery;
  assert.ok(renderVehicle(hass, model, "horizontal", 1)
    .includes(`<tspan data-entity="${tire.batteryProblem}" tabindex="0" role="button">BAT</tspan>`));
});

test("click and keyboard activation open the innermost reading once, with a row fallback", () => {
  const card = new HavrvRvCard();
  const events = [];
  card.dispatchEvent = (event) => events.push(event);
  for (const type of ["click", "keydown"]) {
    for (const key of ["Enter", " "]) {
      for (const specific of ["sensor.temperature", "sensor.volume", "sensor.line_2_voltage", undefined]) {
        let prevented = 0;
        let stopped = 0;
        const path = [new Element(), new Element(specific), new Element("sensor.pressure")];
        const before = events.length;
        card.shadowRoot.listeners.get(type)({
          key, composedPath: () => path,
          preventDefault: () => prevented++,
          stopPropagation: () => stopped++,
        });
        assert.equal(events.length, before + 1);
        assert.equal(events.at(-1).type, "hass-more-info");
        assert.deepEqual(events.at(-1).detail, { entityId: specific || "sensor.pressure" });
        assert.equal(events.at(-1).bubbles, true);
        assert.equal(events.at(-1).composed, true);
        assert.equal(prevented, 1);
        assert.equal(stopped, 1);
      }
    }
  }
  const before = events.length;
  const ignored = {
    key: "Escape", composedPath: () => [new Element()],
    preventDefault: () => assert.fail("non-reading must not activate"),
    stopPropagation: () => assert.fail("non-reading must not activate"),
  };
  card.shadowRoot.listeners.get("click")(ignored);
  card.shadowRoot.listeners.get("keydown")(ignored);
  assert.equal(events.length, before);
});

test("all equipment at R-Rear retains independent unclipped readouts and graphics", () => {
  const { hass, rv } = fixture();
  const model = buildModel(hass, rv);
  for (const source of model.powerSources) {
    hass.states[source.location].state = source.key === "shore_power" ? "right" : "right_rear";
  }
  model.axles = [
    { kind: "front", key: "front", left: [{}], right: [{}] },
    { kind: "drive", key: "rear", left: [{}, {}], right: [{}, {}] },
    { kind: "tag", key: "tag", left: [{}], right: [{}] },
  ];
  model.tanks = [{ name: "Fresh", type: "fresh_water" }];
  const intersects = (a, b) => a.x < b.x + b.width && a.x + a.width > b.x
    && a.y < b.y + b.height && a.y + a.height > b.y;
  for (const orientation of ["horizontal", "vertical"]) {
    const { boxes, icons, obstacles, bounds } = layoutPowerBoxes(hass, model, orientation);
    assert.equal(boxes.length, 6);
    assert.equal(icons.length, 6);
    assert.ok(icons.every((icon) => icon.width === 44));
    for (const box of boxes) {
      assert.equal(box.side, 1);
      for (const other of [...boxes, ...icons, ...obstacles]) {
        if (box !== other) assert.equal(intersects(box, other), false);
      }
      assert.ok(box.x >= bounds.x && box.y >= bounds.y);
      assert.ok(box.x + box.width <= bounds.x + bounds.width);
      assert.ok(box.y + box.height <= bounds.y + bounds.height);
    }
    for (const icon of icons) {
      for (const other of [...icons, ...obstacles]) {
        if (icon !== other) assert.equal(intersects(icon, other), false);
      }
      const lateral = orientation === "horizontal" ? icon.anchor[1] - 188 : icon.anchor[0] - 248;
      assert.ok(icon.source.key === "shore_power" ? lateral > 90 : lateral > 0 && lateral < 90);
      if (icon.source.key !== "shore_power") {
        const u = orientation === "horizontal" ? icon.anchor[0] - 30 : 884 - icon.anchor[1];
        assert.ok(u >= 16 && u < 340, `${icon.source.key} drifted outside the rear region`);
      }
    }
    assert.doesNotMatch(renderVehicle(hass, model, orientation, 1), /power-leader/);
  }
});

test("vertical tanks/power use the tire-card width instead of an extra shore column", () => {
  const { hass, model } = completeFixture();
  model.axles = model.axles.filter((axle) => ["front", "rear_axle_1", "tag_axle"].includes(axle.key));
  model.tanks = model.tanks.filter((tank) => tank.type !== "gray_water");
  model.powerSources = model.powerSources.filter((source) =>
    ["house_bank_1", "chassis_bank_1", "generator", "shore_power"].includes(source.key));
  for (const source of model.powerSources) {
    hass.states[source.location].state = source.key === "shore_power" ? "left" : "left_mid";
  }
  const bounds = (svg) => /viewBox="([^"]+)"/.exec(svg)[1].split(" ").map(Number);
  const driving = bounds(renderVehicle(hass, model, "vertical", 1, {
    show_tanks: false, show_power: false,
  }));
  for (const unmapped of [false, true]) {
    if (unmapped) {
      model.powerSources = model.powerSources.map((source) => ({
        key: source.key, name: source.name, location: source.location,
      }));
    }
    const parked = visibleModel(model, { show_tires: false });
    const layout = layoutPowerBoxes(hass, parked, "vertical");
    assert.ok(layout.bounds.width <= driving[2], `${layout.bounds.width} exceeds ${driving[2]}`);
    assert.ok(layout.bounds.height <= driving[3] && layout.bounds.height >= driving[3] - 24);
    assert.equal(layout.boxes.length, 4);
    const left = layout.boxes.filter((box) => box.side === -1);
    assert.equal(new Set(left.map((box) => box.x)).size, 1);
  }
});

test("equipment tags have their own badge below the complete symbol and within its footprint", () => {
  const { hass, rv } = fixture();
  const layout = layoutPowerBoxes(hass, buildModel(hass, rv), "vertical");
  const svg = renderPowerBoxes(hass, layout);
  assert.match(svg, /class="equipment-badge" x="0" y="25" width="24" height="8"/);
  assert.match(svg, /class="equipment-tag" x="12" y="31"/);
  assert.match(svg, /class="equipment-energy"/);
  for (const icon of layout.icons) {
    assert.ok(33 * icon.width / 24 <= icon.height);
    assert.ok(icon.y + icon.height <= layout.bounds.y + layout.bounds.height);
  }
  assert.match(text, /\.equipment-detail \{ fill: none; stroke: var\(--hv-text\)/);
});

test("coach silhouettes omit decorative roof equipment without removing mapped graphics", () => {
  const { hass, rv } = fixture();
  const model = buildModel(hass, rv);
  for (const orientation of ["horizontal", "vertical"]) {
    const svg = renderVehicle(hass, model, orientation, 1);
    assert.doesNotMatch(svg, /roof-unit|class="[^"]*\bvent\b/);
    assert.match(svg, /class="body"/);
    assert.match(svg, /class="glass"/);
    assert.match(svg, /class="mirror"/);
    assert.match(svg, /class="power-icon /);
  }
});

test("last data tracks valid reports, not outage timestamps, and uses the oldest missing channel", () => {
  const now = Date.parse("2026-10-25T12:00:00Z");
  const hass = { states: {
    "sensor.zero": { state: "0", last_reported: "2026-10-25T10:00:00Z" },
    "sensor.second": { state: "12", last_updated: "2026-10-25T11:59:00Z" },
    "binary_sensor.off": { state: "off", last_changed: "2026-10-25T11:00:00Z" },
  } };
  const ids = Object.keys(hass.states);
  const history = new Map();
  rememberReadings(hass, ids, history, now);
  assert.equal(missingReadingText(hass, ids, now), "");
  for (const id of ids) {
    hass.states[id] = { state: "unavailable", last_updated: "2026-10-25T12:00:00Z" };
  }
  rememberReadings(hass, ids, history, now);
  assert.equal(missingReadingText(hass, ids, now), "Last data 2h ago");
  assert.equal(missingReadingText(hass, ["binary_sensor.off"], now), "Last data 1h ago");
  assert.equal(missingReadingText(hass, ["sensor.second"], now), "Last data 1m ago");
  assert.equal(missingReadingText(hass, ["sensor.second"], now + 2 * 86400000), "Last data 2d ago");
  delete hass.states["sensor.zero"];
  assert.equal(missingReadingText(hass, ["sensor.zero"], now), "Last data 2h ago");
  assert.equal(missingReadingText(hass, ["sensor.zero", "sensor.never"], now), "Last data unknown");
  hass.states["sensor.second"] = { state: "1", last_reported: "2026-10-25T11:59:45Z" };
  rememberReadings(hass, ids, history, now);
  assert.equal(missingReadingText(hass, ["sensor.second"], now), "");
  hass.states["sensor.second"].state = "unknown";
  assert.equal(missingReadingText(hass, ["sensor.second"], now), "Last data 15s ago");
});

test("boolean tire battery mirrors count as valid data and retain their last report", () => {
  const { hass, model } = completeFixture();
  const now = Date.parse("2026-10-25T12:00:00Z");
  const ids = model.axles.flatMap((axle) => [...axle.left, ...axle.right].map((tire, i) => {
    const id = `sensor.${axle.key}_${tire.key || i}_battery`;
    tire.battery = id;
    hass.entities[id] = { entity_id: id, platform: "havrv", translation_key: "tire_battery" };
    return id;
  }));
  assert.ok(ids.length > 0);
  const history = new Map();
  for (const state of ["off", "on"]) {
    for (const id of ids) {
      hass.states[id] = { state, attributes: {}, last_updated: "2026-10-25T11:00:00Z" };
    }
    rememberReadings(hass, ids, history, now);
    assert.equal(missingReadingText(hass, ids, now), "");
    for (const orientation of ["horizontal", "vertical"]) {
      assert.doesNotMatch(renderVehicle(hass, model, orientation, 1), /class="data-age"/);
    }
  }
  for (const id of ids) hass.states[id].state = "unavailable";
  rememberReadings(hass, ids, history, now);
  assert.equal(missingReadingText(hass, ids, now), "Last data 1h ago");
  hass.states["sensor.invalid_pressure"] = { state: "on" };
  assert.equal(missingReadingText(hass, ["sensor.invalid_pressure"], now), "Last data unknown");
});

test("missing, malformed, blank and future reports never invent last-good timestamps", () => {
  const now = Date.parse("2026-10-25T12:00:00Z");
  const hass = { states: {
    "sensor.never": { state: "unavailable", last_updated: "2026-10-25T11:00:00Z" },
    "sensor.bad": { state: "not a number", last_updated: "2026-10-25T11:00:00Z" },
    "sensor.blank": { state: " ", last_updated: "2026-10-25T11:00:00Z" },
    "sensor.timestamp": { state: "1", last_updated: "invalid" },
    "sensor.future": { state: "1", last_updated: "2026-10-26T12:00:00Z" },
  } };
  const history = new Map();
  rememberReadings(hass, Object.keys(hass.states), history, now);
  assert.equal(history.size, 0);
  assert.equal(missingReadingText(hass, ["sensor.never"], now), "Last data unknown");
  assert.equal(missingReadingText(hass, ["sensor.missing"], now), "Last data unknown");
  assert.equal(missingReadingText(hass, [], now), "");
});

test("retained tire values are explicitly historical and respect display units and zeroes", () => {
  const now = Date.parse("2026-10-31T12:00:00Z");
  const hass = { states: { "sensor.old": {
    state: "unavailable", attributes: {
      last_valid_value: 100, last_valid_unit: "psi", unit_of_measurement: "kPa",
      last_valid_time: "2026-10-31T06:00:00Z",
    },
  } }, entities: { "sensor.old": { display_precision: 1 } } };
  const value = tireReading(hass, "sensor.old", "pressure", now);
  assert.equal(value.retained, true);
  assert.equal(value.text, "689.5");
  assert.equal(value.unit, "kPa");
  assert.ok(Math.abs(convertTireValue(32, "°F", "°C", "temperature")) < 0.00001);
  assert.equal(convertTireValue(273.15, "K", "°C", "temperature"), 0);
  assert.equal(convertTireValue(0, "°C", "°F", "temperature"), 32);
  for (const [unit, pascals] of [
    ["mPa", 0.001], ["Pa", 1], ["hPa", 100], ["kPa", 1000], ["bar", 100000],
    ["cbar", 1000], ["mbar", 100], ["psi", 6894.757], ["inHg", 3386.388640341],
    ["mmHg", 133.322387415], ["inH\u2082O", 249.0889083333348], ["atm", 101325],
  ]) {
    assert.ok(Math.abs(convertTireValue(1, unit, "Pa", "pressure") - pascals) < 0.000001);
    assert.ok(Math.abs(convertTireValue(pascals, "Pa", unit, "pressure") - 1) < 0.000001);
  }
  assert.equal(convertTireValue(1, "bogus", "kPa", "pressure"), undefined);
  for (const invalid of ["unavailable", "", "100", NaN, Infinity, undefined]) {
    hass.states["sensor.old"].attributes.last_valid_value = invalid;
    assert.equal(tireReading(hass, "sensor.old", "pressure", now), undefined);
  }
  hass.states["sensor.old"].attributes.last_valid_value = 0;
  assert.equal(tireReading(hass, "sensor.old", "pressure", now).value, 0);
  for (const invalid of ["bad", "2026-11-01T12:00:00Z", undefined]) {
    hass.states["sensor.old"].attributes.last_valid_time = invalid;
    assert.equal(tireReading(hass, "sensor.old", "pressure", now), undefined);
  }
  hass.states["sensor.old"] = { state: "101", attributes: { unit_of_measurement: "psi" } };
  assert.equal(tireReading(hass, "sensor.old", "pressure", now).retained, undefined);
});

test("pressure sparklines use a true one-hour time axis, thin paths and outage breaks", () => {
  const now = Date.parse("2026-10-31T12:00:00Z");
  const sample = (minutes, value, unit = "psi") => ({ time: now - minutes * 60000, value, unit });
  assert.equal(pressureSparkline([sample(90, 100), sample(61, 102)], "psi", 0, 0, 60, now), "");
  assert.equal(pressureSparkline([sample(30, 100)], "psi", 0, 0, 60, now), "");
  assert.equal(pressureSparkline([sample(30, 100), sample(20, null), sample(10, 102)], "psi", 0, 0, 60, now), "");
  const svg = pressureSparkline([
    sample(60, 100), sample(50, 101), sample(40, null), sample(30, 102),
    sample(20, 103), sample(-1, 200),
  ], "psi", 0, 0, 60, now);
  assert.match(svg, /class="pressure-sparkline"/);
  assert.match(svg, /d="M0 -4 L10 -7.3  M30 -10.7 L40 -14"/);
  assert.doesNotMatch(svg, /L60|NaN|Infinity|<rect|<circle/);
  assert.match(svg, /past hour/);
  assert.match(text, /\.pressure-sparkline \{ fill: none;/);
  const flat = pressureSparkline([sample(60, 0), sample(30, 0)], "psi", 0, 0, 60, now);
  assert.match(flat, /M0 -9 L30 -9/);
  const converted = pressureSparkline([sample(60, 100), sample(30, 689.4757, "kPa")], "psi", 0, 0, 60, now);
  assert.match(converted, /M0 -9 L30 -9/);
});

test("compressed Recorder history keeps invalid-state gaps and real source timestamps", () => {
  const now = Date.parse("2026-10-31T12:00:00Z");
  const seconds = (minutes) => (now - minutes * 60000) / 1000;
  const samples = pressureHistory([
    { s: "90", lu: seconds(61), a: { unit_of_measurement: "psi" } },
    { s: "0", lu: seconds(50), a: { unit_of_measurement: "psi" } },
    { s: "unavailable", lu: seconds(40) },
    { s: "100", lu: seconds(10), a: { unit_of_measurement: "psi", last_valid_time: new Date(seconds(20) * 1000).toISOString() } },
    { s: "1", lu: seconds(-1) },
    { s: " ", lu: seconds(5) },
    { s: "3", lu: "malformed" },
  ], now);
  assert.deepEqual(samples.map((point) => point.value), [0, null, 100, null]);
  assert.equal(samples[2].time, seconds(20) * 1000);
});

test("tire rows combine live, last-known, offline and actual reception age on one line", () => {
  const { hass, model } = completeFixture();
  const tire = model.axles[0].left[0];
  const ago = new Date(Date.now() - 6 * 3600000).toISOString();
  hass.states[tire.pressureProblem].state = "off";
  tire.lastReceived = "sensor.actual_reception";
  hass.states[tire.lastReceived] = { state: ago, attributes: {} };
  for (const metric of ["pressure", "temperature"]) {
    Object.assign(hass.states[tire[metric]].attributes, {
      last_valid_value: metric === "pressure" ? 103.7 : 77,
      last_valid_unit: metric === "pressure" ? "psi" : "°F", last_valid_time: ago,
    });
    hass.states[tire[metric]].state = "unavailable";
  }
  for (const orientation of ["horizontal", "vertical"]) {
    const svg = renderVehicle(hass, model, orientation, 1);
    const row = [...svg.matchAll(/<g class="row"[\s\S]*?<\/g>/g)]
      .find(([row]) => row.includes(`data-entity="${tire.pressure}"`))[0];
    assert.match(row, /Last 104/);
    assert.match(row, /class="retained">77 °F/);
    assert.match(row, /Offline 6h/);
    assert.match(row, /Offline; last received 6h ago/);
    assert.match(row, /class="retained mid"/);
    assert.match(row, /Last valid pressure:/);
    assert.ok(row.includes(`data-entity="${tire.lastReceived}" tabindex="0" role="button"`));
    const baselines = [...row.matchAll(/<text[^>]+ y="([^"]+)"/g)].map((match) => match[1]);
    assert.equal(new Set(baselines).size, 1);
    assert.doesNotMatch(row, /pressure-sparkline/);
    assert.match(svg, /class="dot offline"/);
  }
  hass.states[tire.temperature].state = "78";
  assert.match(renderVehicle(hass, model, "vertical", 1), />78 °F<\/tspan>/);
  assert.doesNotMatch(renderVehicle(hass, model, "vertical", 1), /Last 78/);
  hass.states[tire.lastReceived].state = "unknown";
  assert.match(renderVehicle(hass, model, "vertical", 1), /Offline \?/);
  hass.states[tire.pressure].state = "105";
  hass.states[tire.lastReceived].state = new Date(Date.now() - 6 * 60000).toISOString();
  const live = renderVehicle(hass, model, "vertical", 1);
  assert.match(live, /> · 6m<\/text>/);
  assert.doesNotMatch(live, /Last 104|Last 77|Offline 6h/);
  delete tire.lastReceived;
  hass.states[tire.pressure] = { state: "unavailable", attributes: { unit_of_measurement: "psi" } };
  assert.match(renderVehicle(hass, model, "vertical", 1), /Offline; last valid reading unknown/);
});

test("last-received registry roles are discovered and watched without becoming numeric readings", () => {
  const { hass, rv } = completeFixture();
  const pressure = Object.values(hass.entities).find((entry) => entry.translation_key === "tire_pressure");
  const id = "sensor.arbitrarily_renamed_received";
  hass.entities = { ...hass.entities, [id]: {
    entity_id: id, platform: "havrv", device_id: pressure.device_id, translation_key: "tire_last_received",
  } };
  const model = buildModel(hass, rv);
  assert.equal(model.axles[0].left[0].lastReceived, id);
  assert.ok(model.watched.includes(id));
  assert.ok(!visibleModel(model, { show_tires: false }).watched.includes(id));
});

test("unmapped optional tire mirrors do not falsely report a temperature or battery outage", () => {
  const { hass, model } = completeFixture();
  const tire = model.axles[0].left[0];
  const temperature = hass.states[tire.temperature];
  temperature.state = "unavailable";
  temperature.attributes.source_entity_id = null;
  tire.battery = "sensor.unmapped_battery";
  hass.states[tire.battery] = { state: "unavailable", attributes: { source_entity_id: null } };
  for (const orientation of ["horizontal", "vertical"]) {
    let svg = renderVehicle(hass, model, orientation, 1);
    assert.doesNotMatch(svg, /Temp offline|Battery offline/);
    temperature.attributes.source_entity_id = "sensor.configured_but_not_yet_valid";
    svg = renderVehicle(hass, model, orientation, 1);
    assert.match(svg, /Temp offline \?/);
    temperature.attributes.source_entity_id = null;
  }
});

test("remapping immediately invalidates report ages and retained values from another source", () => {
  const { hass, model } = completeFixture();
  const tire = model.axles[0].left[0];
  const id = tire.pressure;
  const state = hass.states[id];
  state.last_reported = new Date(Date.now() - 7200000).toISOString();
  state.attributes.source_entity_id = "sensor.original_tpms";
  const card = new HavrvRvCard();
  card.setConfig({});
  card.hass = hass;
  assert.ok(card._readingHistory.has(id));
  state.state = "unavailable";
  Object.assign(state.attributes, {
    source_entity_id: "sensor.replacement_tpms", last_valid_source: "sensor.original_tpms",
    last_valid_value: 98, last_valid_unit: "psi", last_valid_time: state.last_reported,
  });
  card.hass = { ...hass };
  assert.equal(card._readingHistory.has(id), false);
  assert.equal(tireReading(hass, id, "pressure"), undefined);
  const row = [...card.shadowRoot.innerHTML.matchAll(/<g class="row"[\s\S]*?<\/g>/g)]
    .find(([row]) => row.includes(`data-entity="${id}"`))[0];
  assert.match(row, /Offline; last valid reading unknown/);
  assert.doesNotMatch(row, /Last 98|2h/);
});

test("card batches Recorder history, caches it and exposes failures without losing readings", async () => {
  const { hass } = completeFixture();
  const requests = [];
  const now = Date.now();
  hass.callWS = async (message) => {
    requests.push(message);
    return Object.fromEntries(message.entity_ids.map((id) => [id, [
      { s: "100", lu: (now - 3000000) / 1000, a: { unit_of_measurement: "psi" } },
      { s: "102", lu: (now - 600000) / 1000, a: { unit_of_measurement: "psi" } },
    ]]));
  };
  const card = new HavrvRvCard();
  card.isConnected = true;
  card.setConfig({});
  card.hass = hass;
  await card._historyRequest;
  assert.equal(requests.length, 1);
  assert.equal(requests[0].type, "history/history_during_period");
  assert.equal(Date.parse(requests[0].end_time) - Date.parse(requests[0].start_time), 3600000);
  assert.equal(requests[0].include_start_time_state, false);
  assert.equal(requests[0].minimal_response, false);
  assert.equal(requests[0].no_attributes, false);
  assert.equal(requests[0].entity_ids.length, 16);
  assert.match(card.shadowRoot.innerHTML, /class="pressure-sparkline"/);
  card.hass = { ...hass };
  assert.equal(requests.length, 1);
  hass.callWS = async () => { throw { code: "history_disabled", message: "Recorder disabled" }; };
  card._historyUpdated = 0;
  card.hass = hass;
  await card._historyRequest;
  assert.match(card.shadowRoot.innerHTML, /Pressure history unavailable: Recorder disabled/);
  assert.match(card.shadowRoot.innerHTML, />102<\/tspan>/);
  card.setConfig({ show_tires: false });
  assert.equal(card._pressureHistory.size, 0);
  assert.doesNotMatch(card.shadowRoot.innerHTML, /class="pressure-sparkline|Pressure history unavailable:/);
  card.disconnectedCallback();
});

test("late history cannot repopulate removed mappings or disconnected cards", async () => {
  const { hass } = completeFixture();
  let resolve;
  hass.callWS = () => new Promise((done) => { resolve = done; });
  const card = new HavrvRvCard();
  card.isConnected = true;
  card.setConfig({});
  card.hass = hass;
  const pending = card._historyRequest;
  card.setConfig({ show_tires: false });
  resolve({});
  await pending;
  assert.equal(card._pressureHistory.size, 0);
  assert.doesNotMatch(card.shadowRoot.innerHTML, /class="pressure-sparkline/);
  card.setConfig({});
  const pendingDisconnect = card._historyRequest;
  card.disconnectedCallback();
  const revision = card._historyRevision;
  resolve({});
  await pendingDisconnect;
  assert.equal(card._historyRevision, revision);
});

test("source remapping rejects late requests and Recorder samples from the previous source", async () => {
  const { hass, model } = completeFixture();
  const id = model.axles[0].left[0].pressure;
  const now = Date.now();
  hass.states[id].attributes.last_valid_source = "sensor.original_tpms";
  hass.states[id].attributes.last_valid_time = new Date(now - 60000).toISOString();
  const pending = [];
  hass.callWS = () => new Promise((resolve) => pending.push(resolve));
  const card = new HavrvRvCard();
  card.isConnected = true;
  card.setConfig({});
  card.hass = hass;
  const first = card._historyRequest;
  hass.states[id].attributes.last_valid_source = "sensor.replacement_tpms";
  card.hass = { ...hass };
  const second = card._historyRequest;
  const sample = (value, minutes, source) => ({
    s: String(value), lu: (now - minutes * 60000) / 1000,
    a: { unit_of_measurement: "psi", last_valid_source: source },
  });
  pending[0]({ [id]: [sample(999, 30, "sensor.original_tpms")] });
  await first;
  assert.ok(card._pressureHistory.get(id).every((point) => point.value !== 999));
  pending[1]({ [id]: [
    sample(999, 30, "sensor.original_tpms"), sample(100, 20, "sensor.replacement_tpms"),
    sample(101, 10, "sensor.replacement_tpms"),
  ] });
  await second;
  assert.deepEqual(card._pressureHistory.get(id).map((point) => point.value), [100, 101, 102]);
  assert.match(card.shadowRoot.innerHTML, /class="pressure-sparkline"/);
  card.disconnectedCallback();
});

test("each tire row, tank and electrical box reports missing-channel age and recovers", () => {
  const { hass, model } = completeFixture();
  const now = Date.now();
  const before = new Date(now - 2 * 3600000).toISOString();
  const ids = [
    ...model.axles.flatMap((axle) => [...axle.left, ...axle.right].map((tire) => tire.pressure)),
    ...model.tanks.map((tank) => tank.percentage),
    ...model.powerSources.filter((source) => source.key !== "generator").map((source) => source.voltage),
  ];
  for (const id of ids) hass.states[id].last_updated = before;
  rememberReadings(hass, ids, new Map(), now);
  for (const id of ids) hass.states[id].state = "unavailable";
  for (const orientation of ["horizontal", "vertical"]) {
    const svg = renderVehicle(hass, model, orientation, 1);
    assert.equal((svg.match(/class="data-age" role="img" aria-label="Last data 2h ago"/g) || []).length, 8);
    assert.equal((svg.match(/class="tire-age"/g) || []).length, 16);
    assert.equal((svg.match(/> · Offline 2h<\/text>/g) || []).length, 16);
    const labels = [...svg.matchAll(/<g class="data-age"[\s\S]*?<\/g>/g)].map(([label]) => label);
    assert.equal(labels.length, 8);
    for (const label of labels) {
      assert.match(label, /<title>Last data 2h ago<\/title>/);
      assert.match(label, /class="age-clock"/);
      assert.match(label, /<text x="11" y="0">2h<\/text>/);
      assert.doesNotMatch(label, /<tspan|<text[^>]*>Last data/);
    }
    assert.doesNotMatch(svg, /Last data unknown/);
    for (const chip of layoutPowerBoxes(hass, model, orientation).obstacles) {
      assert.equal(chip.height, Math.max(52, 24 + chip.axle[chip.side].length * 20));
      assert.equal(chip.rowHeight, 20);
    }
    for (const [row] of svg.matchAll(/<g class="row"[\s\S]*?<\/g>/g)) {
      const baseline = /class="row-pressure"[^>]+ y="([^"]+)"/.exec(row)?.[1];
      const ageBaseline = /class="tire-age"[^>]+ y="([^"]+)"/.exec(row)?.[1];
      assert.equal(ageBaseline, baseline);
    }
    for (const [tank] of svg.matchAll(/<g class="tank-label [\s\S]*?<\/g>/g)) {
      const baseline = /class="tank-pct[^"]*"[^>]+ y="([^"]+)"/.exec(tank)?.[1];
      const ageBaseline = /class="data-age"[^>]+transform="translate\([^ ]+ ([^)]+)\)"/.exec(tank)?.[1];
      assert.equal(ageBaseline, baseline);
      if (orientation === "vertical") {
        const percentX = Number(/class="tank-pct[^"]*" x="([^"]+)"/.exec(tank)[1]);
        const ageX = Number(/class="data-age"[^>]+transform="translate\(([^ ]+)/.exec(tank)[1]);
        assert.equal(ageX - percentX, 15);
      }
    }
  }
  for (const id of ids) hass.states[id].state = "1";
  assert.doesNotMatch(renderVehicle(hass, model, "vertical", 1), /class="data-age"/);
});

test("all electrical boxes align labels, values and missing-data ages on compact rows", () => {
  const { hass, rv } = shoreFixture();
  const model = buildModel(hass, rv);
  for (const source of model.powerSources) {
    for (const metric of ["voltage", "current", "frequency", "power", "line_2_voltage",
      "line_2_current", "line_2_frequency", "line_2_power", "energy", "charging"]) {
      if (source[metric]) hass.states[source[metric]].state = "unavailable";
    }
  }
  for (const orientation of ["horizontal", "vertical"]) {
    const layout = layoutPowerBoxes(hass, model, orientation);
    for (const box of layout.boxes) {
      const svg = renderPowerBoxes(hass, { ...layout, boxes: [box], icons: [] });
      assert.equal(box.height, Math.max(52,
        24 + box.headerHeight + box.rows.length * 20 + (box.sharedMetrics.length ? 20 : 0)));
      const labelYs = [...svg.matchAll(/class="small power-label"[^>]+ y="([^"]+)"/g)]
        .map((match) => Number(match[1]));
      assert.equal(labelYs.length, box.rows.length);
      for (const metric of box.rows.flat().filter(Boolean)) {
        const group = svg.split(`<g data-entity="${box.source[metric]}"`)[1].split("</g>")[0];
        const value = /class="power-value" x="([^"]+)" y="([^"]+)"/.exec(group);
        assert.ok(labelYs.includes(Number(value[2])));
        const age = /class="data-age"[^>]+transform="translate\(([^ ]+) ([^)]+)\)"/.exec(group);
        if (metric === "enabled") {
          assert.equal(age, null);
        } else {
          assert.ok(age, `${box.source.key} ${metric} must show an inline missing age`);
          assert.equal(age[2], value[2]);
          assert.ok(Number(age[1]) > Number(value[1]) + 35);
          assert.ok(Number(age[1]) + 17 < Number(value[1]) + box.columnWidth);
        }
      }
      assert.match(svg, />Voltage<\/text>/);
      assert.match(svg, />Amps<\/text>/);
    }
  }
});

test("card ages refresh without state changes, release timers and discard removed mappings", () => {
  const { hass } = fixture();
  const card = new HavrvRvCard();
  const id = "sensor.renamed_house_bank_1_voltage";
  hass.states[id].last_updated = new Date(Date.now() - 3600000).toISOString();
  card.setConfig({});
  card.hass = hass;
  hass.states[id].state = "unavailable";
  card.hass = { ...hass };
  assert.match(card.shadowRoot.innerHTML, /Last data 1h ago/);
  const set = globalThis.setInterval;
  const clear = globalThis.clearInterval;
  const clock = Date.now;
  let tick;
  let cleared;
  const timer = { unref() {} };
  try {
    globalThis.setInterval = (callback, delay) => {
      assert.equal(delay, 30000);
      tick = callback;
      return timer;
    };
    globalThis.clearInterval = (value) => { cleared = value; };
    card.connectedCallback();
    assert.equal(typeof tick, "function");
    Date.now = () => clock() + 2 * 3600000;
    tick();
    assert.match(card.shadowRoot.innerHTML, /Last data 3h ago/);
    card.disconnectedCallback();
    assert.equal(cleared, timer);
    assert.equal(card._ageTimer, undefined);
  } finally {
    globalThis.setInterval = set;
    globalThis.clearInterval = clear;
    Date.now = clock;
  }
  card.setConfig({ show_power: false });
  assert.equal(card._readingHistory.has(id), false);
  card.setConfig({ show_power: true });
  assert.match(card.shadowRoot.innerHTML, /Last data unknown/);
  assert.match(card.shadowRoot.innerHTML, /<title>Last data unknown<\/title>[\s\S]*?<text x="11" y="0">\?<\/text>/);
});
