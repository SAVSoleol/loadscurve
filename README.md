# Générateur de courbe de charge HT/BT — calibration lissée

Cette version corrige les ruptures artificielles aux changements de tarif.

## Modifications

- calibration HT/BT progressive ;
- transition lissée autour des changements de tarif ;
- conservation exacte des consommations annuelles HT et BT ;
- maintien du thème sombre ;
- exports Excel, CSV et PNG.

## Fichiers GitHub

- app.py
- loadcurve_engine.py
- loadcurve_profiles.py
- loadcurve_export.py
- requirements.txt

## Lancement

```bash
pip install -r requirements.txt
streamlit run app.py
```
