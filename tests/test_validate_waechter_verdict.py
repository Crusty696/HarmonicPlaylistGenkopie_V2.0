from tools import validate_waechter_verdict as validator


def _report(*, tor="TOR 1", verdict="DURCHGEWUNKEN", findings="- keine", untested="- keine", extra_contract=""):
    return f"""## Pruefvertrag
- tor: {tor}
- auftrag: Waechtervertrag absichern
- akzeptanzkriterien: Formale Validierung vorhanden
- erlaubte_dateien: .agents/agents/hpg-waechter.md, tools/validate_waechter_verdict.py
- verbotene_dateien: hpg_core/caching.py
- referenzen: .agents/agents/hpg-waechter.md:1
- invarianten: Waechter bleibt read-only
- testbelege: tests/test_validate_waechter_verdict.py
{extra_contract}
## Urteil
{verdict}
## Vertragspruefung
- Vertrag vollstaendig und gegen Ist-Code geprueft.
## Belegmatrix
- Pruefpunkt: Vertrag | Beleg: .agents/agents/hpg-waechter.md:1 | Ergebnis: erfuellt
## Befunde
{findings}
## Nicht geprueft
{untested}
"""


def test_gueltiger_tor_1_bericht_wird_akzeptiert():
    assert validator.validate_report(_report()) == []


def test_gueltiger_tor_2_bericht_braucht_tor_1_und_diff():
    report = _report(tor="TOR 2", extra_contract="- tor_1_urteil: DURCHGEWUNKEN\n- diff_bereich: HEAD~1..HEAD")
    assert validator.validate_report(report) == []


def test_fehlendes_vertragsfeld_wird_abgelehnt():
    report = _report().replace("- testbelege: tests/test_validate_waechter_verdict.py\n", "")
    assert any("testbelege" in error for error in validator.validate_report(report))


def test_ungueltiges_urteil_wird_abgelehnt():
    assert any("Urteil" in error for error in validator.validate_report(_report(verdict="OK")))


def test_fehlender_abschnitt_nicht_geprueft_wird_abgelehnt():
    report = _report().replace("## Nicht geprueft\n- keine\n", "")
    assert any("Nicht geprueft" in error for error in validator.validate_report(report))


def test_befund_ohne_zeilenbeleg_wird_abgelehnt():
    findings = """### Befund 1
- Schwere: hoch
- Szenario: Codepfad nicht erreichbar
- Korrektur: klein halten"""
    assert any("Befunde" in error for error in validator.validate_report(_report(verdict="MIT AUFLAGEN", findings=findings)))


def test_durchgewunken_mit_offenem_punkt_wird_abgelehnt():
    errors = validator.validate_report(_report(untested="- Testlauf nicht ausgefuehrt"))
    assert any("DURCHGEWUNKEN" in error for error in errors)


def test_tor_2_ohne_tor_1_urteil_wird_abgelehnt():
    errors = validator.validate_report(_report(tor="TOR 2"))
    assert any("tor_1_urteil" in error for error in errors)


def test_tor_2_mit_ungueltigem_tor_1_urteil_wird_abgelehnt():
    report = _report(tor="TOR 2", extra_contract="- tor_1_urteil: erfunden\n- diff_bereich: HEAD~1..HEAD")
    assert any("Tor-1-Urteil" in error for error in validator.validate_report(report))


def test_tor_2_ohne_diff_bereich_wird_abgelehnt():
    report = _report(tor="TOR 2", extra_contract="- tor_1_urteil: DURCHGEWUNKEN")
    assert any("diff_bereich" in error for error in validator.validate_report(report))


def test_tor_2_mit_ungueltigem_diff_bereich_wird_abgelehnt():
    report = _report(tor="TOR 2", extra_contract="- tor_1_urteil: DURCHGEWUNKEN\n- diff_bereich: erfunden")
    assert any("diff_bereich" in error for error in validator.validate_report(report))
