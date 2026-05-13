# BenIan

Software para rotulagem, inspecao e avaliacao de imagens biometricas, estruturado a partir da base do BENAPRO.

O repositorio contem a versao de desenvolvimento em Python e uma pasta reservada para o aplicativo empacotado. Artefatos pesados, como executaveis, manuais em PDF/ZIP, audio e pacotes ZIP de exemplo, ficaram fora desta primeira base.

## Estrutura

```text
BenIan/
|-- Aplicativo/
|   |-- README.md
|   `-- catalogo_erros.json
|-- Codigo Fonte/
|   |-- BenIan.py
|   |-- Requeriments.txt
|   |-- README.md
|   |-- Exemplos/
|   `-- Fotos/
|-- LICENSE
`-- README.md
```

## Funcionalidades principais

- Carregamento de imagens por arquivo ZIP.
- Navegacao sequencial entre imagens.
- Visualizacao com zoom, arraste, filtros e camadas RGBA.
- Cadastro e edicao do catalogo de erros.
- Selecao de erros por imagem.
- Avaliacao por severidade de 1 a 5.
- Exportacao das anotacoes em `BENIAN/resultado.json`.

## Como executar pelo codigo fonte

```powershell
cd "Codigo Fonte"
pip install -r Requeriments.txt
python BenIan.py
```

O aplicativo cria a pasta `BENIAN/` automaticamente para salvar os resultados.

## Proximos passos de produto

- Ajustar identidade visual final do BenIan, caso ela seja diferente da base do BENAPRO.
- Validar o catalogo de erros padrao.
- Criar build Windows em `Aplicativo/` quando o comportamento do codigo fonte estiver fechado.
- Gerar manual proprio do BenIan depois que a interface estiver estabilizada.
