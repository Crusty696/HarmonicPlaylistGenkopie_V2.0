# 🚀 Releasing Guide

Automatische Releases mit GitHub Actions

## 📦 Wie du einen neuen Release erstellst

### **Schritt 1: Code aktualisieren**
Stelle sicher dass alle Änderungen committed und gepusht sind:

```bash
git add .
git commit -m "feat: Neue Features für v3.1"
git push
```

### **Schritt 2: Version Tag erstellen**

Erstelle einen Tag mit der neuen Versionsnummer:

```bash
# Format: v{MAJOR}.{MINOR}.{PATCH}
# Beispiele: v3.1.0, v3.2.0, v4.0.0

git tag v3.1.0
git push --tags
```

**Das war's!** 🎉

### **Schritt 3: Automatischer Release**

Nach dem Push des Tags:
1. ✅ GitHub Actions startet automatisch
2. ✅ Baut die EXE mit allen Dependencies
3. ✅ Erstellt GitHub Release
4. ✅ Lädt die EXE hoch
5. ✅ Generiert Release-Notes

**Dauer:** ~3-4 Minuten

### **Überprüfen:**

Gehe zu:
```
https://github.com/Crusty696/HarmonicPlaylistGenkopie_V2.0/releases
```

Du siehst den neuen Release mit:
- ✅ Versionsnummer (v3.1.0)
- ✅ Download-Link für die EXE
- ✅ Automatische Release-Notes
- ✅ Änderungslog

## 📋 Versioning Schema

Wir nutzen **Semantic Versioning** (MAJOR.MINOR.PATCH):

- **MAJOR** (v4.0.0): Große Änderungen, Breaking Changes
- **MINOR** (v3.1.0): Neue Features, abwärtskompatibel
- **PATCH** (v3.0.1): Bug-Fixes, kleine Verbesserungen

### Beispiele:

```bash
# Bug-Fix Release
git tag v3.0.1
git push --tags

# Neues Feature
git tag v3.1.0
git push --tags

# Major Update
git tag v4.0.0
git push --tags
```

## 🛠️ Troubleshooting

### **Release fehlgeschlagen?**

1. Gehe zu: https://github.com/Crusty696/HarmonicPlaylistGenkopie_V2.0/actions
2. Klicke auf den fehlgeschlagenen Workflow
3. Prüfe die Logs

### **Tag löschen (falls Fehler)?**

```bash
# Lokal löschen
git tag -d v3.1.0

# Remote löschen
git push --delete origin v3.1.0
```

### **Release manuell löschen?**

1. Gehe zu Releases
2. Klicke auf den Release
3. "Delete release"

## 📝 Best Practices

1. **Teste lokal** vor dem Tag
2. **Aktualisiere CHANGELOG.md** mit neuen Features
3. **Nutze aussagekräftige Tag-Messages**:
   ```bash
   git tag -a v3.1.0 -m "Release v3.1.0: Added new export formats"
   ```
4. **Prüfe GitHub Actions** nach dem Push

## 🔍 Monitoring

**Nach jedem Tag-Push:**
- Überwache: https://github.com/Crusty696/HarmonicPlaylistGenkopie_V2.0/actions
- Warte ~3 Minuten
- Prüfe Release: https://github.com/Crusty696/HarmonicPlaylistGenkopie_V2.0/releases

## 🎯 Quick Reference

```bash
# Typischer Release-Flow:
git add .
git commit -m "feat: Neue Features"
git push
git tag v3.1.0
git push --tags

# Fertig! ✅
```

---

**Bei Fragen:** Siehe GitHub Actions Logs oder issue tracker.
