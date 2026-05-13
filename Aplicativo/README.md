# BenIan - Aplicativo

Esta pasta fica reservada para a versao empacotada do BenIan no Windows.

No momento, o repositorio esta preparado para desenvolvimento pelo codigo fonte. Depois que a interface e o fluxo forem validados, o executavel pode ser gerado e colocado aqui, junto com os assets necessarios.

## Estrutura esperada para build futuro

```text
Aplicativo/
|-- BenIan.exe
|-- catalogo_erros.json
`-- BENIAN/
    `-- resultado.json
```

Enquanto o executavel nao for gerado, use:

```powershell
cd "..\Codigo Fonte"
python BenIan.py
```
