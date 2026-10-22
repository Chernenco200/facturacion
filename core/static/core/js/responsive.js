/*
 * responsive.js
 * Envuelve automáticamente cada <table> que no esté dentro de un contenedor
 * con scroll horizontal (ej. .table-responsive) en un <div class="table-responsive">.
 * Así las tablas anchas se desplazan horizontalmente en el celular en lugar de
 * desbordar la página o encoger todo el contenido.
 * También funciona con tablas que se agregan después por JavaScript.
 */
(function () {
    "use strict";

    var MAX_NIVELES = 6;

    function yaTieneScroll(tabla) {
        var el = tabla.parentElement;
        var nivel = 0;
        while (el && el !== document.body && nivel < MAX_NIVELES) {
            if (el.classList.contains("table-responsive") ||
                el.hasAttribute("data-no-responsive")) {
                return true;
            }
            var ox = window.getComputedStyle(el).overflowX;
            if (ox === "auto" || ox === "scroll") {
                return true;
            }
            el = el.parentElement;
            nivel++;
        }
        return false;
    }

    function envolver(tabla) {
        if (tabla.dataset.responsiveOk === "1") return;
        tabla.dataset.responsiveOk = "1";

        if (tabla.hasAttribute("data-no-responsive")) return;
        // No tocar tablas anidadas dentro de otra tabla
        if (tabla.parentElement && tabla.parentElement.closest("table")) return;
        if (yaTieneScroll(tabla)) return;

        var wrap = document.createElement("div");
        wrap.className = "table-responsive";
        tabla.parentNode.insertBefore(wrap, tabla);
        wrap.appendChild(tabla);
    }

    function procesar(raiz) {
        if (!raiz || !raiz.querySelectorAll) return;
        if (raiz.tagName === "TABLE") {
            envolver(raiz);
            return;
        }
        var tablas = raiz.querySelectorAll("table");
        for (var i = 0; i < tablas.length; i++) {
            envolver(tablas[i]);
        }
    }

    function iniciar() {
        procesar(document.body);

        if ("MutationObserver" in window) {
            var obs = new MutationObserver(function (mutaciones) {
                for (var i = 0; i < mutaciones.length; i++) {
                    var nodos = mutaciones[i].addedNodes;
                    for (var j = 0; j < nodos.length; j++) {
                        if (nodos[j].nodeType === 1) procesar(nodos[j]);
                    }
                }
            });
            obs.observe(document.body, { childList: true, subtree: true });
        }
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", iniciar);
    } else {
        iniciar();
    }
})();
