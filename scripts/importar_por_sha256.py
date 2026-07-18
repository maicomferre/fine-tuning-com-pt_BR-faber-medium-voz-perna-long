#!/usr/bin/env python3
"""Importa WAVs ausentes pelo conteudo e atribui novos IDs sem sobrescrever.

Por padrao apenas mostra o plano. Use --apply para copiar e atualizar o metadata.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import os
import re
import shutil
from pathlib import Path


ID_RE = re.compile(r"^fatiado_(\d+)$")


def numeric_id(value: str) -> int:
    match = ID_RE.fullmatch(value)
    if not match:
        raise ValueError(f"ID fora do padrao fatiado_NUMERO: {value}")
    return int(match.group(1))


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_metadata(path: Path) -> dict[str, str]:
    records: dict[str, str] = {}
    with path.open(encoding="utf-8-sig") as stream:
        for line_number, raw_line in enumerate(stream, start=1):
            line = raw_line.rstrip("\r\n")
            audio_id, text = line.split("|", 1) if "|" in line else (line, "")
            audio_id = audio_id.strip()
            numeric_id(audio_id)
            if audio_id in records:
                raise ValueError(f"ID duplicado no metadata, linha {line_number}: {audio_id}")
            records[audio_id] = text.strip()
    return records


def parse_text_override(value: str) -> tuple[str, str]:
    if "=" not in value:
        raise argparse.ArgumentTypeError("use ID=TEXTO")
    audio_id, text = value.split("=", 1)
    try:
        numeric_id(audio_id)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from exc
    return audio_id, text


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source_dir", type=Path)
    parser.add_argument("--wav-dir", type=Path, default=Path("dataset/wav"))
    parser.add_argument("--metadata", type=Path, default=Path("dataset/metadata.csv"))
    parser.add_argument("--audit-dir", type=Path, default=Path("auditoria"))
    parser.add_argument("--set-text", action="append", default=[], type=parse_text_override)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    source_dir = args.source_dir.resolve()
    wav_dir = args.wav_dir.resolve()
    metadata_path = args.metadata.resolve()
    audit_dir = args.audit_dir.resolve()
    if not source_dir.is_dir() or not wav_dir.is_dir() or not metadata_path.is_file():
        parser.error("source_dir, wav-dir ou metadata nao encontrado")

    source_wavs = sorted(source_dir.glob("*.wav"), key=lambda p: numeric_id(p.stem))
    target_wavs = sorted(wav_dir.glob("*.wav"), key=lambda p: numeric_id(p.stem))
    metadata = read_metadata(metadata_path)
    metadata.update(dict(args.set_text))

    target_by_hash: dict[str, list[Path]] = {}
    for path in target_wavs:
        target_by_hash.setdefault(sha256(path), []).append(path)
    duplicate_target_hashes = {h: paths for h, paths in target_by_hash.items() if len(paths) > 1}
    if duplicate_target_hashes:
        details = ", ".join("/".join(p.name for p in paths) for paths in duplicate_target_hashes.values())
        raise ValueError(f"dataset ja contem audios duplicados: {details}")

    source_seen: set[str] = set()
    missing: list[tuple[Path, str]] = []
    skipped_existing = 0
    skipped_source_duplicate = 0
    for path in source_wavs:
        digest = sha256(path)
        if digest in target_by_hash:
            skipped_existing += 1
        elif digest in source_seen:
            skipped_source_duplicate += 1
        else:
            source_seen.add(digest)
            missing.append((path, digest))

    max_existing_id = max((numeric_id(path.stem) for path in target_wavs), default=0)
    plan: list[dict[str, str]] = []
    for offset, (source_path, digest) in enumerate(missing, start=1):
        new_id = f"fatiado_{max_existing_id + offset:03d}"
        target_path = wav_dir / f"{new_id}.wav"
        if target_path.exists():
            raise FileExistsError(f"destino ja existe; importacao cancelada: {target_path}")
        plan.append(
            {
                "ordem": str(offset),
                "arquivo_origem": source_path.name,
                "sha256": digest,
                "novo_id": new_id,
                "arquivo_destino": target_path.name,
            }
        )

    final_ids = {path.stem for path in target_wavs} | {row["novo_id"] for row in plan}
    for audio_id in final_ids:
        metadata.setdefault(audio_id, "")
    extra_metadata = set(metadata) - final_ids
    if extra_metadata:
        raise ValueError(
            "metadata possui IDs sem WAV e a operacao foi cancelada: "
            + ", ".join(sorted(extra_metadata, key=numeric_id))
        )

    print(f"WAVs na origem: {len(source_wavs)}")
    print(f"WAVs ja no dataset: {len(target_wavs)}")
    print(f"Ignorados por SHA-256 ja existente: {skipped_existing}")
    print(f"Duplicatas internas da origem ignoradas: {skipped_source_duplicate}")
    print(f"Novos WAVs a importar: {len(plan)}")
    if plan:
        print(
            f"IDs novos: {plan[0]['novo_id']} ate {plan[-1]['novo_id']} "
            f"(maximo atual: {max_existing_id})"
        )
        print(f"Primeiro: {plan[0]['arquivo_origem']} -> {plan[0]['arquivo_destino']}")
        print(f"Ultimo: {plan[-1]['arquivo_origem']} -> {plan[-1]['arquivo_destino']}")
    print(f"WAVs finais esperados: {len(final_ids)}")
    print(f"Linhas finais esperadas no metadata: {len(metadata)}")

    if not args.apply:
        print("Simulacao concluida; nenhum arquivo foi alterado.")
        return 0

    audit_dir.mkdir(parents=True, exist_ok=True)
    backup_path = audit_dir / "metadata.antes_importacao.csv"
    mapping_path = audit_dir / "mapeamento_importacao.csv"
    if backup_path.exists() or mapping_path.exists():
        raise FileExistsError(
            "backup ou mapeamento da importacao ja existe; remova/arquive conscientemente antes de repetir"
        )
    shutil.copy2(metadata_path, backup_path)

    created: list[Path] = []
    temp_metadata = metadata_path.with_name(metadata_path.name + ".importando")
    try:
        for row, (source_path, _digest) in zip(plan, missing, strict=True):
            target_path = wav_dir / row["arquivo_destino"]
            with source_path.open("rb") as source, target_path.open("xb") as target:
                shutil.copyfileobj(source, target)
            shutil.copystat(source_path, target_path)
            created.append(target_path)

        with temp_metadata.open("x", encoding="utf-8", newline="") as stream:
            for audio_id in sorted(metadata, key=numeric_id):
                stream.write(f"{audio_id}|{metadata[audio_id]}\n")
        os.replace(temp_metadata, metadata_path)

        with mapping_path.open("x", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=list(plan[0]) if plan else ["ordem"])
            writer.writeheader()
            writer.writerows(plan)
    except Exception:
        if temp_metadata.exists():
            temp_metadata.unlink()
        for path in reversed(created):
            path.unlink()
        raise

    # Verificacao final independente do plano.
    final_wavs = list(wav_dir.glob("*.wav"))
    final_metadata = read_metadata(metadata_path)
    final_hashes = [sha256(path) for path in final_wavs]
    if len(final_wavs) != len(final_metadata) or len(final_hashes) != len(set(final_hashes)):
        raise RuntimeError("validacao final falhou; consulte o backup e o mapeamento")
    if {path.stem for path in final_wavs} != set(final_metadata):
        raise RuntimeError("IDs do metadata nao correspondem aos nomes dos WAVs")

    print(f"Importacao concluida: {len(created)} WAVs copiados sem sobrescrita.")
    print(f"Backup: {backup_path}")
    print(f"Mapeamento: {mapping_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
