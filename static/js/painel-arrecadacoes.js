/* ReConecta — painel: ações de arrecadação (empresa cria, encerra e vê o que recebeu)
   e contribuições feitas (empresa e doador). Doador não vê o formulário de criar ação. */
(function () {
  "use strict";
  var R = window.RCArrecadacao, el = R.el;
  function $(id) { return document.getElementById(id); }

  var usuario = null;

  /* ---------- avisos e erros de campo ---------- */

  function aviso(caixa, titulo, texto, tipo) {
    caixa.className = "aviso" + (tipo ? " aviso--" + tipo : "") + " form-acao__largo";
    caixa.replaceChildren(el("p", { classe: "aviso__titulo", texto: titulo }), texto ? el("p", { texto: texto }) : null);
    caixa.hidden = false;
  }
  var CAMPOS_ACAO = { titulo: "a-titulo", descricao: "a-descricao", categorias: "a-categorias", meta_descricao: "a-meta", entrega_endereco: "a-entrega", data_inicio: "a-inicio", data_fim: "a-fim" };
  function erro(campo, msg) {
    var id = CAMPOS_ACAO[campo]; if (!id) return null;
    var input = $(id), p = $(id + "-erro");
    if (msg) input.setAttribute("aria-invalid", "true"); else input.removeAttribute("aria-invalid");
    if (p) p.textContent = msg || "";
    return id === "a-categorias" ? input.querySelector("input") : input;
  }
  function limpar() { Object.keys(CAMPOS_ACAO).forEach(function (c) { erro(c, ""); }); $("aviso-acao").hidden = true; }

  /* ---------- criar ação ---------- */

  var CATEGORIAS = ["Hortifrúti", "Padaria", "Laticínios", "Carnes e peixes", "Grãos e cereais", "Refeições prontas", "Bebidas não alcoólicas", "Outros"];

  function montarCategorias(lista) {
    var alvo = $("a-categorias-lista");
    alvo.replaceChildren();
    lista.forEach(function (c, i) {
      var id = "a-cat-" + i;
      alvo.appendChild(el("label", { classe: "form-acao__cat acao__cat acao__cat--" + (R.IMG_CATEGORIA[c] || "outros"), "for": id }, [
        el("input", { type: "checkbox", id: id, value: c, name: "categorias" }), R.imgCategoria(c, 22), c
      ]));
    });
  }

  function abrirForm(abrir) {
    $("form-acao").hidden = !abrir;
    $("btn-nova-acao").setAttribute("aria-expanded", String(abrir));
    if (abrir) {
      limpar();
      if (!$("a-inicio").value) $("a-inicio").value = R.hojeISO();
      $("a-inicio").min = R.hojeISO(); $("a-fim").min = R.hojeISO();
      $("form-acao-t").focus();
    } else {
      $("btn-nova-acao").focus();
    }
  }

  function validarAcao() {
    var c = {};
    var titulo = $("a-titulo").value.trim(), desc = $("a-descricao").value.trim();
    if (titulo.length < 5 || titulo.length > 80) c.titulo = "O título precisa ter de 5 a 80 caracteres.";
    if (desc.length < 10 || desc.length > 500) c.descricao = "A descrição precisa ter de 10 a 500 caracteres.";
    if (!document.querySelectorAll('#a-categorias input:checked').length) c.categorias = "Escolha pelo menos uma categoria.";
    var ent = $("a-entrega").value.trim();
    if (ent && (ent.length < 5 || ent.length > 200)) c.entrega_endereco = "O endereço precisa ter de 5 a 200 caracteres.";
    var ini = $("a-inicio").value, fim = $("a-fim").value, hoje = R.hojeISO();
    if (!ini) c.data_inicio = "Informe quando a ação começa.";
    else if (ini < hoje) c.data_inicio = "A ação não pode começar no passado.";
    if (!fim) c.data_fim = "Informe quando a ação termina.";
    else if (ini && fim < ini) c.data_fim = "O fim não pode ser antes do começo.";
    return c;
  }

  function aplicar(campos) {
    var primeiro = null;
    Object.keys(campos).forEach(function (k) { var i = erro(k, campos[k]); if (i && !primeiro) primeiro = i; });
    if (primeiro) primeiro.focus();
  }

  function criar(e) {
    e.preventDefault();
    limpar();
    var c = validarAcao();
    if (Object.keys(c).length) { aplicar(c); return; }
    var corpo = {
      titulo: $("a-titulo").value.trim(),
      descricao: $("a-descricao").value.trim(),
      categorias: Array.prototype.map.call(document.querySelectorAll('#a-categorias input:checked'), function (i) { return i.value; }),
      meta_descricao: $("a-meta").value.trim() || null,
      data_inicio: $("a-inicio").value,
      data_fim: $("a-fim").value
    };
    var ent = $("a-entrega").value.trim();
    if (ent) corpo.entrega_endereco = ent;
    var btn = $("btn-criar-acao");
    btn.disabled = true; btn.classList.add("is-carregando");
    R.requisitar("/reconecta/arrecadacoes", { method: "POST", json: corpo }).then(function (r) {
      if (r.status === 201) {
        $("form-acao").reset();
        abrirForm(false);
        carregarAcoes();
        aviso($("aviso-lista-acoes") || $("aviso-acao"), "Ação criada", "Ela já aparece em Ações de arrecadação para quem quiser doar.", "ok");
        return;
      }
      if (r.status === 400 && r.corpo.campos) { aplicar(r.corpo.campos); return; }
      if (r.status === 401) { location.replace("/entrar?proximo=/painel"); return; }
      aviso($("aviso-acao"), "Não foi possível criar a ação", r.corpo.mensagem || "Tente novamente em alguns instantes.", "erro");
    }).catch(function () {
      aviso($("aviso-acao"), "Não conseguimos falar com o servidor", "Verifique sua conexão e tente de novo.", "erro");
    }).then(function () { btn.disabled = false; btn.classList.remove("is-carregando"); });
  }

  /* ---------- minhas ações ---------- */

  function quem(c) {
    if (c.quem) return R.nome(typeof c.quem === "string" ? c.quem : (c.quem.nome || ""));
    if (c.doador) return c.doador.nome || "Doador";
    if (c.empresa) return R.nome(c.empresa.nome);
    if (c.estabelecimento) return R.nome(c.estabelecimento.nome);
    return "";
  }
  function qtd(c) {
    var n = Number(c.quantidade);
    return (isNaN(n) ? c.quantidade : n.toLocaleString("pt-BR", { maximumFractionDigits: 2 })) + " " + (c.unidade_medida || "");
  }

  function itemContribuicaoRecebida(c) {
    return el("li", { classe: "recebida" }, [
      c.foto_url
        ? el("a", { classe: "recebida__foto", href: c.foto_url, target: "_blank", rel: "noopener" }, [
            el("img", { src: c.foto_url, alt: "Foto de " + c.alimento + " enviada por " + quem(c), width: "64", height: "64", loading: "lazy" })])
        : el("span", { classe: "recebida__foto recebida__foto--vazia", "aria-hidden": "true" }),
      el("div", { classe: "recebida__texto" }, [
        el("p", { classe: "recebida__alimento" }, [el("strong", { texto: c.alimento }), " · " + qtd(c)]),
        el("p", { classe: "recebida__meta", texto: [quem(c), c.validade ? "val. " + R.dataCurta(c.validade) : "", c.criado_em ? "enviada em " + R.dataCurta(c.criado_em) : ""].filter(Boolean).join(" · ") })
      ])
    ]);
  }

  function cartaoMinhaAcao(a) {
    var ativa = (a.status || "ATIVA") === "ATIVA";
    var recebidas = a.contribuicoes || [];
    var n = a.contribuicoes_aceitas != null ? Number(a.contribuicoes_aceitas) : recebidas.length;
    var art = el("article", { classe: "minha-acao" }, [
      el("div", { classe: "minha-acao__topo" }, [
        el("h3", { classe: "minha-acao__titulo" }, [el("a", { href: "/arrecadacoes/" + a.id, texto: a.titulo })]),
        el("span", { classe: "selo" + (ativa ? "" : " selo--cinza"), texto: ativa ? "Ativa" : "Encerrada" })
      ]),
      el("p", { classe: "minha-acao__meta", texto: R.dataCurta(a.data_inicio) + " a " + R.dataCurta(a.data_fim) + " · " + R.plural(n, "doação recebida", "doações recebidas") }),
      R.chipsCategorias(a.categorias)
    ]);
    if (recebidas.length) {
      art.appendChild(el("details", { classe: "minha-acao__recebidas", open: recebidas.length <= 3 }, [
        el("summary", { texto: "Doações recebidas (" + recebidas.length + ")" }),
        el("ul", null, recebidas.map(itemContribuicaoRecebida))
      ]));
    } else {
      art.appendChild(el("p", { classe: "minha-acao__vazia", texto: "Ainda não chegou nenhuma doação para esta ação." }));
    }
    if (ativa) {
      var acoes = el("div", { classe: "minha-acao__acoes", "aria-live": "polite" });
      var btn = el("button", { type: "button", classe: "btn btn--secundario btn--pequeno", texto: "Encerrar ação" });
      btn.addEventListener("click", function () {
        var sim = el("button", { type: "button", classe: "btn btn--perigo btn--pequeno", texto: "Sim, encerrar" });
        var nao = el("button", { type: "button", classe: "link-seta", texto: "Cancelar" });
        sim.addEventListener("click", function () {
          sim.disabled = true; nao.disabled = true;
          R.requisitar("/reconecta/arrecadacoes/" + a.id + "/encerrar", { method: "POST" }).then(function (r) {
            if (r.ok) { carregarAcoes(); return; }
            acoes.replaceChildren(el("p", { classe: "campo__erro", role: "alert", texto: r.corpo.mensagem || "Não foi possível encerrar." }), btn);
          }).catch(function () { acoes.replaceChildren(el("p", { classe: "campo__erro", role: "alert", texto: "Sem conexão com o servidor." }), btn); });
        });
        nao.addEventListener("click", function () { acoes.replaceChildren(btn); btn.focus(); });
        acoes.replaceChildren(el("span", { classe: "minha-acao__confirmar", role: "group", "aria-label": "Confirmar encerramento" },
          ["Encerrar? Ela deixa de receber doações. ", sim, nao]));
        nao.focus();
      });
      acoes.appendChild(btn);
      art.appendChild(acoes);
    }
    return art;
  }

  function carregarAcoes() {
    var alvo = $("lista-acoes");
    alvo.setAttribute("aria-busy", "true");
    R.requisitar("/reconecta/arrecadacoes/minhas").then(function (r) {
      if (r.status === 401) { location.replace("/entrar?proximo=/painel"); return; }
      var lista = r.ok && Array.isArray(r.corpo) ? r.corpo : [];
      alvo.replaceChildren(el("div", { id: "aviso-lista-acoes", classe: "aviso", hidden: true }));
      if (!lista.length) {
        alvo.appendChild(el("p", { classe: "doacoes__vazio", texto: "Você ainda não criou nenhuma ação. Use “Nova ação” para começar." }));
        return;
      }
      lista.forEach(function (a) { alvo.appendChild(cartaoMinhaAcao(a)); });
    }).catch(function () {
      alvo.replaceChildren(el("p", { classe: "doacoes__vazio", texto: "Não foi possível carregar suas ações. Recarregue a página." }));
    }).then(function () { alvo.setAttribute("aria-busy", "false"); });
  }

  /* ---------- minhas contribuições ---------- */

  function cartaoContribuicao(c) {
    var acao = c.arrecadacao || c.acao || {};
    var ent = c.entrega || {};
    var STATUS = { ACEITA: ["Aceita", ""], ENTREGUE: ["Entregue", "selo--cinza"], CANCELADA: ["Cancelada", "selo--erro"] };
    var st = STATUS[c.status] || STATUS.ACEITA;
    return el("article", { classe: "contribuicao" }, [
      c.foto_url ? el("img", { classe: "contribuicao__foto", src: c.foto_url, alt: "Foto enviada de " + c.alimento, width: "64", height: "64", loading: "lazy" }) : null,
      el("div", { classe: "contribuicao__texto" }, [
        el("div", { classe: "minha-acao__topo" }, [
          el("p", { classe: "recebida__alimento" }, [el("strong", { texto: c.alimento }), " · " + qtd(c)]),
          el("span", { classe: "selo " + st[1], texto: st[0] })
        ]),
        el("p", { classe: "recebida__meta" }, ["Para ", acao.id ? el("a", { href: "/arrecadacoes/" + acao.id, texto: acao.titulo || "ação" }) : (acao.titulo || "ação"),
          acao.empresa && acao.empresa.nome ? " · " + R.nome(acao.empresa.nome) : ""]),
        ent.endereco ? el("p", { classe: "contribuicao__entrega" }, [el("strong", { texto: "Entregar em: " }), ent.endereco]) : null,
        ent.data_fim || acao.data_fim ? el("p", { classe: "recebida__meta", texto: "Até " + R.dataLonga(ent.data_fim || acao.data_fim) }) : null
      ])
    ]);
  }

  function carregarContribuicoes() {
    var alvo = $("lista-contribuicoes");
    alvo.setAttribute("aria-busy", "true");
    R.requisitar("/reconecta/arrecadacoes/minhas-contribuicoes").then(function (r) {
      var lista = r.ok && Array.isArray(r.corpo) ? r.corpo : [];
      alvo.replaceChildren();
      if (!lista.length) {
        alvo.appendChild(el("p", { classe: "doacoes__vazio" }, ["Você ainda não doou para nenhuma ação. ", el("a", { href: "/arrecadacoes", texto: "Veja as ações abertas" }), "."]));
        return;
      }
      lista.forEach(function (c) { alvo.appendChild(cartaoContribuicao(c)); });
    }).catch(function () {
      alvo.replaceChildren(el("p", { classe: "doacoes__vazio", texto: "Não foi possível carregar suas contribuições." }));
    }).then(function () { alvo.setAttribute("aria-busy", "false"); });
  }

  /* ---------- início ---------- */

  document.addEventListener("reconecta:sessao", function (e) {
    usuario = e.detail && e.detail.usuario;
    if (!usuario) return; // painel.js manda para /entrar
    $("bloco-contribuicoes").hidden = false;
    carregarContribuicoes();
    if (usuario.tipo === "empresa") {
      $("bloco-acoes").hidden = false;
      R.requisitar("/reconecta/publico/opcoes").then(function (r) {
        montarCategorias(r.ok && r.corpo.categorias ? r.corpo.categorias : CATEGORIAS);
      }, function () { montarCategorias(CATEGORIAS); });
      carregarAcoes();
      if (location.hash === "#acoes") setTimeout(function () { $("acoes").scrollIntoView({ block: "start" }); }, 300);
    }
    if (location.hash === "#contribuicoes") setTimeout(function () { $("contribuicoes").scrollIntoView({ block: "start" }); }, 300);
  }, { once: true });

  $("btn-nova-acao").addEventListener("click", function () { abrirForm($("form-acao").hidden); });
  $("btn-cancelar-acao").addEventListener("click", function () { abrirForm(false); });
  $("form-acao").addEventListener("submit", criar);
})();
