# HAVRV dashboard

HAVRV includes an RV overview card and a dashboard generated from your RV
profile. Both are installed with the integration. You do not need a separate
HACS frontend download or a Lovelace resource.

![Horizontal HAVRV overview with tires, tanks, placed battery banks and AC sources](images/dashboard-horizontal.png)

These rendered examples use synthetic source readings, not a particular RV's
specifications or wiring. Enabled and Charging are independently mapped.

The card draws your RV from above. It shows every configured wheel with its
pressure and temperature, and every configured water tank with its fill level.
The layout follows the RV profile:

- A front axle, then one to three rear axles, each with single or dual wheels.
- An optional tag axle, drawn behind the drive axles.
- Dual positions show outer (**O**) and inner (**I**) readings on one label.
- Only the fresh, gray, and black water tanks that you configured are drawn.
- Optionally placed house/chassis banks, Inverter and Generator are marked in
  their selected left/right front/mid/rear regions. Shore Power is outside the
  RV on the selected side. **HB1/CB1** identify bank 1, **INV** the logical
  inverter, **GEN** the generator, and **S** the external shore connection.
  Sources in the same region share a numbered marker showing the count of
  colocated devices, to avoid overlapping banks. Hover for source names/readings.
  Individual readouts beneath the drawing show mapped voltage, current,
  Enabled and bank Charging; selecting a reading opens its details.
- Wide cards draw the RV horizontally, with the front on the right. Cards
  narrower than about 560 pixels, such as on phones, draw it vertically with
  the front at the top.

<img src="images/dashboard-vertical.png" alt="Vertical HAVRV card in a dark theme" width="320">

## Configure electrical placement on an existing RV

1. Open **Settings → Devices & services → HAVRV** and the RV entry's
   **Configure/Options** action.
2. Select **Edit power-source mappings, specifications and placement** on
   the initial options form, then submit.
3. Set **Dashboard placement** on each bank, Inverter, Generator, and Shore
   Power screen. Choose one of the six interior regions; shore uses left/right
   outside. Left/right are viewed facing forward.
4. Submit every screen to save. Cancelling the wizard leaves prior settings
   unchanged. **Reconfigure** changes bank counts, not placement.

Placement defaults to **Not shown**. The overview only draws placed sources;
the generated dashboard can still include unplaced source-device sections.
Colocated devices share a numbered marker and retain individual readouts below
the drawing. You do not enter physical positions in dashboard YAML.

The card's visual editor has **Show placed power sources** alongside
**Show header** and **Show legend**. If that toggle is absent, the browser has
an older module: update/restart HAVRV, remove any old manually added HAVRV
dashboard resource, and reset the browser/app cache. See the
[troubleshooting steps](TROUBLESHOOTING.md#the-power-toggle-or-placed-electrical-devices-are-missing).

Readings use the units shown by the HAVRV entities, so they follow your RV
profile's measurement system and any unit you set on an entity. Select a wheel,
tank, or the operation mode to open its details.

## Status colors

Colors come from the HAVRV problem and trend entities. The card does not apply
its own limits.

| Color | Tires | Tanks |
| --- | --- | --- |
| Green | Pressure reading available and no problem reported | **Tank status** is OK |
| Amber (watch) | **Slow pressure loss** or **Battery problem** is on | **Tank status** is Warning |
| Red (alert) | **Sudden pressure drop**, **Pressure problem**, or **Temperature problem** is on | **Tank status** is Problem |
| Gray (no data) | No pressure reading | No percentage reading |

A wheel with a pressure reading but no temperature or battery source is still
shown as green. Tire labels also show **▼** for a pressure-loss trend, **HOT**
for a temperature problem, and **BAT** for a low sensor battery. On dual-wheel
labels, **▼** and **BAT** appear beside the label's title, and a temperature
problem colors that wheel's temperature red. If a dual-wheel label is too
narrow for its readings, the pressure unit is left out for that label.

The header shows the RV name, its year, manufacturer, and model, the operation
mode, and counts of alerts, items to watch, and readings with no data.

## Create the RV dashboard

1. Go to **Settings → Dashboards** and select **Add dashboard**.
2. Choose **New dashboard from scratch** and give it a name, such as **RV**.
3. Open the new dashboard, select the pencil icon, then the three-dot menu, and
   choose **Raw configuration editor**.
4. Replace the contents with:

   ```yaml
   strategy:
     type: custom:havrv
     show_power: true
   ```

5. Save and close the editor.

The dashboard creates one view for each RV profile. Each view contains:

- The RV overview card.
- **Coach**: the operation-mode selector and the RV profile sensors.
- **Tanks**: fill percentage and the last filled or emptied time for each tank.
- **Tire analysis**: All Tire Monitor comparisons, when tires are configured.
- One section for each system device with mapped entities.
- Individual power-source sections, including configured nominal bank
  specifications and read-only statuses. Sources without physical placement
  still appear here. Set `show_power: false` on the strategy to omit these
  sections and overview power markers/readouts.

Power sources have no advisory OK/alert colors. Enabled is not active supply,
and Charging is shown only from an explicit bank source. Neither status changes
the tire/tank alert summary or creates power-flow arrows.

The dashboard updates itself when you change the RV profile, add tanks, or map
entities. To customize it, open the dashboard's three-dot menu and choose
**Take control**. This converts the generated layout into a regular dashboard
that no longer updates itself.

### Add an RV view to an existing dashboard

Add a view with the view strategy. Set `device_id` to the RV device, or to any
of its HAVRV devices, to choose the RV when you have more than one profile.

```yaml
views:
  - title: RV
    path: rv
    icon: mdi:rv-truck
    strategy:
      type: custom:havrv
      device_id: 0123456789abcdef0123456789abcdef
      show_power: true
```

To find a device ID, open the device in **Settings → Devices & services**. The
ID is the last part of the page address.

## Add the card to any dashboard

In dashboard edit mode, select **Add card** and search for
**HAVRV RV overview**. The visual editor offers these options:

| Option | Default | Description |
| --- | --- | --- |
| `device_id` | First RV profile | The RV device, or any of its HAVRV devices |
| `layout` | `auto` | `auto`, `horizontal`, or `vertical` |
| `show_header` | `true` | Show the name, operation mode, and status summary |
| `show_legend` | `true` | Show the status color legend |
| `show_power` | `true` | Show placed power-source markers and individual readouts |

```yaml
type: custom:havrv-rv-card
device_id: 0123456789abcdef0123456789abcdef
layout: auto
show_power: true
```

In a sections view, the card spans the full width of its section.
`show_power` defaults to `true`; it enables placed markers and readouts on the
card, and also electrical-device sections when used on a strategy. There is
no separate electrical strategy. If you previously selected **Take control**,
your static dashboard does not automatically gain new generated sections; add
the current card or a strategy view without replacing other views.

## How the layout is found

The card reads the Home Assistant device and entity registries. HAVRV device
identifiers name each tire position and tank, and entity translation keys
identify each reading, so renamed entity IDs and devices still work. Entities
you hide are left out of the generated dashboard sections, but tire and tank
readings stay on the card.
Power-source identities encode the bank/device, while a diagnostic placement
sensor supplies its region. No source entity names or RV-specific wiring are
assumed.

The tire problem and trend states are advisory. Follow the vehicle and tire
manufacturers' guidance.
