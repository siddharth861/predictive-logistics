# Predictive Logistics & Forward Supply Chain

AI-powered, GIS-enabled predictive logistics platform for demand forecasting,
inventory intelligence, logistics risk analysis, transportation planning,
and explainable decision support.

## Project

The platform is designed to accept logistics data from diverse sources such as:

- CSV / Excel
- JSON / XML
- PDF / DOCX
- APIs
- Databases
- IoT / sensor sources
- Manual entry
- User-defined datasets

The system converts incoming data into a validated canonical data layer and
uses AI/ML, GIS and optimization to support predictive logistics decisions.

## Core Architecture

Data Sources
→ Universal Data Hub
→ Data Assistant
→ Validation & Lineage
→ PostgreSQL + PostGIS
→ AI / GIS / Optimization
→ Logistics Intelligence
→ Command Centre

## Development

This project is being developed incrementally with Git and GitHub.

Every major feature is committed separately so that the project always has
recoverable working versions.

## Technology

- React + Vite
- Python + FastAPI
- PostgreSQL + PostGIS
- Redis
- MinIO
- scikit-learn / XGBoost
- Leaflet / MapLibre
- OR-Tools
- Docker