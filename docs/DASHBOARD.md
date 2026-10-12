# HAVRV dashboard

HAVRV includes an RV overview card and a dashboard generated from your RV
profile. Both are installed with the integration. You do not need a separate
HACS frontend download or a Lovelace resource.

![HAVRV RV overview card](images/dashboard-horizontal.png)

The card draws your RV from above. It shows every configured wheel with its
pressure and temperature, and every configured water tank with its fill level.
The layout follows the RV profile:

- A front axle, then one to three rear axles, each with single or dual wheels.
- An optional tag axle, drawn behind the drive axles.
- Dual positions show outer (**O**) and inner (**I**) readings on one label.
- Only the fresh, gray, and black water tanks that you configured are drawn.
- Wide cards draw the RV horizontally, with the front on the right. Cards
  narrower than about 560 pixels, such as on phones, draw it vertically with
  the front at the top.

<img src="images/dashboard-vertical.png" alt="Vertical HAVRV card in a dark theme" width="320">

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
for a temperature problem, and **BAT** for a low sensor battery.

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
   ```

5. Save and close the editor.

The dashboard creates one view for each RV profile. Each view contains:

- The RV overview card.
- **Coach**: the operation-mode selector and the RV profile sensors.
- **Tanks**: fill percentage and the last filled or emptied time for each tank.
- **Tire analysis**: All Tire Monitor comparisons, when tires are configured.
- One section for each system device with mapped entities.

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

```yaml
type: custom:havrv-rv-card
device_id: 0123456789abcdef0123456789abcdef
layout: auto
```

In a sections view, the card spans the full width of its section.

## How the layout is found

The card reads the Home Assistant device and entity registries. HAVRV device
identifiers name each tire position and tank, and entity translation keys
identify each reading, so renamed entity IDs and devices still work. Entities
you hide are left out of the generated dashboard sections, but tire and tank
readings stay on the card.

The tire problem and trend states are advisory. Follow the vehicle and tire
manufacturers' guidance.
