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
    // formato de título com siglas preservadas (layout.js)
    var R = window.ReConecta;
    return R && R.nomeTitulo ? R.nomeTitulo(nome) : String(nome || "").trim();
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

  /* estilo "redondo": miniaturas SVG do carrossel; "foto": ilustrações recortadas da grade de categorias */
  function imgCategoria(categoria, tamanho, alt, estilo) {
    var slug = IMG_CATEGORIA[categoria] || "outros";
    return el("img", {
      src: estilo === "foto" ? "/static/img/doacoes/cat-" + slug + ".webp" : "/static/img/categorias/" + slug + ".svg",
      width: String(tamanho), height: String(tamanho),
      alt: alt == null ? "" : alt, loading: "lazy", decoding: "async"
    });
  }

  /* Quem doa: empresa (estabelecimento, nome da Receita) ou pessoa física (doador:
     só o primeiro nome e a cidade, sem dados pessoais). */
  function origem(d) {
    if (d.origem === "doador" || (!d.estabelecimento && d.doador)) {
      var p = d.doador || {};
      return { nome: p.nome || "Doador", municipio_uf: p.municipio_uf, pf: true };
    }
    var e = d.empresa || d.estabelecimento || {}; // pedidos (rodada 9) vêm com "empresa"
    return { nome: e.nome, municipio_uf: e.municipio_uf, pf: false };
  }
  function tituloOrigem(o) { return o.pf ? String(o.nome || "") : titulo(o.nome); }
  function seloPF() { return el("span", { classe: "selo selo--pf", texto: "Pessoa física" }); }

  /* ---------- resumo (métricas do hero) ---------- */

  function preencherResumo(r) {
    var alvo = $("resumo");
    var valores = r ? {
      doacoes: inteiro.format(Number(r.doacoes_disponiveis) || 0),      // pedidos abertos
      recebidas: typeof r.doacoes_recebidas === "number" ? inteiro.format(r.doacoes_recebidas) : "—",
      // "instituicoes" vem do backend a partir da rodada 4; sem ele, mostra traço
      instituicoes: typeof r.instituicoes === "number" ? inteiro.format(r.instituicoes) : "—"
    } : { doacoes: "—", recebidas: "—", instituicoes: "—" };
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
    var cartao = $("ultima-doacao");
    var c = $("ultima-doacao-corpo");   // o ícone da caixa fica fixo no HTML
    c.replaceChildren();
    cartao.setAttribute("aria-busy", "false");
    if (falhou) { cartao.hidden = true; return; }
    var d = doacoes[0];
    if (!d) {
      c.append(
        el("p", { classe: "sobretitulo", texto: "Pedidos abertos" }),
        el("p", { classe: "ultima__vazia" }, ["Nenhum pedido aberto neste momento. ", el("a", { href: "/cadastro", texto: "Cadastre sua empresa", "data-convite": "" }), " e publique o primeiro."])
      );
      ajustarConvites();
      return;
    }
    var est = origem(d);
    c.append(
      el("p", { classe: "sobretitulo", texto: d.data_cadastro ? "Pedido mais recente · " + haQuanto(d.data_cadastro) : "Pedido mais recente" }),
      el("p", { classe: "ultima__nome" }, [tituloOrigem(est)]),
      est.municipio_uf ? el("p", { classe: "ultima__local", texto: local(est.municipio_uf) }) : null,
      el("p", { classe: "ultima__itens", texto: "Precisa de " + resumoItens(d.itens || [], 3).toLowerCase() }),
      el("div", { classe: "ultima__rodape" }, [
        el("span", null, ["Receber até ", el("strong", { texto: prazo(receberAte(d)) })]),
        el("a", { href: "/doacoes/" + d.id, texto: "Doar" })
      ])
    );
  }

  /* ---------- carrossel ---------- */

  function receberAte(d) { return d.receber_ate || d.data_limite_retirada; }

  /* "Leite · 12 de 100 unidades" com uma barra fina de progresso */
  function itemPedido(i) {
    var meta = Number(i.quantidade) || 0, recebido = Number(i.recebido) || 0;
    var pct = meta > 0 ? Math.min(100, Math.round(recebido / meta * 100)) : 0;
    var texto = numero.format(recebido) + " de " + quantidade(i);
    return el("li", { classe: "pedido-linha" }, [
      el("span", { classe: "pedido-linha__topo" }, [el("span", { classe: "pedido-linha__nome", texto: i.nome, title: i.nome }), el("span", { classe: "pedido-linha__qtd", texto: texto })]),
      el("span", { classe: "pedido-linha__barra", role: "progressbar", "aria-label": "Recebido de " + i.nome, "aria-valuemin": "0", "aria-valuemax": String(meta), "aria-valuenow": String(Math.min(recebido, meta)), "aria-valuetext": texto }, [
        el("span", { style: "width:" + pct + "%" })
      ])
    ]);
  }

  function cartaoDoacao(d) {
    var est = origem(d);
    var itens = d.itens || [];
    var categorias = d.categorias && d.categorias.length ? d.categorias : [itens[0] && itens[0].categoria];
    var MAX = 3;
    var corpo = el("div", { classe: "doacao__corpo" }, [
      el("h3", { classe: "doacao__nome" }, [tituloOrigem(est)]),
      el("p", { classe: "doacao__local", texto: local(est.municipio_uf) }),
      el("p", { classe: "doacao__precisa", texto: "Precisa de" }),
      el("ul", { classe: "doacao__itens doacao__itens--pedido" }, itens.slice(0, MAX).map(itemPedido)),
      itens.length > MAX ? el("p", { classe: "doacao__mais", texto: "+ " + (itens.length - MAX) + (itens.length - MAX === 1 ? " item" : " itens") }) : null
    ]);
    return el("li", { classe: "doacao doacao--pedido" }, [
      imgCategoria(categorias[0], 76, ""),
      corpo,
      el("div", { classe: "doacao__rodape" }, [
        el("span", { classe: "doacao__prazo" }, ["Receber até ", el("strong", { texto: prazo(receberAte(d)) })]),
        el("a", { classe: "btn btn--primario btn--pequeno doacao__doar", href: "/doacoes/" + d.id, "aria-label": "Doar para o pedido de " + tituloOrigem(est) }, ["Doar"])
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

  var SVG = {
    chevron: '<path d="M9 5.5 15.5 12 9 18.5" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>',
    predio: '<path d="M4 20.5V5.5l8-2.5v17.5M12 8.5l8 2.5v9.5M2.5 20.5h19" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round" stroke-linecap="round"/><path d="M7 8.5h1.5M7 12h1.5M7 15.5h1.5M15 13.5h1.5M15 17h1.5" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/>',
    seta: '<path d="M4 12h15M13 6l6 6-6 6" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/>',
    duvida: '<circle cx="12" cy="12" r="9" fill="none" stroke="currentColor" stroke-width="1.8"/><path d="M9.6 9.4a2.5 2.5 0 0 1 4.8.9c0 1.7-2.4 2.1-2.4 3.7" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/><circle cx="12" cy="17" r="1.1" fill="currentColor"/>'
  };
  function svg(nome, classe) {
    var span = el("span", { classe: classe, "aria-hidden": "true" });
    span.innerHTML = '<svg viewBox="0 0 24 24" focusable="false">' + SVG[nome] + "</svg>";
    return span;
  }

  /* Sem doações: grade de categorias aceitas. Cada cartão leva ao cadastro da empresa
     (ou ao painel, se uma empresa já estiver logada): não há filtro por categoria. */
  function montarVazio(categorias) {
    var alvo = $("doacoes-conteudo");
    $("carrossel-controles").hidden = true;
    alvo.replaceChildren(el("div", { classe: "vazio" }, [
      el("div", { classe: "vazio__texto" }, [
        el("h3", { texto: "Nenhuma doação aberta agora" }),
        el("p", { texto: "Assim que uma empresa publicar um pedido, ele aparece aqui para quem quiser doar. Estas são as categorias que a plataforma recebe:" })
      ]),
      el("ul", { classe: "categorias" }, categorias.map(function (c) {
        var slug = IMG_CATEGORIA[c] || "outros";
        return el("li", null, [
          el("a", { classe: "categoria categoria--" + slug, href: "/cadastro", "data-destino-empresa": "",
                      "aria-label": c + ": cadastrar empresa que doa esta categoria" }, [
            el("span", { classe: "categoria__icone" }, [imgCategoria(c, 56, "", "foto")]),
            el("span", { classe: "categoria__nome", texto: c }),
            svg("chevron", "categoria__seta")
          ])
        ]);
      })),
      el("div", { classe: "vazio__acoes" }, [
        el("a", { classe: "vazio__cta", href: "/cadastro", "data-destino-empresa": "" }, [
          svg("predio", "vazio__cta-icone"), el("span", { texto: "Cadastrar minha empresa" }), svg("seta", "vazio__cta-seta")
        ]),
        el("a", { classe: "vazio__quem", href: "/sobre#criterio" }, [svg("duvida", "vazio__quem-icone"), "Quem pode doar"])
      ])
    ]));
    alvo.setAttribute("aria-busy", "false");
    ajustarConvites();
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
    var empresa = usuarioAtual && usuarioAtual.tipo === "empresa";
    document.querySelectorAll("[data-destino-empresa]").forEach(function (a) { a.href = empresa ? "/painel" : "/cadastro"; });
  }

  document.addEventListener("reconecta:sessao", function (e) {
    var u = e.detail && e.detail.usuario;
    usuarioAtual = u;
    ajustarConvites();
    var cta = $("hero-cta");
    if (!cta) return;
    var rotulo = cta.querySelector("[data-cta-rotulo]");
    var sec = $("hero-secundario");
    // empresa publica pedidos; quem tem CPF (ou visita) vai direto aos pedidos para doar
    if (u && u.tipo === "empresa") {
      cta.href = "/painel#publicar"; rotulo.textContent = "Publicar pedido";
      if (sec) { sec.href = "#doacoes"; sec.textContent = "Ver doações disponíveis"; }
    } else {
      cta.href = "#doacoes"; rotulo.textContent = "Quero doar";
      if (sec && u) { sec.href = "#como-funciona"; sec.textContent = "Como funciona"; }
    }
  });

  carregar();
})();
