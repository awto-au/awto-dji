# awto-dji

Awto's workspace for building on DJI Enterprise drones, docks and cloud services.

## DJI developer APIs and SDKs

Snapshot taken 2026-10-21 from [developer.dji.com](https://developer.dji.com). Check the portal for current versions before you start.

### Current

| SDK / API | Purpose | Key hardware | Latest version (date) | Docs |
|---|---|---|---|---|
| **Mobile SDK (MSDK)** | Android/iOS apps that control the aircraft, camera, gimbal and waypoint missions | Matrice 400, 4E/4T, 4D/4TD, 350 RTK, 300 RTK, 30 Series, Mavic 3 Enterprise, 3M, 3TA | Android 5.18.0 (2026-05-22); iOS 4.16.2 | [Tutorial](https://developer.dji.com/doc/mobile-sdk-tutorial/en/) |
| **Payload SDK (PSDK)** | C/C++ firmware for third-party payloads mounted on the aircraft | Matrice 5TD, 400, 4T/4E, 4D/4TD, Manifold 3 | 3.17.0 (2026-10-14) | [Tutorial](https://developer.dji.com/doc/payload-sdk-tutorial/en/) |
| **Cloud API** | Connects DJI Pilot 2 and DJI Docks to your own server over MQTT, HTTPS and WebSocket: telemetry, live video, wayline missions, media upload | Pilot 2: M4E/4T, M350/M300, M30, M3E. Docks: Dock 1, 2 and 3 | 1.14.0 (2025-04-15) | [Tutorial](https://developer.dji.com/doc/cloud-api-tutorial/en/) |
| **Cloud API 2** | AI-focused kit for building Dock applications | Not yet listed | Not yet listed | [Overview](https://developer.dji.com/cloud-api-2) |
| **Edge SDK (ESDK)** | Edge computing at the Dock: handle media and data locally before it reaches the cloud | Matrice 4D/4TD, DJI O4 Ground Station (v1.x: Dock 1/2/3) | 2.1.0 (2026-10-14) | [Tutorial](https://developer.dji.com/doc/edge-sdk-iot-tutorial/en/) · [GitHub](https://github.com/dji-sdk/Edge-SDK) |
| **FlightHub 2 OpenAPI** | REST API for an organisation's FlightHub 2 projects, devices and media. Authenticates with the organisation key from FlightHub user centre → My Organization | Devices managed in FlightHub 2 | Not listed | Not on the portal; see this [forum thread](https://sdk-forum.dji.net/hc/zh-cn/community/posts/45646586535193-DJI-FlightHub-2-OpenAPI) |
| **FlightHub Mapping API** | FlightHub cloud mapping and reconstruction | Not listed | Not listed | [Overview](https://developer.dji.com/flighthub-api) |
| **DJI Terra API** | Photogrammetry and LiDAR processing | Not listed | Not listed | Listed under Cloud Dev. on the portal |
| **Thermal SDK (TSDK)** | Reads and processes radiometric R-JPEG thermal images | H20T/H30T, M30T, M3T, M4T, others | Not confirmed | DJI Enterprise downloads |

### Private deployment services

- FlightHub 2 On-Premises Service
- 4G Private Enhanced Transmission Service

### Legacy (no longer updated)

- Onboard SDK 4.1.0 (2021): M300 RTK and M210 V2, with ROS support
- UX SDK 4.16.2 (2022)
- Windows SDK 0.3.2 beta (2019)

## Which one to use

- **App on the remote controller or a phone:** MSDK v5
- **Hardware on the aircraft:** PSDK
- **Fleet or Dock integration with our own backend:** Cloud API, plus ESDK at the Dock
- **Integrating with FlightHub 2:** FlightHub 2 OpenAPI

Most of these need a free DJI developer account and an App Key from developer.dji.com.
