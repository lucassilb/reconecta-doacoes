/* ReConecta — dashboard (/dashboard): indicadores, gráficos (Chart.js), alertas, tabelas
   e o resumo com IA (modelo local gratuito; o servidor monta os números, o cliente não envia dados). */
(function () {
  "use strict";
  function $(id) { return document.getElementById(id); }

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
  function requisitar(url, opcoes) {
    opcoes = opcoes || {};
    return fetch(url, { method: opcoes.method || "GET", credentials: "same-origin", headers: { "Accept": "application/json" } })
      .then(function (r) {
        return r.text().then(function (t) {
          var c = null;
          try { c = t ? JSON.parse(t) : null; } catch (e) { c = null; }
          return { status: r.status, ok: r.ok, corpo: c == null ? {} : c };
        });
      });
  }

  var inteiro = new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 0 });
  var decimal = new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 1 });
  function nome(n) { var R = window.ReConecta; return R && R.nomeTitulo ? R.nomeTitulo(n) : String(n || ""); }
  function local(mu) { if (!mu) return ""; var p = String(mu).split("/"); return nome(p[0]) + (p[1] ? "/" + p[1].toUpperCase() : ""); }
  function data(iso) { if (!iso) return null; var d = new Date(String(iso).length <= 10 ? iso + "T12:00:00" : iso); return isNaN(d) ? null : d; }
  function dataHora(iso) { var d = data(iso); return d ? d.toLocaleString("pt-BR", { day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit" }) : ""; }
  function diaMes(iso) { var d = data(iso); return d ? d.toLocaleDateString("pt-BR", { day: "2-digit", month: "2-digit" }) : ""; }
  var PLURAL = { unidade: "unidades", pacote: "pacotes", caixa: "caixas" };
  function qtd(n, u) { var v = Number(n) || 0; return decimal.format(v) + " " + (PLURAL[u] && v !== 1 ? PLURAL[u] : (u || "")); }

  /* tabela simples e acessível */
  function tabela(legenda, cabecalhos, linhas, numericas) {
    numericas = numericas || [];
    if (!linhas.length) return el("p", { classe: "dash-vazio", texto: "Sem dados ainda." });
    return el("table", { classe: "tabela" }, [
      el("caption", { classe: "sr-only", texto: legenda }),
      el("thead", null, [el("tr", null, cabecalhos.map(function (h, i) { return el("th", { scope: "col", classe: numericas.indexOf(i) !== -1 ? "num" : null, texto: h }); }))]),
      el("tbody", null, linhas.map(function (l) {
        return el("tr", null, l.map(function (v, i) { return el(i === 0 ? "th" : "td", { scope: i === 0 ? "row" : null, classe: numericas.indexOf(i) !== -1 ? "num" : null }, [v]); }));
      }))
    ]);
  }

  /* ---------- indicadores ---------- */

  function preencherIndicadores(ind) {
    var lista = $("indicadores");
    Object.keys(ind).forEach(function (k) {
      var item = lista.querySelector('[data-ind="' + k + '"] .indicador__valor');
      if (!item) return;
      item.textContent = k === "percentual_atendimento" ? decimal.format(Number(ind[k]) || 0) + "%" : inteiro.format(Number(ind[k]) || 0);
    });
    var pct = Math.max(0, Math.min(100, Number(ind.percentual_atendimento) || 0));
    lista.querySelector(".indicador__barra span").style.width = pct + "%";
    // itens_pedidos = itens nos pedidos abertos; itens_atendidos = itens com a meta completa
    var ped = Number(ind.itens_pedidos) || 0, at = Number(ind.itens_atendidos) || 0;
    $("ind-itens").textContent = inteiro.format(at) + " de " + inteiro.format(ped) + (ped === 1 ? " item pedido" : " itens pedidos") + " com a meta completa";
    lista.setAttribute("aria-busy", "false");
  }

  /* ---------- gráficos ---------- */

  var graficos = {};
  var COR = { verde: "#4A8326", verdeClaro: "#A9D486", trilho: "#D9E6CB", tinta: "#5E6270", linha: "#E2E3EC" };

  function grafico(id, config) {
    if (typeof window.Chart !== "function") return null; // CDN indisponível: as tabelas continuam valendo
    if (graficos[id]) graficos[id].destroy();
    graficos[id] = new window.Chart($(id), config);
    return graficos[id];
  }
  function opcoesBase() {
    return {
      responsive: true, maintainAspectRatio: false, animation: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? false : { duration: 500 },
      plugins: { legend: { labels: { color: COR.tinta, font: { family: "Manrope", size: 12 }, boxWidth: 14 } },
                 tooltip: { titleFont: { family: "Manrope" }, bodyFont: { family: "Manrope" } } },
      scales: {
        x: { ticks: { color: COR.tinta, font: { family: "Manrope", size: 11 } }, grid: { display: false } },
        y: { beginAtZero: true, ticks: { color: COR.tinta, font: { family: "Manrope", size: 11 }, precision: 0 }, grid: { color: COR.linha } }
      }
    };
  }

  function graficoCategorias(lista) {
    var vazio = !lista.length;
    $("g-categoria").hidden = vazio;
    $("g-categoria-vazio").hidden = !vazio;
    $("t-categoria").replaceChildren(tabela("Pedido e recebido por categoria", ["Categoria", "Pedido", "Recebido"],
      lista.map(function (c) { return [c.categoria, decimal.format(c.pedido), decimal.format(c.recebido)]; }), [1, 2]));
    if (vazio) return;
    grafico("g-categoria", {
      type: "bar",
      data: {
        labels: lista.map(function (c) { return c.categoria; }),
        datasets: [
          { label: "Pedido", data: lista.map(function (c) { return c.pedido; }), backgroundColor: COR.trilho, borderRadius: 6 },
          { label: "Recebido", data: lista.map(function (c) { return c.recebido; }), backgroundColor: COR.verde, borderRadius: 6 }
        ]
      },
      options: opcoesBase()
    });
  }

  function graficoDias(lista) {
    $("t-dia").replaceChildren(tabela("Doações por dia", ["Dia", "Doações"],
      lista.filter(function (d) { return d.doacoes > 0; }).map(function (d) { return [diaMes(d.data), inteiro.format(d.doacoes)]; }), [1]));
    var op = opcoesBase();
    op.plugins.legend.display = false;
    op.scales.x.ticks.maxTicksLimit = 8;
    grafico("g-dia", {
      type: "line",
      data: {
        labels: lista.map(function (d) { return diaMes(d.data); }),
        datasets: [{ label: "Doações", data: lista.map(function (d) { return d.doacoes; }), borderColor: COR.verde, backgroundColor: "rgba(74,131,38,.12)",
                     fill: true, tension: .3, pointRadius: 2, pointHoverRadius: 5 }]
      },
      options: op
    });
  }

  /* ---------- alertas e tabelas ---------- */

  var ALERTA = {
    PRAZO_PROXIMO: ["Prazo perto do fim", "alerta--prazo"],
    SEM_DOACOES: ["Sem doações", "alerta--sem"],
    QUASE_COMPLETO: ["Quase completo", "alerta--quase"],
    META_ATINGIDA: ["Meta atingida", "alerta--meta"]
  };
  function preencherAlertas(lista) {
    var alvo = $("alertas");
    alvo.replaceChildren();
    if (!lista.length) { alvo.appendChild(el("li", { classe: "alerta alerta--nenhum", texto: "Nenhum alerta agora. Os pedidos abertos estão dentro do prazo." })); return; }
    lista.forEach(function (a) {
      var t = ALERTA[a.tipo] || ["Aviso", ""];
      alvo.appendChild(el("li", { classe: "alerta " + t[1] }, [
        el("span", { classe: "alerta__tipo", texto: t[0] }),
        el("span", { classe: "alerta__msg", texto: a.mensagem }),
        a.pedido_id ? el("a", { classe: "alerta__link", href: "/doacoes/" + a.pedido_id, texto: "Ver pedido" }) : null
      ]));
    });
  }

  function preencherTabelas(dados) {
    $("top-empresas").replaceChildren(tabela("Empresas com mais doações recebidas", ["Empresa", "Cidade", "Pedidos", "Doações recebidas"],
      (dados.top_empresas || []).map(function (e) { return [nome(e.nome), local(e.municipio_uf), inteiro.format(e.pedidos), inteiro.format(e.doacoes_recebidas)]; }), [2, 3]));
    $("ultimas").replaceChildren(tabela("Últimas doações", ["Quando", "Item", "Quantidade", "Para", "Quem doou"],
      (dados.ultimas_doacoes || []).map(function (d) {
        return [dataHora(d.data), d.item, qtd(d.quantidade, d.unidade_medida), nome(d.empresa), d.origem === "empresa" ? "Empresa" : "Pessoa (CPF)"];
      }), [2]));
  }

  /* ---------- carga ---------- */

  function carregar() {
    var btn = $("btn-atualizar");
    btn.disabled = true;
    $("dash-erro").hidden = true;
    return requisitar("/reconecta/dashboard").then(function (r) {
      if (!r.ok) throw new Error("HTTP " + r.status);
      var d = r.corpo;
      preencherIndicadores(d.indicadores || {});
      graficoCategorias(d.por_categoria || []);
      graficoDias(d.por_dia || []);
      preencherAlertas(d.alertas || []);
      preencherTabelas(d);
      $("dash-gerado").textContent = "Dados de " + dataHora(d.gerado_em);
    }).catch(function () {
      var e = $("dash-erro");
      e.replaceChildren(el("p", { classe: "aviso__titulo", texto: "Não conseguimos carregar os indicadores" }), el("p", { texto: "Verifique sua conexão e tente atualizar." }));
      e.hidden = false;
      $("dash-gerado").textContent = "";
    }).then(function () { btn.disabled = false; });
  }

  /* ---------- resumo com IA ---------- */

  function gerarResumo() {
    var btn = $("btn-resumo"), alvo = $("ia-resultado");
    btn.disabled = true; btn.classList.add("is-carregando");
    alvo.hidden = false;
    alvo.setAttribute("aria-busy", "true");
    alvo.replaceChildren(el("p", { classe: "dash-ia__carregando", texto: "Gerando o resumo… o modelo local pode levar alguns segundos." }));
    fetch("/reconecta/ia/resumo-dashboard", { method: "POST", credentials: "same-origin", headers: { "Accept": "application/json", "Content-Type": "application/json" }, body: "{}" })
      .then(function (r) { return r.json().catch(function () { return {}; }).then(function (c) { return { status: r.status, ok: r.ok, corpo: c }; }); })
      .then(function (r) {
        var c = r.corpo || {};
        if (r.status === 429) { alvo.replaceChildren(el("p", { classe: "aviso", texto: c.mensagem || "Muitos pedidos de resumo seguidos. Aguarde um pouco e tente de novo." })); return; }
        if (!r.ok) throw new Error("HTTP " + r.status);
        var llm = c.fonte === "llm";
        // a resposta é tratada como texto (textContent), nunca como HTML
        alvo.replaceChildren(
          el("p", { classe: "selo " + (llm ? "selo--ia" : "selo--regras"), texto: llm ? "Gerado pelo modelo local gratuito " + (c.modelo || "") : "Resumo automático (IA indisponível no momento)" }),
          el("p", { classe: "dash-ia__texto", texto: c.resumo || "" }),
          (c.recomendacoes && c.recomendacoes.length) ? el("div", null, [
            el("h3", { classe: "dash-ia__rec-titulo", texto: "Recomendações" }),
            el("ul", { classe: "dash-ia__rec" }, c.recomendacoes.map(function (t) { return el("li", { texto: t }); }))
          ]) : null,
          el("p", { classe: "dash-ia__nota", texto: (c.gerado_em ? "Gerado em " + dataHora(c.gerado_em) + ". " : "") + (llm ? "Texto produzido por IA a partir dos números desta página; confira os dados antes de decidir." : "Texto montado por regras fixas a partir dos números desta página.") })
        );
      })
      .catch(function () {
        alvo.replaceChildren(el("p", { classe: "aviso aviso--erro", texto: "Não foi possível gerar o resumo agora. Tente novamente em instantes." }));
      })
      .then(function () { btn.disabled = false; btn.classList.remove("is-carregando"); alvo.setAttribute("aria-busy", "false"); });
  }

  $("btn-atualizar").addEventListener("click", carregar);
  $("btn-resumo").addEventListener("click", gerarResumo);
  carregar();
})();
