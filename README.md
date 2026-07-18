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
- A quantidade de fragmentos até agora é por volta de 200.
- O tempo total de audio útil ainda é menos que 12 minutos. O ideal é no minimo meia hora.
- Grande parte dos arquivos estão limpos mas alguns aind apossuí residuo de algum som que ocorreu durante a fala.


