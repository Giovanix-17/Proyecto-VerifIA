"""Extracción de texto con Tesseract en español (Fase 4).

Se usa ``image_to_data`` en lugar de ``image_to_string`` para conservar las
coordenadas de cada palabra y poder unir líneas del mismo globo en el
posprocesamiento. ``spa.traineddata`` es obligatorio: con ``eng`` se degradan
acentos y la ñ.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pytesseract
from numpy.typing import NDArray
from pytesseract import Output

from verifia.ocr.errors import OCRNoDisponible
from verifia.ocr.models import OpcionesOCR

_IDIOMA_OBLIGATORIO = "spa.traineddata"
_DIRECTORIOS_TESSDATA = (
    Path("/usr/share/tesseract-ocr/5/tessdata"),
    Path("/usr/share/tesseract-ocr/4.00/tessdata"),
    Path("/usr/share/tessdata"),
    Path("/usr/local/share/tessdata"),
)
_RAIZ_PROYECTO = Path(__file__).resolve().parents[3]


@dataclass(frozen=True)
class LineaOCR:
    """Línea reconocida con su caja, para agrupar globos y quitar marcas."""

    texto: str
    izquierda: int
    arriba: int
    derecha: int
    abajo: int
    confianza: float | None

    @property
    def alto(self) -> int:
        return self.abajo - self.arriba


def _candidatos_binario() -> list[Path]:
    candidatos: list[Path] = []
    personalizado = os.environ.get("TESSERACT_CMD")
    if personalizado:
        candidatos.append(Path(personalizado))
    actual = getattr(pytesseract.pytesseract, "tesseract_cmd", "")
    if actual and actual != "tesseract":
        candidatos.append(Path(actual))
    encontrado = shutil.which("tesseract")
    if encontrado:
        candidatos.append(Path(encontrado))
    local = Path(os.environ.get("LOCALAPPDATA", ""))
    candidatos.extend(
        [
            Path(r"C:\Program Files\Tesseract-OCR\tesseract.exe"),
            Path(r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe"),
            local / "Programs" / "Tesseract-OCR" / "tesseract.exe",
        ]
    )
    return [ruta for ruta in candidatos if ruta and ruta.is_file()]


def resolver_tesseract() -> Path:
    """Localiza el binario o falla con un mensaje accionable."""
    candidatos = _candidatos_binario()
    if not candidatos:
        raise OCRNoDisponible(
            "No se encontró Tesseract. Instálalo y define TESSERACT_CMD o agrégalo al PATH."
        )
    return candidatos[0]


def _normalizar_tessdata(ruta: Path) -> Path | None:
    """Acepta tanto el directorio ``tessdata`` como su carpeta padre."""
    if (ruta / _IDIOMA_OBLIGATORIO).is_file():
        return ruta
    anidado = ruta / "tessdata"
    if (anidado / _IDIOMA_OBLIGATORIO).is_file():
        return anidado
    return None


def resolver_tessdata(binario: Path | None = None) -> Path:
    """Localiza un ``tessdata`` que contenga el paquete español."""
    binario = binario or resolver_tesseract()
    candidatos: list[Path] = []
    variable = os.environ.get("TESSDATA_PREFIX")
    if variable:
        candidatos.append(Path(variable))
    candidatos.extend(
        [
            binario.parent / "tessdata",
            Path(os.environ.get("LOCALAPPDATA", "")) / "tessdata",
            _RAIZ_PROYECTO / "data" / "tessdata",
            *_DIRECTORIOS_TESSDATA,
        ]
    )

    revisados: list[str] = []
    for candidato in candidatos:
        if not str(candidato):
            continue
        encontrado = _normalizar_tessdata(candidato)
        if encontrado is not None:
            return encontrado
        revisados.append(str(candidato))

    raise OCRNoDisponible(
        "Tesseract no tiene el paquete español (spa.traineddata). "
        f"Directores revisados: {', '.join(revisados)}. "
        "Descárgalo en https://github.com/tesseract-ocr/tessdata_best y define TESSDATA_PREFIX."
    )


def _configurar(binario: Path, tessdata: Path) -> None:
    pytesseract.pytesseract.tesseract_cmd = str(binario)
    # Se usa la variable de entorno en lugar de --tessdata-dir porque pytesseract
    # no maneja de forma consistente las comillas en rutas de Windows.
    os.environ["TESSDATA_PREFIX"] = str(tessdata)


def disponibilidad() -> dict[str, str | bool]:
    """Diagnóstico para pruebas y para el mensaje de la interfaz."""
    try:
        binario = resolver_tesseract()
        tessdata = resolver_tessdata(binario)
    except OCRNoDisponible as exc:
        return {"disponible": False, "detalle": str(exc)}

    version = "desconocida"
    try:
        salida = subprocess.run(
            [str(binario), "--version"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        primera = (salida.stdout or salida.stderr).splitlines()
        if primera:
            version = primera[0].strip()
    except (OSError, subprocess.SubprocessError):  # pragma: no cover - entorno raro
        pass

    return {
        "disponible": True,
        "binario": str(binario),
        "tessdata": str(tessdata),
        "version": version,
    }


def reconocer_lineas(imagen: NDArray[np.uint8], opciones: OpcionesOCR) -> list[LineaOCR]:
    """Ejecuta Tesseract y devuelve las líneas con sus cajas y confianza."""
    if opciones.idioma != "spa":
        raise ValueError("El OCR de VerifIA exige idioma 'spa'.")

    binario = resolver_tesseract()
    tessdata = resolver_tessdata(binario)
    _configurar(binario, tessdata)
    config = (
        f"--oem 3 --psm {opciones.psm} -c preserve_interword_spaces=1"
    )

    try:
        datos = pytesseract.image_to_data(
            imagen,
            lang=opciones.idioma,
            config=config,
            output_type=Output.DICT,
        )
    except pytesseract.TesseractNotFoundError as exc:  # pragma: no cover - entorno
        raise OCRNoDisponible("Tesseract no está accesible para ejecutar el OCR.") from exc
    except pytesseract.TesseractError as exc:
        raise OCRNoDisponible(f"Tesseract falló al procesar la imagen: {exc}") from exc

    return _agrupar_palabras(datos)


def _agrupar_palabras(datos: dict) -> list[LineaOCR]:
    grupos: dict[tuple[int, int, int, int], list[int]] = {}
    for indice, texto in enumerate(datos.get("text", [])):
        limpio = (texto or "").strip()
        if not limpio:
            continue
        confianza = _confianza(datos["conf"][indice])
        if confianza is not None and confianza < 0:
            continue
        clave = (
            int(datos["page_num"][indice]),
            int(datos["block_num"][indice]),
            int(datos["par_num"][indice]),
            int(datos["line_num"][indice]),
        )
        grupos.setdefault(clave, []).append(indice)

    lineas: list[LineaOCR] = []
    for indices in grupos.values():
        palabras = [(datos["text"][i] or "").strip() for i in indices]
        izquierda = min(int(datos["left"][i]) for i in indices)
        arriba = min(int(datos["top"][i]) for i in indices)
        derecha = max(int(datos["left"][i]) + int(datos["width"][i]) for i in indices)
        abajo = max(int(datos["top"][i]) + int(datos["height"][i]) for i in indices)

        confianzas = [
            (conf, len(palabra))
            for i, palabra in zip(indices, palabras, strict=True)
            if (conf := _confianza(datos["conf"][i])) is not None and conf >= 0
        ]
        peso = sum(longitud for _, longitud in confianzas)
        promedio = (
            sum(conf * longitud for conf, longitud in confianzas) / peso if peso else None
        )
        lineas.append(
            LineaOCR(
                texto=" ".join(palabras),
                izquierda=izquierda,
                arriba=arriba,
                derecha=derecha,
                abajo=abajo,
                confianza=promedio,
            )
        )

    return sorted(lineas, key=lambda linea: (linea.arriba, linea.izquierda))


def _confianza(valor: object) -> float | None:
    try:
        return float(valor)
    except (TypeError, ValueError):
        return None
