# LoadCurves 2.2.0

Cette version force Streamlit Cloud à charger un nouveau module :

- `loadcurve_engine_v22.py`

La répartition mensuelle est maintenant en forme de U pour tous les profils résidentiels :

- janvier et décembre élevés ;
- diminution régulière au printemps ;
- minimum en juillet ;
- remontée régulière à l'automne.

Après le déploiement, l'application doit afficher :

`Version application : 2.2.0 — Moteur chargé : 2.2.0-courbe-mensuelle-U`

## Fichiers à mettre dans GitHub

- app.py
- loadcurve_engine_v22.py
- loadcurve_profiles.py
- loadcurve_export.py
- requirements.txt

L'ancien fichier `loadcurve_engine.py` peut rester dans le dépôt : la nouvelle application ne l'importe plus.
