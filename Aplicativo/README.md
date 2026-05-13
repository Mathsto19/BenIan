# BenIan - Aplicativo Windows

Esta pasta e destinada a versao empacotada do **BenIan** para Windows e aos arquivos de exemplo para uso final.

Se a distribuicao recebida incluir `BenIan.exe`, use o executavel diretamente. Se o executavel ainda nao estiver presente, rode o sistema pelo codigo fonte em `..\Codigo Fonte\BenIan.py`.

---

## Compatibilidade

| Sistema Operacional | Executavel |
|---------------------|------------|
| Windows 10/11       | `BenIan.exe`, quando disponivel |

Esta documentacao cobre apenas o uso no Windows.

---

## Estrutura Esperada

```text
Aplicativo/
|-- BenIan.exe              (quando a versao empacotada for distribuida)
|-- README.md
`-- exemplo/
    |-- exemplo.zip
    |-- exemplo.json
    `-- README.md
```

Na copia atual do repositorio, a pasta `exemplo/` ja esta disponivel para teste.

---

## Como Inicializar

### Usando o executavel

1. Abra a pasta `Aplicativo`.
2. Execute `BenIan.exe`.
3. Se o Windows SmartScreen bloquear a abertura, clique em `Mais informacoes` e depois em `Executar assim mesmo`.
4. Aguarde a interface abrir no navegador.

### Sem executavel

Use a versao pelo codigo fonte:

```powershell
cd "..\Codigo Fonte"
python -m pip install -r requirements.txt
python BenIan.py
```

---

## Como Utilizar

### 1. Carregar imagens

- Clique em `Carregar`.
- Em `Pacote`, selecione um arquivo `.zip` ou uma pasta com imagens.
- Para testar com o exemplo, use:

```text
exemplo\exemplo.zip
```

### 2. Carregar anotacoes existentes

O campo `Resultado JSON` e opcional. Quando existir uma anotacao anterior, selecione o arquivo JSON correspondente.

Para testar com o exemplo:

```text
exemplo\exemplo.json
```

### 3. Escolher pasta de saida

Selecione a pasta onde o BenIan deve salvar os arquivos revisados. Se estiver usando o executavel, a saida padrao fica na pasta `saida` ao lado do aplicativo.

### 4. Revisar imagens

- Confira a imagem atual.
- Ajuste os rotulos no painel lateral.
- Informe severidade de 1 a 5 para os rotulos selecionados.
- Use `Original`, `Camada 1 (A)` e `Camada 2 (R)` para comparar visualizacoes.

### 5. Salvar decisao

- `Salvar revisão`: salva a revisao da imagem atual.
- `Limpar`: remove os rotulos selecionados.
- `Original`: restaura os rotulos importados do JSON.

---

## Saidas Geradas

O BenIan gera os seguintes arquivos na pasta de saida:

| Arquivo | Finalidade |
|---------|------------|
| `revisoes.json` | Historico completo das revisoes, incluindo se houve mudanca de rotulo. |
| `resultado_benian.json` | JSON revisado no mesmo formato base do resultado carregado, com os rotulos corrigidos. |

Guarde a pasta de saida junto com o pacote analisado quando precisar auditar ou continuar o trabalho posteriormente.

---

## Atalhos

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

Tambem e possivel usar a roda do mouse para zoom e arrastar a imagem quando ela estiver ampliada.

---

## Requisitos Tecnicos

- Windows 10 ou Windows 11.
- Memoria RAM recomendada: 8 GB.
- Navegador instalado.
- Espaco em disco suficiente para extrair pacotes `.zip`, gerar cache visual temporario e salvar os dois JSONs de resultado.

Quando estiver usando `BenIan.exe`, nao e necessario instalar Python manualmente. Quando estiver usando o codigo fonte, instale Python 3.10+ e as dependencias de `requirements.txt`.

---

## Suporte

Em caso de duvidas, sugestoes ou problemas tecnicos:

- matheusaugustooliveira@alunos.utfpr.edu.br
