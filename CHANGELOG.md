# Changelog

## Unreleased

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
