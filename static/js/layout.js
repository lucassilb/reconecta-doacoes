/* ReConecta — cabeçalho, rodapé e estado de sessão compartilhados (Frente E).

   Uso na página:
     <header data-layout="cabecalho"></header>
     <main id="conteudo">…</main>
     <footer data-layout="rodape"></footer>
     <script src="/static/js/layout.js" defer></script>

   API para outras páginas:
     window.ReConecta.sessao            Promise<usuario | null> (resultado de GET /reconecta/auth/me)
     window.ReConecta.atualizarSessao() refaz a consulta e redesenha o cabeçalho; devolve a Promise
     window.ReConecta.sair()            POST /reconecta/auth/logout e volta para /
     window.ReConecta.nomeTitulo(nome)  "PADARIA PAO DOURADO LTDA" → "Padaria Pao Dourado LTDA"
     window.ReConecta.formatarTelefone(t) "11987654321" → "(11) 98765-4321"
     window.ReConecta.dataBrasilia(iso)  interpreta datas da API com fuso explícito
     window.ReConecta.diaISO(data)       dia civil em Brasília (AAAA-MM-DD)
     evento "reconecta:sessao" no document, detail = { usuario }  (usuario null = deslogado) */
(function () {
  "use strict";

  var NAV = [
    { rotulo: "Início", href: "/" },
    { rotulo: "Sobre", href: "/sobre" },
    { rotulo: "Doações", href: "/#doacoes" },
    { rotulo: "Como funciona", href: "/#como-funciona" },
    { rotulo: "Dashboard", href: "/dashboard" }
  ];

  var MARCA_SVG =
    '<svg viewBox="0 0 40 40" aria-hidden="true" focusable="false">' +
    '<circle cx="20" cy="20" r="20" fill="var(--verde)"/>' +
    '<path d="M12 24c0-6.6 5-11.5 12.5-12-.4 7.4-5.3 12.3-11.9 12.3" fill="none" stroke="var(--folha)" stroke-width="2.4" stroke-linecap="round"/>' +
    '<path d="M13 27.5c2.6-4.4 6-7.6 10.4-9.6" fill="none" stroke="var(--folha)" stroke-width="2.4" stroke-linecap="round"/>' +
    '<path d="M27.5 22.5a8 8 0 0 1-8.5 7.4" fill="none" stroke="var(--trigo)" stroke-width="2.4" stroke-linecap="round"/>' +
    '<path d="M20.6 27.6l-1.8 2.3 2.4 1.7" fill="none" stroke="var(--trigo)" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"/>' +
    "</svg>";

  var caminho = normalizar(location.pathname);

  function normalizar(p) {
    p = String(p || "/").replace(/\/index\.html$/, "/").replace(/\.html$/, "");
    if (p.length > 1) p = p.replace(/\/+$/, "");
    return p || "/";
  }

  function el(tag, attrs, filhos) {
    var no = document.createElement(tag);
    Object.keys(attrs || {}).forEach(function (k) {
      if (k === "texto") no.textContent = attrs[k];
      else if (k === "html") no.innerHTML = attrs[k];
      else if (k === "classe") no.className = attrs[k];
      else no.setAttribute(k, attrs[k]);
    });
    (filhos || []).forEach(function (f) {
      if (f == null) return;
      no.appendChild(typeof f === "string" ? document.createTextNode(f) : f);
    });
    return no;
  }

  function linkMarca() {
    return el("a", { classe: "cabecalho__marca", href: "/", "aria-label": "ReConecta, página inicial" }, [
      el("span", { html: MARCA_SVG, "aria-hidden": "true", style: "display:contents" }),
      el("span", { classe: "cabecalho__nome", texto: "ReConecta" })
    ]);
  }

  function ehAtual(href) {
    return href.indexOf("#") === -1 && normalizar(href) === caminho;
  }

  function linkNav(item) {
    var attrs = { href: item.href };
    if (ehAtual(item.href)) attrs["aria-current"] = "page";
    return el("a", attrs, [item.rotulo]);
  }

  /* ---------- cabeçalho ---------- */

  var aba = null;

  function montarCabecalho(alvo) {
    alvo.classList.add("cabecalho");
    alvo.replaceChildren();

    var nav = el("nav", { classe: "cabecalho__nav", id: "rc-nav", "aria-label": "Principal" }, [
      el("ul", null, NAV.map(function (item) { return el("li", null, [linkNav(item)]); }))
    ]);

    var menu = el("button", {
      type: "button", classe: "cabecalho__menu", "aria-expanded": "false", "aria-controls": "rc-nav"
    }, [el("span", { classe: "cabecalho__menu-icone", "aria-hidden": "true" }), el("span", { classe: "sr-only", texto: "Menu" })]);

    function fecharMenu() {
      menu.setAttribute("aria-expanded", "false");
      nav.classList.remove("is-aberta");
    }
    menu.addEventListener("click", function () {
      var abrir = menu.getAttribute("aria-expanded") !== "true";
      menu.setAttribute("aria-expanded", String(abrir));
      nav.classList.toggle("is-aberta", abrir);
      if (abrir) { var primeiro = nav.querySelector("a"); if (primeiro) primeiro.focus(); }
    });
    nav.addEventListener("click", function (e) { if (e.target.closest("a")) fecharMenu(); });
    document.addEventListener("keydown", function (e) {
      if (e.key === "Escape" && nav.classList.contains("is-aberta")) { fecharMenu(); menu.focus(); }
    });
    document.addEventListener("click", function (e) {
      if (nav.classList.contains("is-aberta") && !alvo.contains(e.target)) fecharMenu();
    });

    aba = el("div", { classe: "cabecalho__aba", "aria-busy": "true", "aria-live": "polite" });
    desenharAba(undefined);

    alvo.append(linkMarca(), menu, nav, aba);

    // link "pular para o conteúdo", se a página não trouxe um
    var main = document.querySelector("main");
    if (main && !document.querySelector(".pular")) {
      if (!main.id) main.id = "conteudo";
      document.body.insertBefore(el("a", { classe: "pular", href: "#" + main.id, texto: "Pular para o conteúdo" }), document.body.firstChild);
    }
  }

  /* Nomes em CAIXA ALTA (como vêm da Receita) em formato de título,
     preservando siglas societárias e com conectivos em minúsculas:
     "ARCOS DOURADOS COMERCIO DE ALIMENTOS SA" → "Arcos Dourados Comercio de Alimentos SA". */
  var SIGLAS = /^(S\/?A|S\.A\.?|LTDA\.?|ME|EPP|EIRELI|MEI|SS)$/;
  var CONECTIVOS = /^(de|da|do|das|dos|e|em|para)$/;
  function nomeTitulo(nome) {
    var n = String(nome || "").trim().replace(/\s+/g, " ");
    if (!n || n !== n.toUpperCase()) return n;
    return n.split(" ").map(function (p, i) {
      if (SIGLAS.test(p)) return p;
      var min = p.toLowerCase();
      if (i > 0 && CONECTIVOS.test(min)) return min;
      return min.charAt(0).toUpperCase() + min.slice(1);
    }).join(" ");
  }

  /* (11) 98765-4321 | (11) 4196-9800; outros formatos ficam como vieram */
  function formatarTelefone(t) {
    var d = String(t || "").replace(/\D+/g, "");
    if (d.length === 11) return "(" + d.slice(0, 2) + ") " + d.slice(2, 7) + "-" + d.slice(7);
    if (d.length === 10) return "(" + d.slice(0, 2) + ") " + d.slice(2, 6) + "-" + d.slice(6);
    return String(t || "");
  }

  var FUSO = "America/Sao_Paulo";
  function dataBrasilia(iso) {
    if (!iso) return null;
    var valor = String(iso);
    if (/^\d{4}-\d{2}-\d{2}$/.test(valor)) valor += "T12:00:00Z";
    else if (/^\d{4}-\d{2}-\d{2}T/.test(valor) && !/(Z|[+-]\d{2}:\d{2})$/.test(valor)) valor += "-03:00";
    var data = new Date(valor);
    return isNaN(data) ? null : data;
  }

  function diaISO(data) {
    var partes = new Intl.DateTimeFormat("en-US", {
      timeZone: FUSO, year: "numeric", month: "2-digit", day: "2-digit"
    }).formatToParts(data);
    var campos = {};
    partes.forEach(function (parte) { campos[parte.type] = parte.value; });
    return campos.year + "-" + campos.month + "-" + campos.day;
  }

  function nomeCurto(usuario) {
    // empresa: as duas primeiras palavras do nome ("Arcos Dourados"); pessoa: primeiro nome.
    // O nome completo fica no title do elemento.
    if (usuario.tipo !== "empresa") return primeiroNome(usuario.nome);
    var palavras = nomeTitulo(usuario.nome).split(" ").filter(function (p) { return !SIGLAS.test(p); });
    var curto = palavras.slice(0, 2);
    if (curto.length === 2 && CONECTIVOS.test(curto[1])) curto = palavras.slice(0, 3);
    return curto.join(" ");
  }

  function primeiroNome(nome) {
    var n = String(nome || "").trim();
    if (!n) return "";
    var palavra = n.split(/\s+/)[0];
    // nomes de empresa em CAIXA ALTA ficam mais legíveis em formato de título
    if (palavra === palavra.toUpperCase()) palavra = palavra.charAt(0) + palavra.slice(1).toLowerCase();
    return palavra;
  }

  function desenharAba(usuario) {
    if (!aba) return;
    aba.replaceChildren();
    if (usuario) {
      var painel = { href: "/painel" };
      if (caminho === "/painel") painel["aria-current"] = "page";
      var sair = el("button", { type: "button", classe: "cabecalho__sair", texto: "Sair" });
      sair.addEventListener("click", function () { sair.disabled = true; api.sair(); });
      aba.append(
        el("span", { classe: "cabecalho__ola", title: usuario.nome || "" }, ["Olá, ", el("strong", { texto: nomeCurto(usuario) })]),
        el("a", painel, ["Painel"]),
        sair
      );
    } else {
      var entrar = { href: "/entrar" };
      if (caminho === "/entrar") entrar["aria-current"] = "page";
      var cadastrar = { href: "/cadastro", classe: "btn btn--primario btn--pequeno" };
      if (caminho === "/cadastro") cadastrar["aria-current"] = "page";
      aba.append(el("a", entrar, ["Entrar"]), el("a", cadastrar, ["Cadastrar"]));
    }
    aba.setAttribute("aria-busy", usuario === undefined ? "true" : "false");
  }

  /* ---------- rodapé ---------- */

  function montarRodape(alvo) {
    alvo.classList.add("rodape");
    alvo.replaceChildren();
    function coluna(titulo, links) {
      return el("div", null, [
        el("h2", { texto: titulo }),
        el("ul", null, links.map(function (l) { return el("li", null, [el("a", { href: l[1] }, [l[0]])]); }))
      ]);
    }
    alvo.append(
      el("div", { classe: "rodape__marca" }, [
        linkMarca(),
        el("p", { texto: "Plataforma em que empresas do setor de alimentos publicam o que precisam e pessoas e empresas doam." })
      ]),
      el("div", { classe: "rodape__colunas" }, [
        coluna("Plataforma", [["Início", "/"], ["Doações disponíveis", "/#doacoes"], ["Como funciona", "/#como-funciona"], ["Dashboard", "/dashboard"], ["Sobre", "/sobre"]]),
        coluna("Participe", [["Cadastrar", "/cadastro"], ["Entrar", "/entrar"], ["Painel", "/painel"], ["Documentação da API", "/swagger"]])
      ]),
      el("div", { classe: "rodape__base" }, [
        el("span", { texto: "ReConecta · Projeto acadêmico do CP1 de Computational Thinking with Python" }),
        el("span", { texto: "Alimento bom não é desperdício." })
      ])
    );
  }

  /* ---------- sessão ---------- */

  /* Uma única chamada a GET /reconecta/auth/me por página: o cabeçalho e a
     página (painel.js, entrar.js) reaproveitam a mesma resposta em
     window.ReConecta.sessaoResposta = Promise<{status, ok, corpo}> (rejeita sem rede). */
  function buscarSessao() {
    var controle = typeof AbortController === "function" ? new AbortController() : null;
    var limite = setTimeout(function () { if (controle) controle.abort(); }, 6000);
    return fetch("/reconecta/auth/me", {
      credentials: "same-origin",
      headers: { "Accept": "application/json" },
      signal: controle ? controle.signal : undefined
    }).then(function (r) {
      clearTimeout(limite);
      return r.json().catch(function () { return null; }).then(function (corpo) {
        return { status: r.status, ok: r.ok, corpo: corpo || {} };
      });
    }, function (erro) { clearTimeout(limite); throw erro; });
  }

  function consultarSessao(resposta) {
    return resposta.then(function (r) { return r.ok ? r.corpo : null; }, function () { return null; })
      .then(function (usuario) {
        usuario = usuario && typeof usuario === "object" && usuario.nome !== undefined ? usuario : null;
        desenharAba(usuario);
        document.dispatchEvent(new CustomEvent("reconecta:sessao", { detail: { usuario: usuario } }));
        return usuario;
      });
  }

  var api = window.ReConecta = window.ReConecta || {};
  api.nomeTitulo = nomeTitulo;
  api.formatarTelefone = formatarTelefone;
  api.fuso = FUSO;
  api.dataBrasilia = dataBrasilia;
  api.diaISO = diaISO;
  api.atualizarSessao = function () {
    api.sessaoResposta = buscarSessao();
    api.sessao = consultarSessao(api.sessaoResposta);
    return api.sessao;
  };
  // A consulta começa já no carregamento do script, antes do DOM, para a página reaproveitar.
  api.sessaoResposta = buscarSessao();
  api.sair = function () {
    return fetch("/reconecta/auth/logout", { method: "POST", credentials: "same-origin" })
      .catch(function () {})
      .then(function () { location.href = "/"; });
  };

  function iniciar() {
    document.querySelectorAll('[data-layout="cabecalho"]').forEach(montarCabecalho);
    document.querySelectorAll('[data-layout="rodape"]').forEach(montarRodape);
    api.sessao = consultarSessao(api.sessaoResposta);
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", iniciar);
  else iniciar();
})();
