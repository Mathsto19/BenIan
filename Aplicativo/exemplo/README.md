# Exemplo de Uso - BenIan

Esta pasta contém um exemplo real com dados de teste para você entender como usar o BenIan.

## Arquivos de Exemplo

```text
exemplo/
|-- exemplo.zip             (arquivo compactado com imagens de teste)
|-- exemplo.json            (arquivo com rótulos e anotações de exemplo)
`-- README.md              (este arquivo)
```

## Como testar

1. Abra o BenIan a partir de `Codigo Fonte/`:
```powershell
cd "..\Codigo Fonte"
python BenIan.py
```

2. Na tela de carregamento:
   - **Pacote**: Clique em **"ZIP"** e selecione `exemplo.zip`
   - **Resultado**: Clique em **"Procurar"** e selecione `exemplo.json`

3. Clique em **"Carregar"** para começar

## O que você vai ver

- Imagens do arquivo ZIP carregadas
- Rótulos pré-existentes do arquivo JSON
- Interface para revisar e corrigir as anotações
- Opções de salvar ou revisar depois

## Formato dos Arquivos

### exemplo.zip
Arquivo compactado contendo imagens biométricas organizadas em pastas por dedo/tipo.

### exemplo.json
Estrutura de anotações:
```json
{
  "itens": [
    {
      "id": "identificador",
      "chave": "dedo_01_frame_01",
      "arquivo": "nome_da_imagem.png",
      "status_revisao": "pendente|confirmado|corrigir",
      "rotulos_corrigidos": ["Rótulo 1", "Rótulo 2"],
      "severidades": {
        "Rótulo 1": 1,
        "Rótulo 2": 2
      }
    }
  ]
}
```

## Rótulos Disponíveis

- Digital Clara
- Digital Escura
- Dedo Fora da Área
- Fiapos
- Fora de Foco
- Manchas
- Scanner Sujo
- Segmentação Boa
- Sem Padrão Visível

## Navegação e Atalhos

### Interface Visual
- Clique nos botões **◀** e **▶** embaixo da imagem para navegar
- Os botões mostram a posição atual (ex: "5 / 20")

### Teclado
- **Seta direita** (→): próxima imagem
- **Seta esquerda** (←): imagem anterior
- `S`: salvar correção
- `N`: revisar depois
- `1`, `2`: alternar camadas
- `O`: imagem original
- `+`, `-`, `0`: controlar zoom

## Próximos Passos

Após testar com este exemplo, você pode:
1. Carregar seus próprios arquivos ZIP
2. Adicionar arquivo JSON com anotações existentes
3. Revisar e corrigir cada imagem
4. Exportar resultados em JSON e CSV

