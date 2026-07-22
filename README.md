# Générateur de courbe de charge HT/BT — version corrigée

Cette version renomme les modules internes afin d’éviter les conflits d’import sur Streamlit Cloud.

## Fichiers à déposer dans le dépôt GitHub

- app.py
- loadcurve_engine.py
- loadcurve_profiles.py
- loadcurve_export.py
- requirements.txt

Supprime les anciens fichiers `generator.py`, `profiles.py` et `export.py` du dépôt pour éviter toute confusion.

## Lancement local

```bash
pip install -r requirements.txt
streamlit run app.py
```
