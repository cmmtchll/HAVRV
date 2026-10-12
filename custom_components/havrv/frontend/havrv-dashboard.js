/*
 * HAVRV dashboard: an RV overview card plus dashboard and view strategies.
 *
 * Served by the HAVRV integration. The layout is discovered from the Home
 * Assistant device and entity registries: HAVRV device identifiers encode each
 * configured tire position and tank, and entity translation keys identify the
 * reading each entity represents. No RV entity IDs are assumed.
 */

const DOMAIN = "havrv";
const CARD_TYPE = "havrv-rv-card";
const STRATEGY_TYPE = "havrv";
const DOCS_URL =
  "https://github.com/cmmtchll/HAVRV/blob/main/docs/DASHBOARD.md";

const TIRE_KEY = /^(front|rear_axle_(\d+)|tag_axle)_(left|right)(?:_(inner|outer))?$/;
const TIRE_ROLES = {
  tire_pressure: "pressure",
  tire_temperature: "temperature",
  tire_battery: "battery",
  tire_pressure_problem: "pressureProblem",
  tire_temperature_problem: "temperatureProblem",
  tire_battery_problem: "batteryProblem",
  tire_pressure_sudden_drop: "suddenDrop",
  tire_pressure_slow_loss: "slowLoss",
};
const TANK_ROLES = {
  tank_percentage: "percentage",
  tank_status: "status",
  tank_level: "level",
  tank_capacity: "capacity",
  tank_last_filled: "history",
  tank_last_emptied: "history",
};
const TANK_ORDER = ["fresh_water", "gray_water", "black_water"];
const MODE_ICONS = {
  storage: "mdi:garage-variant",
  driving: "mdi:steering",
  campsite_full_service: "mdi:power-plug",
  campsite_minimal: "mdi:pine-tree",
  maintenance: "mdi:wrench",
};
const LAYOUTS = ["auto", "horizontal", "vertical"];
const VERTICAL_BREAKPOINT = 560;
const UNAVAILABLE = new Set(["unavailable", "unknown"]);

const STR = {
  allClear: "All clear",
  alerts: (n) => `${n} ${n === 1 ? "alert" : "alerts"}`,
  watch: (n) => `${n} to watch`,
  offline: (n) => `${n} no data`,
  noData: "No data",
  suddenDrop: "Sudden pressure drop",
  slowLoss: "Slow pressure loss",
  pressureLimit: "Pressure outside limits",
  temperatureLimit: "Temperature above limit",
  lowBattery: "Sensor battery low",
  noProfile:
    "No HAVRV RV profile was found. Add an RV profile in Settings → Devices & services.",
  noTires: "Set the axle layout in the RV profile to show tires.",
  legendOk: "OK",
  legendWatch: "Watch",
  legendAlert: "Alert",
  legendOffline: "No data",
  outer: "O",
  inner: "I",
  coach: "Coach",
  tanks: "Tanks",
  tireAnalysis: "Tire analysis",
  tankLabels: { fresh_water: "Fresh", gray_water: "Gray", black_water: "Black" },
  form: {
    device_id: "RV profile",
    layout: "Layout",
    show_header: "Show header",
    auto: "Automatic",
    horizontal: "Horizontal",
    vertical: "Vertical",
  },
};

// ---------------------------------------------------------------------------
// Registry discovery.
// ---------------------------------------------------------------------------

const havrvIdentifier = (device) =>
  (device?.identifiers || []).find((identifier) => identifier[0] === DOMAIN)?.[1];

const deviceName = (device) => device?.name_by_user || device?.name || "";

let entityIndex = { entities: undefined, byDevice: new Map() };

/** Group HAVRV entity registry display entries by device. */
function entitiesByDevice(hass) {
  if (entityIndex.entities !== hass.entities) {
    const byDevice = new Map();
    for (const entry of Object.values(hass.entities || {})) {
      if (entry.platform !== DOMAIN || !entry.device_id) continue;
      if (!byDevice.has(entry.device_id)) byDevice.set(entry.device_id, []);
      byDevice.get(entry.device_id).push(entry);
    }
    for (const entries of byDevice.values()) {
      entries.sort((a, b) => a.entity_id.localeCompare(b.entity_id));
    }
    entityIndex = { entities: hass.entities, byDevice };
  }
  return entityIndex.byDevice;
}

/** Return HAVRV RV profile devices; their identifier is the config entry ID. */
export function findRvDevices(hass) {
  return Object.values(hass?.devices || {})
    .filter((device) => {
      const identifier = havrvIdentifier(device);
      return identifier && (device.config_entries || []).includes(identifier);
    })
    .sort((a, b) => deviceName(a).localeCompare(deviceName(b)));
}

/** Resolve an RV device from any HAVRV device ID, or the first RV profile. */
export function resolveRvDevice(hass, deviceId) {
  const rvs = findRvDevices(hass);
  if (!deviceId) return rvs[0];
  const identifier = havrvIdentifier(hass.devices?.[deviceId]);
  if (!identifier) return undefined;
  return rvs.find((rv) => {
    const entryId = havrvIdentifier(rv);
    return identifier === entryId || identifier.startsWith(`${entryId}_`);
  });
}

function entityRoles(entries, roleMap) {
  const roles = {};
  for (const entry of entries || []) {
    const role = roleMap[entry.translation_key];
    if (role && !roles[role]) roles[role] = entry.entity_id;
  }
  return roles;
}

const AXLE_ORDER = { front: 0, drive: 1, tag: 2 };
const WHEEL_ORDER = { outer: 0, single: 0, inner: 1 };

/** Build the RV layout from the device and entity registries. */
export function buildModel(hass, rv) {
  const entryId = havrvIdentifier(rv);
  const byDevice = entitiesByDevice(hass);
  const visible = (deviceId) =>
    (byDevice.get(deviceId) || [])
      .filter((entry) => !entry.hidden)
      .map((entry) => entry.entity_id);
  const model = {
    rv,
    name: deviceName(rv) || "RV",
    profile: entityRoles(byDevice.get(rv.id), {
      coach_year: "year",
      manufacturer: "manufacturer",
      make: "make",
      model: "model",
    }),
    profileEntities: visible(rv.id),
    axles: [],
    tanks: [],
    operationMode: undefined,
    monitorEntities: [],
    systems: [],
  };
  const axles = new Map();
  for (const device of Object.values(hass.devices || {})) {
    const identifier = havrvIdentifier(device);
    if (!identifier || !identifier.startsWith(`${entryId}_`)) continue;
    const part = identifier.slice(entryId.length + 1);
    const entries = byDevice.get(device.id);
    if (part === "tire_monitor") {
      model.monitorEntities = visible(device.id);
    } else if (part.startsWith("tire_")) {
      const match = TIRE_KEY.exec(part.slice("tire_".length));
      if (!match) continue;
      const key = match[1];
      if (!axles.has(key)) {
        axles.set(key, {
          key,
          kind: key === "front" ? "front" : key === "tag_axle" ? "tag" : "drive",
          index: match[2] ? Number(match[2]) : 0,
          dual: false,
          left: [],
          right: [],
        });
      }
      const axle = axles.get(key);
      const wheel = match[4] || "single";
      axle.dual ||= wheel !== "single";
      axle[match[3]].push({
        wheel,
        name: deviceName(device),
        ...entityRoles(entries, TIRE_ROLES),
      });
    } else if (part.startsWith("tank_")) {
      const type = part.slice("tank_".length);
      model.tanks.push({
        type,
        name: device.name_by_user || STR.tankLabels[type] || deviceName(device),
        ...entityRoles(entries, TANK_ROLES),
      });
    } else if (part === "operations") {
      model.operationMode = entityRoles(entries, { operation_mode: "mode" }).mode;
    } else {
      const entities = visible(device.id);
      if (entities.length) {
        model.systems.push({ key: part, name: deviceName(device), entities });
      }
    }
  }
  model.axles = [...axles.values()].sort(
    (a, b) => AXLE_ORDER[a.kind] - AXLE_ORDER[b.kind] || a.index - b.index,
  );
  for (const axle of model.axles) {
    for (const side of ["left", "right"]) {
      axle[side].sort((a, b) => WHEEL_ORDER[a.wheel] - WHEEL_ORDER[b.wheel]);
    }
  }
  const tankRank = (type) => {
    const rank = TANK_ORDER.indexOf(type);
    return rank === -1 ? TANK_ORDER.length : rank;
  };
  model.tanks.sort((a, b) => tankRank(a.type) - tankRank(b.type));
  model.systems.sort((a, b) => a.name.localeCompare(b.name));
  model.watched = [
    ...Object.values(model.profile),
    model.operationMode,
    ...model.axles.flatMap((axle) =>
      [...axle.left, ...axle.right].flatMap((tire) =>
        Object.values(TIRE_ROLES).map((role) => tire[role]),
      ),
    ),
    ...model.tanks.flatMap((tank) => [tank.percentage, tank.status, tank.level]),
  ].filter(Boolean);
  return model;
}

// ---------------------------------------------------------------------------
// Reading presentation. Status comes only from HAVRV's own advisory entities.
// ---------------------------------------------------------------------------

const stateOf = (hass, entityId) => (entityId ? hass.states[entityId] : undefined);
const isOn = (hass, entityId) => stateOf(hass, entityId)?.state === "on";

function formatNumber(hass, value, precision) {
  try {
    return new Intl.NumberFormat(hass.locale?.language || undefined, {
      minimumFractionDigits: precision,
      maximumFractionDigits: precision,
    }).format(value);
  } catch (_err) {
    return value.toFixed(precision);
  }
}

function numeric(hass, entityId, defaultPrecision = 0) {
  const state = stateOf(hass, entityId);
  if (!state || UNAVAILABLE.has(state.state)) return undefined;
  const value = Number(state.state);
  if (!Number.isFinite(value)) return undefined;
  const precision = hass.entities?.[entityId]?.display_precision ?? defaultPrecision;
  return {
    value,
    text: formatNumber(hass, value, precision),
    unit: state.attributes.unit_of_measurement || "",
  };
}

function formatState(hass, entityId) {
  const state = stateOf(hass, entityId);
  if (!state || UNAVAILABLE.has(state.state)) return undefined;
  return typeof hass.formatEntityState === "function"
    ? hass.formatEntityState(state)
    : state.state;
}

const LEVEL_RANK = { ok: 0, offline: 1, watch: 2, alert: 3 };
const worst = (levels) =>
  levels.reduce((a, b) => (LEVEL_RANK[b] > LEVEL_RANK[a] ? b : a), "ok");

/** Summarize one tire; only a missing pressure reading counts as no data. */
export function tireState(hass, tire) {
  const pressure = numeric(hass, tire.pressure);
  const temperature = numeric(hass, tire.temperature);
  const reasons = [];
  let level = pressure ? "ok" : "offline";
  if (!pressure) reasons.push(STR.noData);
  const flag = (entityId, flagLevel, reason) => {
    if (!isOn(hass, entityId)) return;
    reasons.push(reason);
    if (LEVEL_RANK[flagLevel] > LEVEL_RANK[level]) level = flagLevel;
  };
  flag(tire.suddenDrop, "alert", STR.suddenDrop);
  flag(tire.pressureProblem, "alert", STR.pressureLimit);
  flag(tire.temperatureProblem, "alert", STR.temperatureLimit);
  flag(tire.slowLoss, "watch", STR.slowLoss);
  flag(tire.batteryProblem, "watch", STR.lowBattery);
  return {
    level,
    pressure,
    temperature,
    reasons,
    dropping: isOn(hass, tire.suddenDrop) || isOn(hass, tire.slowLoss),
    lowBattery: isOn(hass, tire.batteryProblem),
    hot: isOn(hass, tire.temperatureProblem),
  };
}

/** Summarize one tank from HAVRV's percentage, status, and level entities. */
export function tankState(hass, tank) {
  const percent = numeric(hass, tank.percentage);
  const status = stateOf(hass, tank.status)?.state;
  const level = numeric(hass, tank.level);
  let state = percent ? "ok" : "offline";
  if (percent && status === "warning") state = "watch";
  if (percent && status === "problem") state = "alert";
  return {
    level: state,
    percent,
    volume: level && level.unit !== "%" ? level : undefined,
    statusText: percent ? formatState(hass, tank.status) : STR.noData,
  };
}

/** Count tires and tanks needing attention. */
export function summarize(hass, model) {
  const levels = [
    ...model.axles.flatMap((axle) =>
      [...axle.left, ...axle.right].map((tire) => tireState(hass, tire).level),
    ),
    ...model.tanks.map((tank) => tankState(hass, tank).level),
  ];
  const count = (level) => levels.filter((value) => value === level).length;
  return { alert: count("alert"), watch: count("watch"), offline: count("offline") };
}

const escapeHtml = (value) =>
  String(value ?? "").replace(
    /[&<>"']/g,
    (char) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[char],
  );

// ---------------------------------------------------------------------------
// Plan-view drawing. Vehicle coordinates: u runs 0..L from rear to front and
// v runs across the coach (negative is the driver's left). Shapes are drawn in
// vehicle coordinates inside a transformed group; text is placed in screen
// coordinates so it is never rotated.
// ---------------------------------------------------------------------------

const L = 860;
const BODY = 90;
const TIRE_OUTER = 102;
const TIRE_DEPTH = 22;
const DUAL_OFFSET = 25;
const TIRE_LENGTH = 60;
const CHIP_GAP = 14;
const FRONT_U = 712;
const REAR_U = 150;
const AXLE_SPACING = 110;
const TANK_BAND = 68;

const ORIENTATIONS = {
  horizontal: {
    width: 920,
    height: 376,
    transform: "matrix(1 0 0 1 30 188)",
    map: (u, v) => [30 + u, 188 + v],
    chipWidth: 104,
  },
  vertical: {
    width: 496,
    height: 908,
    transform: `matrix(0 -1 1 0 248 ${24 + L})`,
    map: (u, v) => [248 + v, 24 + L - u],
    chipWidth: 124,
  },
};

const r1 = (value) => Math.round(value * 10) / 10;

function axleLabel(axle, driveCount) {
  if (axle.kind === "front") return "Front";
  if (axle.kind === "tag") return "Tag";
  return driveCount > 1 ? `Rear ${axle.index}` : "Rear";
}

/** Assign plan positions; rear axles are packed toward the back of the coach. */
function placeAxles(model) {
  const axles = model.axles.length
    ? model.axles.map((axle) => ({ ...axle }))
    : [
        { key: "front", kind: "front", ghost: true, left: [{}], right: [{}] },
        { key: "rear", kind: "drive", ghost: true, left: [{}], right: [{}] },
      ];
  const rear = axles.filter((axle) => axle.kind !== "front");
  rear.forEach((axle, i) => {
    axle.u = rear.length === 1 ? 175 : REAR_U + (rear.length - 1 - i) * AXLE_SPACING;
  });
  for (const axle of axles) if (axle.kind === "front") axle.u = FRONT_U;
  const driveCount = axles.filter((axle) => axle.kind === "drive").length;
  for (const axle of axles) axle.label = axleLabel(axle, driveCount);
  return { axles, rearFront: rear.length ? Math.max(...rear.map((a) => a.u)) : REAR_U };
}

function tankSpan(rearFront) {
  let start = rearFront + 75;
  let end = FRONT_U - 70;
  if (end - start > 320) {
    const mid = (start + end) / 2;
    start = mid - 160;
    end = mid + 160;
  }
  if (end - start < 100) start = end - 100;
  return [start, end];
}

function bodyShapes(uid) {
  const frame = [-44, 44]
    .map(
      (v) =>
        `<line class="frame" x1="40" y1="${v}" x2="800" y2="${v}"></line>`,
    )
    .join("");
  const ribs = [];
  for (let u = 60; u < 780; u += 60) {
    ribs.push(`<line class="rib" x1="${u}" y1="-84" x2="${u}" y2="84"></line>`);
  }
  return `
    <path class="body" fill="url(#hv-body-${uid})" d="M10,-${BODY} L780,-${BODY} Q856,-${BODY} 856,-36 L856,36 Q856,${BODY} 780,${BODY} L10,${BODY} Q0,${BODY} 0,80 L0,-80 Q0,-${BODY} 10,-${BODY} Z"></path>
    ${ribs.join("")}
    ${frame}
    <path class="glass" fill="url(#hv-glass-${uid})" d="M790,-76 Q838,-72 844,0 Q838,72 790,76 Q806,0 790,-76 Z"></path>
    <rect class="mirror" x="782" y="-104" width="10" height="16" rx="3"></rect>
    <rect class="mirror" x="782" y="88" width="10" height="16" rx="3"></rect>
    <rect class="roof-unit" x="560" y="-22" width="54" height="44" rx="8"></rect>
    <rect class="roof-unit" x="250" y="-22" width="54" height="44" rx="8"></rect>
    <rect class="roof-unit vent" x="430" y="-14" width="28" height="28" rx="5"></rect>`;
}

function tireRects(axle, states) {
  const shapes = [`<line class="axle" x1="${axle.u}" y1="-80" x2="${axle.u}" y2="80"></line>`];
  for (const [side, sign] of [
    ["left", -1],
    ["right", 1],
  ]) {
    axle[side].forEach((tire, i) => {
      const offset = tire.wheel === "inner" || i > 0 ? DUAL_OFFSET : 0;
      const outer = TIRE_OUTER - offset;
      const y = sign < 0 ? -outer : outer - TIRE_DEPTH;
      const state = states.get(tire);
      const level = axle.ghost ? "ghost" : state.level;
      const entity = tire.pressure || tire.temperature || tire.battery || "";
      const title = axle.ghost
        ? ""
        : `<title>${escapeHtml([tire.name, ...state.reasons].join(" · "))}</title>`;
      shapes.push(`
        <g class="tire ${level}" ${entity ? `data-entity="${entity}"` : ""}>
          ${title}
          <rect x="${axle.u - TIRE_LENGTH / 2}" y="${y}" width="${TIRE_LENGTH}" height="${TIRE_DEPTH}" rx="6"></rect>
          <line class="tread" x1="${axle.u - 18}" y1="${y + 4}" x2="${axle.u - 18}" y2="${y + TIRE_DEPTH - 4}"></line>
          <line class="tread" x1="${axle.u}" y1="${y + 4}" x2="${axle.u}" y2="${y + TIRE_DEPTH - 4}"></line>
          <line class="tread" x1="${axle.u + 18}" y1="${y + 4}" x2="${axle.u + 18}" y2="${y + TIRE_DEPTH - 4}"></line>
        </g>`);
    });
  }
  return shapes.join("");
}

function temperatureText(temperature, compact) {
  if (!temperature) return "";
  const unit = temperature.unit || "";
  if (compact && unit.startsWith("°")) return `${temperature.text}°`;
  return `${temperature.text}${unit ? ` ${unit}` : ""}`;
}

function flagText(state) {
  return [state.dropping && "▼", state.hot && "HOT", state.lowBattery && "BAT"]
    .filter(Boolean)
    .join(" ");
}

function tireChip(axle, side, sign, states, geometry) {
  const tires = axle[side];
  const dual = tires.length > 1;
  const height = dual ? 64 : 52;
  const width = geometry.chipWidth;
  const depth = geometry === ORIENTATIONS.horizontal ? height : width;
  const [cx, cy] = geometry.map(axle.u, sign * (TIRE_OUTER + CHIP_GAP + depth / 2));
  const x = r1(cx - width / 2);
  const y = r1(cy - height / 2);
  const tireStates = tires.map((tire) => states.get(tire));
  const level = worst(tireStates.map((state) => state.level));
  const label = `${axle.label} ${sign < 0 ? "L" : "R"}`;
  const parts = [
    `<rect class="chip-bg" x="${x}" y="${y}" width="${width}" height="${height}" rx="10"></rect>`,
    `<text class="chip-label" x="${x + 9}" y="${y + 13}">${escapeHtml(label)}</text>`,
    `<circle class="dot ${level}" cx="${x + width - 11}" cy="${y + 10}" r="4"></circle>`,
  ];
  if (!dual) {
    const tire = tires[0];
    const state = tireStates[0];
    const entity = tire.pressure || tire.temperature || "";
    const pressure = state.pressure
      ? `<tspan class="big">${escapeHtml(state.pressure.text)}</tspan><tspan class="unit" dx="3">${escapeHtml(state.pressure.unit)}</tspan>`
      : `<tspan class="big muted">—</tspan>`;
    const flags = flagText(state);
    parts.push(
      `<text x="${x + 9}" y="${y + 34}">${pressure}</text>`,
      `<text class="small" x="${x + 9}" y="${y + 46}">${escapeHtml(
        state.pressure ? temperatureText(state.temperature, false) : STR.noData,
      )}</text>`,
      flags
        ? `<text class="flag ${level}" x="${x + width - 9}" y="${y + 46}" text-anchor="end">${flags}</text>`
        : "",
    );
    return `<g class="chip ${level}" ${entity ? `data-entity="${entity}"` : ""} tabindex="0" role="button" aria-label="${escapeHtml(
      `${tire.name}: ${state.reasons.join(", ") || STR.allClear}`,
    )}">${parts.join("")}</g>`;
  }
  // Stack dual rows in the same order as the wheels they describe: a chip
  // below the coach lists the inner wheel first, nearest the body.
  const rowOrder = geometry === ORIENTATIONS.horizontal && sign > 0
    ? tires.map((_, i) => tires.length - 1 - i)
    : tires.map((_, i) => i);
  const rows = rowOrder.map((i, rowIndex) => {
    const tire = tires[i];
    const state = tireStates[i];
    const rowY = y + 32 + rowIndex * 20;
    const entity = tire.pressure || tire.temperature || "";
    const pressure = state.pressure
      ? `<tspan class="mid">${escapeHtml(state.pressure.text)}</tspan><tspan class="unit" dx="2">${escapeHtml(state.pressure.unit)}</tspan>`
      : `<tspan class="mid muted">—</tspan>`;
    // Rows are narrow: show the pressure trend as a glyph, color a hot
    // temperature, and move the battery flag to the chip header.
    const temperature = temperatureText(state.temperature, true);
    const right = state.pressure
      ? [
          state.dropping ? `<tspan class="trend ${state.level}">▼</tspan>` : "",
          temperature ? `<tspan class="${state.hot ? "hot" : ""}">${escapeHtml(temperature)}</tspan>` : "",
        ].filter(Boolean).join(" ")
      : "";
    return `<g class="row" ${entity ? `data-entity="${entity}"` : ""} tabindex="0" role="button" aria-label="${escapeHtml(
      `${tire.name}: ${state.reasons.join(", ") || STR.allClear}`,
    )}">
      <rect class="hit" x="${x}" y="${rowY - 15}" width="${width}" height="20"></rect>
      <text class="wheel ${state.level}" x="${x + 9}" y="${rowY}">${tire.wheel === "inner" ? STR.inner : STR.outer}</text>
      <text class="row-pressure" x="${x + 22}" y="${rowY}">${pressure}</text>
      <text class="small row-right" x="${x + width - 9}" y="${rowY}" text-anchor="end">${right}</text>
    </g>`;
  });
  if (tireStates.some((state) => state.lowBattery)) {
    parts.push(
      `<text class="flag watch" x="${x + width - 20}" y="${y + 13}" text-anchor="end">BAT</text>`,
    );
  }
  return `<g class="chip ${level}">${parts.join("")}${rows.join("")}</g>`;
}

function ghostChip(axle, sign, geometry) {
  const width = geometry.chipWidth;
  const depth = geometry === ORIENTATIONS.horizontal ? 52 : width;
  const [cx, cy] = geometry.map(axle.u, sign * (TIRE_OUTER + CHIP_GAP + depth / 2));
  return `<rect class="chip-bg ghost" x="${r1(cx - width / 2)}" y="${r1(cy - 26)}" width="${width}" height="52" rx="10"></rect>`;
}

function tankShapes(model, span, states) {
  const [start, end] = span;
  const count = model.tanks.length;
  const gap = 8;
  const lane = (TANK_BAND * 2 - gap * (count - 1)) / count;
  return model.tanks.map((tank, i) => {
    const v0 = -TANK_BAND + i * (lane + gap);
    const state = states.get(tank);
    const fill = state.percent
      ? ((end - start) * Math.max(0, Math.min(100, state.percent.value))) / 100
      : 0;
    return `
      <g class="tank ${tank.type} ${state.level}">
        <rect class="tank-shell" x="${start}" y="${r1(v0)}" width="${end - start}" height="${r1(lane)}" rx="8"></rect>
        <rect class="tank-fill" x="${start}" y="${r1(v0)}" width="${r1(fill)}" height="${r1(lane)}" rx="8"></rect>
        <rect class="tank-frame" x="${start}" y="${r1(v0)}" width="${end - start}" height="${r1(lane)}" rx="8"></rect>
      </g>`;
  });
}

function truncate(text, length) {
  return text.length > length ? `${text.slice(0, length - 1)}…` : text;
}

function tankLabels(model, span, states, geometry, vertical) {
  const [start, end] = span;
  const count = model.tanks.length;
  const gap = 8;
  const lane = (TANK_BAND * 2 - gap * (count - 1)) / count;
  return model.tanks.map((tank, i) => {
    const vc = -TANK_BAND + i * (lane + gap) + lane / 2;
    const state = states.get(tank);
    const entity = tank.percentage || tank.level || "";
    const percent = state.percent ? `${state.percent.text}%` : vertical ? "—" : STR.noData;
    const volume = state.volume ? `${state.volume.text} ${state.volume.unit}` : "";
    const title = `<title>${escapeHtml(
      [tank.name, state.statusText].filter(Boolean).join(" · "),
    )}</title>`;
    let body;
    if (vertical) {
      const [x, yTop] = geometry.map(end - 18, vc);
      const [, yName] = geometry.map(start + 10, vc);
      body = `
        <text class="tank-pct" x="${x}" y="${yTop}" text-anchor="middle">${escapeHtml(percent)}</text>
        ${volume ? `<text class="tiny" x="${x}" y="${yTop + 13}" text-anchor="middle">${escapeHtml(volume)}</text>` : ""}
        <text class="tank-name" x="${x}" y="${yName}" text-anchor="middle">${escapeHtml(truncate(tank.name, 7))}</text>`;
    } else {
      const [xs, y] = geometry.map(start + 12, vc);
      const [xe] = geometry.map(end - 12, vc);
      const fontSize = lane < 32 ? "small-lane" : "";
      body = `
        <text class="tank-name ${fontSize}" x="${xs}" y="${y + 4}">${escapeHtml(tank.name)}</text>
        <text class="tank-pct ${fontSize}" x="${xe}" y="${y + 4}" text-anchor="end">${
          volume ? `<tspan class="tank-vol">${escapeHtml(volume)}</tspan><tspan dx="6">${escapeHtml(percent)}</tspan>` : escapeHtml(percent)
        }</text>`;
    }
    return `<g class="tank-label ${state.level}" ${entity ? `data-entity="${entity}"` : ""} tabindex="0" role="button" aria-label="${escapeHtml(
      `${tank.name}: ${percent} ${state.statusText || ""}`,
    )}">${title}${body}</g>`;
  });
}

/** Render the plan-view SVG for the configured axles, wheels, and tanks. */
export function renderVehicle(hass, model, orientation, uid) {
  const geometry = ORIENTATIONS[orientation];
  const vertical = orientation === "vertical";
  const { axles, rearFront } = placeAxles(model);
  const states = new Map();
  for (const axle of axles) {
    if (axle.ghost) continue;
    for (const tire of [...axle.left, ...axle.right]) states.set(tire, tireState(hass, tire));
  }
  for (const tank of model.tanks) states.set(tank, tankState(hass, tank));
  const span = tankSpan(rearFront);
  const chips = axles.flatMap((axle) =>
    [
      ["left", -1],
      ["right", 1],
    ].map(([side, sign]) =>
      axle.ghost ? ghostChip(axle, sign, geometry) : tireChip(axle, side, sign, states, geometry),
    ),
  );
  return `
    <svg class="vehicle" viewBox="0 0 ${geometry.width} ${geometry.height}" role="img" aria-label="${escapeHtml(model.name)}">
      <defs>
        <linearGradient id="hv-body-${uid}" x1="0" y1="0" x2="0" y2="1" gradientUnits="objectBoundingBox">
          <stop offset="0" class="body-stop-edge"></stop>
          <stop offset="0.5" class="body-stop-mid"></stop>
          <stop offset="1" class="body-stop-edge"></stop>
        </linearGradient>
        <linearGradient id="hv-glass-${uid}" x1="0" y1="0" x2="1" y2="0">
          <stop offset="0" class="glass-stop-a"></stop>
          <stop offset="1" class="glass-stop-b"></stop>
        </linearGradient>
      </defs>
      <g transform="${geometry.transform}">
        ${bodyShapes(uid)}
        ${tankShapes(model, span, states).join("")}
        ${axles.map((axle) => tireRects(axle, states)).join("")}
      </g>
      ${tankLabels(model, span, states, geometry, vertical).join("")}
      ${chips.join("")}
    </svg>`;
}

// ---------------------------------------------------------------------------
// Card element.
// ---------------------------------------------------------------------------

const STYLES = `
  :host {
    --hv-ok: var(--success-color, #43a047);
    --hv-watch: var(--warning-color, #ffa600);
    --hv-alert: var(--error-color, #db4437);
    --hv-offline: var(--disabled-text-color, #9e9e9e);
    --hv-fresh: #29b6f6;
    --hv-gray: #90a4ae;
    --hv-black: #8d6e63;
    --hv-text: var(--primary-text-color, #212121);
    --hv-muted: var(--secondary-text-color, #727272);
    --hv-card: var(--ha-card-background, var(--card-background-color, #fff));
    --hv-line: var(--divider-color, rgba(127, 127, 127, 0.25));
    display: block;
  }
  ha-card { overflow: hidden; height: 100%; }
  .wrap { padding: 14px 16px 12px; display: flex; flex-direction: column; gap: 8px; }
  header { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
  .title { flex: 1 1 auto; min-width: 0; }
  .name { font-size: 1.25em; font-weight: 600; line-height: 1.2; color: var(--hv-text);
    white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .subtitle { font-size: 0.85em; color: var(--hv-muted); white-space: nowrap;
    overflow: hidden; text-overflow: ellipsis; }
  .pills { display: flex; gap: 6px; flex-wrap: wrap; }
  .pill { display: inline-flex; align-items: center; gap: 4px; padding: 3px 10px;
    border-radius: 999px; font-size: 0.8em; font-weight: 600; line-height: 18px;
    background: color-mix(in srgb, var(--pill) 16%, transparent); color: var(--pill);
    border: 1px solid color-mix(in srgb, var(--pill) 35%, transparent); }
  .pill ha-icon { --mdc-icon-size: 16px; }
  .pill.mode { --pill: var(--primary-color, #03a9f4); cursor: pointer; }
  .pill.ok { --pill: var(--hv-ok); }
  .pill.watch { --pill: var(--hv-watch); }
  .pill.alert { --pill: var(--hv-alert); }
  .pill.offline { --pill: var(--hv-muted); }
  .message { font-size: 0.85em; color: var(--hv-muted); text-align: center; }
  svg.vehicle { width: 100%; height: auto; display: block; overflow: visible;
    font-family: var(--ha-font-family-body, inherit); }
  svg.vehicle.vertical { max-height: 80vh; }
  .body { stroke: color-mix(in srgb, var(--hv-text) 28%, transparent); stroke-width: 1.5;
    filter: drop-shadow(0 6px 10px rgba(0, 0, 0, 0.18)); }
  .body-stop-edge { stop-color: color-mix(in srgb, var(--hv-text) 9%, var(--hv-card)); }
  .body-stop-mid { stop-color: color-mix(in srgb, var(--hv-text) 3%, var(--hv-card)); }
  .glass-stop-a { stop-color: color-mix(in srgb, var(--primary-color, #03a9f4) 18%, var(--hv-card)); }
  .glass-stop-b { stop-color: color-mix(in srgb, var(--primary-color, #03a9f4) 45%, var(--hv-card)); }
  .glass { stroke: color-mix(in srgb, var(--primary-color, #03a9f4) 50%, transparent); stroke-width: 1; }
  .rib { stroke: color-mix(in srgb, var(--hv-text) 5%, transparent); stroke-width: 1; }
  .frame { stroke: color-mix(in srgb, var(--hv-text) 12%, transparent); stroke-width: 3;
    stroke-dasharray: 2 6; stroke-linecap: round; }
  .mirror { fill: color-mix(in srgb, var(--hv-text) 35%, var(--hv-card)); }
  .roof-unit { fill: color-mix(in srgb, var(--hv-text) 6%, transparent);
    stroke: color-mix(in srgb, var(--hv-text) 12%, transparent); }
  .axle { stroke: color-mix(in srgb, var(--hv-text) 45%, var(--hv-card)); stroke-width: 6;
    stroke-linecap: round; }
  .tire rect { fill: color-mix(in srgb, var(--lvl) 82%, #000); stroke: color-mix(in srgb, var(--lvl) 60%, #000);
    stroke-width: 1.5; }
  .tire .tread { stroke: rgba(0, 0, 0, 0.28); stroke-width: 2; }
  .tire.ghost rect { fill: transparent; stroke: var(--hv-offline); stroke-dasharray: 4 3; }
  .tire.ghost .tread { display: none; }
  .ok { --lvl: var(--hv-ok); }
  .watch { --lvl: var(--hv-watch); }
  .alert { --lvl: var(--hv-alert); }
  .offline { --lvl: var(--hv-offline); }
  .chip-bg { fill: color-mix(in srgb, var(--lvl, var(--hv-offline)) 7%, var(--hv-card));
    stroke: color-mix(in srgb, var(--lvl, var(--hv-offline)) 55%, transparent); stroke-width: 1.5; }
  .chip.ok .chip-bg { stroke: var(--hv-line); }
  .chip-bg.ghost { fill: transparent; stroke: var(--hv-line); stroke-dasharray: 4 4; }
  text { fill: var(--hv-text); font-size: 12px; }
  .chip-label { fill: var(--hv-muted); font-size: 9px; font-weight: 600; letter-spacing: 0.06em;
    text-transform: uppercase; }
  .big { font-size: 19px; font-weight: 700; }
  .mid { font-size: 14px; font-weight: 700; }
  .unit { fill: var(--hv-muted); font-size: 9.5px; font-weight: 500; }
  .small { fill: var(--hv-muted); font-size: 10.5px; }
  .tiny { fill: var(--hv-muted); font-size: 9px; }
  .muted { fill: var(--hv-muted); }
  .flag { fill: var(--lvl); font-size: 8.5px; font-weight: 700; letter-spacing: 0.04em; }
  .wheel { fill: var(--lvl); font-size: 9.5px; font-weight: 700; }
  .trend { fill: var(--lvl); font-size: 8.5px; }
  .hot { fill: var(--hv-alert); font-weight: 700; }
  .dot { fill: var(--lvl); }
  .hit { fill: transparent; }
  .tank-shell { fill: color-mix(in srgb, var(--tank) 10%, var(--hv-card)); }
  .tank-fill { fill: color-mix(in srgb, var(--tank) 70%, transparent); }
  .tank-frame { fill: none; stroke: color-mix(in srgb, var(--tank) 65%, transparent); stroke-width: 1.5; }
  .tank.watch .tank-frame, .tank.alert .tank-frame { stroke: var(--lvl); stroke-width: 2.5; }
  .tank.offline .tank-frame { stroke: var(--hv-offline); stroke-dasharray: 4 3; }
  .tank.fresh_water { --tank: var(--hv-fresh); }
  .tank.gray_water { --tank: var(--hv-gray); }
  .tank.black_water { --tank: var(--hv-black); }
  .tank { --tank: var(--primary-color, #03a9f4); }
  .tank-label text { paint-order: stroke; stroke: var(--hv-card); stroke-width: 3px;
    stroke-linejoin: round; }
  .tank-name { font-size: 11px; font-weight: 600; }
  .tank-pct { font-size: 13px; font-weight: 700; }
  .tank-vol { fill: var(--hv-muted); font-size: 10px; font-weight: 500; }
  .small-lane { font-size: 10px; }
  .tank-label.watch .tank-pct, .tank-label.alert .tank-pct { fill: var(--lvl); }
  [data-entity] { cursor: pointer; }
  [data-entity]:focus { outline: none; }
  [data-entity]:focus-visible .chip-bg, .chip [data-entity]:focus-visible .hit,
  .chip[data-entity]:focus-visible .chip-bg { stroke: var(--primary-color, #03a9f4); stroke-width: 2.5; }
  .chip.alert .chip-bg, .tire.alert rect, .tank.alert .tank-frame { animation: hv-pulse 1.6s ease-in-out infinite; }
  @keyframes hv-pulse { 50% { stroke-opacity: 0.35; } }
  @media (prefers-reduced-motion: reduce) {
    .chip.alert .chip-bg, .tire.alert rect, .tank.alert .tank-frame { animation: none; }
  }
  .legend { display: flex; justify-content: center; gap: 14px; flex-wrap: wrap;
    font-size: 0.75em; color: var(--hv-muted); }
  .legend span { display: inline-flex; align-items: center; gap: 5px; }
  .legend i { width: 9px; height: 9px; border-radius: 50%; background: var(--lvl); display: inline-block; }
`;

let instanceCounter = 0;

function fireMoreInfo(node, entityId) {
  node.dispatchEvent(
    new CustomEvent("hass-more-info", {
      detail: { entityId },
      bubbles: true,
      composed: true,
    }),
  );
}

export class HavrvRvCard extends HTMLElement {
  constructor() {
    super();
    this._uid = ++instanceCounter;
    this._width = 0;
    this.attachShadow({ mode: "open" });
    const activate = (event) => {
      const target = event
        .composedPath()
        .find((node) => node instanceof Element && node.dataset?.entity);
      if (!target) return;
      event.preventDefault();
      event.stopPropagation();
      fireMoreInfo(this, target.dataset.entity);
    };
    this.shadowRoot.addEventListener("click", activate);
    this.shadowRoot.addEventListener("keydown", (event) => {
      if (event.key === "Enter" || event.key === " ") activate(event);
    });
  }

  static getConfigForm() {
    return {
      schema: [
        { name: "device_id", selector: { device: { filter: { integration: DOMAIN } } } },
        {
          name: "layout",
          selector: {
            select: {
              mode: "dropdown",
              options: LAYOUTS.map((value) => ({ value, label: STR.form[value] })),
            },
          },
        },
        {
          type: "grid",
          name: "",
          schema: [
            { name: "show_header", selector: { boolean: {} } },
            { name: "show_legend", selector: { boolean: {} } },
          ],
        },
      ],
      computeLabel: (schema) => STR.form[schema.name],
    };
  }

  static getStubConfig(hass) {
    const rv = findRvDevices(hass)[0];
    return rv ? { device_id: rv.id } : {};
  }

  setConfig(config) {
    if (!config || typeof config !== "object") throw new Error("Invalid configuration");
    if (config.layout && !LAYOUTS.includes(config.layout)) {
      throw new Error(`layout must be one of: ${LAYOUTS.join(", ")}`);
    }
    this._config = { layout: "auto", show_header: true, show_legend: true, ...config };
    this._renderKey = undefined;
    this._update();
  }

  set hass(hass) {
    this._hass = hass;
    this._update();
  }

  get hass() {
    return this._hass;
  }

  getCardSize() {
    return this._orientation === "vertical" ? 12 : 7;
  }

  getGridOptions() {
    return { columns: "full", min_columns: 6, rows: "auto" };
  }

  connectedCallback() {
    if (!this._resizeObserver && typeof ResizeObserver !== "undefined") {
      this._resizeObserver = new ResizeObserver((entries) => {
        const width = entries[0]?.contentRect.width || 0;
        if (Math.abs(width - this._width) < 1) return;
        this._width = width;
        this._update();
      });
    }
    this._resizeObserver?.observe(this);
  }

  disconnectedCallback() {
    this._resizeObserver?.disconnect();
  }

  _resolveOrientation() {
    if (this._config.layout !== "auto") return this._config.layout;
    return this._width && this._width < VERTICAL_BREAKPOINT ? "vertical" : "horizontal";
  }

  _update() {
    if (!this._config || !this._hass) return;
    const hass = this._hass;
    const rv = resolveRvDevice(hass, this._config.device_id);
    const model = rv ? buildModel(hass, rv) : undefined;
    const orientation = this._resolveOrientation();
    const key = JSON.stringify([
      orientation,
      this._config,
      hass.locale?.language,
      hass.themes?.darkMode,
      model && {
        name: model.name,
        axles: model.axles,
        tanks: model.tanks,
        mode: model.operationMode,
      },
      model?.watched.map((id) => {
        const state = hass.states[id];
        return state ? [state.state, state.attributes.unit_of_measurement] : null;
      }),
    ]);
    if (key === this._renderKey) return;
    this._renderKey = key;
    this._orientation = orientation;
    this.shadowRoot.innerHTML = `<style>${STYLES}</style><ha-card>${
      model ? this._renderModel(model, orientation) : `<div class="wrap"><div class="message">${escapeHtml(STR.noProfile)}</div></div>`
    }</ha-card>`;
    this._fitRows();
  }

  /** Drop the pressure unit from dual rows whose text would collide. */
  _fitRows() {
    for (const row of this.shadowRoot.querySelectorAll(".row")) {
      const pressure = row.querySelector(".row-pressure");
      const right = row.querySelector(".row-right");
      if (!pressure?.getBBox || !right?.textContent) continue;
      const box = pressure.getBBox();
      if (box.width && box.x + box.width + 3 > right.getBBox().x) {
        pressure.querySelector(".unit")?.remove();
      }
    }
  }

  _renderHeader(model) {
    const hass = this._hass;
    const subtitle = [...new Set(
      ["year", "manufacturer", "make", "model"]
        .map((role) => formatState(hass, model.profile[role]))
        .filter((value) => value && String(value).trim()),
    )].join(" ");
    const pills = [];
    const mode = stateOf(hass, model.operationMode);
    if (mode && !UNAVAILABLE.has(mode.state)) {
      pills.push(`<span class="pill mode" data-entity="${model.operationMode}" tabindex="0" role="button">
        <ha-icon icon="${MODE_ICONS[mode.state] || "mdi:rv-truck"}"></ha-icon>${escapeHtml(formatState(hass, model.operationMode))}</span>`);
    }
    const summary = summarize(hass, model);
    if (summary.alert) pills.push(`<span class="pill alert"><ha-icon icon="mdi:alert-circle"></ha-icon>${STR.alerts(summary.alert)}</span>`);
    if (summary.watch) pills.push(`<span class="pill watch"><ha-icon icon="mdi:eye"></ha-icon>${STR.watch(summary.watch)}</span>`);
    if (!summary.alert && !summary.watch) pills.push(`<span class="pill ok"><ha-icon icon="mdi:check-circle"></ha-icon>${STR.allClear}</span>`);
    if (summary.offline) pills.push(`<span class="pill offline"><ha-icon icon="mdi:signal-off"></ha-icon>${STR.offline(summary.offline)}</span>`);
    return `<header>
      <div class="title">
        <div class="name">${escapeHtml(model.name)}</div>
        ${subtitle ? `<div class="subtitle">${escapeHtml(subtitle)}</div>` : ""}
      </div>
      <div class="pills">${pills.join("")}</div>
    </header>`;
  }

  _renderModel(model, orientation) {
    const legend = [
      ["ok", STR.legendOk],
      ["watch", STR.legendWatch],
      ["alert", STR.legendAlert],
      ["offline", STR.legendOffline],
    ]
      .map(([level, label]) => `<span class="${level}"><i></i>${label}</span>`)
      .join("");
    const svg = renderVehicle(this._hass, model, orientation, this._uid).replace(
      'class="vehicle"',
      `class="vehicle ${orientation}"`,
    );
    return `<div class="wrap">
      ${this._config.show_header ? this._renderHeader(model) : ""}
      ${svg}
      ${model.axles.length ? "" : `<div class="message">${escapeHtml(STR.noTires)}</div>`}
      ${this._config.show_legend ? `<div class="legend">${legend}</div>` : ""}
    </div>`;
  }
}

// ---------------------------------------------------------------------------
// Dashboard and view strategies.
// ---------------------------------------------------------------------------

const heading = (text, icon) => ({ type: "heading", heading: text, icon });
const halfTile = (entity, extra = {}) => ({
  type: "tile",
  entity,
  grid_options: { columns: 6 },
  ...extra,
});

/** Build a sections view for one RV from its registry layout. */
export function rvView(hass, rv) {
  const model = buildModel(hass, rv);
  const sections = [
    {
      type: "grid",
      column_span: 4,
      cards: [{ type: `custom:${CARD_TYPE}`, device_id: rv.id }],
    },
  ];
  const coach = [heading(STR.coach, "mdi:rv-truck")];
  if (model.operationMode) {
    coach.push({
      type: "tile",
      entity: model.operationMode,
      features: [{ type: "select-options" }],
      features_position: "bottom",
    });
  }
  if (model.profileEntities.length) {
    coach.push({ type: "entities", entities: model.profileEntities, state_color: false });
  }
  if (coach.length > 1) sections.push({ type: "grid", cards: coach });
  if (model.tanks.length) {
    sections.push({
      type: "grid",
      cards: [
        heading(STR.tanks, "mdi:water"),
        ...model.tanks.flatMap((tank) =>
          [
            tank.percentage && halfTile(tank.percentage, { name: tank.name }),
            tank.history && halfTile(tank.history),
          ].filter(Boolean),
        ),
      ],
    });
  }
  if (model.monitorEntities.length) {
    sections.push({
      type: "grid",
      cards: [
        heading(STR.tireAnalysis, "mdi:tire"),
        { type: "entities", entities: model.monitorEntities },
      ],
    });
  }
  for (const system of model.systems) {
    sections.push({
      type: "grid",
      cards: [heading(system.name), ...system.entities.map((entity) => halfTile(entity))],
    });
  }
  return { type: "sections", max_columns: 4, sections };
}

const emptyView = () => ({
  type: "sections",
  sections: [{ type: "grid", cards: [{ type: "markdown", content: STR.noProfile }] }],
});

const slugify = (text, fallback) =>
  text
    .toLowerCase()
    .normalize("NFKD")
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "") || fallback;

export class HavrvDashboardStrategy extends HTMLElement {
  static async generate(_config, hass) {
    const rvs = findRvDevices(hass);
    if (!rvs.length) {
      return { title: "RV", views: [{ ...emptyView(), title: "RV", path: "rv" }] };
    }
    const used = new Set();
    return {
      title: rvs.length === 1 ? deviceName(rvs[0]) || "RV" : "RV",
      views: rvs.map((rv, i) => {
        let path = slugify(deviceName(rv), `rv-${i + 1}`);
        if (used.has(path)) path = `${path}-${i + 1}`;
        used.add(path);
        return { ...rvView(hass, rv), title: deviceName(rv) || "RV", path, icon: "mdi:rv-truck" };
      }),
    };
  }
}

export class HavrvViewStrategy extends HTMLElement {
  static async generate(config, hass) {
    const rv = resolveRvDevice(hass, config?.device_id);
    return rv ? rvView(hass, rv) : emptyView();
  }
}

// ---------------------------------------------------------------------------
// Registration.
// ---------------------------------------------------------------------------

const define = (tag, element) => {
  if (!customElements.get(tag)) customElements.define(tag, element);
};

define(CARD_TYPE, HavrvRvCard);
define(`ll-strategy-dashboard-${STRATEGY_TYPE}`, HavrvDashboardStrategy);
define(`ll-strategy-view-${STRATEGY_TYPE}`, HavrvViewStrategy);

window.customCards = window.customCards || [];
if (!window.customCards.some((card) => card.type === CARD_TYPE)) {
  window.customCards.push({
    type: CARD_TYPE,
    name: "HAVRV RV overview",
    description: "Plan view of the RV with live tire and tank readings.",
    preview: true,
    documentationURL: DOCS_URL,
  });
}
window.customStrategies = window.customStrategies || [];
for (const strategyType of ["dashboard", "view"]) {
  if (
    !window.customStrategies.some(
      (item) => item.type === STRATEGY_TYPE && item.strategyType === strategyType,
    )
  ) {
    window.customStrategies.push({
      type: STRATEGY_TYPE,
      strategyType,
      name: "HAVRV RV",
      description: "RV overview generated from the HAVRV configuration.",
      documentationURL: DOCS_URL,
    });
  }
}
