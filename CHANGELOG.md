# Changelog

## Unreleased

## 0.4.2

- Remove HAVRV tank sensors and empty tank devices when both capacity and level
  source are cleared. Repair leftovers from older versions on setup/reload.
- Keep capacity-only and source-only tanks, including unavailable sources;
  thresholds alone do not define a tank. Remove stale capacity sensors when
  the capacity is cleared but a source remains.
- Exclude empty leftover tank devices from the dashboard and generated views.
  Include tank removal in the management page's impact confirmation.
- Preserve source entities, other RV profiles, and unrelated device entities.
  Re-adding a removed tank may require restoring device customizations and
  updating automations referencing the removed HAVRV device or entities.

## 0.3.2

- Keep tire pressure and temperature on the same line for both single and dual
  wheels, with independent no-data handling and compact unit fitting.
- Stress-test colocated R-Rear equipment in both orientations, improve interior
  slot/readout packing, and add rendered crowded-placement examples.
- Move electrical readouts into individual location-based boxes beside the RV,
  avoiding tire labels and other sources, including colocated battery banks.
- Add optional read-only Warning and Problem source mappings for every power
  device. Tire-style status dots and translucent tints are green/gray for
  Enabled on/off, amber/red for explicit warning/problem, and dashed with a
  hollow dot for unknown status; no thresholds are inferred. Match tire-label
  fonts, font sizes, and reduced-motion-aware alert outlines.
- Add distinct battery, generator, inverter and external shore-plug graphics
  linked to their readouts. Apply tire-style status colors and avoid overlapping
  graphics, including dense colocated banks.
- Enlarge equipment graphics to a tire-comparable footprint, replace crossing
  callout lines with matching equipment tags, remove Enabled Yes/No rows, and
  consolidate electrical/tire/tank status keys into one common legend.
- Include placed electrical alerts in the header summary and add an electrical
  legend. Refresh setup/dashboard guides and both rendered dashboard images.

## 0.3.1

- Invalidate cached dashboard JavaScript using its content revision, including
  frontend-only updates at the same integration version.
- Replace the stale repository-root card with a compatibility loader for the
  integration's canonical module. Old manually copied frontend resources
  should be removed from dashboard Resources.
- Document electrical placement, the Show placed power sources toggle,
  dashboard/view/card YAML, and upgrade troubleshooting. Refresh the horizontal
  and vertical dashboard images with independent banks and electrical readings.

## 0.3.0

- Add independent house/chassis battery banks and logical Inverter, Generator,
  and Shore Power devices. Bank counts default to one each, nominal voltage
  defaults to 24 V DC (12/24/48 selectable), and capacity is optional in Ah.
- Add declared read-only voltage/current/Enabled mappings and independent
  bank Charging mappings, with optional dashboard placement and source sections.
  Do not infer charging, active supply, or electrical wiring.

- Add editable dimensions, capacities, and tank/tire limits to Configuration on
  the main RV device, sharing saved values and validation with the forms.
  Move other profile details to read-only Diagnostics. Main-device dimension
  and fuel-capacity sensor entities are replaced by number entities.
- Link tank devices to the RV device with `via_device_id`, removing the
  deprecated `via_device` usage that stops working in Home Assistant 2027.8.0.

- Add an RV overview card and generated RV dashboard and view strategies,
  served by the integration. They draw the configured axles, single or dual
  wheels, and water tanks with live tire and tank status.
- Add an Operations device with a restorable operation-mode selector.
- Add consistent, field-specific icons to RV profile sensors.
- Expose saved RV profile specifications as sensors on the RV device.
- Add RV and system devices, configurable source-entity mappings, mirrored
  sensor entities, and action-forwarding switch, light, and climate entities.
- Add the initial HACS custom integration foundation and named RV config flow.
