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
  buildModel, powerState, layoutPowerBoxes, renderPowerBoxes, renderVehicle, summarize,
  rvView, HavrvDashboardStrategy, HavrvViewStrategy, HavrvRvCard,
  DISPLAY_CLASSES, dashboardOptions, visibleModel,
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
    assert.equal(box.height, 204);
    const svg = renderPowerBoxes(hass, layout);
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
  assert.match(renderPowerBoxes(hass, layout), /data-entity="sensor.renamed_shore_power_energy" tabindex="0" role="button"/);
  assert.doesNotMatch(renderPowerBoxes(hass, layout), /Line 1|Line 2/);
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
          - (vertical ? 884 - u : 30 + u)) <= 108);
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
    "show_header", "show_legend", "show_tires", "show_tanks", "show_power", "show_coach", "show_systems",
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
    assert.ok(obstacles.every((chip) => chip.width === 156 && chip.height >= 52));
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
