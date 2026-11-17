# Fuentes públicas revisadas — Fase 2

Registro de las fuentes consultadas para la recolección de mensajes con
`origen: publico`. Se documenta **qué aporta cada una** y **por qué no se usó
como texto verbatim** en el corpus.

Fecha de consulta: 16/11/2026.

| Fuente | Tipo | Aporte | Uso en el corpus |
|---|---|---|---|
| [Condusef — Portal de Fraudes Financieros](https://phpapps.condusef.gob.mx/fraudes_financieros/index.php) | Institución financiera | Reporte y consulta de números, sitios e instituciones fraudulentas | Contexto; no publica mensajes completos |
| [Condusef — contenido sobre smishing](https://www.condusef.gob.mx/?p=contenido&idc=2451&idcat=3) | Institución financiera | Definición y recomendaciones | Contexto; sin mensajes citados |
| [Guardia Nacional CERT-MX — Recomendaciones ante paquete retenido](https://www.gob.mx/gncertmx/articulos/recomendaciones-ante-paquete-retenido) | Autoridad | Recomendaciones y detección de faltas de ortografía | Contexto; no reproduce el SMS |
| [Scotiabank — ¿Cómo funciona la estafa del paquete retenido?](https://www.scotiabank.com.mx/blog/para-ti/para-ti-como-funciona-la-estafa-del-paquete-retenido) | Banca | Modus operandi, medios y señales | Contexto; describe, no cita el mensaje |
| [Debate — Condusef alerta por smishing y SMS envenenado](https://www.debate.com.mx/consejos/condusef-alerta-por-smishing-y-sms-envenenado-en-mexico-como-evitar-fraudes-bancarios-20260518-0186.html) | Prensa | Características del SMS envenenado y frases urgentes | Contexto; sin texto literal |
| [Infobae — Así extorsionan delincuentes por medio de WhatsApp](https://www.infobae.com/mexico/2024/08/06/asi-extorsionan-delincuentes-por-medio-de-whatsapp/) | Prensa | Tres modos de suplantación de WhatsApp reportados por la SSPC | Contexto; sin mensaje completo |
| [ADN40 — Este es el mensaje que reciben las víctimas de extorsión por WhatsApp](https://www.adn40.mx/es-tendencia/extorsion-por-whatsapp-como-son-los-mensajes-que-reciben-las-victimas/) | Prensa | Cita una frase de contacto: «Lo siento, ¿quién eres? Te encontré en mi libreta de direcciones.» | Solo como evidencia de la fase de contacto; no es un mensaje de extorsión completo |
| [Proceso — Estafa de trabajo por WhatsApp: task scam](https://www.proceso.com.mx/ciencia-tecnologia/2026/8/10/estafa-de-trabajo-por-whatsapp-como-identificar-una-task-scam-377734.html) | Prensa | Mecanismo de la estafa de tareas y señales de alerta | Contexto; sin mensaje literal |
| [MIT Sloan Management Review México — Ofertas de trabajo falsas por WhatsApp](https://www.mitsloanreview.mx/ciberseguridad/ofertas-de-trabajo-falsas-por-whatsapp-el-fraude-silencioso-que-va-en-aumento/) | Prensa | Relato de una víctima y tácticas de reclutamiento | Contexto; paráfrasis, no mensaje textual |
| [Computrabajo — Cómo evitar las ofertas de empleo fraudulentas](https://mx.computrabajo.com/desarrollo-profesional/computrabajo-te-ayuda/evitar-ofertas-de-empleo-fraudulentas) | Portal de empleo | Cobros por pruebas psicométricas y médicas | Contexto; sin mensaje completo |

## Decisión

No se incorporó una colección `publico` al corpus de 500. Las fuentes revisadas
**describen** las modalidades y dan recomendaciones, pero no publican el texto
completo de los mensajes; reconstruirlo habría convertido la fuente en una
paráfrasis y la etiqueta `publico` sería engañosa. Es la misma limitación que
señala la skill `verifia-corpus`: no existe un corpus público de smishing
mexicano listo para usar.

El esquema de anotación ya admite `origen: publico` con el campo `fuente`. Si el
autor consigue capturas propias o mensajes publicados textualmente, se añaden a
`data/raw/publico.jsonl` con su URL y se reconstruye el corpus con
`scripts/corpus_build.py`.

## Consecuencia para el reporte

- El corpus combina `manual` (redactado para el proyecto), `plantilla_legitima`
  (notificaciones cotidianas) y `sintetico_llm` (generado y revisable).
- La ausencia de `publico` verbatim se declara como **limitación de
  representatividad**: los mensajes sintéticos pueden no cubrir variantes
  locales que sí aparecen en capturas reales.
- La validación con capturas de la Fase 4 y la revisión humana de la Fase 8 son
  las salvaguardas previstas para esa limitación.
