#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
# platform_icons.py — SVGs de los iconos de la plataforma
#
# Responsabilidad única: contener los strings SVG de los 3 iconos
# que se muestran en la zona de plataforma del fondo.
#
# NOTA: los SVGs están limpios — sin encabezado XML ni DOCTYPE.
# MOTIVO: QSvgRenderer de PyQt5 no puede resolver referencias
#   externas del DOCTYPE generado por potrace, lo que hace que
#   el renderer marque el SVG como inválido y no muestre nada.
#   Eliminando el encabezado y dejando solo el bloque <svg>
#   el renderer lo acepta correctamente.
#
# USO en main_window.py:
#   from platform_icons import SVG_LEFT, SVG_CHAIRMAN, SVG_RIGHT


# Icono preset Left — dos personas de pie
SVG_LEFT = """
<svg version="1.0" xmlns="http://www.w3.org/2000/svg"
 width="100.000000pt" height="100.000000pt" viewBox="0 0 100.000000 100.000000"
 preserveAspectRatio="xMidYMid meet">
<metadata>
Created by potrace 1.16, written by Peter Selinger 2001-2019
</metadata>
<g transform="translate(0.000000,100.000000) scale(0.022727,-0.021739)"
fill="#000000" stroke="none">
<path d="M920 4545 c-140 -40 -249 -158 -281 -306 -36 -166 54 -355 204 -429
252 -123 528 15 579 290 31 166 -66 346 -229 422 -81 38 -186 47 -273 23z
M3246 4539 c-234 -80 -339 -331 -234 -556 30 -65 115 -148 183 -179 162 -74
331 -45 456 79 121 120 149 291 75 452 -79 172 -300 266 -480 204z M875 3694
c-11 -2 -45 -9 -75 -15 -203 -39 -356 -132 -503 -308 -175 -209 -264 -398
-274 -587 -14 -246 98 -424 340 -543 94 -46 228 -91 271 -91 33 0 88 33 107
64 23 38 25 106 4 146 -18 35 -48 52 -135 75 -251 69 -353 197 -306 385 17 68
94 231 111 237 7 2 17 -76 29 -206 24 -274 23 -271 71 -298 22 -12 52 -25 68
-28 l27 -7 0 130 c0 72 4 133 8 136 4 2 156 -17 337 -42 l330 -47 3 -419 2
-418 -32 6 c-18 3 -87 12 -153 21 -66 8 -203 28 -305 43 l-185 28 -5 69 -5 69
-47 12 -48 12 0 -47 c0 -104 31 -466 40 -475 6 -6 10 -229 10 -621 l0 -611 26
-53 c34 -67 86 -103 158 -109 63 -5 115 10 157 45 67 56 63 24 69 708 l5 620
50 0 50 0 5 -620 c4 -552 7 -623 22 -650 73 -133 265 -141 353 -16 l30 43 3
626 c1 344 6 630 11 636 12 15 18 73 41 396 26 363 58 772 66 829 l6 44 45
-84 c138 -259 370 -479 504 -479 78 0 139 64 139 145 0 57 -24 91 -89 125
-194 104 -374 400 -486 804 -13 47 -26 68 -68 108 -96 92 -290 173 -487 203
-87 14 -247 18 -295 9z M3235 3690 c-270 -28 -477 -153 -645 -392 -203 -288
-257 -633 -133 -859 77 -142 312 -319 424 -319 75 0 148 83 135 154 -10 52
-40 82 -129 128 -152 79 -221 178 -221 318 0 41 8 103 17 137 17 65 74 199 81
192 3 -2 14 -119 25 -259 25 -293 11 -262 149 -336 107 -57 137 -100 137 -197
0 -64 -3 -77 -30 -114 -42 -58 -99 -93 -152 -93 l-43 0 0 -44 c0 -88 31 -411
40 -420 6 -6 10 -246 10 -623 0 -608 0 -614 21 -656 39 -76 96 -111 184 -111
76 -1 129 25 170 83 l30 43 5 621 5 622 50 0 50 0 5 -622 5 -621 30 -44 c68
-95 202 -114 297 -41 76 59 73 25 76 717 1 372 6 624 12 631 9 10 40 340 40
420 l0 33 -41 -10 c-90 -23 -196 28 -238 115 -43 90 -18 181 72 263 29 26 97
90 152 142 97 94 99 97 106 151 4 31 8 85 8 121 1 72 15 109 27 75 6 -18 46
-113 80 -192 l14 -32 -189 -176 c-104 -98 -194 -188 -200 -202 -41 -89 27
-193 126 -193 45 0 91 36 283 220 100 96 195 186 211 199 43 36 69 83 69 128
0 27 -33 116 -110 299 -217 508 -201 475 -256 530 -146 144 -491 242 -759 214z
M690 2597 l0 -105 30 -12 c17 -7 46 -31 65 -53 83 -97 56 -258 -52 -311 -38
-19 -42 -25 -43 -58 0 -31 4 -39 23 -43 18 -4 420 -61 481 -68 17 -2 18 12 17
333 -1 184 -5 338 -9 341 -6 6 -283 47 -432 65 -25 3 -53 8 -62 11 -16 4 -18
-5 -18 -100z"/>
</g>
</svg>
"""

# Icono preset Chairman — atril sin micrófono
SVG_CHAIRMAN = """
<svg version="1.0" xmlns="http://www.w3.org/2000/svg"
 width="100.000000pt" height="100.000000pt" viewBox="0 0 100.000000 100.000000"
 preserveAspectRatio="xMidYMid meet">
<metadata>
Created by potrace 1.16, written by Peter Selinger 2001-2019
</metadata>
<g transform="translate(0.000000,100.000000) scale(0.019531,-0.019531)"
fill="#000000" stroke="none">
<path d="M860 3852 c0 -9 21 -64 46 -122 25 -58 54 -125 63 -150 68 -172 336
-788 349 -803 14 -15 31 -17 129 -15 l113 3 3 263 2 264 37 34 38 34 920 0
920 0 38 -34 37 -34 2 -264 3 -263 113 -3 c80 -2 117 1 129 10 16 12 219 481
451 1038 8 19 12 41 10 48 -4 9 -354 12 -1704 12 -1616 0 -1699 -1 -1699 -18z
M1660 2035 l0 -1235 900 0 900 0 0 1235 0 1235 -900 0 -900 0 0 -1235z m1569
696 l31 -29 0 -330 c0 -191 -4 -342 -10 -356 -5 -14 -24 -35 -42 -46 -32 -19
-51 -20 -641 -20 -542 0 -613 2 -643 16 -65 31 -64 23 -64 397 l0 339 31 29
31 29 638 0 638 0 31 -29z M1950 2360 l0 -310 610 0 610 0 0 310 0 310 -610 0
-610 0 0 -310z M1330 512 l0 -199 503 -6 c553 -8 1951 -9 1958 -3 2 2 3 95 1
205 l-3 201 -1229 0 -1230 0 0 -198z"/>
</g>
</svg>
"""

# Icono preset Right — mesa de conferencia con sillas
SVG_RIGHT = """
<svg version="1.0" xmlns="http://www.w3.org/2000/svg"
 width="100.000000pt" height="100.000000pt" viewBox="0 0 100.000000 100.000000"
 preserveAspectRatio="xMidYMid meet">
<metadata>
Created by potrace 1.16, written by Peter Selinger 2001-2019
</metadata>
<g transform="translate(0.000000,100.000000) scale(0.022371,-0.032258)"
fill="#000000" stroke="none">
<path d="M545 2987 c-119 -46 -185 -144 -185 -273 0 -107 55 -195 153 -244
141 -70 305 -17 380 123 31 60 31 194 0 253 -31 58 -100 121 -152 139 -52 18
-153 19 -196 2z M3671 2987 c-52 -16 -135 -99 -161 -159 -28 -65 -25 -171 7
-233 73 -142 238 -196 382 -124 106 53 158 147 149 271 -7 108 -62 188 -162
234 -56 26 -152 31 -215 11z M423 2384 c-56 -20 -126 -84 -151 -137 -55 -116
-105 -462 -125 -857 -2 -30 -4 144 -5 388 l-2 442 -70 0 -70 0 0 -689 0 -690
26 -20 c25 -20 40 -21 216 -21 l188 0 -2 -248 -3 -247 -212 -3 -213 -2 0 -70
0 -70 2235 0 2235 0 0 70 0 70 -242 2 -243 3 -3 247 -2 248 190 0 c189 0 191
0 215 25 l25 24 0 686 0 685 -70 0 -70 0 -2 -442 c-1 -322 -3 -407 -9 -311
-16 286 -62 614 -105 744 -19 58 -72 121 -132 157 -42 24 -57 27 -137 27 -103
0 -145 -16 -222 -88 -59 -54 -74 -86 -128 -273 -25 -88 -49 -162 -53 -165 -4
-3 -108 -18 -232 -33 -146 -18 -237 -34 -259 -45 -67 -34 -91 -126 -47 -178
l24 -28 366 -3 366 -3 0 -177 0 -177 -148 0 c-141 0 -149 -1 -198 -27 -62 -32
-108 -77 -133 -127 -9 -20 -44 -110 -76 -201 -32 -91 -91 -255 -130 -365 l-72
-200 -332 -3 -331 -2 0 393 0 394 153 6 c467 20 958 162 1106 321 l24 26 -304
0 c-273 0 -308 2 -344 19 -127 57 -175 203 -111 334 44 91 127 149 235 163 68
9 55 15 -89 48 -234 52 -417 69 -745 70 -328 1 -501 -16 -745 -70 -146 -33
-158 -39 -87 -48 150 -19 261 -138 261 -280 0 -105 -58 -188 -153 -222 -26
-10 -119 -13 -336 -14 l-300 -1 47 -43 c166 -153 636 -283 1096 -304 l142 -7
1 -390 0 -390 -332 0 -333 0 -73 205 c-40 113 -100 282 -134 375 -79 223 -109
268 -209 317 -39 20 -65 23 -192 26 l-148 4 0 174 0 174 361 0 361 0 30 30
c27 27 30 36 26 74 -6 52 -32 90 -73 110 -16 8 -124 26 -240 41 -115 14 -219
28 -231 30 -17 4 -27 28 -63 152 -23 82 -50 166 -59 188 -23 56 -97 132 -157
163 -63 32 -178 40 -242 16z m-233 -1441 c0 -2 -11 -3 -25 -3 -23 0 -25 3 -25
52 l0 51 25 -49 c14 -27 25 -50 25 -51z m4080 47 c0 -47 -1 -50 -26 -50 -14 0
-24 3 -22 8 2 4 13 26 24 49 10 24 20 43 22 43 1 0 2 -22 2 -50z m-3241 -433
c45 -133 81 -245 81 -250 0 -4 -121 -7 -270 -7 l-270 0 0 250 0 250 189 0 189
0 81 -243z m2811 -7 l0 -250 -270 0 c-148 0 -270 3 -270 7 0 5 36 117 81 250
l81 243 189 0 189 0 0 -250z"/>
</g>
</svg>
"""

SVG_WHEELCHAIR = """
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 280 275" width="280" height="275">
  <g fill="none" stroke="#1a1a1a" stroke-linecap="round" stroke-linejoin="round">

    <!-- puntal delantero: se dibuja primero, queda detrás de la rueda -->
    <line x1="164" y1="131" x2="228" y2="190" stroke-width="6"/>

    <!-- rueda trasera grande -->
    <circle cx="147" cy="192" r="78" stroke-width="8"/>
    <circle cx="147" cy="192" r="59" stroke-width="4"/>
    <circle cx="147" cy="192" r="9"  stroke-width="5"/>
    <circle cx="147" cy="192" r="4"  stroke-width="3"/>
    <line x1="147" y1="183" x2="147" y2="133" stroke-width="3.5"/>
    <line x1="147" y1="201" x2="147" y2="251" stroke-width="3.5"/>
    <line x1="138" y1="192" x2="88"  y2="192" stroke-width="3.5"/>
    <line x1="156" y1="192" x2="206" y2="192" stroke-width="3.5"/>
    <line x1="153" y1="186" x2="189" y2="150" stroke-width="3.5"/>
    <line x1="141" y1="198" x2="105" y2="234" stroke-width="3.5"/>
    <line x1="153" y1="198" x2="189" y2="234" stroke-width="3.5"/>
    <line x1="141" y1="186" x2="105" y2="150" stroke-width="3.5"/>

    <!-- rueda delantera pequeña -->
    <circle cx="240" cy="222" r="29" stroke-width="7"/>
    <circle cx="240" cy="222" r="12" stroke-width="4"/>
    <circle cx="240" cy="222" r="5"  stroke-width="3"/>
    <line x1="240" y1="193" x2="240" y2="177" stroke-width="6"/>
    <line x1="228" y1="190" x2="252" y2="190" stroke-width="6"/>
    <circle cx="240" cy="169" r="6" stroke-width="4.5"/>

    <!-- reposacabezas / barra superior horizontal -->
    <rect x="48" y="14" width="78" height="18" rx="4" stroke-width="6"/>

    <!-- respaldo: tubo vertical -->
    <rect x="60" y="30" width="18" height="90" rx="3" stroke-width="6"/>

    <!-- batería: pegada a la izquierda del tubo vertical -->
    <rect x="14" y="52" width="46" height="78" rx="5" stroke-width="7"/>
    <rect x="24" y="43" width="14" height="11" rx="2" stroke-width="5"/>
    <polyline points="44,65 30,88 45,88 31,124" stroke-width="4.5"/>

    <!-- apoyabrazos horizontal -->
    <rect x="78" y="77" width="82" height="13" rx="5" stroke-width="6"/>

    <!-- joystick: poste + bola -->
    <line x1="154" y1="77" x2="154" y2="57" stroke-width="6"/>
    <circle cx="154" cy="46" r="12" stroke-width="5"/>

    <!-- asiento -->
    <rect x="78" y="115" width="88" height="17" rx="4" stroke-width="6"/>

  </g>
</svg>
"""
