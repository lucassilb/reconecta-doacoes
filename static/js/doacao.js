/* ReConecta — detalhe de um pedido de doação (/doacoes/<id>) e questionário curto para doar.
   O servidor é a fonte da verdade; a validação aqui só adianta o que ele vai conferir. */
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
    var init = { method: opcoes.method || "GET", credentials: "same-origin", headers: { "Accept": "application/json" } };
    if (opcoes.form) init.body = opcoes.form;
    return fetch(url, init).then(function (r) {
      return r.text().then(function (t) {
        var c = null;
        try { c = t ? JSON.parse(t) : null; } catch (e) { c = null; }
        return { status: r.status, ok: r.ok, corpo: c == null ? {} : c };
      });
    });
  }

  /* ---------- formatação ---------- */

  function nome(n) { var R = window.ReConecta; return R && R.nomeTitulo ? R.nomeTitulo(n) : String(n || ""); }
  function local(mu) { if (!mu) return ""; var p = String(mu).split("/"); return nome(p[0]) + (p[1] ? " / " + p[1].toUpperCase() : ""); }
  function data(iso) { return window.ReConecta.dataBrasilia(iso); }
  function dataLonga(iso) { var d = data(iso); return d ? d.toLocaleDateString("pt-BR", { timeZone: window.ReConecta.fuso, day: "2-digit", month: "long", year: "numeric" }) : ""; }
  function hojeISO() { return window.ReConecta.diaISO(new Date()); }
  var numero = new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 2 });
  var PLURAL = { unidade: "unidades", pacote: "pacotes", caixa: "caixas" };
  function unidade(u, n) { return PLURAL[u] && Number(n) !== 1 ? PLURAL[u] : (u || ""); }
  function qtd(n, u) { return numero.format(Number(n) || 0) + " " + unidade(u, n); }
  function plural(n, um, varios) { return n + " " + (n === 1 ? um : varios); }
  function listaNomes(itens) {
    var nomes = itens.map(function (i) { return i.nome; });
    if (nomes.length <= 1) return nomes.join("");
    return nomes.slice(0, -1).join(", ") + " e " + nomes[nomes.length - 1].toLowerCase();
  }
  var IMG = { "Hortifrúti": "hortifruti", "Padaria": "padaria", "Laticínios": "laticinios", "Carnes e peixes": "carnes",
    "Grãos e cereais": "graos", "Refeições prontas": "refeicoes", "Bebidas não alcoólicas": "bebidas", "Outros": "outros" };

  var m = location.pathname.match(/\/doacoes\/(\d+)/);
  var ID = m ? m[1] : null;
  var pedido = null;

  /* ---------- o pedido ---------- */

  function itemPedido(i) {
    var meta = Number(i.quantidade) || 0;
    var recebido = Number(i.recebido) || 0;
    var faltam = i.faltam != null ? Number(i.faltam) : Math.max(0, meta - recebido);
    var pct = meta > 0 ? Math.min(100, Math.round(recebido / meta * 100)) : 0;
    return el("li", { classe: "pedido-item" + (faltam <= 0 ? " pedido-item--completo" : "") }, [
      el("img", { classe: "pedido-item__img", src: "/static/img/doacoes/cat-" + (IMG[i.categoria] || "outros") + ".webp", alt: "", width: "40", height: "40" }),
      el("div", { classe: "pedido-item__texto" }, [
        el("p", { classe: "pedido-item__linha" }, [el("strong", { texto: i.nome }), el("span", { texto: numero.format(recebido) + " de " + qtd(meta, i.unidade_medida) })]),
        el("div", { classe: "barra", role: "progressbar", "aria-label": "Recebido de " + i.nome, "aria-valuemin": "0", "aria-valuemax": String(meta), "aria-valuenow": String(Math.min(recebido, meta)), "aria-valuetext": numero.format(recebido) + " de " + qtd(meta, i.unidade_medida) }, [
          el("span", { classe: "barra__cheia", style: "width:" + pct + "%" })
        ]),
        el("p", { classe: "pedido-item__falta", texto: faltam > 0 ? "Faltam " + qtd(faltam, i.unidade_medida) : "Meta atingida. Doações a mais continuam bem-vindas." })
      ])
    ]);
  }

  function preencher(p) {
    pedido = p;
    var itens = p.itens || [];
    var titulo = itens.length ? "Pedido de " + listaNomes(itens).toLowerCase() : "Pedido de doação";
    document.title = titulo + " · ReConecta";
    $("det-titulo").textContent = titulo;
    var emp = p.empresa || {};
    $("det-empresa").replaceChildren(el("span", { classe: "det__empresa-icone", "aria-hidden": "true" }), el("span", null, [
      "Pedido de ", el("strong", { texto: nome(emp.nome) }), emp.municipio_uf ? " · " + local(emp.municipio_uf) : ""]));
    $("det-empresa").firstChild.innerHTML = '<svg viewBox="0 0 24 24" focusable="false"><path d="M4 9.5 5.6 5A1.6 1.6 0 0 1 7.1 4h9.8a1.6 1.6 0 0 1 1.5 1L20 9.5M4 9.5h16v1a2.7 2.7 0 0 1-5.3 0 2.7 2.7 0 0 1-5.4 0A2.7 2.7 0 0 1 4 10.5zM5.5 13.5V20h13v-6.5M10 20v-4h4v4" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linejoin="round"/></svg>';
    var prazo = p.receber_ate || p.data_limite_retirada;
    $("det-prazo").textContent = dataLonga(prazo);
    $("det-entrega").textContent = (emp.municipio_uf ? local(emp.municipio_uf) + ". " : "") + "O endereço completo aparece depois que a doação é confirmada.";
    var n = Number(p.doacoes_recebidas) || 0;
    $("det-contagem").textContent = plural(n, "doação recebida", "doações recebidas");
    $("det-itens").replaceChildren.apply($("det-itens"), itens.map(itemPedido));

    // itens do formulário
    var sel = $("c-item"), atual = sel.value;
    sel.replaceChildren(el("option", { value: "", texto: itens.length > 1 ? "Escolha o item" : "Item" }));
    itens.forEach(function (i) {
      var faltam = i.faltam != null ? Number(i.faltam) : null;
      sel.appendChild(el("option", { value: String(i.id), texto: i.nome + (faltam != null ? (faltam > 0 ? " (faltam " + qtd(faltam, i.unidade_medida) + ")" : " (meta atingida)") : "") }));
    });
    if (atual) sel.value = atual;
    else if (itens.length === 1) sel.value = String(itens[0].id);
    atualizarUnidade();

    estadoInicial(p);
    $("det-carregando").hidden = true;
    $("det").hidden = false;
  }

  /* sem sessão o servidor manda pode_doar=false com "Entre para doar" (ou omite o campo) */
  function estadoInicial(p) {
    var logado = p.pode_doar !== undefined && p.motivo_bloqueio !== "Entre para doar";
    ["btn-abrir", "link-entrar", "doar-bloqueio", "doar-cadastro"].forEach(function (id) { $(id).hidden = true; });
    if (!logado) {
      $("link-entrar").href = "/entrar?proximo=" + encodeURIComponent("/doacoes/" + p.id);
      $("link-entrar").hidden = false;
      $("doar-cadastro").hidden = false;
    } else if (p.pode_doar) {
      $("btn-abrir").hidden = false;
    } else {
      $("doar-bloqueio").textContent = p.motivo_bloqueio || "Você não pode doar para este pedido.";
      $("doar-bloqueio").hidden = false;
    }
  }

  function mostrarErroCarga(titulo, texto) {
    $("det-carregando").hidden = true;
    var e = $("det-erro");
    e.replaceChildren(el("p", { classe: "aviso__titulo", texto: titulo }), el("p", { texto: texto }),
      el("a", { classe: "btn btn--secundario btn--pequeno", href: "/#doacoes" }, ["Ver doações disponíveis"]));
    e.hidden = false;
  }

  function carregar() {
    if (!ID) { mostrarErroCarga("Pedido não encontrado", "O endereço desta página está incompleto."); return Promise.resolve(); }
    return requisitar("/reconecta/publico/doacoes/" + ID).then(function (r) {
      if (r.status === 404) { mostrarErroCarga("Pedido não encontrado", "Ele pode ter sido encerrado ou removido."); return; }
      if (!r.ok) throw new Error("HTTP " + r.status);
      preencher(r.corpo);
    }).catch(function () { mostrarErroCarga("Não conseguimos carregar este pedido", "Verifique sua conexão e recarregue a página."); });
  }

  /* ---------- questionário ---------- */

  var PERGUNTAS = [
    ["dentro_validade", "O alimento está dentro da validade?"],
    ["embalagem_ok", "A embalagem está fechada e sem danos (ou, se for in natura, sem sinais de estrago)?"],
    ["armazenado_ok", "Foi guardado do jeito certo (geladeira ou congelador quando precisa)?"],
    ["nao_caseiro", "Não é comida feita em casa?"]
  ];
  var AVISO_NAO = {
    dentro_validade: "Alimento fora da validade não pode ser doado.",
    embalagem_ok: "Só aceitamos embalagem fechada e sem danos, ou alimento in natura sem estrago.",
    armazenado_ok: "O alimento precisa ter sido guardado do jeito certo.",
    nao_caseiro: "Por segurança, comida feita em casa não pode ser doada."
  };
  var TIPOS_FOTO = ["image/jpeg", "image/png", "image/webp"];
  var MAX_FOTO = 5 * 1024 * 1024;
  var CAMPO_INPUT = { item_id: "c-item", quantidade: "c-quantidade", validade: "c-validade", foto: "c-foto" };

  function montarPerguntas() {
    var alvo = $("quest-perguntas");
    PERGUNTAS.forEach(function (p, i) {
      var chave = p[0];
      var aviso = el("p", { classe: "pergunta__aviso", id: "q-" + chave + "-aviso", "aria-live": "polite" });
      var fs;
      function opcao(valor, rotulo) {
        var input = el("input", { type: "radio", name: chave, value: valor, classe: "pergunta__radio", id: "q-" + chave + "-" + valor });
        input.addEventListener("change", function () {
          aviso.textContent = valor === "nao" ? AVISO_NAO[chave] + " Com essa resposta a doação não será aceita." : "";
          fs.classList.toggle("pergunta--nao", valor === "nao");
          fs.classList.remove("pergunta--erro");
        });
        return el("label", { classe: "pergunta__opcao pergunta__opcao--" + valor, "for": input.id }, [input, el("span", { texto: rotulo })]);
      }
      fs = el("fieldset", { classe: "pergunta", id: "q-" + chave, "aria-describedby": "q-" + chave + "-aviso" }, [
        el("legend", { classe: "pergunta__texto" }, [el("span", { classe: "pergunta__n", "aria-hidden": "true", texto: String(i + 1) }), p[1]]),
        el("div", { classe: "pergunta__opcoes" }, [opcao("sim", "Sim"), opcao("nao", "Não")]),
        aviso
      ]);
      alvo.appendChild(fs);
    });
  }

  function itemEscolhido() {
    var id = $("c-item").value;
    return (pedido && pedido.itens || []).filter(function (i) { return String(i.id) === id; })[0] || null;
  }
  function atualizarUnidade() {
    var i = itemEscolhido();
    $("c-unidade").textContent = i ? "(" + unidade(i.unidade_medida, 2) + ")" : "";
  }

  var fotoUrl = null;
  function validarFoto(f) {
    if (!f) return "Mande uma foto do alimento.";
    if (TIPOS_FOTO.indexOf(f.type) === -1) return "A foto precisa ser JPEG, PNG ou WebP.";
    if (f.size > MAX_FOTO) return "A foto pode ter no máximo 5 MB.";
    return "";
  }
  function atualizarFoto() {
    var f = $("c-foto").files && $("c-foto").files[0], previa = $("c-foto-previa");
    if (fotoUrl) { URL.revokeObjectURL(fotoUrl); fotoUrl = null; }
    erroCampo("foto", "");
    if (!f) { $("c-foto-nome").textContent = "Tirar ou escolher foto"; previa.classList.remove("foto__previa--img"); previa.style.backgroundImage = ""; return; }
    $("c-foto-nome").textContent = f.name.length > 40 ? f.name.slice(0, 37) + "…" : f.name;
    if (TIPOS_FOTO.indexOf(f.type) !== -1) {
      fotoUrl = URL.createObjectURL(f);
      previa.style.backgroundImage = "url(\"" + fotoUrl + "\")";
      previa.classList.add("foto__previa--img");
    }
    var msg = validarFoto(f);
    if (msg) erroCampo("foto", msg);
  }

  function erroCampo(campo, msg) {
    var id = CAMPO_INPUT[campo];
    if (id) {
      var input = $(id), p = $(id + "-erro");
      if (msg) input.setAttribute("aria-invalid", "true"); else input.removeAttribute("aria-invalid");
      if (p) p.textContent = msg || "";
      return input;
    }
    var fs = $("q-" + campo);
    if (fs) {
      fs.classList.toggle("pergunta--erro", !!msg);
      if (msg) $("q-" + campo + "-aviso").textContent = msg;
      return fs.querySelector("input");
    }
    return null;
  }
  function esconderAviso() { $("quest-aviso").hidden = true; $("quest-aviso").replaceChildren(); }
  function limparErros() {
    Object.keys(CAMPO_INPUT).forEach(function (c) { erroCampo(c, ""); });
    PERGUNTAS.forEach(function (p) { $("q-" + p[0]).classList.remove("pergunta--erro"); });
    esconderAviso();
  }
  function resposta(chave) { var r = document.querySelector('input[name="' + chave + '"]:checked'); return r ? r.value : ""; }

  function validar() {
    var c = {};
    if (!itemEscolhido()) c.item_id = "Escolha o item que você vai doar.";
    var q = Number(String($("c-quantidade").value).replace(",", "."));
    if (!$("c-quantidade").value.trim() || isNaN(q) || q <= 0) c.quantidade = "A quantidade precisa ser maior que zero.";
    var v = $("c-validade").value;
    if (!v) c.validade = "Informe a validade do alimento.";
    else if (v < hojeISO()) c.validade = "Alimento vencido não pode ser doado.";
    PERGUNTAS.forEach(function (p) { if (!resposta(p[0])) c[p[0]] = "Responda sim ou não."; });
    var fm = validarFoto($("c-foto").files && $("c-foto").files[0]);
    if (fm) c.foto = fm;
    return c;
  }
  function aplicarCampos(campos) {
    var primeiro = null;
    Object.keys(campos).forEach(function (k) { var i = erroCampo(k === "item" ? "item_id" : k, campos[k]); if (i && !primeiro) primeiro = i; });
    if (primeiro) primeiro.focus();
    else if (Object.keys(campos).length) mostrarAviso("Confira os dados", [campos[Object.keys(campos)[0]]], false);
  }
  function mostrarAviso(titulo, linhas, recusa) {
    var a = $("quest-aviso");
    a.className = "quest__aviso" + (recusa ? " quest__aviso--recusa" : "");
    a.replaceChildren(el("p", { classe: "quest__aviso-titulo", texto: titulo }),
      el("ul", null, linhas.map(function (l) { return el("li", { texto: l }); })),
      recusa ? el("p", { classe: "quest__aviso-rodape", texto: "Nada foi registrado. Se for possível corrigir, ajuste as respostas e tente de novo." }) : null);
    a.hidden = false;
    a.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }

  function abrir() { $("doar-inicio").hidden = true; $("form-contribuicao").hidden = false; $("c-item").focus(); }
  function cancelar() { $("form-contribuicao").hidden = true; $("doar-inicio").hidden = false; $("doar-titulo").focus(); }

  function enviar(e) {
    e.preventDefault();
    limparErros();
    var campos = validar();
    if (Object.keys(campos).length) { aplicarCampos(campos); return; }
    var fd = new FormData();
    fd.append("item_id", $("c-item").value);
    fd.append("quantidade", String(Number(String($("c-quantidade").value).replace(",", "."))));
    fd.append("validade", $("c-validade").value);
    PERGUNTAS.forEach(function (p) { fd.append(p[0], resposta(p[0])); });
    fd.append("foto", $("c-foto").files[0]);

    var btn = $("btn-doar");
    btn.disabled = true; btn.classList.add("is-carregando");
    requisitar("/reconecta/publico/doacoes/" + ID + "/contribuicoes", { method: "POST", form: fd }).then(function (r) {
      var c = r.corpo;
      if (r.status === 201) { confirmar(c); return; }
      if (r.status === 422) {
        var motivos = (c.motivos || []).map(function (mo) { return mo.mensagem; });
        mostrarAviso("Desta vez a doação não pode ser aceita", motivos.length ? motivos : [c.mensagem || "O alimento não atende às regras de doação."], true);
      } else if (r.status === 400 && c.campos) {
        aplicarCampos(c.campos);
      } else if (r.status === 401) {
        location.href = "/entrar?proximo=" + encodeURIComponent("/doacoes/" + ID);
      } else if (r.status === 413) {
        erroCampo("foto", "A foto é grande demais. Use uma de até 5 MB.");
      } else if (r.status === 409 || r.status === 403) {
        mostrarAviso("Não foi possível doar para este pedido", [c.mensagem || "Este pedido não aceita a sua doação."], false);
      } else {
        mostrarAviso("Não foi possível concluir", [c.mensagem || "Tente novamente em alguns instantes."], false);
      }
    }).catch(function () {
      mostrarAviso("Não conseguimos falar com o servidor", ["Verifique sua conexão e tente de novo."], false);
    }).then(function () { btn.disabled = false; btn.classList.remove("is-carregando"); });
  }

  function confirmar(c) {
    var ent = c.entrega || {};
    $("ok-endereco").textContent = ent.endereco || "O endereço está em Minhas doações, no painel.";
    $("ok-prazo").textContent = dataLonga(ent.receber_ate || (pedido && (pedido.receber_ate || pedido.data_limite_retirada)));
    $("form-contribuicao").hidden = true;
    $("doar-ok").hidden = false;
    $("doar-ok").focus();
    // atualiza o progresso dos itens sem tirar a confirmação da tela
    requisitar("/reconecta/publico/doacoes/" + ID).then(function (r) {
      if (!r.ok) return;
      pedido = r.corpo;
      $("det-itens").replaceChildren.apply($("det-itens"), (pedido.itens || []).map(itemPedido));
      var n = Number(pedido.doacoes_recebidas) || 0;
      $("det-contagem").textContent = plural(n, "doação recebida", "doações recebidas");
    }).catch(function () {});
  }

  montarPerguntas();
  $("c-validade").min = hojeISO();
  Object.keys(CAMPO_INPUT).forEach(function (c) {
    if (c === "foto") return;
    var i = $(CAMPO_INPUT[c]);
    ["input", "change"].forEach(function (ev) { i.addEventListener(ev, function () { if (i.getAttribute("aria-invalid")) erroCampo(c, ""); }); });
  });
  $("c-item").addEventListener("change", atualizarUnidade);
  $("c-foto").addEventListener("change", atualizarFoto);
  $("btn-abrir").addEventListener("click", abrir);
  $("btn-cancelar").addEventListener("click", cancelar);
  $("form-contribuicao").addEventListener("submit", enviar);
  carregar();
})();
