# Explicabilidad y recomendaciones (Fase 6)

> Módulo `src/verifia/explain/`, integrado en la cascada de la Fase 5.
> Fecha de cierre: 18/11/2026.

## 1. Resumen

La Fase 6 convierte el dictamen del clasificador en algo que un ciudadano puede
entender y usar:

1. **Semáforo de tres estados** derivado de la puntuación final (0–100).
2. **Señales de alerta resaltadas** sobre el texto sanitizado, con su origen
   trazable (Nivel 1 o Nivel 2) y los offsets para que la interfaz las pinte.
3. **Resumen de tres frases** en lenguaje sencillo: qué se detectó, cuál es la
   señal más relevante y qué puede pasar si se actúa conforme al mensaje.
4. **Recomendaciones de un catálogo cerrado** por tipología, nunca redactadas
   por el LLM.
5. **Aviso orientativo obligatorio** en el 100 % de las respuestas, incluido el
   fallback.

El módulo no decide: recibe tipología y puntuación ya calculadas y no las
recalcula. Es determinista: el mismo dictamen produce exactamente la misma
explicación.

## 2. Contrato de salida

`ResultadoClasificacion` hereda de `Explicacion` y añade la trazabilidad del
dictamen. Los campos nuevos son:

| Campo | Tipo | Uso |
|---|---|---|
| `estado` | `verde` · `amarillo` · `rojo` | Color del semáforo derivado de la puntuación |
| `nivel_riesgo` | `bajo` · `medio` · `alto` | Banda coherente con la puntuación |
| `titulo` | texto | «Riesgo bajo/medio/alto» |
| `icono` | texto | Símbolo no cromático (✔, ⚠, ⛔) |
| `descripcion` | texto | Qué significa el estado |
| `accion` | texto | Qué hacer primero |
| `resumen_legible` | texto | Máximo tres frases |
| `senales_alerta` | lista de `SenalResaltada` | Máximo 5, con `frase`, `motivo`, `categoria`, `origen`, `inicio`, `fin` |
| `recomendaciones` | lista de 3–6 textos | Catálogo general + por tipología |
| `aviso` | texto constante | Herramienta orientativa (regla 13) |

El esquema valida dos coherencias: `estado` ↔ `nivel_riesgo` y
`nivel_riesgo`/`estado` ↔ `puntuacion`. Un resultado incoherente no se puede
construir, así que la interfaz nunca recibe un semáforo que contradiga la
puntuación.

## 3. Semáforo

| Color | Puntuación | Título | Icono | Acción |
|---|---:|---|---|---|
| Verde | 0–33 | Riesgo bajo | ✔ | Puede continuar, con precaución |
| Amarillo | 34–66 | Riesgo medio | ⚠ | Verifique por un canal oficial antes de actuar |
| Rojo | 67–100 | Riesgo alto | ⛔ | No actúe conforme al mensaje |

El estado se deriva **siempre de la puntuación**, nunca del `nivel_riesgo` que
propuso el LLM. El color no es el único canal: cada estado lleva título,
descripción e icono, como exige WCAG 2.1.

## 4. Señales de alerta

### 4.1 Nivel 1 — términos del modelo

El modelo final es Naive Bayes calibrado. Para cada clase se calcula la
contribución de cada palabra del TF-IDF:

```text
contribución(término) = tfidf(término) × [log P(término | clase) − promedio(log P(término | otras clases))]
```

Es el equivalente a `coef[clase] · x` en un modelo lineal. Se usan solo las
palabras del TF-IDF (no los n-gramas de carácter, que son más difíciles de
leer), se descartan stopwords, palabras de una o dos letras y bigramas que
arrastran palabras funcionales. Los términos se localizan en el texto
sanitizado de forma insensible a mayúsculas y acentos; si un término no
aparece literalmente, se omite: no se resalta nada inventado.

Los marcadores tipificados se conservan como señal legítima. Se convierten en
señal `[CODIGO]`, `[CUENTA]`, `[TARJETA]`, `[CURP]`, `[RFC]` y
`[ENLACE:dominio.tld]`; no se alerta por `[TELEFONO]`, `[CORREO]` ni
`[NOMBRE]`, porque pueden aparecer en un aviso legítimo.

### 4.2 Nivel 2 — señales del LLM

Se usan tal cual las señales que ya devolvió y verificó el Nivel 2. Cada
`frase` se localiza sobre el texto sanitizado para calcular sus offsets. Si
una frase no se localiza, se descarta; el Nivel 2 ya había comprobado que
existiera, así que esto solo ocurre ante una diferencia de normalización.

### 4.3 Categorías y prioridad

Las señales se traducen a categorías comprensibles, no se muestra el término
crudo como explicación:

| Categoría | Motivo que ve el usuario |
|---|---|
| `solicitud_codigo` | Pide o menciona un código que conviene no compartir |
| `amenaza` | Advierte una consecuencia negativa si no responde |
| `suplantacion` | Se atribuye la identidad de una institución o marca |
| `enlace_sospechoso` | Incluye un enlace que conviene verificar antes de abrirlo |
| `pago_anticipado` | Menciona un pago que conviene no adelantar |
| `premio_falso` | Ofrece un premio o beneficio condicionado |
| `oferta_laboral` | Ofrece un empleo con condiciones atractivas y poco realistas |
| `solicitud_datos` | Menciona datos personales o bancarios que conviene proteger |
| `urgencia` | Mete prisa con un plazo muy corto |
| `otro` | Término asociado con mensajes de fraude (solo LLM) |

Para el resumen y la interfaz se ordenan por relevancia: primero una solicitud
de código o una amenaza, al final una mención genérica o la urgencia. El límite
es de **cinco señales**; más de cinco abruma y no informa mejor.

### 4.4 Ejemplo

Mensaje sanitizado:

```text
Su cuenta será bloqueada hoy. Ingrese su código en [ENLACE:banco-verify.com]
```

Salida (Nivel 1, puntuación 93):

```json
{
  "estado": "rojo",
  "nivel_riesgo": "alto",
  "titulo": "Riesgo alto",
  "icono": "⛔",
  "resumen_legible": "El mensaje se parece a una suplantación bancaria. La señal más importante es: «código»: pide o menciona un código que conviene no compartir. Si comparte el código, otra persona podría autorizar cargos en su cuenta.",
  "senales_alerta": [
    {"frase": "código", "categoria": "solicitud_codigo", "origen": "nivel_1"},
    {"frase": "bloqueada", "categoria": "amenaza", "origen": "nivel_1"},
    {"frase": "[ENLACE:banco-verify.com]", "categoria": "enlace_sospechoso", "origen": "nivel_1"},
    {"frase": "cuenta", "categoria": "solicitud_datos", "origen": "nivel_1"}
  ],
  "recomendaciones": [
    "Conservar el mensaje como evidencia (captura de pantalla) antes de borrarlo.",
    "Ante cualquier duda, verificar por un canal oficial que usted consiga por su cuenta.",
    "No compartir códigos, NIP, token ni contraseñas.",
    "No entrar al enlace del mensaje.",
    "Llamar al número del reverso de su tarjeta.",
    "Revisar movimientos en la app oficial del banco."
  ],
  "aviso": "Resultado orientativo: no sustituye su criterio ni la denuncia formal ante las autoridades."
}
```

Los offsets `inicio`/`fin` se omiten aquí por brevedad; el objeto real los
incluye para que la interfaz pinte la señal sobre el texto.

## 5. Resumen legible

Plantilla determinista de tres frases:

```text
El mensaje se parece a {tipología llana}.
La señal más importante es: «{frase}»: {motivo}.
{consecuencia de actuar}
```

- Frases cortas, sin tecnicismos (no aparece «TF-IDF», «cascada» ni
  «probabilidad calibrada»).
- Sin segunda persona acusatoria: en extorsión, culpar a la víctima
  revictimiza y reduce la confianza.
- Sin cifras inventadas ni porcentajes de certeza.
- La consecuencia es una constante por tipología, no texto generado.

## 6. Catálogo de recomendaciones

Dos recomendaciones generales acompañan siempre al dictamen:

1. Conservar el mensaje como evidencia (captura de pantalla) antes de borrarlo.
2. Ante cualquier duda, verificar por un canal oficial que usted consiga por su
   cuenta.

Y tres o cuatro específicas por tipología. Las acciones cubren las previstas
en la memoria: no compartir códigos ni contraseñas, verificar por canales
oficiales, no hacer pagos anticipados, conservar evidencia y denunciar.

El catálogo es una constante de código. Ninguna recomendación se redacta con el
LLM. Las pruebas comprueban que no contiene URL, correos ni secuencias de ocho
o más dígitos; la única cifra permitida es el **911**, declarado como constante
con su fuente. Esto evita que el sistema invente teléfonos, trámites o enlaces.

## 7. Integración en la cascada

`CascadeVerifIA.analizar()` construye la explicación en los tres caminos:

| Camino | Señales | Advertencias | Aviso |
|---|---|---|---|
| Nivel 1 (alta confianza) | Marcadores + términos del modelo | — | Sí |
| Nivel 2 (zona gris) | Señales verificadas del LLM | — | Sí |
| Fallback (sin LLM o JSON inválido) | Marcadores + términos del modelo | «análisis parcial…» | Sí |
| Texto vacío | Ninguna | — | Sí |

El fallback conserva la puntuación del Nivel 1 y añade la advertencia visible
de análisis parcial (regla 8). El texto vacío devuelve un resultado verde con
el aviso de que no hay nada que clasificar.

## 8. Corrección detectada al integrar el semáforo

Al conectar el semáforo se detectó que `puntuacion_nivel1` leía la
probabilidad de la clase legítima en una posición fija del catálogo
(`TIPOLOGIAS`). scikit-learn ordena las clases alfabéticamente, así que en el
modelo real `legitimo` ocupa la posición 1 y la posición 0 es `extorsion`. El
efecto era grave: un mensaje legítimo con `P(extorsión)` baja recibía una
puntuación cercana a 95 y se mostraba en rojo.

La corrección pasa `modelo.classes_` a `puntuacion_nivel1`, que localiza
`legitimo` en el orden real. Se añadió una prueba de regresión. Las métricas de
clasificación de la Fase 5 **no cambian** (F1, recall y matriz de confusión se
calculan con `argmax`, no con la puntuación), pero el conteo de discrepancias
de puntuación bajó de 8 a 5. La nota está en
[`metricas_clasificador.md`](metricas_clasificador.md) §6.5.

## 9. Pruebas

`tests/test_explain.py` cubre los criterios de la skill:

| Prueba | Qué verifica |
|---|---|
| Semáforo en los límites 0/33/34/66/67/100 | Banda correcta y texto + icono |
| Coherencia del esquema | Un estado o una puntuación incoherentes no se pueden construir |
| Snapshot 5 tipologías × 3 estados | El resumen no cambia sin revisión explícita |
| Determinismo | Dos llamadas con el mismo dictamen son idénticas |
| Catálogo | 3–6 recomendaciones, sin URL, correos ni teléfonos inventados |
| Aviso | Presente en Nivel 1, Nivel 2 y fallback |
| Señales | Máximo 5, frase presente y offsets correctos |
| Señal alucinada | Se descarta si la frase no está en el texto |
| Marcadores | Solo código, datos y enlace; no teléfono, correo ni nombre |
| Términos Nivel 1 | Naive Bayes y modelo calibrado devuelven términos útiles |
| Integración | La cascada devuelve semáforo, recomendaciones y aviso en los tres caminos |

Resultado de la suite completa al cierre: **171 pruebas en verde**, `ruff` sin
errores.

## 10. Limitaciones

- **La explicación del Nivel 1 es aproximada.** Indica qué palabras del propio
  mensaje empujan la predicción, no una relación causal. Un término puede ser
  señal en un contexto y no en otro; por eso el resumen usa también la
  tipología y el catálogo.
- **Mensajes muy cortos o con escritura muy ofuscada** pueden no tener términos
  útiles. En ese caso el resumen dice que no se identificó una señal concreta;
  el semáforo sigue mandando.
- **Las señales del Nivel 2 dependen del LLM.** Ya se validan con Pydantic y se
  comprueba que la frase exista en el texto, pero su redacción puede ser
  redundante o poco precisa.
- **No hay validación con usuarios todavía.** La claridad del resumen, el tono
  y la utilidad percibida se medirán en la Fase 8 con SUS y con la comparación
  de decisiones antes/después de ver la alerta.
- **No se muestran más de cinco señales.** Es una decisión de diseño para no
  abrumar; si el usuario necesita el detalle completo, el Nivel 2 conserva su
  lista original en el dictamen interno, pero la respuesta al ciudadano se
  limita a cinco.
