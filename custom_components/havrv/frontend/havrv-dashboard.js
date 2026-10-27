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
const POWER_ROLES = {
  power_voltage: "voltage",
  power_current: "current",
  power_enabled: "enabled",
  power_charging: "charging",
  power_warning: "warning",
  power_problem: "problem",
  power_location: "location",
  shore_voltage: "voltage",
  shore_current: "current",
  shore_frequency: "frequency",
  shore_power: "power",
  shore_line_2_voltage: "line_2_voltage",
  shore_line_2_current: "line_2_current",
  shore_line_2_frequency: "line_2_frequency",
  shore_line_2_power: "line_2_power",
  shore_energy: "energy",
};
const POWER_LOCATION_LABELS = {
  left_front: "L-Front",
  left_mid: "L-Mid",
  left_rear: "L-Rear",
  right_front: "R-Front",
  right_mid: "R-Mid",
  right_rear: "R-Rear",
  left: "L (outside)",
  right: "R (outside)",
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
    auto: "Automatic",
    horizontal: "Horizontal",
    vertical: "Vertical",
  },
};

// Every display class declares its default, label and model fields here.
// Strategies and the card share this contract; do not add undeclared groups.
export const DISPLAY_CLASSES = {
  show_header: { default: true, label: "Show header", fields: {} },
  show_legend: { default: true, label: "Show legend", fields: {} },
  show_tires: { default: true, label: "Show tires and tire analysis", fields: { axles: [], monitorEntities: [] } },
  show_tanks: { default: true, label: "Show tanks", fields: { tanks: [] } },
  show_power: { default: true, label: "Show placed power sources", fields: { powerSources: [] } },
  show_tow: { default: true, label: "Show tow vehicle", fields: { tow: undefined } },
  show_coach: { default: true, label: "Show coach information and operation mode", fields: { profile: {}, profileEntities: [], operationMode: undefined } },
  show_systems: { default: true, label: "Show mapped system sections", fields: { systems: [] } },
};

export function dashboardOptions(config = {}) {
  return {
    layout: config.layout ?? "auto",
    ...Object.fromEntries(Object.entries(DISPLAY_CLASSES).map(([key, group]) =>
      [key, config[key] ?? group.default])),
  };
}

/** Filter before rendering, counting or placing anything; never alter discovery. */
export function visibleModel(model, config = {}) {
  const options = dashboardOptions(config);
  const visible = { ...model, tiresVisible: options.show_tires && model.tiresVisible !== false };
  for (const [key, group] of Object.entries(DISPLAY_CLASSES)) {
    if (options[key] === false) Object.assign(visible, structuredClone(group.fields));
  }
  visible.watched = watchedEntities(visible);
  return visible;
}

function watchedEntities(model) {
  return [
    ...Object.values(model.profile || {}),
    model.operationMode,
    ...Object.values(model.tow || {}),
    ...model.axles.flatMap((axle) =>
      [...axle.left, ...axle.right].flatMap((tire) =>
        Object.values(TIRE_ROLES).map((role) => tire[role]),
      ),
    ),
    ...model.tanks.flatMap((tank) => [tank.percentage, tank.status, tank.level]),
    ...(model.powerSources || []).flatMap((source) =>
      [...new Set(Object.values(POWER_ROLES))].map((role) => source[role]),
    ),
  ].filter(Boolean);
}

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
    powerSources: [],
    tow: undefined,
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
      const roles = entityRoles(entries, TANK_ROLES);
      if (!Object.keys(roles).length) continue;
      model.tanks.push({
        type,
        name: device.name_by_user || STR.tankLabels[type] || deviceName(device),
        ...roles,
      });
    } else if (part.startsWith("source_")) {
      const key = part.slice("source_".length);
      model.powerSources.push({
        key,
        name: deviceName(device),
        entities: visible(device.id),
        ...entityRoles(entries, POWER_ROLES),
      });
    } else if (part === "operations") {
      model.operationMode = entityRoles(entries, { operation_mode: "mode" }).mode;
    } else if (part === "tow") {
      model.tow = entityRoles(entries, {
        towing: "enabled", tow_type: "type", tow_weight: "weight",
      });
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
  model.powerSources.sort((a, b) => a.key.localeCompare(b.key, undefined, { numeric: true }));
  model.watched = watchedEntities(model);
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
  if (!state || UNAVAILABLE.has(state.state) || !String(state.state).trim()) return undefined;
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

const readingHistory = new WeakMap();

function validReading(hass, entityId) {
  const state = stateOf(hass, entityId);
  if (!state || UNAVAILABLE.has(state.state) || !String(state.state).trim()) return false;
  const entry = hass.entities?.[entityId];
  const booleanBattery = entry?.platform === DOMAIN && entry.translation_key === "tire_battery"
    && (state.state === "on" || state.state === "off");
  return entityId.startsWith("binary_sensor.") || booleanBattery
    ? state.state === "on" || state.state === "off"
    : Number.isFinite(Number(state.state));
}

/** Use only observed valid reports, never the timestamp of an unavailable state. */
export function rememberReadings(hass, entityIds, history, now = Date.now()) {
  for (const id of entityIds) {
    if (!validReading(hass, id)) continue;
    const state = stateOf(hass, id);
    const timestamp = Date.parse(state.last_reported || state.last_updated || state.last_changed);
    if (Number.isFinite(timestamp) && timestamp <= now) {
      history.set(id, Math.max(history.get(id) || 0, timestamp));
    }
  }
  readingHistory.set(hass, history);
}

export function missingReadingText(hass, entityIds, now = Date.now()) {
  const missing = entityIds.filter((id) => id && !validReading(hass, id));
  if (!missing.length) return "";
  const timestamps = missing.map((id) => readingHistory.get(hass)?.get(id));
  if (timestamps.some((timestamp) => !Number.isFinite(timestamp))) return "Last data unknown";
  // Use the oldest missing channel so a newer channel cannot hide a long outage.
  const seconds = Math.max(0, Math.floor((now - Math.min(...timestamps)) / 1000));
  const age = seconds < 60 ? `${seconds}s` : seconds < 3600 ? `${Math.floor(seconds / 60)}m`
    : seconds < 86400 ? `${Math.floor(seconds / 3600)}h` : `${Math.floor(seconds / 86400)}d`;
  return `Last data ${age} ago`;
}

/** Report only declared measurements and definite binary statuses. */
export function powerState(hass, source) {
  const binary = (entity) => {
    const value = stateOf(hass, entity)?.state;
    return value === "on" ? true : value === "off" ? false : undefined;
  };
  const state = {
    enabled: binary(source.enabled),
    charging: binary(source.charging),
    warning: binary(source.warning),
    problem: binary(source.problem),
    location: stateOf(hass, source.location)?.state,
  };
  for (const metric of SHORE_READING_METRICS) {
    state[metric] = numeric(hass, source[metric], metric === "energy" ? 3 : 1);
  }
  state.level = state.problem === true ? "problem"
    : state.warning === true ? "warning"
      : (source.problem && state.problem === undefined) || (source.warning && state.warning === undefined)
        ? "unknown" : state.enabled === true ? "on" : state.enabled === false ? "off" : "unknown";
  return state;
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

/** Count tires, tanks and visible explicitly mapped power statuses needing attention. */
export function summarize(hass, model, showPower = true) {
  model = visibleModel(model, typeof showPower === "object" ? showPower : { show_power: showPower });
  const levels = [
    ...model.axles.flatMap((axle) =>
      [...axle.left, ...axle.right].map((tire) => tireState(hass, tire).level),
    ),
    ...model.tanks.map((tank) => tankState(hass, tank).level),
    ...(model.powerSources || []).flatMap((source) => {
      const state = powerState(hass, source);
      if (!POWER_LOCATION_LABELS[state.location]) return [];
      if (state.level === "problem") return ["alert"];
      if (state.level === "warning") return ["watch"];
      return state.level === "unknown" && (source.enabled || source.warning || source.problem)
        ? ["offline"] : [];
    }),
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
    chipWidth: 156,
  },
  vertical: {
    width: 496,
    height: 908,
    transform: `matrix(0 -1 1 0 248 ${24 + L})`,
    map: (u, v) => [248 + v, 24 + L - u],
    chipWidth: 156,
  },
};

const r1 = (value) => Math.round(value * 10) / 10;

function compactDataAge(age) {
  const compact = age === "Last data unknown" ? "?" : age.replace(/^Last data | ago$/g, "");
  return /^\d+d$/.test(compact) && Number.parseInt(compact, 10) >= 365
    ? `${Math.floor(Number.parseInt(compact, 10) / 365)}y` : compact;
}

function dataAgeWidth(age, small = false) {
  return age ? 11 + compactDataAge(age).length * (small ? 4.2 : 6) : 0;
}

function dataAgeLabel(age, x, y) {
  if (!age) return "";
  return `<g class="data-age" role="img" aria-label="${escapeHtml(age)}" transform="translate(${x} ${y})">
    <title>${escapeHtml(age)}</title>
    <circle class="age-clock" cx="4" cy="-3.5" r="3.5"></circle>
    <path class="age-clock" d="M4 -6 V-3.5 L6 -2.5"></path>
    <text x="11" y="0">${escapeHtml(compactDataAge(age))}</text>
  </g>`;
}

function axleLabel(axle, driveCount) {
  if (axle.kind === "front") return "Front";
  if (axle.kind === "tag") return "Tag";
  return driveCount > 1 ? `Rear ${axle.index}` : "Rear";
}

/** Assign plan positions; rear axles are packed toward the back of the coach. */
function placeAxles(model) {
  if (model.tiresVisible === false) return { axles: [], rearFront: REAR_U };
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
  // Full rear/tag layouts still need room for readable tank names and values.
  if (end - start < 240) start = end - 240;
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
    <rect class="mirror" x="782" y="88" width="10" height="16" rx="3"></rect>`;
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

function flagText(state, tire) {
  return [
    state.dropping && `<tspan ${readingAction(tire.pressure)}>▼</tspan>`,
    state.hot && `<tspan ${readingAction(tire.temperature)}>HOT</tspan>`,
    state.lowBattery && `<tspan ${readingAction(tire.battery || tire.batteryProblem)}>BAT</tspan>`,
  ]
    .filter(Boolean)
    .join(" ");
}

function readingAction(entity) {
  return entity ? `data-entity="${escapeHtml(entity)}" tabindex="0" role="button"` : "";
}

function tireChip(hass, axle, side, sign, states, geometry, box) {
  const tires = axle[side];
  const dual = tires.length > 1;
  const { height, width, x, y } = box;
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
      ? `<tspan class="mid">${escapeHtml(state.pressure.text)}</tspan><tspan class="unit" dx="2">${escapeHtml(state.pressure.unit)}</tspan>`
      : `<tspan class="mid muted">—</tspan>`;
    const flags = flagText(state, tire);
    const age = missingReadingText(hass, [tire.pressure, tire.temperature, tire.battery]);
    const pressureAge = !state.pressure && state.temperature ? age : "";
    const rightAge = pressureAge ? "" : age;
    const rightEnd = x + width - 9;
    parts.push(
      `<g class="row">
        <text class="row-pressure" x="${x + 9}" y="${y + 34}" ${readingAction(tire.pressure)}>${pressure}</text>
        ${dataAgeLabel(pressureAge, x + 25, y + 34)}
        <text class="small row-right" x="${rightEnd - (rightAge ? dataAgeWidth(rightAge) + 4 : 0)}" y="${y + 34}" text-anchor="end" ${readingAction(tire.temperature)}>${
          state.temperature
            ? `<tspan class="${state.hot ? "hot" : ""}" data-compact="${escapeHtml(temperatureText(state.temperature, true))}">${escapeHtml(temperatureText(state.temperature, false))}</tspan>`
            : `<tspan>${escapeHtml(STR.noData)}</tspan>`
        }</text>
        ${dataAgeLabel(rightAge, rightEnd - dataAgeWidth(rightAge), y + 34)}
      </g>`,
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
    const rowY = y + 32 + rowIndex * box.rowHeight;
    const entity = tire.pressure || tire.temperature || "";
    const pressure = state.pressure
      ? `<tspan class="mid">${escapeHtml(state.pressure.text)}</tspan><tspan class="unit" dx="2">${escapeHtml(state.pressure.unit)}</tspan>`
      : `<tspan class="mid muted">—</tspan>`;
    // Rows are narrow: keep the full temperature, color a hot temperature,
    // and show trend and battery flags in the chip header.
    const temperature = temperatureText(state.temperature, false);
    const right = temperature
      ? `<tspan class="${state.hot ? "hot" : ""}" data-compact="${escapeHtml(temperatureText(state.temperature, true))}">${escapeHtml(temperature)}</tspan>`
      : `<tspan>${escapeHtml(STR.noData)}</tspan>`;
    const age = missingReadingText(hass, [tire.pressure, tire.temperature, tire.battery]);
    const pressureAge = !state.pressure && state.temperature ? age : "";
    const rightAge = pressureAge ? "" : age;
    const rightEnd = x + width - 9;
    return `<g class="row" ${entity ? `data-entity="${entity}"` : ""} tabindex="0" role="button" aria-label="${escapeHtml(
      `${tire.name}: ${state.reasons.join(", ") || STR.allClear}`,
    )}">
      <rect class="hit" x="${x}" y="${rowY - 15}" width="${width}" height="20"></rect>
      <text class="wheel ${state.level}" x="${x + 9}" y="${rowY}">${tire.wheel === "inner" ? STR.inner : STR.outer}</text>
      <text class="row-pressure" x="${x + 22}" y="${rowY}" ${readingAction(tire.pressure)}>${pressure}</text>
      ${dataAgeLabel(pressureAge, x + 38, rowY)}
      <text class="small row-right" x="${rightEnd - (rightAge ? dataAgeWidth(rightAge) + 4 : 0)}" y="${rowY}" text-anchor="end" ${readingAction(tire.temperature)}>${right}</text>
      ${dataAgeLabel(rightAge, rightEnd - dataAgeWidth(rightAge), rowY)}
    </g>`;
  });
  const headerFlags = [
    tireStates.some((state) => state.dropping) && `<tspan class="trend">▼</tspan>`,
    tireStates.some((state) => state.lowBattery) && "BAT",
  ].filter(Boolean);
  if (headerFlags.length) {
    parts.push(
      `<text class="flag ${level}" x="${x + width - 20}" y="${y + 13}" text-anchor="end">${headerFlags.join(" ")}</text>`,
    );
  }
  return `<g class="chip dual ${level}">${parts.join("")}${rows.join("")}</g>`;
}

function ghostChip(box) {
  return `<rect class="chip-bg ghost" x="${box.x}" y="${box.y}" width="${box.width}" height="${box.height}" rx="10"></rect>`;
}

/** Stack crowded tire labels outward, using the same obstacles for power. */
function layoutTireChips(hass, axles, geometry) {
  const boxes = [];
  for (const axle of axles) {
    for (const [side, sign] of [["left", -1], ["right", 1]]) {
      if (!axle[side].length) continue;
      const rowHeight = 20;
      const height = axle.ghost ? 52 : Math.max(52, 24 + axle[side].length * rowHeight);
      const width = Math.max(geometry.chipWidth, ...axle[side].map((tire) => {
        const pressure = numeric(hass, tire.pressure);
        const temperature = numeric(hass, tire.temperature);
        const pressureText = pressure ? `${pressure.text} ${pressure.unit}` : "—";
        const rightText = temperatureText(temperature, false) || STR.noData;
        const age = missingReadingText(hass, [tire.pressure, tire.temperature, tire.battery]);
        return Math.ceil(pressureText.length * 8.5 + rightText.length * 7 + 51
          + (age ? dataAgeWidth(age) + 4 : 0));
      }));
      const depth = geometry === ORIENTATIONS.horizontal ? height : width;
      let distance = TIRE_OUTER + CHIP_GAP + depth / 2;
      let box;
      do {
        const [cx, cy] = geometry.map(axle.u, sign * distance);
        box = { axle, side, sign, rowHeight, x: r1(cx - width / 2), y: r1(cy - height / 2), width, height };
        distance += depth + CHIP_GAP;
      } while (boxes.some((other) => overlaps(box, other)));
      boxes.push(box);
    }
  }
  return boxes;
}

function drawingBounds(geometry, items, model) {
  let base = { x: 0, y: 0, width: geometry.width, height: geometry.height };
  if (model.tiresVisible === false) {
    const [x0, y0] = geometry.map(0, -104);
    const [x1, y1] = geometry.map(L, 104);
    base = {
      x: Math.min(x0, x1) - 12, y: Math.min(y0, y1) - 12,
      width: Math.abs(x1 - x0) + 24, height: Math.abs(y1 - y0) + 24,
    };
  }
  const left = Math.min(base.x, ...items.map((box) => box.x - 12));
  const top = Math.min(base.y, ...items.map((box) => box.y - 12));
  const right = Math.max(base.x + base.width, ...items.map((box) => box.x + box.width + 12));
  const bottom = Math.max(base.y + base.height, ...items.map((box) => box.y + box.height + 12));
  return { x: left, y: top, width: right - left, height: bottom - top };
}

function tankShapes(model, span, states, band = TANK_BAND) {
  const [start, end] = span;
  const count = model.tanks.length;
  const gap = 8;
  const lane = (band * 2 - gap * (count - 1)) / count;
  return model.tanks.map((tank, i) => {
    const v0 = -band + i * (lane + gap);
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

function tankLabels(hass, model, span, states, geometry, vertical, band = TANK_BAND) {
  const [start, end] = span;
  const count = model.tanks.length;
  const gap = 8;
  const lane = (band * 2 - gap * (count - 1)) / count;
  return model.tanks.map((tank, i) => {
    const vc = -band + i * (lane + gap) + lane / 2;
    const state = states.get(tank);
    const entity = tank.percentage || tank.level || "";
    const percent = state.percent ? `${state.percent.text}%` : vertical ? "—" : STR.noData;
    const volume = state.volume ? `${state.volume.text} ${state.volume.unit}` : "";
    const age = missingReadingText(hass, [tank.percentage, tank.level]);
    const title = `<title>${escapeHtml(
      [tank.name, state.statusText].filter(Boolean).join(" · "),
    )}</title>`;
    let body;
    if (vertical) {
      const [x, yTop] = geometry.map(end - 18, vc);
      const [, yName] = geometry.map(start + 10, vc);
      const ageWidth = dataAgeWidth(age, true);
      const percentWidth = percent === "—" ? 12 : percent.length * (age ? 6 : 7);
      const readingStart = x - (percentWidth + (age ? ageWidth + 3 : 0)) / 2;
      body = `
        <text class="tank-pct${age ? " aged" : ""}" x="${age ? readingStart : x}" y="${yTop}" text-anchor="${age ? "start" : "middle"}" ${readingAction(tank.percentage)}>${escapeHtml(percent)}</text>
        ${dataAgeLabel(age, readingStart + percentWidth + 3, yTop)}
        ${volume ? `<text class="tiny" x="${x}" y="${yTop + 13}" text-anchor="middle" ${readingAction(tank.level)}>${escapeHtml(volume)}</text>` : ""}
        <text class="tank-name" x="${x}" y="${yName}" text-anchor="middle">${escapeHtml(truncate(tank.name, 7))}</text>`;
    } else {
      const [xs, y] = geometry.map(start + 12, vc);
      const [xe] = geometry.map(end - 12, vc);
      const fontSize = lane < 32 ? "small-lane" : "";
      body = `
        <text class="tank-name ${fontSize}" x="${xs}" y="${y - 5}">${escapeHtml(truncate(tank.name, Math.floor((end - start - 24) / 7)))}</text>
        <text class="tank-pct ${fontSize}" x="${xe - (age ? dataAgeWidth(age, true) + 4 : 0)}" y="${y + 12}" text-anchor="end">${
          volume ? `<tspan class="tank-vol" ${readingAction(tank.level)}>${escapeHtml(volume)}</tspan><tspan dx="6" ${readingAction(tank.percentage)}>${escapeHtml(percent)}</tspan>` : `<tspan ${readingAction(tank.percentage)}>${escapeHtml(percent)}</tspan>`
        }</text>`;
      body += dataAgeLabel(age, xe - dataAgeWidth(age, true), y + 12);
    }
    return `<g class="tank-label ${state.level}${vertical && lane < 26 ? " compact-tank" : ""}" ${entity ? `data-entity="${entity}"` : ""} tabindex="0" role="button" aria-label="${escapeHtml(
      `${tank.name}: ${percent} ${state.statusText || ""}`,
    )}">${title}${body}</g>`;
  });
}

function towDrawing(hass, model, geometry, bounds, vertical) {
  const tow = model.tow;
  const type = stateOf(hass, tow?.type)?.state;
  if (!isOn(hass, tow?.enabled) || !["car", "trailer"].includes(type)) return undefined;
  // Place behind the entire drawing, including dense electrical overflow lanes.
  const front = Math.min(-40, vertical
    ? geometry.map(0, 0)[1] - bounds.y - bounds.height - 24
    : bounds.x - geometry.map(0, 0)[0] - 24);
  const [x0, y0] = geometry.map(front - 220, -70);
  const [x1, y1] = geometry.map(front, 70);
  const box = {
    x: Math.min(x0, x1), y: Math.min(y0, y1),
    width: Math.abs(x1 - x0), height: Math.abs(y1 - y0),
  };
  const shape = type === "car"
    ? `<rect x="-216" y="-56" width="208" height="112" rx="32"></rect>
       <path d="M-64,-48 L-48,-34 L-48,34 L-64,48 Z M-170,-48 L-184,-34 L-184,34 L-170,48 Z"></path>
       ${[-180, -64].flatMap((u) => [-70, 56].map((v) =>
         `<rect x="${u}" y="${v}" width="32" height="14" rx="3"></rect>`)).join("")}`
    : `<path d="M0,0 L-40,-46 M0,0 L-40,46"></path>
       <rect x="-216" y="-58" width="176" height="116" rx="6"></rect>
       <path d="M-144,-58 V-70 H-112 V-58 M-144,58 V70 H-112 V58"></path>`;
  const weight = numeric(hass, tow.weight, 1);
  const label = `${type === "car" ? "Car" : "Trailer"} · ${weight ? `${weight.text} ${weight.unit}` : STR.noData}`;
  const [cx, cy] = geometry.map(front - 118, 0);
  return {
    box,
    svg: `<g class="tow" data-tow-type="${type}">
      <g class="tow-outline" transform="${geometry.transform}">
        <path d="M0,0 H${front}"></path>
        <g transform="translate(${front} 0)" data-entity="${tow.type}" tabindex="0" role="button" aria-label="${escapeHtml(label)}">
          <title>${escapeHtml(label)}</title>${shape}
        </g>
      </g>
      <text class="tow-label" x="${cx}" y="${cy - 20}" text-anchor="middle" data-entity="${tow.enabled}" tabindex="0" role="button">Towing</text>
      <text class="tow-label" x="${cx}" y="${cy}" text-anchor="middle" ${readingAction(tow.type)}>${escapeHtml(type === "car" ? "Car" : "Trailer")}
        <tspan x="${cx}" dy="18" ${readingAction(tow.weight)}>${escapeHtml(weight ? `${weight.text} ${weight.unit}` : STR.noData)}</tspan>
      </text>
    </g>`,
  };
}

/** Render the plan-view SVG for the RV and its currently towed vehicle. */
export function renderVehicle(hass, model, orientation, uid, showPower = true) {
  model = visibleModel(model, typeof showPower === "object" ? showPower : { show_power: showPower, show_tires: model.tiresVisible });
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
  const tireBoxes = layoutTireChips(hass, axles, geometry);
  const chips = tireBoxes.map((box) => box.axle.ghost ? ghostChip(box)
    : tireChip(hass, box.axle, box.side, box.sign, states, geometry, box));
  const power = model.powerSources?.length ? layoutPowerBoxes(hass, model, orientation) : undefined;
  const tankBand = TANK_BAND;
  let bounds = power?.bounds || drawingBounds(geometry, tireBoxes, model);
  const tow = towDrawing(hass, model, geometry, bounds, vertical);
  if (tow) bounds = drawingBounds(geometry, [bounds, tow.box], model);
  return `
    <svg class="vehicle" style="min-width:${bounds.width}px" viewBox="${bounds.x} ${bounds.y} ${bounds.width} ${bounds.height}" role="img" aria-label="${escapeHtml(model.name)}">
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
        ${axles.map((axle) => tireRects(axle, states)).join("")}
        ${tankShapes(model, span, states, tankBand).join("")}
      </g>
      ${tankLabels(hass, model, span, states, geometry, vertical, tankBand).join("")}
      ${chips.join("")}
      ${power ? renderPowerBoxes(hass, power) : ""}
      ${tow?.svg || ""}
    </svg>`;
}

const powerTag = (source) =>
  source.key.startsWith("house_bank_") ? `HB${source.key.slice(11)}`
    : source.key.startsWith("chassis_bank_") ? `CB${source.key.slice(13)}`
      : ({ inverter: "INV", generator: "GEN", shore_power: "SHORE" })[source.key] || source.name;

const POWER_READING_METRICS = ["voltage", "current", "charging"];
const AC_LINE_METRICS = ["voltage", "current", "frequency", "power"];
const SHORE_READING_METRICS = [
  "voltage", "current", "frequency", "power",
  "line_2_voltage", "line_2_current", "line_2_frequency", "line_2_power", "energy",
];
const powerMetricLabel = (metric, shore) => {
  if (metric === "current" && !shore) return "Amps";
  if (!shore) return metric[0].toUpperCase() + metric.slice(1);
  if (metric === "energy" || metric === "enabled") return metric === "energy" ? "Energy" : "Enabled";
  const kind = metric.replace(/^line_2_/, "");
  const label = ({ voltage: "Voltage", current: "Amps", frequency: "Frequency", power: "Watts" })[kind]
    || kind[0].toUpperCase() + kind.slice(1);
  return `Line ${metric.startsWith("line_2_") ? 2 : 1} ${label}`;
};
const POWER_STATUS_LABELS = {
  on: "On", off: "Off", warning: "Warning", problem: "Problem", unknown: "No status data",
};
const overlaps = (a, b, gap = 10) =>
  a.x < b.x + b.width + gap && a.x + a.width + gap > b.x
  && a.y < b.y + b.height + gap && a.y + a.height + gap > b.y;

function powerStatusEntity(source, state) {
  return state.level === "problem" ? source.problem
    : state.level === "warning" ? source.warning
      : source.problem && state.problem === undefined ? source.problem
        : source.warning && state.warning === undefined ? source.warning : source.enabled;
}

/** Compact original SVG equipment drawings, independent of external icon resources. */
function powerSymbol(source) {
  const shell = (x, y, width, height) =>
    `<rect class="equipment-shell" x="${x}" y="${y}" width="${width}" height="${height}" rx="2"></rect>`;
  if (source.key.includes("_bank_")) {
    return shell(2, 5, 20, 17)
      + '<path class="equipment-detail" d="M5 5 V2 H9 V5 M15 5 V2 H19 V5 M5 10 H9 M7 8 V12 M16 10 H19"></path>'
      + '<path class="equipment-energy" d="M13 8 L8 16 H12 L11 21 L17 13 H13 Z"></path>';
  }
  if (source.key === "generator") {
    return shell(1, 6, 22, 16)
      + '<path class="equipment-detail" d="M6 6 V2 H18 V6 M4 11 H10 M4 15 H10 M4 19 H10"></path>'
      + '<circle class="equipment-detail" cx="16" cy="14" r="4"></circle>'
      + '<path class="equipment-energy" d="M16 10 L13 15 H16 L15 19 L19 13 H16 Z"></path>';
  }
  if (source.key === "inverter") {
    return shell(1, 3, 22, 18)
      + '<path class="equipment-detail" d="M4 8 H9 M4 11 H9 M4 16 H9 M12 12 C14 5 16 5 17 12 S21 19 22 12"></path>';
  }
  return shell(6, 7, 12, 10)
    + '<path class="equipment-detail" d="M8 7 V1 M16 7 V1 M12 17 V21 Q12 23 7 23"></path>';
}

/** Place readouts beside their regions, avoiding tire chips and other sources. */
export function layoutPowerBoxes(hass, model, orientation) {
  const geometry = ORIENTATIONS[orientation];
  const vertical = orientation === "vertical";
  const { axles, rearFront } = placeAxles(model);
  const [tankStart, tankEnd] = tankSpan(rearFront);
  const tankObstacles = model.tanks.length ? [vertical
    ? { x: 248 - TANK_BAND, y: 884 - tankEnd, width: TANK_BAND * 2, height: tankEnd - tankStart }
    : { x: 30 + tankStart, y: 188 - TANK_BAND, width: tankEnd - tankStart, height: TANK_BAND * 2 }] : [];
  const obstacles = layoutTireChips(hass, axles, geometry);
  const placed = (model.powerSources || [])
    .map((source) => ({ source, state: powerState(hass, source) }))
    .filter(({ state }) => POWER_LOCATION_LABELS[state.location])
    .sort((a, b) => {
      const external = (location) => location === "left" || location === "right";
      return Number(external(a.state.location)) - Number(external(b.state.location))
        || a.state.location.localeCompare(b.state.location)
        || a.source.key.localeCompare(b.source.key, undefined, { numeric: true });
    });
  const icons = [];
  const size = 44;
  // Keep equipment readable. If the coach fills, use outward overflow lanes.
  for (const { source, state } of placed) {
    const location = state.location;
    const side = location.startsWith("left") ? -1 : 1;
    const external = location === "left" || location === "right";
    const regionU = location.endsWith("front") ? 680 : location.endsWith("rear") ? 110 : 430;
    let chosen;
    for (let offset = 0; offset <= L && !chosen; offset += 12) {
      for (const direction of offset ? [-1, 1] : [1]) {
        const u = regionU + offset * direction;
        if (u < size / 2 || u > L - size / 2) continue;
        const tireCollision = axles.some((axle) => Math.abs(axle.u - u) < TIRE_LENGTH / 2 + size * 0.7);
        const lanes = external ? [TIRE_OUTER + size / 2 + 14]
          : [BODY - size / 2, Math.max(0, BODY - size * 1.5 - 14)];
        for (const [laneIndex, lane] of lanes.entries()) {
          if (!external && tireCollision && laneIndex === 0) continue;
          const [cx, cy] = geometry.map(u, side * lane);
          const icon = { source, state, side, anchor: [cx, cy], x: cx - size / 2, y: cy - size / 2, width: size, height: size + 18 };
          if ([...obstacles, ...icons].some((other) => overlaps(icon, other, size / 5))
            || tankObstacles.some((other) => overlaps(icon, other, 4))) continue;
          chosen = icon;
          break;
        }
        if (chosen) break;
      }
    }
    if (!chosen) {
      let distance = BODY + size + 14;
      do {
        const [cx, cy] = geometry.map(regionU, side * distance);
        chosen = { source, state, side, anchor: [cx, cy], x: cx - size / 2, y: cy - size / 2, width: size, height: size + 18 };
        distance += size + 14;
      } while ([...obstacles, ...icons, ...tankObstacles].some((other) => overlaps(chosen, other)));
    }
    icons.push(chosen);
  }
  const boxes = [];
  for (const { source, state } of placed) {
    const location = state.location;
    const side = location.startsWith("left") ? -1 : 1;
    const external = location === "left" || location === "right";
    const u = location.endsWith("front") ? 680 : location.endsWith("rear") ? 110 : 430;
    const shore = source.key === "shore_power";
    const metrics = (shore ? SHORE_READING_METRICS : POWER_READING_METRICS)
      .filter((metric) => source[metric]);
    const lines = !shore ? []
      : AC_LINE_METRICS.some((metric) => source[`line_2_${metric}`]) ? ["", "line_2_"]
        : AC_LINE_METRICS.some((metric) => source[metric]) ? [""] : [];
    const rows = shore
      ? AC_LINE_METRICS.map((metric) =>
        lines.map((prefix) => source[`${prefix}${metric}`] ? `${prefix}${metric}` : undefined))
        .filter((row) => row.some(Boolean))
      : metrics.map((metric) => [metric]);
    const sharedMetrics = shore ? ["enabled", "energy"].filter((metric) => source[metric]) : [];
    rows.push(...sharedMetrics.map((metric) => [metric]));
    const labelWidth = Math.max(45, ...[...metrics, ...sharedMetrics].map((metric) =>
      powerMetricLabel(metric, shore).replace(/^Line [12] /, "").length * 5.5 + 8));
    const columnWidth = Math.max(75, ...metrics.map((metric) =>
      (state[metric] && typeof state[metric] === "object"
        ? `${state[metric].text} ${state[metric].unit}`.length * 8 + 12 : 75)),
      ...[...metrics, ...sharedMetrics].map((metric) => {
        const age = missingReadingText(hass, [source[metric]]);
        return age ? STR.noData.length * 5.5 + dataAgeWidth(age) + 16 : 0;
      }));
    const width = Math.max(156, labelWidth + columnWidth * Math.max(1, lines.length) + 18);
    const rowHeight = 20;
    const headerHeight = lines.length ? 16 : 0;
    const statusAge = missingReadingText(hass, ["enabled", "warning", "problem"].map((metric) => source[metric]));
    const height = Math.max(52, 24 + headerHeight + rows.length * rowHeight + (sharedMetrics.length ? 20 : 0));
    const depth = vertical ? width : height;
    const anchor = icons.find((icon) => icon.source === source).anchor;
    let distance = TIRE_OUTER + 14 + depth / 2;
    if (external && !vertical) {
      const center = geometry.map(0, 0)[vertical ? 0 : 1];
      distance = Math.max(distance, ...boxes.filter((box) => box.side === side).map((box) =>
        Math.abs((vertical ? box.x + box.width / 2 : box.y + box.height / 2) - center)
        + (vertical ? box.width : box.height) / 2 + 14 + depth / 2,
      ));
    }
    let box;
    const offsets = vertical
      ? [0, ...Array.from({ length: Math.ceil(L / 18) }, (_, i) => [-(i + 1) * 18, (i + 1) * 18]).flat()]
      : [0, -36, 36, -72, 72, -108, 108];
    // Try nearby slots within the region before adding an outward lane.
    do {
      for (const offset of offsets) {
        if (vertical && (u + offset < height / 2 || u + offset > L - height / 2)) continue;
        const [cx, cy] = geometry.map(u + offset, side * distance);
        box = { source, state, metrics, rows, lines, sharedMetrics, headerHeight, statusAge, side, anchor, x: cx - width / 2, y: cy - height / 2, width, height, columnWidth, labelWidth, vertical };
        if (![...obstacles, ...icons, ...boxes].some((other) => overlaps(box, other))) break;
      }
      distance += depth + 12;
    } while ([...obstacles, ...icons, ...boxes].some((other) => overlaps(box, other)));
    boxes.push(box);
  }
  return { boxes, icons, obstacles, bounds: drawingBounds(geometry, [...boxes, ...icons, ...obstacles], model) };
}

function powerReadingValue(metric, value) {
  if (metric === "enabled") return value === true ? "On" : value === false ? "Off" : STR.noData;
  if (metric === "charging") return value === true ? "Yes" : value === false ? "No" : STR.noData;
  return value ? `${value.text} ${value.unit}` : STR.noData;
}

function powerReadingText(metric, value, shore = false) {
  return `${powerMetricLabel(metric, shore)}: ${powerReadingValue(metric, value)}`;
}

/** Draw color-coded, keyboard-accessible source boxes instead of bottom tiles. */
export function renderPowerBoxes(hass, layout) {
  const icons = layout.icons.map(({ source, state, x, y, width }) => {
    const entity = powerStatusEntity(source, state) || source.voltage || source.current || source.charging
      || SHORE_READING_METRICS.map((metric) => source[metric]).find(Boolean);
    const action = entity ? `data-entity="${escapeHtml(entity)}" tabindex="0" role="button"` : 'role="img"';
    const label = `${source.name}: ${POWER_STATUS_LABELS[state.level]}`;
    return `<g class="power-icon power-${state.level}" data-source="${escapeHtml(source.key)}" ${action} aria-label="${escapeHtml(label)}" transform="translate(${x} ${y}) scale(${width / 24})">
      <title>${escapeHtml(label)}</title>${powerSymbol(source)}
      <rect class="equipment-badge" x="0" y="25" width="24" height="8" rx="3"></rect>
      <text class="equipment-tag" x="12" y="31" text-anchor="middle">${escapeHtml(powerTag(source))}</text>
    </g>`;
  }).join("");
  return icons + layout.boxes.map((box) => {
    const { source, state, metrics, rows, lines, sharedMetrics, headerHeight, x, y, width, height, columnWidth, labelWidth } = box;
    const shore = source.key === "shore_power";
    const sharedY = y + 24 + headerHeight + (rows.length - sharedMetrics.length) * 20;
    const name = `${powerTag(source)}: ${source.name}`;
    const status = POWER_STATUS_LABELS[state.level];
    const statusEntity = powerStatusEntity(source, state);
    const statusAction = statusEntity
      ? `data-entity="${escapeHtml(statusEntity)}" tabindex="0" role="button"` : "";
    return `<g class="power-box power-${state.level}" data-source="${escapeHtml(source.key)}">
      <title>${escapeHtml(`${name} (${POWER_LOCATION_LABELS[state.location]}): ${status}`)}</title>
      <rect class="power-bg" x="${x}" y="${y}" width="${width}" height="${height}" rx="10"></rect>
      <text class="chip-label" x="${x + 9}" y="${y + 13}">${escapeHtml(truncate(name,
        Math.min(22, Math.floor((width - 35 - (box.statusAge ? dataAgeWidth(box.statusAge) + 4 : 0)) / 5.5))))}</text>
      ${dataAgeLabel(box.statusAge, x + width - 26 - dataAgeWidth(box.statusAge), y + 13)}
      <g class="power-status" ${statusAction} aria-label="${escapeHtml(`${source.name}: ${status}`)}">
        <title>${escapeHtml(status)}</title>
        <rect class="hit" x="${x + width - 22}" y="${y}" width="22" height="22"></rect>
        <circle class="dot" cx="${x + width - 11}" cy="${y + 10}" r="4"></circle>
      </g>
      ${lines.map((prefix, column) =>
        `<text class="chip-label" x="${x + 9 + labelWidth + column * columnWidth}" y="${y + 30}">Line ${prefix ? 2 : 1}</text>`).join("")}
      ${sharedMetrics.length ? `<path class="shore-divider" d="M${x + 9} ${sharedY} H${x + width - 9}"></path>
        <text class="chip-label" x="${x + 9}" y="${sharedY + 14}">Combined</text>` : ""}
      ${!metrics.length && !sharedMetrics.length ? `<text class="small" x="${x + 9}" y="${y + 34}">No readings mapped</text>` : ""}
      ${rows.map((row, rowIndex) => {
        const firstMetric = row.find(Boolean);
        const rowY = y + 32 + headerHeight + rowIndex * 20
          + (sharedMetrics.includes(firstMetric) ? 20 : 0);
        return `<text class="small power-label" x="${x + 9}" y="${rowY}" ${row.length === 1 ? readingAction(source[firstMetric]) : ""}>${escapeHtml(
          powerMetricLabel(firstMetric, shore).replace(/^Line [12] /, ""))}</text>`
          + row.map((metric, column) => {
            if (!metric) return "";
            const text = powerReadingText(metric, state[metric], shore);
            const rowX = x + 9 + labelWidth + column * columnWidth;
            const age = missingReadingText(hass, [source[metric]]);
            const measurement = metric !== "charging" && metric !== "enabled";
            const value = measurement && state[metric]
              ? `<tspan class="mid">${escapeHtml(state[metric].text)}</tspan><tspan class="unit" dx="2">${escapeHtml(state[metric].unit)}</tspan>`
              : `<tspan class="small row-right">${escapeHtml(powerReadingValue(metric, state[metric]))}</tspan>`;
            return `<g data-entity="${escapeHtml(source[metric])}" tabindex="0" role="button" aria-label="${escapeHtml(`${source.name}: ${text}`)}">
              <title>${escapeHtml(text)}</title>
              <rect class="hit" x="${rowX - 4}" y="${rowY - 13}" width="${columnWidth - 2}" height="16"></rect>
              <text class="power-value" x="${rowX}" y="${rowY}">${value}</text>
              ${dataAgeLabel(age, rowX + STR.noData.length * 5.5 + 4, rowY)}
            </g>`;
          }).join("");
      }).join("")}
    </g>`;
  }).join("");
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
  .drawing { overflow: auto; max-height: 80vh; }
  svg.vehicle { width: 100%; height: auto; display: block;
    font-family: var(--ha-font-family-body, inherit); }
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
  .axle { stroke: color-mix(in srgb, var(--hv-text) 45%, var(--hv-card)); stroke-width: 6;
    stroke-linecap: round; }
  .tow-outline { fill: none; stroke: var(--hv-text); stroke-width: 2; }
  .tow-label { paint-order: stroke; stroke: var(--hv-card); stroke-width: 3px;
    stroke-linejoin: round; }
  .tow-outline [data-entity]:focus-visible { stroke: var(--primary-color, #03a9f4); stroke-width: 3; }
  .tow-label:focus-visible { text-decoration: underline; }
  .tire rect, .equipment-shell { fill: color-mix(in srgb, var(--lvl) 82%, #000); stroke: color-mix(in srgb, var(--lvl) 60%, #000);
    stroke-width: 1.5; }
  .tire .tread { stroke: rgba(0, 0, 0, 0.28); stroke-width: 2; }
  .tire.ghost rect, .power-unknown .equipment-shell { fill: transparent; stroke: var(--hv-offline); stroke-dasharray: 4 3; }
  .tire.ghost .tread { display: none; }
  .ok { --lvl: var(--hv-ok); }
  .watch { --lvl: var(--hv-watch); }
  .alert { --lvl: var(--hv-alert); }
  .offline { --lvl: var(--hv-offline); }
  .chip-bg, .power-bg { fill: color-mix(in srgb, var(--lvl, var(--hv-offline)) 7%, var(--hv-card));
    stroke: color-mix(in srgb, var(--lvl, var(--hv-offline)) 55%, transparent); stroke-width: 1.5; }
  .chip.ok .chip-bg, .power-on .power-bg { stroke: var(--hv-line); }
  .chip-bg.ghost { fill: transparent; stroke: var(--hv-line); stroke-dasharray: 4 4; }
  text { fill: var(--hv-text); font-size: 12px; }
  .chip-label { fill: var(--hv-muted); font-size: 9px; font-weight: 600; letter-spacing: 0.06em;
    text-transform: uppercase; }
  .big { font-size: 19px; font-weight: 700; }
  .mid { font-size: 14px; font-weight: 700; }
  .unit { fill: var(--hv-muted); font-size: 9.5px; font-weight: 500; }
  .small { fill: var(--hv-muted); font-size: 10.5px; }
  .tiny { fill: var(--hv-muted); font-size: 9px; }
  .data-age { color: var(--hv-muted); }
  .data-age text { fill: var(--hv-muted); font-size: 9px; }
  .tank-label .data-age text { font-size: 7px; }
  .age-clock { fill: none; stroke: currentColor; stroke-width: 1; stroke-linecap: round; stroke-linejoin: round; }
  .muted { fill: var(--hv-muted); }
  .flag { fill: var(--lvl); font-size: 8.5px; font-weight: 700; letter-spacing: 0.04em; }
  .wheel { fill: var(--lvl); font-size: 9.5px; font-weight: 700; }
  .trend { fill: var(--lvl); font-size: 8.5px; }
  .hot { fill: var(--hv-alert); }
  .row-right { font-size: 10px; }
  .dot { fill: var(--lvl); }
  .hit { fill: transparent; }
  .shore-divider { fill: none; stroke: var(--hv-line); stroke-width: 1; }
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
  .tank-pct.aged { font-size: 10px; }
  .tank-vol { fill: var(--hv-muted); font-size: 10px; font-weight: 500; }
  .compact-tank .tank-name { font-size: 8px; }
  .compact-tank .tank-pct { font-size: 9px; }
  .compact-tank .tiny { font-size: 7px; }
  .small-lane { font-size: 10px; }
  .tank-label.watch .tank-pct, .tank-label.alert .tank-pct { fill: var(--lvl); }
  [data-entity] { cursor: pointer; }
  [data-entity]:focus { outline: none; }
  text[data-entity]:focus-visible, tspan[data-entity]:focus-visible { outline: 2px solid var(--primary-color, #03a9f4); }
  [data-entity]:focus-visible .chip-bg, .chip [data-entity]:focus-visible .hit,
  .chip[data-entity]:focus-visible .chip-bg { stroke: var(--primary-color, #03a9f4); stroke-width: 2.5; }
  .chip.alert .chip-bg, .power-problem .power-bg, .power-problem .equipment-shell, .tire.alert rect, .tank.alert .tank-frame { animation: hv-pulse 1.6s ease-in-out infinite; }
  @keyframes hv-pulse { 50% { stroke-opacity: 0.35; } }
  @media (prefers-reduced-motion: reduce) {
    .chip.alert .chip-bg, .power-problem .power-bg, .power-problem .equipment-shell, .tire.alert rect, .tank.alert .tank-frame { animation: none; }
  }
  .legend { display: flex; justify-content: center; gap: 14px; flex-wrap: wrap;
    font-size: 0.75em; color: var(--hv-muted); }
  .legend span { display: inline-flex; align-items: center; gap: 5px; }
  .legend i { width: 9px; height: 9px; border-radius: 50%; background: var(--lvl); display: inline-block; }
  .power-on { --lvl: var(--hv-ok); }
  .power-off, .power-unknown { --lvl: var(--hv-offline); }
  .power-warning { --lvl: var(--hv-watch); }
  .power-problem { --lvl: var(--hv-alert); }
  .power-icon.power-on { --lvl: var(--hv-ok); }
  .equipment-shell { fill: color-mix(in srgb, var(--lvl) 24%, var(--hv-card)); stroke: var(--lvl); }
  .equipment-energy { fill: var(--lvl); stroke: none; }
  .equipment-detail { fill: none; stroke: var(--hv-text); stroke-width: 1.5;
    stroke-linecap: round; stroke-linejoin: round; }
  .power-unknown .equipment-detail { stroke: var(--hv-muted); }
  .power-icon:focus-visible .equipment-shell { stroke: var(--primary-color); stroke-width: 2.5; }
  .power-unknown .power-bg { stroke-dasharray: 4 3; }
  .power-unknown .dot { fill: none; stroke: var(--lvl); stroke-width: 1.5; stroke-dasharray: 2 1; }
  .equipment-badge { fill: var(--hv-card); stroke: var(--lvl); stroke-width: 0.6; }
  .equipment-tag { fill: var(--hv-text); font-size: 5px; font-weight: 700; }
  .power-legend i { border: 1px solid var(--hv-line); }
  .power-legend.power-unknown i { border-style: dashed; border-color: var(--hv-text); }
  .power-box [data-entity]:focus-visible .hit { stroke: var(--primary-color); stroke-width: 2; }
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
    this._readingHistory = new Map();
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
            ...Object.entries(DISPLAY_CLASSES).map(([name, group]) =>
              ({ name, default: group.default, selector: { boolean: {} } })),
          ],
        },
      ],
      computeLabel: (schema) => DISPLAY_CLASSES[schema.name]?.label || STR.form[schema.name],
    };
  }

  static getStubConfig(hass) {
    const rv = findRvDevices(hass)[0];
    return { ...dashboardOptions(), ...(rv ? { device_id: rv.id } : {}) };
  }

  setConfig(config) {
    if (!config || typeof config !== "object") throw new Error("Invalid configuration");
    if (config.layout && !LAYOUTS.includes(config.layout)) {
      throw new Error(`layout must be one of: ${LAYOUTS.join(", ")}`);
    }
    this._config = { ...config, ...dashboardOptions(config) };
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
        this._scheduleFit();
      });
    }
    this._resizeObserver?.observe(this);
    if (!this._ageTimer) {
      this._ageTimer = setInterval(() => this._update(), 30000);
      this._ageTimer.unref?.();
    }
    this._scheduleFit();
  }

  disconnectedCallback() {
    this._resizeObserver?.disconnect();
    clearInterval(this._ageTimer);
    this._ageTimer = undefined;
    cancelAnimationFrame(this._fitFrame);
  }

  _resolveOrientation() {
    if (this._config.layout !== "auto") return this._config.layout;
    return this._width && this._width < VERTICAL_BREAKPOINT ? "vertical" : "horizontal";
  }

  _update() {
    if (!this._config || !this._hass) return;
    const hass = this._hass;
    const rv = resolveRvDevice(hass, this._config.device_id);
    const model = rv ? visibleModel(buildModel(hass, rv), this._config) : undefined;
    if (model) {
      const readings = [
        ...model.axles.flatMap((axle) => [...axle.left, ...axle.right]
          .flatMap((tire) => [tire.pressure, tire.temperature, tire.battery])),
        ...model.tanks.flatMap((tank) => [tank.percentage, tank.level]),
        ...model.powerSources.flatMap((source) => [...SHORE_READING_METRICS,
          "enabled", "charging", "warning", "problem"].map((metric) => source[metric])),
      ].filter(Boolean);
      const current = new Set(readings);
      for (const id of this._readingHistory.keys()) {
        if (!current.has(id)) this._readingHistory.delete(id);
      }
      rememberReadings(hass, readings, this._readingHistory);
    }
    const orientation = this._resolveOrientation();
    const key = JSON.stringify([
      orientation,
      this._config,
      hass.locale?.language,
      hass.themes?.darkMode,
      Math.floor(Date.now() / 30000),
      model && {
        name: model.name,
        axles: model.axles,
        tanks: model.tanks,
        powerSources: model.powerSources,
        tow: model.tow,
        mode: model.operationMode,
      },
      model?.watched.map((id) => {
        const state = hass.states[id];
        return state ? [state.state, state.attributes.unit_of_measurement, state.last_reported, state.last_updated] : null;
      }),
    ]);
    if (key === this._renderKey) return;
    this._renderKey = key;
    this._orientation = orientation;
    this.shadowRoot.innerHTML = `<style>${STYLES}</style><ha-card>${
      model ? this._renderModel(model, orientation) : `<div class="wrap"><div class="message">${escapeHtml(STR.noProfile)}</div></div>`
    }</ha-card>`;
    this._scheduleFit();
  }

  /**
   * Keep dual-chip rows from colliding: drop the chip's pressure units first,
   * then shorten temperatures to the compact form only if still needed.
   */
  _fitRows() {
    if (!this.isConnected) return;
    const rowsCollide = (chip) =>
      [...chip.querySelectorAll(".row")].some((row) => {
        const pressure = row.querySelector(".row-pressure");
        const right = row.querySelector(".row-right");
        if (!pressure?.getBBox || !right?.textContent) return false;
        const box = pressure.getBBox();
        return box.width > 0 && box.x + box.width + 4 > right.getBBox().x;
      });
    for (const chip of this.shadowRoot.querySelectorAll(".chip")) {
      if (!rowsCollide(chip)) continue;
      chip.querySelectorAll(".row-pressure .unit").forEach((unit) => unit.remove());
      if (!rowsCollide(chip)) continue;
      chip.querySelectorAll(".row-right [data-compact]").forEach((text) => {
        text.textContent = text.dataset.compact;
      });
    }
  }

  _scheduleFit() {
    cancelAnimationFrame(this._fitFrame);
    this._fitFrame = requestAnimationFrame(() => this._fitRows());
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
    const summary = summarize(hass, model, this._config.show_power);
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
    const hasPower = this._config.show_power && (model.powerSources || []).some((source) =>
      POWER_LOCATION_LABELS[powerState(this._hass, source).location]);
    const legend = [
      ["ok", hasPower ? "OK / On" : STR.legendOk],
      ["watch", hasPower ? "Watch / Warning" : STR.legendWatch],
      ["alert", hasPower ? "Alert / Problem" : STR.legendAlert],
      ...(hasPower ? [["offline", "Off"]] : []),
      [hasPower ? "power-legend power-unknown" : "offline", STR.legendOffline],
    ]
      .map(([level, label]) => `<span class="${level}"><i></i>${label}</span>`)
      .join("");
    const svg = renderVehicle(this._hass, model, orientation, this._uid, this._config.show_power).replace(
      'class="vehicle"',
      `class="vehicle ${orientation}"`,
    );
    return `<div class="wrap">
      ${this._config.show_header ? this._renderHeader(model) : ""}
      <div class="drawing" tabindex="0" role="region" aria-label="RV diagram">${svg}</div>
      ${!this._config.show_tires || model.axles.length ? "" : `<div class="message">${escapeHtml(STR.noTires)}</div>`}
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
export function rvView(hass, rv, config = {}) {
  const options = dashboardOptions(config);
  const model = visibleModel(buildModel(hass, rv), options);
  const sections = [
    {
      type: "grid",
      column_span: 4,
      cards: [{ type: `custom:${CARD_TYPE}`, device_id: rv.id, ...options }],
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
  if (config.show_power !== false) {
    for (const source of model.powerSources) {
      if (!source.entities.length) continue;
      sections.push({
        type: "grid",
        cards: [heading(source.name, source.key.startsWith("house_bank_") || source.key.startsWith("chassis_bank_") ? "mdi:battery" : "mdi:flash"),
          { type: "entities", entities: source.entities, state_color: false }],
      });
    }
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
  static async generate(config, hass) {
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
        return { ...rvView(hass, rv, config), title: deviceName(rv) || "RV", path, icon: "mdi:rv-truck" };
      }),
    };
  }
}

export class HavrvViewStrategy extends HTMLElement {
  static async generate(config, hass) {
    const rv = resolveRvDevice(hass, config?.device_id);
    return rv ? rvView(hass, rv, config) : emptyView();
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
