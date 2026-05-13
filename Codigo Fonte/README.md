# BenIan - Código Fonte

O BenIan agora tem toda a estrutura organizada nesta pasta:

```text
Codigo Fonte/
|-- BenIan.py              (arquivo principal)
|-- requirements.txt       (dependências)
|-- README.md             (este arquivo)
`-- Imagem/               (imagens do aplicativo)
    |-- icon.png
    `-- logo_texto.png
```

## Como executar

```powershell
pip install -r requirements.txt
python BenIan.py
```

O aplicativo iniciará em modo fullscreen no navegador:

```text
http://127.0.0.1:8877
```

## Dependências

As dependências estão listadas em `requirements.txt`. Instale com:

```powershell
pip install -r requirements.txt
```

Principais dependências:
- **Pillow** (>=10.0.0): Processamento de imagens
- Python 3.10+: Requerido

## Recursos

- Interface web em modo fullscreen/aplicativo
- Servidor HTTP local automático
- Processamento de imagens com filtros
- Suporte a pacotes ZIP e pastas
- Exportação em JSON e CSV

