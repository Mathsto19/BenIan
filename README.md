# BenIan - Correcao de Anotacoes de Digitais Neonatais

Bem-vindo ao **BenIan**, um software desenvolvido para revisar, corrigir e padronizar anotacoes de qualidade em imagens de impressoes digitais neonatais.

O BenIan funciona localmente no Windows. Ao iniciar, ele sobe um servidor HTTP em `127.0.0.1` e abre a interface no navegador em modo aplicativo/tela cheia. Nenhum dado precisa ser enviado para servidor externo.

Este repositorio reune:

- **Codigo fonte em Python** para execucao, manutencao e evolucao do projeto.
- **Area de aplicativo Windows** para distribuicao empacotada e exemplos de uso.

---

## Sobre o Projeto

O BenIan foi criado para apoiar a revisao de anotacoes de qualidade em bases de biometria neonatal. Em vez de apenas aceitar uma classificacao automatica ou manual anterior, a ferramenta permite que o avaliador confira imagem por imagem, ajuste os rotulos, informe severidades e exporte resultados consistentes para pesquisa.

A ferramenta permite:

- carregamento de imagens por arquivo `.zip` ou pasta local;
- importacao opcional de anotacoes existentes em JSON;
- revisao sequencial das imagens;
- correcao de rotulos de qualidade;
- avaliacao de severidade de 1 a 5;
- visualizacao da imagem original e de camadas auxiliares;
- exportacao rastreavel em JSON.

Com isso, o BenIan auxilia na formacao de datasets mais confiaveis para estudos de qualidade, segmentacao e reconhecimento biometrico neonatal.

---

## Compatibilidade

| Sistema Operacional | Execucao principal | Executavel |
|---------------------|-------------------|------------|
| Windows 10/11       | `BenIan.py`       | `BenIan.exe`, quando empacotado |

> Este projeto esta documentado apenas para Windows.

---

## Estrutura do Repositorio

```text
BenIan/
|-- Aplicativo/
|   |-- README.md
|   `-- exemplo/
|       |-- exemplo.zip
|       |-- exemplo.json
|       `-- README.md
|-- Codigo Fonte/
|   |-- BenIan.py
|   |-- requirements.txt
|   |-- README.md
|   |-- exemplo/
|   |   |-- exemplo.zip
|   |   |-- exemplo.json
|   |   `-- README.md
|   `-- Imagens/
|       |-- icon.png
|       `-- logo_texto.png
|-- LICENSE
`-- README.md
```

---

## Componentes

### 1. Codigo Fonte

Contem a implementacao principal do BenIan.

Arquivos principais:

- `Codigo Fonte/BenIan.py`: aplicacao principal.
- `Codigo Fonte/requirements.txt`: dependencias Python.
- `Codigo Fonte/Imagens/`: icone e logo usados na interface.
- `Codigo Fonte/exemplo/`: pacote de teste com imagens e anotacoes.

Manual especifico:

- `Codigo Fonte/README.md`

### 2. Aplicativo

Pasta destinada a versao empacotada para Windows e aos arquivos de exemplo para uso final. Se a distribuicao recebida ja incluir `BenIan.exe`, ele deve ser executado diretamente por essa pasta. Caso contrario, use a execucao pelo codigo fonte.

Manual especifico:

- `Aplicativo/README.md`

---

## Funcionalidades Principais

- **Carregamento por ZIP ou pasta**: aceita pacotes compactados e diretorios contendo imagens.
- **Importacao de anotacoes**: carrega um `resultado.json` ou arquivo equivalente com rotulos existentes.
- **Revisao assistida**: mostra a anotacao original e permite corrigir os rotulos finais.
- **Severidade por rotulo**: cada problema selecionado pode receber nota de 1 a 5.
- **Camadas de visualizacao**: alterna entre imagem original e camadas auxiliares disponiveis.
- **Navegacao rapida**: botoes de anterior/proxima, setas do teclado e contador de progresso.
- **Exportacao estruturada**: gera `revisoes.json` e `resultado_benian.json` para auditoria e reutilizacao.
- **Execucao local**: interface web local aberta automaticamente no Windows.

---

## Catalogo de Rotulos Padrao

| Rotulo | Descricao |
|--------|-----------|
| Digital Clara | Falta de pressao ou cristas pouco visiveis. |
| Digital Escura | Excesso de pressao ou cristas fundidas. |
| Dedo Fora da Area | Parte da digital ficou fora da area de captura. |
| Fiapos | Presenca de fibras ou fiapos sobre a digital. |
| Fora de Foco | Imagem com perda de nitidez ou movimento. |
| Manchas | Manchas, residuos ou descamacao entre as cristas. |
| Scanner Sujo | Sujeira ou contaminacao na superficie do sensor. |
| Segmentacao Boa | Imagem adequada para uso biometrico. |
| Sem Padrao Visivel | Nao ha padrao de cristas confiavel para analise. |

### Regras de consistencia

Durante a exportacao, o BenIan aplica algumas regras para evitar anotacoes contraditorias:

- `Segmentacao Boa` nao e mantida quando existe algum erro selecionado.
- `Dedo Fora da Area` com severidade 4 ou 5 prevalece sobre os demais rotulos.
- `Sem Padrao Visivel` com severidade 4 ou 5 remove outros erros, mantendo apenas `Digital Clara` ou `Digital Escura` quando tambem forem severidade 4 ou 5.

---

## Como Executar pelo Codigo Fonte

### 1. Entrar na pasta do codigo

```powershell
cd "C:\Users\mathe\Downloads\BenIan\Codigo Fonte"
```

### 2. Instalar dependencias

```powershell
python -m pip install -r requirements.txt
```

### 3. Executar o BenIan

```powershell
python BenIan.py
```

Por padrao, o aplicativo abre em:

```text
http://127.0.0.1:8877
```

Se a porta estiver ocupada, o BenIan tenta iniciar em uma porta proxima.

---

## Teste com o Exemplo Incluso

Depois de executar `python BenIan.py`:

1. Clique em `Carregar`.
2. Em `Pacote`, escolha `Codigo Fonte\exemplo\exemplo.zip`.
3. Em `Resultado JSON`, escolha `Codigo Fonte\exemplo\exemplo.json`.
4. Em `Pasta de saida`, escolha onde os arquivos revisados serao salvos.
5. Clique em `Carregar`.

O mesmo exemplo tambem esta disponivel em:

```text
Aplicativo\exemplo\
```

---

## Execucao com Parametros

O BenIan tambem pode iniciar ja carregando um pacote:

```powershell
python BenIan.py --origem "C:\caminho\pacote.zip" --resultado "C:\caminho\resultado.json" --saida "C:\caminho\saida"
```

Parametros uteis:

| Parametro | Funcao |
|-----------|--------|
| `--origem` | Caminho de um `.zip` ou pasta com imagens. |
| `--resultado` | Caminho opcional de um JSON com anotacoes existentes. |
| `--saida` | Pasta onde os resultados serao gravados. |
| `--porta` | Porta local do servidor. Padrao: `8877`. |
| `--nao-abrir` | Inicia o servidor sem abrir o navegador automaticamente. |

---

## Entradas

O BenIan aceita:

- arquivo `.zip` contendo imagens;
- pasta local contendo imagens;
- arquivo JSON opcional com anotacoes existentes;
- imagens nos formatos `.png`, `.jpg`, `.jpeg`, `.bmp`, `.tif`, `.tiff` e `.webp`.

Quando o JSON de resultado nao e informado manualmente, o sistema tambem tenta localizar arquivos conhecidos como:

```text
resultado.json
BENIAN\resultado.json
BENAPRO\resultado.json
```

---

## Saida de Dados

Ao salvar revisoes, o BenIan grava os resultados na pasta de saida selecionada. Os principais arquivos gerados sao:

| Arquivo | Conteudo |
|---------|----------|
| `revisoes.json` | Registro completo das revisoes feitas no BenIan, incluindo se houve mudanca de rotulo. |
| `resultado_benian.json` | JSON revisado no mesmo formato base do resultado carregado, com os rotulos corrigidos. |

Se nenhuma pasta de saida for escolhida, a saida padrao pelo codigo fonte fica em:

```text
Codigo Fonte\saida\
```

---

## Como Usar a Interface

### 1. Carregar dados

- Clique em `Carregar`.
- Selecione um `.zip` ou uma pasta de imagens.
- Opcionalmente selecione um JSON com anotacoes anteriores.
- Escolha a pasta de saida.
- Clique em `Carregar` para iniciar a revisao.

### 2. Revisar uma imagem

- Confira a imagem exibida.
- Marque ou desmarque os rotulos no painel lateral.
- Informe a severidade quando necessario.
- Use `Original`, `Camada 1 (A)` ou `Camada 2 (R)` para comparar visualizacoes.

### 3. Salvar decisao

- Clique em `Salvar revisão` para salvar a revisao.
- Clique em `Limpar` para remover os rotulos selecionados.
- Clique em `Original` para restaurar os rotulos vindos da anotacao carregada.

---

## Atalhos

| Atalho | Acao |
|--------|------|
| `Seta direita` | Proxima imagem. |
| `Seta esquerda` | Imagem anterior. |
| `S` | Salvar revisão. |
| `1` | Visualizar Camada 1. |
| `2` | Visualizar Camada 2. |
| `O` | Visualizar imagem original. |
| `+` ou `=` | Aumentar zoom. |
| `-` ou `_` | Diminuir zoom. |
| `0` | Restaurar zoom para 100%. |
| `Esc` | Abrir/fechar confirmacao de saida. |

Tambem e possivel usar a roda do mouse para zoom e clicar/arrastar a imagem quando ela estiver ampliada.

---

## Requisitos Tecnicos

- Sistema operacional: Windows 10 ou Windows 11.
- Python: 3.10 ou superior, para execucao pelo codigo fonte.
- Dependencia principal: Pillow 10+.
- Navegador instalado no Windows.
- Memoria RAM recomendada: 8 GB.
- Armazenamento: conforme o volume de imagens, pacotes `.zip` e resultados exportados.

---

## Suporte e Contato

Para duvidas, suporte tecnico ou colaboracoes:

- Matheus Augusto - [matheusaugustooliveira@alunos.utfpr.edu.br](mailto:matheusaugustooliveira@alunos.utfpr.edu.br)

---

## Agradecimentos

Este projeto foi desenvolvido na UTFPR com apoio das instituicoes:

- CNPq
- CAPES
- InfantID
- UTFPR - Campus Pato Branco

---

## Licenca

Distribuicao autorizada apenas para fins academicos, cientificos e de pesquisa. Uso comercial ou redistribuicao sem permissao nao e permitido.
