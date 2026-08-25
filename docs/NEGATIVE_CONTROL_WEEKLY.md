# Weekly Negative-Control Re-Run Log

Append-only. Each run re-checks every live pair's real fill-adjusted monthly net against a random-entry control and a shuffled-price control, on a fresh kline pull. Does not backfill history that predates this log — the first entry below is the first run.

---

## 2026-08-25T19:06:01.708435Z — weekly negative-control re-run
Fresh MEXC kline pull per pair (not the static data_fetch.py CSVs), spread=1.0%, 30 trials/control, seed=42.
- **MINAUSDT**: real=39.0421%/mo, random-entry=-22.9240%/mo (beats: True), shuffled-price=-132.8094%/mo (beats: True) -> **PASS (beats both controls)**
- **SFPUSDT**: real=40.4719%/mo, random-entry=-16.4454%/mo (beats: True), shuffled-price=-63.8456%/mo (beats: True) -> **PASS (beats both controls)**
- **XYOUSDT**: real=96.9837%/mo, random-entry=-28.7962%/mo (beats: True), shuffled-price=27.8428%/mo (beats: True) -> **PASS (beats both controls)**
- **GOATUSDT**: real=57.0781%/mo, random-entry=-21.6964%/mo (beats: True), shuffled-price=-16.1663%/mo (beats: True) -> **PASS (beats both controls)**
- **XPRUSDT**: real=70.4691%/mo, random-entry=-16.2787%/mo (beats: True), shuffled-price=-16.1416%/mo (beats: True) -> **PASS (beats both controls)**
- **PIPPINUSDT**: real=36.8830%/mo, random-entry=-21.9919%/mo (beats: True), shuffled-price=6.2546%/mo (beats: True) -> **PASS (beats both controls)**
- **SUSDT**: real=10.2472%/mo, random-entry=-16.7682%/mo (beats: True), shuffled-price=-37.4822%/mo (beats: True) -> **PASS (beats both controls)**
- **NILUSDT**: real=110.6831%/mo, random-entry=-1.2185%/mo (beats: True), shuffled-price=-115.5930%/mo (beats: True) -> **PASS (beats both controls)**

Summary: 8/8 pairs beat both negative controls this run.
