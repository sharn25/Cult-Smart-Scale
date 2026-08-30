# Cult Smart Scale — Automation Recipes & iOS Shortcut Guide 🚀

The **Cult Smart Scale** integration fires standardized Home Assistant events whenever a weigh-in occurs. This allows you to easily trigger iOS Shortcuts, log metrics to Apple Health, send rich push notifications, or run custom automations.

---

## 📡 Event Details

Whenever a measurement is finalized, the integration fires:
- **`cult_smart_scale_reading_received`**: When assigned to a user (Automatic matching OR Manual assignment).
- **`cult_smart_scale_unassigned_reading`**: When an unknown person/guest steps on the scale.

### Event Data Fields Available in Templates:

| Variable | Description | Example |
|---|---|---|
| `trigger.event.data.user_name` | Name of the person | `"<person_name>"` |
| `trigger.event.data.user_id` | Unique user profile ID | `"<person_slug>"` |
| `trigger.event.data.person_entity` | Associated person entity | `"person.<name>"` |
| `trigger.event.data.weight_kg` | Stabilized Weight in kg | `72.4` |
| `trigger.event.data.bmi` | Body Mass Index | `21.6` |
| `trigger.event.data.body_fat_percentage` | Body Fat % | `21.7` |
| `trigger.event.data.muscle_mass_kg` | Muscle Mass in kg | `55.5` |
| `trigger.event.data.skeletal_muscle_kg` | Skeletal Muscle in kg | `40.0` |
| `trigger.event.data.water_percentage` | Total Body Water % | `56.5` |
| `trigger.event.data.bone_mass_kg` | Bone Mass in kg | `4.9` |
| `trigger.event.data.bmr_kcal` | Basal Metabolic Rate | `1750` |
| `trigger.event.data.visceral_fat_level` | Visceral Fat Level | `3` |
| `trigger.event.data.body_age` | Metabolic Body Age | `30` |
| `trigger.event.data.heart_rate_bpm` | Heart Rate in BPM | `70` |
| `trigger.event.data.body_type` | Body Composition Classification | `"Standard"` |
| `trigger.event.data.battery_level` | Scale Battery % | `85` |

---

## 📱 Recipe 1: iOS Push Notification with Direct Shortcut Trigger (Automatic Mode)

When you finish weighing in, your iPhone receives a push notification. Tapping the notification automatically launches your iOS Shortcut to write the data into Apple Health!

```yaml
alias: "Cult Scale: Sync Weigh-In to iOS / Apple Health"
description: "Sends push notification to iPhone for running iOS Shortcut."
trigger:
  - platform: event
    event_type: cult_smart_scale_reading_received
    event_data:
      user_name: "person.<person_name>" # Set your user id
condition: []
actions:
  - action: notify.mobile_app_<your_iphone>
    metadata: {}
    data:
      title: "⚖️ Scale: {{ trigger.event.data.weight_kg }} kg"
      message: >-
        Weight: {{ trigger.event.data.weight_kg }} kg {% if
        trigger.event.data.impedance_ohms %} (Impedance: {{
        trigger.event.data.impedance_ohms }} Ω) {% endif %} {% if
        trigger.event.data.heart_rate_bpm %} (Heart Rate: {{
        trigger.event.data.heart_rate_bpm }} BPM) {% endif %}. Tap the Message to record.
      data:
        shortcut:
          name: Log Scale to Apple Health
          input: text
          text: >-
            Tested{"weight":"{{ trigger.event.data.weight_kg }}","body_fat":"{{
            trigger.event.data.body_fat_percentage }}","bmi":"{{
            trigger.event.data.bmi }}","heart_rate":"{{
            trigger.event.data.heart_rate_bpm }}"}
          ignore_result: ignore
mode: single
```

### iOS Shortcut for Apple HealthSync
Following shortcuts can be imported directy to use with the Automation.
👉 **[Download "Log Scale to Apple Health" Shortcut](https://www.icloud.com/shortcuts/69e95acda5fd4ac39de441af4ed3b8aa)**

---

## ❓ Recipe 2: Unassigned Weigh-In Notification with Action Buttons (Manual Mode)

If an unknown person steps on the scale, send a notification to your phone with quick action buttons to assign the reading with one tap:

```yaml
alias: "Cult Scale: Unassigned Weigh-In Confirmation"
trigger:
  - platform: event
    event_type: cult_smart_scale_unassigned_reading
actions:
  - service: notify.mobile_app_<your_iphone>
    data:
      title: "⚖️ Unassigned Weigh-In: {{ trigger.event.data.weight_kg }} kg"
      message: "Who stepped on the scale?"
      data:
        actions:
          - action: "ASSIGN_MEMBER_1"
            title: "<person_name>"
          - action: "ASSIGN_MEMBER_2"
            title: "<person_name>"
          - action: "ASSIGN_GUEST"
            title: "Guest (Ignore)"
```

And handle the button tap with:

```yaml
alias: "Cult Scale: Handle Unassigned Button Tap"
description: Assigns scale reading based on button pressed in mobile notification.
triggers:
  - event_type: mobile_app_notification_action
    event_data:
      action: ASSIGN_MEMBER_1
    id: member1
    trigger: event
  - event_type: mobile_app_notification_action
    event_data:
      action: ASSIGN_MEMBER_2
    id: member2
    trigger: event
actions:
  - choose:
      - conditions:
          - condition: trigger
            id: member1
        sequence:
          - data:
              user_id: <Person_Name>
            action: cult_smart_scale.assign_reading
      - conditions:
          - condition: trigger
            id: member2
        sequence:
          - data:
              user_id: <Person_Name>
            action: cult_smart_scale.assign_reading
```

