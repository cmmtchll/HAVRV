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

test("very many colocated banks keep distinct graphics on the coach", () => {
  const { hass, rv } = fixture();
  const model = buildModel(hass, rv);
  const bank = model.powerSources.find((source) => source.key === "house_bank_1");
  model.powerSources = Array.from({ length: 50 }, (_, index) => ({
    ...bank, key: `house_bank_${index + 1}`,
  }));
  const layout = layoutPowerBoxes(hass, model, "vertical");
  assert.equal(layout.boxes.length, 50);
  assert.equal(layout.icons.length, 50);
  assert.ok(layout.icons[0].width < 44);
  for (const icon of layout.icons) {
    assert.ok(icon.x >= 158 && icon.x + icon.width <= 338);
    assert.ok(icon.y >= 24 && icon.y + icon.height <= 884);
    for (const other of layout.icons) {
      if (other === icon) continue;
      assert.ok(icon.x + icon.width <= other.x || other.x + other.width <= icon.x
        || icon.y + icon.height <= other.y || other.y + other.height <= icon.y);
    }
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
      ? { x: 316, y: 148, width: 320, height: 80 }
      : { x: 208, y: 278, width: 80, height: 320 };
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
