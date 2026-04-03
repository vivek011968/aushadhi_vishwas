# Aushadhi Vishwas - Fake Medicine Verification & Supply Chain Tracking System

## 🏥 Problem Statement
Fake and duplicate medicines are increasing in the market, causing serious health risks, treatment failures, and loss of trust in the healthcare system. Consumers and pharmacies often cannot easily verify if a drug is genuine or where it originated.

## 🛡️ Our Solution
**Aushadhi Vishwas** provides a digital trust layer for the pharmaceutical supply chain using:
- **Secure QR Codes**: Unique identities for every medicine unit.
- **Simulated Blockchain Ledger**: Cryptographic SHA-256 integrity checks for every movement.
- **Real-time Analytics**: Admin dashboard for monitoring scan trends and fake alerts.
- **Geo-Mapping**: Instant visualization of counterfeit detection sites.
- **Direct Reporting**: Consumer portal to flag suspicious medications directly to authorities.

---

## 🚀 Getting Started

### 1. Installation
Ensure you have Python 3.x installed.
```bash
pip install flask
```

### 2. Running the Application
```bash
python app.py
```
*Note: The app will automatically detect your local network IP to allow mobile devices on the same Wi-Fi to scan QR codes.*

### 3. Accessing the Platform
- **Consumer Portal**: `http://localhost:5000`
- **Admin Panel**: `http://localhost:5000/login`
  - **Username**: `admin`
  - **Password**: `admin123`

---

## ✨ Key Features
- **Blockchain Integrity**: Simulation of a digital ledger where each event is hashed and linked.
- **Mobile First**: QR codes are generated with dynamic network IPs for real-world phone scanning demos.
- **Smart Expiry Alerts**: Automatically highlights medicines reaching expiry in the next 30 days.
- **Advanced Visualization**: Interactive donut charts (Scan distribution) and line charts (Scan trends).
- **Security Hardened**: Admin credentials stored using PBKDF2 cryptography.

---

## 🛠️ Technological Stack
- **Backend**: Flask (Python)
- **Database**: SQLite (Relational Storage)
- **Frontend**: HTML5, CSS3 (Glassmorphism), JavaScript (ES6)
- **Libraries**: Leaflet.js (Mapping), Chart.js (Analytics), Html5-QRCode (Scanning), QRCode.js (Generation)

---
*Developed for Smart India Hackathon (SIH) Prototype.*
