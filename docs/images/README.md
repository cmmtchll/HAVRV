# Dashboard illustrations

These PNGs illustrate the bundled
[`havrv-dashboard.js`](../../custom_components/havrv/frontend/havrv-dashboard.js)
card using synthetic Home Assistant device/entity registries and states.
They contain no connected-vehicle data. Equipment placement, readings, weight,
and advisory states are examples, not recommended vehicle specifications.

| Image | Scenario |
| --- | --- |
| [Horizontal overview](dashboard-horizontal.png) | Front on the right; Towing on with Car selected and 3,500 lb entered |
| [Vertical overview](dashboard-vertical.png) | Front at the top; the same profile, sources, and tow state |
| [Horizontal placement stress](dashboard-stress-horizontal.png) | Five independent electrical devices at R-Rear; Shore Power on R; Towing off |
| [Vertical placement stress](dashboard-stress-vertical.png) | The same crowded configuration in a vertical layout |
| [Horizontal tire trends](dashboard-tires-horizontal.png) | Tire-only synthetic current, six-hour-old offline, partial-temperature and never-seen readings; thin one-hour pressure lines and mapped reception ages |
| [Vertical tire trends](dashboard-tires-vertical.png) | The same tire states, one data line per inner/outer wheel, with a recorded outage gap in the right inner pressure trace |

All scenarios include a front axle, a dual-wheel rear axle, and a single-wheel tag
axle. The overview/placement scenarios also include three water tanks,
two house battery banks, one chassis bank, an inverter,
a generator, and two-line shore power with shared energy. HB2 has an explicitly
mapped warning and the inverter an explicitly mapped problem; these are not
calculated from the example electrical readings. The stress examples make one
rear tire temperature and HB2 current unavailable without hiding their other
readings. A clock with `?` means no valid report has been observed by that card.

## Refreshing the pictures

Render the current bundled custom element in a browser with synthetic `hass`
registries and states, using HAVRV device identifiers and entity translation
keys rather than relying on entity names. Supply a dark Home Assistant-style
card shell and theme variables; the drawing and readouts must come from the
unmodified bundled card, not a hand-drawn recreation.

Capture the whole card in both explicit orientations, with reduced motion
enabled and enough viewport space to avoid cropping internally scrolled
content. These are expanded diagram illustrations, not phone-size screenshots;
actual small cards can scroll. For the overview/placement pairs, check that all six electrical boxes, both shore
columns, the combined energy/status rows, and the legend are visible. Check
that towing appears only in the overview pair and missing-data indicators only
in the stress pair. For the tire-only pair, supply mapped timestamp sources,
last-valid value/unit/source/time metadata, and compressed one-hour history with
an explicit unavailable gap. Include live, old/offline, partly available and
never-seen tires, and verify that pressure, temperature and age share one
baseline without overlap in every single/dual row. Review both orientations
and update the captions in the
[README](../../README.md) and [dashboard guide](../DASHBOARD.md) together.
