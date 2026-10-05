/* ReConecta — utilitários das ações de arrecadação (lista, detalhe, painel e Home).
   Expõe window.RCArrecadacao. Carregar antes do script da página. */
(function () {
  "use strict";

  var API = "/reconecta/arrecadacoes";

  function el(tag, attrs, filhos) {
    var no = document.createElement(tag);
    Object.keys(attrs || {}).forEach(function (k) {
      var v = attrs[k];
      if (v == null || v === false) return;
      if (k === "texto") no.textContent = v;
      else if (k === "classe") no.className = v;
      else no.setAttribute(k, v === true ? "" : v);
    });
    (filhos || []).forEach(function (f) {
      if (f == null || f === "" || f === false) return;
      no.appendChild(typeof f === "string" ? document.createTextNode(f) : f);
    });
    return no;
  }

  /* fetch com sessão; corpo JSON ou FormData; devolve {status, ok, corpo} */
  function requisitar(caminho, opcoes) {
    opcoes = opcoes || {};
    var init = { method: opcoes.method || "GET", credentials: "same-origin", headers: { "Accept": "application/json" } };
    if (opcoes.json !== undefined) { init.headers["Content-Type"] = "application/json"; init.body = JSON.stringify(opcoes.json); }
    if (opcoes.form) init.body = opcoes.form; // o navegador define o boundary do multipart
    return fetch(caminho.charAt(0) === "/" ? caminho : API + "/" + caminho, init).then(function (r) {
      return r.text().then(function (t) {
        var c = null;
        try { c = t ? JSON.parse(t) : null; } catch (e) { c = null; }
        return { status: r.status, ok: r.ok, corpo: c == null ? {} : c };
      });
    });
  }

  function svg(caminhos, classe) {
    var span = el("span", { classe: classe, "aria-hidden": "true" });
    span.innerHTML = '<svg viewBox="0 0 24 24" focusable="false">' + caminhos + "</svg>";
    return span;
  }
  var ICONES = {
    calendario: '<rect x="3.5" y="5" width="17" height="15" rx="3" fill="none" stroke="currentColor" stroke-width="1.8"/><path d="M3.5 10h17M8 3v4M16 3v4" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/>',
    local: '<path d="M12 21s-6.5-5.6-6.5-11a6.5 6.5 0 0 1 13 0c0 5.4-6.5 11-6.5 11z" fill="none" stroke="currentColor" stroke-width="1.8"/><circle cx="12" cy="10" r="2.3" fill="currentColor"/>',
    loja: '<path d="M4 9.5 5.6 5A1.6 1.6 0 0 1 7.1 4h9.8a1.6 1.6 0 0 1 1.5 1L20 9.5M4 9.5h16v1a2.7 2.7 0 0 1-5.3 0 2.7 2.7 0 0 1-5.4 0A2.7 2.7 0 0 1 4 10.5zM5.5 13.5V20h13v-6.5M10 20v-4h4v4" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linejoin="round"/>',
    coracao: '<path d="M12 19.5s-7.5-4.4-7.5-9.6A4.1 4.1 0 0 1 12 7.4a4.1 4.1 0 0 1 7.5 2.5c0 5.2-7.5 9.6-7.5 9.6z" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round"/>',
    seta: '<path d="M4 12h15M13 6l6 6-6 6" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/>',
    alvo: '<circle cx="12" cy="12" r="8.5" fill="none" stroke="currentColor" stroke-width="1.8"/><circle cx="12" cy="12" r="4" fill="none" stroke="currentColor" stroke-width="1.8"/><circle cx="12" cy="12" r="1.2" fill="currentColor"/>'
  };
  function icone(nome, classe) { return svg(ICONES[nome] || "", classe || "acao__icone"); }

  /* datas */
  function data(iso) {
    if (!iso) return null;
    var d = new Date(String(iso).length <= 10 ? iso + "T12:00:00" : iso);
    return isNaN(d) ? null : d;
  }
  function dataCurta(iso) { var d = data(iso); return d ? d.toLocaleDateString("pt-BR", { day: "2-digit", month: "2-digit" }) : ""; }
  function dataLonga(iso) { var d = data(iso); return d ? d.toLocaleDateString("pt-BR", { day: "2-digit", month: "long", year: "numeric" }) : ""; }
  function hojeISO() {
    var d = new Date();
    return d.getFullYear() + "-" + String(d.getMonth() + 1).padStart(2, "0") + "-" + String(d.getDate()).padStart(2, "0");
  }
  function diasRestantes(fim) {
    var f = data(fim); if (!f) return null;
    var h = data(hojeISO());
    return Math.round((f - h) / 86400000);
  }
  function prazoTexto(fim) {
    var n = diasRestantes(fim);
    if (n == null) return "";
    if (n < 0) return "encerrada";
    if (n === 0) return "termina hoje";
    if (n === 1) return "termina amanhã";
    return "faltam " + n + " dias";
  }

  /* nomes em CAIXA ALTA da Receita: mesmo formato do cabeçalho (layout.js) */
  function nome(n) {
    var R = window.ReConecta;
    return R && R.nomeTitulo ? R.nomeTitulo(n) : String(n || "");
  }
  function local(municipioUf) {
    if (!municipioUf) return "";
    var p = String(municipioUf).split("/");
    return nome(p[0]) + (p[1] ? " / " + p[1].toUpperCase() : "");
  }

  var IMG_CATEGORIA = {
    "Hortifrúti": "hortifruti", "Padaria": "padaria", "Laticínios": "laticinios", "Carnes e peixes": "carnes",
    "Grãos e cereais": "graos", "Refeições prontas": "refeicoes", "Bebidas não alcoólicas": "bebidas", "Outros": "outros"
  };
  function imgCategoria(c, tam) {
    return el("img", { src: "/static/img/doacoes/cat-" + (IMG_CATEGORIA[c] || "outros") + ".webp", alt: "", width: String(tam), height: String(tam), loading: "lazy", decoding: "async" });
  }
  function chipsCategorias(cats, max) {
    cats = cats || [];
    var lista = el("ul", { classe: "acao__cats", "aria-label": "Categorias aceitas" });
    cats.slice(0, max || cats.length).forEach(function (c) {
      lista.appendChild(el("li", { classe: "acao__cat acao__cat--" + (IMG_CATEGORIA[c] || "outros") }, [imgCategoria(c, 22), c]));
    });
    if (max && cats.length > max) lista.appendChild(el("li", { classe: "acao__cat acao__cat--mais", texto: "+" + (cats.length - max) }));
    return lista;
  }

  function plural(n, um, varios) { return n + " " + (n === 1 ? um : varios); }

  /* cartão de ação para lista pública e Home */
  function cartaoAcao(a) {
    var n = Number(a.contribuicoes_aceitas) || 0;
    return el("article", { classe: "acao" }, [
      el("div", { classe: "acao__topo" }, [
        el("p", { classe: "acao__empresa" }, [icone("loja", "acao__empresa-icone"), nome(a.empresa && a.empresa.nome)]),
        el("span", { classe: "selo selo--prazo", texto: prazoTexto(a.data_fim) })
      ]),
      el("h3", { classe: "acao__titulo" }, [el("a", { href: "/arrecadacoes/" + a.id, classe: "acao__link", texto: a.titulo })]),
      el("p", { classe: "acao__descricao", texto: a.descricao }),
      a.meta_descricao ? el("p", { classe: "acao__meta" }, [icone("alvo"), el("span", null, [el("strong", { texto: "Meta: " }), a.meta_descricao])]) : null,
      chipsCategorias(a.categorias, 4),
      el("div", { classe: "acao__rodape" }, [
        el("span", { classe: "acao__info" }, [icone("calendario"), "Até " + dataCurta(a.data_fim)]),
        a.entrega && a.entrega.municipio_uf ? el("span", { classe: "acao__info" }, [icone("local"), "Entrega em " + local(a.entrega.municipio_uf)]) : null,
        el("span", { classe: "acao__info" }, [icone("coracao"), plural(n, "doação", "doações")])
      ]),
      el("span", { classe: "acao__cta", "aria-hidden": "true" }, ["Doar para esta ação", icone("seta", "acao__cta-seta")])
    ]);
  }

  window.RCArrecadacao = {
    API: API, el: el, requisitar: requisitar, icone: icone,
    dataCurta: dataCurta, dataLonga: dataLonga, hojeISO: hojeISO, prazoTexto: prazoTexto,
    nome: nome, local: local, imgCategoria: imgCategoria, chipsCategorias: chipsCategorias,
    plural: plural, cartaoAcao: cartaoAcao, IMG_CATEGORIA: IMG_CATEGORIA
  };
})();
