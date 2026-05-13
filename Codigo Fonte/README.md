# BenIan - Codigo Fonte

Este diretorio contem o codigo principal do **BenIan**, software local para revisao e correcao de anotacoes de qualidade em imagens de digitais neonatais.

A execucao documentada aqui e para Windows. O programa e iniciado por Python, cria um servidor local em `127.0.0.1` e abre a interface no navegador.

---

## Estrutura

```text
Codigo Fonte/
|-- BenIan.py
|-- requirements.txt
|-- README.md
|-- exemplo/
|   |-- exemplo.zip
|   |-- exemplo.json
|   `-- README.md
`-- Imagens/
    |-- icon.png
    `-- logo_texto.png
```

Arquivos principais:

- `BenIan.py`: aplicacao principal.
- `requirements.txt`: dependencias necessarias para rodar pelo codigo fonte.
- `Imagens/icon.png`: icone usado pelo aplicativo.
- `Imagens/logo_texto.png`: logo exibida no topo da interface.
- `exemplo/`: pacote de teste para validar o fluxo.

---

## Requisitos

- Windows 10 ou Windows 11.
- Python 3.10 ou superior.
- Navegador instalado.
- Permissao de leitura nos pacotes de imagem e escrita na pasta de saida.

Instale as dependencias com:

```powershell
python -m pip install -r requirements.txt
```

Dependencia atual:

- `Pillow>=10.0.0`

---

## Como Executar

Entre nesta pasta:

```powershell
cd "C:\Users\mathe\Downloads\BenIan\Codigo Fonte"
```

Execute:

```powershell
python BenIan.py
```

O BenIan abre automaticamente no navegador. A URL padrao e:

```text
http://127.0.0.1:8877
```

Se a porta `8877` estiver ocupada, o sistema tenta outra porta proxima.

---

## Execucao com Arquivos Pre-carregados

Para iniciar o BenIan ja com um pacote e um JSON de anotacoes:

```powershell
python BenIan.py --origem "C:\caminho\pacote.zip" --resultado "C:\caminho\resultado.json" --saida "C:\caminho\saida"
```

Parametros disponiveis:

| Parametro | Descricao |
|-----------|-----------|
| `--host` | Host local do servidor. Padrao: `127.0.0.1`. |
| `--porta` | Porta local. Padrao: `8877`. |
| `--origem` | `.zip` ou pasta com imagens para carregar ao iniciar. |
| `--resultado` | JSON opcional com anotacoes existentes. |
| `--saida` | Pasta onde os resultados serao salvos. |
| `--nao-abrir` | Nao abre o navegador automaticamente. |

---

## Teste Rapido

1. Execute `python BenIan.py`.
2. Clique em `Carregar`.
3. Em `Pacote`, selecione:

```text
exemplo\exemplo.zip
```

4. Em `Resultado JSON`, selecione:

```text
exemplo\exemplo.json
```

5. Escolha uma pasta de saida.
6. Clique em `Carregar`.

O exemplo contem imagens e rotulos para testar o fluxo completo de revisao.

---

## Fluxo de Uso

1. Carregue um `.zip` ou pasta com imagens.
2. Carregue um JSON de anotacoes, se existir.
3. Revise cada imagem.
4. Ajuste os rotulos e severidades.
5. Clique em `Salvar revisão`.
6. Use os arquivos JSON exportados na pasta de saida.

---

## Rotulos Padrao

- Digital Clara
- Digital Escura
- Dedo Fora da Area
- Fiapos
- Fora de Foco
- Manchas
- Scanner Sujo
- Segmentacao Boa
- Sem Padrao Visivel

Cada rotulo pode receber severidade de 1 a 5 quando selecionado.

---

## Saidas Geradas

Os resultados sao salvos na pasta escolhida na tela de carregamento ou pelo parametro `--saida`.

Arquivos gerados:

- `revisoes.json`: historico completo das revisoes, informando se os rotulos foram mantidos ou alterados.
- `resultado_benian.json`: JSON revisado no mesmo formato base do resultado carregado, com os rotulos corrigidos.

Quando nenhuma pasta e informada, a saida padrao e:

```text
Codigo Fonte\saida\
```

---

## Atalhos da Interface

| Atalho | Acao |
|--------|------|
| `Seta direita` | Proxima imagem. |
| `Seta esquerda` | Imagem anterior. |
| `S` | Salvar revisão. |
| `1` | Camada 1. |
| `2` | Camada 2. |
| `O` | Imagem original. |
| `+` ou `=` | Aumentar zoom. |
| `-` ou `_` | Diminuir zoom. |
| `0` | Resetar zoom. |
| `Esc` | Abrir/fechar confirmacao de saida. |

---

## Observacoes de Desenvolvimento

- O aplicativo usa apenas servidor local HTTP, sem backend remoto.
- A pasta de saida recebe apenas `revisoes.json` e `resultado_benian.json`.
- As imagens temporarias de visualizacao ficam no diretorio temporario do sistema.
- O arquivo `logo_texto.png` pode ser substituido para alterar a marca exibida na interface.
- Evite remover a estrutura de `Imagens/`, pois ela e usada pela interface.

---

## Suporte

Em caso de duvidas, sugestoes ou problemas tecnicos:

- matheusaugustooliveira@alunos.utfpr.edu.br
