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
     evento "reconecta:sessao" no document, detail = { usuario }  (usuario null = deslogado)

   Tempo real (barramento de eventos do navegador):
     Só este arquivo abre a conexão: EventSource("/reconecta/tempo-real"), com retomada pelo id;
     se falhar ou vier 503, consulta GET /reconecta/novidades a cada 10 s.
     Para cada evento dispara, no document:
       new CustomEvent("reconecta:evento", { detail: { id, tipo, criado_em, dados, privado } })
     privado = true quando o evento foi destinado ao usuário logado (também aparece no sino).
     window.ReConecta.tempoReal = { estado: "sse" | "consulta" | "parado", ultimoId, silenciar(ms) }
       silenciar(ms): a página chama antes de uma ação do próprio usuário (reservar, doar…) para não
       mostrar o aviso público do que ele mesmo acabou de fazer; o evento continua sendo disparado
       e os avisos destinados a ele continuam aparecendo.
     window.ReConecta.descreverEvento(evento, privado) → { texto, href } ou null
     As páginas só escutam "reconecta:evento" e recarregam o trecho afetado. */
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
  var api = window.ReConecta = window.ReConecta || {};

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
        montarSino(),
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
        el("p", { texto: "Plataforma que conecta, em tempo real, quem tem alimento sobrando a ONGs e organizações que precisam." })
      ]),
      el("div", { classe: "rodape__colunas" }, [
        coluna("Plataforma", [["Início", "/"], ["Doações disponíveis", "/#doacoes"], ["Excedentes de hoje", "/#excedentes"], ["Como funciona", "/#como-funciona"], ["Dashboard", "/dashboard"], ["Sobre", "/sobre"]]),
        coluna("Participe", [["Cadastrar", "/cadastro"], ["Entrar", "/entrar"], ["Painel", "/painel"], ["Privacidade", "/privacidade"], ["Documentação da API", "/swagger"]])
      ]),
      el("div", { classe: "rodape__base" }, [
        el("span", { texto: "ReConecta · Projeto acadêmico de Computational Thinking with Python" }),
        el("span", { texto: "Alimento bom não é desperdício." })
      ])
    );
  }

  /* ---------- tempo real: textos dos eventos ---------- */

  var PLURAL_UN = { unidade: "unidades", pacote: "pacotes", caixa: "caixas" };
  function quantidadeTexto(q, unidade) {
    var n = Number(q);
    if (!isFinite(n)) return "";
    var u = unidade || "";
    if (PLURAL_UN[u] && n !== 1) u = PLURAL_UN[u];
    return (n.toLocaleString("pt-BR", { maximumFractionDigits: 2 }) + " " + u).trim();
  }

  function ateQuando(iso) {
    var d = dataBrasilia(iso);
    if (!d) return "";
    var hora = d.toLocaleTimeString("pt-BR", { timeZone: FUSO, hour: "2-digit", minute: "2-digit" });
    if (diaISO(d) === diaISO(new Date())) return "hoje às " + hora;
    return d.toLocaleDateString("pt-BR", { timeZone: FUSO, day: "2-digit", month: "2-digit" }) + " às " + hora;
  }

  function localTitulo(municipioUf) {
    var partes = String(municipioUf || "").split("/");
    if (!partes[0]) return "";
    return nomeTitulo(partes[0]) + (partes[1] ? "/" + partes[1].toUpperCase() : "");
  }

  /* Frase curta e destino de cada evento. privado = destinado ao usuário logado. */
  function descreverEvento(evento, privado) {
    var d = (evento && evento.dados) || {};
    var org = nomeTitulo(d.organizacao || "");
    var cats = Array.isArray(d.categorias) ? d.categorias.join(", ") : "";
    var pedido = d.pedido_id ? "/doacoes/" + d.pedido_id : "/#doacoes";
    var excedente = d.excedente_id ? "/excedentes/" + d.excedente_id : "/#excedentes";
    var qtd = quantidadeTexto(d.quantidade, d.unidade_medida);
    var ate = ateQuando(d.retirar_ate);
    switch (evento && evento.tipo) {
      case "pedido.publicado":
        return { href: pedido, texto: "Novo pedido" + (org ? " de " + org : "") +
          (d.municipio_uf ? " em " + localTitulo(d.municipio_uf) : "") + (cats ? ": " + cats : "") + "." };
      case "doacao.aceita":
        return privado
          ? { href: "/painel", texto: "Seu pedido recebeu uma doação" + (qtd ? ": " + qtd + " de " + d.item : "") + "." }
          : { href: pedido, texto: "Doação aceita agora" + (qtd ? ": " + qtd + " de " + d.item : "") + "." };
      case "doacao.entregue":
        return privado
          ? { href: "/painel", texto: "A organização confirmou que recebeu a sua doação" + (d.item ? " de " + d.item : "") + ". Obrigado!" }
          : { href: pedido, texto: "Doação entregue e confirmada" + (d.item ? ": " + d.item : "") + "." };
      case "doacao.nao_recebida":
        return { href: "/painel", texto: "A organização informou que não recebeu a sua doação" + (d.item ? " de " + d.item : "") + "." };
      case "excedente.publicado":
        return privado
          ? { href: excedente, texto: (org || "Uma empresa") + " publicou um excedente que combina com um pedido seu" +
              (cats ? ": " + cats : "") + "." + (ate ? " Retirar até " + ate + "." : "") }
          : { href: excedente, texto: "Novo excedente" + (org ? " de " + org : "") + (cats ? ": " + cats : "") + "." +
              (ate ? " Retirar até " + ate + "." : "") };
      case "excedente.reservado":
        return privado
          ? { href: excedente, texto: (d.ong ? nomeTitulo(d.ong) : "Uma ONG") + " reservou o seu excedente." }
          : { href: excedente, texto: "Um excedente acabou de ser reservado por uma ONG." };
      case "excedente.reserva_cancelada":
        return privado
          ? { href: excedente, texto: "A reserva de um excedente foi cancelada." }
          : { href: excedente, texto: "Um excedente voltou a ficar disponível." };
      case "excedente.retirado":
        return privado
          ? { href: excedente, texto: "A retirada do excedente foi confirmada." }
          : { href: excedente, texto: "Um excedente foi retirado: alimento aproveitado." };
      case "excedente.cancelado":
        return privado ? { href: "/painel", texto: "Um excedente seu foi cancelado." } : null;
      default:
        return null;
    }
  }

  function haQuantoTempo(iso) {
    var d = dataBrasilia(iso);
    if (!d) return "";
    var min = Math.floor((Date.now() - d.getTime()) / 60000);
    if (min < 1) return "agora";
    if (min < 60) return "há " + min + " min";
    if (min < 24 * 60) return "há " + Math.floor(min / 60) + " h";
    return d.toLocaleDateString("pt-BR", { timeZone: FUSO, day: "2-digit", month: "2-digit" }) + " às " +
      d.toLocaleTimeString("pt-BR", { timeZone: FUSO, hour: "2-digit", minute: "2-digit" });
  }

  /* ---------- sino de notificações (só com sessão) ---------- */

  var SINO_SVG =
    '<svg viewBox="0 0 24 24" aria-hidden="true" focusable="false" width="20" height="20">' +
    '<path d="M6.5 10a5.5 5.5 0 0 1 11 0c0 4.2 1.6 5.6 2 6.5H4.500c.4-.9 2-2.300 2-6.500z" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linejoin="round"/>' +
    '<path d="M10 19.200a2.100 2.100 0 0 0 4 0" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"/></svg>';

  var sino = null;                 // { raiz, botao, conta, painel, lista, vazio, marcar }
  var notificacoes = [];
  var idsPrivados = {};

  function montarSino() {
    if (sino) return sino.raiz;
    var botao = el("button", { type: "button", classe: "sino__botao", "aria-expanded": "false",
      "aria-controls": "rc-sino-painel", "aria-label": "Notificações", html: SINO_SVG });
    var conta = el("span", { classe: "sino__conta", "aria-hidden": "true", hidden: "" });
    botao.appendChild(conta);
    var marcar = el("button", { type: "button", classe: "sino__marcar", texto: "Marcar como lidas", hidden: "" });
    var lista = el("ul", { classe: "sino__lista" });
    var vazio = el("p", { classe: "sino__vazio", texto: "Nenhuma notificação por enquanto." });
    var painel = el("div", { classe: "sino__painel", id: "rc-sino-painel", role: "region",
      "aria-label": "Notificações", hidden: "" }, [
      el("div", { classe: "sino__topo" }, [el("h2", { texto: "Notificações" }), marcar]),
      lista, vazio
    ]);
    var raiz = el("div", { classe: "sino" }, [botao, painel]);
    sino = { raiz: raiz, botao: botao, conta: conta, painel: painel, lista: lista, vazio: vazio, marcar: marcar };

    function fechar(devolverFoco) {
      if (painel.hidden) return;
      painel.hidden = true;
      botao.setAttribute("aria-expanded", "false");
      if (devolverFoco) botao.focus();
    }
    botao.addEventListener("click", function () {
      if (!painel.hidden) { fechar(false); return; }
      painel.hidden = false;
      botao.setAttribute("aria-expanded", "true");
      carregarNotificacoes();
    });
    document.addEventListener("keydown", function (e) { if (e.key === "Escape") fechar(painel.contains(document.activeElement)); });
    document.addEventListener("click", function (e) { if (!raiz.contains(e.target)) fechar(false); });
    marcar.addEventListener("click", function () {
      var maior = notificacoes.reduce(function (m, n) { return Math.max(m, n.id); }, 0);
      if (!maior) return;
      marcar.disabled = true;
      fetch("/reconecta/notificacoes/lidas", {
        method: "POST", credentials: "same-origin",
        headers: { "Content-Type": "application/json", "Accept": "application/json" },
        body: JSON.stringify({ ate_id: maior })
      }).catch(function () {}).then(carregarNotificacoes).then(function () { marcar.disabled = false; botao.focus(); });
    });
    return raiz;
  }

  function desenharSino() {
    if (!sino) return;
    var novas = notificacoes.filter(function (n) { return !n.lida; }).length;
    sino.conta.hidden = novas === 0;
    sino.conta.textContent = novas > 9 ? "9+" : String(novas);
    sino.botao.setAttribute("aria-label", novas === 0 ? "Notificações"
      : "Notificações, " + novas + (novas === 1 ? " não lida" : " não lidas"));
    sino.marcar.hidden = novas === 0;
    sino.vazio.hidden = notificacoes.length > 0;
    sino.lista.replaceChildren.apply(sino.lista, notificacoes.map(function (n) {
      var d = descreverEvento(n, true) || { texto: "Atualização na sua conta.", href: "/painel" };
      return el("li", { classe: "sino__item" + (n.lida ? "" : " is-nova") }, [
        el("a", { href: d.href }, [
          el("span", { classe: "sino__texto", texto: d.texto }),
          el("span", { classe: "sino__quando" }, [n.lida ? "" : el("span", { classe: "sr-only", texto: "Não lida. " }), haQuantoTempo(n.criado_em)])
        ])
      ]);
    }));
  }

  /* Nunca rejeita: sem sessão ou sem rede, a lista fica como estava. */
  function carregarNotificacoes() {
    return fetch("/reconecta/notificacoes", { credentials: "same-origin", headers: { "Accept": "application/json" } })
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (corpo) {
        if (!corpo || !Array.isArray(corpo.notificacoes)) return;
        notificacoes = corpo.notificacoes;
        notificacoes.forEach(function (n) { idsPrivados[n.id] = true; });
        desenharSino();
      })
      .catch(function () {});
  }

  /* ---------- avisos discretos (eventos ao vivo) ---------- */

  var avisos = null;
  function mostrarAviso(descricao, privado) {
    if (!descricao || !document.body) return;
    if (!avisos) {
      avisos = el("div", { classe: "avisos-vivo", role: "status", "aria-live": "polite", "aria-label": "Novidades ao vivo" });
      document.body.appendChild(avisos);
    }
    while (avisos.children.length >= 3) avisos.removeChild(avisos.firstChild);
    var fechar = el("button", { type: "button", classe: "aviso-vivo__fechar", "aria-label": "Dispensar aviso", texto: "×" });
    var aviso = el("div", { classe: "aviso-vivo" + (privado ? " aviso-vivo--meu" : "") }, [
      el("span", { classe: "aviso-vivo__ponto", "aria-hidden": "true" }),
      el("a", { href: descricao.href, classe: "aviso-vivo__texto", texto: descricao.texto }),
      fechar
    ]);
    function remover() { if (aviso.parentNode) aviso.parentNode.removeChild(aviso); }
    fechar.addEventListener("click", remover);
    var relogio = setTimeout(remover, 8000);
    // quem está lendo (mouse ou teclado em cima) não perde o aviso
    aviso.addEventListener("mouseenter", function () { clearTimeout(relogio); });
    aviso.addEventListener("focusin", function () { clearTimeout(relogio); });
    aviso.addEventListener("mouseleave", function () { relogio = setTimeout(remover, 4000); });
    avisos.appendChild(aviso);
  }

  /* ---------- tempo real: conexão e barramento ---------- */

  var INTERVALO_CONSULTA = 10000;
  var RETORNO_SSE = 60000;
  var tr = api.tempoReal = { estado: "parado", ultimoId: 0 };
  var semAvisosAte = 0;
  tr.silenciar = function (ms) { semAvisosAte = Date.now() + (Number(ms) > 0 ? Number(ms) : 6000); };
  api.descreverEvento = descreverEvento;

  var fonte = null, relogioConsulta = null, relogioRetorno = null, relogioFila = null;
  var cursor = null;               // id do último evento visto; null = ainda não sabemos
  var chaveSessao;                 // "empresa:3", "doador:7" ou "" (sem sessão)
  var logado = false, falhas = 0, fila = [], meuNome = "";

  function definirEstado(estado) {
    tr.estado = estado;
    document.documentElement.setAttribute("data-tempo-real", estado);
  }

  function pararConexoes() {
    if (fonte) { fonte.close(); fonte = null; }
    clearInterval(relogioConsulta); relogioConsulta = null;
    clearTimeout(relogioRetorno); relogioRetorno = null;
  }

  function despachar(lote) {
    var chaves = {};
    lote.forEach(function (ev) { ev.privado = !!idsPrivados[ev.id]; });
    // o mesmo fato chega em duas linhas (pública e minha): avisa só a minha
    lote.forEach(function (ev) {
      if (ev.privado) chaves[ev.tipo + "|" + (ev.dados.pedido_id || "") + "|" + (ev.dados.excedente_id || "")] = true;
    });
    lote.forEach(function (ev) {
      document.dispatchEvent(new CustomEvent("reconecta:evento", {
        detail: { id: ev.id, tipo: ev.tipo, criado_em: ev.criado_em, dados: ev.dados, privado: ev.privado }
      }));
    });
    var calado = Date.now() < semAvisosAte;   // a própria pessoa acabou de agir: a tela dela já mostra o resultado
    lote.slice(-3).forEach(function (ev) {
      if (calado && !ev.privado) return;
      var repetido = !ev.privado && chaves[ev.tipo + "|" + (ev.dados.pedido_id || "") + "|" + (ev.dados.excedente_id || "")];
      // o que a própria organização acabou de publicar não precisa de aviso para ela mesma
      var meu = !ev.privado && meuNome && ev.dados.organizacao === meuNome;
      if (!repetido && !meu) mostrarAviso(descreverEvento(ev, ev.privado), ev.privado);
    });
  }

  function esvaziarFila() {
    relogioFila = null;
    var lote = fila.splice(0);
    if (!lote.length) return;
    if (logado) carregarNotificacoes().then(function () { despachar(lote); });
    else despachar(lote);
  }

  function receber(evento) {
    if (!evento || typeof evento.id !== "number" || (cursor != null && evento.id <= cursor)) return;
    cursor = tr.ultimoId = evento.id;
    fila.push({ id: evento.id, tipo: String(evento.tipo || ""), criado_em: evento.criado_em || null,
      dados: evento.dados && typeof evento.dados === "object" ? evento.dados : {} });
    // junta o que chegou no mesmo instante (a linha pública e a destinada a mim)
    if (!relogioFila) relogioFila = setTimeout(esvaziarFila, 200);
  }

  function consultarNovidades() {
    return fetch("/reconecta/novidades" + (cursor == null ? "" : "?desde=" + cursor), {
      credentials: "same-origin", headers: { "Accept": "application/json" }
    }).then(function (r) { return r.ok ? r.json() : null; }).then(function (corpo) {
      if (!corpo) return false;
      if (cursor == null) { cursor = tr.ultimoId = Number(corpo.ultimo_id) || 0; return true; }
      (corpo.eventos || []).forEach(receber);
      return true;
    }).catch(function () { return false; });
  }

  function cairParaConsulta() {
    if (fonte) { fonte.close(); fonte = null; }
    definirEstado("consulta");
    if (!relogioConsulta) relogioConsulta = setInterval(consultarNovidades, INTERVALO_CONSULTA);
    clearTimeout(relogioRetorno);
    relogioRetorno = setTimeout(function () { if (!document.hidden) abrirFluxo(); }, RETORNO_SSE);
  }

  function abrirFluxo() {
    if (fonte) { fonte.close(); fonte = null; }
    if (typeof window.EventSource !== "function") { cairParaConsulta(); return; }
    falhas = 0;
    var esta = fonte = new EventSource("/reconecta/tempo-real?desde=" + (cursor || 0));
    function ligado() {
      if (fonte !== esta || esta.readyState === 2) return;
      falhas = 0;
      clearInterval(relogioConsulta); relogioConsulta = null;
      clearTimeout(relogioRetorno); relogioRetorno = null;
      definirEstado("sse");
    }
    esta.onopen = ligado;
    // O servidor só manda os cabeçalhos junto com o primeiro evento ou batimento (até 15 s).
    // Recusa (503) e queda de rede disparam onerror na hora; sem erro em 1,5 s, o fluxo está aberto.
    setTimeout(function () { if (falhas === 0) ligado(); }, 1500);
    esta.onmessage = function (e) {
      if (fonte !== esta) return;
      try { receber(JSON.parse(e.data)); } catch (erro) { /* linha inválida: ignora */ }
    };
    esta.onerror = function () {
      if (fonte !== esta) return;
      falhas += 1;
      // 503 (lotado) ou resposta que não é fluxo fecha de vez; três quedas seguidas também desistem
      if (esta.readyState === 2 || falhas >= 3) cairParaConsulta();
    };
  }

  function ligarTempoReal() {
    pararConexoes();
    if (document.hidden) { definirEstado("parado"); return; }
    // primeira carga: só o último id, para não reapresentar o que já passou
    (cursor == null ? consultarNovidades() : Promise.resolve(true)).then(function (ok) {
      if (document.hidden || fonte || relogioConsulta) return;
      if (!ok && cursor == null) { cairParaConsulta(); return; }
      abrirFluxo();
    });
  }

  function iniciarTempoReal(usuario) {
    var chave = usuario ? usuario.tipo + ":" + usuario.id : "";
    if (chave === chaveSessao) return;      // mesma sessão: a conexão continua
    chaveSessao = chave;
    logado = !!usuario;
    meuNome = usuario && usuario.tipo === "empresa" ? String(usuario.nome || "") : "";
    notificacoes = []; idsPrivados = {};
    if (logado) carregarNotificacoes(); else desenharSino();
    ligarTempoReal();                       // o fluxo depende do cookie: reabre quando a sessão muda
  }

  // aba em segundo plano não ocupa uma das conexões do servidor; ao voltar, retoma do último id
  document.addEventListener("visibilitychange", function () {
    if (chaveSessao === undefined) return;
    if (document.hidden) { pararConexoes(); definirEstado("parado"); }
    else ligarTempoReal();
  });
  window.addEventListener("pagehide", pararConexoes);

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
        iniciarTempoReal(usuario);
        return usuario;
      });
  }

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
