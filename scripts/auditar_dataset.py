#!/usr/bin/env python3
"""Audita a correspondencia entre uma pasta de WAVs e o dataset local.

O script e somente-leitura para os audios. Ele compara os arquivos por SHA-256 e
gera relatorios CSV/Markdown; nao copia, remove nem renomeia WAVs.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import re
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Record:
    audio_id: str
    text: str
    line: int
    malformed: bool


def natural_key(path: Path | str) -> tuple[object, ...]:
    return tuple(
        int(part) if part.isdigit() else part.lower()
        for part in re.split(r"(\d+)", str(path))
    )


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_records(path: Path) -> tuple[dict[str, Record], list[Record], list[str]]:
    by_id: dict[str, Record] = {}
    records: list[Record] = []
    duplicate_ids: list[str] = []
    with path.open(encoding="utf-8-sig") as stream:
        for line_number, raw_line in enumerate(stream, start=1):
            line = raw_line.rstrip("\r\n")
            malformed = "|" not in line
            audio_id, text = line.split("|", 1) if not malformed else (line, "")
            record = Record(audio_id.strip(), text.strip(), line_number, malformed)
            records.append(record)
            if record.audio_id in by_id:
                duplicate_ids.append(record.audio_id)
            else:
                by_id[record.audio_id] = record
    return by_id, records, duplicate_ids


def write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def joined(values: list[str]) -> str:
    return ", ".join(sorted(values, key=natural_key))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source_dir", type=Path, help="pasta normalizados")
    parser.add_argument("--project-wav-dir", type=Path, default=Path("dataset/wav"))
    parser.add_argument("--metadata", type=Path, default=Path("dataset/metadata.csv"))
    parser.add_argument("--output-dir", type=Path, default=Path("auditoria"))
    args = parser.parse_args()

    source_dir = args.source_dir.resolve()
    source_list = source_dir / "list.txt"
    project_wav_dir = args.project_wav_dir.resolve()
    metadata_path = args.metadata.resolve()
    output_dir = args.output_dir.resolve()

    for required in (source_dir, source_list, project_wav_dir, metadata_path):
        if not required.exists():
            parser.error(f"caminho nao encontrado: {required}")

    source_wavs = sorted(source_dir.glob("*.wav"), key=natural_key)
    project_wavs = sorted(project_wav_dir.glob("*.wav"), key=natural_key)
    source_records, source_record_list, source_duplicates = read_records(source_list)
    metadata, metadata_record_list, metadata_duplicates = read_records(metadata_path)

    source_hashes = {path: sha256(path) for path in source_wavs}
    project_hashes = {path: sha256(path) for path in project_wavs}
    project_by_hash: dict[str, list[Path]] = {}
    for path, digest in project_hashes.items():
        project_by_hash.setdefault(digest, []).append(path)

    inventory_rows: list[dict[str, str]] = []
    missing_rows: list[dict[str, str]] = []

    for sequence, source_path in enumerate(source_wavs, start=1):
        audio_id = source_path.stem
        digest = source_hashes[source_path]
        matches = project_by_hash.get(digest, [])
        list_record = source_records.get(audio_id)
        metadata_record = metadata.get(audio_id)
        list_text = list_record.text if list_record else ""
        metadata_text = metadata_record.text if metadata_record else ""
        problems: list[str] = []
        if not list_record:
            problems.append("WAV sem entrada no list.txt")
        elif not list_text:
            problems.append("transcricao vazia no list.txt")
        if len(matches) > 1:
            problems.append("checksum aparece mais de uma vez no projeto")
        if matches and not any(match.name == source_path.name for match in matches):
            problems.append("presente com outro nome")

        status = "presente" if matches else "faltante"
        inventory_rows.append(
            {
                "id_origem": audio_id,
                "arquivo_origem": source_path.name,
                "sha256": digest,
                "status_projeto": status,
                "arquivo_projeto_por_checksum": joined([p.name for p in matches]),
                "texto_list": list_text,
                "problemas": "; ".join(problems),
            }
        )
        if not matches:
            missing_rows.append(
                {
                    "ordem_fila": str(len(missing_rows) + 1),
                    "id_origem": audio_id,
                    "arquivo_origem": source_path.name,
                    "sha256": digest,
                    "texto_antigo_apenas_referencia": list_text,
                    "problemas": "; ".join(problems),
                }
            )

    source_ids = {path.stem for path in source_wavs}
    project_ids = {path.stem for path in project_wavs}
    list_ids = set(source_records)
    metadata_ids = set(metadata)
    source_without_list = sorted(source_ids - list_ids, key=natural_key)
    list_without_source = sorted(list_ids - source_ids, key=natural_key)
    project_without_valid_metadata = sorted(
        (audio_id for audio_id in project_ids if not metadata.get(audio_id) or not metadata[audio_id].text),
        key=natural_key,
    )
    metadata_without_project = sorted(metadata_ids - project_ids, key=natural_key)

    divergence_rows: list[dict[str, str]] = []
    for audio_id in sorted(metadata_ids & list_ids, key=natural_key):
        if metadata[audio_id].text != source_records[audio_id].text:
            divergence_rows.append(
                {
                    "id": audio_id,
                    "texto_metadata_revisado": metadata[audio_id].text,
                    "texto_list_antigo": source_records[audio_id].text,
                }
            )

    malformed_metadata = [r.audio_id for r in metadata_record_list if r.malformed]
    malformed_list = [r.audio_id for r in source_record_list if r.malformed]
    output_dir.mkdir(parents=True, exist_ok=True)
    write_csv(
        output_dir / "inventario.csv",
        [
            "id_origem",
            "arquivo_origem",
            "sha256",
            "status_projeto",
            "arquivo_projeto_por_checksum",
            "texto_list",
            "problemas",
        ],
        inventory_rows,
    )
    write_csv(
        output_dir / "faltantes.csv",
        [
            "ordem_fila",
            "id_origem",
            "arquivo_origem",
            "sha256",
            "texto_antigo_apenas_referencia",
            "problemas",
        ],
        missing_rows,
    )
    write_csv(
        output_dir / "divergencias_texto.csv",
        ["id", "texto_metadata_revisado", "texto_list_antigo"],
        divergence_rows,
    )

    same_name_same_hash = sum(
        1
        for source_path, digest in source_hashes.items()
        if (project_wav_dir / source_path.name) in project_hashes
        and project_hashes[project_wav_dir / source_path.name] == digest
    )
    summary = f"""# Auditoria do dataset

Esta auditoria e somente-leitura para os WAVs. Nenhum audio foi copiado, removido
ou renomeado.

## Resultado

- WAVs em `normalizados`: **{len(source_wavs)}**
- WAVs no projeto: **{len(project_wavs)}**
- WAVs do projeto identicos ao arquivo homonimo da origem: **{same_name_same_hash}**
- WAVs da origem ausentes do projeto, comparados por SHA-256: **{len(missing_rows)}**
- Linhas em `list.txt`: **{len(source_record_list)}**
- Linhas em `metadata.csv`: **{len(metadata_record_list)}**
- WAVs do projeto sem transcricao valida no metadata: **{len(project_without_valid_metadata)}**
- Textos diferentes entre metadata e list para o mesmo ID: **{len(divergence_rows)}**

## Observacoes

- WAVs da origem sem entrada no `list.txt`: {joined(source_without_list) or "nenhum"}
- Entradas antigas do `list.txt` sem WAV na origem, ignoradas por terem sido descartadas: {joined(list_without_source) or "nenhuma"}
- WAVs do projeto sem metadata valido: {joined(project_without_valid_metadata) or "nenhum"}
- Metadata sem WAV no projeto: {joined(metadata_without_project) or "nenhum"}
- Linhas malformadas no metadata (sem `|`): {joined(malformed_metadata) or "nenhuma"}
- Linhas malformadas no list (sem `|`): {joined(malformed_list) or "nenhuma"}
- IDs duplicados no metadata: {joined(metadata_duplicates) or "nenhum"}
- IDs duplicados no list: {joined(source_duplicates) or "nenhum"}

## Arquivos gerados

- `inventario.csv`: todos os WAVs da origem, checksum e presenca no projeto.
- `faltantes.csv`: fila dos 89 WAVs que ainda nao estao no projeto e precisam ser transcritos novamente.
- `divergencias_texto.csv`: preserva as correcoes feitas no metadata.

## Recomendacao segura

Use `faltantes.csv` como a fila de trabalho. O texto antigo aparece somente como
referencia e nao deve ser tratado como transcricao correta. As entradas do
`list.txt` que nao possuem WAV foram deliberadamente filtradas e nao precisam ser
recuperadas. Nao renomeie os WAVs existentes ate escolhermos juntos a regra de
numeracao, pois uma renumeracao direta pode causar colisao de nomes.
"""
    (output_dir / "resumo.md").write_text(summary, encoding="utf-8")

    print(summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
