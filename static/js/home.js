/* ReConecta — Home: resumo, doação mais recente e carrossel de doações disponíveis. */
(function () {
  "use strict";

  var API = "/reconecta/publico";

  var IMG_CATEGORIA = {
    "Hortifrúti": "hortifruti",
    "Padaria": "padaria",
    "Laticínios": "laticinios",
    "Carnes e peixes": "carnes",
    "Grãos e cereais": "graos",
    "Refeições prontas": "refeicoes",
    "Bebidas não alcoólicas": "bebidas",
    "Outros": "outros"
  };
  var CATEGORIAS_PADRAO = Object.keys(IMG_CATEGORIA);

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

  function obter(caminho) {
    return fetch(API + caminho, { headers: { "Accept": "application/json" }, credentials: "same-origin" })
      .then(function (r) { if (!r.ok) throw new Error("HTTP " + r.status); return r.json(); });
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
    var n = String(nome || "").trim();
    if (n && n === n.toUpperCase()) {
      return n.toLowerCase().replace(/(^|\s)(\S)/g, function (m, a, b) { return a + b.toUpperCase(); })
        .replace(/\b(De|Da|Do|Das|Dos|E)\b/g, function (m) { return m.toLowerCase(); });
    }
    return n;
  }

  function local(municipioUf) {
    if (!municipioUf) return "";
    var partes = String(municipioUf).split("/");
    return titulo(partes[0]) + (partes[1] ? " / " + partes[1].toUpperCase() : "");
  }

  function data(valor) {
    if (!valor) return null;
    var d = new Date(String(valor).length <= 10 ? valor + "T00:00:00" : valor);
    return isNaN(d) ? null : d;
  }

  function prazo(valor) {
    var d = data(valor);
    if (!d) return "";
    var hoje = new Date(); hoje.setHours(0, 0, 0, 0);
    var dia = new Date(d); dia.setHours(0, 0, 0, 0);
    var dif = Math.round((dia - hoje) / 86400000);
    var hora = d.toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" });
    var quando;
    if (dif === 0) quando = "hoje";
    else if (dif === 1) quando = "amanhã";
    else if (dif > 1 && dif < 7) quando = d.toLocaleDateString("pt-BR", { weekday: "long" }).replace("-feira", "");
    else quando = d.toLocaleDateString("pt-BR", { day: "2-digit", month: "2-digit" });
    return quando + ", " + hora;
  }

  function haQuanto(valor) {
    var d = data(valor);
    if (!d) return "";
    var min = Math.round((Date.now() - d.getTime()) / 60000);
    if (min < 1) return "agora";
    if (min < 60) return "há " + min + " min";
    var h = Math.round(min / 60);
    if (h < 24) return "há " + h + " h";
    var dias = Math.round(h / 24);
    return dias === 1 ? "ontem" : "há " + dias + " dias";
  }

  function imgCategoria(categoria, tamanho, alt) {
    var slug = IMG_CATEGORIA[categoria] || "outros";
    return el("img", {
      src: "/static/img/categorias/" + slug + ".svg",
      width: String(tamanho), height: String(tamanho),
      alt: alt == null ? "" : alt, loading: "lazy", decoding: "async"
    });
  }

  /* ---------- resumo (métricas do hero) ---------- */

  function preencherResumo(r) {
    var alvo = $("resumo");
    var valores = r ? {
      kg: numero.format(Number(r.kg_disponiveis) || 0),
      doacoes: inteiro.format(Number(r.doacoes_disponiveis) || 0),
      empresas: inteiro.format(Number(r.empresas) || 0)
    } : { kg: "—", doacoes: "—", empresas: "—" };
    Object.keys(valores).forEach(function (k) {
      alvo.querySelector('[data-resumo="' + k + '"]').textContent = valores[k];
    });
    alvo.setAttribute("aria-busy", "false");
  }

  /* ---------- doação mais recente (cartão flutuante) ---------- */

  function resumoItens(itens, max) {
    var nomes = itens.slice(0, max).map(function (i) { return i.nome; });
    var resto = itens.length - nomes.length;
    return nomes.join(", ") + (resto > 0 ? " e mais " + resto : "");
  }

  function preencherUltima(doacoes, falhou) {
    var c = $("ultima-doacao");
    c.replaceChildren();
    c.setAttribute("aria-busy", "false");
    if (falhou) { c.hidden = true; return; }
    var d = doacoes[0];
    if (!d) {
      c.append(
        el("p", { classe: "sobretitulo", texto: "Doações abertas" }),
        el("p", { classe: "ultima__vazia" }, ["Nenhuma doação aberta neste momento. ", el("a", { href: "/cadastro", texto: "Cadastre sua empresa", "data-convite": "" }), " e publique a primeira."])
      );
      ajustarConvites();
      return;
    }
    var est = d.estabelecimento || {};
    c.append(
      el("p", { classe: "sobretitulo" }, ["Mais recente · ", haQuanto(d.data_cadastro)]),
      el("p", { classe: "ultima__nome", texto: titulo(est.nome) }),
      est.municipio_uf ? el("p", { classe: "ultima__local", texto: local(est.municipio_uf) }) : null,
      el("p", { classe: "ultima__itens", texto: resumoItens(d.itens || [], 3) }),
      el("div", { classe: "ultima__rodape" }, [
        el("span", null, ["Retirar até ", el("strong", { texto: prazo(d.data_limite_retirada) })]),
        el("a", { href: "#doacoes", texto: "Ver todas" })
      ])
    );
  }

  /* ---------- carrossel ---------- */

  function cartaoDoacao(d) {
    var est = d.estabelecimento || {};
    var itens = d.itens || [];
    var categorias = d.categorias && d.categorias.length ? d.categorias : [itens[0] && itens[0].categoria];
    var MAX = 3;
    var lista = el("ul", { classe: "doacao__itens" }, itens.slice(0, MAX).map(function (i) {
      return el("li", null, [el("span", { texto: i.nome, title: i.nome }), el("span", { texto: quantidade(i) })]);
    }));
    var corpo = el("div", { classe: "doacao__corpo" }, [
      el("h3", { classe: "doacao__nome", texto: titulo(est.nome) }),
      el("p", { classe: "doacao__local", texto: local(est.municipio_uf) }),
      lista,
      itens.length > MAX ? el("p", { classe: "doacao__mais", texto: "+ " + (itens.length - MAX) + (itens.length - MAX === 1 ? " item" : " itens") }) : null
    ]);
    return el("li", { classe: "doacao" }, [
      imgCategoria(categorias[0], 76, ""),
      corpo,
      el("div", { classe: "doacao__rodape" }, [
        el("span", { classe: "doacao__prazo" }, ["Retirar até ", el("strong", { texto: prazo(d.data_limite_retirada) })]),
        el("span", { classe: "doacao__cats" }, categorias.filter(Boolean).map(function (c) { return el("span", { classe: "selo", texto: c }); }))
      ])
    ]);
  }

  function montarCarrossel(doacoes) {
    var alvo = $("doacoes-conteudo");
    var lista = el("ul", {
      classe: "carrossel", id: "lista-doacoes", tabindex: "0",
      "aria-label": doacoes.length + (doacoes.length === 1 ? " doação disponível" : " doações disponíveis")
    }, doacoes.map(cartaoDoacao));
    alvo.replaceChildren(lista);
    alvo.setAttribute("aria-busy", "false");

    var controles = $("carrossel-controles");
    var anterior = $("carrossel-anterior");
    var proximo = $("carrossel-proximo");

    function atualizar() {
      var max = lista.scrollWidth - lista.clientWidth;
      controles.hidden = max <= 4;
      anterior.disabled = lista.scrollLeft <= 4;
      proximo.disabled = lista.scrollLeft >= max - 4;
    }
    function passo(direcao) {
      var item = lista.querySelector(".doacao");
      var largura = item ? item.getBoundingClientRect().width + 16 : lista.clientWidth;
      var porVez = Math.max(1, Math.floor((lista.clientWidth + 16) / largura));
      lista.scrollBy({ left: direcao * largura * porVez, behavior: "smooth" });
    }
    anterior.onclick = function () { passo(-1); };
    proximo.onclick = function () { passo(1); };
    lista.addEventListener("scroll", function () { window.requestAnimationFrame(atualizar); }, { passive: true });
    window.addEventListener("resize", atualizar);
    atualizar();
  }

  function montarVazio(categorias) {
    var alvo = $("doacoes-conteudo");
    $("carrossel-controles").hidden = true;
    alvo.replaceChildren(el("div", { classe: "vazio" }, [
      el("div", { classe: "vazio__texto" }, [
        el("h3", { texto: "Nenhuma doação aberta agora" }),
        el("p", { texto: "Assim que uma empresa publicar o excedente do dia, ele aparece aqui. Estas são as categorias que a plataforma recebe:" })
      ]),
      el("ul", { classe: "categorias" }, categorias.map(function (c) {
        return el("li", { classe: "categoria-convite" }, [imgCategoria(c, 72, ""), c]);
      })),
      el("div", { classe: "vazio__acoes" }, [
        el("a", { classe: "btn btn--primario", href: "/cadastro" }, ["Cadastrar minha empresa"]),
        el("a", { classe: "btn btn--secundario", href: "/sobre#criterio" }, ["Quem pode doar"])
      ])
    ]));
    alvo.setAttribute("aria-busy", "false");
  }

  function montarFalha() {
    var alvo = $("doacoes-conteudo");
    $("carrossel-controles").hidden = true;
    var tentar = el("button", { type: "button", classe: "btn btn--secundario btn--pequeno", texto: "Tentar novamente" });
    tentar.addEventListener("click", carregar);
    alvo.replaceChildren(el("div", { classe: "aviso falha", role: "alert" }, [
      el("p", { texto: "Não conseguimos carregar as doações agora." }), tentar
    ]));
    alvo.setAttribute("aria-busy", "false");
  }

  /* ---------- carga ---------- */

  function carregar() {
    $("doacoes-conteudo").setAttribute("aria-busy", "true");
    obter("/resumo").then(preencherResumo, function () { preencherResumo(null); });

    obter("/doacoes?limite=8").then(function (doacoes) {
      doacoes = Array.isArray(doacoes) ? doacoes : [];
      preencherUltima(doacoes, false);
      if (doacoes.length) { montarCarrossel(doacoes); return; }
      return obter("/opcoes")
        .then(function (o) { return o && o.categorias && o.categorias.length ? o.categorias : CATEGORIAS_PADRAO; },
              function () { return CATEGORIAS_PADRAO; })
        .then(montarVazio);
    }).catch(function () {
      preencherUltima([], true);
      montarFalha();
    });
  }

  /* ---------- CTA conforme a sessão ---------- */

  var usuarioAtual = null;
  function ajustarConvites() {
    document.querySelectorAll("[data-convite]").forEach(function (a) {
      if (usuarioAtual && usuarioAtual.tipo === "empresa") { a.href = "/painel"; a.textContent = "Abra o painel"; }
    });
  }

  document.addEventListener("reconecta:sessao", function (e) {
    var u = e.detail && e.detail.usuario;
    usuarioAtual = u;
    ajustarConvites();
    var cta = $("hero-cta");
    if (!cta) return;
    var rotulo = cta.querySelector("[data-cta-rotulo]");
    var acao = cta.querySelector("[data-cta-acao]");
    if (u && u.tipo === "empresa") { cta.href = "/painel"; rotulo.textContent = "Publicar doação"; acao.textContent = "Painel"; }
    else if (u) { cta.href = "/painel"; rotulo.textContent = "Meu cadastro"; acao.textContent = "Painel"; }
    else { cta.href = "/cadastro"; rotulo.textContent = "Quero doar"; acao.textContent = "Cadastrar"; }
  });

  carregar();
})();
