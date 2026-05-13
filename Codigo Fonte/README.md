# BenIan - Codigo Fonte

Esta pasta contem a implementacao principal do BenIan.

## Arquivos

- `BenIan.py`: aplicacao principal em Python/PyQt6.
- `Requeriments.txt`: dependencias necessarias para rodar o sistema.
- `Fotos/`: logos e imagens usadas na interface.
- `Exemplos/catalogo_erros.json`: catalogo inicial de erros.
- `BENIAN/`: pasta criada em tempo de execucao para armazenar `resultado.json`.

## Preparacao

```powershell
pip install -r Requeriments.txt
```

## Execucao

```powershell
python BenIan.py
```

## Uso basico

1. Clique em `Carregar ZIP` e selecione um pacote de imagens.
2. Navegue pelas imagens com os botoes ou pelas setas do teclado.
3. Use `Cores` e os botoes `1`, `2`, `3`, `4` para alternar filtros e camadas quando disponiveis.
4. Use `Personalizar Erros` para ajustar o catalogo.
5. Use `Erro` para marcar os problemas encontrados.
6. Use `Avaliacao` para atribuir notas de 1 a 5.
7. Clique em `Salvar` para gravar a anotacao em `BENIAN/resultado.json`.

## Dependencias

- Python 3.10 ou superior.
- PyQt6.
- OpenCV.
- NumPy.
