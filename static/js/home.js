/* ReConecta — Home (rodada 16): topo curto e o bloco "Agora na rede" com três abas:
   Pedidos das ONGs (a ONG diz o que precisa), Alimentos doados (alguém oferece e uma ONG
   retira) e ONGs na rede. A faixa de categorias filtra as abas. Tudo se atualiza sozinho
   com os eventos que o layout.js dispara em "reconecta:evento". O assistente
   "Tenho alimento para doar" continua o mesmo. */
(function () {
  "use strict";

  var API = "/reconecta/publico";

  /* categoria → slug da foto real (static/img/categorias/<slug>.webp); enquanto a foto
     não existe, cai na imagem antiga da categoria */
  var CATEGORIAS = [
    ["Hortifrúti", "hortifruti", "hortifruti"],
    ["Padaria", "padaria", "padaria"],
    ["Laticínios", "laticinios", "laticinios"],
    ["Carnes e peixes", "carnes-peixes", "carnes"],
    ["Grãos e cereais", "graos-cereais", "graos"],
    ["Refeições prontas", "refeicoes-prontas", "refeicoes"],
    ["Bebidas não alcoólicas", "bebidas", "bebidas"],
    ["Outros", "outros", "outros"]
  ];
  var FOTO = {}, RESERVA = {};
  CATEGORIAS.forEach(function (c) { FOTO[c[0]] = c[1]; RESERVA[c[0]] = c[2]; });

  function $(id) { return document.getElementById(id); }

  function el(tag, attrs, filhos) {
    var no = document.createElement(tag);
    Object.keys(attrs || {}).forEach(function (k) {
      if (k === "texto") no.textContent = attrs[k];
      else if (k === "classe") no.className = attrs[k];
      else no.setAttribute(k, attrs[k]);
    });
    (filhos || []).forEach(function (f) {
      if (f == null || f === "") return;
      no.appendChild(typeof f === "string" ? document.createTextNode(f) : f);
    });
    return no;
  }

  function obterJSON(url) {
    return fetch(url, { headers: { "Accept": "application/json" }, credentials: "same-origin" })
      .then(function (r) {
        if (!r.ok) { var e = new Error("HTTP " + r.status); e.status = r.status; throw e; }
        var total = Number(r.headers.get("X-Total-Count"));
        return r.json().then(function (corpo) { return { corpo: corpo, total: isFinite(total) ? total : null }; });
      });
  }

  /* ---------- formatação ---------- */

  var numero = new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 1 });
  var inteiro = new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 0 });

  var PLURAL = { unidade: "unidades", pacote: "pacotes", caixa: "caixas" };
  function quantidade(item) {
    var q = Number(item.quantidade);
    var u = item.unidade_medida || "";
    if (PLURAL[u] && q !== 1) u = PLURAL[u];
    return numero.format(q) + " " + u;
  }

  function titulo(nome) {
    var R = window.ReConecta;
    return R && R.nomeTitulo ? R.nomeTitulo(nome) : String(nome || "").trim();
  }

  function local(municipioUf) {
    if (!municipioUf) return "";
    var partes = String(municipioUf).split("/");
    return titulo(partes[0]) + (partes[1] ? "/" + partes[1].toUpperCase() : "");
  }

  function data(valor) { return window.ReConecta.dataBrasilia(valor); }

  function diasAte(valor) {
    var d = data(valor);
    if (!d) return null;
    var hoje = window.ReConecta.diaISO(new Date());
    return Math.round((Date.parse(window.ReConecta.diaISO(d) + "T00:00:00Z") - Date.parse(hoje + "T00:00:00Z")) / 86400000);
  }

  function prazo(valor) {
    var d = data(valor);
    if (!d) return "";
    var dif = diasAte(valor);
    var hora = d.toLocaleTimeString("pt-BR", { timeZone: window.ReConecta.fuso, hour: "2-digit", minute: "2-digit" });
    var quando;
    if (dif === 0) quando = "hoje";
    else if (dif === 1) quando = "amanhã";
    else if (dif > 1 && dif < 7) quando = d.toLocaleDateString("pt-BR", { timeZone: window.ReConecta.fuso, weekday: "long" }).replace("-feira", "");
    else quando = d.toLocaleDateString("pt-BR", { timeZone: window.ReConecta.fuso, day: "2-digit", month: "2-digit" });
    return quando + ", " + hora;
  }

  function vence(iso) {
    var dif = diasAte(iso + "T12:00:00");
    if (dif === null) return "";
    if (dif <= 0) return "vence hoje";
    if (dif === 1) return "vence amanhã";
    if (dif < 30) return "vence em " + dif + " dias";
    return "vence " + iso.split("-").reverse().slice(0, 2).join("/");
  }

  /* Fotos reais por categoria (static/img/categorias/<slug>.webp, frente de fotos da
     rodada 16). Enquanto elas não estão no repositório, usa a imagem antiga da categoria;
     se uma foto faltar depois de ligada, cai na antiga sem quebrar o cartão. */
  var FOTOS_REAIS = true;
  function fotoCategoria(categoria, classe) {
    var nome = FOTO[categoria] ? categoria : "Outros";
    var antiga = "/static/img/doacoes/cat-" + RESERVA[nome] + ".webp";
    var img = el("img", { classe: classe, src: FOTOS_REAIS ? "/static/img/categorias/" + FOTO[nome] + ".webp" : antiga, alt: "",
                          width: "640", height: "480", loading: "lazy", decoding: "async" });
    if (FOTOS_REAIS) img.addEventListener("error", function trocar() { img.removeEventListener("error", trocar); img.src = antiga; });
    return img;
  }

  /* ---------- perfil de quem vê ---------- */

  var usuarioAtual = null;
  function perfis() { return (usuarioAtual && usuarioAtual.perfis) || []; }
  function ehOng() { return !!(usuarioAtual && usuarioAtual.tipo === "empresa" && perfis().indexOf("ong") !== -1); }
  function ehEmpresaAlimentos() { return !!(usuarioAtual && usuarioAtual.tipo === "empresa" && perfis().indexOf("empresa_alimentos") !== -1); }
  function podePublicar() { return !!(usuarioAtual && (usuarioAtual.tipo === "doador" || ehEmpresaAlimentos())); }

  /* ---------- estado do bloco "Agora na rede" ---------- */

  var estado = {
    aba: "pedidos", categoria: "", organizacao: "",
    pedidos: null, doados: null, meus: [], ongs: null,
    erro: {}
  };
  var MAX_CARTOES = 8;
  var mostrarTodos = false;

  var EXPLICA = {
    pedidos: "O que as ONGs pediram e ainda falta. Escolha um pedido e doe.",
    doados: "Alimentos oferecidos por empresas e pessoas. Uma ONG reserva e retira.",
    ongs: "As organizações da rede e quantos pedidos cada uma tem abertos."
  };

  /* ---------- cartões ---------- */

  function botao(texto, href, classe) {
    return el("a", { classe: "btn btn--pequeno " + (classe || "btn--primario"), href: href }, [texto]);
  }

  function cartaoPedido(d) {
    var e = d.empresa || {};
    var itens = d.itens || [];
    var abertos = itens.filter(function (i) { return Number(i.faltam) > 0; });
    var mostrar = (abertos.length ? abertos : itens).slice(0, 3);
    var principal = (mostrar[0] || itens[0] || {}).categoria;
    return el("li", { classe: "cartao-rede cartao-rede--pedido" }, [
      fotoCategoria(principal, "cartao-rede__foto"),
      el("div", { classe: "cartao-rede__corpo" }, [
        el("p", { classe: "cartao-rede__tipo", texto: "Pedido" }),
        el("h3", { classe: "cartao-rede__titulo", texto: titulo(e.nome) }),
        el("p", { classe: "cartao-rede__local", texto: local(e.municipio_uf) }),
        el("ul", { classe: "cartao-rede__itens", "aria-label": "Itens que faltam" }, mostrar.map(function (i) {
          var falta = Number(i.faltam);
          return el("li", null, [el("span", { texto: i.nome }), el("strong", { texto: falta > 0 ? "faltam " + quantidade({ quantidade: falta, unidade_medida: i.unidade_medida }) : "completo" })]);
        })),
        itens.length > mostrar.length ? el("p", { classe: "cartao-rede__mais", texto: "+ " + (itens.length - mostrar.length) + " itens" }) : null,
        el("p", { classe: "cartao-rede__prazo" }, ["Receber até ", el("strong", { texto: prazo(d.receber_ate || d.data_limite_retirada) })])
      ]),
      el("div", { classe: "cartao-rede__acao" }, [
        botao("Doar", "/doacoes/" + d.id)
      ])
    ]);
  }

  var ESTADO_DOADO = {
    DISPONIVEL: ["Aguardando uma ONG retirar", "estado--espera"],
    RESERVADO: ["Reservado", "estado--reservado"],
    RETIRADO: ["Retirado", "estado--ok"],
    CANCELADO: ["Cancelado", "estado--fim"],
    EXPIRADO: ["Prazo encerrado", "estado--fim"]
  };

  function cartaoDoado(x) {
    var e = x.empresa || {};
    var itens = x.itens || [];
    var i0 = itens[0] || {};
    var meu = x.meu === true;
    var st = ESTADO_DOADO[x.status] || [x.status, ""];
    var textoEstado = x.status === "RESERVADO" && x.reservado_por && x.reservado_por.nome
      ? "Reservado por " + titulo(x.reservado_por.nome) : st[0];
    var quem = e.pessoa_fisica ? "Pessoa física" : titulo(e.nome);
    var acao;
    if (meu) acao = botao("Ver sua doação", "/excedentes/" + x.id, "btn--secundario");
    else if (ehOng() && x.status === "DISPONIVEL") acao = botao("Reservar", "/excedentes/" + x.id);
    else acao = botao("Ver detalhes", "/excedentes/" + x.id, "btn--secundario");
    return el("li", { classe: "cartao-rede cartao-rede--doado" + (meu ? " cartao-rede--meu" : "") }, [
      fotoCategoria(i0.categoria, "cartao-rede__foto"),
      meu ? el("p", { classe: "cartao-rede__selo", texto: "Sua doação" }) : null,
      el("div", { classe: "cartao-rede__corpo" }, [
        el("p", { classe: "cartao-rede__tipo", texto: "Alimento doado" }),
        el("h3", { classe: "cartao-rede__titulo cartao-rede__titulo--grande" }, [
          quantidade(i0) + " de " + (i0.nome || "alimento"),
          itens.length > 1 ? el("span", { classe: "cartao-rede__mais", texto: " + " + (itens.length - 1) }) : null]),
        el("p", { classe: "cartao-rede__local", texto: "Doado por " + quem + (e.municipio_uf ? " · " + local(e.municipio_uf) : "") }),
        el("p", { classe: "cartao-rede__prazo" }, [
          i0.validade ? el("span", { texto: vence(i0.validade) }) : null,
          i0.validade ? " · " : null,
          "retirar até ", el("strong", { texto: prazo(x.retirar_ate) })]),
        el("p", { classe: "estado " + st[1], texto: textoEstado })
      ]),
      el("div", { classe: "cartao-rede__acao" }, [acao])
    ]);
  }

  function iniciais(nome) {
    var partes = titulo(nome).split(/\s+/).filter(function (p) { return p.length > 2; });
    return ((partes[0] || nome || "?").charAt(0) + (partes[1] ? partes[1].charAt(0) : "")).toUpperCase();
  }

  function cartaoOng(o) {
    var n = Number(o.pedidos_abertos) || 0;
    return el("li", { classe: "cartao-rede cartao-rede--ong" }, [
      el("span", { classe: "cartao-rede__avatar", "aria-hidden": "true", texto: iniciais(o.nome) }),
      el("div", { classe: "cartao-rede__corpo" }, [
        el("p", { classe: "cartao-rede__tipo", texto: "ONG" }),
        el("h3", { classe: "cartao-rede__titulo", texto: titulo(o.nome) }),
        el("p", { classe: "cartao-rede__local", texto: local(o.municipio_uf) }),
        el("p", { classe: "estado " + (n ? "estado--ok" : "estado--fim"),
                  texto: n ? (n === 1 ? "1 pedido aberto" : n + " pedidos abertos") : "Ainda não publicou pedido" })
      ]),
      n ? el("div", { classe: "cartao-rede__acao" }, [(function () {
        var b = el("button", { type: "button", classe: "btn btn--secundario btn--pequeno", texto: "Ver pedidos" });
        b.addEventListener("click", function () { estado.organizacao = o.nome; estado.categoria = ""; trocarAba("pedidos", true); });
        return b;
      })()]) : null
    ]);
  }

  /* ---------- estado vazio: duas linhas e uma ação certa por perfil ---------- */

  function acaoVazio(aba) {
    if (aba === "ongs") return usuarioAtual ? null : botao("Cadastrar ONG", "/cadastro", "btn--secundario");
    if (ehOng()) return aba === "pedidos" ? botao("Publicar o primeiro pedido", "/painel#publicar")
                                          : botao("Ver pedidos das ONGs", "#doacoes", "btn--secundario");
    if (podePublicar()) return botao("Doar o que sobrou", "/painel#publicar-excedente");
    var b = el("button", { type: "button", classe: "btn btn--primario btn--pequeno", texto: "Tenho alimento para doar" });
    b.addEventListener("click", function () { abrirAssistente(); });
    return b;
  }

  function vazio(aba) {
    var cat = estado.categoria;
    var linhas = {
      pedidos: estado.organizacao ? ["Esta ONG não tem pedido aberto agora.", "Veja os pedidos das outras ONGs."]
        : cat ? ["Nenhum pedido de " + cat.toLowerCase() + " agora.", "Veja todas as categorias ou doe o que sobrou."]
        : ehOng() ? ["Sua ONG ainda não tem pedido aberto.", "Publique o que falta e quem tem alimento é avisado na hora."]
        : ["Nenhuma ONG pediu alimentos agora.", "Cadastrar uma ONG não cria pedido: ele aparece aqui quando a ONG publica o que falta."],
      doados: cat ? ["Nenhum alimento de " + cat.toLowerCase() + " doado agora.", "Veja todas as categorias."]
        : ["Nenhum alimento doado aguardando retirada.", "Quando alguém doar o que sobrou, aparece aqui na hora."],
      ongs: ["Nenhuma ONG na rede ainda.", "As ONGs aparecem aqui assim que se cadastram."]
    }[aba];
    var acoes = [];
    if (cat || estado.organizacao) {
      var limpar = el("button", { type: "button", classe: "btn btn--secundario btn--pequeno", texto: "Ver todas" });
      limpar.addEventListener("click", function () { estado.categoria = ""; estado.organizacao = ""; desenhar(); });
      acoes.push(limpar);
    }
    var a = acaoVazio(aba);
    if (a) acoes.push(a);
    return el("div", { classe: "rede__vazio" }, [
      el("p", { classe: "rede__vazio-titulo", texto: linhas[0] }),
      el("p", { texto: linhas[1] }),
      acoes.length ? el("div", { classe: "rede__vazio-acoes" }, acoes) : null
    ]);
  }

  /* ---------- filtro por categoria (fotos) ---------- */

  function montarFiltro() {
    var alvo = $("filtro");
    var opcoes = [["", "Todas"]].concat(CATEGORIAS.map(function (c) { return [c[0], c[0]]; }));
    alvo.replaceChildren.apply(alvo, opcoes.map(function (o) {
      var b = el("button", { type: "button", classe: "filtro__chip", "data-categoria": o[0], "aria-pressed": String(estado.categoria === o[0]) }, [
        o[0] ? fotoCategoria(o[0], "filtro__foto") : el("span", { classe: "filtro__todas", "aria-hidden": "true", texto: "✓" }),
        el("span", { texto: o[1] === "Bebidas não alcoólicas" ? "Bebidas" : o[1] })
      ]);
      b.addEventListener("click", function () {
        estado.categoria = estado.categoria === o[0] ? "" : o[0];
        estado.organizacao = "";
        mostrarTodos = false;
        desenhar();
      });
      return b;
    }));
  }

  function temCategoria(itens) {
    return !estado.categoria || (itens || []).some(function (i) { return i.categoria === estado.categoria; });
  }

  /* ---------- desenho ---------- */

  function listaDaAba() {
    if (estado.aba === "pedidos") {
      return (estado.pedidos || []).filter(function (d) {
        return temCategoria(d.itens) && (!estado.organizacao || (d.empresa || {}).nome === estado.organizacao);
      });
    }
    if (estado.aba === "doados") {
      // as doações de quem está vendo vêm primeiro, com o estado delas (reservada, retirada)
      var vistos = {};
      var meus = estado.meus.filter(function (x) { return x.status === "DISPONIVEL" || x.status === "RESERVADO" || x.status === "RETIRADO"; });
      var todos = meus.concat(estado.doados || []).filter(function (x) {
        if (vistos[x.id]) return false;
        vistos[x.id] = true;
        return true;
      });
      return todos.filter(function (x) { return temCategoria(x.itens); });
    }
    return estado.ongs || [];
  }

  function contar() {
    var n = {
      pedidos: estado.pedidos ? estado.pedidos.length : null,
      doados: estado.doados ? listaDaAbaDoados().length : null,
      ongs: estado.ongs ? estado.ongs.length : null
    };
    Object.keys(n).forEach(function (k) {
      var no = document.querySelector('[data-conta="' + k + '"]');
      if (no) no.textContent = n[k] == null ? "" : String(n[k]);
    });
    var resumo = $("resumo");
    resumo.querySelector('[data-resumo="pedidos"]').textContent = n.pedidos == null ? "—" : inteiro.format(n.pedidos);
    resumo.querySelector('[data-resumo="doados"]').textContent = estado.doados ? inteiro.format(estado.doados.length) : "—";
    resumo.querySelector('[data-resumo="ongs"]').textContent = n.ongs == null ? "—" : inteiro.format(n.ongs);
    resumo.setAttribute("aria-busy", "false");
  }
  function listaDaAbaDoados() {
    var aba = estado.aba, cat = estado.categoria;
    estado.aba = "doados"; estado.categoria = "";
    var l = listaDaAba();
    estado.aba = aba; estado.categoria = cat;
    return l;
  }

  function desenhar() {
    contar();
    var aba = estado.aba;
    $("filtro").hidden = aba === "ongs";
    $("filtro").querySelectorAll(".filtro__chip").forEach(function (b) {
      b.setAttribute("aria-pressed", String(b.getAttribute("data-categoria") === estado.categoria));
    });
    $("rede-explica").textContent = estado.organizacao && aba === "pedidos"
      ? "Pedidos de " + titulo(estado.organizacao) + "." : EXPLICA[aba];
    var alvo = $("rede-conteudo");
    var dados = { pedidos: estado.pedidos, doados: estado.doados, ongs: estado.ongs }[aba];
    if (dados === null && !estado.erro[aba]) return;   // ainda carregando: fica o esqueleto
    if (estado.erro[aba]) {
      var tentar = el("button", { type: "button", classe: "btn btn--secundario btn--pequeno", texto: "Tentar de novo" });
      tentar.addEventListener("click", function () { carregarTudo(false); });
      alvo.replaceChildren(el("div", { classe: "rede__vazio", role: "alert" }, [
        el("p", { classe: "rede__vazio-titulo", texto: "Não conseguimos carregar agora." }), tentar]));
      alvo.setAttribute("aria-busy", "false");
      return;
    }
    var lista = listaDaAba();
    if (!lista.length) {
      alvo.replaceChildren(vazio(aba));
    } else {
      var cartao = aba === "pedidos" ? cartaoPedido : aba === "doados" ? cartaoDoado : cartaoOng;
      var visiveis = mostrarTodos ? lista : lista.slice(0, MAX_CARTOES);
      var filhos = [el("ul", { classe: "grade", "aria-label": EXPLICA[aba] }, visiveis.map(cartao))];
      if (lista.length > visiveis.length) {
        var mais = el("button", { type: "button", classe: "btn btn--secundario btn--pequeno rede__mais", texto: "Ver mais " + (lista.length - visiveis.length) });
        mais.addEventListener("click", function () { mostrarTodos = true; desenhar(); });
        filhos.push(mais);
      }
      if (aba === "pedidos" && ehOng() && !estado.organizacao) {
        filhos.unshift(el("p", { classe: "rede__dica" }, ["Sua ONG precisa de algo? ", el("a", { href: "/painel#publicar", texto: "Publicar pedido" })]));
      }
      alvo.replaceChildren.apply(alvo, filhos);
    }
    alvo.setAttribute("aria-busy", "false");
  }

  /* ---------- abas ---------- */

  function trocarAba(aba, focar) {
    estado.aba = aba;
    mostrarTodos = false;
    if (aba !== "pedidos") estado.organizacao = "";
    document.querySelectorAll(".aba").forEach(function (b) {
      var sel = b.getAttribute("data-aba") === aba;
      b.setAttribute("aria-selected", String(sel));
      b.tabIndex = sel ? 0 : -1;
      if (sel) { $("rede-painel").setAttribute("aria-labelledby", b.id); if (focar) b.focus(); }
    });
    desenhar();
  }

  document.querySelectorAll(".aba").forEach(function (b, i, todas) {
    b.addEventListener("click", function () { estado.escolheu = true; trocarAba(b.getAttribute("data-aba")); });
    b.addEventListener("keydown", function (e) {
      var passo = e.key === "ArrowRight" ? 1 : e.key === "ArrowLeft" ? -1 : 0;
      if (!passo) return;
      e.preventDefault();
      trocarAba(todas[(i + passo + todas.length) % todas.length].getAttribute("data-aba"), true);
    });
  });

  // links antigos e do menu: /#doacoes, /#excedentes, /#ongs abrem a aba certa
  function abaDoEndereco() {
    var h = location.hash;
    if (h === "#excedentes") trocarAba("doados");
    else if (h === "#ongs") trocarAba("ongs");
    else if (h === "#doacoes") trocarAba("pedidos");
  }
  window.addEventListener("hashchange", abaDoEndereco);

  /* ---------- carga ---------- */

  function carregarPedidos() {
    return obterJSON(API + "/doacoes?limite=100").then(function (r) {
      estado.pedidos = Array.isArray(r.corpo) ? r.corpo : []; estado.erro.pedidos = false;
    }, function () { if (estado.pedidos === null) estado.erro.pedidos = true; });
  }
  function carregarDoados() {
    var publicos = obterJSON("/reconecta/excedentes?limite=100").then(function (r) {
      estado.doados = Array.isArray(r.corpo) ? r.corpo : []; estado.erro.doados = false;
    }, function () { if (estado.doados === null) estado.erro.doados = true; });
    // as doações de quem está logado, com o estado delas (o público só lista as disponíveis)
    var meus = usuarioAtual && podePublicar()
      ? obterJSON("/reconecta/excedentes/meus").then(function (r) { estado.meus = Array.isArray(r.corpo) ? r.corpo : []; }, function () {})
      : Promise.resolve(estado.meus = []);
    return Promise.all([publicos, meus]);
  }
  function carregarOngs() {
    return obterJSON(API + "/ongs").then(function (r) {
      var lista = Array.isArray(r.corpo) ? r.corpo : (r.corpo && r.corpo.ongs) || [];
      estado.ongs = lista; estado.erro.ongs = false;
    }, function () {
      // sem a rota (versão anterior do servidor): monta pelas ONGs que têm pedido aberto
      var mapa = {};
      (estado.pedidos || []).forEach(function (d) {
        var e = d.empresa || {};
        if (!e.nome) return;
        mapa[e.nome] = mapa[e.nome] || { nome: e.nome, municipio_uf: e.municipio_uf, pedidos_abertos: 0 };
        mapa[e.nome].pedidos_abertos += 1;
      });
      estado.ongs = Object.keys(mapa).map(function (k) { return mapa[k]; });
    });
  }
  function carregarTudo() {
    return carregarPedidos().then(function () { return Promise.all([carregarDoados(), carregarOngs()]); }).then(function () {
      // sem endereço de aba: sem pedido aberto, abre no que existe (alimentos doados ou ONGs)
      if (!/^#(doacoes|excedentes|ongs)$/.test(location.hash) && !estado.escolheu && estado.pedidos && !estado.pedidos.length) {
        if (listaDaAbaDoados().length) estado.aba = "doados";
        else if ((estado.ongs || []).length) estado.aba = "ongs";
        trocarAba(estado.aba);
        return;
      }
      desenhar();
    });
  }

  /* ---------- tempo real ---------- */

  var relogios = {};
  function agendar(chave, funcao) {
    clearTimeout(relogios[chave]);
    relogios[chave] = setTimeout(funcao, 250);   // junta eventos que chegam juntos
  }

  document.addEventListener("reconecta:evento", function (e) {
    var tipo = (e.detail && e.detail.tipo) || "";
    if (tipo === "pedido.publicado" || tipo.indexOf("doacao.") === 0 || tipo.indexOf("pedido.") === 0) {
      agendar("pedidos", function () { carregarPedidos().then(carregarOngs).then(desenhar); });
    }
    if (tipo.indexOf("excedente.") === 0) agendar("doados", function () { carregarDoados().then(desenhar); });
  });

  // a contagem regressiva dos prazos muda com o tempo
  setInterval(function () { if (estado.aba !== "ongs") desenhar(); }, 60000);

  /* "Ao vivo" quando o fluxo está aberto; na consulta periódica, diz o intervalo */
  function mostrarEstado() {
    var est = document.documentElement.getAttribute("data-tempo-real");
    document.querySelectorAll("[data-ao-vivo]").forEach(function (no) {
      no.hidden = est !== "sse" && est !== "consulta";
      no.textContent = est === "sse" ? "Ao vivo" : "Atualiza a cada 10 s";
      no.classList.toggle("ao-vivo--consulta", est === "consulta");
    });
  }
  if (typeof MutationObserver === "function") {
    new MutationObserver(mostrarEstado).observe(document.documentElement, { attributes: true, attributeFilter: ["data-tempo-real"] });
  }
  mostrarEstado();

  /* ---------- assistente "Tenho alimento para doar" ---------- */

  var CHAVE_TEXTO = "reconecta:assistente-texto";
  var CHAVE_RASCUNHO = "reconecta:rascunho-excedente";
  function guardar(chave, valor) { try { sessionStorage.setItem(chave, valor); } catch (erro) { /* sem armazenamento: segue sem guardar */ } }
  function ler(chave) { try { return sessionStorage.getItem(chave) || ""; } catch (erro) { return ""; } }
  function apagar(chave) { try { sessionStorage.removeItem(chave); } catch (erro) { /* idem */ } }

  var dlg = $("assistente");
  var campoTexto = $("assistente-texto");
  var resultado = $("assistente-resultado");
  var avisoAssistente = $("assistente-aviso");
  var campoCep = $("assistente-cep");
  var cepDigitado = false;
  function erroCep(mensagem) {
    $("assistente-cep-erro").textContent = mensagem || "";
    if (mensagem) campoCep.setAttribute("aria-invalid", "true"); else campoCep.removeAttribute("aria-invalid");
  }
  campoCep.addEventListener("input", function () {
    var d = campoCep.value.replace(/\D/g, "").slice(0, 8);
    campoCep.value = d.length > 5 ? d.slice(0, 5) + "-" + d.slice(5) : d;
    if (campoCep.getAttribute("aria-invalid")) erroCep("");
  });

  function erroTexto(mensagem) {
    $("assistente-texto-erro").textContent = mensagem || "";
    if (mensagem) campoTexto.setAttribute("aria-invalid", "true"); else campoTexto.removeAttribute("aria-invalid");
  }

  function avisar(tituloAviso, texto) {
    avisoAssistente.className = "aviso aviso--erro";
    avisoAssistente.replaceChildren(el("p", { classe: "aviso__titulo", texto: tituloAviso }), texto ? el("p", { texto: texto }) : null);
    avisoAssistente.hidden = false;
  }

  function abrirAssistente() {
    $("assistente-entrar").hidden = true;
    avisoAssistente.hidden = true;
    if (!campoTexto.value) campoTexto.value = ler(CHAVE_TEXTO);
    if (typeof dlg.showModal === "function") { if (!dlg.open) dlg.showModal(); }
    else dlg.setAttribute("open", "");
    campoTexto.focus();
  }
  function fecharAssistente() {
    if (typeof dlg.close === "function" && dlg.open) dlg.close(); else dlg.removeAttribute("open");
  }

  function pedirEntrada() {
    guardar(CHAVE_TEXTO, campoTexto.value.trim());
    $("assistente-link-entrar").href = "/entrar?proximo=" + encodeURIComponent("/?assistente=1");
    resultado.hidden = true;
    $("assistente-entrar").hidden = false;
    $("assistente-link-entrar").focus();
  }

  function maiuscula(t) { t = String(t || ""); return t.charAt(0).toUpperCase() + t.slice(1); }

  function cartaoSugestao(sg) {
    var distancia = sg.distancia || "";
    var onde = [sg.municipio_uf ? local(sg.municipio_uf) : "", distancia].filter(Boolean).join(" · ");
    var pontos = Math.max(0, Math.min(100, Number(sg.pontuacao) || 0));
    var qtdSugerida = Number(sg.quantidade_sugerida);
    var destino = "/doacoes/" + sg.pedido_id + "?item=" + encodeURIComponent(sg.item_id) +
      (isFinite(qtdSugerida) && qtdSugerida > 0 ? "&quantidade=" + encodeURIComponent(qtdSugerida) : "");
    return el("li", { classe: "sugestao" }, [
      el("div", { classe: "sugestao__topo" }, [
        el("div", null, [
          el("h4", { classe: "sugestao__nome", texto: titulo(sg.organizacao) }),
          onde ? el("p", { classe: "sugestao__local", texto: onde }) : null
        ]),
        el("p", { classe: "sugestao__pontos" }, [el("strong", { texto: String(pontos) }), " de 100"])
      ]),
      el("span", { classe: "sugestao__barra", "aria-hidden": "true" }, [el("span", { style: "width:" + pontos + "%" })]),
      el("ul", { classe: "sugestao__motivos", "aria-label": "Por que combina" },
        // a distância já aparece ao lado da cidade
        (sg.motivos || []).filter(function (m) { return m !== distancia; }).map(function (m) { return el("li", { texto: maiuscula(m) }); })),
      el("a", { classe: "btn btn--primario btn--pequeno", href: destino,
                "aria-label": "Doar para o pedido de " + titulo(sg.organizacao) }, ["Doar para este pedido"])
    ]);
  }

  function mostrarResultado(c, texto) {
    var itens = Array.isArray(c.itens) ? c.itens : [];
    var sugestoes = Array.isArray(c.sugestoes) ? c.sugestoes : [];
    var blocos = [];
    if (itens.length) {
      blocos.push(el("h3", { texto: "Entendemos assim" }));
      blocos.push(el("ul", { classe: "assistente__itens" }, itens.map(function (i) {
        return el("li", null, [el("strong", { texto: quantidade(i) + " de " + i.nome }), " · " + i.categoria]);
      })));
    } else {
      blocos.push(el("p", { classe: "assistente__nada", texto: "Não conseguimos identificar os alimentos. Escreva a quantidade e o alimento, como “30 pães e 5 kg de tomate”." }));
    }
    if (sugestoes.length) {
      blocos.push(el("h3", { texto: sugestoes.length === 1 ? "O pedido que mais combina" : "Os pedidos que mais combinam" }));
      blocos.push(el("ol", { classe: "assistente__sugestoes" }, sugestoes.map(cartaoSugestao)));
    } else if (itens.length) {
      blocos.push(el("p", { classe: "assistente__nada", texto: "Nenhum pedido aberto combina com isso agora." }));
    }
    var acoes = [];
    if (c.pode_publicar_excedente && itens.length) {
      var publicar = el("a", { classe: "btn " + (sugestoes.length ? "btn--secundario" : "btn--primario") + " btn--pequeno",
        href: "/painel#publicar-excedente" }, ["Doar o que sobrou"]);
      // o painel pode aproveitar os itens já interpretados
      publicar.addEventListener("click", function () { guardar(CHAVE_RASCUNHO, JSON.stringify({ texto: texto, itens: itens })); });
      acoes.push(publicar);
    }
    if (!sugestoes.length) {
      var ver = el("a", { classe: "btn btn--secundario btn--pequeno", href: "#doacoes" }, ["Ver os pedidos abertos"]);
      ver.addEventListener("click", fecharAssistente);
      acoes.push(ver);
    }
    if (acoes.length) blocos.push(el("div", { classe: "assistente__acoes" }, acoes));
    var distancias = "";
    if (sugestoes.length && c.origem) {
      distancias = "Distâncias em linha reta a partir " + (usuarioAtual && usuarioAtual.tipo === "empresa" ? "do endereço da sua organização" : "do CEP informado") +
        (c.origem.precisao === "municipio" ? ", localizado pela cidade (aproximadas). " : ". ");
    } else if (sugestoes.length && cepDigitado) {
      distancias = "Não conseguimos localizar o CEP; as sugestões não consideram a distância. ";
    }
    blocos.push(el("p", { classe: "assistente__nota", texto:
      distancias + "É uma recomendação: você escolhe para quem doar. " +
      (c.fonte === "llm" ? "Interpretação feita pelo modelo local gratuito" + (c.modelo ? " " + c.modelo : "") + "."
                         : "Interpretação feita pelas regras automáticas e pelo classificador do projeto.") }));
    resultado.replaceChildren.apply(resultado, blocos);
    resultado.hidden = false;
    resultado.focus();
  }

  $("assistente-form").addEventListener("submit", function (e) {
    e.preventDefault();
    var texto = campoTexto.value.trim();
    avisoAssistente.hidden = true;
    if (texto.length < 5) { erroTexto("Descreva o que você tem, com pelo menos 5 caracteres."); campoTexto.focus(); return; }
    erroTexto("");
    if (!usuarioAtual) { pedirEntrada(); return; }
    var cep = usuarioAtual.tipo === "empresa" ? "" : campoCep.value.replace(/\D/g, "");
    if (cep && cep.length !== 8) { erroCep("Informe o CEP com 8 números ou deixe em branco."); campoCep.focus(); return; }
    erroCep("");
    cepDigitado = !!cep;
    var btn = $("assistente-enviar");
    btn.disabled = true; btn.classList.add("is-carregando"); btn.textContent = "Procurando…";
    resultado.hidden = true;
    fetch("/reconecta/ia/sugerir-destino", {
      method: "POST", credentials: "same-origin",
      headers: { "Content-Type": "application/json", "Accept": "application/json" },
      body: JSON.stringify(cep ? { texto: texto, cep: cep } : { texto: texto })
    }).then(function (r) {
      return r.json().catch(function () { return {}; }).then(function (c) { return { status: r.status, corpo: c || {} }; });
    }).then(function (r) {
      var c = r.corpo;
      if (r.status === 200) { apagar(CHAVE_TEXTO); mostrarResultado(c, texto); return; }
      if (r.status === 401) { pedirEntrada(); return; }
      if (r.status === 400 && c.campos && c.campos.texto) { erroTexto(c.campos.texto); campoTexto.focus(); return; }
      if (r.status === 429) { avisar("Muitas consultas seguidas", c.mensagem || "Aguarde um minuto e tente de novo."); return; }
      avisar("Não foi possível sugerir agora", c.mensagem || "Tente novamente em instantes.");
    }).catch(function () {
      avisar("Sem conexão com o servidor", "Verifique sua internet e tente de novo.");
    }).then(function () {
      btn.disabled = false; btn.classList.remove("is-carregando"); btn.textContent = "Ver para onde doar";
    });
  });
  campoTexto.addEventListener("input", function () { if (campoTexto.getAttribute("aria-invalid")) erroTexto(""); });
  $("assistente-fechar").addEventListener("click", fecharAssistente);
  // clique fora do cartão (no fundo do diálogo) fecha
  dlg.addEventListener("click", function (e) { if (e.target === dlg) fecharAssistente(); });
  dlg.addEventListener("close", function () { $("hero-cta").focus(); });
  $("hero-cta").addEventListener("click", abrirAssistente);
  // "Doar" do cabeçalho: na própria Home abre o assistente sem recarregar
  document.addEventListener("click", function (e) {
    var a = e.target.closest && e.target.closest('a[href="/?assistente=1"]');
    if (!a) return;
    e.preventDefault();
    abrirAssistente();
  });

  /* ---------- ações conforme a sessão ---------- */

  function ajustarTopo() {
    var sec = $("hero-secundario");
    if (ehOng()) { sec.href = "/painel#publicar"; sec.textContent = "Publicar pedido"; }
    else if (usuarioAtual) { sec.href = "#doacoes"; sec.textContent = "Ver pedidos das ONGs"; }
    else { sec.href = "/cadastro"; sec.textContent = "Sou ONG · pedir doações"; }
  }

  var abriuPeloEndereco = false;
  document.addEventListener("reconecta:sessao", function (e) {
    var antes = usuarioAtual;
    usuarioAtual = (e.detail && e.detail.usuario) || null;
    ajustarTopo();
    // empresa usa o endereço do cadastro; pessoa física pode informar o CEP
    $("assistente-cep-campo").hidden = !!(usuarioAtual && usuarioAtual.tipo === "empresa");
    // "Sua doação" e as ações dependem de quem está vendo
    if (usuarioAtual && podePublicar()) carregarDoados().then(desenhar);
    else if (antes !== usuarioAtual) desenhar();
    // volta do login com ?assistente=1: reabre com o texto guardado
    if (!abriuPeloEndereco && /[?&]assistente=1(&|$)/.test(location.search)) {
      abriuPeloEndereco = true;
      abrirAssistente();
    }
  });

  montarFiltro();
  abaDoEndereco();
  carregarTudo();
})();
