import csv

import numpy as np
import pytest
import soundfile as sf

from tools.prepare_dj_blind_test import prepare


def test_prepare_copies_neutral_clips_and_separates_key(tmp_path):
  hpg = tmp_path / "obvious_hpg.wav"
  baseline = tmp_path / "obvious_baseline.wav"
  sf.write(hpg, np.zeros(8000), 8000)
  sf.write(baseline, np.ones(8000) * 0.1, 8000)
  manifest = tmp_path / "manifest.csv"
  manifest.write_text(
    f"pair_id,hpg_clip,baseline_clip\np1,{hpg},{baseline}\n",
    encoding="utf-8",
  )

  public_path, key_path = prepare(
    manifest, tmp_path / "session", tmp_path / "private" / "key.csv", seed=4
  )

  public = list(csv.DictReader(public_path.open(encoding="utf-8")))
  key = list(csv.DictReader(key_path.open(encoding="utf-8")))
  assert len(public) == 1
  assert {row["system"] for row in key} == {"HPG", "baseline"}
  assert "hpg" not in public[0]["candidate_a_clip"].casefold()
  assert (public_path.parent / public[0]["candidate_a_clip"]).is_file()
  assert (public_path.parent / public[0]["candidate_b_clip"]).is_file()
  assert key_path.parent != public_path.parent


def test_prepare_refuses_to_overwrite_existing_session(tmp_path):
  output = tmp_path / "session"
  output.mkdir()
  with pytest.raises(FileExistsError):
    prepare(tmp_path / "missing.csv", output, tmp_path / "key.csv")


def test_prepare_balances_hpg_side_and_randomizes_pair_order(tmp_path):
  manifest = tmp_path / "manifest.csv"
  rows = ["pair_id,hpg_clip,baseline_clip"]
  for index in range(5):
    hpg = tmp_path / f"hpg_{index}.wav"
    baseline = tmp_path / f"baseline_{index}.wav"
    sf.write(hpg, np.full(800, index / 20 + 0.01), 8000)
    sf.write(baseline, np.full(800, index / 20 + 0.02), 8000)
    rows.append(f"p{index},{hpg.name},{baseline.name}")
  manifest.write_text("\n".join(rows) + "\n", encoding="utf-8")

  public_path, key_path = prepare(
    manifest, tmp_path / "session", tmp_path / "key.csv", seed=3
  )

  public = list(csv.DictReader(public_path.open(encoding="utf-8")))
  key = list(csv.DictReader(key_path.open(encoding="utf-8")))
  hpg_a = sum(row["candidate"] == "A" and row["system"] == "HPG" for row in key)
  assert hpg_a in {2, 3}
  assert [row["pair_id"] for row in public] != [f"p{i}" for i in range(5)]
