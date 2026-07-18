#!/bin/bash

WORKDIR="/home/maicom/Documentos/estudo/programacao/Machine.Learning/perna.longa/vozes/compilado"
INPUT_FILE="${1:-$WORKDIR/sem título.wav}"
OUTDIR="${OUTDIR:-$WORKDIR/normalizados}"

# Ajuste principal do fatiamento:
# - deixe no Kdenlive espacos de 1.5s a 2s entre falas que devem virar arquivos separados;
# - pausas menores que isso ficam dentro do mesmo fragmento.
SILENCE_DURATION="${SILENCE_DURATION:-1.2}"
SILENCE_THRESHOLD="${SILENCE_THRESHOLD:--55d}"
MIN_FRAGMENT_DURATION="${MIN_FRAGMENT_DURATION:-1.0}"
DRY_RUN="${DRY_RUN:-0}"
ARCHIVE_INPUT="${ARCHIVE_INPUT:-1}"
START_ID="${START_ID:-}"

if [ ! -f "$INPUT_FILE" ]; then
    echo "Erro: '$INPUT_FILE' não encontrado."
    exit 1
fi

mkdir -p "$OUTDIR"
TMPDIR=$(mktemp -d "$WORKDIR/tmp_slices.XXXXXX")
trap 'rm -rf "$TMPDIR"' EXIT

if [ -n "$START_ID" ]; then
    NEXT_ID=$((10#$START_ID))
else
    MAX_ID=$(find "$OUTDIR" -name "fatiado_*.wav" | awk -F'[_.]' '{print $(NF-1)}' | sort -n | tail -1)
    if [ -z "$MAX_ID" ]; then
        NEXT_ID=1
    else
        NEXT_ID=$((MAX_ID + 1))
    fi
fi

echo "Arquivo de entrada: $INPUT_FILE"
echo "Pasta de saida: $OUTDIR"
echo "Primeiro ID de saida: $(printf "%03d" "$NEXT_ID")"
echo "Threshold de silencio: $SILENCE_THRESHOLD"
echo "Duracao minima de silencio para corte: ${SILENCE_DURATION}s"
echo "Duracao minima do fragmento salvo: ${MIN_FRAGMENT_DURATION}s"

FFMPEG_THRESHOLD="${SILENCE_THRESHOLD%d}dB"
REPORT="$WORKDIR/silencios_$(date +%Y%m%d_%H%M%S).log"
echo "Gerando relatorio de silencios: $REPORT"
ffmpeg -hide_banner -nostats -i "$INPUT_FILE" -af "silencedetect=n=${FFMPEG_THRESHOLD}:d=${SILENCE_DURATION}" -f null - >"$REPORT" 2>&1

if [ "$DRY_RUN" = "1" ]; then
    echo "DRY_RUN=1: relatorio gerado, nenhum arquivo foi fatiado."
    echo "Revise as linhas silence_start/silence_end em: $REPORT"
    exit 0
fi

echo "Iniciando fatiamento..."
sox "$INPUT_FILE" "$TMPDIR/temp_.wav" silence 1 "$SILENCE_DURATION" "$SILENCE_THRESHOLD" 1 "$SILENCE_DURATION" "$SILENCE_THRESHOLD" : newfile : restart

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

    FORMATTED_ID=$(printf "%03d" $NEXT_ID)
    FINAL_FILE="$OUTDIR/fatiado_${FORMATTED_ID}.wav"

    ffmpeg -i "$temp_file" -af "loudnorm=I=-16:TP=-1.5:LRA=11" -ac 1 -ar 22050 -c:a pcm_s16le -y "$FINAL_FILE" -loglevel error
    
    echo "Salvo: fatiado_${FORMATTED_ID}.wav"
    NEXT_ID=$((NEXT_ID + 1))
done

if [ "$ARCHIVE_INPUT" = "1" ]; then
    mv "$INPUT_FILE" "$WORKDIR/processado_$(date +%Y%m%d_%H%M%S).wav"
fi

echo "Processamento concluído."
