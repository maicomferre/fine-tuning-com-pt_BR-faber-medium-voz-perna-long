#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
WORKDIR="$SCRIPT_DIR"
INPUT_FILE="${1:-$WORKDIR/sem título.wav}"
OUTDIR="$WORKDIR/normalizados"

# Padrao de audio esperado para o dataset do modelo pt_BR-faber-medium.
TARGET_SAMPLE_RATE="${TARGET_SAMPLE_RATE:-22050}"
TARGET_CHANNELS="${TARGET_CHANNELS:-1}"
TARGET_CODEC="${TARGET_CODEC:-pcm_s16le}"

# Padronizacao de volume por fragmento. O alvo -16 LUFS e conservador para fala:
# deixa os trechos mais uniformes sem forcar volume excessivo.
LOUDNORM_I="${LOUDNORM_I:--16}"
LOUDNORM_TP="${LOUDNORM_TP:--1.5}"
LOUDNORM_LRA="${LOUDNORM_LRA:-11}"

# Ajuste principal do fatiamento:
# - deixe no Kdenlive espacos de 1.5s a 2s entre falas que devem virar arquivos separados;
# - pausas menores que isso ficam dentro do mesmo fragmento.
SILENCE_DURATION="${SILENCE_DURATION:-1.2}"
SILENCE_THRESHOLD="${SILENCE_THRESHOLD:--55d}"
MIN_FRAGMENT_DURATION="${MIN_FRAGMENT_DURATION:-1.0}"
DRY_RUN="${DRY_RUN:-0}"
ARCHIVE_INPUT="${ARCHIVE_INPUT:-1}"
START_ID="${START_ID:-${NEXT_ID:-}}"

if [ ! -f "$INPUT_FILE" ]; then
    echo "Erro: '$INPUT_FILE' não encontrado."
    exit 1
fi

if ! command -v ffmpeg >/dev/null 2>&1; then
    echo "Erro: ffmpeg nao encontrado no PATH."
    exit 1
fi

if ! command -v ffprobe >/dev/null 2>&1; then
    echo "Erro: ffprobe nao encontrado no PATH."
    exit 1
fi

if ! command -v sox >/dev/null 2>&1; then
    echo "Erro: sox nao encontrado no PATH."
    exit 1
fi

mkdir -p "$OUTDIR"
TMPDIR=$(mktemp -d "$WORKDIR/tmp_slices.XXXXXX")
trap 'rm -rf "$TMPDIR"' EXIT

proximo_id_livre() {
    local id="$1"
    local formatted_id

    while true; do
        formatted_id=$(printf "%03d" "$id")
        if [ ! -e "$OUTDIR/fatiado_${formatted_id}.wav" ]; then
            echo "$id"
            return 0
        fi
        id=$((id + 1))
    done
}

if [ -n "$START_ID" ]; then
    CURRENT_ID=$(proximo_id_livre "$((10#$START_ID))")
else
    CURRENT_ID=$(proximo_id_livre 1)
fi

echo "Arquivo de entrada: $INPUT_FILE"
echo "Pasta de saida: $OUTDIR"
echo "Primeiro ID de saida: $(printf "%03d" "$CURRENT_ID")"
echo "Padrao de saida: ${TARGET_SAMPLE_RATE} Hz, ${TARGET_CHANNELS} canal(is), ${TARGET_CODEC}"
echo "Loudness por fragmento: I=${LOUDNORM_I} LUFS, TP=${LOUDNORM_TP} dB, LRA=${LOUDNORM_LRA}"
echo "Threshold de silencio: $SILENCE_THRESHOLD"
echo "Duracao minima de silencio para corte: ${SILENCE_DURATION}s"
echo "Duracao minima do fragmento salvo: ${MIN_FRAGMENT_DURATION}s"

STANDARD_INPUT="$TMPDIR/entrada_padronizada.wav"
echo "Padronizando arquivo grande antes do fatiamento..."
ffmpeg \
    -hide_banner \
    -nostdin \
    -y \
    -i "$INPUT_FILE" \
    -map_metadata -1 \
    -ac "$TARGET_CHANNELS" \
    -ar "$TARGET_SAMPLE_RATE" \
    -c:a "$TARGET_CODEC" \
    "$STANDARD_INPUT" \
    -loglevel error

FFMPEG_THRESHOLD="${SILENCE_THRESHOLD%d}dB"
REPORT="$WORKDIR/silencios_$(date +%Y%m%d_%H%M%S).log"
echo "Gerando relatorio de silencios: $REPORT"
ffmpeg -hide_banner -nostats -i "$STANDARD_INPUT" -af "silencedetect=n=${FFMPEG_THRESHOLD}:d=${SILENCE_DURATION}" -f null - >"$REPORT" 2>&1

if [ "$DRY_RUN" = "1" ]; then
    echo "DRY_RUN=1: arquivo temporario padronizado e relatorio gerados, nenhum fragmento foi salvo."
    echo "Revise as linhas silence_start/silence_end em: $REPORT"
    exit 0
fi

echo "Iniciando fatiamento..."
sox "$STANDARD_INPUT" "$TMPDIR/temp_.wav" silence 1 "$SILENCE_DURATION" "$SILENCE_THRESHOLD" 1 "$SILENCE_DURATION" "$SILENCE_THRESHOLD" : newfile : restart

# Validação do SoX
COUNT=$(find "$TMPDIR" -maxdepth 1 -name "temp_*.wav" | wc -l)
echo "SoX gerou $COUNT arquivos temporários."

if [ "$COUNT" -eq 0 ]; then
    echo "Erro: Nenhum arquivo gerado. O audio nao possui silencios que correspondam aos parametros (${SILENCE_THRESHOLD}, ${SILENCE_DURATION}s)."
    exit 1
fi

echo "Iniciando conversão e normalização..."
for temp_file in "$TMPDIR"/temp_*.wav; do
    [ -e "$temp_file" ] || continue

    # LC_ALL=C garante que a saída use ponto em vez de vírgula decimal
    DURATION=$(LC_ALL=C ffprobe -i "$temp_file" -show_entries format=duration -v quiet -of csv="p=0")
    
    # Validação com awk (não depende do pacote bc)
    if awk -v dur="$DURATION" -v min="$MIN_FRAGMENT_DURATION" 'BEGIN { exit (dur < min ? 0 : 1) }'; then
        echo "Descartado (curto demais): $(basename "$temp_file") - ${DURATION}s"
        continue 
    fi

    CURRENT_ID=$(proximo_id_livre "$CURRENT_ID")
    FORMATTED_ID=$(printf "%03d" "$CURRENT_ID")
    FINAL_FILE="$OUTDIR/fatiado_${FORMATTED_ID}.wav"

    ffmpeg \
        -hide_banner \
        -nostdin \
        -n \
        -i "$temp_file" \
        -map_metadata -1 \
        -af "loudnorm=I=${LOUDNORM_I}:TP=${LOUDNORM_TP}:LRA=${LOUDNORM_LRA}" \
        -ac "$TARGET_CHANNELS" \
        -ar "$TARGET_SAMPLE_RATE" \
        -c:a "$TARGET_CODEC" \
        "$FINAL_FILE" \
        -loglevel error

    FINAL_INFO=$(ffprobe -v error -select_streams a:0 -show_entries stream=sample_rate,channels,bits_per_sample,codec_name -of csv=p=0 "$FINAL_FILE")
    EXPECTED_INFO="${TARGET_CODEC},${TARGET_SAMPLE_RATE},${TARGET_CHANNELS},16"
    if [ "$FINAL_INFO" != "$EXPECTED_INFO" ]; then
        echo "Erro: arquivo fora do padrao esperado: $FINAL_FILE"
        echo "Esperado: $EXPECTED_INFO"
        echo "Obtido:   $FINAL_INFO"
        exit 1
    fi

    echo "Salvo: fatiado_${FORMATTED_ID}.wav"
    CURRENT_ID=$((CURRENT_ID + 1))
done

if [ "$ARCHIVE_INPUT" = "1" ]; then
    mv "$INPUT_FILE" "$WORKDIR/processado_$(date +%Y%m%d_%H%M%S).wav"
fi

echo "Processamento concluído."
