# SentinelAI - AI Powered Smart Home Operating System

## 🏠 Overview

**SentinelAI** is a modular AI-powered smart home operating system built using Raspberry Pi, Arduino, IoT sensors, and computer vision.

Instead of creating isolated sensor demonstrations, SentinelAI combines multiple security, safety, environmental monitoring, and automation modules into a single intelligent platform capable of monitoring an entire home in real time.

The project is designed to be scalable, allowing additional hardware modules and AI capabilities to be integrated over time while maintaining a unified dashboard and event logging system.

---

## 🎯 Vision

Modern smart homes often require multiple disconnected devices for security, automation, environmental monitoring, and remote access.

SentinelAI aims to unify these systems into one extensible platform capable of:

* Home Security
* Environmental Monitoring
* Hazard Detection
* AI-based Vision
* Remote Monitoring
* Home Automation
* Analytics & Logging

---

## ✨ Features

### 🔒 Security

* Door & Window Monitoring
* Motion Detection
* AI Person Detection
* Face Recognition *(Planned)*
* RFID Authentication *(Planned)*
* Intruder Alerts

### 🔥 Safety

* Gas Leak Detection
* Fire Detection
* Smoke Monitoring
* Alarm System

### 🌍 Environment

* Temperature Monitoring
* Humidity Monitoring
* Ambient Light Detection
* Rain Detection

### 🌱 Automation

* Smart Irrigation
* Water Tank Monitoring
* Automatic Pump Control
* Smart Lighting

### 📊 Dashboard

* Live Sensor Status
* Event Timeline
* Camera Feed
* Historical Logs
* System Health
* Device Monitoring

### 🌐 Remote Access

* Tailscale Integration
* Telegram Notifications
* Live Monitoring
* Secure Remote Dashboard

---

# 🏗️ Project Architecture

```
                        SentinelAI Dashboard
                               │
                Flask + SQLite + REST API
                               │
                     Raspberry Pi 4 (Brain)
                               │
      ┌──────────────┬──────────────┬──────────────┐
      │              │              │
   AI Camera      Arduino Hub     Notifications
      │              │              │
      │              │          Telegram
      │              │
      │      All Sensor Modules
      │
      ├── Security
      ├── Environment
      ├── Safety
      └── Automation
```

---

# 📦 Modules

## Phase 1 — Smart Door Monitoring 🚧

Status: **In Development**

Features

* Door Open Detection
* Door Close Detection
* Timestamp Logging
* Alarm Trigger
* Dashboard Integration
* Event History

Hardware

* Raspberry Pi
* MC-38 Magnetic Door Sensor
* LED
* Active Buzzer

---

## Future Modules

### Phase 2

Motion Detection

### Phase 3

Camera + AI Person Detection

### Phase 4

Gas & Fire Detection

### Phase 5

Environmental Monitoring

### Phase 6

Smart Irrigation

### Phase 7

Central Dashboard

### Phase 8

Remote Monitoring & Notifications

---

# 🛠️ Tech Stack

## Hardware

* Raspberry Pi 4
* Raspberry Pi Camera
* Arduino Uno
* PIR Sensor
* MC-38 Magnetic Switch
* MQ-2 Gas Sensor
* Flame Sensor
* DHT11
* Soil Moisture Sensor
* Rain Sensor
* Water Level Sensor
* RFID Module
* OLED Display
* LCD Display
* Relay Module
* Servo Motor

---

## Software

* Python
* Flask
* SQLite
* OpenCV
* YOLOv8 *(Planned)*
* GPIO Zero
* HTML
* CSS
* JavaScript
* Tailscale

---

# 📂 Repository Structure

```
SentinelAI/

├── docs/
├── hardware/
├── firmware/
├── dashboard/
├── database/
├── ai/
├── sensors/
├── notifications/
├── logs/
├── static/
├── templates/
├── README.md
└── LICENSE
```

---

# 🎯 Long-Term Goals

* AI-based Occupancy Detection
* Intelligent Intruder Classification
* Face Recognition
* Smart Energy Monitoring
* Predictive Analytics
* Mobile Dashboard
* Voice Assistant Integration
* MQTT Support
* Home Assistant Integration

---

# 🤝 Contributing

SentinelAI is being developed incrementally through modular phases. Contributions, suggestions, and feature requests are always welcome.

---

# 📜 License

This project is licensed under the MIT License.
