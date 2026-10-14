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
  function data(iso) { return window.ReConecta.dataBrasilia(iso); }
  function dataHora(iso) { var d = data(iso); return d ? d.toLocaleString("pt-BR", { timeZone: window.ReConecta.fuso, day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit" }) : ""; }
  function diaMes(iso) { var d = data(iso); return d ? d.toLocaleDateString("pt-BR", { timeZone: window.ReConecta.fuso, day: "2-digit", month: "2-digit" }) : ""; }
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
      if (k === "tempo_medio_reserva_min") item.textContent = ind[k] == null ? "—" : Number(ind[k]) < 1 ? "< 1 min" : decimal.format(Number(ind[k])) + " min";
      else item.textContent = k === "percentual_atendimento" ? decimal.format(Number(ind[k]) || 0) + "%" : inteiro.format(Number(ind[k]) || 0);
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
    $("t-dia").replaceChildren(tabela("Doações e resgates por dia", ["Dia", "Doações aceitas", "Excedentes retirados"],
      lista.filter(function (d) { return d.doacoes > 0 || d.excedentes_resgatados > 0; })
        .map(function (d) { return [diaMes(d.data), inteiro.format(d.doacoes), inteiro.format(d.excedentes_resgatados)]; }), [1, 2]));
    var op = opcoesBase();
    op.scales.x.ticks.maxTicksLimit = 8;
    grafico("g-dia", {
      type: "line",
      data: {
        labels: lista.map(function (d) { return diaMes(d.data); }),
        datasets: [
          { label: "Doações aceitas", data: lista.map(function (d) { return d.doacoes; }), borderColor: COR.verde, backgroundColor: "rgba(74,131,38,.12)",
            fill: true, tension: .3, pointRadius: 2, pointHoverRadius: 5 },
          { label: "Excedentes retirados", data: lista.map(function (d) { return d.excedentes_resgatados; }), borderColor: "#B17413",
            tension: .3, pointRadius: 2, pointHoverRadius: 5 }
        ]
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
    $("top-empresas").replaceChildren(tabela("Organizações com mais doações recebidas", ["Organização", "Cidade", "Pedidos", "Doações recebidas"],
      (dados.top_empresas || []).map(function (e) { return [nome(e.nome), local(e.municipio_uf), inteiro.format(e.pedidos), inteiro.format(e.doacoes_recebidas)]; }), [2, 3]));
    $("ultimas").replaceChildren(tabela("Últimas doações", ["Quando", "Item", "Quantidade", "Para", "Quem doou"],
      (dados.ultimas_doacoes || []).map(function (d) {
        return [dataHora(d.data), d.item, qtd(d.quantidade, d.unidade_medida), nome(d.empresa), d.origem === "empresa" ? "Empresa" : "Pessoa (CPF)"];
      }), [2]));
  }

  /* ---------- impacto e segurança ---------- */

  function duracao(min) {
    if (min == null) return "Sem amostras";
    return min >= 60 ? decimal.format(min / 60) + " h" : decimal.format(min) + " min";
  }
  function pintarImpacto(d) {
    var peso = d.peso || {}, refeicoes = d.refeicoes || {}, match = d.match || {};
    $("kg-medido").textContent = decimal.format(peso.kg_medido || 0) + " kg";
    $("kg-estimado").textContent = decimal.format(peso.kg_estimado || 0) + " kg";
    $("refeicoes-total").textContent = inteiro.format((Number(peso.kg_medido || 0) + Number(peso.kg_estimado || 0)) / (refeicoes.kg_por_refeicao || .5));
    $("refeicoes-premissa").textContent = refeicoes.premissa || "Premissa não informada";
    $("match-total").textContent = duracao(match.combinado_min);
    $("match-detalhe").textContent = "Pedido → doação: " + duracao(match.pedido_min) + " (" + (match.pedido_amostras || 0) + "); oferta → reserva: " + duracao(match.excedente_min) + " (" + (match.excedente_amostras || 0) + ").";
    $("sem-conversao").textContent = peso.itens_sem_conversao ? peso.itens_sem_conversao + " item(ns) sem conversão ficaram fora do cálculo." : "Todos os itens confirmados tinham conversão.";
    graficoRegiao(refeicoes.por_regiao || []);
    mapaUF(refeicoes.por_uf || []);
    mapaHoras(d.calor_doacoes || {});
    graficoAcuracia(d.ia || {});
  }

  function graficoRegiao(lista) {
    $("t-regiao").replaceChildren(tabela("Refeições potenciais por região", ["Região", "Refeições potenciais", "Kg físicos", "Kg estimados"],
      lista.map(function (r) { return [r.regiao, inteiro.format(r.refeicoes_estimadas), decimal.format(r.kg_medido), decimal.format(r.kg_estimado)]; }), [1, 2, 3]));
    if (!lista.length) return;
    var op = opcoesBase();
    op.indexAxis = "y";
    grafico("g-regiao", { type: "bar", data: { labels: lista.map(function (r) { return r.regiao; }),
      datasets: [{ label: "Refeições potenciais", data: lista.map(function (r) { return r.refeicoes_estimadas; }), backgroundColor: COR.verde, borderRadius: 5 }] }, options: op });
  }

  function graficoAcuracia(ia) {
    var m = ia.metricas, l = ia.limiares;
    if (!m || !l) { $("ia-medicao").textContent = "Avaliação indisponível."; return; }
    $("ia-medicao").textContent = "Avaliação de " + (m.data || "data não informada") + "; versão " + (m.versao || "—") + ". Valores do conjunto de teste, não taxa de acerto em produção.";
    var chaves = ["acuracia_classificador", "acuracia_top1", "acuracia_top3", "taxa_sem_sugestao_correta"];
    var rotulos = ["Classificador", "Destino top-1", "Destino top-3", "Sem sugestão correta"];
    $("ia-metricas").replaceChildren.apply($("ia-metricas"), chaves.map(function (k, i) {
      return el("p", { texto: rotulos[i] + ": " + decimal.format(100 * Number(m[k] || 0)) + "% · limiar " + decimal.format(100 * Number(l[k] || 0)) + "%" });
    }));
    var op = opcoesBase(); op.indexAxis = "y"; op.scales.x.max = 100;
    grafico("g-acuracia", { type: "bar", data: { labels: rotulos, datasets: [
      { label: "Medido (%)", data: chaves.map(function (k) { return 100 * Number(m[k] || 0); }), backgroundColor: COR.verde, borderRadius: 5 },
      { label: "Limiar (%)", data: chaves.map(function (k) { return 100 * Number(l[k] || 0); }), backgroundColor: COR.trilho, borderRadius: 5 }
    ] }, options: op });
  }

  var POSICOES_UF = { RR:[2,0], AP:[5,0], AM:[2,1], PA:[4,1], AC:[1,2], RO:[2,2], TO:[5,2], MA:[6,1], PI:[7,2], CE:[8,1], RN:[10,1], PB:[10,2], PE:[9,3], AL:[10,4], SE:[9,4], BA:[7,4], MT:[4,3], GO:[5,4], DF:[6,4], MS:[4,5], MG:[7,5], ES:[9,5], SP:[6,6], RJ:[8,6], PR:[5,7], SC:[6,8], RS:[5,9] };
  function mapaUF(lista) {
    var porUf = {};
    lista.forEach(function (r) { porUf[r.uf] = r; });
    var maximo = Math.max.apply(null, lista.map(function (r) { return r.refeicoes_estimadas; }).concat([1]));
    var svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    svg.setAttribute("viewBox", "0 0 660 510");
    svg.setAttribute("aria-hidden", "true");
    Object.keys(POSICOES_UF).forEach(function (uf) {
      var pos = POSICOES_UF[uf], valor = (porUf[uf] || {}).refeicoes_estimadas || 0;
      var grupo = document.createElementNS(svg.namespaceURI, "g");
      var ret = document.createElementNS(svg.namespaceURI, "rect");
      ret.setAttribute("x", 12 + pos[0] * 58); ret.setAttribute("y", 12 + pos[1] * 48);
      ret.setAttribute("width", 53); ret.setAttribute("height", 43); ret.setAttribute("rx", 7);
      ret.setAttribute("fill", valor ? "hsl(98 47% " + (85 - 56 * valor / maximo) + "%)" : "#e8e9e3");
      var rotulo = document.createElementNS(svg.namespaceURI, "text");
      rotulo.setAttribute("x", 38 + pos[0] * 58); rotulo.setAttribute("y", 39 + pos[1] * 48);
      rotulo.setAttribute("text-anchor", "middle"); rotulo.setAttribute("font-size", "14");
      rotulo.setAttribute("font-weight", "700"); rotulo.setAttribute("fill", "#19351c");
      rotulo.textContent = uf;
      var titulo = document.createElementNS(svg.namespaceURI, "title");
      titulo.textContent = uf + ": " + inteiro.format(valor) + " refeições potenciais";
      grupo.append(ret, rotulo, titulo); svg.appendChild(grupo);
    });
    $("mapa-uf").replaceChildren(svg);
    $("t-uf").replaceChildren(tabela("Impacto por UF de destino", ["UF", "Refeições potenciais", "Kg físicos", "Kg estimados"],
      lista.map(function (r) { return [r.uf, inteiro.format(r.refeicoes_estimadas), decimal.format(r.kg_medido), decimal.format(r.kg_estimado)]; }), [1, 2, 3]));
  }

  function mapaHoras(calor) {
    var matriz = calor.valores || [], dias = calor.dias || [], alvo = $("mapa-horas");
    var maximo = Math.max.apply(null, matriz.flat().concat([1]));
    var nos = [el("span", { texto: "" })];
    for (var h = 0; h < 24; h++) nos.push(el("span", { texto: h % 3 === 0 ? String(h) : "" }));
    dias.forEach(function (dia, i) {
      nos.push(el("span", { texto: dia }));
      for (var hora = 0; hora < 24; hora++) {
        var n = (matriz[i] || [])[hora] || 0;
        nos.push(el("span", { classe: "celula", title: dia + " " + hora + "h: " + n + " doações", style: "background:hsl(98 47% " + (n ? 85 - 56 * n / maximo : 94) + "%)" }));
      }
    });
    alvo.replaceChildren.apply(alvo, nos);
    $("t-horas").replaceChildren(tabela("Doações aceitas por dia e hora de Brasília", ["Dia", "Total", "Hora de pico"],
      dias.map(function (dia, i) { var valores = matriz[i] || [], pico = Math.max.apply(null, valores.concat([0])); return [dia, inteiro.format(valores.reduce(function (a, b) { return a + b; }, 0)), pico ? valores.indexOf(pico) + "h (" + pico + ")" : "—"]; }), [1]));
  }

  function pintarSeguranca(d) {
    var sast = d.sast, alvo = $("sast-cards");
    if (!sast) { alvo.textContent = "Resumo SAST indisponível."; return; }
    var rotulos = { bandit: "Bandit · código", "trivy-fs": "Trivy · arquivos", "trivy-config": "Trivy · configuração", "trivy-image": "Trivy · imagem" };
    alvo.replaceChildren.apply(alvo, Object.keys(rotulos).map(function (nome) {
      var r = (sast.ferramentas || {})[nome] || {}, sev = r.severidades || {};
      var achados = Object.keys(sev).reduce(function (n, k) { return n + Number(sev[k] || 0); }, 0) + Number(r.segredos || 0) + Number(r.configuracoes || 0);
      return el("div", { classe: "sast-card" + (Number(sev.HIGH || 0) || Number(sev.CRITICAL || 0) ? " sast-card--alerta" : "") }, [
        el("b", { texto: rotulos[nome] }), el("strong", { texto: r.disponivel ? inteiro.format(achados) + " achados" : "Indisponível" }),
        el("small", { texto: "Alta " + (sev.HIGH || 0) + " · crítica " + (sev.CRITICAL || 0) + " · varredura " + (r.varredura_em ? String(r.varredura_em).slice(0, 10) : "sem data") })
      ]);
    }));
    var stride = sast.stride || {};
    var correcoes = sast.correcoes_documentadas || {};
    $("stride-resumo").textContent = "Correções documentadas: " + (correcoes.cves_corrigidas || 0) + " CVEs de dependências e " + (correcoes.bandit_b104_corrigido ? "1 achado Bandit B104" : "nenhum B104 confirmado") + ". " + (correcoes.bandit_b608_justificado ? "Os 4 B608 foram justificados; não contam como CVEs corrigidas. " : "") + "STRIDE: " + (stride.mitigados || 0) + " riscos marcados mitigados; " + (stride.residuais || 0) + " com risco residual. Os achados HIGH da imagem Debian, na data indicada acima, não foram contados como mitigados.";
    var c = d.controles || {};
    $("seg-controles").replaceChildren(
      el("p", { texto: "Cabeçalhos ativos: " + (c.cabecalhos || []).join(", ") + ". HSTS " + (c.hsts_condicional ? "ativo em HTTPS" : "condicionado a COOKIE_SEGURO=1") + "." }),
      el("p", { texto: "Cotas: " + (c.cotas || "não informadas") }),
      el("p", { texto: "Falhas de login: " + (c.falhas_login || "não medidas") }),
      el("p", { texto: "Bloqueios de login: " + (c.bloqueios_login || "não medidos") })
    );
  }

  function carregarAnalise() {
    return requisitar("/reconecta/dashboard/impacto").then(function (r) {
      if (!r.ok) throw new Error("HTTP " + r.status);
      pintarImpacto(r.corpo);
    }).catch(function () { $("kg-medido").textContent = "Indisponível"; });
  }
  function carregarSeguranca() {
    return requisitar("/reconecta/dashboard/seguranca").then(function (r) {
      if (!r.ok) throw new Error("HTTP " + r.status);
      pintarSeguranca(r.corpo);
    }).catch(function () { $("sast-cards").textContent = "Indicadores de segurança indisponíveis."; });
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
      carregarAnalise();
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
  var atualizacaoPendente;
  document.addEventListener("reconecta:evento", function (evento) {
    if (!evento.detail || !/^(pedido\.|doacao\.|excedente\.)/.test(evento.detail.tipo)) return;
    clearTimeout(atualizacaoPendente);
    atualizacaoPendente = setTimeout(carregar, 250);
  });
  document.addEventListener("visibilitychange", function () {
    if (!document.hidden) carregar();
  });
  carregar();
  carregarSeguranca();
})();
