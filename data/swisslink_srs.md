# Operation SwissLink — Software Requirements Specification (FICTIONAL)

Version 1.0 · Hackathon exercise · 9 November 2026
All organizations, devices and interfaces in this document are fictional and exist only for the hackathon demonstration.

## 1. Purpose
SwissLink is a tactical situational-awareness system for a small field unit and its command post. It links friendly-force positions, sensor feeds, video analytics, routes and operator records into one common operating picture, and delivers alerts to field personnel through a cellular app, a fictional Swiss Army multifunction device ("SAM device") and a fictional Swiss watch ("SW-Watch").

## 2. Context and external systems
- **SAM device (fictional):** handheld multifunction device carried by every soldier. Reports GPS position, emergency button presses and equipment status (battery, radio, water). Communicates over a proprietary short-range radio bridged to IP by a field gateway.
- **SW-Watch (fictional):** wrist device paired to the SAM device. Displays alerts, vibrates, lets the wearer acknowledge, and keeps synchronized time.
- **Cellular app:** Android/iOS app for team leaders on available cellular networks.
- **EO sensors:** electro-optical cameras (fixed masts and a small UAV) delivering video streams.
- **Heterogeneous sensors:** acoustic, seismic and radar sensors from different suppliers with different message formats.
- **Map data provider:** supplies base maps and elevation tiles.

## 3. Functional requirements

### 3.1 Friendly force tracking
- **SL-FT-01** The system shall receive GPS positions from every SAM device and cellular app and display them on a map in near real time.
- **SL-FT-02** The system shall store the full position history of every tracked unit and allow playback of any time window.
- **SL-FT-03** The system shall show the last known position and the age of the position for units that stop reporting.
- **SL-FT-04** The system shall support geofences and raise an alert when a unit enters or leaves one.

### 3.2 Maps
- **SL-MAP-01** The map shall display base map, elevation, friendly units, detections, routes and geofences as selectable layers.
- **SL-MAP-02** The map shall work without internet connectivity using pre-loaded map tiles.

### 3.3 Route planning and ETA
- **SL-RT-01** The system shall compute a route between two points taking terrain and user-defined no-go areas into account.
- **SL-RT-02** The system shall estimate the time of arrival for a unit on a planned route and update it from live positions.

### 3.4 EO / video analytics
- **SL-EO-01** The system shall ingest live video from EO sensors and record it.
- **SL-EO-02** The system shall detect and classify people and vehicles in video.
- **SL-EO-03** The system shall track detected objects across frames and assign track IDs.
- **SL-EO-04** The system should provide semantic segmentation of terrain (road, vegetation, building, water).
- **SL-EO-05** The system should detect changes between two images of the same area taken at different times.
- **SL-EO-06** The system should generate short natural-language captions describing a video clip.
- **SL-EO-07** Detections shall be geo-referenced and shown on the map.

### 3.5 Sensor fusion
- **SL-SF-01** The system shall normalize messages from heterogeneous sensors into a single common data model.
- **SL-SF-02** The system shall fuse detections from multiple sensors and EO analytics into a single track picture, removing duplicates.

### 3.6 Operator diary
- **SL-OD-01** Operators shall record timestamped diary entries, optionally linked to a unit, track, detection or map location.
- **SL-OD-02** Diary entries shall be searchable by text, time and linked object.

### 3.7 Alerts and devices
- **SL-AL-01** An emergency button press on a SAM device shall raise a high-priority alert at the command post and on team-leader apps.
- **SL-AL-02** The system shall send alerts to SW-Watch devices, and the wearer shall be able to acknowledge them; acknowledgements shall be visible at the command post.
- **SL-AL-03** The system shall display SAM device equipment status (battery, radio, water) and alert on low battery.
- **SL-AL-04** SW-Watch devices shall keep time synchronized with the system.

### 3.8 Communications
- **SL-COM-01** Components shall exchange data through a publish/subscribe messaging layer.
- **SL-COM-02** The system shall continue to operate in degraded mode when links to the field are intermittent, and deliver queued messages when the link returns.

### 3.9 Cellular app
- **SL-APP-01** The cellular app shall show the map, own unit, friendly units and alerts, and allow team leaders to send position reports and diary entries.
- **SL-APP-02** The cellular app shall receive push notifications for high-priority alerts.

## 4. Nonfunctional requirements
- **SL-NF-01** Position updates shall be displayed with low latency.
- **SL-NF-02** The system shall be highly available at the command post.
- **SL-NF-03** Position history and diary entries shall be retained for as long as needed for after-action review.
- **SL-NF-04** The video analytics shall run on GPU hardware available at the command post.
- **SL-NF-05** The system shall scale to the number of units in a battalion.

## 5. Security and deployment constraints
- **SL-SEC-01** All data shall remain on-premises at the command post; no data may be sent to public cloud services.
- **SL-SEC-02** All communication between components and with field devices shall be encrypted and authenticated.
- **SL-SEC-03** Users shall be authenticated and authorized by role (commander, operator, team leader, analyst).
- **SL-SEC-04** All operator actions and alerts shall be written to a tamper-evident audit log.
- **SL-DEP-01** The command-post software shall run on Linux servers, deployable as containers.
- **SL-DEP-02** Open-source software is permitted only with licenses compatible with redistribution inside a closed defense product.

## 6. Notes from the customer
- The team is considering a commercial mobile push-notification service for SL-APP-02.
- Exact numbers for latency, availability, retention period and battalion size will be provided later.
