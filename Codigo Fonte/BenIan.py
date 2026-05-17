# -*- coding: utf-8 -*-

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import mimetypes
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import unicodedata
import webbrowser
import zipfile
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from PIL import Image, ImageEnhance, ImageOps


def obter_raiz_aplicativo() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent

    return Path(__file__).resolve().parent


def obter_raiz_recursos() -> Path:
    if getattr(sys, "frozen", False):
        caminho_temporario = getattr(sys, "_MEIPASS", None)
        if caminho_temporario:
            return Path(caminho_temporario).resolve()

    return Path(__file__).resolve().parent


RAIZ_REPOSITORIO = obter_raiz_aplicativo()
RAIZ_RECURSOS = obter_raiz_recursos()
PASTA_SAIDA_PADRAO = RAIZ_REPOSITORIO / "saida"

ROTULO_SEGMENTACAO_BOA = "Segmentação Boa"

ROTULOS = [
    "Digital Clara",
    "Digital Escura",
    "Dedo Fora da Área",
    "Fiapos",
    "Fora de Foco",
    "Manchas",
    "Scanner Sujo",
    ROTULO_SEGMENTACAO_BOA,
    "Sem Padrão Visível",
]

DESCRICOES_ROTULOS = {
    "Digital Clara": "Falta de pressão ou cristas pouco visíveis.",
    "Digital Escura": "Excesso de pressão ou cristas fundidas.",
    "Dedo Fora da Área": "Parte da digital ficou fora da área de captura.",
    "Fiapos": "Presença de fibras ou fiapos sobre a digital.",
    "Fora de Foco": "Imagem com perda de nitidez ou movimento.",
    "Manchas": "Manchas, resíduos ou descamação entre as cristas.",
    "Scanner Sujo": "Sujeira ou contaminação na superfície do sensor.",
    "Segmentação Boa": "Imagem adequada para uso biométrico.",
    "Sem Padrão Visível": "Não há padrão de cristas confiável para análise.",
}

ALIASES_ROTULOS = {
    "dedo fora da area": "Dedo Fora da Área",
    "posicionamento fora da area": "Dedo Fora da Área",
    "fiapos na digital": "Fiapos",
    "fiapos": "Fiapos",
    "manchas na digital": "Manchas",
    "manchas": "Manchas",
    "escaner sujo": "Scanner Sujo",
    "scanner sujo": "Scanner Sujo",
    "contaminacao do escaner": "Scanner Sujo",
    "segmentacao boa": "Segmentação Boa",
    "segmentacao adequada": "Segmentação Boa",
    "sem padrao visivel": "Sem Padrão Visível",
    "digital clara": "Digital Clara",
    "clareamento da digital": "Digital Clara",
    "digital escura": "Digital Escura",
    "escurecimento da digital": "Digital Escura",
    "fora de foco": "Fora de Foco",
    "desfoque": "Fora de Foco",
}

EXTENSOES_IMAGEM = {".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff", ".webp"}
CAMADAS = ["A", "B", "C", "D"]

DEDOS = {
    "1d": "Mindinho - Direita",
    "1e": "Mindinho - Esquerda",
    "2d": "Anelar - Direita",
    "2e": "Anelar - Esquerda",
    "3d": "Médio - Direita",
    "3e": "Médio - Esquerda",
    "4d": "Indicador - Direita",
    "4e": "Indicador - Esquerda",
    "5d": "Polegar - Direita",
    "5e": "Polegar - Esquerda",
}

ARQUIVO_REVISOES = "revisoes.json"
ARQUIVO_RESULTADO_BENIAN = "resultado_benian.json"


@dataclass(slots=True)
class Anotacao:
    nome: str
    descricao: str = ""
    avaliacao: int | None = None


@dataclass(slots=True)
class ItemImagem:
    id: str
    chave: str
    caminho_principal: Path
    arquivos_camada: dict[str, Path] = field(default_factory=dict)
    anotacao_original: list[Anotacao] = field(default_factory=list)
    metadados: dict[str, str] = field(default_factory=dict)

    @property
    def arquivo(self) -> str:
        return self.caminho_principal.name


@dataclass(slots=True)
class PacoteCarregado:
    nome: str
    origem: Path
    pasta_trabalho: Path
    itens: list[ItemImagem]
    resultado_original: Path | None = None


def reparar_texto(texto: str | None) -> str:
    valor = str(texto or "").strip()

    if not valor:
        return ""

    if "Ã" not in valor and "Â" not in valor:
        return valor

    try:
        return valor.encode("latin1").decode("utf-8")
    except UnicodeError:
        return valor


def chave_normalizada(texto: str) -> str:
    texto = reparar_texto(texto).casefold()
    texto = unicodedata.normalize("NFKD", texto)
    texto = "".join(caractere for caractere in texto if not unicodedata.combining(caractere))
    texto = re.sub(r"\s+", " ", texto)
    return texto.strip()


def normalizar_rotulo(nome: str | None) -> str:
    chave = chave_normalizada(nome or "")
    return ALIASES_ROTULOS.get(chave, reparar_texto(nome))


def chave_sem_camada(caminho: Path) -> str:
    match = re.match(r"(.+)_([ABCD])$", caminho.stem, flags=re.IGNORECASE)
    return match.group(1) if match else caminho.stem


def camada_do_arquivo(caminho: Path) -> str | None:
    match = re.match(r".+_([ABCD])$", caminho.stem, flags=re.IGNORECASE)
    return match.group(1).upper() if match else None


def extrair_metadados_nome(caminho: Path) -> dict[str, str]:
    stem = caminho.stem
    partes = stem.split("_")
    identificador = partes[0] if partes else ""
    dedo = ""

    for parte in partes:
        chave = parte.lower()

        if chave in DEDOS:
            dedo = DEDOS[chave]
            break

    match_frame = re.search(r"(\d{9,}(?:\.\d+)?)$", stem)

    return {
        "arquivo": caminho.name,
        "id": identificador,
        "dedo": dedo,
        "frame": match_frame.group(1) if match_frame else "",
    }


def aplicar_regras_rotulos(rotulos: list[str], severidades: dict[str, int] | None = None) -> list[str]:
    severidades = severidades or {}
    selecionados = []

    for rotulo in rotulos:
        normalizado = normalizar_rotulo(rotulo)

        if normalizado in ROTULOS and normalizado not in selecionados:
            selecionados.append(normalizado)

    erros = [rotulo for rotulo in selecionados if rotulo != ROTULO_SEGMENTACAO_BOA]

    if ROTULO_SEGMENTACAO_BOA in selecionados and erros:
        selecionados.remove(ROTULO_SEGMENTACAO_BOA)

    if severidades.get("Dedo Fora da Área", 0) >= 4 and "Dedo Fora da Área" in selecionados:
        return ["Dedo Fora da Área"]

    if severidades.get("Sem Padrão Visível", 0) >= 4 and "Sem Padrão Visível" in selecionados:
        preservados = {"Sem Padrão Visível"}

        for rotulo in ["Digital Clara", "Digital Escura"]:
            if rotulo in selecionados and severidades.get(rotulo, 0) >= 4:
                preservados.add(rotulo)

        selecionados = [rotulo for rotulo in selecionados if rotulo in preservados]

    return [rotulo for rotulo in ROTULOS if rotulo in selecionados]


def normalizar_lista_rotulos(rotulos: list[str]) -> list[str]:
    selecionados = []

    for rotulo in rotulos:
        normalizado = normalizar_rotulo(rotulo)

        if normalizado in ROTULOS and normalizado not in selecionados:
            selecionados.append(normalizado)

    return selecionados


def carregar_json(caminho: Path, padrao):
    if not caminho.exists():
        return padrao

    with caminho.open("r", encoding="utf-8-sig") as arquivo:
        return json.load(arquivo)


def salvar_json(caminho: Path, dados) -> None:
    caminho.parent.mkdir(parents=True, exist_ok=True)

    with caminho.open("w", encoding="utf-8") as arquivo:
        json.dump(dados, arquivo, ensure_ascii=False, indent=2)


def criar_pasta_temporaria(prefixo: str) -> Path:
    return Path(tempfile.mkdtemp(prefix=f"benian_{prefixo}_")).resolve()


def pasta_cache_visual() -> Path:
    caminho = Path(tempfile.gettempdir()) / "benian_cache_visual"
    caminho.mkdir(parents=True, exist_ok=True)
    return caminho


def normalizar_severidade(valor, padrao: int = 1) -> int:
    try:
        severidade = int(valor)
    except (TypeError, ValueError):
        severidade = padrao

    return max(1, min(5, severidade))


def rotulos_de_anotacoes(anotacoes: list[Anotacao]) -> list[str]:
    rotulos = []

    for anotacao in anotacoes:
        rotulo = normalizar_rotulo(anotacao.nome)

        if rotulo in ROTULOS and rotulo not in rotulos:
            rotulos.append(rotulo)

    return rotulos


def severidades_de_anotacoes(anotacoes: list[Anotacao]) -> dict[str, int]:
    severidades = {}

    for anotacao in anotacoes:
        rotulo = normalizar_rotulo(anotacao.nome)

        if rotulo in ROTULOS:
            severidades[rotulo] = normalizar_severidade(anotacao.avaliacao)

    return severidades


def comparar_revisao(
    rotulos_originais: list[str],
    severidades_originais: dict[str, int],
    rotulos_corrigidos: list[str],
    severidades_corrigidas: dict[str, int],
) -> dict:
    originais = set(rotulos_originais)
    corrigidos = set(rotulos_corrigidos)
    mantidos = [rotulo for rotulo in rotulos_corrigidos if rotulo in originais]
    adicionados = [rotulo for rotulo in rotulos_corrigidos if rotulo not in originais]
    removidos = [rotulo for rotulo in rotulos_originais if rotulo not in corrigidos]
    severidades_alteradas = {}

    for rotulo in mantidos:
        original = normalizar_severidade(severidades_originais.get(rotulo))
        corrigida = normalizar_severidade(severidades_corrigidas.get(rotulo))

        if original != corrigida:
            severidades_alteradas[rotulo] = {
                "original": original,
                "corrigida": corrigida,
            }

    houve_alteracao = bool(adicionados or removidos or severidades_alteradas)

    return {
        "houve_alteracao": houve_alteracao,
        "resultado": "alterado" if houve_alteracao else "mantido",
        "adicionados": adicionados,
        "removidos": removidos,
        "mantidos": mantidos,
        "severidades_alteradas": severidades_alteradas,
    }


def resumir_mudancas(mudancas: dict) -> str:
    partes = []

    if mudancas.get("adicionados"):
        partes.append("Adicionou rotulos: " + ", ".join(mudancas["adicionados"]))

    if mudancas.get("removidos"):
        partes.append("Removeu rotulos: " + ", ".join(mudancas["removidos"]))

    if mudancas.get("severidades_alteradas"):
        rotulos = ", ".join(mudancas["severidades_alteradas"].keys())
        partes.append("Alterou severidade: " + rotulos)

    if not partes:
        return "Nao sofreu alteracoes."

    return "; ".join(partes) + "."


def nome_seguro(texto: str) -> str:
    texto = reparar_texto(texto)
    texto = re.sub(r"[^A-Za-z0-9_. -]+", "_", texto)
    texto = re.sub(r"\s+", " ", texto).strip()
    return texto or "pacote"


def arquivo_tem_extensao_imagem(caminho: str | Path) -> bool:
    return Path(caminho).suffix.lower() in EXTENSOES_IMAGEM


def extrair_membro_zip_seguro(arquivo_zip: zipfile.ZipFile, membro: zipfile.ZipInfo, destino_base: Path) -> Path | None:
    partes = [
        parte
        for parte in re.split(r"[\\/]+", membro.filename)
        if parte and parte not in [".", ".."]
    ]

    if not partes:
        return None

    destino_base = destino_base.resolve()
    destino = destino_base.joinpath(*partes).resolve()

    if not str(destino).startswith(str(destino_base)):
        return None

    destino.parent.mkdir(parents=True, exist_ok=True)

    with arquivo_zip.open(membro) as origem, destino.open("wb") as saida:
        shutil.copyfileobj(origem, saida)

    return destino


def extrair_zip(caminho_zip: Path, pasta_saida: Path) -> Path:
    carimbo = time.strftime("%Y%m%d_%H%M%S")
    destino = pasta_saida / f"{nome_seguro(caminho_zip.stem)}_{carimbo}"
    destino.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(caminho_zip, "r") as arquivo_zip:
        for membro in arquivo_zip.infolist():
            if membro.is_dir() or not arquivo_tem_extensao_imagem(membro.filename):
                continue

            extrair_membro_zip_seguro(arquivo_zip, membro, destino)

    return destino


def listar_imagens(pasta: Path) -> list[Path]:
    if not pasta.exists():
        return []

    return sorted(
        caminho
        for caminho in pasta.rglob("*")
        if caminho.is_file() and arquivo_tem_extensao_imagem(caminho)
    )


def localizar_resultado_padrao(origem: Path) -> Path | None:
    pasta = origem.parent if origem.is_file() else origem
    candidatos = [
        pasta / "BENIAN" / "resultado.json",
        pasta / "BENAPRO" / "resultado.json",
        pasta / "resultado.json",
    ]

    if origem.is_file():
        candidatos.extend([
            origem.parent / "BENIAN" / "resultado.json",
            origem.parent / "BENAPRO" / "resultado.json",
        ])

    for candidato in candidatos:
        if candidato.exists():
            return candidato

    encontrados = sorted(pasta.glob("*/BENAPRO/resultado.json"))
    return encontrados[0] if encontrados else None


def carregar_resultado_benapro(caminho: Path | None) -> dict[str, list[Anotacao]]:
    if caminho is None or not caminho.exists():
        return {}

    dados = carregar_json(caminho, {})
    indice: dict[str, list[Anotacao]] = {}

    if isinstance(dados, dict):
        listas = dados.values()
    elif isinstance(dados, list):
        listas = [dados]
    else:
        return indice

    for itens in listas:
        if not isinstance(itens, list):
            continue

        for item in itens:
            if not isinstance(item, dict):
                continue

            arquivo = str(item.get("arquivo") or item.get("nome_arquivo") or "")

            if not arquivo:
                continue

            anotacoes = []

            for erro in item.get("erros", []) or item.get("rotulos", []):
                if isinstance(erro, str):
                    anotacoes.append(Anotacao(nome=normalizar_rotulo(erro)))
                    continue

                if not isinstance(erro, dict):
                    continue

                avaliacao = erro.get("avaliacao")

                try:
                    avaliacao = int(avaliacao) if avaliacao not in ["", None] else None
                except (TypeError, ValueError):
                    avaliacao = None

                anotacoes.append(Anotacao(
                    nome=normalizar_rotulo(erro.get("nome") or erro.get("rotulo")),
                    descricao=reparar_texto(erro.get("descricao")),
                    avaliacao=avaliacao,
                ))

            chave_arquivo = Path(arquivo).name
            indice[chave_arquivo] = anotacoes
            indice[chave_sem_camada(Path(chave_arquivo))] = anotacoes

    return indice


def criar_id_item(pasta: Path, chave: str) -> str:
    bruto = f"{pasta.resolve()}|{chave}".encode("utf-8", errors="ignore")
    return hashlib.sha1(bruto).hexdigest()[:16]


def carregar_pacote(origem: Path, pasta_saida: Path, resultado_original: Path | None = None) -> PacoteCarregado:
    origem = origem.resolve()
    pasta_saida = pasta_saida.resolve()

    if origem.is_file():
        if origem.suffix.lower() != ".zip":
            raise ValueError("Selecione um arquivo .zip ou uma pasta com imagens.")

        pasta_trabalho = extrair_zip(origem, criar_pasta_temporaria("entrada"))
        nome_pacote = origem.name
    elif origem.is_dir():
        imagens_existentes = listar_imagens(origem)
        zips = sorted(origem.glob("*.zip"))

        if not imagens_existentes and zips:
            pasta_trabalho = extrair_zip(zips[0], criar_pasta_temporaria("entrada"))
            nome_pacote = zips[0].name
        else:
            pasta_trabalho = origem
            nome_pacote = origem.name
    else:
        raise FileNotFoundError(f"Pacote não encontrado: {origem}")

    resultado_original = resultado_original or localizar_resultado_padrao(origem)
    anotacoes = carregar_resultado_benapro(resultado_original)
    grupos: dict[str, ItemImagem] = {}

    for caminho in listar_imagens(pasta_trabalho):
        chave = chave_sem_camada(caminho)
        id_grupo = criar_id_item(caminho.parent, chave)
        camada = camada_do_arquivo(caminho)

        if id_grupo not in grupos:
            grupos[id_grupo] = ItemImagem(
                id=id_grupo,
                chave=chave,
                caminho_principal=caminho,
                anotacao_original=anotacoes.get(caminho.name) or anotacoes.get(chave) or [],
                metadados=extrair_metadados_nome(caminho),
            )

        item = grupos[id_grupo]

        if camada in CAMADAS:
            item.arquivos_camada[camada] = caminho

        if camada == "A" or not item.caminho_principal.exists():
            item.caminho_principal = caminho

    itens = sorted(grupos.values(), key=lambda item: (str(item.caminho_principal.parent), item.chave))

    if not itens:
        raise ValueError("Nenhuma imagem foi encontrada no pacote selecionado.")

    return PacoteCarregado(
        nome=nome_pacote,
        origem=origem,
        pasta_trabalho=pasta_trabalho,
        itens=itens,
        resultado_original=resultado_original,
    )


def carregar_revisoes(pasta_saida: Path) -> dict[str, dict]:
    dados = carregar_json(pasta_saida / ARQUIVO_REVISOES, {})

    if isinstance(dados, dict):
        return {str(chave): valor for chave, valor in dados.items() if isinstance(valor, dict)}

    if isinstance(dados, list):
        return {
            str(item["id"]): item
            for item in dados
            if isinstance(item, dict) and item.get("id")
        }

    return {}


def salvar_revisoes(pasta_saida: Path, revisoes: dict[str, dict]) -> None:
    dados = sorted(
        revisoes.values(),
        key=lambda revisao: (
            str(revisao.get("pacote", "")),
            str(revisao.get("arquivo", "")),
            str(revisao.get("id", "")),
        ),
    )
    salvar_json(pasta_saida / ARQUIVO_REVISOES, dados)


def criar_revisao(
    item: ItemImagem,
    pacote: str,
    status: str,
    rotulos: list[str],
    severidades: dict[str, int],
) -> dict:
    rotulos_corrigidos = normalizar_lista_rotulos(rotulos)
    severidades_corrigidas = {
        rotulo: normalizar_severidade(severidades.get(rotulo))
        for rotulo in rotulos_corrigidos
    }
    rotulos_originais = normalizar_lista_rotulos(rotulos_de_anotacoes(item.anotacao_original))
    severidades_originais = {
        rotulo: normalizar_severidade(severidades_de_anotacoes(item.anotacao_original).get(rotulo))
        for rotulo in rotulos_originais
    }
    mudancas = comparar_revisao(
        rotulos_originais=rotulos_originais,
        severidades_originais=severidades_originais,
        rotulos_corrigidos=rotulos_corrigidos,
        severidades_corrigidas=severidades_corrigidas,
    )
    alteracao = "sofreu_alteracoes" if mudancas["houve_alteracao"] else "nao_sofreu_alteracoes"

    return {
        "id": item.id,
        "pacote": pacote,
        "imagem": item.arquivo,
        "chave": item.chave,
        "arquivo": item.arquivo,
        "caminho_imagem": str(item.caminho_principal),
        "status": status,
        "metadados": dict(item.metadados),
        "anotacao_original": [
            {
                "nome": anotacao.nome,
                "descricao": anotacao.descricao,
                "avaliacao": anotacao.avaliacao,
            }
            for anotacao in item.anotacao_original
        ],
        "rotulos_originais": rotulos_originais,
        "severidades_originais": severidades_originais,
        "rotulos_corrigidos": rotulos_corrigidos,
        "severidades": severidades_corrigidas,
        "salvo": True,
        "houve_alteracao": mudancas["houve_alteracao"],
        "alteracao": alteracao,
        "resultado_rotulos": alteracao,
        "resumo": resumir_mudancas(mudancas),
        "mudancas": {
            "adicionados": mudancas["adicionados"],
            "removidos": mudancas["removidos"],
            "mantidos": mudancas["mantidos"],
            "severidades_alteradas": mudancas["severidades_alteradas"],
        },
        "revisado_em": time.strftime("%Y-%m-%d %H:%M:%S"),
    }


def salvar_revisao(
    pasta_saida: Path,
    revisoes: dict[str, dict],
    item: ItemImagem,
    pacote: PacoteCarregado,
    status: str,
    rotulos: list[str],
    severidades: dict[str, int],
) -> dict:
    revisao = criar_revisao(item, pacote.nome, status, rotulos, severidades)
    revisoes[item.id] = revisao
    salvar_revisoes(pasta_saida, revisoes)
    exportar_resultado_benian(pasta_saida, revisoes, pacote)
    return revisao


def rotulo_de_erro_resultado(erro) -> str:
    if isinstance(erro, str):
        return normalizar_rotulo(erro)

    if isinstance(erro, dict):
        return normalizar_rotulo(erro.get("nome") or erro.get("rotulo"))

    return ""


def timestamp_dos_erros(erros: list) -> str:
    for erro in erros:
        if not isinstance(erro, dict):
            continue

        timestamp = str(erro.get("timestamp") or "")

        if timestamp:
            return timestamp

    return ""


def modelo_de_erro(erros: list) -> dict:
    for erro in erros:
        if isinstance(erro, dict):
            return copy.deepcopy(erro)

    return {}


def definir_nome_erro(erro: dict, rotulo: str) -> None:
    if "nome" in erro or "rotulo" not in erro:
        erro["nome"] = rotulo

    if "rotulo" in erro:
        erro["rotulo"] = rotulo


def erro_novo_para_resultado(rotulo: str, severidade: int, erros_originais: list, revisao: dict, usar_dict: bool):
    if not usar_dict:
        return rotulo

    erro = modelo_de_erro(erros_originais)
    timestamp = timestamp_dos_erros(erros_originais) or str(revisao.get("revisado_em") or "")

    if not erro:
        erro = {
            "nome": rotulo,
            "descricao": DESCRICOES_ROTULOS.get(rotulo, ""),
            "avaliacao": normalizar_severidade(severidade),
        }
    else:
        definir_nome_erro(erro, rotulo)

        if "descricao" in erro:
            erro["descricao"] = DESCRICOES_ROTULOS.get(rotulo, "")

        erro["avaliacao"] = normalizar_severidade(severidade)

    if timestamp or "timestamp" in erro:
        erro["timestamp"] = timestamp

    return erro


def erro_existente_para_resultado(erro, severidade: int):
    if not isinstance(erro, dict):
        return erro

    atualizado = copy.deepcopy(erro)

    if "avaliacao" in atualizado:
        atualizado["avaliacao"] = normalizar_severidade(severidade)

    return atualizado


def lista_erros_corrigida(erros_originais: list, revisao: dict, usar_dict: bool) -> list:
    rotulos_corrigidos = list(revisao.get("rotulos_corrigidos", []))
    corrigidos = set(rotulos_corrigidos)
    severidades = dict(revisao.get("severidades", {}))
    atualizados = []
    usados = set()

    for erro in erros_originais:
        rotulo = rotulo_de_erro_resultado(erro)

        if not rotulo or rotulo not in ROTULOS:
            atualizados.append(copy.deepcopy(erro))
            continue

        if rotulo not in corrigidos or rotulo in usados:
            continue

        atualizados.append(erro_existente_para_resultado(erro, severidades.get(rotulo)))
        usados.add(rotulo)

    for rotulo in rotulos_corrigidos:
        if rotulo in usados:
            continue

        atualizados.append(erro_novo_para_resultado(
            rotulo=rotulo,
            severidade=severidades.get(rotulo),
            erros_originais=erros_originais,
            revisao=revisao,
            usar_dict=usar_dict,
        ))
        usados.add(rotulo)

    return atualizados


def erros_para_resultado(revisao: dict) -> list[dict]:
    severidades = dict(revisao.get("severidades", {}))
    erros = []

    for rotulo in list(revisao.get("rotulos_corrigidos", [])):
        erros.append({
            "nome": rotulo,
            "descricao": DESCRICOES_ROTULOS.get(rotulo, ""),
            "avaliacao": normalizar_severidade(severidades.get(rotulo)),
            "timestamp": revisao.get("revisado_em", ""),
        })

    return erros


def item_resultado_de_revisao(revisao: dict) -> dict:
    metadados = dict(revisao.get("metadados", {}))

    return {
        "arquivo": revisao.get("arquivo", ""),
        "id": metadados.get("id") or revisao.get("chave", ""),
        "dedo": metadados.get("dedo", ""),
        "frame": metadados.get("frame", ""),
        "erros": erros_para_resultado(revisao),
    }


def chaves_revisao_resultado(revisao: dict) -> set[str]:
    arquivo = str(revisao.get("arquivo") or "")
    chave = str(revisao.get("chave") or "")
    chaves = {chave}

    if arquivo:
        nome = Path(arquivo).name
        chaves.add(nome)
        chaves.add(chave_sem_camada(Path(nome)))

    return {valor for valor in chaves if valor}


def chaves_item_resultado(item: dict) -> set[str]:
    arquivo = str(item.get("arquivo") or item.get("nome_arquivo") or "")
    chaves = set()

    if arquivo:
        nome = Path(arquivo).name
        chaves.add(nome)
        chaves.add(chave_sem_camada(Path(nome)))

    return {valor for valor in chaves if valor}


def iterar_listas_resultado(dados) -> list[tuple[str, list]]:
    if isinstance(dados, list):
        return [("", dados)]

    if isinstance(dados, dict):
        return [
            (str(chave), valor)
            for chave, valor in dados.items()
            if isinstance(valor, list)
        ]

    return []


def escolher_lista_resultado_para_novos(dados, pacote_nome: str) -> list | None:
    if isinstance(dados, list):
        return dados

    if not isinstance(dados, dict):
        return None

    if pacote_nome and isinstance(dados.get(pacote_nome), list):
        return dados[pacote_nome]

    listas = iterar_listas_resultado(dados)

    if len(listas) == 1:
        return listas[0][1]

    chave = pacote_nome or "pacote"

    if not isinstance(dados.get(chave), list):
        dados[chave] = []

    return dados[chave]


def atualizar_item_resultado(item: dict, revisao: dict) -> None:
    if "erros" in item:
        erros_originais = item.get("erros", [])

        if not isinstance(erros_originais, list):
            erros_originais = []

        item["erros"] = lista_erros_corrigida(
            erros_originais=erros_originais,
            revisao=revisao,
            usar_dict=any(isinstance(erro, dict) for erro in erros_originais) or not erros_originais,
        )
        return

    if "rotulos" in item:
        rotulos_originais = item.get("rotulos", [])

        if not isinstance(rotulos_originais, list):
            rotulos_originais = []

        item["rotulos"] = lista_erros_corrigida(
            erros_originais=rotulos_originais,
            revisao=revisao,
            usar_dict=any(isinstance(rotulo, dict) for rotulo in rotulos_originais),
        )
        return

    item["erros"] = erros_para_resultado(revisao)


def carregar_resultado_original(pacote: PacoteCarregado | None):
    if pacote is None or pacote.resultado_original is None or not pacote.resultado_original.exists():
        return {}

    dados = carregar_json(pacote.resultado_original, {})

    if isinstance(dados, (dict, list)):
        return copy.deepcopy(dados)

    return {}


def exportar_resultado_benian(
    pasta_saida: Path,
    revisoes: dict[str, dict],
    pacote: PacoteCarregado | None = None,
) -> None:
    resultado = carregar_resultado_original(pacote)
    aplicadas: set[str] = set()

    for _, itens in iterar_listas_resultado(resultado):
        for item in itens:
            if not isinstance(item, dict):
                continue

            chaves_item = chaves_item_resultado(item)

            for id_revisao, revisao in revisoes.items():
                if id_revisao in aplicadas:
                    continue

                if chaves_item & chaves_revisao_resultado(revisao):
                    atualizar_item_resultado(item, revisao)
                    aplicadas.add(id_revisao)
                    break

    destino_novos = escolher_lista_resultado_para_novos(
        resultado,
        pacote.nome if pacote else "",
    )

    if destino_novos is None:
        resultado = {}
        destino_novos = escolher_lista_resultado_para_novos(resultado, pacote.nome if pacote else "")

    for id_revisao, revisao in revisoes.items():
        if id_revisao not in aplicadas:
            destino_novos.append(item_resultado_de_revisao(revisao))

    salvar_json(pasta_saida / ARQUIVO_RESULTADO_BENIAN, resultado)

def extrair_camada_rgba(imagem: Image.Image, camada: str) -> Image.Image:
    rgba = imagem.convert("RGBA")
    mapa = {"1": "A", "2": "R", "3": "G", "4": "B"}
    return rgba.getchannel(mapa.get(camada, "A")).convert("RGB")


def aplicar_filtro_visual(imagem: Image.Image, filtro: str) -> Image.Image:
    rgb = imagem.convert("RGB")

    if filtro == "invertido":
        return ImageOps.invert(rgb)
    if filtro == "contraste":
        return ImageOps.autocontrast(rgb)
    if filtro == "claro":
        return ImageEnhance.Brightness(rgb).enhance(1.35)
    if filtro == "escuro":
        return ImageEnhance.Brightness(rgb).enhance(0.70)

    return rgb


def preparar_visualizacao(item: ItemImagem, camada: str, filtro: str) -> Path:
    camada = camada if camada in {"original", "1", "2", "3", "4"} else "1"
    filtro = filtro if filtro in {"normal", "invertido", "contraste", "claro", "escuro"} else "normal"
    caminho_base = item.caminho_principal
    camada_arquivo = {"1": "A", "2": "B", "3": "C", "4": "D"}.get(camada)

    if camada_arquivo and camada_arquivo in item.arquivos_camada:
        caminho_base = item.arquivos_camada[camada_arquivo]
        imagem = Image.open(caminho_base)
    else:
        imagem = Image.open(caminho_base)

        if camada in {"1", "2", "3", "4"}:
            imagem = extrair_camada_rgba(imagem, camada)

    imagem = aplicar_filtro_visual(imagem, filtro)
    destino = pasta_cache_visual() / f"{item.id}_{camada}_{filtro}.png"
    destino.parent.mkdir(parents=True, exist_ok=True)
    imagem.save(destino)
    return destino


def anotacao_para_json(anotacao: Anotacao) -> dict:
    return {
        "nome": anotacao.nome,
        "descricao": anotacao.descricao,
        "avaliacao": anotacao.avaliacao,
    }


@dataclass
class EstadoWeb:
    pasta_saida: Path = PASTA_SAIDA_PADRAO
    pacote: PacoteCarregado | None = None
    revisoes: dict[str, dict] = field(default_factory=dict)
    ultima_mensagem: str = ""

    def carregar(self, origem: Path, pasta_saida: Path, resultado: Path | None = None) -> None:
        pacote = carregar_pacote(origem, pasta_saida, resultado)
        self.pacote = pacote
        self.pasta_saida = pasta_saida.resolve()
        self.revisoes = carregar_revisoes(self.pasta_saida)

        if self.revisoes:
            exportar_resultado_benian(self.pasta_saida, self.revisoes, pacote)

        self.ultima_mensagem = f"Pacote carregado: {pacote.nome}"

    def item_por_id(self, id_item: str) -> ItemImagem | None:
        if self.pacote is None:
            return None

        for item in self.pacote.itens:
            if item.id == id_item:
                return item

        return None

    def salvar(self, id_item: str, status: str, rotulos: list[str], severidades: dict[str, int]) -> dict:
        if self.pacote is None:
            raise RuntimeError("Nenhum pacote carregado.")

        if status not in {"confirmado", "corrigir"}:
            raise ValueError("Status inválido.")

        item = self.item_por_id(id_item)

        if item is None:
            raise KeyError(f"Item não encontrado: {id_item}")

        revisao = salvar_revisao(
            pasta_saida=self.pasta_saida,
            revisoes=self.revisoes,
            item=item,
            pacote=self.pacote,
            status=status,
            rotulos=rotulos,
            severidades=severidades,
        )
        self.ultima_mensagem = f"Revisão salva: {item.arquivo}"
        return revisao

    def metricas(self) -> dict[str, int]:
        total = len(self.pacote.itens) if self.pacote else 0
        confirmado = sum(1 for revisao in self.revisoes.values() if revisao.get("status") == "confirmado")
        corrigir = sum(1 for revisao in self.revisoes.values() if revisao.get("status") == "corrigir")
        return {
            "total": total,
            "confirmado": confirmado,
            "corrigir": corrigir,
            "pendente": max(0, total - confirmado - corrigir),
        }

    def item_json(self, item: ItemImagem) -> dict:
        revisao = self.revisoes.get(item.id, {})
        rotulos = list(revisao.get("rotulos_corrigidos", []))
        severidades = dict(revisao.get("severidades", {}))

        if not revisao:
            rotulos = [anotacao.nome for anotacao in item.anotacao_original]
            severidades = {
                anotacao.nome: int(anotacao.avaliacao or 1)
                for anotacao in item.anotacao_original
                if anotacao.nome
            }

        return {
            "id": item.id,
            "chave": item.chave,
            "arquivo": item.arquivo,
            "caminho_imagem": str(item.caminho_principal),
            "camadas": sorted(item.arquivos_camada.keys()),
            "metadados": dict(item.metadados),
            "anotacao_original": [anotacao_para_json(anotacao) for anotacao in item.anotacao_original],
            "status_revisao": revisao.get("status", "pendente"),
            "rotulos_corrigidos": rotulos,
            "severidades": severidades,
        }

    def json(self) -> dict:
        return {
            "rotulos": ROTULOS,
            "descricoes": DESCRICOES_ROTULOS,
            "metricas": self.metricas(),
            "pacote": {
                "nome": self.pacote.nome,
                "origem": str(self.pacote.origem),
                "pasta_trabalho": str(self.pacote.pasta_trabalho),
                "resultado_original": str(self.pacote.resultado_original or ""),
            } if self.pacote else None,
            "pasta_saida": str(self.pasta_saida),
            "saida": {
                "revisoes": str(self.pasta_saida / ARQUIVO_REVISOES),
                "resultado_benian": str(self.pasta_saida / ARQUIVO_RESULTADO_BENIAN),
            },
            "itens": [self.item_json(item) for item in self.pacote.itens] if self.pacote else [],
            "mensagem": self.ultima_mensagem,
        }


HTML = r"""<!doctype html>
<html lang="pt-BR">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <link rel="icon" href="/icon?t=" type="image/jpeg">
  <title>BenIan</title>
  <style>
    :root {
      color-scheme: dark;
      --bg: #0b1016;
      --panel: #111820;
      --panel-soft: #151f29;
      --line: #283541;
      --line-strong: #405160;
      --text: #e6edf3;
      --muted: #9db0c2;
      --accent: #46bff0;
      --accent-soft: #103247;
      --ok: #1f8f5f;
      --bad: #bd4942;
    }
    * { box-sizing: border-box; }
    html, body { height: 100%; }
    body {
      margin: 0;
      background: var(--bg);
      color: var(--text);
      font-family: Arial, Helvetica, sans-serif;
      font-size: 14px;
      overflow: hidden;
    }
    header {
      height: 56px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 14px;
      padding: 0 18px;
      border-bottom: 1px solid var(--line);
      background: var(--panel);
    }
    .brand {
      min-width: 120px;
      height: 44px;
      display: flex;
      align-items: center;
    }
    .brand img {
      max-width: 190px;
      max-height: 42px;
      object-fit: contain;
      display: block;
    }
    .brand span {
      display: none;
      font-size: 20px;
      font-weight: 700;
      letter-spacing: 0;
    }
    button, input { font: inherit; }
    button {
      min-height: 36px;
      border: 1px solid var(--line-strong);
      background: #18222d;
      color: var(--text);
      padding: 0 12px;
      font-weight: 700;
      cursor: pointer;
    }
    button:hover { background: #213040; }
    button:disabled { opacity: .45; cursor: not-allowed; }
    .actions button:disabled { display: none; }
    button.active {
      border-color: var(--accent);
      background: var(--accent-soft);
      color: #e9f8ff;
    }
    button.ok { border-color: #12643d; background: var(--ok); color: #fff; }
    button.bad { border-color: #94302b; background: var(--bad); color: #fff; }
    button.ghost { background: var(--panel-soft); color: #cfe2f2; }
    button.original-btn {
      border-color: #4a7fa5;
      background: #0e2d45;
      color: #7dd3fc;
    }
    button.original-btn:hover { background: #153d5c; }
    button#exitBtn {
      border-color: #6b2420;
      background: #8b3630;
      color: #fff;
    }
    button#exitBtn:hover { background: #a03a32; }
    button.clear-btn {
      border-color: #7a5c1a;
      background: #2d1f05;
      color: #fcd34d;
    }
    button.clear-btn:hover { background: #3d2a08; }
    input[type="text"], input[type="file"], input[type="number"] {
      min-height: 36px;
      width: 100%;
      border: 1px solid var(--line-strong);
      background: #0d141c;
      color: var(--text);
      padding: 7px 9px;
    }
    input[type="checkbox"] {
      width: 19px;
      height: 19px;
      accent-color: #1d9ce5;
    }
    main {
      display: grid;
      grid-template-columns: minmax(0, 1fr) 468px;
      gap: 14px;
      padding: 14px 16px 16px;
      height: calc(100vh - 56px);
      min-height: 0;
    }
    .viewer, .side {
      min-height: 0;
      background: var(--panel);
      border: 1px solid var(--line);
    }
    .viewer {
      display: grid;
      grid-template-rows: auto minmax(0, 1fr) auto;
    }
    .toolbar {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 10px;
      padding: 12px;
      border-bottom: 1px solid var(--line);
    }
    .view-buttons, .nav-buttons, .actions, .header-actions {
      display: flex;
      gap: 8px;
      align-items: center;
      flex-wrap: wrap;
    }
    .image-wrap {
      min-height: 0;
      display: flex;
      align-items: center;
      justify-content: center;
      background: #05080c;
      overflow: hidden;
      padding: 14px;
      position: relative;
      cursor: grab;
    }
    .image-wrap.dragging { cursor: grabbing; }
    #image {
      max-width: 100%;
      max-height: 100%;
      object-fit: contain;
      background: #05080c;
      border: 1px solid var(--line);
      transform-origin: center center;
      user-select: none;
      pointer-events: none;
    }
    .footer {
      min-height: 44px;
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 12px;
      padding: 0 12px;
      border-top: 1px solid var(--line);
      color: #a7cfee;
      overflow: hidden;
      white-space: nowrap;
    }
    .footer span:first-child {
      min-width: 0;
      overflow: hidden;
      text-overflow: ellipsis;
    }
    .side {
      overflow: auto;
      padding: 16px;
    }
    .summary {
      display: grid;
      grid-template-columns: repeat(3, 1fr);
      gap: 8px;
      margin-bottom: 14px;
    }
    .metric {
      border: 1px solid var(--line);
      padding: 9px;
      background: var(--panel-soft);
      min-width: 0;
    }
    .metric span {
      display: block;
      color: var(--muted);
      font-size: 12px;
    }
    .metric strong {
      display: block;
      margin-top: 3px;
      font-size: 18px;
    }
    h2 {
      margin: 14px 0 8px;
      font-size: 15px;
    }
    .label-row {
      display: grid;
      grid-template-columns: 24px minmax(0, 1fr) 58px;
      align-items: center;
      gap: 8px;
      padding: 7px 0;
      border-bottom: 1px solid #1d2934;
    }
    .label-row .name {
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }
    .label-row.detected .name {
      color: var(--accent);
      font-weight: 700;
    }
    .label-row input[type="number"] {
      min-height: 30px;
      padding: 4px 5px;
      text-align: center;
    }
    .status {
      display: inline-flex;
      align-items: center;
      min-height: 36px;
      padding: 0 10px;
      border: 1px solid var(--line);
      background: var(--panel-soft);
      color: var(--muted);
      font-weight: 700;
    }
    .status.confirmado { color: #bdf0d7; border-color: #2f9d70; }
    .status.corrigir { color: #ffd0cd; border-color: #bd4942; }
    .muted { color: var(--muted); font-size: 12px; }
    .path {
      color: #99c8eb;
      font-size: 12px;
      overflow-wrap: anywhere;
      margin-top: 14px;
      white-space: pre-wrap;
    }
    .original-list {
      border: 1px solid var(--line);
      background: #0d141c;
      padding: 9px;
      min-height: 42px;
      color: #cbd8e3;
      font-size: 12px;
    }
    .empty {
      height: 100%;
      display: flex;
      align-items: center;
      justify-content: center;
      color: var(--muted);
      text-align: center;
      padding: 30px;
    }
    .modal-backdrop {
      position: fixed;
      inset: 0;
      z-index: 20;
      display: none;
      align-items: center;
      justify-content: center;
      background: rgba(3, 7, 12, .82);
      padding: 18px;
    }
    .modal-backdrop.open { display: flex; }
    .modal {
      width: min(900px, 100%);
      max-height: min(760px, 100%);
      overflow: auto;
      background: var(--panel);
      border: 1px solid var(--line-strong);
    }
    .modal-head {
      height: 52px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 0 16px;
      border-bottom: 1px solid var(--line);
    }
    .modal-head strong { font-size: 17px; }
    .modal-body {
      padding: 16px;
      display: grid;
      gap: 14px;
    }
    .grid {
      display: grid;
      grid-template-columns: 170px minmax(0, 1fr);
      gap: 9px 12px;
      align-items: center;
    }
    .picker-row, .modal-actions {
      display: flex;
      gap: 8px;
      align-items: center;
    }
    .picker-row input { min-width: 0; }
    .picker-row button { white-space: nowrap; }
    .modal-actions { justify-content: flex-end; padding-top: 4px; }
    .load-status {
      display: none;
      align-items: center;
      gap: 10px;
      color: #b9d8ed;
      font-weight: 700;
    }
    .load-status.open { display: flex; }
    .spinner {
      width: 18px;
      height: 18px;
      border: 3px solid #263747;
      border-top-color: var(--accent);
      border-radius: 50%;
      animation: spin .8s linear infinite;
    }
    .progress-bar-wrap {
    width: 100%;
    height: 4px;
    background: #1a2a3a;
    border-radius: 2px;
    overflow: hidden;
    margin-top: 8px;
  }
  .progress-bar {
    height: 100%;
    width: 0%;
    background: linear-gradient(90deg, var(--accent) 0%, #7be0ff 100%);
    border-radius: 2px;
    transition: width 0.3s ease;
  }
  .load-status {
    display: none;
    flex-direction: column;
    gap: 8px;
    color: #b9d8ed;
    font-weight: 700;
    width: 100%;
  }
  .load-status.open { display: flex; }
    @keyframes spin { to { transform: rotate(360deg); } }
    .toast {
      position: fixed;
      right: 16px;
      bottom: 16px;
      z-index: 30;
      max-width: 560px;
      display: none;
      border: 1px solid var(--line-strong);
      background: #101923;
      padding: 10px 12px;
      color: var(--text);
      box-shadow: 0 12px 30px rgba(0, 0, 0, .32);
    }
    .toast.open { display: block; }
    .toast.error { border-color: #bd4942; color: #ffd0cd; }
    @media (max-width: 1050px) {
      body { overflow: auto; }
      main { grid-template-columns: 1fr; height: auto; }
      .viewer { height: 68vh; }
    }
    @media (max-width: 700px) {
      header { height: auto; min-height: 56px; align-items: flex-start; padding: 12px; }
      main { padding: 10px; }
      .toolbar { align-items: flex-start; flex-direction: column; }
      .grid { grid-template-columns: 1fr; }
      .actions button { flex: 1 1 auto; }
    }
  </style>
</head>
<body>
  <header>
    <div class="brand">
      <img id="brandLogo" src="/logo" alt="BenIan" onerror="this.style.display='none'; document.getElementById('brandFallback').style.display='block';">
      <span id="brandFallback">BenIan</span>
    </div>
    <div class="header-actions">
      <span id="headerInfo" class="muted"></span>
      <button id="openLoadBtn">Carregar</button>
      <button id="exitBtn">Sair</button>
    </div>
  </header>

  <main>
    <section class="viewer">
      <div class="toolbar">
        <div class="view-buttons" id="viewButtons"></div>
        <div class="nav-buttons">
          <button id="zoomOutBtn">-</button>
          <button id="zoomResetBtn">100%</button>
          <button id="zoomInBtn">+</button>
          <button id="prevBtn">Anterior</button>
          <button id="nextBtn">Próxima</button>
        </div>
      </div>
      <div class="image-wrap" id="imageWrap">
        <div class="empty">Nenhum pacote carregado.</div>
      </div>
      <div class="footer">
        <span id="imageName"></span>
        <span id="position"></span>
      </div>
    </section>

    <aside class="side">
      <div class="summary">
        <div class="metric"><span>Total</span><strong id="mTotal">0</strong></div>
        <div class="metric"><span>Confirmadas</span><strong id="mOk">0</strong></div>
        <div class="metric"><span>Pendentes</span><strong id="mBad">0</strong></div>
      </div>
      <div class="actions">
        <button class="ok" id="acceptBtn">Salvar revisão</button>
        <button class="original-btn" id="originalBtn">Original</button>
        <button class="clear-btn" id="clearBtn">Limpar</button>
        <span class="status" id="status">pendente</span>
      </div>
      <h2>Rótulos</h2>
      <div id="labels"></div>
      <p class="path" id="paths"></p>
    </aside>
  </main>

  <div class="modal-backdrop" id="loadDialog">
    <div class="modal">
      <div class="modal-head">
        <strong>Carregar pacote</strong>
        <button class="ghost" id="closeLoadBtn">Fechar</button>
      </div>
      <div class="modal-body">
        <div class="grid">
          <label>Pacote</label>
          <div class="picker-row">
            <input id="originPath" type="text" placeholder="ZIP ou pasta de imagens">
            <button id="chooseZipBtn" type="button">ZIP</button>
            <button id="chooseFolderBtn" type="button">Pasta</button>
          </div>
          <label>Resultado JSON</label>
          <div class="picker-row">
            <input id="resultPath" type="text" placeholder="resultado.json opcional">
            <button id="chooseResultBtn" type="button">JSON</button>
          </div>
          <label>Pasta de saída</label>
          <div class="picker-row">
            <input id="outputPath" type="text">
            <button id="chooseOutputBtn" type="button">Saída</button>
          </div>
        </div>
        <div class="load-status" id="loadStatus">
          <div style="width:100%">
            <div style="display:flex;align-items:center;gap:10px;">
              <span class="spinner"></span>
              <span id="loadStatusText">Carregando pacote...</span>
            </div>
            <div class="progress-bar-wrap">
              <div class="progress-bar" id="progressBar"></div>
            </div>
          </div>
        </div>
        <div class="modal-actions"><button class="ok" id="loadBtn">Carregar</button></div>
      </div>
    </div>
  </div>

  <div class="modal-backdrop" id="exitDialog">
    <div class="modal">
      <div class="modal-head">
        <strong>Sair da aplicação</strong>
      </div>
      <div class="modal-body">
        <p>Tem certeza que deseja sair?</p>
      </div>
      <div class="modal-actions">
        <button class="ghost" id="exitCancelBtn">Cancelar</button>
        <button class="bad" id="exitConfirmBtn">Sair</button>
      </div>
    </div>
  </div>

  <div class="toast" id="toast"></div>

  <script>
    let state = { rotulos: [], descricoes: {}, itens: [], metricas: {}, pacote: null };
    let index = 0;
    let camada = "1";
    let zoom = 1;
    let panX = 0;
    let panY = 0;
    let dragging = false;
    let dragStart = { x: 0, y: 0, panX: 0, panY: 0 };
    let draft = {};
    const el = (id) => document.getElementById(id);

    function toast(message, error = false) {
      const box = el("toast");
      box.textContent = message;
      box.className = `toast open ${error ? "error" : ""}`;
      window.clearTimeout(toast._timer);
      toast._timer = window.setTimeout(() => box.className = "toast", 4200);
    }

    async function api(path, options) {
      const response = await fetch(path, options);
      if (!response.ok) throw new Error(await response.text());
      return await response.json();
    }

    function current() {
      return state.itens[index] || null;
    }

    async function loadState(keepIndex = false) {
      const previousId = current()?.id;
      state = await api("/api/state");
      el("outputPath").value = state.pasta_saida || "";

      if (keepIndex && previousId) {
        const found = state.itens.findIndex((item) => item.id === previousId);
        index = found >= 0 ? found : Math.min(index, state.itens.length - 1);
      } else {
        index = Math.max(0, Math.min(index, state.itens.length - 1));
      }

      render();
      if (!state.itens.length) openLoad();
    }

    function openLoad() {
      el("loadDialog").classList.add("open");
    }

    function closeLoad() {
      el("loadDialog").classList.remove("open");
    }

    function openExit() {
      el("exitDialog").classList.add("open");
    }

    function closeExit() {
      el("exitDialog").classList.remove("open");
    }

    function setLoading(active, text = "Carregando pacote...") {
      el("loadStatusText").textContent = text;
      el("loadStatus").classList.toggle("open", active);
      el("loadBtn").disabled = active;
      el("chooseZipBtn").disabled = active;
      el("chooseFolderBtn").disabled = active;
      el("chooseResultBtn").disabled = active;
      el("chooseOutputBtn").disabled = active;
      if (active) setProgress(0);
    }

    function setProgress(percent) {
      el("progressBar").style.width = Math.min(100, Math.max(0, percent)) + "%";
    }

    function renderMetrics() {
      const metricas = state.metricas || {};
      el("mTotal").textContent = metricas.total || 0;
      el("mOk").textContent = metricas.confirmado || 0;
      el("mBad").textContent = metricas.pendente || 0;
      const pacote = state.pacote ? state.pacote.nome : "sem pacote";
      el("headerInfo").textContent = `${metricas.pendente || 0} pendentes | ${pacote}`;
    }

    function renderEmpty() {
      el("viewButtons").innerHTML = "";
      el("imageWrap").innerHTML = '<div class="empty">Nenhum pacote carregado.</div>';
      el("imageName").textContent = "";
      el("position").textContent = "";
      el("labels").innerHTML = "";
      el("status").textContent = "vazio";
      el("status").className = "status";
      el("paths").textContent = "";
      ["prevBtn", "nextBtn", "acceptBtn", "originalBtn", "clearBtn", "zoomOutBtn", "zoomResetBtn", "zoomInBtn"].forEach((id) => el(id).disabled = true);
    }

    function itemDraft(item) {
      if (!draft[item.id]) {
        const originais = (item.anotacao_original || [])
          .map((anotacao) => anotacao.nome)
          .filter((rotulo) => state.rotulos.includes(rotulo));
        const rotulos = Array.isArray(item.rotulos_corrigidos)
          ? item.rotulos_corrigidos
          : originais;
        const severidades = { ...(item.severidades || {}) };
        (item.anotacao_original || []).forEach((anotacao) => {
          if (!severidades[anotacao.nome]) {
            severidades[anotacao.nome] = Math.max(1, Math.min(5, Number(anotacao.avaliacao || 1)));
          }
        });
        draft[item.id] = {
          rotulos: [...rotulos],
          severidades,
        };
      }
      return draft[item.id];
    }

    function syncDraft() {
      const item = current();
      if (!item) return;
      const rotulos = [];
      const severidades = {};
      document.querySelectorAll(".label-check").forEach((check) => {
        if (!check.checked) return;
        rotulos.push(check.value);
        const sev = document.querySelector(`.severity[data-label="${CSS.escape(check.value)}"]`);
        severidades[check.value] = Math.max(1, Math.min(5, Number(sev?.value || 1)));
      });
      draft[item.id] = { rotulos, severidades };
    }

    function resetZoom() {
      zoom = 1;
      panX = 0;
      panY = 0;
      applyZoom();
    }

    function applyZoom() {
      const image = el("image");
      if (!image) return;
      if (zoom <= 1.01) {
        panX = 0;
        panY = 0;
      }
      image.style.transform = `translate(${panX}px, ${panY}px) scale(${zoom})`;
      el("zoomResetBtn").textContent = `${Math.round(zoom * 100)}%`;
    }

    function setZoom(value) {
      zoom = Math.max(1, Math.min(8, value));
      applyZoom();
    }

    function mudarIndice(nextIndex) {
      syncDraft();
      index = Math.max(0, Math.min(state.itens.length - 1, nextIndex));
      resetZoom();
      render();
    }

    function mudarCamada(nextCamada) {
      syncDraft();
      camada = nextCamada;
      resetZoom();
      render();
    }

    function usarOriginal() {
      const item = current();
      if (!item) return;
      const rotulos = [];
      const severidades = {};
      (item.anotacao_original || []).forEach((anotacao) => {
        if (!state.rotulos.includes(anotacao.nome)) return;
        rotulos.push(anotacao.nome);
        severidades[anotacao.nome] = Math.max(1, Math.min(5, Number(anotacao.avaliacao || 1)));
      });
      draft[item.id] = { rotulos, severidades };
      render();
    }

    function limparRotulos() {
      const item = current();
      if (!item) return;
      draft[item.id] = { rotulos: [], severidades: {} };
      render();
    }

    function renderViews() {
      const views = [
        ["original", "Original"],
        ["1", "Camada 1 (A)"],
        ["2", "Camada 2 (R)"],
      ];
      el("viewButtons").innerHTML = "";
      views.forEach(([value, label]) => {
        const button = document.createElement("button");
        button.textContent = label;
        button.className = camada === value ? "active" : "";
        button.onclick = () => mudarCamada(value);
        el("viewButtons").appendChild(button);
      });
    }

    function renderLabels(item) {
      const currentDraft = itemDraft(item);
      const selected = new Set(currentDraft.rotulos || []);
      const original = new Set((item.anotacao_original || []).map((anotacao) => anotacao.nome));
      el("labels").innerHTML = "";

      state.rotulos.forEach((rotulo) => {
        const row = document.createElement("label");
        row.className = `label-row ${original.has(rotulo) ? "detected" : ""}`;
        row.title = state.descricoes?.[rotulo] || "";

        const check = document.createElement("input");
        check.type = "checkbox";
        check.className = "label-check";
        check.value = rotulo;
        check.checked = selected.has(rotulo);

        const name = document.createElement("span");
        name.className = "name";
        name.textContent = rotulo;

        const sev = document.createElement("input");
        sev.type = "number";
        sev.min = "1";
        sev.max = "5";
        sev.className = "severity";
        sev.dataset.label = rotulo;
        sev.disabled = !check.checked;
        
        // Só mostrar severidade se estava na original
        if (original.has(rotulo)) {
          sev.value = currentDraft.severidades?.[rotulo] || "";
        } else if (selected.has(rotulo)) {
          sev.value = currentDraft.severidades?.[rotulo] || "";
        } else {
          sev.value = "";
        }

        check.onchange = () => {
          sev.disabled = !check.checked;
          if (check.checked) {
            sev.value = currentDraft.severidades?.[rotulo] || 1;
          } else {
            sev.value = "";
          }
          syncDraft();
        };
        sev.onchange = () => syncDraft();

        row.appendChild(check);
        row.appendChild(name);
        row.appendChild(sev);
        el("labels").appendChild(row);
      });
    }

    function render() {
      renderMetrics();
      if (!state.itens.length) {
        renderEmpty();
        return;
      }

      const item = current();
      renderViews();
      el("imageWrap").innerHTML = '<img id="image" alt="">';
      el("image").src = `/imagem?id=${encodeURIComponent(item.id)}&camada=${encodeURIComponent(camada)}&filtro=normal&t=${Date.now()}`;
      el("image").onload = () => applyZoom();
      el("imageName").textContent = item.arquivo || item.chave || "";
      el("position").textContent = `${index + 1} / ${state.itens.length}`;
      el("prevBtn").disabled = index <= 0;
      el("nextBtn").disabled = index >= state.itens.length - 1;
      ["acceptBtn", "originalBtn", "clearBtn", "zoomOutBtn", "zoomResetBtn", "zoomInBtn"].forEach((id) => el(id).disabled = false);

      const status = item.status_revisao || "pendente";
      el("status").textContent = status === "corrigir" ? "revisar depois" : status === "pendente" ? "" : status;
      el("status").style.display = status === "pendente" ? "none" : "inline-flex";
      el("status").className = `status ${status}`;

      const meta = item.metadados || {};
      const details = [meta.id, meta.dedo, meta.frame].filter(Boolean).join(" | ");
      el("paths").textContent = `${details ? `${details}\n` : ""}${item.caminho_imagem || ""}`;
      renderLabels(item);
      applyZoom();
    }

    function nextPendingIndex(startIndex) {
      if (!state.itens.length) return 0;
      for (let offset = 1; offset <= state.itens.length; offset += 1) {
        const candidate = (startIndex + offset) % state.itens.length;
        if ((state.itens[candidate].status_revisao || "pendente") === "pendente") return candidate;
      }
      return Math.min(startIndex, state.itens.length - 1);
    }

    async function save(status) {
      const item = current();
      if (!item) return;
      syncDraft();
      const payload = {
        id: item.id,
        status,
        rotulos: draft[item.id]?.rotulos || [],
        severidades: draft[item.id]?.severidades || {},
      };
      const oldIndex = index;
      await api("/api/revisao", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      delete draft[item.id];
      await loadState(true);
      index = nextPendingIndex(oldIndex);
      resetZoom();
      render();
    }

    async function carregarPacote() {
      const payload = {
        saida_path: el("outputPath").value || "",
        origem_path: el("originPath").value || "",
        resultado_path: el("resultPath").value || "",
      };

      setLoading(true, "Carregando pacote...");
      let progress = 0;
      const progressInterval = setInterval(() => {
        if (progress < 90) progress += Math.random() * 20;
        setProgress(progress);
      }, 300);

      try {
        state = await api("/api/carregar", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        });
        clearInterval(progressInterval);
        setProgress(100);
        draft = {};
        index = 0;
        camada = "1";
        resetZoom();
        el("loadDialog").classList.remove("open");
        render();
        toast(state.mensagem || "Pacote carregado.");
      } catch (error) {
        clearInterval(progressInterval);
        toast(error.message, true);
      } finally {
        setLoading(false);
      }
    }

    async function escolherCaminho(tipo, destino) {
      setLoading(true, "Aguardando seleção...");
      try {
        const data = await api("/api/escolher", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ tipo }),
        });
        if (data.path) el(destino).value = data.path;
      } catch (error) {
        toast(error.message, true);
      } finally {
        setLoading(false);
      }
    }

    el("openLoadBtn").onclick = openLoad;
    el("closeLoadBtn").onclick = closeLoad;
    el("exitBtn").onclick = openExit;
    el("exitCancelBtn").onclick = closeExit;
    el("exitConfirmBtn").onclick = async () => {
      try {
        await fetch("/api/sair");
        setTimeout(() => window.close(), 500);
      } catch (e) {
        window.close();
      }
    };
    el("loadBtn").onclick = carregarPacote;
    el("chooseZipBtn").onclick = () => escolherCaminho("zip", "originPath");
    el("chooseFolderBtn").onclick = () => escolherCaminho("pasta", "originPath");
    el("chooseResultBtn").onclick = () => escolherCaminho("resultado", "resultPath");
    el("chooseOutputBtn").onclick = () => escolherCaminho("saida", "outputPath");
    el("prevBtn").onclick = () => mudarIndice(index - 1);
    el("nextBtn").onclick = () => mudarIndice(index + 1);
    el("acceptBtn").onclick = () => save("confirmado").catch((error) => toast(error.message, true));
    el("originalBtn").onclick = usarOriginal;
    el("clearBtn").onclick = limparRotulos;
    el("zoomOutBtn").onclick = () => setZoom(zoom / 1.25);
    el("zoomResetBtn").onclick = resetZoom;
    el("zoomInBtn").onclick = () => setZoom(zoom * 1.25);

    el("imageWrap").addEventListener("wheel", (event) => {
      if (!current()) return;
      event.preventDefault();
      setZoom(zoom * (event.deltaY < 0 ? 1.18 : 1 / 1.18));
    }, { passive: false });

    el("imageWrap").addEventListener("mousedown", (event) => {
      if (!current() || zoom <= 1.01) return;
      dragging = true;
      dragStart = { x: event.clientX, y: event.clientY, panX, panY };
      el("imageWrap").classList.add("dragging");
    });

    window.addEventListener("mousemove", (event) => {
      if (!dragging) return;
      panX = dragStart.panX + event.clientX - dragStart.x;
      panY = dragStart.panY + event.clientY - dragStart.y;
      applyZoom();
    });

    window.addEventListener("mouseup", () => {
      dragging = false;
      el("imageWrap").classList.remove("dragging");
    });

    // Atualizar favicon com timestamp para evitar cache
    document.querySelector('link[rel="icon"]').href = `/icon?t=${Date.now()}`;

    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape") {
        if (el("exitDialog").classList.contains("open")) {
          closeExit();
        } else {
          openExit();
        }
        return;
      }
      if (event.target && ["INPUT", "SELECT", "TEXTAREA"].includes(event.target.tagName)) return;
      const item = current();
      if (!item) return;
      if (["1", "2"].includes(event.key)) mudarCamada(event.key);
      if (event.key.toLowerCase() === "o") mudarCamada("original");
      if (event.key.toLowerCase() === "s") save("confirmado").catch((error) => toast(error.message, true));
      if (event.key === "ArrowLeft" && index > 0) mudarIndice(index - 1);
      if (event.key === "ArrowRight" && index < state.itens.length - 1) mudarIndice(index + 1);
      if (event.key === "+" || event.key === "=") setZoom(zoom * 1.25);
      if (event.key === "-" || event.key === "_") setZoom(zoom / 1.25);
      if (event.key === "0") resetZoom();
    });

    loadState().catch((error) => {
      toast(error.message, true);
      openLoad();
    });
  </script>
</body>
</html>
"""


def bases_recursos() -> list[Path]:
    bases: list[Path] = []
    for base in (RAIZ_RECURSOS, RAIZ_REPOSITORIO):
        if base not in bases:
            bases.append(base)
    return bases


def localizar_logo() -> Path | None:
    caminhos_relativos = [
        Path("Imagens") / "logo_texto.png",
        Path("logo_texto.png"),
        Path("logo.png"),
        Path("logo_benian.png"),
        Path("benian_logo.png"),
        Path("dados") / "logo_texto.png",
        Path("dados") / "icon.png",
        Path("dados") / "logo_benian.png",
        Path("assets") / "logo_texto.png",
        Path("assets") / "logo.png",
        Path("assets") / "logo_benian.png",
    ]

    for base in bases_recursos():
        for caminho_relativo in caminhos_relativos:
            candidato = base / caminho_relativo
            if candidato.exists() and candidato.is_file():
                return candidato

    return None


def localizar_icon() -> Path | None:
    caminhos_relativos = [
        Path("Imagens") / "icon.jpg",
        Path("Imagens") / "icon.png",
        Path("Imagem") / "icon.jpg",
        Path("Imagem") / "icon.png",
        Path("icon.jpg"),
        Path("icon.png"),
        Path("favicon.ico"),
        Path("assets") / "icon.jpg",
        Path("assets") / "icon.png",
    ]
    for base in bases_recursos():
        for caminho_relativo in caminhos_relativos:
            candidato = base / caminho_relativo
            if candidato.exists() and candidato.is_file():
                return candidato
    return None


def escolher_caminho(tipo: str) -> str:
    import tkinter as tk
    from tkinter import filedialog

    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    caminho = ""

    try:
        if tipo == "zip":
            caminho = filedialog.askopenfilename(
                title="Selecionar pacote ZIP",
                filetypes=[("Pacotes ZIP", "*.zip"), ("Todos os arquivos", "*.*")],
            )
        elif tipo == "pasta":
            caminho = filedialog.askdirectory(title="Selecionar pasta com imagens")
        elif tipo == "resultado":
            caminho = filedialog.askopenfilename(
                title="Selecionar resultado.json",
                filetypes=[("Arquivos JSON", "*.json"), ("Todos os arquivos", "*.*")],
            )
        elif tipo == "saida":
            caminho = filedialog.askdirectory(title="Selecionar pasta de saída")
        else:
            raise ValueError("Tipo de seleção inválido.")
    finally:
        root.destroy()

    return str(caminho or "")


class Handler(BaseHTTPRequestHandler):
    estado: EstadoWeb

    def log_message(self, formato, *args):
        return

    def enviar(self, status: int, corpo: bytes, content_type: str, headers: dict = None) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(corpo)))
        if headers:
            for key, value in headers.items():
                self.send_header(key, value)
        self.end_headers()
        self.wfile.write(corpo)

    def enviar_texto(self, status: int, texto: str) -> None:
        self.enviar(status, texto.encode("utf-8"), "text/plain; charset=utf-8")

    def enviar_json(self, dados, status: int = 200) -> None:
        corpo = json.dumps(dados, ensure_ascii=False).encode("utf-8")
        self.enviar(status, corpo, "application/json; charset=utf-8")

    def enviar_arquivo(self, caminho: Path) -> None:
        if not caminho.exists() or not caminho.is_file():
            self.enviar_texto(404, "Arquivo não encontrado.")
            return

        content_type = mimetypes.guess_type(caminho.name)[0] or "application/octet-stream"
        self.enviar(200, caminho.read_bytes(), content_type)

    def do_GET(self):
        try:
            url = urlparse(self.path)

            if url.path in {"/", "/index.html"}:
                self.enviar(200, HTML.encode("utf-8"), "text/html; charset=utf-8")
                return

            if url.path == "/logo":
                logo = localizar_logo()

                if logo is None:
                    self.enviar_texto(404, "Logo não encontrado.")
                    return

                self.enviar_arquivo(logo)
                return

            if url.path in ("/favicon.ico", "/icon"):
              icon = localizar_icon()
              if icon is None:
                  self.enviar_texto(404, "Ícone não encontrado.")
                  return
              content_type = mimetypes.guess_type(icon.name)[0] or "application/octet-stream"
              self.enviar(200, icon.read_bytes(), content_type, {"Cache-Control": "no-cache, must-revalidate"})
              return

            if url.path == "/api/state":
                self.enviar_json(self.estado.json())
                return

            if url.path == "/imagem":
                params = parse_qs(url.query)
                item = self.estado.item_por_id(params.get("id", [""])[0])

                if item is None:
                    self.enviar_texto(404, "Imagem não encontrada.")
                    return

                caminho = preparar_visualizacao(
                    item=item,
                    camada=params.get("camada", ["1"])[0],
                    filtro=params.get("filtro", ["normal"])[0],
                )
                self.enviar_arquivo(caminho)
                return

            if url.path == "/api/sair":
                self.enviar_json({"status": "saindo"})
                # Encerrar o servidor em uma thread separada
                import threading
                threading.Thread(target=lambda: os._exit(0), daemon=True).start()
                return

            self.enviar_texto(404, "Rota não encontrada.")
        except Exception as erro:
            self.enviar_texto(500, str(erro))

    def do_POST(self):
        try:
            url = urlparse(self.path)

            if url.path == "/api/revisao":
                tamanho = int(self.headers.get("Content-Length", "0") or "0")
                payload = json.loads(self.rfile.read(tamanho).decode("utf-8"))
                revisao = self.estado.salvar(
                    id_item=str(payload.get("id", "")),
                    status=str(payload.get("status", "")),
                    rotulos=list(payload.get("rotulos", [])),
                    severidades={
                        str(chave): int(valor)
                        for chave, valor in dict(payload.get("severidades", {})).items()
                    },
                )
                self.enviar_json({"ok": True, "revisao": revisao})
                return

            if url.path == "/api/escolher":
                tamanho = int(self.headers.get("Content-Length", "0") or "0")
                payload = json.loads(self.rfile.read(tamanho).decode("utf-8"))
                self.enviar_json({"path": escolher_caminho(str(payload.get("tipo", "")))})
                return

            if url.path == "/api/carregar":
                tamanho = int(self.headers.get("Content-Length", "0") or "0")
                payload = json.loads(self.rfile.read(tamanho).decode("utf-8"))
                pasta_saida = Path(str(payload.get("saida_path") or PASTA_SAIDA_PADRAO)).resolve()
                origem_texto = str(payload.get("origem_path") or "").strip()
                resultado_texto = str(payload.get("resultado_path") or "").strip()

                if not origem_texto:
                    raise ValueError("Selecione um ZIP ou uma pasta com imagens.")

                origem = Path(origem_texto).resolve()
                resultado = Path(resultado_texto).resolve() if resultado_texto else None
                self.estado.carregar(origem, pasta_saida, resultado)
                self.enviar_json(self.estado.json())
                return

            self.enviar_texto(404, "Rota não encontrada.")
        except Exception as erro:
            self.enviar_texto(400, str(erro))


def candidatos_navegador_windows() -> list[Path]:
    bases = [
        os.environ.get("PROGRAMFILES", ""),
        os.environ.get("PROGRAMFILES(X86)", ""),
        os.environ.get("LOCALAPPDATA", ""),
    ]
    relativos = [
        Path("Microsoft") / "Edge" / "Application" / "msedge.exe",
        Path("Google") / "Chrome" / "Application" / "chrome.exe",
    ]
    candidatos = []

    for base in bases:
        if not base:
            continue

        for relativo in relativos:
            candidatos.append(Path(base) / relativo)

    return candidatos


def abrir_navegador(url: str, tela_cheia: bool = True) -> None:
    if sys.platform.startswith("win"):
        # Usar diretório temporário para evitar cache de janela anterior
        import tempfile
        temp_dir = tempfile.gettempdir()
        user_data_dir = os.path.join(temp_dir, "benian_chrome_tmp")
        
        argumentos = [
            f"--app={url}",
            f"--user-data-dir={user_data_dir}",
            "--new-window",
            "--start-fullscreen"
        ]

        for candidato in candidatos_navegador_windows():
            if candidato.exists():
                subprocess.Popen(
                    [str(candidato), *argumentos],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    close_fds=True,
                )
                return

    webbrowser.open(url)


def criar_servidor(host: str, porta: int, estado: EstadoWeb) -> ThreadingHTTPServer:
    Handler.estado = estado
    tentativas = [porta] if porta == 0 else list(range(porta, porta + 20))
    ultimo_erro = None

    for porta_tentativa in tentativas:
        try:
            return ThreadingHTTPServer((host, porta_tentativa), Handler)
        except OSError as erro:
            ultimo_erro = erro

    raise RuntimeError(f"Não foi possível iniciar o servidor: {ultimo_erro}")


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="BenIan local com interface web.")
    parser.add_argument("--host", default="127.0.0.1", help="Host local do servidor.")
    parser.add_argument("--porta", type=int, default=8877, help="Porta local do servidor.")
    parser.add_argument("--origem", default="", help="ZIP ou pasta para carregar ao iniciar.")
    parser.add_argument("--resultado", default="", help="resultado.json opcional para carregar ao iniciar.")
    parser.add_argument("--saida", default=str(PASTA_SAIDA_PADRAO), help="Pasta de saída.")
    parser.add_argument("--nao-abrir", action="store_true", help="Não abre o navegador automaticamente.")
    parser.add_argument("--janela", action="store_true", help="Abre maximizado em vez de tela cheia.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    estado = EstadoWeb(pasta_saida=Path(args.saida).resolve())

    if args.origem.strip():
        resultado = Path(args.resultado).resolve() if args.resultado.strip() else None
        estado.carregar(Path(args.origem).resolve(), Path(args.saida).resolve(), resultado)

    servidor = criar_servidor(args.host, args.porta, estado)
    host_url = "127.0.0.1" if args.host in {"", "0.0.0.0"} else args.host
    url = f"http://{host_url}:{servidor.server_port}"
    print(f"BenIan iniciado em {url}")

    if not args.nao_abrir:
        abrir_navegador(url, tela_cheia=True)

    try:
        servidor.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        servidor.server_close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
