# Home Assistant task guide

Read the relevant section for the current task. This local guide supplements
ha-tools.md; it does not replace the MCP ha_get_skill_guide best-practices guide.

# Home Assistant configuration and scheduled actions

You can create and edit automations through the configured home-assistant-config
MCP. Its automation create/read/remove tools and ha_get_skill_guide are direct
tools; call them directly. Other configuration tools remain available through
Code Mode search and execute. Read ha_get_skill_guide before configuration writes.
The OpenCode skill catalogue is not the HA best-practices guide.

A request to act later authorizes scheduling, not acting immediately. Resolve
the device with read-only tools, obtain HA's current date/time when needed, and
calculate the requested due date/time in its timezone, preserving seconds.
For a relative delay, add the full duration to that timestamp; do not round to
a whole minute. Use code or HA template evaluation for the calculation.
Pass the guide's current acknowledgment key as BestPracticeKey on gated writes.
Create an identifiable
one-time HA automation for that exact date/time, with the requested action and
self-disabling behavior after execution. A clock-time trigger needs a date guard so a missed run cannot execute on
another day. Do not create a recurring daily action for a one-time request. Do not run its actions during creation or keep a model
request sleeping until it is due.

Read back the saved configuration and verify it is enabled before confirming
that it is scheduled. If the deadline has passed, clarify rather than act now
or silently move it to another day. If creation fails, report that it was not
scheduled. To cancel, disable or remove only the specific pending automation;
never cancel unrelated timers or change other automations. Completed one-time
automations may remain disabled for inspection; remove those when requested.

# Complete integration and camera discovery

GetLiveContext searches only Assist-exposed entities. No match there does not
mean a device, camera or integration is absent from Home Assistant. For cameras,
Ring devices, missing devices or integration configuration, use the direct
ha_get_device tool with integration (e.g. "ring") and detail_level="full".
This lists the integration's devices and entities, including registry-disabled
entities. Use ha_get_entity for exact registry entries/disabled_by and
ha_get_integration to check integration setup. Follow pagination when needed.
Do not ask the user whether an integration is installed until these registry
reads have been tried. Never scan local files to discover a remote HA deployment.
Distinguish live-view cameras from last-recording cameras, a still snapshot from
a recorded video, and registry-enabled from a usable recording URL.

# Historical sensor questions

Use the direct ha_get_history tool for historical sensor values over a date range,
including odometer distance, energy, temperature and battery history. It supports
raw history and long-term statistics. Do not claim historical readings are
unavailable without querying it. Existing history does not require a new helper.
For "this week", use Monday midnight in HA's timezone through now, with explicit
timezone offsets; distinguish this from the last seven days. For an odometer,
subtract the valid reading at the period start from the latest valid reading,
preserving the reported unit. Request ascending rows and the window-start state;
follow pagination when needed. Check unavailable values, counter resets, units
and recorder coverage. If the start reading is missing, report the actual
covered interval and partial distance rather than claiming a full-week total.

A local midnight timestamp has time T00:00:00. For example, Monday midnight
in America/Los_Angeles on 2026-11-02 is 2026-11-02T00:00:00-08:00, equivalent
to 2026-11-02T08:00:00Z. Do not combine T08:00 with -08:00; that is 8 AM local.
HA may return a window-start state stamped exactly at the requested boundary;
that is the carried-forward baseline, not proof that recording started then.
Read reported units from a status tool instead of assuming the unit from the
vehicle model. Never invent a localhost HA endpoint or credential file.
