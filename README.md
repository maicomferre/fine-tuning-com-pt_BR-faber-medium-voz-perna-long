# fine-tuning-com-pt_BR-faber-medium-voz-perna-long
Treinamento de modelo com voz do perna longa 

### Informações
Modelo: pt_BR-faber-medium
Tamanho: ~63.2 MB

### Sequencia de processamento dos audios
- Foram obtidos da internet, grande maioria do youtube com o  ./yt-dlp -x --audio-format mp3 link
- Em seguida foram processados com [UVR GUI]([https://openai.com](https://github.com/Anjok07/ultimatevocalremovergui/)) usando modelo *UVR-MDX-NET-Voc_FT*
- Abri o Kdenlive e fui separando o audio do _Perna Longa_ dos demais personagens manualmente.
- Em seguida eu deixei no editor de vídeo os audios lá separados com espaço entre eles.
- Fiz a renderização dos audios em .wav em um unico audio grande
- Usei o processar_vozes.sh para identificar o espaço entre os audios e gerar os fragmentos.
- Com isso usei o Audacity para o refinamento final e tentar remover algumas informações.


### Tempo de audio e qualidade
- Auditoria feita em 2026-07-19 com `ffprobe`/`soxi`.
- Total atual: **183 arquivos WAV** em `dataset/wav`, batendo com **183 entradas** em `dataset/metadata.csv`.
- Tempo total de audio atual: **00:09:24,50**.
- Tempo atualmente dentro dos requisitos mínimos do pipeline: **00:09:19,23**.
- Requisitos mínimos usados para o `pt_BR-faber-medium`: WAV PCM signed 16-bit (`pcm_s16le`), **mono**, **22050 Hz** e fragmento com pelo menos **1s**.
- Arquivos que cumprem todos os requisitos mínimos: **177/183**.
- Arquivos fora do requisito mínimo: **6/183**.
  - **6** arquivos têm menos de 1s: `fatiado_020`, `fatiado_027`, `fatiado_030`, `fatiado_032`, `fatiado_033`, `fatiado_037`.
- Todos os arquivos estão em 22050 Hz, mono, PCM 16-bit e todos possuem transcrição não vazia no metadata.
- O volume ainda está abaixo do ideal para fine-tuning: o alvo mínimo prático continua sendo **30 minutos ou mais** de áudio limpo, mono e em 22050 Hz.
- Grande parte dos arquivos está limpa, mas alguns ainda podem conter resíduos de som durante a fala; a próxima ação técnica é decidir se os 6 fragmentos abaixo de 1s serão mantidos, unidos a outros trechos ou removidos do metadata.
