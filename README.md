# BenIan

Repositório do Software BenIan - Correção de anotação de imagens de digitais neonatais.

O BenIan é um aplicativo local em Python com interface web. Ao iniciar, ele sobe um servidor HTTP local e abre o navegador em modo aplicativo/tela cheia, mantendo o fluxo simples para empacotar como executável Windows.

## Objetivo

O software serve para revisar e corrigir anotações de qualidade em imagens biométricas neonatais. O fluxo principal é:

1. Carregar um ZIP ou uma pasta de imagens.
2. Carregar anotações existentes, quando houver.
3. Revisar imagem por imagem.
4. Ajustar rótulos e severidade.
5. Exportar as correções em JSON e CSV.

## Estrutura

```text
BenIan/
|-- Codigo Fonte/
|   |-- BenIan.py
|   |-- requirements.txt
|   |-- README.md
|   `-- Imagem/
|       |-- icon.png
|       `-- logo_texto.png
|-- dados/
|   `-- saida/
|       |-- resultado_benian.json
|       |-- revisoes.json
|       |-- rotulos_confirmados.csv
|       |-- rotulos_corrigir.csv
|       `-- entrada/
|-- LICENSE
`-- README.md
```

Todo o código do aplicativo fica em `Codigo Fonte/BenIan.py`. As imagens (logo e ícone) estão em `Codigo Fonte/Imagem/` para melhor organização.

## Como rodar em desenvolvimento

```powershell
cd "Codigo Fonte"
pip install -r requirements.txt
python BenIan.py
```

Por padrão o app abre em:

```text
http://127.0.0.1:8877
```

Para iniciar já com um pacote:

```powershell
python BenIan.py --origem "C:\caminho\pacote.zip" --resultado "C:\caminho\resultado.json"
```

## Entradas

O BenIan aceita:

- Arquivo `.zip` com imagens.
- Pasta com imagens.
- Pasta de pacote contendo um `.zip` e `BENAPRO/resultado.json`.
- `resultado.json` do BENAPRO/BENIAN, opcional.
- Seleção por diálogo local do Windows na tela de carregamento.

Quando o pacote for ZIP, as imagens são extraídas para a pasta de saída em:

```text
dados/saida/entrada/pacotes
```

## Saídas

Por padrão, o BenIan grava em `dados/saida`:

- `revisoes.json`: registro completo das revisões.
- `rotulos_confirmados.csv`: correções salvas como confirmadas.
- `rotulos_corrigir.csv`: imagens marcadas para revisar depois.
- `resultado_benian.json`: saída em formato próximo ao `resultado.json`.
- `cache_visual/`: imagens temporárias usadas para filtros e camadas.

## Atalhos

- Seta direita: próxima imagem.
- Seta esquerda: imagem anterior.
- `S`: salvar correção.
- `N`: revisar depois.
- `1`, `2`: alternar camadas.
- `O`: imagem original.
- `+`, `-`, `0`: zoom.

## Logo

Para trocar o texto `BenIan` por uma imagem sem fundo, coloque o arquivo como `logo_texto.png` em `Codigo Fonte/Imagem/`.

## Gerar executável

```powershell
.\scripts\build_exe.ps1
```

O executável será gerado em:

```text
dist/BenIan.exe
```
