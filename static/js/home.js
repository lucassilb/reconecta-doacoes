/* ReConecta — Home: resumo, pedido mais recente, carrossel de pedidos, faixa de excedentes
   e o assistente "Tenho alimento para doar". Os trechos se atualizam sozinhos com os eventos
   de tempo real que o layout.js dispara em "reconecta:evento". */
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
    return window.ReConecta.dataBrasilia(valor);
  }

  function prazo(valor) {
    var d = data(valor);
    if (!d) return "";
    var hoje = window.ReConecta.diaISO(new Date());
    var dia = window.ReConecta.diaISO(d);
    var dif = Math.round((Date.parse(dia + "T00:00:00Z") - Date.parse(hoje + "T00:00:00Z")) / 86400000);
    var hora = d.toLocaleTimeString("pt-BR", { timeZone: window.ReConecta.fuso, hour: "2-digit", minute: "2-digit" });
    var quando;
    if (dif === 0) quando = "hoje";
    else if (dif === 1) quando = "amanhã";
    else if (dif > 1 && dif < 7) quando = d.toLocaleDateString("pt-BR", { timeZone: window.ReConecta.fuso, weekday: "long" }).replace("-feira", "");
    else quando = d.toLocaleDateString("pt-BR", { timeZone: window.ReConecta.fuso, day: "2-digit", month: "2-digit" });
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
      recebidas: typeof r.doacoes_recebidas === "number" ? inteiro.format(r.doacoes_recebidas) : "—"
    } : { doacoes: "—", recebidas: "—" };
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

  /* Frase do cartão "Pedidos abertos" sem pedido: o convite muda com quem está vendo. */
  function conviteSemPedido() {
    if (usuarioAtual && !ehOng() && podePublicar()) {
      return ["Nenhum pedido aberto neste momento. Tem alimento sobrando? ",
              el("a", { href: "/painel#publicar-excedente", texto: "Doe o que sobrou", "data-convite": "" }), " para uma ONG retirar."];
    }
    if (usuarioAtual) {
      return ["Nenhum pedido aberto neste momento. ",
              el("a", { href: "/painel#publicar", texto: "Publique o pedido da sua ONG", "data-convite": "" }), "."];
    }
    return ["Nenhum pedido aberto neste momento. ", el("a", { href: "/cadastro", texto: "Cadastre sua ONG", "data-convite": "" }), " e publique o primeiro."];
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
        el("p", { classe: "ultima__vazia" }, conviteSemPedido())
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

  var atualizarControles = null;
  window.addEventListener("resize", function () { if (atualizarControles) atualizarControles(); });

  function montarCarrossel(doacoes) {
    var alvo = $("doacoes-conteudo");
    var anteriorLista = $("lista-doacoes");
    var posicao = anteriorLista ? anteriorLista.scrollLeft : 0;
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
    atualizarControles = atualizar;
    if (posicao) lista.scrollLeft = posicao;
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

  /* Sem pedido aberto: diz isso com clareza e oferece o caminho que existe agora,
     "Doar o que sobrou" (publicar para as ONGs retirarem). As categorias são só
     informativas: nenhum cartão leva a cadastro ou login de quem já entrou. */
  var categoriasVazio = null;
  function podePublicar() { return !!(usuarioAtual && (usuarioAtual.tipo === "doador" || ehEmpresaAlimentos())); }
  function acoesVazio() {
    var principal, secundaria;
    if (!usuarioAtual) {
      principal = el("button", { type: "button", classe: "vazio__cta" }, [
        svg("predio", "vazio__cta-icone"), el("span", { texto: "Doar o que sobrou" }), svg("seta", "vazio__cta-seta")]);
      principal.addEventListener("click", abrirAssistente);
      secundaria = el("a", { classe: "vazio__quem", href: "/cadastro" }, [svg("duvida", "vazio__quem-icone"), "Criar conta (CPF ou CNPJ)"]);
    } else if (!ehOng() && podePublicar()) {
      principal = el("a", { classe: "vazio__cta", href: "/painel#publicar-excedente" }, [
        svg("predio", "vazio__cta-icone"), el("span", { texto: "Doar o que sobrou" }), svg("seta", "vazio__cta-seta")]);
      secundaria = el("a", { classe: "vazio__quem", href: "#excedentes" }, [svg("duvida", "vazio__quem-icone"), "O que já foi oferecido"]);
    } else {
      // ONG: o caminho dela é pedir ou reservar o que foi oferecido
      principal = el("a", { classe: "vazio__cta", href: "/painel#publicar" }, [
        svg("predio", "vazio__cta-icone"), el("span", { texto: "Publicar um pedido" }), svg("seta", "vazio__cta-seta")]);
      secundaria = el("a", { classe: "vazio__quem", href: "#excedentes" }, [svg("duvida", "vazio__quem-icone"), "Ver excedentes de hoje"]);
    }
    return el("div", { classe: "vazio__acoes" }, [principal, secundaria]);
  }
  function montarVazio(categorias) {
    categoriasVazio = categorias;
    var alvo = $("doacoes-conteudo");
    $("carrossel-controles").hidden = true;
    atualizarControles = null;
    var ong = !!usuarioAtual && ehOng();
    alvo.replaceChildren(el("div", { classe: "vazio" }, [
      el("div", { classe: "vazio__texto" }, [
        el("h3", { texto: "Nenhum pedido aberto agora" }),
        el("p", { texto: ong
          ? "Quando uma ONG publicar o que está faltando, o pedido aparece aqui na hora. Publique o pedido da sua organização para receber doações."
          : "Quando uma ONG publicar o que está faltando, o pedido aparece aqui na hora. Tem alimento sobrando? Dá para doar agora: publique o que sobrou e uma ONG reserva e retira." })
      ]),
      acoesVazio(),
      el("p", { classe: "vazio__legenda", texto: "Categorias que a plataforma recebe:" }),
      el("ul", { classe: "categorias categorias--info", "aria-label": "Categorias que a plataforma recebe" }, categorias.map(function (c) {
        var slug = IMG_CATEGORIA[c] || "outros";
        return el("li", null, [
          el("span", { classe: "categoria categoria--" + slug }, [
            el("span", { classe: "categoria__icone" }, [imgCategoria(c, 56, "", "foto")]),
            el("span", { classe: "categoria__nome", texto: c })
          ])
        ]);
      }))
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

  function carregar(aoVivo) {
    aoVivo = aoVivo === true;
    if (!aoVivo) $("doacoes-conteudo").setAttribute("aria-busy", "true");
    obter("/resumo").then(preencherResumo, function () { if (!aoVivo) preencherResumo(null); });

    obter("/doacoes?limite=8").then(function (doacoes) {
      doacoes = Array.isArray(doacoes) ? doacoes : [];
      preencherUltima(doacoes, false);
      if (doacoes.length) { montarCarrossel(doacoes); return; }
      return obter("/opcoes")
        .then(function (o) { return o && o.categorias && o.categorias.length ? o.categorias : CATEGORIAS_PADRAO; },
              function () { return CATEGORIAS_PADRAO; })
        .then(montarVazio);
    }).catch(function () {
      if (aoVivo) return;            // falha numa atualização ao vivo: fica o que já estava na tela
      preencherUltima([], true);
      montarFalha();
    });
  }

  /* ---------- excedentes de hoje ---------- */

  function faltaTexto(ate) {
    var d = data(ate);
    if (!d) return "";
    var min = Math.floor((d.getTime() - Date.now()) / 60000);
    if (min < 1) return "encerra agora";
    if (min < 60) return "faltam " + min + " min";
    var h = Math.floor(min / 60), resto = min % 60;
    if (h < 24) return "faltam " + h + " h" + (resto ? " " + resto + " min" : "");
    var dias = Math.floor(h / 24);
    return "faltam " + dias + (dias === 1 ? " dia" : " dias");
  }

  function validadeCurta(iso) {
    var d = data(iso);
    if (!d) return "";
    var hoje = window.ReConecta.diaISO(new Date());
    if (iso === hoje) return "vence hoje";
    return "vence " + d.toLocaleDateString("pt-BR", { timeZone: window.ReConecta.fuso, day: "2-digit", month: "2-digit" });
  }

  function ehOng() { return !!(usuarioAtual && usuarioAtual.tipo === "empresa" && (usuarioAtual.perfis || []).indexOf("ong") !== -1); }
  function ehEmpresaAlimentos() { return !!(usuarioAtual && usuarioAtual.tipo === "empresa" && (usuarioAtual.perfis || []).indexOf("empresa_alimentos") !== -1); }

  function cartaoExcedente(x) {
    var emp = x.empresa || {};
    var itens = x.itens || [];
    var MAX = 3;
    return el("li", { classe: "excedente", "data-excedente": String(x.id) }, [
      el("div", { classe: "excedente__topo" }, [
        imgCategoria(itens[0] && itens[0].categoria, 52, ""),
        el("div", null, [
          el("h3", { classe: "excedente__nome", texto: titulo(emp.nome) }),
          el("p", { classe: "excedente__local", texto: local(emp.municipio_uf) })
        ])
      ]),
      el("ul", { classe: "excedente__itens" }, itens.slice(0, MAX).map(function (i) {
        return el("li", null, [
          el("span", { classe: "excedente__item", texto: quantidade(i) + " de " + i.nome }),
          el("span", { classe: "excedente__validade", texto: validadeCurta(i.validade) })
        ]);
      })),
      itens.length > MAX ? el("p", { classe: "doacao__mais", texto: "+ " + (itens.length - MAX) + (itens.length - MAX === 1 ? " item" : " itens") }) : null,
      el("div", { classe: "excedente__rodape" }, [
        el("p", { classe: "excedente__prazo" }, [
          "Retirar até ", el("strong", { texto: prazo(x.retirar_ate) }),
          el("span", { classe: "excedente__falta", "data-ate": x.retirar_ate, texto: faltaTexto(x.retirar_ate) })
        ]),
        el("a", { classe: "btn btn--primario btn--pequeno", href: "/excedentes/" + x.id,
                  "aria-label": (ehOng() ? "Ver e reservar" : "Ver") + " o excedente de " + titulo(emp.nome) },
           [ehOng() ? "Ver e reservar" : "Ver detalhes"])
      ])
    ]);
  }

  var excedentesAtuais = null, excedentesTotal = 0;
  function desenharExcedentes(lista, total) {
    excedentesAtuais = lista; excedentesTotal = total;
    var alvo = $("excedentes-conteudo");
    var metrica = document.querySelector('[data-resumo="excedentes"]');
    if (metrica) metrica.textContent = inteiro.format(total);
    // uma linha de explicação e uma ação útil para cada perfil, nunca um beco sem saída
    var publicar = $("excedentes-publicar"), lead = $("excedentes-lead");
    if (ehOng()) {
      publicar.hidden = !ehEmpresaAlimentos();
      publicar.textContent = "Publicar excedente"; publicar.href = "/painel#publicar-excedente";
      lead.textContent = "Alimentos oferecidos por empresas e pessoas para a sua ONG reservar e retirar antes de vencer. Quando alguém reserva, o cartão some daqui na hora.";
    } else if (podePublicar()) {
      publicar.hidden = false;
      publicar.textContent = "Doar o que sobrou"; publicar.href = "/painel#publicar-excedente";
      lead.textContent = "Alimentos oferecidos para ONGs retirarem; só ONGs reservam. Quer doar também? Publique o que sobrou e uma ONG retira.";
    } else if (!usuarioAtual) {
      publicar.hidden = false;
      publicar.textContent = "Entrar como ONG"; publicar.href = "/entrar?proximo=" + encodeURIComponent("/#excedentes");
      lead.textContent = "Alimentos oferecidos por empresas e pessoas para ONGs retirarem antes de vencer. A ONG entra, reserva pelo site e retira no prazo.";
    } else {
      publicar.hidden = true;
      lead.textContent = "Alimentos oferecidos para ONGs retirarem; só ONGs reservam. Para doar, escolha um pedido das ONGs acima.";
    }
    if (!lista.length) {
      alvo.replaceChildren(el("div", { classe: "excedentes__vazio" }, [
        el("h3", { texto: "Nenhum excedente disponível agora" }),
        el("p", { texto: podePublicar()
          ? "Sobrou alimento bom hoje? Publique e as ONGs com pedido parecido são avisadas na hora."
          : "Quando alguém publicar o que sobrou, o cartão aparece aqui na hora, sem recarregar a página." })
      ]));
    } else {
      alvo.replaceChildren(el("ul", { classe: "excedentes__lista",
        "aria-label": lista.length + (lista.length === 1 ? " excedente disponível" : " excedentes disponíveis") },
        lista.map(cartaoExcedente)));
    }
    alvo.setAttribute("aria-busy", "false");
  }

  function carregarExcedentes(aoVivo) {
    return fetch("/reconecta/excedentes?limite=8", { headers: { "Accept": "application/json" }, credentials: "same-origin" })
      .then(function (r) {
        if (!r.ok) throw new Error("HTTP " + r.status);
        var total = Number(r.headers.get("X-Total-Count"));
        return r.json().then(function (lista) {
          lista = Array.isArray(lista) ? lista : [];
          desenharExcedentes(lista, isFinite(total) && total >= lista.length ? total : lista.length);
        });
      })
      .catch(function () {
        if (aoVivo === true) return;
        var alvo = $("excedentes-conteudo");
        var tentar = el("button", { type: "button", classe: "btn btn--secundario btn--pequeno", texto: "Tentar novamente" });
        tentar.addEventListener("click", carregarExcedentes);
        alvo.replaceChildren(el("div", { classe: "aviso falha", role: "alert" }, [
          el("p", { texto: "Não conseguimos carregar os excedentes agora." }), tentar]));
        alvo.setAttribute("aria-busy", "false");
      });
  }

  // contagem regressiva: atualiza o texto a cada 30 s e tira da lista o que venceu
  setInterval(function () {
    var venceu = false;
    document.querySelectorAll(".excedente__falta[data-ate]").forEach(function (no) {
      var d = data(no.getAttribute("data-ate"));
      if (d && d.getTime() <= Date.now()) venceu = true;
      else no.textContent = faltaTexto(no.getAttribute("data-ate"));
    });
    if (venceu) carregarExcedentes(true);
  }, 30000);

  /* ---------- tempo real ---------- */

  var relogios = {};
  function agendar(chave, funcao) {
    clearTimeout(relogios[chave]);
    relogios[chave] = setTimeout(funcao, 250);   // junta eventos que chegam juntos
  }

  document.addEventListener("reconecta:evento", function (e) {
    var tipo = (e.detail && e.detail.tipo) || "";
    if (tipo === "pedido.publicado" || tipo.indexOf("doacao.") === 0) agendar("pedidos", function () { carregar(true); });
    if (tipo.indexOf("excedente.") === 0) agendar("excedentes", function () { carregarExcedentes(true); });
  });

  /* "Ao vivo" quando o fluxo está aberto; na consulta periódica, diz o intervalo */
  function mostrarEstado() {
    var estado = document.documentElement.getAttribute("data-tempo-real");
    document.querySelectorAll("[data-ao-vivo]").forEach(function (no) {
      no.hidden = estado !== "sse" && estado !== "consulta";
      no.textContent = estado === "sse" ? "Ao vivo" : "Atualiza a cada 10 s";
      no.classList.toggle("ao-vivo--consulta", estado === "consulta");
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
        href: "/painel#publicar-excedente" }, [usuarioAtual && usuarioAtual.tipo === "doador" ? "Publicar para as ONGs retirarem" : "Publicar como excedente"]);
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

  /* ---------- CTA conforme a sessão ---------- */

  var usuarioAtual = null;
  /* Quem já entrou nunca é mandado para o cadastro: cada convite vira a ação do perfil. */
  function ajustarConvites() {
    var vazio = document.querySelector("#ultima-doacao-corpo .ultima__vazia");
    if (vazio) vazio.replaceChildren.apply(vazio, conviteSemPedido());
    var ong = !!usuarioAtual && ehOng();
    var acoes = {
      empresa: usuarioAtual && usuarioAtual.tipo === "empresa" ? ["/painel", "Abrir o painel"] : null,
      doador: usuarioAtual && usuarioAtual.tipo === "doador" ? ["/?assistente=1", "Doar agora"] : null,
      ong: ong ? ["/painel#publicar", "Publicar pedido"] : null
    };
    document.querySelectorAll("[data-sessao]").forEach(function (a) {
      var tipo = a.getAttribute("data-sessao");
      if (!a.dataset.original) a.dataset.original = a.innerHTML;
      if (!usuarioAtual) { a.hidden = false; a.href = "/cadastro"; a.innerHTML = a.dataset.original; return; }
      var acao = tipo === "cta" ? (ong ? ["/painel#publicar", "Publicar pedido"] : null) : acoes[tipo];
      a.hidden = !acao;
      if (acao) { a.href = acao[0]; a.textContent = acao[1]; }
    });
    // o convite final é para ONGs: quem não é ONG e já entrou não precisa dele
    $("cta-final").hidden = !!usuarioAtual && !ong;
  }

  var abriuPeloEndereco = false;
  document.addEventListener("reconecta:sessao", function (e) {
    var u = e.detail && e.detail.usuario;
    var mudouPerfil = !!excedentesAtuais && JSON.stringify((u && u.perfis) || []) !== JSON.stringify((usuarioAtual && usuarioAtual.perfis) || []);
    usuarioAtual = u;
    ajustarConvites();
    // empresa usa o endereço do cadastro; pessoa física pode informar o CEP
    $("assistente-cep-campo").hidden = !!(u && u.tipo === "empresa");
    var sec = $("hero-secundario");
    if (sec) {
      if (u && u.tipo === "empresa") { sec.href = "/painel#publicar"; sec.textContent = "Preciso de doações · publicar pedido"; }
      else if (u) { sec.href = "#doacoes"; sec.textContent = "Ver os pedidos abertos"; }
      else { sec.href = "/cadastro"; sec.textContent = "Preciso de doações · publicar pedido"; }
    }
    // os cartões de excedente dizem "Ver e reservar" só para ONG
    if (excedentesAtuais && (mudouPerfil || u)) desenharExcedentes(excedentesAtuais, excedentesTotal);
    // o estado vazio dos pedidos depende de quem está vendo (visitante, pessoa, empresa ou ONG)
    if (categoriasVazio && !document.querySelector("#doacoes-conteudo .carrossel")) montarVazio(categoriasVazio);
    // volta do login com ?assistente=1: reabre com o texto guardado
    if (!abriuPeloEndereco && /[?&]assistente=1(&|$)/.test(location.search)) {
      abriuPeloEndereco = true;
      abrirAssistente();
    }
  });

  carregar();
  carregarExcedentes();
})();
