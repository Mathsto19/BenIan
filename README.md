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

## Quick Start

```powershell
# 1. Vá para a pasta do código
cd "Codigo Fonte"

# 2. Instale as dependências
pip install -r requirements.txt

# 3. Execute o aplicativo
python BenIan.py

# 4. Use o exemplo fornecido
#    Carregue: Codigo Fonte/exemplo/exemplo.zip
#    Com rótulos de: Codigo Fonte/exemplo/exemplo.json
```

Para entender melhor, veja o `README.md` em `Codigo Fonte/exemplo/`.

## Estrutura

```text
BenIan/
|-- Codigo Fonte/              (código principal)
|   |-- BenIan.py
|   |-- requirements.txt
|   |-- README.md
|   |-- exemplo/               (exemplo completo com ZIP + JSON)
|   |   |-- exemplo.zip
|   |   |-- exemplo.json
|   |   `-- README.md
|   `-- Imagem/
|       |-- icon.png
|       `-- logo_texto.png
|-- Aplicativo/                (referência e exemplos)
|   `-- exemplo/               (exemplo completo com ZIP + JSON)
|       |-- exemplo.zip
|       |-- exemplo.json
|       `-- README.md
|-- LICENSE
`-- README.md
```

O código fica em `Codigo Fonte/BenIan.py`. As imagens estão em `Codigo Fonte/Imagem/`.

Para entender como usar, veja os exemplos em `Codigo Fonte/exemplo/` ou `Aplicativo/exemplo/`.

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
- `resultado.json` (anotações pré-existentes), opcional.
- Seleção por diálogo local do Windows na tela de carregamento.

Para exemplos de formato, veja `Aplicativo/exemplo/`.

## Saídas

Quando você salva anotações, o BenIan cria os arquivos de resultado:

- `revisoes.json`: registro completo das revisões (histórico).
- `rotulos_confirmados.csv`: correções salvas como confirmadas.
- `rotulos_corrigir.csv`: imagens marcadas para revisar depois.
- `resultado_benian.json`: saída em formato similar ao `resultado.json` de entrada.

Os arquivos são salvos na pasta de saída que você especificar durante a execução.

## Navegação

### Teclado
- **Seta direita** (→): próxima imagem.
- **Seta esquerda** (←): imagem anterior.
- `S`: salvar correção.
- `N`: revisar depois.
- `1`, `2`: alternar camadas.
- `O`: imagem original.
- `+`, `-`, `0`: zoom.
- `ESC`: sair do aplicativo.

### Interface
- Botões **◀** e **▶** embaixo da imagem para navegar
- Mostra a posição atual (ex: "5 / 20")
- Botões na toolbar de cima também disponíveis

## Logo

Para trocar o texto `BenIan` por uma imagem sem fundo, coloque o arquivo como `logo_texto.png` em `Codigo Fonte/Imagem/`.
